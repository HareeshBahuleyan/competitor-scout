from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from competitor_scout.agents.contracts import FindingCategory, SignificanceLevel, SourceType
from competitor_scout.api.deps import current_user
from competitor_scout.config import Settings
from competitor_scout.db import session_dependency
from competitor_scout.main import create_app
from competitor_scout.models.auth import User
from competitor_scout.models.intelligence import (
    AgentTask,
    AgentTaskRole,
    AgentTaskStatus,
    Competitor,
    CompetitorStatus,
    EvidenceItem,
    Finding,
    FindingEvidence,
    RunType,
    ScoutRun,
    ScoutRunStatus,
)
from competitor_scout.schemas.findings import EvidencePublication, FindingPublication
from competitor_scout.services.findings import (
    FindingPublicationService,
    PublicationValidationError,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class PublicationContext:
    user_id: uuid.UUID
    competitor_id: uuid.UUID
    scout_run_id: uuid.UUID
    agent_task_id: uuid.UUID


@pytest_asyncio.fixture
async def publication_store(migrated_database_url: str):
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        await engine.dispose()


async def seed_context(sessions, stem: str = "publisher") -> PublicationContext:
    async with sessions.begin() as session:
        user = User(email=f"{stem}-{uuid.uuid4().hex}@example.com", display_name=stem)
        competitor = Competitor(
            user=user,
            name=f"{stem} competitor",
            primary_domain=f"{uuid.uuid4().hex}.example",
        )
        run = ScoutRun(
            user=user,
            competitor=competitor,
            run_type=RunType.DAILY_SCOUT,
            status=ScoutRunStatus.SYNTHESIZING,
            scheduled_for=NOW,
        )
        task = AgentTask(
            scout_run=run,
            role=AgentTaskRole.CHILD_RESEARCHER,
            task_kind="first_party_source_review",
            status=AgentTaskStatus.SUCCEEDED,
            model_alias="competitor-scout-child",
            objective="Review pricing",
        )
        session.add(task)
        await session.flush()
        return PublicationContext(user.id, competitor.id, run.id, task.id)


async def seed_context_with_lifecycle(
    sessions,
    stem: str,
    *,
    competitor_status: CompetitorStatus = CompetitorStatus.ACTIVE,
    run_type: RunType = RunType.DAILY_SCOUT,
    run_status: ScoutRunStatus = ScoutRunStatus.SYNTHESIZING,
    task_role: AgentTaskRole = AgentTaskRole.CHILD_RESEARCHER,
    task_status: AgentTaskStatus = AgentTaskStatus.SUCCEEDED,
) -> PublicationContext:
    async with sessions.begin() as session:
        user = User(email=f"{stem}-{uuid.uuid4().hex}@example.com", display_name=stem)
        competitor = Competitor(
            user=user,
            name=f"{stem} competitor",
            primary_domain=f"{uuid.uuid4().hex}.example",
            status=competitor_status,
            deleted_at=NOW if competitor_status is CompetitorStatus.DELETED else None,
        )
        run = ScoutRun(
            user=user,
            competitor=competitor,
            run_type=run_type,
            status=run_status,
            scheduled_for=NOW,
        )
        task = AgentTask(
            scout_run=run,
            role=task_role,
            task_kind="first_party_source_review",
            status=task_status,
            model_alias="competitor-scout-child",
            objective="Review pricing",
        )
        session.add(task)
        await session.flush()
        return PublicationContext(user.id, competitor.id, run.id, task.id)


def evidence(
    context: PublicationContext,
    *,
    suffix: str = "pricing",
    fingerprint: str | None = None,
    agent_task_id: uuid.UUID | None = None,
    source_url: str | None = None,
) -> EvidencePublication:
    resolved_url = source_url or f"https://www.example.com/{suffix}"
    quote = f"The {suffix} page contains a sufficiently long direct quotation."
    resolved_fingerprint = (
        fingerprint or hashlib.sha256(f"{resolved_url}\n{quote}".encode()).hexdigest()
    )
    return EvidencePublication(
        agent_task_id=agent_task_id or context.agent_task_id,
        source_url=resolved_url,
        source_title=suffix.title(),
        source_type=SourceType.FIRST_PARTY,
        published_at=NOW,
        captured_at=NOW,
        quoted_text=quote,
        normalized_claim=f"Normalized claim for {suffix}",
        content_fingerprint=resolved_fingerprint,
    )


def finding(
    *,
    normalized_claim: str = "Pro plan costs $99 per month",
    evidence_indexes: list[int] | None = None,
    primary_evidence_index: int = 0,
    confidence: Decimal = Decimal("0.9500"),
) -> FindingPublication:
    return FindingPublication(
        category=FindingCategory.PRICING,
        title="Pro price increased",
        summary="The monthly Pro price is now $99.",
        significance_explanation="This changes the competitive price comparison.",
        significance_level=SignificanceLevel.HIGH,
        confidence=confidence,
        normalized_claim=normalized_claim,
        material_change=True,
        evidence_indexes=evidence_indexes or [0],
        primary_evidence_index=primary_evidence_index,
        decision_rationale="The cited first-party page directly supports the claim.",
    )


async def test_publication_rejects_bad_citation_without_orphan_rows(publication_store) -> None:
    context = await seed_context(publication_store, "rollback")
    service = FindingPublicationService(publication_store)

    with pytest.raises(PublicationValidationError, match="citation"):
        await service.publish(
            user_id=context.user_id,
            competitor_id=context.competitor_id,
            scout_run_id=context.scout_run_id,
            finding=finding(evidence_indexes=[1], primary_evidence_index=1),
            evidence=[evidence(context)],
            published_at=NOW,
        )

    async with publication_store() as session:
        assert await session.scalar(select(func.count(EvidenceItem.id))) == 0
        assert await session.scalar(select(func.count(Finding.id))) == 0
        assert await session.scalar(select(func.count()).select_from(FindingEvidence)) == 0


async def test_publication_rejects_low_confidence_and_wrong_task_ownership(
    publication_store,
) -> None:
    context = await seed_context(publication_store, "owner")
    other = await seed_context(publication_store, "other")
    service = FindingPublicationService(publication_store, minimum_confidence=Decimal("0.70"))

    with pytest.raises(PublicationValidationError, match="confidence"):
        await service.publish(
            user_id=context.user_id,
            competitor_id=context.competitor_id,
            scout_run_id=context.scout_run_id,
            finding=finding(confidence=Decimal("0.6999")),
            evidence=[evidence(context)],
            published_at=NOW,
        )
    with pytest.raises(PublicationValidationError, match="ownership"):
        await service.publish(
            user_id=context.user_id,
            competitor_id=context.competitor_id,
            scout_run_id=context.scout_run_id,
            finding=finding(),
            evidence=[evidence(context, agent_task_id=other.agent_task_id)],
            published_at=NOW,
        )
    with pytest.raises(PublicationValidationError, match="ownership"):
        await service.publish(
            user_id=context.user_id,
            competitor_id=context.competitor_id,
            scout_run_id=context.scout_run_id,
            finding=finding(evidence_indexes=[0]),
            evidence=[
                evidence(context),
                evidence(
                    context,
                    suffix="unreferenced",
                    agent_task_id=other.agent_task_id,
                ),
            ],
            published_at=NOW,
        )

    async with publication_store() as session:
        assert await session.scalar(select(func.count(Finding.id))) == 0
        assert await session.scalar(select(func.count(EvidenceItem.id))) == 0


async def test_publication_rejects_non_public_source_domain(publication_store) -> None:
    context = await seed_context(publication_store, "source-domain")
    service = FindingPublicationService(publication_store)

    with pytest.raises(PublicationValidationError, match="source URL"):
        await service.publish(
            user_id=context.user_id,
            competitor_id=context.competitor_id,
            scout_run_id=context.scout_run_id,
            finding=finding(),
            evidence=[evidence(context, source_url="https://user@example.com/pricing")],
            published_at=NOW,
        )


async def test_publication_rejects_unverified_evidence_fingerprint_without_orphans(
    publication_store,
) -> None:
    context = await seed_context(publication_store, "fingerprint")
    service = FindingPublicationService(publication_store)

    with pytest.raises(PublicationValidationError, match="fingerprint"):
        await service.publish(
            user_id=context.user_id,
            competitor_id=context.competitor_id,
            scout_run_id=context.scout_run_id,
            finding=finding(),
            evidence=[evidence(context, fingerprint="f" * 64)],
            published_at=NOW,
        )

    async with publication_store() as session:
        assert await session.scalar(select(func.count(EvidenceItem.id))) == 0
        assert await session.scalar(select(func.count(Finding.id))) == 0


async def test_evidence_conflict_never_substitutes_different_normalized_content(
    publication_store,
) -> None:
    context = await seed_context(publication_store, "content-conflict")
    service = FindingPublicationService(publication_store)
    original = evidence(context)
    await service.publish(
        user_id=context.user_id,
        competitor_id=context.competitor_id,
        scout_run_id=context.scout_run_id,
        finding=finding(),
        evidence=[original],
        published_at=NOW,
    )
    conflicting = original.model_copy(
        update={"normalized_claim": "A different normalized claim for the same quotation"}
    )

    with pytest.raises(PublicationValidationError, match="different content"):
        await service.publish(
            user_id=context.user_id,
            competitor_id=context.competitor_id,
            scout_run_id=context.scout_run_id,
            finding=finding(normalized_claim="A distinct finding claim"),
            evidence=[conflicting],
            published_at=NOW + timedelta(minutes=1),
        )

    async with publication_store() as session:
        assert (
            await session.scalar(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.competitor_id == context.competitor_id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(Finding.id)).where(Finding.competitor_id == context.competitor_id)
            )
            == 1
        )


