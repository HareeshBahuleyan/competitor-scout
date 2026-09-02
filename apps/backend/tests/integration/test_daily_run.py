from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from competitor_scout.agents.client import OtariError, OtariMetadata, OtariUsage
from competitor_scout.agents.contracts import (
    ChildTaskResult,
    ScoutPlan,
    SynthesisResult,
)
from competitor_scout.agents.orchestrator import ScoutOrchestrator
from competitor_scout.config import Settings
from competitor_scout.jobs.scheduler import schedule_due_daily_runs
from competitor_scout.models.auth import User
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
    SourceCategory,
    UsageEvent,
)
from competitor_scout.models.jobs import Job
from competitor_scout.services.findings import FindingPublicationService

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "environment": "test",
        "database_url": "postgresql+asyncpg://test:test@localhost/test",
        "public_base_url": "https://testserver",
        "session_secret": "s" * 32,
        "csrf_secret": "c" * 32,
        "google_client_id": "google-id",
        "google_client_secret": "google-secret",
        "otari_base_url": "https://otari.invalid",
        "otari_ai_token": "dummy-never-live",
        "max_concurrent_child_tasks": 4,
        "max_child_search_calls": 2,
        "max_child_retries": 1,
        "max_planning_repairs": 1,
        "max_synthesis_repairs": 1,
    }
    values.update(changes)
    return Settings(**values)  # type: ignore[arg-type]


def plan(task_count: int) -> ScoutPlan:
    return ScoutPlan.model_validate_json(
        json.dumps(
            {
                "tasks": [
                    {
                        "kind": "news_discovery",
                        "objective": f"Research synthetic topic {index}",
                        "source_urls": [],
                        "search_query": f"Acme synthetic topic {index}",
                        "expected_category": "product",
                        "max_search_calls": 1,
                        "completion_criteria": "Return directly quoted evidence or none",
                    }
                    for index in range(task_count)
                ]
            }
        )
    )


def child_result(index: int) -> ChildTaskResult:
    url = f"https://news-{index}.example/story"
    return ChildTaskResult.model_validate_json(
        json.dumps(
            {
                "sources_inspected": [url],
                "evidence": [
                    {
                        "source_url": url,
                        "source_title": f"Synthetic report {index}",
                        "source_type": "news",
                        "quoted_text": (
                            f"Acme announced synthetic product update number {index} today."
                        ),
                        "normalized_claim": f"acme product update {index}",
                        "published_at": NOW.isoformat(),
                        "confidence": 0.95,
                        "limitations": [],
                    }
                ],
                "limitations": [],
            }
        )
    )


def first_party_child_result(*, include_out_of_scope: bool = False) -> ChildTaskResult:
    inspected = ["https://acme.example/pricing"]
    if include_out_of_scope:
        inspected.append("https://other.example/hidden")
    return ChildTaskResult.model_validate_json(
        json.dumps(
            {
                "sources_inspected": inspected,
                "evidence": [
                    {
                        "source_url": "https://acme.example/pricing",
                        "source_title": "Acme pricing",
                        "source_type": "first_party",
                        "quoted_text": ("Acme lists a synthetic enterprise pricing update today."),
                        "normalized_claim": "acme enterprise pricing update",
                        "published_at": NOW.isoformat(),
                        "confidence": 0.95,
                        "limitations": [],
                    }
                ],
                "limitations": [],
            }
        )
    )


def synthesis() -> SynthesisResult:
    return SynthesisResult.model_validate_json(
        json.dumps(
            {
                "findings": [
                    {
                        "category": "product",
                        "title": "Synthetic product update",
                        "summary": "Acme announced a synthetic product update.",
                        "significance_explanation": "This may affect product positioning.",
                        "significance_level": "medium",
                        "confidence": 0.95,
                        "normalized_claim": "acme announced a synthetic product update",
                        "material_change": True,
                        "evidence_indexes": [0],
                        "primary_evidence_index": 0,
                        "decision_rationale": "The cited public report directly states the update.",
                    }
                ]
            }
        )
    )


