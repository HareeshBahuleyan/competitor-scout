from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.agents.client import OtariError
from competitor_scout.agents.contracts import DiscoveredSource
from competitor_scout.agents.orchestrator import SourceDiscoveryOutcome
from competitor_scout.config import Settings
from competitor_scout.db import SessionFactory
from competitor_scout.jobs.repository import enqueue_in_session
from competitor_scout.models.intelligence import (
    AgentTask,
    AgentTaskRole,
    AgentTaskStatus,
    Competitor,
    CompetitorStatus,
    MonitoredSource,
    RunType,
    ScoutRun,
    ScoutRunStatus,
    SourceCategory,
    UsageEvent,
)

type Clock = Callable[[], datetime]
type CostEstimator = Callable[[str, int, bool], Decimal | None]


class DiscoveryService(Protocol):
    async def discover(
        self,
        *,
        domain: str,
        run_id: uuid.UUID,
    ) -> SourceDiscoveryOutcome: ...


@dataclass(frozen=True)
class _DiscoveryClaim:
    run_id: uuid.UUID
    user_id: uuid.UUID
    competitor_id: uuid.UUID
    competitor_domain: str
    task_id: uuid.UUID
    initial_daily_cost: Decimal


def utc_now() -> datetime:
    return datetime.now(UTC)


