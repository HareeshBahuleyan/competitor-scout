from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from competitor_scout.agents.contracts import SourceType
from competitor_scout.api.deps import current_user, require_csrf
from competitor_scout.config import Settings
from competitor_scout.db import session_dependency
from competitor_scout.main import create_app
from competitor_scout.models.auth import User
from competitor_scout.models.intelligence import (
    AgentTask,
    AgentTaskRole,
    AgentTaskStatus,
    ApprovalStatus,
    Competitor,
    CompetitorStatus,
    EvidenceItem,
    EvidenceObservation,
    MonitoredSource,
    RunType,
    ScoutRun,
    ScoutRunStatus,
    SourceCategory,
)
from competitor_scout.models.jobs import Job
from competitor_scout.models.snapshots import CompetitorStartingSnapshot
from competitor_scout.security.urls import UnsafeSourceUrl
from competitor_scout.services.competitors import (
    CompetitorLimitReached,
    create_competitor,
)


def competitor_settings() -> Settings:
    return Settings(
        environment="test",
        database_url="postgresql+asyncpg://test:test@localhost/test",
        public_base_url="https://testserver",
        session_secret="s" * 32,
        csrf_secret="c" * 32,
        google_client_id="google-id",
        google_client_secret="google-secret",
        otari_base_url="https://otari.invalid",
        otari_ai_token="test-token",
        max_active_competitors=10,
    )


class FakeSourceValidator:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.results: dict[str, str | Exception] = {}

    async def __call__(self, value: str) -> str:
        self.calls.append(value)
        result = self.results.get(value, value)
        if isinstance(result, Exception):
            raise result
        return result


async def make_client(db_session, user: User, validator: FakeSourceValidator) -> AsyncClient:
    async def no_database_probe() -> None:
        return None

    async def override_session() -> AsyncIterator:
        yield db_session

    async def override_user() -> User:
        return user

    async def skip_csrf() -> None:
        return None

    app = create_app(
        settings=competitor_settings(),
        readiness_probe=no_database_probe,
        testing=True,
        current_user_override=override_user,
        source_url_validator=validator,
    )
    app.dependency_overrides[session_dependency] = override_session
    app.dependency_overrides[current_user] = override_user
    app.dependency_overrides[require_csrf] = skip_csrf
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")


async def add_user(db_session, stem: str) -> User:
    user = User(email=f"{stem}-{uuid.uuid4().hex}@example.com", display_name=stem)
    db_session.add(user)
    await db_session.flush()
    return user


async def test_competitor_crud_and_cursor_list_envelope(db_session) -> None:
    user = await add_user(db_session, "owner")
    validator = FakeSourceValidator()

    async with await make_client(db_session, user, validator) as client:
        first = await client.post(
            "/api/v1/competitors",
            json={"name": "Acme", "primary_domain": "HTTPS://ACME.COM/pricing"},
        )
        second = await client.post(
            "/api/v1/competitors",
            json={"name": "Beta", "primary_domain": "beta.example"},
        )

        assert first.status_code == 201
        assert first.json()["primary_domain"] == "acme.com"
        assert first.json()["status"] == "discovering"
        assert second.status_code == 201

        page_one = await client.get("/api/v1/competitors", params={"limit": 1})
        assert page_one.status_code == 200
        assert len(page_one.json()["items"]) == 1
        assert page_one.json()["next_cursor"]

        page_two = await client.get(
            "/api/v1/competitors",
            params={"limit": 1, "cursor": page_one.json()["next_cursor"]},
        )
        assert page_two.status_code == 200
        assert len(page_two.json()["items"]) == 1
        assert page_two.json()["items"][0]["id"] != page_one.json()["items"][0]["id"]
        assert page_two.json()["next_cursor"] is None

        competitor_id = first.json()["id"]
        fetched = await client.get(f"/api/v1/competitors/{competitor_id}")
        updated = await client.patch(
            f"/api/v1/competitors/{competitor_id}",
            json={"name": "Acme Corp", "description": "Market leader"},
        )
        deleted = await client.delete(f"/api/v1/competitors/{competitor_id}")
        archived = await client.get(f"/api/v1/competitors/{competitor_id}")

    assert fetched.status_code == 200
    assert updated.status_code == 200
    assert updated.json()["name"] == "Acme Corp"
    assert updated.json()["description"] == "Market leader"
    assert deleted.status_code == 204
    assert archived.status_code == 200
    assert archived.json()["status"] == "deleted"


