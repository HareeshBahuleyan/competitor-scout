from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from competitor_scout.agents.client import OtariMetadata, OtariUsage
from competitor_scout.config import Settings
from competitor_scout.jobs import scheduler
from competitor_scout.jobs.scheduler import weekly_deduplication_key
from competitor_scout.jobs.weekly_brief import WeeklyBriefHandler, weekly_period
from competitor_scout.main import create_app
from competitor_scout.models.auth import User
from competitor_scout.models.briefs import WeeklyBrief
from competitor_scout.models.intelligence import (
    AgentTask,
    AgentTaskRole,
    AgentTaskStatus,
    ApprovalStatus,
    Competitor,
    CompetitorStatus,
    EvidenceItem,
    EvidenceObservation,
    Finding,
    FindingEvidence,
    MonitoredSource,
    RunType,
    ScoutRun,
    ScoutRunStatus,
    UsageEvent,
)
from competitor_scout.models.jobs import Job
from competitor_scout.schemas.briefs import (
    EMPTY_BRIEF_EXECUTIVE_SUMMARY,
    EMPTY_BRIEF_TITLE,
    WeeklyBriefResult,
)
from competitor_scout.services.briefs import digest_overview, next_weekly_generation

SCHEDULED = datetime(2026, 10, 25, 23, 0, tzinfo=UTC)  # Monday midnight in Berlin.


def test_weekly_period_uses_exact_local_midnight_boundaries_across_dst() -> None:
    period = weekly_period(SCHEDULED, "Europe/Berlin")

    assert period.period_start == date(2026, 10, 19)
    assert period.period_end == date(2026, 10, 25)
    assert period.start_utc == datetime(2026, 10, 18, 22, 0, tzinfo=UTC)
    assert period.end_exclusive_utc == datetime(2026, 10, 25, 23, 0, tzinfo=UTC)


def test_next_weekly_generation_uses_the_users_local_schedule() -> None:
    before_due = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    after_due = datetime(2026, 10, 26, 7, 1, tzinfo=UTC)

    assert next_weekly_generation(before_due, "Europe/Berlin") == datetime(
        2026, 10, 26, 7, 0, tzinfo=UTC
    )
    assert next_weekly_generation(after_due, "Europe/Berlin") == datetime(
        2026, 11, 2, 7, 0, tzinfo=UTC
    )


