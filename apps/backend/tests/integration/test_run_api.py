from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from competitor_scout.api.deps import authenticated_session, require_csrf
from competitor_scout.config import Settings
from competitor_scout.main import create_app
from competitor_scout.models.auth import Session, User
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
from competitor_scout.models.jobs import Job
from competitor_scout.security.csrf import csrf_token
from competitor_scout.services.auth import AuthenticatedSession

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def run_settings() -> Settings:
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
async def run_store(migrated_database_url: str):
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        async with sessions.begin() as session:
            user_ids = list(
                (
                    await session.scalars(
                        select(User.id).where(User.email.like("run-api-%@example.com"))
                    )
                ).all()
            )
            if user_ids:
                run_ids = list(
                    (
                        await session.scalars(
                            select(ScoutRun.id).where(ScoutRun.user_id.in_(user_ids))
                        )
                    ).all()
                )
                if run_ids:
                    await session.execute(
                        delete(Job).where(
                            Job.payload["run_id"]
                            .as_string()
                            .in_([str(run_id) for run_id in run_ids])
                        )
                    )
                await session.execute(delete(User).where(User.id.in_(user_ids)))
        await engine.dispose()


async def seed_user(sessions, stem: str) -> User:
    async with sessions.begin() as session:
        user = User(
            email=f"run-api-{stem}-{uuid.uuid4().hex}@example.com",
            display_name=stem,
        )
        session.add(user)
        await session.flush()
        return user


async def seed_competitor(
    sessions,
    user: User,
    *,
    status: CompetitorStatus = CompetitorStatus.ACTIVE,
    approved: bool = True,
) -> Competitor:
    async with sessions.begin() as session:
        competitor = Competitor(
            user_id=user.id,
            name=f"Competitor {uuid.uuid4().hex[:6]}",
            primary_domain=f"{uuid.uuid4().hex}.example",
            status=status,
        )
        session.add(competitor)
        if approved:
            session.add(
                MonitoredSource(
                    competitor=competitor,
                    url=f"https://{competitor.primary_domain}/pricing",
                    normalized_url=f"https://{competitor.primary_domain}/pricing",
                    source_category=SourceCategory.PRICING,
                    title="Pricing",
                    discovery_reason="Approved synthetic source",
                    approval_status=ApprovalStatus.APPROVED,
                )
            )
        await session.flush()
        return competitor


async def make_client(
    sessions,
    user: User,
    *,
    enforce_csrf: bool = False,
) -> tuple[AsyncClient, str | None]:
    configured = run_settings()

    async def current_user_override() -> User:
        return user

    async def no_database_probe() -> None:
        return None

    app = create_app(
        settings=configured,
        session_factory=sessions,
        readiness_probe=no_database_probe,
        testing=True,
        current_user_override=current_user_override,
    )
    token: str | None = None
    if enforce_csrf:
        cookie_secret = "synthetic-cookie-secret"
        auth_session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            secret_hash="not-a-real-secret-hash",
            expires_at=NOW + timedelta(days=1),
        )

        async def auth_override() -> AuthenticatedSession:
            return AuthenticatedSession(auth_session, user, cookie_secret)

        app.dependency_overrides[authenticated_session] = auth_override
        token = csrf_token(
            auth_session.id,
            cookie_secret,
            configured.csrf_secret.get_secret_value(),
        )
    else:

        async def skip_csrf() -> None:
            return None

        app.dependency_overrides[require_csrf] = skip_csrf
    return (
        AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver"),
        token,
    )


async def test_manual_run_requires_session_csrf_and_is_durably_enqueued(
    run_store,
) -> None:
    user = await seed_user(run_store, "csrf")
    competitor = await seed_competitor(run_store, user)
    client, token = await make_client(run_store, user, enforce_csrf=True)
    assert token is not None

    async with client:
        rejected = await client.post(f"/api/v1/competitors/{competitor.id}/runs")
        accepted = await client.post(
            f"/api/v1/competitors/{competitor.id}/runs",
            headers={"X-CSRF-Token": token},
        )

    assert rejected.status_code == 403
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "queued"
    assert accepted.json()["run_type"] == "manual_scout"
    async with run_store() as session:
        run = await session.get(ScoutRun, uuid.UUID(accepted.json()["id"]))
        job = await session.scalar(
            select(Job).where(Job.payload["run_id"].as_string() == accepted.json()["id"])
        )
    assert run is not None and job is not None
    assert job.job_type == "manual_scout"


