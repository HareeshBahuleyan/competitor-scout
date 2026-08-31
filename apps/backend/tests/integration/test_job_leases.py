from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from competitor_scout.jobs.repository import (
    JobRepository,
    LeaseOwnershipError,
    enqueue_in_session,
    json_safe_payload,
    utc_now,
)
from competitor_scout.models.auth import User
from competitor_scout.models.intelligence import (
    AgentTask,
    AgentTaskRole,
    AgentTaskStatus,
    Competitor,
    RunType,
    ScoutRun,
    ScoutRunStatus,
    UsageEvent,
)
from competitor_scout.models.jobs import Job, JobStatus

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def test_repository_clock_and_payload_boundary_validation() -> None:
    assert utc_now().tzinfo is UTC
    with pytest.raises(ValueError, match="JSON object"):
        json_safe_payload(["not", "an", "object"])  # type: ignore[arg-type]


@dataclass
class MutableClock:
    current: datetime = NOW

    def __call__(self) -> datetime:
        return self.current

    def advance(self, *, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


@pytest_asyncio.fixture
async def job_store(migrated_database_url: str):
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        await session.execute(delete(Job))
    clock = MutableClock()
    try:
        yield sessions, clock
    finally:
        async with sessions.begin() as session:
            await session.execute(delete(Job))
        await engine.dispose()


async def test_enqueue_is_idempotent_under_concurrency_and_payload_is_json_safe(job_store) -> None:
    sessions, clock = job_store
    repository = JobRepository(sessions, now=clock)
    key = f"daily:{uuid.uuid4()}"

    first, second = await asyncio.gather(
        repository.enqueue("daily_scout", key, {"competitor_id": "one"}),
        repository.enqueue("daily_scout", key, {"competitor_id": "two"}),
    )

    assert first.id == second.id
    async with sessions() as session:
        count = await session.scalar(select(func.count(Job.id)).where(Job.deduplication_key == key))
        persisted_payload = await session.scalar(
            select(Job.payload).where(Job.deduplication_key == key)
        )
    assert count == 1
    assert persisted_payload in ({"competitor_id": "one"}, {"competitor_id": "two"})
    with pytest.raises(ValueError, match="JSON"):
        await repository.enqueue("daily_scout", f"unsafe:{uuid.uuid4()}", {"cost": Decimal("1")})


async def test_repository_rejects_naive_clocks_schedules_and_nonpositive_leases(
    job_store,
) -> None:
    sessions, clock = job_store
    naive = NOW.replace(tzinfo=None)
    naive_clock_repository = JobRepository(sessions, now=lambda: naive)

    with pytest.raises(ValueError, match="clock"):
        await naive_clock_repository.enqueue("daily_scout", "naive-clock", {"id": "x"})

    repository = JobRepository(sessions, now=clock)
    with pytest.raises(ValueError, match="available_at"):
        await repository.enqueue(
            "daily_scout",
            "naive-schedule",
            {"id": "x"},
            available_at=naive,
        )
    async with sessions.begin() as session:
        with pytest.raises(ValueError, match="available_at"):
            await enqueue_in_session(
                session,
                "daily_scout",
                "naive-in-session",
                {"id": "x"},
                available_at=naive,
            )
    with pytest.raises(ValueError, match="positive"):
        await repository.claim("worker-a", lease_seconds=0)
    with pytest.raises(ValueError, match="positive"):
        await repository.renew(uuid.uuid4(), "worker-a", lease_seconds=0)


async def test_concurrent_claims_use_independent_transactions_and_skip_locked(job_store) -> None:
    sessions, clock = job_store
    locked = asyncio.Event()
    release = asyncio.Event()

    async def hold_after_lock() -> None:
        locked.set()
        await release.wait()

    blocking_repository = JobRepository(sessions, now=clock, after_claim_lock=hold_after_lock)
    other_repository = JobRepository(sessions, now=clock)
    job = await other_repository.enqueue("daily_scout", f"claim:{uuid.uuid4()}", {"id": "x"})

    first_claim_task = asyncio.create_task(blocking_repository.claim("worker-a", lease_seconds=30))
    await asyncio.wait_for(locked.wait(), timeout=2)
    second_claim = await other_repository.claim("worker-b", lease_seconds=30)
    release.set()
    first_claim = await asyncio.wait_for(first_claim_task, timeout=2)

    assert first_claim is not None
    assert first_claim.id == job.id
    assert first_claim.lease_owner == "worker-a"
    assert second_claim is None


async def test_expired_lease_can_be_reclaimed(job_store) -> None:
    sessions, clock = job_store
    repository = JobRepository(sessions, now=clock)
    job = await repository.enqueue("daily_scout", f"reclaim:{uuid.uuid4()}", {"id": "x"})
    first = await repository.claim("worker-a", lease_seconds=1)
    assert first is not None
    clock.advance(seconds=2)

    reclaimed = await repository.claim("worker-b", lease_seconds=30)

    assert reclaimed is not None
    assert reclaimed.id == job.id
    assert reclaimed.lease_owner == "worker-b"
    assert reclaimed.attempt_count == 2
    assert reclaimed.lease_expires_at == clock.current + timedelta(seconds=30)


async def test_matching_owner_can_renew_complete_and_fail(job_store) -> None:
    sessions, clock = job_store
    repository = JobRepository(sessions, now=clock)
    first = await repository.enqueue("daily_scout", f"complete:{uuid.uuid4()}", {"id": "one"})
    claimed = await repository.claim("worker-a", lease_seconds=30)
    assert claimed is not None and claimed.id == first.id

    clock.advance(seconds=5)
    renewed = await repository.renew(first.id, "worker-a", lease_seconds=60)
    assert renewed.lease_expires_at == clock.current + timedelta(seconds=60)

    for operation in (
        repository.renew(first.id, "worker-b", lease_seconds=60),
        repository.complete(first.id, "worker-b"),
        repository.fail(first.id, "worker-b", error_code="wrong-owner"),
    ):
        with pytest.raises(LeaseOwnershipError):
            await operation

    completed = await repository.complete(first.id, "worker-a")
    assert completed.status is JobStatus.COMPLETED
    assert completed.lease_owner is None
    assert completed.lease_expires_at is None

    second = await repository.enqueue("weekly_brief", f"fail:{uuid.uuid4()}", {"id": "two"})
    claimed_second = await repository.claim("worker-c", lease_seconds=30)
    assert claimed_second is not None and claimed_second.id == second.id
    failed = await repository.fail(second.id, "worker-c", error_code="provider_unavailable")
    assert failed.status is JobStatus.FAILED
    assert failed.last_error_code == "provider_unavailable"
    assert failed.lease_owner is None


async def test_expired_owner_cannot_renew_or_finish(job_store) -> None:
    sessions, clock = job_store
    repository = JobRepository(sessions, now=clock)
    job = await repository.enqueue("daily_scout", f"expired-owner:{uuid.uuid4()}", {"id": "x"})
    claimed = await repository.claim("worker-a", lease_seconds=1)
    assert claimed is not None
    clock.advance(seconds=2)

    with pytest.raises(LeaseOwnershipError):
        await repository.renew(job.id, "worker-a", lease_seconds=30)
    with pytest.raises(LeaseOwnershipError):
        await repository.complete(job.id, "worker-a")
    with pytest.raises(LeaseOwnershipError):
        await repository.fail(job.id, "worker-a", error_code="late")


async def test_run_task_and_usage_persist_exact_costs_and_safe_json(db_session) -> None:
    user = User(email=f"run-{uuid.uuid4().hex}@example.com", display_name="Run Owner")
    run = ScoutRun(
        user=user,
        run_type=RunType.WEEKLY_BRIEF,
        status=ScoutRunStatus.SYNTHESIZING,
        scheduled_for=NOW,
        started_at=NOW,
        partial_reasons=["one source unavailable"],
        input_tokens=100,
        output_tokens=20,
        tool_calls=2,
        settled_cost_usd=Decimal("0.123456"),
    )
    task = AgentTask(
        scout_run=run,
        role=AgentTaskRole.MAIN_SYNTHESIZER,
        task_kind="weekly_synthesis",
        status=AgentTaskStatus.SUCCEEDED,
        model_alias="competitor-scout-main",
        objective="Summarize validated findings",
        source_scope=["https://example.com/news"],
        attempt_count=1,
        started_at=NOW,
        completed_at=NOW,
        otari_request_id="request-safe-id",
        input_tokens=100,
        output_tokens=20,
        tool_calls=2,
        settled_cost_usd=Decimal("0.123456"),
        validated_output={"sections": [{"title": "Launch", "finding_ids": ["safe-id"]}]},
    )
    usage = UsageEvent(
        user=user,
        scout_run=run,
        agent_task=task,
        provider_request_id="request-safe-id",
        model_alias="competitor-scout-main",
        input_tokens=100,
        output_tokens=20,
        tool_calls=2,
        settled_cost_usd=Decimal("0.123456"),
        occurred_at=NOW,
    )
    db_session.add(usage)
    await db_session.flush()
    db_session.expunge_all()

    persisted_run = await db_session.get(ScoutRun, run.id)
    persisted_task = await db_session.get(AgentTask, task.id)
    persisted_usage = await db_session.get(UsageEvent, usage.id)

    assert persisted_run is not None
    assert persisted_run.competitor_id is None
    assert persisted_run.partial_reasons == ["one source unavailable"]
    assert persisted_run.settled_cost_usd == Decimal("0.123456")
    assert persisted_task is not None
    assert persisted_task.validated_output == {
        "sections": [{"title": "Launch", "finding_ids": ["safe-id"]}]
    }
    assert persisted_task.settled_cost_usd == Decimal("0.123456")
    assert persisted_usage is not None
    assert persisted_usage.settled_cost_usd == Decimal("0.123456")


async def test_unknown_accounting_stays_null_and_known_zero_stays_priced_zero(
    db_session,
) -> None:
    user = User(email=f"accounting-{uuid.uuid4().hex}@example.com", display_name="Accounting")
    unknown_run = ScoutRun(
        user=user,
        run_type=RunType.WEEKLY_BRIEF,
        scheduled_for=NOW,
        tool_calls=None,
        settled_cost_usd=None,
    )
    unknown_task = AgentTask(
        scout_run=unknown_run,
        role=AgentTaskRole.MAIN_SYNTHESIZER,
        task_kind="weekly_synthesis",
        model_alias="competitor-scout-main",
        objective="Unknown accounting",
        tool_calls=None,
        settled_cost_usd=None,
        pricing_source=None,
    )
    unknown_usage = UsageEvent(
        user=user,
        scout_run=unknown_run,
        agent_task=unknown_task,
        provider_request_id="unknown-accounting",
        model_alias="competitor-scout-main",
        input_tokens=0,
        output_tokens=0,
        tool_calls=None,
        settled_cost_usd=None,
        pricing_source=None,
        occurred_at=NOW,
    )
    zero_run = ScoutRun(
        user=user,
        run_type=RunType.WEEKLY_BRIEF,
        scheduled_for=NOW + timedelta(seconds=1),
        tool_calls=0,
        settled_cost_usd=Decimal("0"),
    )
    zero_task = AgentTask(
        scout_run=zero_run,
        role=AgentTaskRole.MAIN_SYNTHESIZER,
        task_kind="weekly_synthesis",
        model_alias="competitor-scout-main",
        objective="Priced zero accounting",
        tool_calls=0,
        settled_cost_usd=Decimal("0"),
        pricing_source="hosted_catalog",
    )
    zero_usage = UsageEvent(
        user=user,
        scout_run=zero_run,
        agent_task=zero_task,
        provider_request_id="priced-zero-accounting",
        model_alias="competitor-scout-main",
        input_tokens=0,
        output_tokens=0,
        tool_calls=0,
        settled_cost_usd=Decimal("0"),
        pricing_source="hosted_catalog",
        occurred_at=NOW,
    )
    db_session.add_all([unknown_usage, zero_usage])
    await db_session.flush()
    ids = {
        "unknown_run": unknown_run.id,
        "unknown_task": unknown_task.id,
        "unknown_usage": unknown_usage.id,
        "zero_run": zero_run.id,
        "zero_task": zero_task.id,
        "zero_usage": zero_usage.id,
    }
    db_session.expunge_all()

    unknown_values = [
        await db_session.get(ScoutRun, ids["unknown_run"]),
        await db_session.get(AgentTask, ids["unknown_task"]),
        await db_session.get(UsageEvent, ids["unknown_usage"]),
    ]
    zero_values = [
        await db_session.get(ScoutRun, ids["zero_run"]),
        await db_session.get(AgentTask, ids["zero_task"]),
        await db_session.get(UsageEvent, ids["zero_usage"]),
    ]

    assert all(value is not None for value in unknown_values + zero_values)
    assert all(value.tool_calls is None for value in unknown_values if value is not None)
    assert all(value.settled_cost_usd is None for value in unknown_values if value is not None)
    assert all(value.tool_calls == 0 for value in zero_values if value is not None)
    assert all(value.settled_cost_usd == Decimal("0") for value in zero_values if value is not None)
    assert unknown_values[1] is not None and unknown_values[1].pricing_source is None
    assert unknown_values[2] is not None and unknown_values[2].pricing_source is None
    assert zero_values[1] is not None and zero_values[1].pricing_source == "hosted_catalog"
    assert zero_values[2] is not None and zero_values[2].pricing_source == "hosted_catalog"


async def test_run_schedule_idempotency_handles_nullable_competitor(db_session) -> None:
    user = User(email=f"schedule-{uuid.uuid4().hex}@example.com", display_name="Scheduler")
    competitor = Competitor(user=user, name="Acme", primary_domain=f"{uuid.uuid4().hex}.example")
    db_session.add(competitor)
    await db_session.flush()

    daily = ScoutRun(
        user_id=user.id,
        competitor_id=competitor.id,
        run_type=RunType.DAILY_SCOUT,
        status=ScoutRunStatus.COMPLETED,
        scheduled_for=NOW,
    )
    weekly = ScoutRun(
        user_id=user.id,
        competitor_id=None,
        run_type=RunType.WEEKLY_BRIEF,
        status=ScoutRunStatus.COMPLETED,
        scheduled_for=NOW,
    )
    db_session.add_all([daily, weekly])
    await db_session.flush()

    duplicates = [
        ScoutRun(
            user_id=user.id,
            competitor_id=competitor.id,
            run_type=RunType.DAILY_SCOUT,
            status=ScoutRunStatus.COMPLETED,
            scheduled_for=NOW,
        ),
        ScoutRun(
            user_id=user.id,
            competitor_id=None,
            run_type=RunType.WEEKLY_BRIEF,
            status=ScoutRunStatus.COMPLETED,
            scheduled_for=NOW,
        ),
    ]
    for duplicate in duplicates:
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(duplicate)
                await db_session.flush()


async def test_run_scope_requires_competitors_except_for_weekly_briefs(db_session) -> None:
    user = User(email=f"scope-{uuid.uuid4().hex}@example.com", display_name="Scoped Runner")
    competitor = Competitor(user=user, name="Acme", primary_domain=f"{uuid.uuid4().hex}.example")
    db_session.add(competitor)
    await db_session.flush()

    invalid_runs = [
        ScoutRun(
            user_id=user.id,
            competitor_id=None,
            run_type=RunType.DAILY_SCOUT,
            scheduled_for=NOW,
        ),
        ScoutRun(
            user_id=user.id,
            competitor_id=competitor.id,
            run_type=RunType.WEEKLY_BRIEF,
            scheduled_for=NOW,
        ),
    ]
    for invalid_run in invalid_runs:
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                db_session.add(invalid_run)
                await db_session.flush()


async def test_one_active_daily_or_manual_run_but_discovery_can_coexist(db_session) -> None:
    user = User(email=f"active-{uuid.uuid4().hex}@example.com", display_name="Active Runner")
    competitor = Competitor(user=user, name="Acme", primary_domain=f"{uuid.uuid4().hex}.example")
    db_session.add(competitor)
    await db_session.flush()
    daily = ScoutRun(
        user_id=user.id,
        competitor_id=competitor.id,
        run_type=RunType.DAILY_SCOUT,
        status=ScoutRunStatus.GATHERING,
        scheduled_for=NOW,
    )
    discovery = ScoutRun(
        user_id=user.id,
        competitor_id=competitor.id,
        run_type=RunType.SOURCE_DISCOVERY,
        status=ScoutRunStatus.PLANNING,
        scheduled_for=NOW + timedelta(seconds=1),
    )
    db_session.add_all([daily, discovery])
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                ScoutRun(
                    user_id=user.id,
                    competitor_id=competitor.id,
                    run_type=RunType.MANUAL_SCOUT,
                    scheduled_for=NOW + timedelta(seconds=2),
                )
            )
            await db_session.flush()

    daily.status = ScoutRunStatus.COMPLETED
    manual = ScoutRun(
        user_id=user.id,
        competitor_id=competitor.id,
        run_type=RunType.MANUAL_SCOUT,
        scheduled_for=NOW + timedelta(seconds=2),
    )
    db_session.add(manual)
    await db_session.flush()