@pytest.mark.parametrize("qualifying_run_type", [RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT])
async def test_weekly_scheduler_requires_period_scout_activity_and_skips_disabled(
    brief_store,
    qualifying_run_type: RunType,
) -> None:
    sessions = brief_store
    async with sessions.begin() as session:
        stem = uuid.uuid4().hex
        eligible = User(
            email=f"weekly-schedule-{stem}@example.com",
            display_name="Weekly Schedule Owner",
            timezone="Europe/Berlin",
        )
        disabled = User(
            email=f"weekly-disabled-{stem}@example.com",
            display_name="Disabled Weekly Owner",
            timezone="Europe/Berlin",
            disabled_at=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
        )
        discovery_only = User(
            email=f"weekly-discovery-{stem}@example.com",
            display_name="Discovery-only Weekly Owner",
            timezone="Europe/Berlin",
        )
        session.add_all([eligible, disabled, discovery_only])
        await session.flush()

        eligible_competitor = Competitor(
            user_id=eligible.id,
            name="Eligible competitor",
            primary_domain=f"eligible-{stem}.example",
        )
        discovery_competitor = Competitor(
            user_id=discovery_only.id,
            name="Discovery-only competitor",
            primary_domain=f"discovery-{stem}.example",
        )
        session.add_all([eligible_competitor, discovery_competitor])
        await session.flush()
        session.add_all(
            [
                ScoutRun(
                    user_id=eligible.id,
                    competitor_id=eligible_competitor.id,
                    run_type=qualifying_run_type,
                    status=ScoutRunStatus.COMPLETED,
                    scheduled_for=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
                ),
                ScoutRun(
                    user_id=discovery_only.id,
                    competitor_id=discovery_competitor.id,
                    run_type=RunType.SOURCE_DISCOVERY,
                    status=ScoutRunStatus.COMPLETED,
                    scheduled_for=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
                ),
            ]
        )
        eligible_id = eligible.id
        disabled_id = disabled.id
        discovery_only_id = discovery_only.id

    before_due = datetime(2026, 10, 26, 6, 59, tzinfo=UTC)
    due = datetime(2026, 10, 26, 7, 0, tzinfo=UTC)
    async with sessions.begin() as session:
        early = await scheduler.schedule_due_weekly_briefs(session, now=before_due)
    async with sessions.begin() as session:
        first = await scheduler.schedule_due_weekly_briefs(session, now=due)
    async with sessions.begin() as session:
        repeated = await scheduler.schedule_due_weekly_briefs(
            session,
            now=due.replace(minute=30),
        )

    assert all(run.user_id != eligible_id for run in early)
    first_for_user = [run for run in first if run.user_id == eligible_id]
    repeated_for_user = [run for run in repeated if run.user_id == eligible_id]
    assert len(first_for_user) == len(repeated_for_user) == 1
    assert first_for_user[0].id == repeated_for_user[0].id
    assert first_for_user[0].scheduled_for == due

    period = weekly_period(first_for_user[0].scheduled_for, "Europe/Berlin")
    assert (period.period_start, period.period_end) == (
        date(2026, 10, 19),
        date(2026, 10, 25),
    )
    assert period.start_utc == datetime(2026, 10, 18, 22, 0, tzinfo=UTC)
    assert period.end_exclusive_utc == datetime(2026, 10, 25, 23, 0, tzinfo=UTC)

    async with sessions() as session:
        eligible_runs = list(
            (
                await session.scalars(
                    select(ScoutRun).where(
                        ScoutRun.user_id == eligible_id,
                        ScoutRun.run_type == RunType.WEEKLY_BRIEF,
                    )
                )
            ).all()
        )
        disabled_run_count = await session.scalar(
            select(func.count(ScoutRun.id)).where(
                ScoutRun.user_id == disabled_id,
                ScoutRun.run_type == RunType.WEEKLY_BRIEF,
            )
        )
        discovery_only_run_count = await session.scalar(
            select(func.count(ScoutRun.id)).where(
                ScoutRun.user_id == discovery_only_id,
                ScoutRun.run_type == RunType.WEEKLY_BRIEF,
            )
        )
        jobs = list(
            (
                await session.scalars(
                    select(Job).where(
                        Job.deduplication_key
                        == weekly_deduplication_key(str(eligible_id), date(2026, 10, 25))
                    )
                )
            ).all()
        )

    assert len(eligible_runs) == 1
    assert disabled_run_count == 0
    assert discovery_only_run_count == 0
    assert len(jobs) == 1
    assert jobs[0].job_type == "weekly_brief"
    assert jobs[0].payload == {"run_id": str(eligible_runs[0].id)}


def settings() -> Settings:
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
    )


@pytest_asyncio.fixture
async def brief_store(migrated_database_url: str):
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        await engine.dispose()


@dataclass(frozen=True)
class SeededBriefRun:
    user_id: uuid.UUID
    competitor_id: uuid.UUID
    run_id: uuid.UUID
    finding_ids: tuple[uuid.UUID, ...]