async def test_manual_run_requires_owned_active_competitor_and_approved_source(
    run_store,
) -> None:
    owner = await seed_user(run_store, "requirements-owner")
    outsider = await seed_user(run_store, "requirements-outsider")
    paused = await seed_competitor(
        run_store,
        owner,
        status=CompetitorStatus.PAUSED,
    )
    no_source = await seed_competitor(run_store, owner, approved=False)
    outsider_client, _ = await make_client(run_store, outsider)
    owner_client, _ = await make_client(run_store, owner)

    async with outsider_client, owner_client:
        hidden = await outsider_client.post(f"/api/v1/competitors/{paused.id}/runs")
        inactive = await owner_client.post(f"/api/v1/competitors/{paused.id}/runs")
        unapproved = await owner_client.post(f"/api/v1/competitors/{no_source.id}/runs")

    assert hidden.status_code == 404
    assert inactive.status_code == 422
    assert unapproved.status_code == 422


async def test_concurrent_manual_requests_create_one_run_and_one_job(run_store) -> None:
    user = await seed_user(run_store, "concurrency")
    competitor = await seed_competitor(run_store, user)
    client, _ = await make_client(run_store, user)

    async with client:
        responses = await asyncio.gather(
            *(client.post(f"/api/v1/competitors/{competitor.id}/runs") for _ in range(8))
        )

    assert {response.status_code for response in responses} == {202}
    run_ids = {response.json()["id"] for response in responses}
    assert len(run_ids) == 1
    async with run_store() as session:
        runs = await session.scalar(
            select(func.count(ScoutRun.id)).where(
                ScoutRun.competitor_id == competitor.id,
                ScoutRun.run_type == RunType.MANUAL_SCOUT,
            )
        )
        jobs = await session.scalar(
            select(func.count(Job.id)).where(
                Job.payload["run_id"].as_string() == next(iter(run_ids))
            )
        )
    assert runs == 1 and jobs == 1


async def test_manual_request_reuses_active_daily_run_without_duplicate_job(
    run_store,
) -> None:
    user = await seed_user(run_store, "active-daily")
    competitor = await seed_competitor(run_store, user)
    async with run_store.begin() as session:
        daily = ScoutRun(
            user_id=user.id,
            competitor_id=competitor.id,
            run_type=RunType.DAILY_SCOUT,
            status=ScoutRunStatus.QUEUED,
            scheduled_for=NOW,
        )
        session.add(daily)
        await session.flush()
        session.add(
            Job(
                job_type="daily_scout",
                deduplication_key=f"daily_scout:{competitor.id}:2026-08-21",
                payload={"run_id": str(daily.id)},
                available_at=NOW,
            )
        )
    client, _ = await make_client(run_store, user)

    async with client:
        response = await client.post(f"/api/v1/competitors/{competitor.id}/runs")

    assert response.status_code == 202
    assert response.json()["id"] == str(daily.id)
    assert response.json()["run_type"] == "daily_scout"
    async with run_store() as session:
        job_count = await session.scalar(
            select(func.count(Job.id)).where(Job.payload["run_id"].as_string() == str(daily.id))
        )
    assert job_count == 1


async def test_recent_terminal_manual_run_is_idempotent_for_five_minutes(
    run_store,
) -> None:
    from competitor_scout.services.runs import enqueue_manual_run

    user = await seed_user(run_store, "recent")
    competitor = await seed_competitor(run_store, user)
    async with run_store.begin() as session:
        first = await enqueue_manual_run(
            session,
            user_id=user.id,
            competitor_id=competitor.id,
            now=NOW,
        )
    async with run_store.begin() as session:
        stored = await session.get(ScoutRun, first.id)
        assert stored is not None
        stored.status = ScoutRunStatus.COMPLETED
        stored.completed_at = NOW + timedelta(minutes=1)
    async with run_store.begin() as session:
        repeated = await enqueue_manual_run(
            session,
            user_id=user.id,
            competitor_id=competitor.id,
            now=NOW + timedelta(minutes=4, seconds=59),
        )
    async with run_store.begin() as session:
        newer = await enqueue_manual_run(
            session,
            user_id=user.id,
            competitor_id=competitor.id,
            now=NOW + timedelta(minutes=5, seconds=1),
        )

    assert repeated.id == first.id
    assert newer.id != first.id