@pytest.mark.parametrize(
    "lifecycle",
    [
        {"competitor_status": CompetitorStatus.DELETED},
        {"run_type": RunType.SOURCE_DISCOVERY},
        {"run_status": ScoutRunStatus.QUEUED},
        {"run_status": ScoutRunStatus.FAILED},
        {"task_role": AgentTaskRole.MAIN_PLANNER},
        {"task_status": AgentTaskStatus.RUNNING},
        {"task_status": AgentTaskStatus.FAILED},
    ],
    ids=[
        "deleted-competitor",
        "source-discovery-run",
        "queued-run",
        "failed-run",
        "planner-task",
        "running-child",
        "failed-child",
    ],
)
async def test_publication_rejects_invalid_competitor_run_and_task_lifecycle(
    publication_store,
    lifecycle: dict[str, object],
) -> None:
    context = await seed_context_with_lifecycle(
        publication_store,
        f"lifecycle-{uuid.uuid4().hex}",
        **lifecycle,
    )

    with pytest.raises(PublicationValidationError, match="lifecycle"):
        await FindingPublicationService(publication_store).publish(
            user_id=context.user_id,
            competitor_id=context.competitor_id,
            scout_run_id=context.scout_run_id,
            finding=finding(),
            evidence=[evidence(context)],
            published_at=NOW,
        )

    async with publication_store() as session:
        assert (
            await session.scalar(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.competitor_id == context.competitor_id
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count(Finding.id)).where(Finding.competitor_id == context.competitor_id)
            )
            == 0
        )