class FakeOtari:
    def __init__(
        self,
        *,
        task_count: int,
        fail_children: set[int] | None = None,
        budget_children: set[int] | None = None,
        planning_schema_failures: int = 0,
        planning_delay_seconds: float = 0,
        synthesis_schema_failures: int = 0,
        synthesis_delay_seconds: float = 0,
        known_cost: Decimal | None = None,
        input_tokens: int = 10,
        tool_calls: int | None = None,
        first_party_out_of_scope: bool = False,
        fail_while_mcp: bool = False,
    ) -> None:
        self.plan = plan(task_count)
        self.fail_children = fail_children or set()
        self.budget_children = budget_children or set()
        self.planning_schema_failures = planning_schema_failures
        self.planning_delay_seconds = planning_delay_seconds
        self.synthesis_schema_failures = synthesis_schema_failures
        self.synthesis_delay_seconds = synthesis_delay_seconds
        self.known_cost = known_cost
        self.input_tokens = input_tokens
        self.tool_calls = tool_calls
        self.first_party_out_of_scope = first_party_out_of_scope
        self.fail_while_mcp = fail_while_mcp
        self.calls: list[dict[str, object]] = []
        self.child_attempts: dict[int, int] = {}
        self.active_children = 0
        self.maximum_children = 0
        self.child_gate = asyncio.Event()

    async def structured_completion(self, **kwargs: object):
        self.calls.append(kwargs)
        output_type = kwargs["output_type"]
        if output_type is ScoutPlan:
            await asyncio.sleep(self.planning_delay_seconds)
            if self.planning_schema_failures:
                self.planning_schema_failures -= 1
                raise OtariError("otari_schema_error", retryable=False)
            return self.plan, self._metadata("plan")
        if output_type is ChildTaskResult:
            messages = kwargs["messages"]
            assert isinstance(messages, list)
            payload = json.loads(messages[1]["content"])
            objective = payload["task"]["objective"]
            index = int(objective.rsplit(" ", 1)[1])
            self.child_attempts[index] = self.child_attempts.get(index, 0) + 1
            self.active_children += 1
            self.maximum_children = max(self.maximum_children, self.active_children)
            try:
                target = min(len(self.plan.tasks), 4)
                if self.active_children >= target:
                    self.child_gate.set()
                await asyncio.wait_for(self.child_gate.wait(), timeout=1)
                if index in self.budget_children:
                    raise OtariError("otari_budget_exceeded", retryable=False, status_code=403)
                if index in self.fail_children:
                    raise OtariError("otari_upstream_error", retryable=True)
                if self.fail_while_mcp and kwargs.get("mcp_server_ids"):
                    raise OtariError("otari_upstream_error", retryable=True)
                if payload["task"]["kind"] == "first_party_source_review":
                    return first_party_child_result(
                        include_out_of_scope=self.first_party_out_of_scope
                    ), self._metadata(f"child-{index}")
                return child_result(index), self._metadata(f"child-{index}")
            finally:
                self.active_children -= 1
        if output_type is SynthesisResult:
            await asyncio.sleep(self.synthesis_delay_seconds)
            if self.synthesis_schema_failures:
                self.synthesis_schema_failures -= 1
                raise OtariError("otari_schema_error", retryable=False)
            return synthesis(), self._metadata("synthesis")
        raise AssertionError(f"unexpected output type: {output_type}")

    def _metadata(self, label: str) -> OtariMetadata:
        return OtariMetadata(
            request_id=f"req-{label}-{len(self.calls)}",
            usage=OtariUsage(
                input_tokens=self.input_tokens,
                output_tokens=5,
                tool_calls=self.tool_calls,
                cost_usd=self.known_cost,
                pricing_source="hosted_catalog" if self.known_cost is not None else None,
            ),
        )


async def public_url(value: str) -> str:
    return value.split("?", 1)[0].split("#", 1)[0].casefold()


async def no_sleep(_seconds: float) -> None:
    return None


class FailingPublisher:
    async def publish(self, **_kwargs: object) -> None:
        raise RuntimeError("synthetic publication failure")


async def seed_daily_run(sessions) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    async with sessions.begin() as session:
        user = User(
            email=f"daily-{uuid.uuid4().hex}@example.com",
            display_name="Daily Owner",
            timezone="UTC",
        )
        competitor = Competitor(
            user=user,
            name="Acme",
            primary_domain="acme.example",
            status=CompetitorStatus.ACTIVE,
        )
        source = MonitoredSource(
            competitor=competitor,
            url="https://acme.example/pricing",
            normalized_url="https://acme.example/pricing",
            source_category=SourceCategory.PRICING,
            title="Pricing",
            discovery_reason="Approved synthetic source",
            approval_status=ApprovalStatus.APPROVED,
        )
        run = ScoutRun(
            user=user,
            competitor=competitor,
            run_type=RunType.DAILY_SCOUT,
            scheduled_for=NOW,
        )
        session.add_all([source, run])
        await session.flush()
        return user.id, competitor.id, run.id


async def seed_user_for_mismatch(sessions) -> User:
    async with sessions.begin() as session:
        user = User(
            email=f"daily-mismatch-{uuid.uuid4().hex}@example.com",
            display_name="Mismatch Owner",
            timezone="UTC",
        )
        session.add(user)
        await session.flush()
        return user


