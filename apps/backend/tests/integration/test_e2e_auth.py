from __future__ import annotations

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from competitor_scout.config import Settings
from competitor_scout.db import session_dependency
from competitor_scout.main import create_app
from competitor_scout.models.auth import Session, User

E2E_SECRET = "e2e-random-secret-with-sufficient-entropy"


def e2e_settings(
    *,
    environment: str = "test",
    secret: str | None = E2E_SECRET,
) -> Settings:
    return Settings(
        environment=environment,
        database_url="postgresql+asyncpg://test:test@localhost/test",
        public_base_url="https://testserver",
        session_secret="s" * 32,
        csrf_secret="c" * 32,
        google_client_id="google-id",
        google_client_secret="google-secret",
        otari_base_url="https://otari.invalid",
        otari_ai_token="dummy-never-live",
        e2e_auth_secret=secret,
    )


def e2e_app(db_session, configured: Settings):
    async def no_database_probe() -> None:
        return None

    async def override_session() -> AsyncIterator:
        yield db_session

    app = create_app(
        settings=configured,
        readiness_probe=no_database_probe,
        testing=True,
    )
    app.dependency_overrides[session_dependency] = override_session
    return app


async def test_e2e_login_route_is_absent_without_test_secret(db_session) -> None:
    app = e2e_app(db_session, e2e_settings(secret=None))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.post(
            "/api/test/login",
            headers={"X-E2E-Secret": E2E_SECRET},
        )

    assert response.status_code == 404
    assert not any(getattr(route, "path", None) == "/api/test/login" for route in app.routes)


async def test_e2e_login_route_is_never_registered_in_production(db_session) -> None:
    app = e2e_app(
        db_session,
        e2e_settings(environment="production", secret=None),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.post(
            "/api/test/login",
            headers={"X-E2E-Secret": E2E_SECRET},
        )

    assert response.status_code == 404
    assert not any(getattr(route, "path", None) == "/api/test/login" for route in app.routes)


async def test_e2e_login_rejects_missing_or_wrong_secret_without_creating_state(
    db_session,
) -> None:
    app = e2e_app(db_session, e2e_settings())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        missing = await client.post("/api/test/login")
        wrong = await client.post(
            "/api/test/login",
            headers={"X-E2E-Secret": "wrong-secret"},
        )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    fixture_user_id = await db_session.scalar(
        select(User.id).where(User.email == "e2e-fixture@example.test")
    )
    assert fixture_user_id is None
    serialized = f"{missing.text} {wrong.text}".casefold()
    assert E2E_SECRET.casefold() not in serialized
    assert "wrong-secret" not in serialized


async def test_valid_e2e_login_creates_normal_secure_session_cookie(db_session) -> None:
    configured = e2e_settings()
    app = e2e_app(db_session, configured)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.post(
            "/api/test/login",
            headers={"X-E2E-Secret": E2E_SECRET},
        )
        me = await client.get("/api/v1/me")

    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert configured.session_cookie_name in cookie
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert me.status_code == 200
    assert me.json()["email"] == "e2e-fixture@example.test"
    assert len(me.json()["csrf_token"]) == 64
    fixture_user_id = await db_session.scalar(
        select(User.id).where(User.email == "e2e-fixture@example.test")
    )
    assert fixture_user_id is not None
    assert (
        await db_session.scalar(
            select(func.count(Session.id)).where(Session.user_id == fixture_user_id)
        )
        == 1
    )
