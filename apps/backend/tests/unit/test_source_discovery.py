from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from competitor_scout.agents.client import (
    OtariClient,
    OtariError,
    OtariMetadata,
    OtariUsage,
)
from competitor_scout.agents.contracts import DiscoveredSource, SourceDiscoveryResult
from competitor_scout.agents.orchestrator import (
    SourceDiscoveryOutcome,
    SourceDiscoveryService,
)
from competitor_scout.config import Settings
from competitor_scout.jobs.handlers import SourceDiscoveryHandler
from competitor_scout.models.auth import User
from competitor_scout.models.intelligence import (
    AgentTask,
    AgentTaskRole,
    AgentTaskStatus,
    ApprovalStatus,
    Competitor,
    CompetitorStatus,
    MonitoredSource,
    RunType,
    ScoutRun,
    ScoutRunStatus,
    SourceCategory,
    UsageEvent,
)
from competitor_scout.security.urls import UnsafeSourceUrl

NOW = datetime(2026, 8, 21, 12, 3, tzinfo=UTC)
UrlValidator = Callable[[str], Awaitable[str]]


def discovery_settings() -> Settings:
    return Settings(
        environment="test",
        database_url="postgresql+asyncpg://test:test@localhost/test",
        public_base_url="https://testserver",
        session_secret="s" * 32,
        csrf_secret="c" * 32,
        google_client_id="google-id",
        google_client_secret="google-secret",
        otari_base_url="https://otari.invalid",
        otari_ai_token="dummy-never-live",
        otari_main_model_alias="competitor-scout-main",
        max_child_search_calls=2,
    )


def source(
    url: str = "https://acme.example/pricing",
    *,
    category: str = "pricing",
) -> DiscoveredSource:
    return DiscoveredSource.model_validate_json(
        json.dumps(
            {
                "url": url,
                "title": f"Synthetic {category}",
                "category": category,
                "reason": "Useful public first-party monitoring source",
            }
        )
    )


def metadata() -> OtariMetadata:
    return OtariMetadata(
        request_id="req-discovery-synthetic",
        usage=OtariUsage(
            input_tokens=120,
            output_tokens=44,
            tool_calls=None,
            cost_usd=None,
            pricing_source=None,
        ),
    )


class FakeValidator:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, value: str) -> str:
        self.calls.append(value)
        if "127.0.0.1" in value:
            raise UnsafeSourceUrl("synthetic unsafe URL")
        return value.split("?", 1)[0].split("#", 1)[0].casefold()


class FakeDiscoveryService:
    def __init__(self, outcome: SourceDiscoveryOutcome | Exception) -> None:
        self.outcome = outcome
        self.calls: list[tuple[str, uuid.UUID]] = []

    async def discover(self, *, domain: str, run_id: uuid.UUID) -> SourceDiscoveryOutcome:
        self.calls.append((domain, run_id))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest_asyncio.fixture
async def discovery_store(migrated_database_url: str):
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        await engine.dispose()


async def seed_discovery_run(
    sessions,
    stem: str,
    *,
    status: CompetitorStatus = CompetitorStatus.DISCOVERING,
    run_user_mismatch: bool = False,
    scheduled_for: datetime = NOW,
) -> uuid.UUID:
    async with sessions.begin() as session:
        owner = User(email=f"{stem}-{uuid.uuid4().hex}@example.com", display_name="Owner")
        competitor = Competitor(
            user=owner,
            name="Acme",
            primary_domain=f"{uuid.uuid4().hex}.example",
            status=status,
            deleted_at=NOW if status is CompetitorStatus.DELETED else None,
        )
        run_user = owner
        if run_user_mismatch:
            run_user = User(
                email=f"mismatch-{uuid.uuid4().hex}@example.com",
                display_name="Other",
            )
        run = ScoutRun(
            user=run_user,
            competitor=competitor,
            run_type=RunType.SOURCE_DISCOVERY,
            scheduled_for=scheduled_for,
        )
        session.add(run)
        await session.flush()
        return run.id