@pytest.fixture
async def daily_store(migrated_database_url: str):
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        async with sessions.begin() as session:
            user_ids = list(
                (
                    await session.scalars(
                        select(User.id).where(
                            or_(
                                User.email.like("daily-%@example.com"),
                                User.email.like("dst-%@example.com"),
                            )
                        )
                    )
                ).all()
            )
            if user_ids:
                run_ids = [
                    str(item)
                    for item in (
                        await session.scalars(
                            select(ScoutRun.id).where(ScoutRun.user_id.in_(user_ids))
                        )
                    ).all()
                ]
                if run_ids:
                    await session.execute(
                        delete(Job).where(Job.payload["run_id"].as_string().in_(run_ids))
                    )
                await session.execute(delete(User).where(User.id.in_(user_ids)))
        await engine.dispose()


async def make_orchestrator(
    sessions,
    fake: FakeOtari,
    configured: Settings,
    *,
    cost_estimator: Callable[[str], Decimal | None] | None = None,
) -> ScoutOrchestrator:
    return ScoutOrchestrator(
        session_factory=sessions,
        client=fake,  # type: ignore[arg-type]
        settings=configured,
        publisher=FindingPublicationService(
            sessions,
            minimum_confidence=configured.max_run_cost_usd * 0
            + Decimal(str(configured.finding_confidence_threshold)),
        ),
        url_validator=public_url,
        now=lambda: NOW,
        sleep=no_sleep,
        cost_estimator=cost_estimator,
    )


@pytest.mark.parametrize("run_type", [RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT])
@pytest.mark.parametrize(
    ("stuck_status", "expected_status"),
    [
        (ScoutRunStatus.PLANNING, ScoutRunStatus.FAILED),
        (ScoutRunStatus.GATHERING, ScoutRunStatus.FAILED),
        (ScoutRunStatus.SYNTHESIZING, ScoutRunStatus.PARTIAL),
    ],
)
async def test_reclaimed_daily_or_manual_run_terminalizes_without_repeating_otari(
    daily_store,
    run_type: RunType,
    stuck_status: ScoutRunStatus,
    expected_status: ScoutRunStatus,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    role = (
        AgentTaskRole.MAIN_SYNTHESIZER
        if stuck_status is ScoutRunStatus.SYNTHESIZING
        else AgentTaskRole.CHILD_RESEARCHER
        if stuck_status is ScoutRunStatus.GATHERING
        else AgentTaskRole.MAIN_PLANNER
    )
    async with sessions.begin() as session:
        run = await session.get(ScoutRun, run_id)
        assert run is not None
        run.run_type = run_type
        run.status = stuck_status
        run.started_at = NOW.replace(minute=0)
        run.input_tokens = 123
        run.output_tokens = 45
        run.settled_cost_usd = Decimal("0.125000")
        session.add(
            AgentTask(
                scout_run_id=run.id,
                role=role,
                task_kind=f"interrupted_{stuck_status.value}",
                status=AgentTaskStatus.RUNNING,
                model="competitor-scout-main",
                objective="Synthetic interrupted task",
                attempt_count=1,
                started_at=NOW.replace(minute=0),
            )
        )
    fake = FakeOtari(task_count=1)
    orchestrator = await make_orchestrator(sessions, fake, settings())

    first = await orchestrator.execute_daily_run(run_id)
    second = await orchestrator.execute_daily_run(run_id)

    assert first is expected_status
    assert second is expected_status
    assert fake.calls == []
    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
        task = await session.scalar(select(AgentTask).where(AgentTask.scout_run_id == run_id))
    assert run is not None and run.completed_at == NOW
    assert run.input_tokens == 123 and run.settled_cost_usd == Decimal("0.125000")
    assert task is not None and task.status is AgentTaskStatus.FAILED
    assert task.error_code == "interrupted_scout_run"
    if expected_status is ScoutRunStatus.PARTIAL:
        assert run.failure_code is None
        assert run.partial_reasons == ["interrupted_scout_run"]
    else:
        assert run.failure_code == "interrupted_scout_run"
        assert run.failure_summary == "Scout Run was interrupted"


async def test_daily_run_happy_path_is_bounded_auditable_and_publishes(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(
        task_count=4,
        planning_schema_failures=1,
        synthesis_schema_failures=1,
    )
    orchestrator = await make_orchestrator(sessions, fake, settings())

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
        tasks = list(
            (
                await session.scalars(
                    select(AgentTask)
                    .where(AgentTask.scout_run_id == run_id)
                    .order_by(AgentTask.created_at, AgentTask.id)
                )
            ).all()
        )
        evidence_count = await session.scalar(
            select(func.count(EvidenceItem.id)).where(EvidenceItem.scout_run_id == run_id)
        )
        finding_count = await session.scalar(
            select(func.count(Finding.id)).where(Finding.originating_scout_run_id == run_id)
        )
        usage_count = await session.scalar(
            select(func.count(UsageEvent.id)).where(UsageEvent.scout_run_id == run_id)
        )

    assert status is ScoutRunStatus.COMPLETED
    assert run is not None and run.status is ScoutRunStatus.COMPLETED
    assert run.settled_cost_usd is None and run.tool_calls is None
    assert len(tasks) == 6
    assert [task.role for task in tasks].count(AgentTaskRole.CHILD_RESEARCHER) == 4
    assert all(task.status is AgentTaskStatus.SUCCEEDED for task in tasks)
    planner = next(task for task in tasks if task.role is AgentTaskRole.MAIN_PLANNER)
    synthesizer = next(task for task in tasks if task.role is AgentTaskRole.MAIN_SYNTHESIZER)
    assert planner.attempt_count == 2
    assert synthesizer.attempt_count == 2
    assert evidence_count == 4 and finding_count == 1 and usage_count == 6
    assert fake.maximum_children == 4
    assert {call["session_label"] for call in fake.calls} == {f"scout-run:{run_id}"}
    planning_call = next(call for call in fake.calls if call["output_type"] is ScoutPlan)
    synthesis_call = next(call for call in fake.calls if call["output_type"] is SynthesisResult)
    assert planning_call["model"] == "competitor-scout-main"
    assert planning_call["enable_web_search"] is False
    assert synthesis_call["model"] == "competitor-scout-main"
    assert synthesis_call["enable_web_search"] is False
    synthesis_messages_payload = synthesis_call["messages"]
    assert isinstance(synthesis_messages_payload, list)
    synthesis_payload = json.loads(synthesis_messages_payload[1]["content"])
    assert {item["expected_category_hint"] for item in synthesis_payload["validated_evidence"]} == {
        "product"
    }
    child_calls = [call for call in fake.calls if call["output_type"] is ChildTaskResult]
    assert all(call["model"] == "competitor-scout-child" for call in child_calls)
    assert all(call["enable_web_search"] is True for call in child_calls)
    assert all(call["max_tool_iterations"] == 4 for call in child_calls)


async def test_planning_repair_gets_a_fresh_request_deadline(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(
        task_count=1,
        planning_schema_failures=1,
        planning_delay_seconds=0.6,
    )
    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(planning_deadline_seconds=1),
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        planner = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.role == AgentTaskRole.MAIN_PLANNER,
            )
        )

    assert status is ScoutRunStatus.COMPLETED
    assert planner is not None and planner.status is AgentTaskStatus.SUCCEEDED
    assert planner.attempt_count == 2


async def test_synthesis_repair_gets_a_fresh_request_deadline(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(
        task_count=1,
        synthesis_schema_failures=1,
        synthesis_delay_seconds=0.6,
    )
    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(synthesis_deadline_seconds=1),
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        synthesizer = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.role == AgentTaskRole.MAIN_SYNTHESIZER,
            )
        )

    assert status is ScoutRunStatus.COMPLETED
    assert synthesizer is not None and synthesizer.status is AgentTaskStatus.SUCCEEDED
    assert synthesizer.attempt_count == 2