async def test_primary_evidence_domain_partitions_finding_duplicate_keys(
    publication_store,
) -> None:
    context = await seed_context(publication_store, "source-key")
    service = FindingPublicationService(publication_store)

    first = await service.publish(
        user_id=context.user_id,
        competitor_id=context.competitor_id,
        scout_run_id=context.scout_run_id,
        finding=finding(),
        evidence=[evidence(context, source_url="https://news-a.example/story")],
        published_at=NOW,
    )
    second = await service.publish(
        user_id=context.user_id,
        competitor_id=context.competitor_id,
        scout_run_id=context.scout_run_id,
        finding=finding(),
        evidence=[evidence(context, source_url="https://news-b.example/story")],
        published_at=NOW + timedelta(minutes=1),
    )

    assert second.id != first.id
    async with publication_store() as session:
        assert (
            await session.scalar(
                select(func.count(Finding.id)).where(Finding.competitor_id == context.competitor_id)
            )
            == 2
        )


async def test_duplicate_updates_last_seen_and_adds_evidence_without_new_feed_row(
    publication_store,
) -> None:
    context = await seed_context(publication_store, "duplicate")
    service = FindingPublicationService(publication_store)
    first = await service.publish(
        user_id=context.user_id,
        competitor_id=context.competitor_id,
        scout_run_id=context.scout_run_id,
        finding=finding(normalized_claim="Pro price increased"),
        evidence=[evidence(context, suffix="pricing")],
        published_at=NOW,
    )
    second = await service.publish(
        user_id=context.user_id,
        competitor_id=context.competitor_id,
        scout_run_id=context.scout_run_id,
        finding=finding(normalized_claim="  pro PRICE\nincreased "),
        evidence=[evidence(context, suffix="announcement")],
        published_at=NOW + timedelta(days=1),
    )

    assert second.id == first.id
    assert second.first_seen_at == NOW
    assert second.last_seen_at == NOW + timedelta(days=1)
    assert second.published_at == NOW
    async with publication_store() as session:
        assert (
            await session.scalar(
                select(func.count(Finding.id)).where(Finding.competitor_id == context.competitor_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.competitor_id == context.competitor_id
                )
            )
            == 2
        )
        links = list(
            (
                await session.scalars(
                    select(FindingEvidence)
                    .where(FindingEvidence.finding_id == first.id)
                    .order_by(FindingEvidence.citation_order)
                )
            ).all()
        )
    assert [link.citation_order for link in links] == [1, 2]
    assert sum(link.is_primary for link in links) == 1