async def legacy_handle(handler, sessions, run_id: uuid.UUID) -> ScoutRunStatus:
    return await handler.handle(run_id=run_id)


def test_source_discovery_contract_permits_an_empty_bounded_list() -> None:
    result = SourceDiscoveryResult.model_validate_json('{"sources":[]}')

    assert result.sources == []


async def test_discovery_uses_exact_hosted_tool_contract_and_filters_sources() -> None:
    response_payload = {
        "sources": [
            {
                "url": "https://ACME.example/pricing?campaign=x",
                "title": "Pricing",
                "category": "pricing",
                "reason": "Plans",
            },
            {
                "url": "https://acme.example/pricing#duplicate",
                "title": "Duplicate",
                "category": "pricing",
                "reason": "Duplicate",
            },
            {
                "url": "https://evil.example/phish",
                "title": "Outside",
                "category": "other",
                "reason": "Outside domain",
            },
            {
                "url": "https://127.0.0.1/private",
                "title": "Unsafe",
                "category": "other",
                "reason": "Unsafe",
            },
        ]
    }

    async def transport_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads((await request.aread()).decode())
        assert body["model"] == "competitor-scout-main"
        assert body["tools"] == [{"type": "otari_web_search"}]
        assert body["parallel_tool_calls"] is False
        assert body["max_tool_iterations"] == 3
        assert body["session_label"].startswith("source-discovery:")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(response_payload)}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 44},
            },
            headers={"X-Otari-Request-ID": "req-discovery-synthetic"},
        )

    validator = FakeValidator()
    async with OtariClient(
        discovery_settings(),
        transport=httpx.MockTransport(transport_handler),
    ) as client:
        outcome = await SourceDiscoveryService(
            client=client,
            settings=discovery_settings(),
            url_validator=validator,
        ).discover(domain="acme.example", run_id=uuid.uuid4())

    assert [str(item.url) for item in outcome.sources] == ["https://acme.example/pricing"]
    assert outcome.rejected_count == 3
    assert len(validator.calls) == 4
    assert outcome.metadata.request_id == "req-discovery-synthetic"


async def test_handler_commits_claim_before_external_call_and_concurrent_call_is_noop(
    discovery_store,
) -> None:
    run_id = await seed_discovery_run(discovery_store, "atomic-claim")
    entered = asyncio.Event()
    release = asyncio.Event()

    class InspectingService:
        def __init__(self) -> None:
            self.calls = 0
            self.observed_status: ScoutRunStatus | None = None
            self.observed_task_count = 0

        async def discover(self, *, domain: str, run_id: uuid.UUID) -> SourceDiscoveryOutcome:
            self.calls += 1
            async with discovery_store() as observer:
                self.observed_status = await observer.scalar(
                    select(ScoutRun.status).where(ScoutRun.id == run_id)
                )
                self.observed_task_count = len(
                    (
                        await observer.scalars(
                            select(AgentTask).where(AgentTask.scout_run_id == run_id)
                        )
                    ).all()
                )
            entered.set()
            await release.wait()
            return SourceDiscoveryOutcome((source(),), metadata(), 0)

    service = InspectingService()
    handler = SourceDiscoveryHandler(
        discovery_store,
        service=service,
        settings=discovery_settings(),
        now=lambda: NOW,
    )
    first = asyncio.create_task(legacy_handle(handler, discovery_store, run_id))
    await asyncio.wait_for(entered.wait(), timeout=2)
    second = asyncio.create_task(legacy_handle(handler, discovery_store, run_id))
    await asyncio.sleep(0.05)

    assert service.observed_status is ScoutRunStatus.PLANNING
    assert service.observed_task_count == 1
    assert service.calls == 1
    release.set()
    first_status, second_status = await asyncio.gather(first, second)

    assert first_status is ScoutRunStatus.COMPLETED
    assert second_status in {ScoutRunStatus.PLANNING, ScoutRunStatus.COMPLETED}
    assert service.calls == 1
    async with discovery_store() as session:
        tasks = list(
            (await session.scalars(select(AgentTask).where(AgentTask.scout_run_id == run_id))).all()
        )
    assert len(tasks) == 1


