from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from competitor_scout.config import Settings
from competitor_scout.db import session_dependency
from competitor_scout.main import create_app
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
from competitor_scout.security.csrf import csrf_token
from competitor_scout.services.auth import create_session


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


async def authenticated_client(db_session, user: User) -> tuple[AsyncClient, str]:
    settings = api_settings()
    session, secret = await create_session(db_session, user)
    await db_session.flush()

    async def no_database_probe() -> None:
        return None

    async def override_session() -> AsyncIterator:
        yield db_session

    app = create_app(
        settings=settings,
        readiness_probe=no_database_probe,
        testing=True,
    )
    app.dependency_overrides[session_dependency] = override_session
    client = AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")
    client.cookies.set(
        settings.session_cookie_name,
        f"{session.id}.{secret}",
    )
    token = csrf_token(session.id, secret, settings.csrf_secret.get_secret_value())
    return client, token


async def add_user(db_session, stem: str) -> User:
    user = User(email=f"{stem}-{uuid.uuid4().hex}@example.com", display_name=stem)
    db_session.add(user)
    await db_session.flush()
    return user


async def add_usage(
    db_session,
    *,
    user: User,
    model: str,
    occurred_at: datetime,
    input_tokens: int,
    output_tokens: int,
    tool_calls: int | None,
    settled_cost_usd: Decimal | None,
    provider_request_id: str | None = "request-id",
) -> UsageEvent:
    competitor = Competitor(
        user_id=user.id,
        name=f"Competitor {uuid.uuid4().hex}",
        primary_domain=f"{uuid.uuid4().hex}.example",
    )
    run = ScoutRun(
        user_id=user.id,
        competitor=competitor,
        run_type=RunType.DAILY_SCOUT,
        status=ScoutRunStatus.COMPLETED,
        scheduled_for=occurred_at,
    )
    task = AgentTask(
        scout_run=run,
        role=AgentTaskRole.CHILD_RESEARCHER,
        task_kind="research",
        status=AgentTaskStatus.SUCCEEDED,
        model=model,
        objective="Synthetic public research",
    )
    event = UsageEvent(
        user=user,
        scout_run=run,
        agent_task=task,
        provider_request_id=provider_request_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_calls=tool_calls,
        settled_cost_usd=settled_cost_usd,
        occurred_at=occurred_at,
    )
    db_session.add(event)
    await db_session.flush()
    return event


async def test_settings_get_and_patch_only_user_editable_fields(db_session) -> None:
    user = await add_user(db_session, "settings-owner")
    client, token = await authenticated_client(db_session, user)

    async with client:
        initial = await client.get("/api/v1/settings")
        updated = await client.patch(
            "/api/v1/settings",
            headers={"X-CSRF-Token": token},
            json={
                "display_name": "Market Analyst",
                "timezone": "Europe/Berlin",
                "default_daily_time": "09:30:00",
            },
        )

    assert initial.status_code == 200
    assert initial.json() == {
        "display_name": "settings-owner",
        "timezone": "UTC",
        "default_daily_time": "08:00:00",
    }
    assert updated.status_code == 200
    assert updated.json() == {
        "display_name": "Market Analyst",
        "timezone": "Europe/Berlin",
        "default_daily_time": "09:30:00",
    }
    await db_session.refresh(user)
    assert user.display_name == "Market Analyst"
    assert user.timezone == "Europe/Berlin"
    assert user.default_daily_run_time_local == time(9, 30)


async def test_settings_patch_requires_csrf(db_session) -> None:
    user = await add_user(db_session, "csrf-owner")
    client, _token = await authenticated_client(db_session, user)

    async with client:
        response = await client.patch(
            "/api/v1/settings",
            json={"display_name": "Unauthorized update"},
        )

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "CSRF validation failed"
    await db_session.refresh(user)
    assert user.display_name == "csrf-owner"


async def test_settings_reject_invalid_timezone_and_developer_fields(db_session) -> None:
    user = await add_user(db_session, "validation-owner")
    client, token = await authenticated_client(db_session, user)

    async with client:
        invalid_zone = await client.patch(
            "/api/v1/settings",
            headers={"X-CSRF-Token": token},
            json={"timezone": "Mars/Olympus_Mons"},
        )
        developer_field = await client.patch(
            "/api/v1/settings",
            headers={"X-CSRF-Token": token},
            json={"otari_main_model": "forbidden", "daily_cost_ceiling_usd": 99},
        )

    assert invalid_zone.status_code == 422
    assert developer_field.status_code == 422
    assert invalid_zone.headers["content-type"].startswith("application/problem+json")
    assert developer_field.headers["content-type"].startswith("application/problem+json")
    assert invalid_zone.json()["detail"] == "request validation failed"
    assert developer_field.json()["detail"] == "request validation failed"
    await db_session.refresh(user)
    assert user.timezone == "UTC"