def discovery_bucket(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("discovery clock must be timezone-aware")
    current = value.astimezone(UTC)
    return current.replace(minute=current.minute - current.minute % 5, second=0, microsecond=0)


async def enqueue_source_discovery(
    session: AsyncSession,
    *,
    competitor: Competitor,
    now: datetime,
) -> ScoutRun:
    scheduled_for = discovery_bucket(now)
    proposed_id = uuid.uuid4()
    statement = (
        insert(ScoutRun)
        .values(
            id=proposed_id,
            user_id=competitor.user_id,
            competitor_id=competitor.id,
            run_type=RunType.SOURCE_DISCOVERY,
            status=ScoutRunStatus.QUEUED,
            scheduled_for=scheduled_for,
        )
        .on_conflict_do_nothing(
            index_elements=[
                ScoutRun.run_type,
                ScoutRun.competitor_id,
                ScoutRun.scheduled_for,
            ],
            index_where=ScoutRun.competitor_id.is_not(None),
        )
        .returning(ScoutRun)
    )
    run = (await session.scalars(statement)).one_or_none()
    if run is None:
        run = await session.scalar(
            select(ScoutRun).where(
                ScoutRun.run_type == RunType.SOURCE_DISCOVERY,
                ScoutRun.competitor_id == competitor.id,
                ScoutRun.scheduled_for == scheduled_for,
            )
        )
    if run is None:
        raise RuntimeError("idempotent source discovery did not resolve a run")
    await enqueue_in_session(
        session,
        "source_discovery",
        f"source_discovery:{run.id}",
        {"run_id": str(run.id)},
        available_at=now,
    )
    return run


class SourceDiscoveryHandler:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        service: DiscoveryService,
        settings: Settings,
        now: Clock = utc_now,
        cost_estimator: CostEstimator | None = None,
    ) -> None:
        self._sessions = session_factory
        self._service = service
        self._settings = settings
        self._now = now
        self._cost_estimator = cost_estimator

    async def handle(self, *, run_id: uuid.UUID) -> ScoutRunStatus:
        claimed = await self._claim(run_id)
        if isinstance(claimed, ScoutRunStatus):
            return claimed

        reserved_cost = Decimal("0")
        for attempt in (1, 2):
            estimate = self._request_estimate()
            if estimate is not None:
                if self._would_exceed_cost_ceiling(claimed, reserved_cost + estimate):
                    return await self._stop_for_cost(claimed)
                reserved_cost += estimate
            try:
                outcome = await self._service.discover(
                    domain=claimed.competitor_domain,
                    run_id=claimed.run_id,
                )
            except OtariError as error:
                if error.retryable and attempt == 1:
                    await self._set_attempt(claimed, 2)
                    continue
                return await self._complete_failure(claimed, code=error.code)
            except Exception:
                return await self._complete_failure(
                    claimed,
                    code="source_discovery_failed",
                )
            return await self._complete_success(claimed, outcome)
        raise RuntimeError("source discovery retry loop did not terminate")

    async def _claim(
        self,
        run_id: uuid.UUID,
    ) -> _DiscoveryClaim | ScoutRunStatus:
        now = self._current_time()
        async with self._sessions.begin() as session:
            run = await session.scalar(
                select(ScoutRun).where(ScoutRun.id == run_id).with_for_update()
            )
            if run is None or run.run_type is not RunType.SOURCE_DISCOVERY:
                raise ValueError("source discovery run was not found")
            if run.status is ScoutRunStatus.PLANNING:
                return await self._recover_or_report_planning(session, run, now=now)
            if run.status is not ScoutRunStatus.QUEUED:
                return run.status
            competitor = await session.scalar(
                select(Competitor).where(
                    Competitor.id == run.competitor_id,
                    Competitor.user_id == run.user_id,
                    Competitor.status != CompetitorStatus.DELETED,
                )
            )
            if competitor is None:
                run.status = ScoutRunStatus.FAILED
                run.completed_at = now
                run.failure_code = "competitor_ineligible"
                run.failure_summary = "source discovery competitor is not eligible"
                return run.status

            run.status = ScoutRunStatus.PLANNING
            run.started_at = now
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            daily_cost = await session.scalar(
                select(func.coalesce(func.sum(UsageEvent.settled_cost_usd), 0)).where(
                    UsageEvent.user_id == run.user_id,
                    UsageEvent.occurred_at >= day_start,
                    UsageEvent.occurred_at < day_start + timedelta(days=1),
                )
            )
            task = AgentTask(
                scout_run_id=run.id,
                role=AgentTaskRole.MAIN_PLANNER,
                task_kind="source_discovery",
                status=AgentTaskStatus.RUNNING,
                model_alias=self._settings.otari_main_model_alias,
                objective="Discover useful public first-party monitoring sources",
                source_scope=[f"https://{competitor.primary_domain}"],
                attempt_count=1,
                started_at=now,
            )
            session.add(task)
            await session.flush()
            return _DiscoveryClaim(
                run_id=run.id,
                user_id=run.user_id,
                competitor_id=competitor.id,
                competitor_domain=competitor.primary_domain,
                task_id=task.id,
                initial_daily_cost=Decimal(daily_cost or 0),
            )

    async def _recover_or_report_planning(
        self,
        session: AsyncSession,
        run: ScoutRun,
        *,
        now: datetime,
    ) -> ScoutRunStatus:
        task = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run.id,
                AgentTask.task_kind == "source_discovery",
            )
        )
        stale_before = now - timedelta(seconds=self._settings.planning_deadline_seconds)
        if run.started_at is not None and run.started_at > stale_before:
            return run.status
        if task is not None and task.status is AgentTaskStatus.RUNNING:
            task.status = AgentTaskStatus.FAILED
            task.completed_at = now
            task.error_code = "interrupted_source_discovery"
            task.error_summary = "source discovery was interrupted"
        run.status = ScoutRunStatus.FAILED
        run.completed_at = now
        run.failure_code = "interrupted_source_discovery"
        run.failure_summary = "source discovery was interrupted"
        return run.status

    async def _set_attempt(self, claim: _DiscoveryClaim, attempt: int) -> None:
        async with self._sessions.begin() as session:
            task = await session.get(AgentTask, claim.task_id)
            if task is not None and task.status is AgentTaskStatus.RUNNING:
                task.attempt_count = attempt

    async def _complete_failure(
        self,
        claim: _DiscoveryClaim,
        *,
        code: str,
    ) -> ScoutRunStatus:
        async with self._sessions.begin() as session:
            run = await session.scalar(
                select(ScoutRun).where(ScoutRun.id == claim.run_id).with_for_update()
            )
            task = await session.get(AgentTask, claim.task_id)
            if run is None or task is None:
                raise RuntimeError("claimed source discovery records disappeared")
            if run.status is not ScoutRunStatus.PLANNING:
                return run.status
            self._mark_failed(run, task, code=code)
            return run.status

    async def _complete_success(
        self,
        claim: _DiscoveryClaim,
        outcome: SourceDiscoveryOutcome,
    ) -> ScoutRunStatus:
        async with self._sessions.begin() as session:
            run = await session.scalar(
                select(ScoutRun).where(ScoutRun.id == claim.run_id).with_for_update()
            )
            task = await session.get(AgentTask, claim.task_id)
            if run is None or task is None:
                raise RuntimeError("claimed source discovery records disappeared")
            if run.status is not ScoutRunStatus.PLANNING:
                return run.status
            for candidate in outcome.sources:
                await self._upsert_source(session, claim.competitor_id, candidate)
            self._record_success(session, run, task, outcome)
            return run.status

    def _current_time(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ValueError("handler clock must be timezone-aware")
        return value.astimezone(UTC)

    def _request_estimate(self) -> Decimal | None:
        if self._cost_estimator is None:
            return None
        try:
            estimate = self._cost_estimator(
                self._settings.otari_main_model_alias,
                self._settings.main_output_token_limit,
                True,
            )
            if estimate is None:
                return None
            normalized = Decimal(estimate)
        except (ArithmeticError, TypeError, ValueError):
            return None
        return normalized if normalized.is_finite() and normalized >= 0 else None

    def _would_exceed_cost_ceiling(
        self,
        claim: _DiscoveryClaim,
        reserved_cost: Decimal,
    ) -> bool:
        return (
            reserved_cost > self._settings.max_run_cost_usd
            or claim.initial_daily_cost + reserved_cost
            > self._settings.max_user_daily_cost_usd
        )

    async def _stop_for_cost(self, claim: _DiscoveryClaim) -> ScoutRunStatus:
        completed_at = self._current_time()
        async with self._sessions.begin() as session:
            run = await session.scalar(
                select(ScoutRun).where(ScoutRun.id == claim.run_id).with_for_update()
            )
            task = await session.get(AgentTask, claim.task_id)
            if run is None or task is None:
                raise RuntimeError("claimed source discovery records disappeared")
            if run.status is not ScoutRunStatus.PLANNING:
                return run.status
            run.status = ScoutRunStatus.PARTIAL
            run.partial_reasons = ["cost_ceiling_reached"]
            run.completed_at = completed_at
            task.status = AgentTaskStatus.CANCELLED
            task.completed_at = completed_at
            task.error_code = "cost_ceiling_reached"
            task.error_summary = "agent task cancelled by run budget"
            return run.status

    def _mark_failed(self, run: ScoutRun, task: AgentTask, *, code: str) -> None:
        completed_at = self._current_time()
        task.status = AgentTaskStatus.FAILED
        task.completed_at = completed_at
        task.error_code = code
        task.error_summary = "source discovery failed"
        run.status = ScoutRunStatus.FAILED
        run.completed_at = completed_at
        run.failure_code = code
        run.failure_summary = "source discovery failed"

    async def _upsert_source(
        self,
        session: AsyncSession,
        competitor_id: uuid.UUID,
        candidate: DiscoveredSource,
    ) -> None:
        canonical_url = str(candidate.url)
        category = SourceCategory(candidate.category.value)
        statement = insert(MonitoredSource).values(
            competitor_id=competitor_id,
            url=canonical_url,
            normalized_url=canonical_url,
            source_category=category,
            title=candidate.title,
            discovery_reason=candidate.reason,
        )
        await session.execute(
            statement.on_conflict_do_update(
                constraint="uq_monitored_sources_competitor_url",
                set_={
                    "url": statement.excluded.url,
                    "source_category": statement.excluded.source_category,
                    "title": statement.excluded.title,
                    "discovery_reason": statement.excluded.discovery_reason,
                    "updated_at": func.now(),
                },
            )
        )

    def _record_success(
        self,
        session: AsyncSession,
        run: ScoutRun,
        task: AgentTask,
        outcome: SourceDiscoveryOutcome,
    ) -> None:
        completed_at = self._current_time()
        usage = outcome.metadata.usage
        task.status = AgentTaskStatus.SUCCEEDED
        task.completed_at = completed_at
        task.otari_request_id = outcome.metadata.request_id
        task.input_tokens = usage.input_tokens
        task.output_tokens = usage.output_tokens
        task.tool_calls = usage.tool_calls
        task.settled_cost_usd = usage.cost_usd
        task.pricing_source = usage.pricing_source
        task.validated_output = {
            "sources": [item.model_dump(mode="json") for item in outcome.sources],
            "rejected_count": outcome.rejected_count,
        }
        run.input_tokens = usage.input_tokens
        run.output_tokens = usage.output_tokens
        run.tool_calls = usage.tool_calls
        run.settled_cost_usd = usage.cost_usd
        run.completed_at = completed_at
        if outcome.sources:
            run.status = ScoutRunStatus.COMPLETED
        else:
            run.status = ScoutRunStatus.PARTIAL
            run.partial_reasons = ["insufficient_sources"]

        session.add(
            UsageEvent(
                user_id=run.user_id,
                scout_run_id=run.id,
                agent_task_id=task.id,
                provider_request_id=outcome.metadata.request_id,
                model_alias=self._settings.otari_main_model_alias,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                tool_calls=usage.tool_calls,
                settled_cost_usd=usage.cost_usd,
                pricing_source=usage.pricing_source,
                occurred_at=completed_at,
            )
        )