async def test_first_party_child_search_stays_within_approved_scope(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=1)
    fake.plan = ScoutPlan.model_validate(
        {
            "tasks": [
                {
                    "kind": "first_party_source_review",
                    "objective": "Review approved source 0",
                    "source_urls": ["https://acme.example/pricing"],
                    "search_query": None,
                    "expected_category": "pricing",
                    "max_search_calls": 1,
                    "completion_criteria": "Return directly quoted evidence or none",
                }
            ]
        },
        strict=False,
    )
    orchestrator = await make_orchestrator(sessions, fake, settings())

    status = await orchestrator.execute_daily_run(run_id)

    child_call = next(call for call in fake.calls if call["output_type"] is ChildTaskResult)
    child_payload = json.loads(child_call["messages"][1]["content"])
    assert status is ScoutRunStatus.COMPLETED
    assert child_call["enable_web_search"] is True
    assert child_call["max_tool_iterations"] == 4
    assert child_payload["task"]["source_urls"] == ["https://acme.example/pricing"]
    async with sessions() as session:
        evidence_urls = list(
            (
                await session.scalars(
                    select(EvidenceItem.source_url).where(EvidenceItem.scout_run_id == run_id)
                )
            ).all()
        )
    assert evidence_urls == ["https://acme.example/pricing"]