async def seed_run_api_detail(sessions) -> tuple[User, User, ScoutRun]:
    owner = await seed_user(sessions, "detail-owner")
    outsider = await seed_user(sessions, "detail-outsider")
    competitor = await seed_competitor(sessions, owner)
    async with sessions.begin() as session:
        run = ScoutRun(
            user_id=owner.id,
            competitor_id=competitor.id,
            run_type=RunType.MANUAL_SCOUT,
            status=ScoutRunStatus.PARTIAL,
            scheduled_for=NOW,
            started_at=NOW + timedelta(seconds=1),
            completed_at=NOW + timedelta(seconds=30),
            failure_code=None,
            failure_summary="Traceback: internal implementation detail",
            partial_reasons=["child_task_failed"],
            input_tokens=30,
            output_tokens=15,
            tool_calls=None,
            settled_cost_usd=None,
        )
        child = AgentTask(
            scout_run=run,
            role=AgentTaskRole.CHILD_RESEARCHER,
            task_kind="first_party_source_review",
            status=AgentTaskStatus.SUCCEEDED,
            model="competitor-scout-child",
            objective="Raw prompt with authorization and otari_ai_token=top-secret",
            source_scope=["private prompt scope"],
            attempt_count=2,
            otari_request_id="provider-request-secret",
            input_tokens=20,
            output_tokens=10,
            tool_calls=None,
            settled_cost_usd=None,
            pricing_source="internal-pricing-source",
            validated_output={
                "sources_inspected": ["https://safe.example/pricing"],
                "evidence": [
                    {
                        "source_url": "https://safe.example/pricing",
                        "source_title": "Pricing",
                        "source_type": "first_party",
                        "quoted_text": "A sufficiently long synthetic direct quotation.",
                        "normalized_claim": "synthetic pricing claim",
                        "confidence": 0.9,
                        "prompt": "hidden nested prompt",
                    }
                ],
                "rejected_reasons": [
                    "unsafe_url",
                    "Traceback authorization secret should not escape",
                ],
                "prompt": "hidden raw prompt",
                "authorization": "Bearer hidden",
            },
            error_summary="Traceback: should never be returned",
        )
        planner = AgentTask(
            scout_run=run,
            role=AgentTaskRole.MAIN_PLANNER,
            task_kind="daily_planning",
            status=AgentTaskStatus.SUCCEEDED,
            model="competitor-scout-main",
            objective="Private planning prompt",
            source_scope=["private"],
            attempt_count=1,
            input_tokens=10,
            output_tokens=5,
            tool_calls=0,
            settled_cost_usd=Decimal("0.20"),
            validated_output={"tasks": [], "secret": "hidden"},
        )
        session.add_all([child, planner])
        await session.flush()
        session.add_all(
            [
                UsageEvent(
                    user_id=owner.id,
                    scout_run_id=run.id,
                    agent_task_id=child.id,
                    provider_request_id="provider-child",
                    model="competitor-scout-child",
                    input_tokens=20,
                    output_tokens=10,
                    tool_calls=None,
                    settled_cost_usd=None,
                    pricing_source=None,
                    occurred_at=NOW,
                ),
                UsageEvent(
                    user_id=owner.id,
                    scout_run_id=run.id,
                    agent_task_id=planner.id,
                    provider_request_id="provider-main",
                    model="competitor-scout-main",
                    input_tokens=10,
                    output_tokens=5,
                    tool_calls=0,
                    settled_cost_usd=Decimal("0.20"),
                    pricing_source="catalog-internal",
                    occurred_at=NOW,
                ),
            ]
        )
        await session.flush()
        return owner, outsider, run


