from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.agents.client import OtariClient, OtariMetadata
from competitor_scout.agents.contracts import (
    ChildTaskKind,
    ChildTaskResult,
    DiscoveredSource,
    PlannedChildTask,
    ScoutPlan,
    SourceDiscoveryResult,
    SynthesisResult,
)
from competitor_scout.agents.prompts import (
    PROMPT_VERSION,
    UNTRUSTED_SOURCE_POLICY,
    child_messages,
    planning_messages,
    synthesis_messages,
)
from competitor_scout.agents.session_labels import scout_run_session_label
from competitor_scout.agents.validation import NormalizedEvidence, validate_evidence_scope
from competitor_scout.config import Settings
from competitor_scout.db import SessionFactory
from competitor_scout.models.intelligence import (
    AgentTask,
    AgentTaskRole,
    AgentTaskStatus,
    ApprovalStatus,
    Competitor,
    CompetitorStatus,
    EvidenceItem,
    Finding,
    MonitoredSource,
    RunType,
    ScoutRun,
    ScoutRunStatus,
    UsageEvent,
)
from competitor_scout.schemas.findings import EvidencePublication, FindingPublication
from competitor_scout.security.urls import (
    UnsafeSourceUrl,
    same_registrable_domain,
    validate_public_https_url,
)
from competitor_scout.services.findings import PublicationValidationError, public_source_domain

type UrlValidator = Callable[[str], Awaitable[str]]
type Sleeper = Callable[[float], Awaitable[None]]
type CostEstimator = Callable[[str, int, bool], Decimal | None]


class FindingPublisher(Protocol):
    async def publish(
        self,
        *,
        user_id: uuid.UUID,
        competitor_id: uuid.UUID,
        scout_run_id: uuid.UUID,
        finding: FindingPublication,
        evidence: list[EvidencePublication],
        published_at: datetime,
    ) -> object: ...


class PlanValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_scout_plan(
    plan: ScoutPlan,
    *,
    approved_urls: set[str],
    max_tasks: int,
    max_search_calls: int,
) -> None:
    if len(plan.tasks) > max_tasks:
        raise PlanValidationError("invalid_plan_limits")
    for task in plan.tasks:
        if task.max_search_calls > max_search_calls:
            raise PlanValidationError("invalid_plan_limits")
        if task.kind is ChildTaskKind.FIRST_PARTY_SOURCE_REVIEW and any(
            str(url) not in approved_urls for url in task.source_urls
        ):
            raise PlanValidationError("invalid_plan_scope")


@dataclass
class _UsageAccumulator:
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    settled_cost_usd: Decimal = Decimal("0")
    has_usage: bool = False
    tool_calls_known: bool = True
    cost_known: bool = True
    estimated_cost_usd: Decimal = Decimal("0")

    def add(self, metadata: OtariMetadata) -> None:
        usage = metadata.usage
        self.has_usage = True
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        if usage.tool_calls is None:
            self.tool_calls_known = False
        elif self.tool_calls_known:
            self.tool_calls += usage.tool_calls
        if usage.cost_usd is None:
            self.cost_known = False
        elif self.cost_known:
            self.settled_cost_usd += usage.cost_usd

    def mark_unsettled(self) -> None:
        self.has_usage = True
        self.tool_calls_known = False
        self.cost_known = False

    @property
    def recorded_tool_calls(self) -> int | None:
        return self.tool_calls if self.has_usage and self.tool_calls_known else None

    @property
    def recorded_cost(self) -> Decimal | None:
        return self.settled_cost_usd if self.has_usage and self.cost_known else None


@dataclass(frozen=True)
class _RunContext:
    run_id: uuid.UUID
    user_id: uuid.UUID
    competitor_id: uuid.UUID
    competitor_name: str
    competitor_description: str
    competitor_domain: str
    approved_urls: tuple[str, ...]
    recent_findings: tuple[dict[str, object], ...]
    last_run_summary: dict[str, object] | None
    planner_task_id: uuid.UUID
    initial_daily_cost: Decimal


@dataclass(frozen=True)
class _AcceptedEvidence:
    task_id: uuid.UUID
    evidence: NormalizedEvidence


@dataclass(frozen=True)
class _ChildOutcome:
    accepted: tuple[_AcceptedEvidence, ...] = ()
    metadata: tuple[OtariMetadata, ...] = ()
    failed: bool = False
    unsettled_attempt: bool = False
    cost_stopped: bool = False