@pytest.mark.parametrize(
    "run_user_mismatch,status",
    [
        (False, CompetitorStatus.DELETED),
        (True, CompetitorStatus.DISCOVERING),
    ],
    ids=["deleted", "ownership-mismatch"],
)
async def test_handler_rejects_ineligible_competitor_before_external_call(
    discovery_store,
    run_user_mismatch: bool,
    status: CompetitorStatus,
) -> None:
    run_id = await seed_discovery_run(
        discovery_store,
        "ineligible",
        status=status,
        run_user_mismatch=run_user_mismatch,
    )
    service = FakeDiscoveryService(SourceDiscoveryOutcome((source(),), metadata(), 0))

    result = await legacy_handle(
        SourceDiscoveryHandler(
            discovery_store,
            service=service,
            settings=discovery_settings(),
            now=lambda: NOW,
        ),
        discovery_store,
        run_id,
    )

    assert result is ScoutRunStatus.FAILED
    assert service.calls == []
    async with discovery_store() as session:
        run = await session.get(ScoutRun, run_id)
        task_count = len(
            (await session.scalars(select(AgentTask).where(AgentTask.scout_run_id == run_id))).all()
        )
    assert run is not None and run.failure_code == "competitor_ineligible"
    assert task_count == 0


async def test_handler_retries_retryable_otari_error_once(discovery_store) -> None:
    run_id = await seed_discovery_run(discovery_store, "retry")

    class RetryThenSucceed:
        def __init__(self) -> None:
            self.calls = 0

        async def discover(self, *, domain: str, run_id: uuid.UUID) -> SourceDiscoveryOutcome:
            self.calls += 1
            if self.calls == 1:
                raise OtariError("otari_timeout", retryable=True)
            return SourceDiscoveryOutcome((source(),), metadata(), 0)

    service = RetryThenSucceed()
    result = await legacy_handle(
        SourceDiscoveryHandler(
            discovery_store,
            service=service,
            settings=discovery_settings(),
            now=lambda: NOW,
        ),
        discovery_store,
        run_id,
    )

    assert result is ScoutRunStatus.COMPLETED
    assert service.calls == 2
    async with discovery_store() as session:
        task = await session.scalar(select(AgentTask).where(AgentTask.scout_run_id == run_id))
    assert task is not None and task.attempt_count == 2


async def test_handler_stops_before_source_discovery_would_exceed_cost_limit(
    discovery_store,
) -> None:
    run_id = await seed_discovery_run(discovery_store, "cost-limit")
    service = FakeDiscoveryService(SourceDiscoveryOutcome((source(),), metadata(), 0))
    settings = discovery_settings()

    result = await SourceDiscoveryHandler(
        discovery_store,
        service=service,
        settings=settings,
        now=lambda: NOW,
        cost_estimator=lambda _model, _tokens, _search: settings.max_run_cost_usd + Decimal("0.01"),
    ).handle(run_id=run_id)

    assert result is ScoutRunStatus.PARTIAL
    assert service.calls == []
    async with discovery_store() as session:
        run = await session.get(ScoutRun, run_id)
        task = await session.scalar(select(AgentTask).where(AgentTask.scout_run_id == run_id))
    assert run is not None and run.partial_reasons == ["cost_ceiling_reached"]
    assert task is not None and task.status is AgentTaskStatus.CANCELLED
    assert task.error_code == "cost_ceiling_reached"