async def test_evidence_is_unique_across_distinct_findings(publication_store) -> None:
    context = await seed_context(publication_store, "evidence-unique")
    service = FindingPublicationService(publication_store)
    shared = evidence(context)
    await service.publish(
        user_id=context.user_id,
        competitor_id=context.competitor_id,
        scout_run_id=context.scout_run_id,
        finding=finding(normalized_claim="First material claim"),
        evidence=[shared],
        published_at=NOW,
    )
    await service.publish(
        user_id=context.user_id,
        competitor_id=context.competitor_id,
        scout_run_id=context.scout_run_id,
        finding=finding(normalized_claim="Second material claim"),
        evidence=[shared],
        published_at=NOW,
    )

    async with publication_store() as session:
        assert (
            await session.scalar(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.competitor_id == context.competitor_id
                )
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(Finding.id)).where(Finding.competitor_id == context.competitor_id)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(FindingEvidence)
                .join(Finding, Finding.id == FindingEvidence.finding_id)
                .where(Finding.competitor_id == context.competitor_id)
            )
            == 2
        )


async def test_exact_evidence_reuse_keeps_first_observation_provenance(
    publication_store,
) -> None:
    first_context = await seed_context(publication_store, "first-observation")
    service = FindingPublicationService(publication_store)
    first = await service.publish(
        user_id=first_context.user_id,
        competitor_id=first_context.competitor_id,
        scout_run_id=first_context.scout_run_id,
        finding=finding(),
        evidence=[evidence(first_context)],
        published_at=NOW,
    )
    async with publication_store.begin() as session:
        first_run = await session.get(ScoutRun, first_context.scout_run_id)
        assert first_run is not None
        first_run.status = ScoutRunStatus.COMPLETED
        later_run = ScoutRun(
            user_id=first_context.user_id,
            competitor_id=first_context.competitor_id,
            run_type=RunType.MANUAL_SCOUT,
            status=ScoutRunStatus.SYNTHESIZING,
            scheduled_for=NOW + timedelta(days=1),
        )
        later_task = AgentTask(
            scout_run=later_run,
            role=AgentTaskRole.CHILD_RESEARCHER,
            task_kind="first_party_source_review",
            status=AgentTaskStatus.SUCCEEDED,
            model_alias="competitor-scout-child",
            objective="Review pricing again",
        )
        session.add(later_task)
        await session.flush()
        later_context = PublicationContext(
            first_context.user_id,
            first_context.competitor_id,
            later_run.id,
            later_task.id,
        )

    repeated = await service.publish(
        user_id=later_context.user_id,
        competitor_id=later_context.competitor_id,
        scout_run_id=later_context.scout_run_id,
        finding=finding(),
        evidence=[evidence(later_context)],
        published_at=NOW + timedelta(days=1),
    )

    assert repeated.id == first.id
    assert repeated.last_seen_at == NOW + timedelta(days=1)
    async with publication_store() as session:
        stored = list(
            (
                await session.scalars(
                    select(EvidenceItem).where(
                        EvidenceItem.competitor_id == first_context.competitor_id
                    )
                )
            ).all()
        )
    assert len(stored) == 1
    assert stored[0].scout_run_id == first_context.scout_run_id
    assert stored[0].agent_task_id == first_context.agent_task_id