class ScoutOrchestrator:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        client: OtariClient,
        settings: Settings,
        publisher: FindingPublisher,
        url_validator: UrlValidator = validate_public_https_url,
        now: Callable[[], datetime] | None = None,
        sleep: Sleeper | None = None,
        cost_estimator: CostEstimator | None = None,
    ) -> None:
        self._sessions = session_factory
        self._client = client
        self._settings = settings
        self._publisher = publisher
        self._url_validator = url_validator
        self._now = now or (lambda: datetime.now(UTC))
        self._sleep = sleep or asyncio.sleep
        self._cost_estimator = cost_estimator
        # Deployment invariant: this shared instance is the process-wide permit owner.
        # Run one worker replica until Otari concurrency is backed by a shared permit.
        self._child_semaphore = asyncio.Semaphore(
            min(settings.max_concurrent_child_tasks, settings.max_otari_concurrency)
        )

    async def execute_daily_run(self, run_id: uuid.UUID) -> ScoutRunStatus:
        usage = _UsageAccumulator()
        context = await self._start_run(run_id)
        if context is None:
            return await self._run_status(run_id)

        plan = await self._plan(context, usage)
        if plan is None:
            await self._apply_usage(run_id, usage)
            return await self._run_status(run_id)
        if self._run_budget_reached(context, usage):
            await self._fail_run(run_id, "run_cost_limit", usage)
            return ScoutRunStatus.FAILED

        children = await self._create_child_tasks(context, plan)
        outcomes: list[_ChildOutcome] = []
        budget_stopped = False
        budget_reason = "run_cost_limit"
        wave_size = self._settings.max_concurrent_child_tasks
        for offset in range(0, len(children), wave_size):
            wave = children[offset : offset + wave_size]
            wave_outcomes = await asyncio.gather(
                *(
                    self._execute_child(context, task_id, planned, usage)
                    for task_id, planned in wave
                )
            )
            outcomes.extend(wave_outcomes)
            if any(outcome.cost_stopped for outcome in wave_outcomes):
                remaining_ids = [task_id for task_id, _planned in children[offset + wave_size :]]
                await self._cancel_tasks(remaining_ids, "cost_ceiling_reached")
                budget_stopped = True
                budget_reason = "cost_ceiling_reached"
            for outcome in wave_outcomes:
                for metadata in outcome.metadata:
                    usage.add(metadata)
                if outcome.unsettled_attempt:
                    usage.mark_unsettled()
            if budget_stopped:
                break
            if self._run_budget_reached(context, usage):
                remaining_ids = [task_id for task_id, _planned in children[offset + wave_size :]]
                await self._cancel_tasks(remaining_ids, "run_cost_limit")
                budget_stopped = True
                break
        child_failed = any(outcome.failed for outcome in outcomes)
        accepted = self._deduplicate_evidence(outcomes)
        await self._persist_evidence(context, accepted)
        await self._apply_usage(run_id, usage)
        if not accepted:
            if budget_stopped:
                await self._finish_run(
                    run_id,
                    ScoutRunStatus.PARTIAL,
                    usage,
                    partial_reasons=[budget_reason],
                )
                return ScoutRunStatus.PARTIAL
            code = "no_valid_evidence"
            await self._fail_run(run_id, code, usage)
            return ScoutRunStatus.FAILED
        if budget_stopped:
            await self._finish_run(
                run_id,
                ScoutRunStatus.PARTIAL,
                usage,
                partial_reasons=[budget_reason],
            )
            return ScoutRunStatus.PARTIAL

        synthesis = await self._synthesize(context, accepted, usage)
        if synthesis is None:
            await self._apply_usage(run_id, usage)
            return await self._run_status(run_id)
        try:
            await self._publish(context, synthesis, accepted)
        except Exception:
            await self._fail_run(run_id, "publication_failed", usage)
            return ScoutRunStatus.FAILED

        partial_reasons = ["child_task_failed"] if child_failed else []
        if self._run_budget_reached(context, usage):
            partial_reasons.append("run_cost_limit")
        final_status = ScoutRunStatus.PARTIAL if partial_reasons else ScoutRunStatus.COMPLETED
        await self._finish_run(
            run_id,
            final_status,
            usage,
            partial_reasons=partial_reasons,
        )
        return final_status

    async def _start_run(self, run_id: uuid.UUID) -> _RunContext | None:
        now = self._current_time()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        async with self._sessions.begin() as session:
            run = await session.scalar(
                select(ScoutRun).where(ScoutRun.id == run_id).with_for_update()
            )
            if run is None or run.run_type not in {RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT}:
                raise ValueError("daily Scout Run was not found")
            if run.status in {
                ScoutRunStatus.PLANNING,
                ScoutRunStatus.GATHERING,
                ScoutRunStatus.SYNTHESIZING,
            }:
                # A live handler owns and renews the job lease. Re-entry at an
                # intermediate state therefore represents recovery after lease loss.
                await self._terminalize_interrupted_run(session, run, now)
                return None
            if run.status is not ScoutRunStatus.QUEUED:
                return None
            competitor = await session.get(Competitor, run.competitor_id)
            if competitor is not None and run.user_id != competitor.user_id:
                run.status = ScoutRunStatus.FAILED
                run.failure_code = "run_ownership_mismatch"
                run.failure_summary = "Scout Run ownership is invalid"
                run.completed_at = now
                return None
            if competitor is None or competitor.status is not CompetitorStatus.ACTIVE:
                run.status = ScoutRunStatus.FAILED
                run.failure_code = "competitor_inactive"
                run.failure_summary = "competitor is not active"
                run.completed_at = now
                return None
            daily_cost = await session.scalar(
                select(func.coalesce(func.sum(UsageEvent.settled_cost_usd), 0)).where(
                    UsageEvent.user_id == run.user_id,
                    UsageEvent.occurred_at >= day_start,
                    UsageEvent.occurred_at < day_start + timedelta(days=1),
                )
            )
            initial_daily_cost = Decimal(daily_cost or 0)
            if initial_daily_cost >= self._settings.max_user_daily_cost_usd:
                run.status = ScoutRunStatus.FAILED
                run.failure_code = "daily_cost_limit"
                run.failure_summary = "daily settled-cost limit reached"
                run.completed_at = now
                return None
            approved_urls = tuple(
                (
                    await session.scalars(
                        select(MonitoredSource.normalized_url)
                        .where(
                            MonitoredSource.competitor_id == competitor.id,
                            MonitoredSource.approval_status == ApprovalStatus.APPROVED,
                        )
                        .order_by(MonitoredSource.created_at, MonitoredSource.id)
                        .limit(160)
                    )
                ).all()
            )
            recent_finding_rows = list(
                (
                    await session.execute(
                        select(
                            Finding.category,
                            Finding.title,
                            Finding.normalized_claim_fingerprint,
                            Finding.last_seen_at,
                        )
                        .where(Finding.competitor_id == competitor.id)
                        .order_by(Finding.published_at.desc(), Finding.id.desc())
                        .limit(20)
                    )
                ).all()
            )
            recent_findings = tuple(
                {
                    "category": category.value,
                    "title": title,
                    "claim_fingerprint": fingerprint,
                    "last_seen_at": last_seen_at.isoformat(),
                }
                for category, title, fingerprint, last_seen_at in recent_finding_rows
            )
            previous_run = await session.scalar(
                select(ScoutRun)
                .where(
                    ScoutRun.competitor_id == competitor.id,
                    ScoutRun.id != run.id,
                    ScoutRun.status.in_(
                        [
                            ScoutRunStatus.COMPLETED,
                            ScoutRunStatus.PARTIAL,
                            ScoutRunStatus.FAILED,
                        ]
                    ),
                )
                .order_by(ScoutRun.scheduled_for.desc(), ScoutRun.id.desc())
                .limit(1)
            )
            last_run_summary = (
                {
                    "status": previous_run.status.value,
                    "failure_code": previous_run.failure_code,
                    "partial_reasons": previous_run.partial_reasons,
                    "completed_at": (
                        previous_run.completed_at.isoformat()
                        if previous_run.completed_at is not None
                        else None
                    ),
                }
                if previous_run is not None
                else None
            )
            run.status = ScoutRunStatus.PLANNING
            run.started_at = now
            planner = AgentTask(
                scout_run_id=run.id,
                role=AgentTaskRole.MAIN_PLANNER,
                task_kind="daily_planning",
                status=AgentTaskStatus.RUNNING,
                model=self._settings.otari_main_model,
                objective="Create a bounded daily Scout plan",
                source_scope=list(approved_urls),
                started_at=now,
            )
            session.add(planner)
            await session.flush()
            return _RunContext(
                run_id=run.id,
                user_id=run.user_id,
                competitor_id=competitor.id,
                competitor_name=competitor.name,
                competitor_description=competitor.description,
                competitor_domain=competitor.primary_domain,
                approved_urls=approved_urls,
                recent_findings=recent_findings,
                last_run_summary=last_run_summary,
                planner_task_id=planner.id,
                initial_daily_cost=initial_daily_cost,
            )

    @staticmethod
    async def _terminalize_interrupted_run(
        session: AsyncSession,
        run: ScoutRun,
        completed_at: datetime,
    ) -> None:
        interrupted_status = run.status
        tasks = list(
            (
                await session.scalars(
                    select(AgentTask)
                    .where(
                        AgentTask.scout_run_id == run.id,
                        AgentTask.status.in_([AgentTaskStatus.QUEUED, AgentTaskStatus.RUNNING]),
                    )
                    .with_for_update()
                )
            ).all()
        )
        for task in tasks:
            task.status = (
                AgentTaskStatus.FAILED
                if task.status is AgentTaskStatus.RUNNING
                else AgentTaskStatus.CANCELLED
            )
            task.completed_at = completed_at
            task.error_code = "interrupted_scout_run"
            task.error_summary = "Scout Run was interrupted"

        run.completed_at = completed_at
        if interrupted_status is ScoutRunStatus.SYNTHESIZING:
            run.status = ScoutRunStatus.PARTIAL
            run.failure_code = None
            run.failure_summary = None
            reasons = [str(reason) for reason in run.partial_reasons]
            if "interrupted_scout_run" not in reasons:
                reasons.append("interrupted_scout_run")
            run.partial_reasons = reasons
        else:
            run.status = ScoutRunStatus.FAILED
            run.failure_code = "interrupted_scout_run"
            run.failure_summary = "Scout Run was interrupted"
            run.partial_reasons = []

    async def _plan(
        self,
        context: _RunContext,
        usage: _UsageAccumulator,
    ) -> ScoutPlan | None:
        try:
            async with asyncio.timeout(self._settings.planning_deadline_seconds):
                return await self._plan_within_deadline(context, usage)
        except TimeoutError:
            usage.mark_unsettled()
            await self._fail_task(context.planner_task_id, "planning_timeout")
            await self._fail_run(context.run_id, "planning_timeout", usage)
            return None

    async def _plan_within_deadline(
        self,
        context: _RunContext,
        usage: _UsageAccumulator,
    ) -> ScoutPlan | None:
        payload = {
            "competitor": {
                "name": context.competitor_name,
                "description": context.competitor_description,
                "primary_domain": context.competitor_domain,
            },
            "approved_first_party_urls": list(context.approved_urls),
            "allowed_task_kinds": [kind.value for kind in ChildTaskKind],
            "limits": {
                "max_tasks": self._settings.max_child_tasks_per_run,
                "max_search_calls_per_task": self._settings.max_child_search_calls,
            },
            "recent_findings": list(context.recent_findings),
            "last_run_summary": context.last_run_summary,
        }
        messages = planning_messages(payload)
        if self._estimated_tokens(messages) > self._settings.main_input_token_limit:
            await self._fail_task(context.planner_task_id, "main_input_token_limit")
            await self._fail_run(context.run_id, "main_input_token_limit", usage)
            return None
        unsettled_attempt = False
        for attempt in range(1, self._settings.max_planning_repairs + 2):
            if self._request_would_exceed_cost_ceiling(
                context,
                usage,
                model=self._settings.otari_main_model,
                max_completion_tokens=self._settings.main_output_token_limit,
                enable_web_search=False,
            ):
                await self._cancel_tasks(
                    [context.planner_task_id],
                    "cost_ceiling_reached",
                )
                await self._finish_run(
                    context.run_id,
                    ScoutRunStatus.PARTIAL,
                    usage,
                    partial_reasons=["cost_ceiling_reached"],
                )
                return None
            metadata: OtariMetadata | None = None
            plan: ScoutPlan | None = None
            await self._set_task_attempt(context.planner_task_id, attempt)
            try:
                plan, metadata = await self._client.structured_completion(
                    model=self._settings.otari_main_model,
                    messages=messages,
                    output_type=ScoutPlan,
                    session_label=scout_run_session_label(context.run_id),
                    max_completion_tokens=self._settings.main_output_token_limit,
                    deadline_seconds=self._settings.planning_deadline_seconds,
                    enable_web_search=False,
                )
                usage.add(metadata)
                validate_scout_plan(
                    plan,
                    approved_urls=set(context.approved_urls),
                    max_tasks=self._settings.max_child_tasks_per_run,
                    max_search_calls=self._settings.max_child_search_calls,
                )
                if metadata.usage.input_tokens > self._settings.main_input_token_limit:
                    raise PlanValidationError("main_input_token_limit")
            except PlanValidationError as error:
                await self._fail_task(
                    context.planner_task_id,
                    error.code,
                    context=context,
                    metadata=metadata,
                    unsettled=unsettled_attempt,
                )
                await self._fail_run(context.run_id, error.code, usage)
                return None
            except Exception as error:
                unsettled_attempt = True
                usage.mark_unsettled()
                code = self._safe_error_code(error, "planning_failed")
                repairable = code in {"otari_schema_error", "otari_invalid_response"}
                if repairable and attempt <= self._settings.max_planning_repairs:
                    continue
                await self._fail_task(context.planner_task_id, code)
                await self._fail_run(context.run_id, code, usage)
                return None
            if plan is None or metadata is None:
                raise RuntimeError("planning response metadata was not resolved")
            await self._succeed_task(
                context,
                context.planner_task_id,
                metadata,
                plan.model_dump(mode="json"),
                unsettled=unsettled_attempt,
            )
            return plan
        return None

    async def _create_child_tasks(
        self,
        context: _RunContext,
        plan: ScoutPlan,
    ) -> list[tuple[uuid.UUID, PlannedChildTask]]:
        created: list[tuple[uuid.UUID, PlannedChildTask]] = []
        async with self._sessions.begin() as session:
            run = await session.get(ScoutRun, context.run_id)
            if run is None:
                raise RuntimeError("Scout Run disappeared")
            for planned in plan.tasks:
                scope = (
                    [str(url) for url in planned.source_urls]
                    if planned.source_urls
                    else [f"search:{planned.search_query}"]
                )
                task = AgentTask(
                    scout_run_id=context.run_id,
                    parent_task_id=context.planner_task_id,
                    role=AgentTaskRole.CHILD_RESEARCHER,
                    task_kind=planned.kind.value,
                    model=self._settings.otari_child_model,
                    objective=planned.objective,
                    source_scope=scope,
                )
                session.add(task)
                await session.flush()
                created.append((task.id, planned))
            run.status = ScoutRunStatus.GATHERING
        return created

    async def _execute_child(
        self,
        context: _RunContext,
        task_id: uuid.UUID,
        planned: PlannedChildTask,
        usage: _UsageAccumulator,
    ) -> _ChildOutcome:
        try:
            async with asyncio.timeout(self._settings.child_deadline_seconds):
                return await self._execute_child_within_deadline(
                    context,
                    task_id,
                    planned,
                    usage,
                )
        except TimeoutError:
            await self._fail_task(task_id, "child_timeout")
            return _ChildOutcome(failed=True, unsettled_attempt=True)

    async def _execute_child_within_deadline(
        self,
        context: _RunContext,
        task_id: uuid.UUID,
        planned: PlannedChildTask,
        usage: _UsageAccumulator,
    ) -> _ChildOutcome:
        metadata_records: list[OtariMetadata] = []
        unsettled = False
        deadline = asyncio.get_running_loop().time() + self._settings.child_deadline_seconds
        async with self._child_semaphore:
            for attempt in range(1, self._settings.max_child_retries + 2):
                metadata: OtariMetadata | None = None
                await self._set_task_attempt(task_id, attempt)
                try:
                    if self._request_would_exceed_cost_ceiling(
                        context,
                        usage,
                        model=self._settings.otari_child_model,
                        max_completion_tokens=self._settings.child_output_token_limit,
                        enable_web_search=True,
                    ):
                        await self._cancel_tasks([task_id], "cost_ceiling_reached")
                        return _ChildOutcome(cost_stopped=True)
                    messages = child_messages(
                        {
                            "task": planned.model_dump(mode="json"),
                            "competitor": {
                                "name": context.competitor_name,
                                "primary_domain": context.competitor_domain,
                            },
                            "recent_duplicate_hints": list(context.recent_findings),
                        }
                    )
                    if self._estimated_tokens(messages) > self._settings.child_input_token_limit:
                        raise PlanValidationError("child_input_token_limit")
                    result, metadata = await self._client.structured_completion(
                        model=self._settings.otari_child_model,
                        messages=messages,
                        output_type=ChildTaskResult,
                        session_label=scout_run_session_label(context.run_id),
                        max_completion_tokens=self._settings.child_output_token_limit,
                        deadline_seconds=self._settings.child_deadline_seconds,
                        enable_web_search=True,
                        max_tool_iterations=planned.max_search_calls + 1,
                    )
                    metadata_records.append(metadata)
                    if (
                        metadata.usage.tool_calls is not None
                        and metadata.usage.tool_calls > planned.max_search_calls
                    ):
                        raise PlanValidationError("child_tool_budget_exceeded")
                    await self._validate_child_inspection_scope(planned, result)
                    accepted, rejected = await validate_evidence_scope(
                        result.evidence,
                        approved_urls=(str(url) for url in planned.source_urls),
                        inspected_urls=(str(url) for url in result.sources_inspected),
                        task_kind=planned.kind,
                        url_validator=self._url_validator,
                    )
                    if metadata.usage.input_tokens > self._settings.child_input_token_limit:
                        raise PlanValidationError("child_input_token_limit")
                except Exception as error:
                    if metadata is None:
                        unsettled = True
                    code = self._safe_error_code(error, "child_task_failed")
                    retryable = bool(getattr(error, "retryable", False)) or code in {
                        "otari_schema_error",
                        "otari_invalid_response",
                    }
                    if retryable and attempt <= self._settings.max_child_retries:
                        delay = self._retry_delay(error, attempt)
                        if delay < deadline - asyncio.get_running_loop().time():
                            await self._sleep(delay)
                            continue
                    await self._fail_task(
                        task_id,
                        code,
                        context=context,
                        metadata=metadata,
                        unsettled=unsettled,
                    )
                    return _ChildOutcome(
                        metadata=tuple(metadata_records),
                        failed=True,
                        unsettled_attempt=unsettled,
                    )
                if metadata is None:
                    raise RuntimeError("child response metadata was not resolved")
                await self._succeed_task(
                    context,
                    task_id,
                    metadata,
                    {
                        "sources_inspected": [str(url) for url in result.sources_inspected],
                        "evidence": [
                            {
                                "source_url": item.source_url,
                                "source_title": item.source_title,
                                "source_type": item.source_type.value,
                                "quoted_text": item.quoted_text,
                                "normalized_claim": item.normalized_claim,
                                "published_at": (
                                    item.published_at.isoformat()
                                    if item.published_at is not None
                                    else None
                                ),
                                "confidence": item.confidence,
                                "limitations": list(item.limitations),
                                "fingerprint": item.fingerprint,
                            }
                            for item in accepted
                        ],
                        "rejected_reasons": [item.reason for item in rejected],
                    },
                    unsettled=unsettled,
                )
                return _ChildOutcome(
                    accepted=tuple(
                        _AcceptedEvidence(task_id=task_id, evidence=item) for item in accepted
                    ),
                    metadata=tuple(metadata_records),
                    unsettled_attempt=unsettled,
                )
        return _ChildOutcome(failed=True, unsettled_attempt=True)

    async def _validate_child_inspection_scope(
        self,
        planned: PlannedChildTask,
        result: ChildTaskResult,
    ) -> None:
        try:
            inspected = {await self._url_validator(str(url)) for url in result.sources_inspected}
            if planned.kind is ChildTaskKind.FIRST_PARTY_SOURCE_REVIEW:
                approved = {await self._url_validator(str(url)) for url in planned.source_urls}
                if not inspected.issubset(approved):
                    raise PlanValidationError("child_source_scope_violated")
        except PlanValidationError:
            raise
        except (UnsafeSourceUrl, TypeError, ValueError) as error:
            raise PlanValidationError("child_source_scope_violated") from error

    @staticmethod
    def _deduplicate_evidence(
        outcomes: Sequence[_ChildOutcome],
    ) -> list[_AcceptedEvidence]:
        accepted: list[_AcceptedEvidence] = []
        seen: set[tuple[str, str]] = set()
        for outcome in outcomes:
            for item in outcome.accepted:
                key = (item.evidence.source_url, item.evidence.fingerprint)
                if key in seen:
                    continue
                seen.add(key)
                accepted.append(item)
        return accepted

    async def _persist_evidence(
        self,
        context: _RunContext,
        accepted: Sequence[_AcceptedEvidence],
    ) -> None:
        captured_at = self._current_time()
        async with self._sessions.begin() as session:
            for item in accepted:
                evidence = item.evidence
                await session.execute(
                    insert(EvidenceItem)
                    .values(
                        user_id=context.user_id,
                        competitor_id=context.competitor_id,
                        scout_run_id=context.run_id,
                        agent_task_id=item.task_id,
                        source_url=evidence.source_url,
                        source_domain=public_source_domain(evidence.source_url),
                        source_title=evidence.source_title,
                        source_type=evidence.source_type,
                        published_at=evidence.published_at,
                        captured_at=captured_at,
                        quoted_text=evidence.quoted_text,
                        normalized_claim=evidence.normalized_claim,
                        content_fingerprint=evidence.fingerprint,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_evidence_items_competitor_source_fingerprint"
                    )
                )

    async def _synthesize(
        self,
        context: _RunContext,
        accepted: Sequence[_AcceptedEvidence],
        usage: _UsageAccumulator,
    ) -> SynthesisResult | None:
        task_id = await self._create_synthesis_task(context)
        try:
            async with asyncio.timeout(self._settings.synthesis_deadline_seconds):
                return await self._synthesize_within_deadline(
                    context,
                    task_id,
                    accepted,
                    usage,
                )
        except TimeoutError:
            usage.mark_unsettled()
            await self._fail_task(task_id, "synthesis_timeout")
            await self._fail_run(context.run_id, "synthesis_timeout", usage)
            return None

    async def _synthesize_within_deadline(
        self,
        context: _RunContext,
        task_id: uuid.UUID,
        accepted: Sequence[_AcceptedEvidence],
        usage: _UsageAccumulator,
    ) -> SynthesisResult | None:
        evidence_payload = [
            {
                "source_url": item.evidence.source_url,
                "source_title": item.evidence.source_title,
                "source_type": item.evidence.source_type.value,
                "quoted_text": item.evidence.quoted_text,
                "normalized_claim": item.evidence.normalized_claim,
                "published_at": (
                    item.evidence.published_at.isoformat()
                    if item.evidence.published_at is not None
                    else None
                ),
                "confidence": item.evidence.confidence,
                "fingerprint": item.evidence.fingerprint,
            }
            for item in accepted
        ]
        messages = synthesis_messages(
            {
                "competitor": {
                    "name": context.competitor_name,
                    "primary_domain": context.competitor_domain,
                },
                "validated_evidence": evidence_payload,
                "recent_finding_fingerprints": [
                    item["claim_fingerprint"] for item in context.recent_findings
                ],
            }
        )
        while (
            evidence_payload
            and self._estimated_tokens(messages) > self._settings.main_input_token_limit
        ):
            evidence_payload.pop()
            messages = synthesis_messages(
                {
                    "competitor": {
                        "name": context.competitor_name,
                        "primary_domain": context.competitor_domain,
                    },
                    "validated_evidence": evidence_payload,
                    "recent_finding_fingerprints": [
                        item["claim_fingerprint"] for item in context.recent_findings
                    ],
                }
            )
        if not evidence_payload:
            await self._fail_task(task_id, "main_input_token_limit")
            await self._fail_run(context.run_id, "main_input_token_limit", usage)
            return None
        unsettled_attempt = False
        for attempt in range(1, self._settings.max_synthesis_repairs + 2):
            if self._request_would_exceed_cost_ceiling(
                context,
                usage,
                model=self._settings.otari_main_model,
                max_completion_tokens=self._settings.main_output_token_limit,
                enable_web_search=False,
            ):
                await self._cancel_tasks([task_id], "cost_ceiling_reached")
                await self._finish_run(
                    context.run_id,
                    ScoutRunStatus.PARTIAL,
                    usage,
                    partial_reasons=["cost_ceiling_reached"],
                )
                return None
            metadata: OtariMetadata | None = None
            await self._set_task_attempt(task_id, attempt)
            try:
                result, metadata = await self._client.structured_completion(
                    model=self._settings.otari_main_model,
                    messages=messages,
                    output_type=SynthesisResult,
                    session_label=scout_run_session_label(context.run_id),
                    max_completion_tokens=self._settings.main_output_token_limit,
                    deadline_seconds=self._settings.synthesis_deadline_seconds,
                    enable_web_search=False,
                )
                usage.add(metadata)
                if metadata.usage.input_tokens > self._settings.main_input_token_limit:
                    raise PlanValidationError("main_input_token_limit")
            except Exception as error:
                if metadata is None:
                    unsettled_attempt = True
                    usage.mark_unsettled()
                code = self._safe_error_code(error, "synthesis_failed")
                repairable = code in {"otari_schema_error", "otari_invalid_response"}
                if repairable and attempt <= self._settings.max_synthesis_repairs:
                    continue
                await self._fail_task(
                    task_id,
                    code,
                    context=context,
                    metadata=metadata,
                    unsettled=unsettled_attempt,
                )
                await self._fail_run(context.run_id, code, usage)
                return None
            if metadata is None:
                raise RuntimeError("synthesis response metadata was not resolved")
            await self._succeed_task(
                context,
                task_id,
                metadata,
                result.model_dump(mode="json"),
                unsettled=unsettled_attempt,
            )
            return result
        return None

    async def _create_synthesis_task(self, context: _RunContext) -> uuid.UUID:
        async with self._sessions.begin() as session:
            run = await session.get(ScoutRun, context.run_id)
            if run is None:
                raise RuntimeError("Scout Run disappeared")
            run.status = ScoutRunStatus.SYNTHESIZING
            task = AgentTask(
                scout_run_id=context.run_id,
                parent_task_id=context.planner_task_id,
                role=AgentTaskRole.MAIN_SYNTHESIZER,
                task_kind="daily_synthesis",
                model=self._settings.otari_main_model,
                objective="Synthesize validated evidence into publishable findings",
                source_scope=[],
                status=AgentTaskStatus.RUNNING,
                started_at=self._current_time(),
            )
            session.add(task)
            await session.flush()
            return task.id

    async def _publish(
        self,
        context: _RunContext,
        result: SynthesisResult,
        accepted: Sequence[_AcceptedEvidence],
    ) -> None:
        captured_at = self._current_time()
        publications = [
            EvidencePublication(
                agent_task_id=item.task_id,
                source_url=item.evidence.source_url,
                source_title=item.evidence.source_title,
                source_type=item.evidence.source_type,
                published_at=item.evidence.published_at,
                captured_at=captured_at,
                quoted_text=item.evidence.quoted_text,
                normalized_claim=item.evidence.normalized_claim,
                content_fingerprint=item.evidence.fingerprint,
            )
            for item in accepted
        ]
        for candidate in result.findings:
            if not candidate.material_change:
                continue
            finding = FindingPublication(
                category=candidate.category,
                title=candidate.title,
                summary=candidate.summary,
                significance_explanation=candidate.significance_explanation,
                significance_level=candidate.significance_level,
                confidence=Decimal(str(candidate.confidence)),
                normalized_claim=candidate.normalized_claim,
                material_change=candidate.material_change,
                evidence_indexes=candidate.evidence_indexes,
                primary_evidence_index=candidate.primary_evidence_index,
                decision_rationale=candidate.decision_rationale,
            )
            try:
                await self._publisher.publish(
                    user_id=context.user_id,
                    competitor_id=context.competitor_id,
                    scout_run_id=context.run_id,
                    finding=finding,
                    evidence=publications,
                    published_at=captured_at,
                )
            except PublicationValidationError:
                continue

    async def _set_task_attempt(self, task_id: uuid.UUID, attempt: int) -> None:
        async with self._sessions.begin() as session:
            task = await session.get(AgentTask, task_id)
            if task is None:
                raise RuntimeError("Agent Task disappeared")
            task.status = AgentTaskStatus.RUNNING
            task.attempt_count = attempt
            task.started_at = task.started_at or self._current_time()

    async def _succeed_task(
        self,
        context: _RunContext,
        task_id: uuid.UUID,
        metadata: OtariMetadata,
        validated_output: dict[str, object],
        *,
        unsettled: bool = False,
    ) -> None:
        async with self._sessions.begin() as session:
            task = await session.get(AgentTask, task_id)
            if task is None:
                raise RuntimeError("Agent Task disappeared")
            task.status = AgentTaskStatus.SUCCEEDED
            task.completed_at = self._current_time()
            task.otari_request_id = metadata.request_id
            task.input_tokens = metadata.usage.input_tokens
            task.output_tokens = metadata.usage.output_tokens
            task.tool_calls = None if unsettled else metadata.usage.tool_calls
            task.settled_cost_usd = None if unsettled else metadata.usage.cost_usd
            task.pricing_source = None if unsettled else metadata.usage.pricing_source
            task.validated_output = validated_output
            session.add(
                UsageEvent(
                    user_id=context.user_id,
                    scout_run_id=context.run_id,
                    agent_task_id=task.id,
                    provider_request_id=metadata.request_id,
                    model=task.model,
                    input_tokens=metadata.usage.input_tokens,
                    output_tokens=metadata.usage.output_tokens,
                    tool_calls=metadata.usage.tool_calls,
                    settled_cost_usd=metadata.usage.cost_usd,
                    pricing_source=metadata.usage.pricing_source,
                    occurred_at=self._current_time(),
                )
            )

    async def _fail_task(
        self,
        task_id: uuid.UUID,
        code: str,
        *,
        context: _RunContext | None = None,
        metadata: OtariMetadata | None = None,
        unsettled: bool = False,
    ) -> None:
        async with self._sessions.begin() as session:
            task = await session.get(AgentTask, task_id)
            if task is None:
                return
            task.status = AgentTaskStatus.FAILED
            task.completed_at = self._current_time()
            task.error_code = code
            task.error_summary = "agent task failed"
            if metadata is not None:
                task.otari_request_id = metadata.request_id
                task.input_tokens = metadata.usage.input_tokens
                task.output_tokens = metadata.usage.output_tokens
                task.tool_calls = None if unsettled else metadata.usage.tool_calls
                task.settled_cost_usd = None if unsettled else metadata.usage.cost_usd
                task.pricing_source = None if unsettled else metadata.usage.pricing_source
                if context is not None:
                    session.add(
                        UsageEvent(
                            user_id=context.user_id,
                            scout_run_id=context.run_id,
                            agent_task_id=task.id,
                            provider_request_id=metadata.request_id,
                            model=task.model,
                            input_tokens=metadata.usage.input_tokens,
                            output_tokens=metadata.usage.output_tokens,
                            tool_calls=metadata.usage.tool_calls,
                            settled_cost_usd=metadata.usage.cost_usd,
                            pricing_source=metadata.usage.pricing_source,
                            occurred_at=self._current_time(),
                        )
                    )

    async def _cancel_tasks(self, task_ids: Sequence[uuid.UUID], code: str) -> None:
        if not task_ids:
            return
        async with self._sessions.begin() as session:
            tasks = list(
                (await session.scalars(select(AgentTask).where(AgentTask.id.in_(task_ids)))).all()
            )
            for task in tasks:
                task.status = AgentTaskStatus.CANCELLED
                task.completed_at = self._current_time()
                task.error_code = code
                task.error_summary = "agent task cancelled by run budget"

    async def _apply_usage(self, run_id: uuid.UUID, usage: _UsageAccumulator) -> None:
        async with self._sessions.begin() as session:
            run = await session.get(ScoutRun, run_id)
            if run is None:
                return
            run.input_tokens = usage.input_tokens
            run.output_tokens = usage.output_tokens
            run.tool_calls = usage.recorded_tool_calls
            run.settled_cost_usd = usage.recorded_cost

    async def _fail_run(
        self,
        run_id: uuid.UUID,
        code: str,
        usage: _UsageAccumulator,
    ) -> None:
        async with self._sessions.begin() as session:
            run = await session.get(ScoutRun, run_id)
            if run is None:
                return
            run.status = ScoutRunStatus.FAILED
            run.failure_code = code
            run.failure_summary = "Scout Run failed"
            run.completed_at = self._current_time()
            run.input_tokens = usage.input_tokens
            run.output_tokens = usage.output_tokens
            run.tool_calls = usage.recorded_tool_calls
            run.settled_cost_usd = usage.recorded_cost

    async def _finish_run(
        self,
        run_id: uuid.UUID,
        status: ScoutRunStatus,
        usage: _UsageAccumulator,
        *,
        partial_reasons: list[str],
    ) -> None:
        async with self._sessions.begin() as session:
            run = await session.get(ScoutRun, run_id)
            if run is None:
                raise RuntimeError("Scout Run disappeared")
            run.status = status
            run.partial_reasons = partial_reasons
            run.completed_at = self._current_time()
            run.input_tokens = usage.input_tokens
            run.output_tokens = usage.output_tokens
            run.tool_calls = usage.recorded_tool_calls
            run.settled_cost_usd = usage.recorded_cost

    async def _run_status(self, run_id: uuid.UUID) -> ScoutRunStatus:
        async with self._sessions() as session:
            status = await session.scalar(select(ScoutRun.status).where(ScoutRun.id == run_id))
        if status is None:
            raise ValueError("Scout Run was not found")
        return status

    def _run_budget_reached(
        self,
        context: _RunContext,
        usage: _UsageAccumulator,
    ) -> bool:
        if usage.recorded_cost is None:
            current_cost = usage.estimated_cost_usd
        else:
            current_cost = max(usage.recorded_cost, usage.estimated_cost_usd)
        return (
            current_cost >= self._settings.max_run_cost_usd
            or context.initial_daily_cost + current_cost >= self._settings.max_user_daily_cost_usd
        )

    def _request_would_exceed_cost_ceiling(
        self,
        context: _RunContext,
        usage: _UsageAccumulator,
        *,
        model: str,
        max_completion_tokens: int,
        enable_web_search: bool,
    ) -> bool:
        if self._cost_estimator is None:
            return False
        try:
            estimate = self._cost_estimator(
                model,
                max_completion_tokens,
                enable_web_search,
            )
            if estimate is None:
                return False
            estimate = Decimal(estimate)
        except (ArithmeticError, TypeError, ValueError):
            return False
        if not estimate.is_finite() or estimate < 0:
            return False
        current_cost = usage.estimated_cost_usd
        exceeds = (
            current_cost + estimate > self._settings.max_run_cost_usd
            or context.initial_daily_cost + current_cost + estimate
            > self._settings.max_user_daily_cost_usd
        )
        if not exceeds:
            usage.estimated_cost_usd += estimate
        return exceeds

    def _current_time(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ValueError("orchestrator clock must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _safe_error_code(error: Exception, fallback: str) -> str:
        code = getattr(error, "code", None)
        return code if isinstance(code, str) and len(code) <= 100 else fallback

    @staticmethod
    def _estimated_tokens(messages: Sequence[dict[str, str]]) -> int:
        encoded_size = len(json.dumps(messages, sort_keys=True, separators=(",", ":")).encode())
        return (encoded_size + 3) // 4

    @staticmethod
    def _retry_delay(error: Exception, attempt: int) -> float:
        retry_after = getattr(error, "retry_after", None)
        try:
            return (
                max(float(retry_after), 0)
                if retry_after is not None
                else min(2 ** (attempt - 1), 5)
            )
        except (TypeError, ValueError):
            return min(2 ** (attempt - 1), 5)


@dataclass(frozen=True)
class SourceDiscoveryOutcome:
    sources: tuple[DiscoveredSource, ...]
    metadata: OtariMetadata
    rejected_count: int


class SourceDiscoveryService:
    def __init__(
        self,
        *,
        client: OtariClient,
        settings: Settings,
        url_validator: UrlValidator = validate_public_https_url,
    ) -> None:
        self._client = client
        self._settings = settings
        self._url_validator = url_validator

    async def discover(
        self,
        *,
        domain: str,
        run_id: uuid.UUID,
    ) -> SourceDiscoveryOutcome:
        payload = json.dumps(
            {
                "competitor_domain": domain,
                "maximum_sources": 30,
                "objective": "Suggest useful public first-party monitoring sources.",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        search_limit = self._settings.max_source_discovery_search_calls
        system = "\n\n".join(
            (
                UNTRUSTED_SOURCE_POLICY,
                f"Prompt version: {PROMPT_VERSION}.",
                (
                    "Use only the otari_web_search tool. Do not use or request any "
                    f"other tool. Make no more than {search_limit} web search calls. "
                    "Stay within the competitor domain and return SourceDiscoveryResult only."
                ),
            )
        )
        result, metadata = await self._client.structured_completion(
            model=self._settings.otari_main_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": payload},
            ],
            output_type=SourceDiscoveryResult,
            session_label=scout_run_session_label(run_id),
            max_completion_tokens=self._settings.main_output_token_limit,
            deadline_seconds=self._settings.planning_deadline_seconds,
            enable_web_search=True,
            max_tool_iterations=search_limit + 1,
        )

        accepted: list[DiscoveredSource] = []
        seen_urls: set[str] = set()
        rejected_count = 0
        for candidate in result.sources:
            try:
                canonical_url = await self._url_validator(str(candidate.url))
            except (UnsafeSourceUrl, TypeError, ValueError):
                rejected_count += 1
                continue
            if not same_registrable_domain(canonical_url, domain) or canonical_url in seen_urls:
                rejected_count += 1
                continue
            seen_urls.add(canonical_url)
            normalized = candidate.model_dump(mode="json")
            normalized["url"] = canonical_url
            accepted.append(
                DiscoveredSource.model_validate_json(
                    json.dumps(normalized, sort_keys=True, separators=(",", ":"))
                )
            )

        return SourceDiscoveryOutcome(tuple(accepted), metadata, rejected_count)