async def test_first_party_child_uses_firecrawl_mcp_when_configured(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=1)
    fake.plan = ScoutPlan.model_validate(
        {
            "tasks": [
                {
                    "kind": "first_party_source_review",
                    "objective": "Review approved source 0",
                    "source_urls": ["https://acme.example/pricing"],
                    "search_query": None,
                    "expected_category": "pricing",
                    "max_search_calls": 1,
                    "completion_criteria": "Return directly quoted evidence or none",
                }
            ]
        },
        strict=False,
    )
    configured = settings(otari_firecrawl_mcp_server_id="11111111-1111-1111-1111-111111111111")
    orchestrator = await make_orchestrator(sessions, fake, configured)

    status = await orchestrator.execute_daily_run(run_id)

    child_call = next(call for call in fake.calls if call["output_type"] is ChildTaskResult)
    child_system_prompt = child_call["messages"][0]["content"]
    assert status is ScoutRunStatus.COMPLETED
    assert child_call["enable_web_search"] is False
    assert child_call["mcp_server_ids"] == ["11111111-1111-1111-1111-111111111111"]
    assert "firecrawl" in child_system_prompt


async def test_first_party_child_falls_back_to_web_search_when_firecrawl_fails(
    daily_store,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=1, fail_while_mcp=True)
    fake.plan = ScoutPlan.model_validate(
        {
            "tasks": [
                {
                    "kind": "first_party_source_review",
                    "objective": "Review approved source 0",
                    "source_urls": ["https://acme.example/pricing"],
                    "search_query": None,
                    "expected_category": "pricing",
                    "max_search_calls": 1,
                    "completion_criteria": "Return directly quoted evidence or none",
                }
            ]
        },
        strict=False,
    )
    configured = settings(
        otari_firecrawl_mcp_server_id="11111111-1111-1111-1111-111111111111",
        max_child_retries=1,
    )
    orchestrator = await make_orchestrator(sessions, fake, configured)

    status = await orchestrator.execute_daily_run(run_id)

    child_calls = [call for call in fake.calls if call["output_type"] is ChildTaskResult]
    assert status is ScoutRunStatus.COMPLETED
    # FireCrawl kept its own configured retry (2 attempts), then got exactly one
    # bonus web-search attempt: 3 total, not 4 (which would double the retry budget).
    assert len(child_calls) == 3
    assert [call["mcp_server_ids"] for call in child_calls] == [
        ["11111111-1111-1111-1111-111111111111"],
        ["11111111-1111-1111-1111-111111111111"],
        None,
    ]
    assert [call["enable_web_search"] for call in child_calls] == [False, False, True]
    async with sessions() as session:
        task = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.role == AgentTaskRole.CHILD_RESEARCHER,
            )
        )
    assert task is not None and task.attempt_count == 3


async def test_first_party_child_fails_when_firecrawl_and_fallback_both_fail(
    daily_store,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=1, fail_while_mcp=True, fail_children={0})
    fake.plan = ScoutPlan.model_validate(
        {
            "tasks": [
                {
                    "kind": "first_party_source_review",
                    "objective": "Review approved source 0",
                    "source_urls": ["https://acme.example/pricing"],
                    "search_query": None,
                    "expected_category": "pricing",
                    "max_search_calls": 1,
                    "completion_criteria": "Return directly quoted evidence or none",
                }
            ]
        },
        strict=False,
    )
    configured = settings(
        otari_firecrawl_mcp_server_id="11111111-1111-1111-1111-111111111111",
        max_child_retries=0,
    )
    orchestrator = await make_orchestrator(sessions, fake, configured)

    status = await orchestrator.execute_daily_run(run_id)

    child_calls = [call for call in fake.calls if call["output_type"] is ChildTaskResult]
    assert status is ScoutRunStatus.FAILED
    assert len(child_calls) == 2
    assert [call["mcp_server_ids"] for call in child_calls] == [
        ["11111111-1111-1111-1111-111111111111"],
        None,
    ]


async def test_news_discovery_child_keeps_web_search_when_firecrawl_configured(
    daily_store,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=1)
    configured = settings(otari_firecrawl_mcp_server_id="11111111-1111-1111-1111-111111111111")
    orchestrator = await make_orchestrator(sessions, fake, configured)

    status = await orchestrator.execute_daily_run(run_id)

    child_call = next(call for call in fake.calls if call["output_type"] is ChildTaskResult)
    assert status is ScoutRunStatus.COMPLETED
    assert child_call["enable_web_search"] is True
    assert child_call["mcp_server_ids"] is None