async def test_competitor_create_uses_account_default_daily_time_when_omitted(db_session) -> None:
    user = await add_user(db_session, "default-time-owner")
    user.default_daily_run_time_local = time(6, 45)

    async with await make_client(db_session, user, FakeSourceValidator()) as client:
        response = await client.post(
            "/api/v1/competitors",
            json={"name": "Acme", "primary_domain": "default-time.example"},
        )

    assert response.status_code == 201
    assert response.json()["daily_run_time_local"] == "06:45:00"


@pytest.mark.parametrize("field", ["name", "description", "daily_run_time_local"])
async def test_competitor_update_rejects_null_fields(db_session, field: str) -> None:
    user = await add_user(db_session, f"null-update-{field}")
    competitor = Competitor(
        user_id=user.id,
        name="Acme",
        primary_domain=f"{field.replace('_', '-')}.example",
    )
    db_session.add(competitor)
    await db_session.flush()

    async with await make_client(db_session, user, FakeSourceValidator()) as client:
        response = await client.patch(
            f"/api/v1/competitors/{competitor.id}",
            json={field: None},
        )

    assert response.status_code == 422
    await db_session.refresh(competitor)
    assert competitor.name == "Acme"
    assert competitor.description == ""
    assert competitor.daily_run_time_local == time(hour=8)