async def test_run_read_apis_are_filtered_cursor_paginated_and_safe(run_store) -> None:
    owner, _outsider, run = await seed_run_api_detail(run_store)
    competitor = run.competitor_id
    assert competitor is not None
    async with run_store.begin() as session:
        session.add(
            ScoutRun(
                user_id=owner.id,
                competitor_id=competitor,
                run_type=RunType.DAILY_SCOUT,
                status=ScoutRunStatus.COMPLETED,
                scheduled_for=NOW - timedelta(days=1),
            )
        )
    client, _ = await make_client(run_store, owner)

    async with client:
        filtered = await client.get(
            "/api/v1/runs",
            params={
                "competitor_id": str(competitor),
                "status": "partial",
                "run_type": "manual_scout",
                "limit": 1,
            },
        )
        first_page = await client.get("/api/v1/runs", params={"limit": 1})
        second_page = await client.get(
            "/api/v1/runs",
            params={"limit": 1, "cursor": first_page.json()["next_cursor"]},
        )
        detail = await client.get(f"/api/v1/runs/{run.id}")
        tasks = await client.get(f"/api/v1/runs/{run.id}/tasks", params={"limit": 1})
        tasks_next = await client.get(
            f"/api/v1/runs/{run.id}/tasks",
            params={"limit": 1, "cursor": tasks.json()["next_cursor"]},
        )
        usage = await client.get(f"/api/v1/runs/{run.id}/usage")
        invalid_cursor = await client.get("/api/v1/runs", params={"cursor": "bad"})

    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [str(run.id)]
    assert filtered.json()["next_cursor"] is None
    assert first_page.status_code == 200
    assert first_page.json()["next_cursor"] is not None
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1
    assert detail.status_code == 200
    assert set(detail.json()) == {
        "id",
        "competitor_id",
        "run_type",
        "status",
        "scheduled_for",
        "started_at",
        "completed_at",
        "failure_code",
        "failure_summary",
        "partial_reasons",
        "partial_summaries",
        "input_tokens",
        "output_tokens",
        "tool_calls",
        "settled_cost_usd",
        "created_at",
    }
    assert detail.json()["status"] == "partial"
    assert detail.json()["partial_reasons"] == ["child_task_failed"]
    assert detail.json()["partial_summaries"] == ["Some research tasks could not complete."]
    assert detail.json()["failure_summary"] is None
    assert tasks.status_code == 200 and tasks.json()["next_cursor"] is not None
    assert tasks_next.status_code == 200
    task_items = tasks.json()["items"] + tasks_next.json()["items"]
    assert all(
        set(item)
        == {
            "id",
            "scout_run_id",
            "parent_task_id",
            "role",
            "task_kind",
            "status",
            "model",
            "objective",
            "source_scope",
            "attempt_count",
            "started_at",
            "completed_at",
            "input_tokens",
            "output_tokens",
            "tool_calls",
            "settled_cost_usd",
            "validated_output",
            "error_code",
            "error_summary",
            "created_at",
        }
        for item in task_items
    )
    assert {item["attempt_count"] for item in task_items} == {1, 2}
    serialized_tasks = str(task_items).casefold()
    for forbidden in (
        "prompt",
        "authorization",
        "otari_ai_token",
        "top-secret",
        "provider-request",
        "traceback",
        "pricing_source",
        "user_id",
    ):
        assert forbidden not in serialized_tasks
    assert usage.status_code == 200
    assert usage.json()["input_tokens"] == 30
    assert usage.json()["output_tokens"] == 15
    assert usage.json()["tool_calls"] is None
    assert usage.json()["settled_cost_usd"] is None
    by_model = {item["model"]: item for item in usage.json()["models"]}
    assert by_model["competitor-scout-child"]["tool_calls"] is None
    assert by_model["competitor-scout-child"]["settled_cost_usd"] is None
    assert by_model["competitor-scout-main"]["settled_cost_usd"] == "0.200000"
    assert invalid_cursor.status_code == 422


async def test_run_detail_tasks_and_usage_hide_cross_user_records(run_store) -> None:
    _owner, outsider, run = await seed_run_api_detail(run_store)
    client, _ = await make_client(run_store, outsider)

    async with client:
        responses = [
            await client.get(f"/api/v1/runs/{run.id}"),
            await client.get(f"/api/v1/runs/{run.id}/tasks"),
            await client.get(f"/api/v1/runs/{run.id}/usage"),
        ]

    assert [response.status_code for response in responses] == [404, 404, 404]
    assert all(response.json()["detail"] == "run not found" for response in responses)