async def test_concurrent_duplicate_publication_creates_one_finding(publication_store) -> None:
    context = await seed_context(publication_store, "concurrent")
    first_service = FindingPublicationService(publication_store)
    second_service = FindingPublicationService(publication_store)

    first, second = await asyncio.gather(
        first_service.publish(
            user_id=context.user_id,
            competitor_id=context.competitor_id,
            scout_run_id=context.scout_run_id,
            finding=finding(),
            evidence=[evidence(context, suffix="pricing")],
            published_at=NOW,
        ),
        second_service.publish(
            user_id=context.user_id,
            competitor_id=context.competitor_id,
            scout_run_id=context.scout_run_id,
            finding=finding(normalized_claim=" PRO PLAN costs $99 per month "),
            evidence=[evidence(context, suffix="news")],
            published_at=NOW + timedelta(minutes=1),
        ),
    )

    assert first.id == second.id
    async with publication_store() as session:
        assert (
            await session.scalar(
                select(func.count(Finding.id)).where(Finding.competitor_id == context.competitor_id)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count(EvidenceItem.id)).where(
                    EvidenceItem.competitor_id == context.competitor_id
                )
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(FindingEvidence)
                .join(Finding, Finding.id == FindingEvidence.finding_id)
                .where(Finding.competitor_id == context.competitor_id)
            )
            == 2
        )


def api_settings() -> Settings:
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
    )


async def findings_client(db_session, user: User) -> AsyncClient:
    async def no_database_probe() -> None:
        return None

    async def override_session() -> AsyncIterator:
        yield db_session

    async def override_user() -> User:
        return user

    app = create_app(
        settings=api_settings(),
        readiness_probe=no_database_probe,
        testing=True,
        current_user_override=override_user,
    )
    app.dependency_overrides[session_dependency] = override_session
    app.dependency_overrides[current_user] = override_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")