async def seed_brief_run(
    sessions,
    *,
    timezone: str = "Europe/Berlin",
    published_times: tuple[datetime, ...] = (),
    competitor_status: CompetitorStatus = CompetitorStatus.ACTIVE,
) -> SeededBriefRun:
    async with sessions.begin() as session:
        stem = uuid.uuid4().hex
        user = User(
            email=f"brief-{stem}@example.com", display_name="Brief Owner", timezone=timezone
        )
        competitor = Competitor(
            user=user,
            name="Acme",
            primary_domain=f"{stem}.example",
            status=competitor_status,
        )
        source_run = ScoutRun(
            user=user,
            competitor=competitor,
            run_type=RunType.DAILY_SCOUT,
            status=ScoutRunStatus.COMPLETED,
            scheduled_for=datetime(2026, 10, 20, 12, 0, tzinfo=UTC),
        )
        task = AgentTask(
            scout_run=source_run,
            role=AgentTaskRole.CHILD_RESEARCHER,
            task_kind="first_party_source_review",
            status=AgentTaskStatus.SUCCEEDED,
            model="competitor-scout-child",
            objective="Review accepted source",
        )
        weekly_run = ScoutRun(
            user=user,
            run_type=RunType.WEEKLY_BRIEF,
            status=ScoutRunStatus.QUEUED,
            scheduled_for=SCHEDULED,
        )
        session.add_all([task, weekly_run])
        await session.flush()
        coverage_evidence = EvidenceItem(
            user=user,
            competitor=competitor,
            scout_run=source_run,
            agent_task=task,
            source_url=f"https://{stem}.example/",
            source_domain=f"{stem}.example",
            source_title="Homepage",
            source_type="first_party",
            published_at=None,
            captured_at=datetime(2026, 10, 20, 12, 5, tzinfo=UTC),
            quoted_text="This is a sufficiently long homepage quotation used for coverage.",
            normalized_claim="homepage reviewed",
            content_fingerprint=f"{999:064x}",
        )
        session.add(coverage_evidence)
        await session.flush()
        session.add(
            EvidenceObservation(
                scout_run_id=source_run.id,
                evidence_item_id=coverage_evidence.id,
                agent_task_id=task.id,
            )
        )
        finding_ids: list[uuid.UUID] = []
        for index, published_at in enumerate(published_times):
            finding = Finding(
                user=user,
                competitor=competitor,
                originating_scout_run=source_run,
                category="pricing",
                title=f"Accepted change {index}",
                summary=f"Accepted summary {index}",
                significance_explanation="Material to competitive positioning.",
                significance_level="high",
                confidence=Decimal("0.9500"),
                decision_rationale="Direct evidence supports this accepted finding.",
                normalized_claim_fingerprint=f"{index + 1:064x}",
                duplicate_key=uuid.uuid4().hex.ljust(64, "0"),
                first_seen_at=published_at,
                last_seen_at=published_at,
                published_at=published_at,
            )
            quote = f"This is a sufficiently long direct quotation for accepted change {index}."
            evidence = EvidenceItem(
                user=user,
                competitor=competitor,
                scout_run=source_run,
                agent_task=task,
                source_url=f"https://{stem}.example/change-{index}",
                source_domain=f"{stem}.example",
                source_title=f"Source {index}",
                source_type="first_party",
                published_at=published_at,
                captured_at=published_at,
                quoted_text=quote,
                normalized_claim=f"accepted change {index}",
                content_fingerprint=f"{index + 101:064x}",
            )
            session.add(
                FindingEvidence(
                    finding=finding,
                    evidence_item=evidence,
                    citation_order=1,
                    is_primary=True,
                )
            )
            await session.flush()
            finding_ids.append(finding.id)
        return SeededBriefRun(user.id, competitor.id, weekly_run.id, tuple(finding_ids))


def grounded_result(finding_ids: tuple[uuid.UUID, ...]) -> WeeklyBriefResult:
    return WeeklyBriefResult.model_validate_json(
        json.dumps(
            {
                "title": "Weekly competitive brief",
                "executive_summary": "Accepted findings show notable pricing movement.",
                "sections": [
                    {
                        "heading": "Pricing changes",
                        "narrative": "The accepted evidence shows pricing movement.",
                        "references": [
                            {
                                "finding_id": str(item),
                                "statement": "This accepted finding supports the section.",
                            }
                            for item in finding_ids
                        ],
                    }
                ],
            }
        )
    )