@pytest.mark.parametrize(
    "payload",
    [
        {"display_name": None},
        {"timezone": None},
        {"default_daily_time": None},
    ],
)
async def test_settings_reject_null_for_non_nullable_fields(db_session, payload) -> None:
    user = await add_user(db_session, "null-settings")
    client, token = await authenticated_client(db_session, user)

    async with client:
        response = await client.patch(
            "/api/v1/settings",
            headers={"X-CSRF-Token": token},
            json=payload,
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "request validation failed"


async def test_usage_summary_groups_by_utc_date_and_model_without_identifiers(db_session) -> None:
    user = await add_user(db_session, "usage-owner")
    outsider = await add_user(db_session, "usage-outsider")
    await add_usage(
        db_session,
        user=user,
        model="child-model",
        occurred_at=datetime(2026, 8, 21, 22, 30, tzinfo=UTC),
        input_tokens=100,
        output_tokens=20,
        tool_calls=1,
        settled_cost_usd=Decimal("0.100000"),
        provider_request_id="private-provider-request-one",
    )
    await add_usage(
        db_session,
        user=user,
        model="child-model",
        occurred_at=datetime(2026, 8, 21, 23, 45, tzinfo=UTC),
        input_tokens=50,
        output_tokens=10,
        tool_calls=2,
        settled_cost_usd=Decimal("0.200000"),
        provider_request_id="private-provider-request-two",
    )
    await add_usage(
        db_session,
        user=user,
        model="main-model",
        occurred_at=datetime(2026, 8, 22, 0, 15, tzinfo=UTC),
        input_tokens=80,
        output_tokens=30,
        tool_calls=None,
        settled_cost_usd=None,
        provider_request_id=None,
    )
    await add_usage(
        db_session,
        user=outsider,
        model="secret-outsider-model",
        occurred_at=datetime(2026, 8, 21, 22, 30, tzinfo=UTC),
        input_tokens=999,
        output_tokens=999,
        tool_calls=9,
        settled_cost_usd=Decimal("9.990000"),
    )
    client, _token = await authenticated_client(db_session, user)

    async with client:
        response = await client.get("/api/v1/usage/summary")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "date": "2026-08-22",
                "model": "main-model",
                "input_tokens": 80,
                "output_tokens": 30,
                "settled_cost_usd": None,
            },
            {
                "date": "2026-08-21",
                "model": "child-model",
                "input_tokens": 150,
                "output_tokens": 30,
                "settled_cost_usd": "0.300000",
            },
        ]
    }
    serialized = response.text.casefold()
    assert "private-provider-request" not in serialized
    assert "secret-outsider-model" not in serialized
    assert "user_id" not in serialized
    assert "scout_run_id" not in serialized
    assert "agent_task_id" not in serialized


async def test_usage_event_roundtrips_without_provider_request_id(db_session) -> None:
    user = await add_user(db_session, "no-request-id")
    event = await add_usage(
        db_session,
        user=user,
        model="main-model",
        occurred_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        input_tokens=12,
        output_tokens=3,
        tool_calls=None,
        settled_cost_usd=None,
        provider_request_id=None,
    )
    event_id = event.id
    db_session.expire_all()

    persisted = await db_session.get(UsageEvent, event_id)

    assert persisted is not None
    assert persisted.provider_request_id is None
    assert persisted.input_tokens == 12
    assert persisted.output_tokens == 3
    column = UsageEvent.__table__.c.provider_request_id
    assert column.nullable is True


async def test_user_default_daily_time_has_database_default(db_session) -> None:
    user = User(email=f"default-{uuid.uuid4().hex}@example.com", display_name="Default")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.default_daily_run_time_local == time(8)
    column = User.__table__.c.default_daily_run_time_local
    assert column.nullable is False
    assert column.server_default is not None


async def test_usage_summary_requires_authentication(db_session) -> None:
    async def no_database_probe() -> None:
        return None

    async def override_session() -> AsyncIterator:
        yield db_session

    app = create_app(
        settings=api_settings(),
        readiness_probe=no_database_probe,
        testing=True,
    )
    app.dependency_overrides[session_dependency] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.get("/api/v1/usage/summary")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 401
    assert body["detail"] == "authentication required"
    assert uuid.UUID(body["request_id"])


async def test_settings_row_is_owned_by_authenticated_user(db_session) -> None:
    owner = await add_user(db_session, "owner-settings")
    outsider = await add_user(db_session, "outsider-settings")
    owner.timezone = "Asia/Tokyo"
    owner.default_daily_run_time_local = time(7, 15)
    await db_session.flush()
    client, token = await authenticated_client(db_session, outsider)

    async with client:
        response = await client.patch(
            "/api/v1/settings",
            headers={"X-CSRF-Token": token},
            json={"timezone": "America/New_York"},
        )

    assert response.status_code == 200
    await db_session.refresh(owner)
    await db_session.refresh(outsider)
    assert owner.timezone == "Asia/Tokyo"
    assert owner.default_daily_run_time_local == time(7, 15)
    assert outsider.timezone == "America/New_York"


async def test_usage_summary_uses_persisted_rows(db_session) -> None:
    user = await add_user(db_session, "persisted-usage")
    event = await add_usage(
        db_session,
        user=user,
        model="persisted-model",
        occurred_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
        input_tokens=7,
        output_tokens=4,
        tool_calls=0,
        settled_cost_usd=Decimal("0"),
    )
    await db_session.flush()
    persisted = await db_session.scalar(select(UsageEvent).where(UsageEvent.id == event.id))

    assert persisted is not None
    assert persisted.model == "persisted-model"