@pytest.mark.parametrize(
    "initial_status",
    [CompetitorStatus.DISCOVERING, CompetitorStatus.PAUSED],
)
async def test_competitor_cannot_activate_without_an_approved_source(
    db_session,
    initial_status: CompetitorStatus,
) -> None:
    user = await add_user(db_session, f"activate-without-source-{initial_status}")
    competitor = Competitor(
        user_id=user.id,
        name="Unready",
        primary_domain=f"{initial_status}.unready.example",
        status=initial_status,
    )
    db_session.add(competitor)
    await db_session.flush()

    async with await make_client(db_session, user, FakeSourceValidator()) as client:
        response = await client.patch(
            f"/api/v1/competitors/{competitor.id}",
            json={"status": "active"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "approved source required to activate competitor"
    await db_session.refresh(competitor)
    assert competitor.status is initial_status


async def test_competitor_with_approved_source_can_resume_and_pause(db_session) -> None:
    user = await add_user(db_session, "resume-owner")
    competitor = Competitor(
        user_id=user.id,
        name="Ready",
        primary_domain="ready.example",
        status=CompetitorStatus.PAUSED,
    )
    source = MonitoredSource(
        competitor=competitor,
        url="https://ready.example/pricing",
        normalized_url="https://ready.example/pricing",
        source_category=SourceCategory.PRICING,
        title="Pricing",
        discovery_reason="Approved first-party source",
        approval_status=ApprovalStatus.APPROVED,
    )
    db_session.add(source)
    await db_session.flush()

    async with await make_client(db_session, user, FakeSourceValidator()) as client:
        resumed = await client.patch(
            f"/api/v1/competitors/{competitor.id}",
            json={"status": "active"},
        )
        paused = await client.patch(
            f"/api/v1/competitors/{competitor.id}",
            json={"status": "paused"},
        )

    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"


async def test_duplicate_is_generic_and_soft_deleted_domain_can_be_readded(db_session) -> None:
    user = await add_user(db_session, "duplicate-owner")
    validator = FakeSourceValidator()

    async with await make_client(db_session, user, validator) as client:
        created = await client.post(
            "/api/v1/competitors",
            json={"name": "First", "primary_domain": "Example.COM"},
        )
        duplicate = await client.post(
            "/api/v1/competitors",
            json={"name": "Duplicate", "primary_domain": "https://example.com/other"},
        )
        await client.delete(f"/api/v1/competitors/{created.json()['id']}")
        replacement = await client.post(
            "/api/v1/competitors",
            json={"name": "Replacement", "primary_domain": "example.com"},
        )

    assert created.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "competitor already exists"
    assert replacement.status_code == 201
    assert replacement.json()["id"] != created.json()["id"]


@pytest.mark.parametrize(
    "primary_domain",
    ["localhost", "127.0.0.1", "https://user@example.com", "https://example.com:8443"],
)
async def test_create_rejects_invalid_primary_domains(db_session, primary_domain: str) -> None:
    user = await add_user(db_session, "invalid-domain-owner")

    async with await make_client(db_session, user, FakeSourceValidator()) as client:
        response = await client.post(
            "/api/v1/competitors",
            json={"name": "Invalid", "primary_domain": primary_domain},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "primary domain is invalid"


async def test_partial_unique_index_enforces_only_non_deleted_domains(db_session) -> None:
    user = await add_user(db_session, "index-owner")
    original = Competitor(user_id=user.id, name="Original", primary_domain="indexed.example")
    db_session.add(original)
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(
                Competitor(user_id=user.id, name="Duplicate", primary_domain="indexed.example")
            )
            await db_session.flush()

    original.status = CompetitorStatus.DELETED
    db_session.add(
        Competitor(user_id=user.id, name="Replacement", primary_domain="indexed.example")
    )
    await db_session.flush()


async def test_capacity_limit_is_422(db_session) -> None:
    user = await add_user(db_session, "capacity-owner")
    validator = FakeSourceValidator()

    async with await make_client(db_session, user, validator) as client:
        for number in range(10):
            response = await client.post(
                "/api/v1/competitors",
                json={"name": f"Competitor {number}", "primary_domain": f"c{number}.example"},
            )
            assert response.status_code == 201

        over_limit = await client.post(
            "/api/v1/competitors",
            json={"name": "Eleventh", "primary_domain": "eleventh.example"},
        )

    assert over_limit.status_code == 422
    assert over_limit.json()["detail"] == "competitor limit reached"


async def test_cross_user_record_routes_all_return_404(db_session) -> None:
    owner = await add_user(db_session, "record-owner")
    outsider = await add_user(db_session, "record-outsider")
    competitor = Competitor(
        user_id=owner.id,
        name="Private competitor",
        primary_domain="private.example",
    )
    source = MonitoredSource(
        competitor=competitor,
        url="https://private.example/pricing",
        normalized_url="https://private.example/pricing",
        source_category=SourceCategory.PRICING,
        title="Pricing",
        discovery_reason="Candidate pricing page",
    )
    db_session.add(source)
    outsider_competitor = Competitor(
        user_id=outsider.id,
        name="Outsider competitor",
        primary_domain="outsider.example",
    )
    db_session.add(outsider_competitor)
    await db_session.flush()

    async with await make_client(db_session, outsider, FakeSourceValidator()) as client:
        responses = [
            await client.get(f"/api/v1/competitors/{competitor.id}"),
            await client.patch(f"/api/v1/competitors/{competitor.id}", json={"name": "Stolen"}),
            await client.delete(f"/api/v1/competitors/{competitor.id}"),
            await client.get(f"/api/v1/competitors/{competitor.id}/sources"),
            await client.patch(
                f"/api/v1/competitors/{competitor.id}/sources/{source.id}",
                json={"approval_status": "approved"},
            ),
            await client.patch(
                f"/api/v1/competitors/{outsider_competitor.id}/sources/{source.id}",
                json={"approval_status": "approved"},
            ),
        ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404, 404, 404]
    assert all(response.json()["detail"] == "competitor not found" for response in responses)


async def test_source_list_is_cursor_paginated_and_approval_does_not_activate(db_session) -> None:
    user = await add_user(db_session, "source-owner")
    competitor = Competitor(
        user_id=user.id,
        name="Acme",
        primary_domain="acme.com",
    )
    first = MonitoredSource(
        competitor=competitor,
        url="https://www.acme.com/pricing?utm=discovery",
        normalized_url="https://www.acme.com/pricing",
        source_category=SourceCategory.PRICING,
        title="Pricing",
        discovery_reason="Pricing changes are high signal",
    )
    second = MonitoredSource(
        competitor=competitor,
        url="https://acme.com/changelog",
        normalized_url="https://acme.com/changelog",
        source_category=SourceCategory.CHANGELOG,
        title="Changelog",
        discovery_reason="Product updates",
    )
    db_session.add_all([first, second])
    await db_session.flush()
    validator = FakeSourceValidator()
    original_url = first.url
    validator.results[original_url] = "https://www.acme.com/pricing"

    async with await make_client(db_session, user, validator) as client:
        page = await client.get(f"/api/v1/competitors/{competitor.id}/sources", params={"limit": 1})
        approved = await client.patch(
            f"/api/v1/competitors/{competitor.id}/sources/{first.id}",
            json={"approval_status": "approved"},
        )

    assert page.status_code == 200
    assert len(page.json()["items"]) == 1
    assert page.json()["next_cursor"]
    assert approved.status_code == 200
    assert approved.json()["approval_status"] == "approved"
    assert validator.calls == [original_url]
    await db_session.refresh(competitor)
    assert competitor.status is CompetitorStatus.DISCOVERING


async def test_rejecting_every_source_leaves_competitor_discovering(db_session) -> None:
    user = await add_user(db_session, "reject-owner")
    competitor = Competitor(
        user_id=user.id,
        name="Acme",
        primary_domain="acme.example",
    )
    sources = [
        MonitoredSource(
            competitor=competitor,
            url=f"https://acme.example/{path}",
            normalized_url=f"https://acme.example/{path}",
            source_category=SourceCategory.OTHER,
            title=path,
            discovery_reason="Candidate",
        )
        for path in ("one", "two")
    ]
    db_session.add_all(sources)
    await db_session.flush()

    async with await make_client(db_session, user, FakeSourceValidator()) as client:
        approved = await client.patch(
            f"/api/v1/competitors/{competitor.id}/sources/{sources[0].id}",
            json={"approval_status": "approved"},
        )
        assert approved.status_code == 200
        competitor.status = CompetitorStatus.ACTIVE
        await db_session.flush()
        responses = [
            await client.patch(
                f"/api/v1/competitors/{competitor.id}/sources/{source.id}",
                json={"approval_status": "rejected"},
            )
            for source in sources
        ]

    assert all(response.status_code == 200 for response in responses)
    assert all(response.json()["approval_status"] == "rejected" for response in responses)
    await db_session.refresh(competitor)
    assert competitor.status is CompetitorStatus.DISCOVERING


@pytest.mark.parametrize("failure", ["unsafe", "outside-domain"])
async def test_source_approval_revalidates_url_and_domain(db_session, failure: str) -> None:
    user = await add_user(db_session, f"validation-{failure}")
    competitor = Competitor(user_id=user.id, name="Acme", primary_domain="acme.com")
    source = MonitoredSource(
        competitor=competitor,
        url="https://acme.com/redirect",
        normalized_url="https://acme.com/redirect",
        source_category=SourceCategory.OTHER,
        title="Redirect",
        discovery_reason="Needs revalidation",
    )
    db_session.add(source)
    await db_session.flush()
    validator = FakeSourceValidator()
    validator.results[source.url] = (
        UnsafeSourceUrl("not public")
        if failure == "unsafe"
        else "https://acme.com.evil.example/redirect"
    )

    async with await make_client(db_session, user, validator) as client:
        response = await client.patch(
            f"/api/v1/competitors/{competitor.id}/sources/{source.id}",
            json={"approval_status": "approved"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "source URL is not allowed"
    source_status = await db_session.scalar(
        select(MonitoredSource.approval_status).where(MonitoredSource.id == source.id)
    )
    competitor_status = await db_session.scalar(
        select(Competitor.status).where(Competitor.id == competitor.id)
    )
    assert source_status is ApprovalStatus.SUGGESTED
    assert competitor_status is CompetitorStatus.DISCOVERING


async def test_manual_first_party_source_is_validated_scoped_and_idempotent(db_session) -> None:
    user = await add_user(db_session, "manual-source-owner")
    competitor = Competitor(user_id=user.id, name="Acme", primary_domain="acme.com")
    db_session.add(competitor)
    await db_session.flush()
    validator = FakeSourceValidator()
    supplied_url = "https://www.acme.com/pricing?utm_source=setup"
    validator.results[supplied_url] = "https://www.acme.com/pricing"

    async with await make_client(db_session, user, validator) as client:
        first = await client.post(
            f"/api/v1/competitors/{competitor.id}/sources",
            json={"url": supplied_url},
        )
        second = await client.post(
            f"/api/v1/competitors/{competitor.id}/sources",
            json={"url": supplied_url},
        )

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["url"] == "https://www.acme.com/pricing"
    assert first.json()["approval_status"] == "suggested"
    assert validator.calls == [supplied_url, supplied_url]
    sources = list(
        (
            await db_session.scalars(
                select(MonitoredSource).where(MonitoredSource.competitor_id == competitor.id)
            )
        ).all()
    )
    assert len(sources) == 1


async def test_manual_first_party_source_rejects_out_of_scope_url(db_session) -> None:
    user = await add_user(db_session, "outside-source-owner")
    competitor = Competitor(user_id=user.id, name="Acme", primary_domain="acme.com")
    db_session.add(competitor)
    await db_session.flush()

    async with await make_client(db_session, user, FakeSourceValidator()) as client:
        response = await client.post(
            f"/api/v1/competitors/{competitor.id}/sources",
            json={"url": "https://evil.example/pricing"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "source URL is not allowed"


async def test_start_monitoring_approves_selection_rejects_rest_and_queues_first_scan(
    db_session,
    monkeypatch,
) -> None:
    from competitor_scout.api import competitors as competitors_api

    now = datetime(2026, 8, 21, 12, 3, 47, tzinfo=UTC)
    monkeypatch.setattr(competitors_api, "utc_now", lambda: now)
    user = await add_user(db_session, "start-monitoring-owner")
    competitor = Competitor(user_id=user.id, name="Acme", primary_domain="acme.example")
    selected = MonitoredSource(
        competitor=competitor,
        url="https://acme.example/pricing",
        normalized_url="https://acme.example/pricing",
        source_category=SourceCategory.PRICING,
        title="Pricing",
        discovery_reason="Pricing signal",
    )
    skipped = MonitoredSource(
        competitor=competitor,
        url="https://acme.example/blog",
        normalized_url="https://acme.example/blog",
        source_category=SourceCategory.BLOG,
        title="Blog",
        discovery_reason="Company news",
    )
    db_session.add_all([selected, skipped])
    await db_session.flush()

    async with await make_client(db_session, user, FakeSourceValidator()) as client:
        first = await client.post(
            f"/api/v1/competitors/{competitor.id}/start-monitoring",
            json={"source_ids": [str(selected.id)], "run_initial_scan": True},
        )
        second = await client.post(
            f"/api/v1/competitors/{competitor.id}/start-monitoring",
            json={"source_ids": [str(selected.id)], "run_initial_scan": True},
        )

    assert first.status_code == second.status_code == 202
    assert first.json()["competitor"]["status"] == "active"
    assert first.json()["run"]["status"] == "queued"
    assert first.json()["run"]["run_type"] == "manual_scout"
    assert first.json()["run"]["id"] == second.json()["run"]["id"]
    await db_session.refresh(competitor)
    await db_session.refresh(selected)
    await db_session.refresh(skipped)
    assert competitor.starting_snapshot_requested_at == now
    assert selected.approval_status is ApprovalStatus.APPROVED
    assert skipped.approval_status is ApprovalStatus.REJECTED
    jobs = list((await db_session.scalars(select(Job).where(Job.job_type == "manual_scout"))).all())
    assert len(jobs) == 1


async def test_start_monitoring_requires_at_least_one_owned_source(db_session) -> None:
    user = await add_user(db_session, "start-monitoring-empty")
    competitor = Competitor(user_id=user.id, name="Acme", primary_domain="empty.example")
    db_session.add(competitor)
    await db_session.flush()

    async with await make_client(db_session, user, FakeSourceValidator()) as client:
        response = await client.post(
            f"/api/v1/competitors/{competitor.id}/start-monitoring",
            json={"source_ids": [], "run_initial_scan": True},
        )

    assert response.status_code == 422


async def test_capacity_check_is_safe_under_concurrent_creates(
    migrated_database_url: str,
) -> None:
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id: uuid.UUID

    async with sessions.begin() as seed_session:
        user = User(email=f"race-{uuid.uuid4().hex}@example.com", display_name="Race")
        seed_session.add(user)
        await seed_session.flush()
        user_id = user.id
        seed_session.add_all(
            [
                Competitor(
                    user_id=user_id,
                    name=f"Seed {number}",
                    primary_domain=f"seed-{number}.example",
                    daily_run_time_local=time(9, 0),
                )
                for number in range(9)
            ]
        )

    async def race(number: int) -> Competitor:
        async with sessions() as session:
            async with session.begin():
                return await create_competitor(
                    session,
                    user_id=user_id,
                    name=f"Racer {number}",
                    primary_domain=f"racer-{number}.example",
                    description="",
                    daily_run_time_local=time(9, 0),
                    limit=10,
                )

    results = await asyncio.gather(race(1), race(2), return_exceptions=True)

    assert sum(isinstance(result, Competitor) for result in results) == 1
    assert sum(isinstance(result, CompetitorLimitReached) for result in results) == 1
    async with sessions() as verification_session:
        count = await verification_session.scalar(
            select(func.count(Competitor.id)).where(
                Competitor.user_id == user_id,
                Competitor.status != CompetitorStatus.DELETED,
            )
        )
    assert count == 10

    await engine.dispose()


async def test_discovery_endpoint_atomically_enqueues_one_run_per_five_minute_bucket(
    db_session,
    monkeypatch,
) -> None:
    from competitor_scout.api import competitors as competitors_api

    now = datetime(2026, 8, 21, 12, 3, 47, tzinfo=UTC)
    monkeypatch.setattr(competitors_api, "utc_now", lambda: now)
    user = await add_user(db_session, "discovery-api-owner")
    competitor = Competitor(
        user_id=user.id,
        name="Acme",
        primary_domain="discovery-api.example",
    )
    db_session.add(competitor)
    await db_session.flush()

    async with await make_client(db_session, user, FakeSourceValidator()) as client:
        first = await client.post(f"/api/v1/competitors/{competitor.id}/discover-sources")
        second = await client.post(f"/api/v1/competitors/{competitor.id}/discover-sources")

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    run_id = uuid.UUID(first.json()["run_id"])
    run = await db_session.get(ScoutRun, run_id)
    jobs = list(
        (await db_session.scalars(select(Job).where(Job.job_type == "source_discovery"))).all()
    )
    assert run is not None
    assert run.status is ScoutRunStatus.QUEUED
    assert run.run_type is RunType.SOURCE_DISCOVERY
    assert run.scheduled_for == datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
    assert len(jobs) == 1
    assert jobs[0].payload == {"run_id": str(run_id)}


async def test_starting_snapshot_read_is_grounded_and_user_scoped(db_session) -> None:
    owner = await add_user(db_session, "snapshot-owner")
    other = await add_user(db_session, "snapshot-other")
    competitor = Competitor(
        user_id=owner.id,
        name="Acme",
        primary_domain="snapshot.example",
        status=CompetitorStatus.ACTIVE,
        starting_snapshot_requested_at=datetime(2026, 8, 21, 12, tzinfo=UTC),
    )
    run = ScoutRun(
        user_id=owner.id,
        competitor=competitor,
        run_type=RunType.MANUAL_SCOUT,
        status=ScoutRunStatus.COMPLETED,
        scheduled_for=datetime(2026, 8, 21, 12, tzinfo=UTC),
    )
    task = AgentTask(
        scout_run=run,
        role=AgentTaskRole.CHILD_RESEARCHER,
        task_kind="first_party_source_review",
        status=AgentTaskStatus.SUCCEEDED,
        model="test-child",
        objective="Review pricing",
    )
    evidence = EvidenceItem(
        user_id=owner.id,
        competitor=competitor,
        scout_run=run,
        agent_task=task,
        source_url="https://snapshot.example/pricing",
        source_domain="snapshot.example",
        source_title="Acme pricing",
        source_type=SourceType.FIRST_PARTY,
        captured_at=datetime(2026, 8, 21, 12, tzinfo=UTC),
        quoted_text="Acme offers a public enterprise plan for product teams.",
        normalized_claim="acme offers enterprise pricing",
        content_fingerprint="a" * 64,
    )
    db_session.add_all([competitor, run, task, evidence])
    await db_session.flush()
    db_session.add(
        EvidenceObservation(
            scout_run_id=run.id,
            evidence_item_id=evidence.id,
            agent_task_id=task.id,
        )
    )
    snapshot = CompetitorStartingSnapshot(
        user_id=owner.id,
        competitor_id=competitor.id,
        scout_run_id=run.id,
        executive_summary="Acme serves product teams with enterprise analytics.",
        sections=[
            {
                "topic": "pricing",
                "narrative": "Acme publishes enterprise pricing information.",
                "references": [
                    {
                        "evidence_id": str(evidence.id),
                        "statement": "The pricing page describes an enterprise plan.",
                    }
                ],
            }
        ],
        coverage={
            "approved_source_count": 1,
            "inspected_source_count": 1,
            "uninspected_source_count": 0,
            "inspected_source_categories": ["pricing"],
            "coverage_complete": True,
        },
        published_at=datetime(2026, 8, 21, 12, tzinfo=UTC),
    )
    db_session.add(snapshot)
    await db_session.flush()

    async with await make_client(db_session, owner, FakeSourceValidator()) as client:
        response = await client.get(f"/api/v1/competitors/{competitor.id}/starting-snapshot")
    async with await make_client(db_session, other, FakeSourceValidator()) as client:
        hidden = await client.get(f"/api/v1/competitors/{competitor.id}/starting-snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["competitor_name"] == "Acme"
    assert body["sections"][0]["references"][0]["source_url"] == (
        "https://snapshot.example/pricing"
    )
    assert hidden.status_code == 404