class FakeOtari:
    def __init__(self, result: WeeklyBriefResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def structured_completion(self, **kwargs: object):
        self.calls.append(kwargs)
        return self.result, OtariMetadata(
            request_id="brief-request",
            usage=OtariUsage(
                input_tokens=120,
                output_tokens=30,
                tool_calls=0,
                cost_usd=Decimal("0.012345"),
                pricing_source="hosted_catalog",
            ),
        )


class NeverOtari:
    calls = 0

    async def structured_completion(self, **_kwargs: object):
        self.calls += 1
        raise AssertionError("empty weeks must not call Otari")


async def test_grounded_brief_uses_only_local_period_findings_and_is_idempotent(
    brief_store,
) -> None:
    seeded = await seed_brief_run(
        brief_store,
        published_times=(
            datetime(2026, 10, 18, 22, 0, tzinfo=UTC),  # Included start.
            datetime(2026, 10, 25, 22, 59, tzinfo=UTC),  # Included end local day.
            datetime(2026, 10, 25, 23, 0, tzinfo=UTC),  # Excluded end boundary.
        ),
    )
    client = FakeOtari(grounded_result(seeded.finding_ids[:2]))
    handler = WeeklyBriefHandler(
        brief_store, client=client, settings=settings(), now=lambda: SCHEDULED
    )

    assert await handler.handle(seeded.run_id) is ScoutRunStatus.COMPLETED
    assert await handler.handle(seeded.run_id) is ScoutRunStatus.COMPLETED
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["model"] == settings().otari_main_model
    assert call["session_label"] == f"scout-run:{seeded.run_id}"
    assert call["enable_web_search"] is False
    assert call["max_tool_iterations"] == 1
    input_payload = json.loads(call["messages"][1]["content"])
    assert {item["id"] for item in input_payload["findings"]} == {
        str(item) for item in seeded.finding_ids[:2]
    }

    async with brief_store() as session:
        brief = await session.scalar(
            select(WeeklyBrief).where(WeeklyBrief.user_id == seeded.user_id)
        )
        run = await session.get(ScoutRun, seeded.run_id)
        assert brief is not None
        assert (brief.period_start, brief.period_end) == (date(2026, 10, 19), date(2026, 10, 25))
        assert run is not None and run.status is ScoutRunStatus.COMPLETED
        assert run.input_tokens == 120 and run.settled_cost_usd == Decimal("0.012345")
        assert brief.coverage == {
            "competitors": [
                {
                    "competitor_id": str(seeded.competitor_id),
                    "competitor_name": "Acme",
                }
            ],
            "completed_scan_count": 1,
            "partial_scan_count": 0,
            "failed_scan_count": 0,
            "inspected_source_count": 1,
            "coverage_complete": True,
        }
        assert (
            await session.scalar(
                select(func.count(AgentTask.id)).where(AgentTask.scout_run_id == seeded.run_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(UsageEvent.id)).where(UsageEvent.scout_run_id == seeded.run_id)
            )
            == 1
        )


async def test_unknown_finding_reference_fails_without_publishing_and_keeps_usage(
    brief_store,
) -> None:
    seeded = await seed_brief_run(
        brief_store,
        published_times=(datetime(2026, 10, 20, 12, 0, tzinfo=UTC),),
    )
    client = FakeOtari(grounded_result((uuid.uuid4(),)))
    handler = WeeklyBriefHandler(
        brief_store, client=client, settings=settings(), now=lambda: SCHEDULED
    )

    assert await handler.handle(seeded.run_id) is ScoutRunStatus.FAILED
    async with brief_store() as session:
        run = await session.get(ScoutRun, seeded.run_id)
        task = await session.scalar(
            select(AgentTask).where(AgentTask.scout_run_id == seeded.run_id)
        )
        assert run is not None and run.failure_code == "brief_invalid_reference"
        assert task is not None and task.error_code == "brief_invalid_reference"
        assert task.validated_output is None
        assert (
            await session.scalar(
                select(func.count(WeeklyBrief.id)).where(WeeklyBrief.user_id == seeded.user_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count(UsageEvent.id)).where(UsageEvent.scout_run_id == seeded.run_id)
            )
            == 1
        )


async def test_weekly_cost_preflight_stops_before_otari(brief_store) -> None:
    seeded = await seed_brief_run(
        brief_store,
        published_times=(datetime(2026, 10, 20, 12, 0, tzinfo=UTC),),
    )
    client = FakeOtari(grounded_result(seeded.finding_ids))
    configured = settings().model_copy(update={"max_run_cost_usd": Decimal("0.10")})
    handler = WeeklyBriefHandler(
        brief_store,
        client=client,
        settings=configured,
        now=lambda: SCHEDULED,
        cost_estimator=lambda _role: Decimal("0.20"),
    )

    assert await handler.handle(seeded.run_id) is ScoutRunStatus.PARTIAL
    assert client.calls == []
    async with brief_store() as session:
        run = await session.get(ScoutRun, seeded.run_id)
        task = await session.scalar(
            select(AgentTask).where(AgentTask.scout_run_id == seeded.run_id)
        )
    assert run is not None and run.partial_reasons == ["cost_ceiling_reached"]
    assert task is not None and task.status is AgentTaskStatus.CANCELLED
    assert task.error_code == "cost_ceiling_reached"


async def test_reclaimed_synthesizing_brief_terminalizes_without_repeating_otari(
    brief_store,
) -> None:
    seeded = await seed_brief_run(
        brief_store,
        published_times=(datetime(2026, 10, 20, 12, 0, tzinfo=UTC),),
    )
    async with brief_store.begin() as session:
        run = await session.get(ScoutRun, seeded.run_id)
        assert run is not None
        run.status = ScoutRunStatus.SYNTHESIZING
        run.started_at = SCHEDULED.replace(hour=22)
        session.add(
            AgentTask(
                scout_run_id=run.id,
                role=AgentTaskRole.MAIN_SYNTHESIZER,
                task_kind="weekly_synthesis",
                status=AgentTaskStatus.RUNNING,
                model="competitor-scout-main",
                objective="Summarize accepted findings into a grounded weekly brief",
                source_scope=[str(item) for item in seeded.finding_ids],
                attempt_count=1,
                started_at=SCHEDULED.replace(hour=22),
            )
        )
    client = NeverOtari()
    handler = WeeklyBriefHandler(
        brief_store,
        client=client,
        settings=settings(),
        now=lambda: SCHEDULED,
    )

    first = await handler.handle(seeded.run_id)
    second = await handler.handle(seeded.run_id)

    assert first is ScoutRunStatus.FAILED
    assert second is ScoutRunStatus.FAILED
    assert client.calls == 0
    async with brief_store() as session:
        run = await session.get(ScoutRun, seeded.run_id)
        task = await session.scalar(
            select(AgentTask).where(AgentTask.scout_run_id == seeded.run_id)
        )
        brief_count = await session.scalar(
            select(func.count(WeeklyBrief.id)).where(WeeklyBrief.scout_run_id == seeded.run_id)
        )
    assert run is not None and run.failure_code == "interrupted_weekly_brief"
    assert run.failure_summary == "weekly brief generation was interrupted"
    assert task is not None and task.status is AgentTaskStatus.FAILED
    assert task.error_code == "interrupted_weekly_brief"
    assert brief_count == 0


async def test_paused_competitor_does_not_erase_published_period_findings(
    brief_store,
) -> None:
    seeded = await seed_brief_run(
        brief_store,
        competitor_status=CompetitorStatus.PAUSED,
        published_times=(datetime(2026, 10, 20, 12, 0, tzinfo=UTC),),
    )
    client = FakeOtari(grounded_result(seeded.finding_ids))
    handler = WeeklyBriefHandler(
        brief_store,
        client=client,
        settings=settings(),
        now=lambda: SCHEDULED,
    )

    assert await handler.handle(seeded.run_id) is ScoutRunStatus.COMPLETED
    assert len(client.calls) == 1
    payload = json.loads(client.calls[0]["messages"][1]["content"])
    assert [item["id"] for item in payload["findings"]] == [str(seeded.finding_ids[0])]


async def test_digest_overview_distinguishes_setup_scan_waiting_and_paused(
    brief_store,
) -> None:
    now = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    async with brief_store.begin() as session:
        stem = uuid.uuid4().hex
        user = User(
            email=f"overview-{stem}@example.com",
            display_name="Overview Owner",
            timezone="Europe/Berlin",
        )
        session.add(user)
        await session.flush()
        required = await digest_overview(
            session,
            user_id=user.id,
            timezone_name=user.timezone,
            now=now,
        )
        competitor = Competitor(
            user=user,
            name="Overview competitor",
            primary_domain=f"overview-{stem}.example",
            status=CompetitorStatus.DISCOVERING,
        )
        session.add(competitor)
        await session.flush()
        incomplete = await digest_overview(
            session,
            user_id=user.id,
            timezone_name=user.timezone,
            now=now,
        )
        competitor.status = CompetitorStatus.ACTIVE
        session.add(
            MonitoredSource(
                competitor=competitor,
                url=f"https://overview-{stem}.example/",
                normalized_url=f"https://overview-{stem}.example/",
                source_category="homepage",
                title="Homepage",
                discovery_reason="Primary first-party source",
                approval_status=ApprovalStatus.APPROVED,
            )
        )
        await session.flush()
        awaiting = await digest_overview(
            session,
            user_id=user.id,
            timezone_name=user.timezone,
            now=now,
        )
        competitor.starting_snapshot_requested_at = now
        run = ScoutRun(
            user=user,
            competitor=competitor,
            run_type=RunType.DAILY_SCOUT,
            status=ScoutRunStatus.QUEUED,
            scheduled_for=now,
        )
        session.add(run)
        await session.flush()
        running = await digest_overview(
            session,
            user_id=user.id,
            timezone_name=user.timezone,
            now=now,
        )
        run.status = ScoutRunStatus.FAILED
        await session.flush()
        failed_active = await digest_overview(
            session,
            user_id=user.id,
            timezone_name=user.timezone,
            now=now,
        )
        competitor.status = CompetitorStatus.PAUSED
        await session.flush()
        paused = await digest_overview(
            session,
            user_id=user.id,
            timezone_name=user.timezone,
            now=now,
        )

    assert required.state == "setup_required"
    assert required.next_digest_at is None
    assert incomplete.state == "setup_incomplete"
    assert incomplete.incomplete_competitor is not None
    assert incomplete.incomplete_competitor.competitor_id == competitor.id
    assert awaiting.state == "awaiting_first_digest"
    assert awaiting.approved_source_count == 1
    assert awaiting.next_digest_at == datetime(2026, 10, 26, 7, 0, tzinfo=UTC)
    assert running.state == "initial_scan_running"
    assert running.running_scan is not None and running.running_scan.run_id == run.id
    assert failed_active.monitoring_issue_count == 1
    assert paused.state == "setup_incomplete"
    assert paused.next_digest_at is None
    assert paused.monitoring_issue_count == 0


async def test_empty_week_is_deterministic_and_never_calls_otari(brief_store) -> None:
    seeded = await seed_brief_run(brief_store, timezone="UTC")
    client = NeverOtari()
    handler = WeeklyBriefHandler(
        brief_store, client=client, settings=settings(), now=lambda: SCHEDULED
    )

    assert await handler.handle(seeded.run_id) is ScoutRunStatus.COMPLETED
    assert client.calls == 0
    async with brief_store() as session:
        brief = await session.scalar(
            select(WeeklyBrief).where(WeeklyBrief.user_id == seeded.user_id)
        )
        assert brief is not None
        assert brief.title == EMPTY_BRIEF_TITLE
        assert brief.executive_summary == EMPTY_BRIEF_EXECUTIVE_SUMMARY
        assert brief.sections == []
        assert brief.coverage == {
            "competitors": [
                {
                    "competitor_id": str(seeded.competitor_id),
                    "competitor_name": "Acme",
                }
            ],
            "completed_scan_count": 1,
            "partial_scan_count": 0,
            "failed_scan_count": 0,
            "inspected_source_count": 1,
            "coverage_complete": True,
        }
        assert (
            await session.scalar(
                select(func.count(AgentTask.id)).where(AgentTask.scout_run_id == seeded.run_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count(UsageEvent.id)).where(UsageEvent.scout_run_id == seeded.run_id)
            )
            == 0
        )


async def test_quiet_week_receipt_counts_completed_partial_failed_and_inspected_sources(
    brief_store,
) -> None:
    seeded = await seed_brief_run(brief_store, timezone="UTC")
    async with brief_store.begin() as session:
        user = await session.get(User, seeded.user_id)
        assert user is not None
        statuses = (
            ("Partial competitor", CompetitorStatus.ACTIVE, ScoutRunStatus.PARTIAL),
            ("Failed competitor", CompetitorStatus.ACTIVE, ScoutRunStatus.FAILED),
            ("Paused competitor", CompetitorStatus.PAUSED, None),
        )
        for index, (name, competitor_status, run_status) in enumerate(statuses):
            competitor = Competitor(
                user=user,
                name=name,
                primary_domain=f"coverage-{index}-{uuid.uuid4().hex}.example",
                status=competitor_status,
            )
            session.add(competitor)
            await session.flush()
            if run_status is not None:
                session.add(
                    ScoutRun(
                        user=user,
                        competitor=competitor,
                        run_type=RunType.DAILY_SCOUT,
                        status=run_status,
                        scheduled_for=datetime(2026, 10, 20, 13, 0, tzinfo=UTC),
                    )
                )

    handler = WeeklyBriefHandler(
        brief_store,
        client=NeverOtari(),
        settings=settings(),
        now=lambda: SCHEDULED,
    )
    assert await handler.handle(seeded.run_id) is ScoutRunStatus.COMPLETED

    async with brief_store() as session:
        brief = await session.scalar(
            select(WeeklyBrief).where(WeeklyBrief.user_id == seeded.user_id)
        )
        assert brief is not None
        assert brief.coverage is not None
        receipt = brief.coverage
    assert {item["competitor_name"] for item in receipt["competitors"]} == {
        "Acme",
        "Partial competitor",
        "Failed competitor",
    }
    assert receipt["completed_scan_count"] == 1
    assert receipt["partial_scan_count"] == 1
    assert receipt["failed_scan_count"] == 1
    assert receipt["inspected_source_count"] == 1
    assert receipt["coverage_complete"] is False


async def test_brief_api_is_cursor_paginated_and_user_scoped(brief_store) -> None:
    owner = await seed_brief_run(brief_store, timezone="UTC")
    other = await seed_brief_run(brief_store, timezone="UTC")
    for seeded in (owner, other):
        await WeeklyBriefHandler(
            brief_store,
            client=NeverOtari(),
            settings=settings(),
            now=lambda: SCHEDULED,
        ).handle(seeded.run_id)
    async with brief_store() as session:
        owner_user = await session.get(User, owner.user_id)
        owner_brief = await session.scalar(
            select(WeeklyBrief).where(WeeklyBrief.user_id == owner.user_id)
        )
        other_brief = await session.scalar(
            select(WeeklyBrief).where(WeeklyBrief.user_id == other.user_id)
        )
        assert owner_user is not None and owner_brief is not None and other_brief is not None
        owner_brief.coverage = None
        session.add(
            Competitor(
                user=owner_user,
                name="New setup in progress",
                primary_domain=f"new-setup-{uuid.uuid4().hex}.example",
                status=CompetitorStatus.DISCOVERING,
            )
        )
        await session.commit()

    async def current_owner() -> User:
        return owner_user

    app = create_app(
        settings=settings(),
        session_factory=brief_store,
        readiness_probe=lambda: None,
        testing=True,
        current_user_override=current_owner,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://testserver"
    ) as client:
        response = await client.get("/api/v1/briefs", params={"limit": 1})
        assert response.status_code == 200
        document = response.json()
        assert len(document["items"]) == 1
        assert document["items"][0]["id"] != str(other_brief.id)
        assert document["items"][0]["coverage"] is None
        own_id = document["items"][0]["id"]
        assert (await client.get(f"/api/v1/briefs/{own_id}")).status_code == 200
        overview = await client.get("/api/v1/briefs/overview")
        assert overview.status_code == 200
        assert overview.json()["state"] == "archive_available"
        assert overview.json()["latest_brief"]["id"] == own_id
        assert overview.json()["active_competitor_count"] == 1
        hidden = await client.get(f"/api/v1/briefs/{other_brief.id}")
        assert hidden.status_code == 404