@pytest.mark.parametrize(
    ("fake_changes", "expected_code"),
    [
        ({"tool_calls": 2}, "child_tool_budget_exceeded"),
        ({"first_party_out_of_scope": True}, "child_source_scope_violated"),
    ],
)
async def test_child_rejects_hosted_usage_or_inspection_scope_expansion(
    daily_store,
    fake_changes: dict[str, object],
    expected_code: str,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=1, **fake_changes)  # type: ignore[arg-type]
    fake.plan = ScoutPlan.model_validate(
        {
            "tasks": [
                {
                    "kind": "first_party_source_review",
                    "objective": "Review approved source 0",
                    "source_urls": ["https://acme.example/pricing"],
                    "search_query": None,
                    "expected_category": "pricing",
                    "max_search_calls": 1,
                    "completion_criteria": "Return directly quoted evidence or none",
                }
            ]
        },
        strict=False,
    )
    orchestrator = await make_orchestrator(sessions, fake, settings())

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
        child = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.role == AgentTaskRole.CHILD_RESEARCHER,
            )
        )
        evidence_count = await session.scalar(
            select(func.count(EvidenceItem.id)).where(EvidenceItem.scout_run_id == run_id)
        )
    assert status is ScoutRunStatus.FAILED
    assert run is not None and run.failure_code == "no_valid_evidence"
    assert child is not None and child.error_code == expected_code
    assert evidence_count == 0


async def test_run_and_competitor_ownership_mismatch_fails_before_otari(
    daily_store,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    other = await seed_user_for_mismatch(sessions)
    async with sessions.begin() as session:
        run = await session.get(ScoutRun, run_id)
        assert run is not None
        run.user_id = other.id
    fake = FakeOtari(task_count=1)
    orchestrator = await make_orchestrator(sessions, fake, settings())

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
    assert status is ScoutRunStatus.FAILED
    assert run is not None and run.failure_code == "run_ownership_mismatch"
    assert fake.calls == []


async def test_concurrent_daily_runs_share_the_process_wide_child_limit(
    daily_store,
) -> None:
    sessions = daily_store
    *_unused, first_run_id = await seed_daily_run(sessions)
    *_unused, second_run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=2)
    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(max_concurrent_child_tasks=2, max_otari_concurrency=2),
    )

    statuses = await asyncio.gather(
        orchestrator.execute_daily_run(first_run_id),
        orchestrator.execute_daily_run(second_run_id),
    )

    assert statuses == [ScoutRunStatus.COMPLETED, ScoutRunStatus.COMPLETED]
    assert fake.maximum_children == 2


async def test_known_usage_remains_settled_when_app_rejects_child_output(
    daily_store,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(
        task_count=1,
        known_cost=Decimal("0.25"),
        input_tokens=1_001,
    )
    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(child_input_token_limit=1_000),
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
        child = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.role == AgentTaskRole.CHILD_RESEARCHER,
            )
        )
    assert status is ScoutRunStatus.FAILED
    assert run is not None and run.settled_cost_usd == Decimal("0.50")
    assert child is not None and child.settled_cost_usd == Decimal("0.25")


async def test_publication_failure_does_not_unsettle_known_provider_usage(
    daily_store,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    configured = settings()
    fake = FakeOtari(task_count=1, known_cost=Decimal("0.10"))
    orchestrator = ScoutOrchestrator(
        session_factory=sessions,
        client=fake,  # type: ignore[arg-type]
        settings=configured,
        publisher=FailingPublisher(),
        url_validator=public_url,
        now=lambda: NOW,
        sleep=no_sleep,
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
    assert status is ScoutRunStatus.FAILED
    assert run is not None and run.failure_code == "publication_failed"
    assert run.settled_cost_usd == Decimal("0.30")


async def test_one_child_failing_twice_yields_partial_with_remaining_finding(
    daily_store,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=2, fail_children={1})
    orchestrator = await make_orchestrator(sessions, fake, settings())

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
        failed_task = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.status == AgentTaskStatus.FAILED,
            )
        )
        finding_count = await session.scalar(
            select(func.count(Finding.id)).where(Finding.originating_scout_run_id == run_id)
        )
    assert status is ScoutRunStatus.PARTIAL
    assert run is not None and "child_task_failed" in run.partial_reasons
    assert failed_task is not None and failed_task.attempt_count == 2
    assert fake.child_attempts[1] == 2
    assert finding_count == 1


async def test_all_children_failing_means_no_evidence_and_failed_run(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=2, fail_children={0, 1})
    orchestrator = await make_orchestrator(sessions, fake, settings())

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
    assert status is ScoutRunStatus.FAILED
    assert run is not None and run.failure_code == "no_valid_evidence"
    assert not any(call["output_type"] is SynthesisResult for call in fake.calls)


async def test_otari_budget_exhaustion_stops_unstarted_child_waves(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=5, budget_children={0})
    orchestrator = await make_orchestrator(sessions, fake, settings())

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
        failed = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.error_code == "otari_budget_exceeded",
            )
        )
        cancelled = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.status == AgentTaskStatus.CANCELLED,
            )
        )

    assert status is ScoutRunStatus.PARTIAL
    assert run is not None and run.partial_reasons == ["otari_budget_exceeded"]
    assert failed is not None and failed.status is AgentTaskStatus.FAILED
    assert cancelled is not None and cancelled.error_code == "otari_budget_exceeded"
    assert len(fake.child_attempts) == 4
    assert not any(call["output_type"] is SynthesisResult for call in fake.calls)