async def test_stale_planning_run_is_terminally_failed_without_repeating_otari(
    discovery_store,
) -> None:
    run_id = await seed_discovery_run(discovery_store, "stale")
    async with discovery_store.begin() as session:
        run = await session.get(ScoutRun, run_id)
        assert run is not None
        run.status = ScoutRunStatus.PLANNING
        run.started_at = NOW.replace(minute=0)
        session.add(
            AgentTask(
                scout_run_id=run.id,
                role=AgentTaskRole.MAIN_PLANNER,
                task_kind="source_discovery",
                status=AgentTaskStatus.RUNNING,
                model_alias="competitor-scout-main",
                objective="Discover sources",
                attempt_count=1,
                started_at=NOW.replace(minute=0),
            )
        )
    service = FakeDiscoveryService(SourceDiscoveryOutcome((source(),), metadata(), 0))
    handler = SourceDiscoveryHandler(
        discovery_store,
        service=service,
        settings=discovery_settings(),
        now=lambda: NOW,
    )

    first = await legacy_handle(handler, discovery_store, run_id)
    second = await legacy_handle(handler, discovery_store, run_id)

    assert first is ScoutRunStatus.FAILED
    assert second is ScoutRunStatus.FAILED
    assert service.calls == []
    async with discovery_store() as session:
        run = await session.get(ScoutRun, run_id)
        tasks = list(
            (await session.scalars(select(AgentTask).where(AgentTask.scout_run_id == run_id))).all()
        )
    assert run is not None and run.failure_code == "interrupted_source_discovery"
    assert len(tasks) == 1 and tasks[0].status is AgentTaskStatus.FAILED


async def test_source_upsert_handles_concurrent_insert_without_changing_approval(
    discovery_store,
) -> None:
    run_id = await seed_discovery_run(discovery_store, "upsert-race")
    async with discovery_store() as session:
        run = await session.get(ScoutRun, run_id)
        assert run is not None and run.competitor_id is not None
        competitor_id = run.competitor_id

    blocker = discovery_store()
    blocker_transaction = await blocker.begin()
    blocker.add(
        MonitoredSource(
            competitor_id=competitor_id,
            url="https://acme.example/pricing",
            normalized_url="https://acme.example/pricing",
            source_category=SourceCategory.PRICING,
            title="Approved title",
            discovery_reason="Approved reason",
            approval_status=ApprovalStatus.APPROVED,
        )
    )
    await blocker.flush()
    outcome = SourceDiscoveryOutcome((source(),), metadata(), 0)
    handler = SourceDiscoveryHandler(
        discovery_store,
        service=FakeDiscoveryService(outcome),
        settings=discovery_settings(),
        now=lambda: NOW,
    )
    handling = asyncio.create_task(handler.handle(run_id=run_id))
    await asyncio.sleep(0.05)
    assert not handling.done()
    await blocker_transaction.commit()
    await blocker.close()
    result = await handling

    assert result is ScoutRunStatus.COMPLETED
    async with discovery_store() as session:
        sources = list(
            (
                await session.scalars(
                    select(MonitoredSource).where(MonitoredSource.competitor_id == competitor_id)
                )
            ).all()
        )
    assert len(sources) == 1
    assert sources[0].approval_status is ApprovalStatus.APPROVED