async def api_finding(db_session, user: User, *, category, significance, confidence, when):
    competitor = Competitor(
        user=user,
        name=f"Competitor {uuid.uuid4().hex[:6]}",
        primary_domain=f"{uuid.uuid4().hex}.example",
    )
    run = ScoutRun(
        user=user,
        competitor=competitor,
        run_type=RunType.DAILY_SCOUT,
        status=ScoutRunStatus.COMPLETED,
        scheduled_for=when,
    )
    task = AgentTask(
        scout_run=run,
        role=AgentTaskRole.CHILD_RESEARCHER,
        task_kind="first_party_source_review",
        status=AgentTaskStatus.SUCCEEDED,
        model_alias="child",
        objective="Research",
    )
    item = EvidenceItem(
        user=user,
        competitor=competitor,
        scout_run=run,
        agent_task=task,
        source_url="https://public.example/pricing",
        source_domain="public.example",
        source_title="Pricing",
        source_type=SourceType.FIRST_PARTY,
        captured_at=when,
        quoted_text="A sufficiently long direct quote for the finding detail.",
        normalized_claim=f"Claim {uuid.uuid4().hex}",
        content_fingerprint=uuid.uuid4().hex.ljust(64, "0"),
    )
    record = Finding(
        user=user,
        competitor=competitor,
        originating_scout_run=run,
        category=category,
        title="Finding",
        summary="Summary",
        significance_explanation="Why it matters",
        significance_level=significance,
        confidence=confidence,
        decision_rationale="Direct evidence supports this finding.",
        normalized_claim_fingerprint=uuid.uuid4().hex.ljust(64, "0"),
        duplicate_key=uuid.uuid4().hex.ljust(64, "0"),
        first_seen_at=when,
        last_seen_at=when,
        published_at=when,
    )
    link = FindingEvidence(finding=record, evidence_item=item, citation_order=1, is_primary=True)
    db_session.add(link)
    await db_session.flush()
    return competitor, record, item


async def test_findings_api_scopes_filters_and_cursor_pages(db_session) -> None:
    owner = User(email=f"feed-{uuid.uuid4().hex}@example.com", display_name="Feed Owner")
    outsider = User(email=f"other-{uuid.uuid4().hex}@example.com", display_name="Other")
    db_session.add_all([owner, outsider])
    await db_session.flush()
    competitor, newest, _ = await api_finding(
        db_session,
        owner,
        category=FindingCategory.PRICING,
        significance=SignificanceLevel.HIGH,
        confidence=Decimal("0.9000"),
        when=NOW,
    )
    _, older, _ = await api_finding(
        db_session,
        owner,
        category=FindingCategory.PRODUCT,
        significance=SignificanceLevel.LOW,
        confidence=Decimal("0.7500"),
        when=NOW - timedelta(days=1),
    )
    _, foreign, _ = await api_finding(
        db_session,
        outsider,
        category=FindingCategory.PRICING,
        significance=SignificanceLevel.CRITICAL,
        confidence=Decimal("0.9900"),
        when=NOW + timedelta(days=1),
    )

    async with await findings_client(db_session, owner) as client:
        page_one = await client.get("/api/v1/findings", params={"limit": 1})
        page_two = await client.get(
            "/api/v1/findings",
            params={"limit": 1, "cursor": page_one.json()["next_cursor"]},
        )
        filtered = await client.get(
            "/api/v1/findings",
            params={
                "competitor_id": str(competitor.id),
                "category": "pricing",
                "significance": "high",
                "confidence_min": "0.85",
                "published_from": (NOW - timedelta(hours=1)).isoformat(),
                "published_to": (NOW + timedelta(hours=1)).isoformat(),
            },
        )
        detail = await client.get(f"/api/v1/findings/{newest.id}")
        citations = await client.get(f"/api/v1/findings/{newest.id}/evidence")
        foreign_detail = await client.get(f"/api/v1/findings/{foreign.id}")
        foreign_evidence = await client.get(f"/api/v1/findings/{foreign.id}/evidence")

    assert page_one.status_code == 200
    assert [item["id"] for item in page_one.json()["items"]] == [str(newest.id)]
    assert page_one.json()["next_cursor"]
    assert [item["id"] for item in page_two.json()["items"]] == [str(older.id)]
    assert page_two.json()["next_cursor"] is None
    assert [item["id"] for item in filtered.json()["items"]] == [str(newest.id)]
    assert detail.status_code == 200
    assert detail.json()["decision_rationale"] == "Direct evidence supports this finding."
    assert citations.status_code == 200
    assert citations.json()["items"][0]["citation_order"] == 1
    assert foreign_detail.status_code == 404
    assert foreign_evidence.status_code == 404