async def test_known_planning_cost_at_run_limit_stops_before_children(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=2, known_cost=Decimal("1.00"))
    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(max_run_cost_usd=Decimal("1.00")),
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
    assert status is ScoutRunStatus.FAILED
    assert run is not None and run.failure_code == "run_cost_limit"
    assert run.settled_cost_usd == Decimal("1.000000")
    assert not any(call["output_type"] is ChildTaskResult for call in fake.calls)


async def test_known_daily_user_cost_at_limit_stops_before_otari(daily_store) -> None:
    sessions = daily_store
    user_id, competitor_id, run_id = await seed_daily_run(sessions)
    async with sessions.begin() as session:
        prior_run = ScoutRun(
            user_id=user_id,
            competitor_id=competitor_id,
            run_type=RunType.SOURCE_DISCOVERY,
            status=ScoutRunStatus.COMPLETED,
            scheduled_for=NOW.replace(hour=8),
        )
        prior_task = AgentTask(
            scout_run=prior_run,
            role=AgentTaskRole.MAIN_PLANNER,
            task_kind="source_discovery",
            status=AgentTaskStatus.SUCCEEDED,
            model="competitor-scout-main",
            objective="Historical synthetic usage",
            attempt_count=1,
        )
        session.add(
            UsageEvent(
                user_id=user_id,
                scout_run=prior_run,
                agent_task=prior_task,
                provider_request_id=f"prior-{uuid.uuid4()}",
                model="competitor-scout-main",
                input_tokens=1,
                output_tokens=1,
                tool_calls=0,
                settled_cost_usd=Decimal("5.00"),
                pricing_source="hosted_catalog",
                occurred_at=NOW.replace(hour=9),
            )
        )
    fake = FakeOtari(task_count=1)
    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(max_user_daily_cost_usd=Decimal("5.00")),
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
    assert status is ScoutRunStatus.FAILED
    assert run is not None and run.failure_code == "daily_cost_limit"
    assert fake.calls == []


async def test_estimated_request_over_run_ceiling_stops_before_otari(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=1)
    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(max_run_cost_usd=Decimal("0.10")),
        cost_estimator=lambda _role: Decimal("0.20"),
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
        planner = await session.scalar(select(AgentTask).where(AgentTask.scout_run_id == run_id))
    assert status is ScoutRunStatus.PARTIAL
    assert run is not None and run.partial_reasons == ["cost_ceiling_reached"]
    assert run.input_tokens == 0 and run.settled_cost_usd is None
    assert planner is not None and planner.status is AgentTaskStatus.CANCELLED
    assert fake.calls == []


async def test_estimated_request_over_remaining_daily_ceiling_stops_pre_call(
    daily_store,
) -> None:
    sessions = daily_store
    user_id, competitor_id, run_id = await seed_daily_run(sessions)
    async with sessions.begin() as session:
        prior_run = ScoutRun(
            user_id=user_id,
            competitor_id=competitor_id,
            run_type=RunType.SOURCE_DISCOVERY,
            status=ScoutRunStatus.COMPLETED,
            scheduled_for=NOW.replace(hour=8),
        )
        prior_task = AgentTask(
            scout_run=prior_run,
            role=AgentTaskRole.MAIN_PLANNER,
            task_kind="source_discovery",
            status=AgentTaskStatus.SUCCEEDED,
            model="competitor-scout-main",
            objective="Historical synthetic usage",
            attempt_count=1,
        )
        session.add(
            UsageEvent(
                user_id=user_id,
                scout_run=prior_run,
                agent_task=prior_task,
                provider_request_id=f"prior-estimate-{uuid.uuid4()}",
                model="competitor-scout-main",
                input_tokens=1,
                output_tokens=1,
                tool_calls=0,
                settled_cost_usd=Decimal("4.90"),
                pricing_source="hosted_catalog",
                occurred_at=NOW.replace(hour=9),
            )
        )
    fake = FakeOtari(task_count=1)
    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(
            max_run_cost_usd=Decimal("1.00"),
            max_user_daily_cost_usd=Decimal("5.00"),
        ),
        cost_estimator=lambda _role: Decimal("0.20"),
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
    assert status is ScoutRunStatus.PARTIAL
    assert run is not None and run.partial_reasons == ["cost_ceiling_reached"]
    assert fake.calls == []