async def test_handler_upserts_suggestions_preserving_decisions_and_usage_nulls(
    discovery_store,
) -> None:
    async with discovery_store.begin() as session:
        user = User(email=f"discovery-{uuid.uuid4().hex}@example.com", display_name="Owner")
        competitor = Competitor(user=user, name="Acme", primary_domain="acme.example")
        existing = MonitoredSource(
            competitor=competitor,
            url="https://acme.example/pricing",
            normalized_url="https://acme.example/pricing",
            source_category=SourceCategory.PRICING,
            title="Old title",
            discovery_reason="Previously reviewed",
            approval_status=ApprovalStatus.APPROVED,
        )
        run = ScoutRun(
            user=user,
            competitor=competitor,
            run_type=RunType.SOURCE_DISCOVERY,
            scheduled_for=NOW,
        )
        session.add_all([existing, run])
        await session.flush()
        competitor_id, existing_id, run_id = competitor.id, existing.id, run.id
    service = FakeDiscoveryService(
        SourceDiscoveryOutcome(
            sources=(source(), source("https://acme.example/blog", category="blog")),
            metadata=metadata(),
            rejected_count=0,
        )
    )

    await SourceDiscoveryHandler(
        discovery_store,
        service=service,
        settings=discovery_settings(),
        now=lambda: NOW,
    ).handle(run_id=run_id)

    async with discovery_store() as session:
        sources = list(
            (
                await session.scalars(
                    select(MonitoredSource)
                    .where(MonitoredSource.competitor_id == competitor_id)
                    .order_by(MonitoredSource.normalized_url)
                )
            ).all()
        )
        task = await session.scalar(select(AgentTask).where(AgentTask.scout_run_id == run_id))
        usage = await session.scalar(select(UsageEvent).where(UsageEvent.scout_run_id == run_id))
        run = await session.get(ScoutRun, run_id)

    assert run is not None
    assert run.status is ScoutRunStatus.COMPLETED
    assert run.input_tokens == 120 and run.output_tokens == 44
    assert run.tool_calls is None and run.settled_cost_usd is None
    assert len(sources) == 2
    persisted_existing = next(item for item in sources if item.id == existing_id)
    assert persisted_existing.approval_status is ApprovalStatus.APPROVED
    assert task is not None and task.status is AgentTaskStatus.SUCCEEDED
    assert task.otari_request_id == "req-discovery-synthetic"
    assert task.tool_calls is None and task.settled_cost_usd is None
    assert usage is not None and usage.tool_calls is None
    assert usage.settled_cost_usd is None and usage.pricing_source is None


async def test_handler_records_usage_without_provider_request_id(discovery_store) -> None:
    run_id = await seed_discovery_run(discovery_store, "missing-request-id")
    outcome = SourceDiscoveryOutcome(
        sources=(source(),),
        metadata=OtariMetadata(
            request_id=None,
            usage=OtariUsage(
                input_tokens=17,
                output_tokens=5,
                tool_calls=None,
                cost_usd=None,
                pricing_source=None,
            ),
        ),
        rejected_count=0,
    )

    await SourceDiscoveryHandler(
        discovery_store,
        service=FakeDiscoveryService(outcome),
        settings=discovery_settings(),
        now=lambda: NOW,
    ).handle(run_id=run_id)

    async with discovery_store() as session:
        usage = await session.scalar(select(UsageEvent).where(UsageEvent.scout_run_id == run_id))

    assert usage is not None
    assert usage.provider_request_id is None
    assert usage.input_tokens == 17
    assert usage.output_tokens == 5


@pytest.mark.parametrize(
    ("outcome", "expected_status", "reason"),
    [
        (
            SourceDiscoveryOutcome(
                sources=(),
                metadata=metadata(),
                rejected_count=0,
            ),
            ScoutRunStatus.PARTIAL,
            "insufficient_sources",
        ),
        (
            OtariError("otari_upstream_error", retryable=True),
            ScoutRunStatus.FAILED,
            "otari_upstream_error",
        ),
    ],
)
async def test_handler_marks_empty_partial_and_provider_error_failed(
    discovery_store,
    outcome: SourceDiscoveryOutcome | Exception,
    expected_status: ScoutRunStatus,
    reason: str,
) -> None:
    run_id = await seed_discovery_run(discovery_store, "state")

    await SourceDiscoveryHandler(
        discovery_store,
        service=FakeDiscoveryService(outcome),
        settings=discovery_settings(),
        now=lambda: NOW,
    ).handle(run_id=run_id)
    async with discovery_store() as session:
        run = await session.get(ScoutRun, run_id)

    assert run is not None
    assert run.status is expected_status
    if expected_status is ScoutRunStatus.PARTIAL:
        assert run.partial_reasons == [reason]
    else:
        assert run.failure_code == reason


def test_exact_decimal_metadata_is_preserved_by_handler_contract() -> None:
    exact = OtariMetadata(
        request_id="req-priced",
        usage=OtariUsage(1, 2, 1, Decimal("0.001234"), "hosted_catalog"),
    )

    assert exact.usage.cost_usd == Decimal("0.001234")
