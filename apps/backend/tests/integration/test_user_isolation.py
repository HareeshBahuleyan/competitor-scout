from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

from httpx import ASGITransport, AsyncClient

from competitor_scout.agents.contracts import (
    FindingCategory,
    SignificanceLevel,
    SourceType,
)
from competitor_scout.api.deps import current_user, require_csrf
from competitor_scout.config import Settings
from competitor_scout.db import session_dependency
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
    Finding,
    FindingEvidence,
    MonitoredSource,
    RunType,
    ScoutRun,
    ScoutRunStatus,
    SourceCategory,
    UsageEvent,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def isolation_settings() -> Settings:
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


async def isolation_client(db_session, outsider: User) -> AsyncClient:
    async def no_database_probe() -> None:
        return None

    async def override_session() -> AsyncIterator:
        yield db_session

    async def override_user() -> User:
        return outsider

    async def skip_csrf() -> None:
        return None

    app = create_app(
        settings=isolation_settings(),
        readiness_probe=no_database_probe,
        testing=True,
        current_user_override=override_user,
    )
    app.dependency_overrides[session_dependency] = override_session
    app.dependency_overrides[current_user] = override_user
    app.dependency_overrides[require_csrf] = skip_csrf
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")


async def test_complete_cross_user_api_isolation_matrix(db_session) -> None:
    owner = User(
        email=f"matrix-owner-{uuid.uuid4().hex}@example.com",
        display_name="Private Owner Identity",
        timezone="Asia/Tokyo",
    )
    outsider = User(
        email=f"matrix-outsider-{uuid.uuid4().hex}@example.com",
        display_name="Outsider",
        timezone="UTC",
    )
    competitor = Competitor(
        user=owner,
        name="Private Competitor Identity",
        primary_domain=f"{uuid.uuid4().hex}.example",
        status=CompetitorStatus.ACTIVE,
    )
    source = MonitoredSource(
        competitor=competitor,
        url=f"https://{competitor.primary_domain}/pricing",
        normalized_url=f"https://{competitor.primary_domain}/pricing",
        source_category=SourceCategory.PRICING,
        title="Private Source Identity",
        discovery_reason="Synthetic isolation fixture",
        approval_status=ApprovalStatus.APPROVED,
    )
    run = ScoutRun(
        user=owner,
        competitor=competitor,
        run_type=RunType.MANUAL_SCOUT,
        status=ScoutRunStatus.COMPLETED,
        scheduled_for=NOW,
    )
    task = AgentTask(
        scout_run=run,
        role=AgentTaskRole.CHILD_RESEARCHER,
        task_kind="first_party_source_review",
        status=AgentTaskStatus.SUCCEEDED,
        model="private-owner-model",
        objective="Private task objective",
    )
    evidence = EvidenceItem(
        user=owner,
        competitor=competitor,
        scout_run=run,
        agent_task=task,
        source_url=f"https://{competitor.primary_domain}/pricing",
        source_domain=competitor.primary_domain,
        source_title="Private Evidence Identity",
        source_type=SourceType.FIRST_PARTY,
        captured_at=NOW,
        quoted_text="A sufficiently long synthetic isolation quotation.",
        normalized_claim="Private normalized claim",
        content_fingerprint="a" * 64,
    )
    finding = Finding(
        user=owner,
        competitor=competitor,
        originating_scout_run=run,
        category=FindingCategory.PRICING,
        title="Private Finding Identity",
        summary="Private finding summary",
        significance_explanation="Private significance",
        significance_level=SignificanceLevel.HIGH,
        confidence=Decimal("0.9000"),
        decision_rationale="Private rationale",
        normalized_claim_fingerprint="b" * 64,
        duplicate_key="c" * 64,
        first_seen_at=NOW,
        last_seen_at=NOW,
        published_at=NOW,
    )
    link = FindingEvidence(
        finding=finding,
        evidence_item=evidence,
        citation_order=1,
        is_primary=True,
    )
    weekly_run = ScoutRun(
        user=owner,
        competitor_id=None,
        run_type=RunType.WEEKLY_BRIEF,
        status=ScoutRunStatus.COMPLETED,
        scheduled_for=NOW,
    )
    brief = WeeklyBrief(
        user=owner,
        scout_run=weekly_run,
        period_start=date(2026, 8, 10),
        period_end=date(2026, 8, 16),
        title="Private Brief Identity",
        executive_summary="Private brief summary",
        sections=[],
        published_at=NOW,
    )
    usage = UsageEvent(
        user=owner,
        scout_run=run,
        agent_task=task,
        provider_request_id="private-provider-id",
        model="private-owner-model",
        input_tokens=10,
        output_tokens=5,
        tool_calls=1,
        settled_cost_usd=Decimal("0.100000"),
        pricing_source="private-pricing-source",
        occurred_at=NOW,
    )
    db_session.add_all([outsider, source, link, brief, usage])
    await db_session.flush()

    async with await isolation_client(db_session, outsider) as client:
        resource_responses = [
            await client.get(f"/api/v1/competitors/{competitor.id}"),
            await client.patch(
                f"/api/v1/competitors/{competitor.id}",
                json={"name": "cross-user mutation"},
            ),
            await client.get(f"/api/v1/competitors/{competitor.id}/sources"),
            await client.patch(
                f"/api/v1/competitors/{competitor.id}/sources/{source.id}",
                json={"approval_status": "rejected"},
            ),
            await client.post(f"/api/v1/competitors/{competitor.id}/runs"),
            await client.get(f"/api/v1/runs/{run.id}"),
            await client.get(f"/api/v1/runs/{run.id}/tasks"),
            await client.get(f"/api/v1/runs/{run.id}/usage"),
            await client.get(f"/api/v1/findings/{finding.id}"),
            await client.get(f"/api/v1/findings/{finding.id}/evidence"),
            await client.get(f"/api/v1/briefs/{brief.id}"),
        ]
        local_responses = [
            await client.get("/api/v1/competitors"),
            await client.get("/api/v1/runs"),
            await client.get("/api/v1/findings"),
            await client.get("/api/v1/briefs"),
            await client.get("/api/v1/settings"),
            await client.get("/api/v1/usage/summary"),
        ]

    owner_identifiers = {
        str(owner.id),
        owner.email,
        str(competitor.id),
        str(source.id),
        str(run.id),
        str(task.id),
        str(evidence.id),
        str(finding.id),
        str(brief.id),
        "Private Owner Identity",
        "Private Competitor Identity",
        "Private Source Identity",
        "Private Evidence Identity",
        "Private Finding Identity",
        "Private Brief Identity",
        "private-owner-model",
        "private-provider-id",
        "private-pricing-source",
    }
    assert all(response.status_code == 404 for response in resource_responses)
    serialized = " ".join(
        response.text for response in resource_responses + local_responses
    ).casefold()
    assert all(identifier.casefold() not in serialized for identifier in owner_identifiers)
    assert all(response.status_code == 200 for response in local_responses)