async def test_estimated_child_request_stops_before_child_call(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=1)

    def estimate(role: str) -> Decimal:
        return Decimal("0.05") if role == "main" else Decimal("0.20")

    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(max_run_cost_usd=Decimal("0.10")),
        cost_estimator=estimate,
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        child = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.role == AgentTaskRole.CHILD_RESEARCHER,
            )
        )
    assert status is ScoutRunStatus.PARTIAL
    assert child is not None and child.status is AgentTaskStatus.CANCELLED
    assert child.error_code == "cost_ceiling_reached"
    assert [call["output_type"] for call in fake.calls] == [ScoutPlan]


async def test_estimated_synthesis_request_stops_before_synthesis_call(
    daily_store,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=1)
    main_estimates = iter((Decimal("0.02"), Decimal("0.20")))

    def estimate(role: str) -> Decimal:
        if role == "child":
            return Decimal("0.02")
        return next(main_estimates)

    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(max_run_cost_usd=Decimal("0.10")),
        cost_estimator=estimate,
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        synthesis_task = await session.scalar(
            select(AgentTask).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.role == AgentTaskRole.MAIN_SYNTHESIZER,
            )
        )
    assert status is ScoutRunStatus.PARTIAL
    assert synthesis_task is not None
    assert synthesis_task.status is AgentTaskStatus.CANCELLED
    assert synthesis_task.error_code == "cost_ceiling_reached"
    assert not any(call["output_type"] is SynthesisResult for call in fake.calls)


@pytest.mark.parametrize(
    "estimate",
    [None, "not-a-decimal", Decimal("NaN"), Decimal("-0.01")],
)
async def test_invalid_or_unavailable_cost_estimates_do_not_claim_a_known_guard(
    daily_store,
    estimate: object,
) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=1, known_cost=Decimal("0.01"))
    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(),
        cost_estimator=lambda _role: estimate,  # type: ignore[return-value]
    )

    assert await orchestrator.execute_daily_run(run_id) is ScoutRunStatus.COMPLETED
    assert len(fake.calls) == 3


async def test_settled_cost_stops_unstarted_child_wave_and_marks_partial(daily_store) -> None:
    sessions = daily_store
    _user_id, _competitor_id, run_id = await seed_daily_run(sessions)
    fake = FakeOtari(task_count=5, known_cost=Decimal("0.20"))
    orchestrator = await make_orchestrator(
        sessions,
        fake,
        settings(
            max_run_cost_usd=Decimal("1.00"),
            max_user_daily_cost_usd=Decimal("10.00"),
        ),
    )

    status = await orchestrator.execute_daily_run(run_id)

    async with sessions() as session:
        run = await session.get(ScoutRun, run_id)
        cancelled = await session.scalar(
            select(func.count(AgentTask.id)).where(
                AgentTask.scout_run_id == run_id,
                AgentTask.status == AgentTaskStatus.CANCELLED,
            )
        )
        evidence_count = await session.scalar(
            select(func.count(EvidenceItem.id)).where(EvidenceItem.scout_run_id == run_id)
        )
    assert status is ScoutRunStatus.PARTIAL
    assert run is not None and run.partial_reasons == ["run_cost_limit"]
    assert run.settled_cost_usd == Decimal("1.000000")
    assert cancelled == 1 and evidence_count == 4
    assert not any(call["output_type"] is SynthesisResult for call in fake.calls)


async def test_scheduler_enqueues_dst_fallback_only_once(daily_store) -> None:
    sessions = daily_store
    async with sessions.begin() as session:
        user = User(
            email=f"dst-{uuid.uuid4().hex}@example.com",
            display_name="DST Owner",
            timezone="Europe/Berlin",
        )
        competitor = Competitor(
            user=user,
            name="DST Acme",
            primary_domain="dst-acme.example",
            status=CompetitorStatus.ACTIVE,
            daily_run_time_local=time(2, 30),
        )
        session.add(competitor)

    async with sessions.begin() as session:
        first = await schedule_due_daily_runs(
            session,
            now=datetime(2026, 10, 25, 0, 31, tzinfo=UTC),
        )
    async with sessions.begin() as session:
        second = await schedule_due_daily_runs(
            session,
            now=datetime(2026, 10, 25, 1, 31, tzinfo=UTC),
        )
    async with sessions() as session:
        run_count = await session.scalar(
            select(func.count(ScoutRun.id)).where(
                ScoutRun.competitor_id == competitor.id,
                ScoutRun.run_type == RunType.DAILY_SCOUT,
            )
        )
        job_count = await session.scalar(
            select(func.count(Job.id)).where(Job.job_type == "daily_scout")
        )

    assert len(first) == 1 and len(second) == 1
    assert first[0].id == second[0].id
    assert run_count == 1 and job_count >= 1
