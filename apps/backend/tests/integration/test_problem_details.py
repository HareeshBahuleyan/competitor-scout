from __future__ import annotations

import uuid

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from competitor_scout.config import Settings
from competitor_scout.main import create_app


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


def assert_problem(response, *, status: int, title: str, detail: str) -> None:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == title
    assert body["status"] == status
    assert body["detail"] == detail
    assert uuid.UUID(body["request_id"])


async def test_http_exception_is_problem_details_and_preserves_headers() -> None:
    async def no_database_probe() -> None:
        return None

    app = create_app(settings=api_settings(), readiness_probe=no_database_probe, testing=True)

    @app.get("/test-http-error")
    async def http_error() -> None:
        raise HTTPException(
            status_code=401,
            detail="authentication required",
            headers={"WWW-Authenticate": 'Bearer realm="scout"'},
        )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.get("/test-http-error")

    assert_problem(
        response,
        status=401,
        title="Unauthorized",
        detail="authentication required",
    )
    assert response.headers["www-authenticate"] == 'Bearer realm="scout"'


async def test_request_validation_is_safe_problem_details() -> None:
    async def no_database_probe() -> None:
        return None

    app = create_app(settings=api_settings(), readiness_probe=no_database_probe, testing=True)

    @app.get("/test-validation")
    async def validated(value: int) -> dict[str, int]:
        return {"value": value}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://testserver",
    ) as client:
        response = await client.get("/test-validation", params={"value": "private-secret"})

    assert_problem(
        response,
        status=422,
        title="Unprocessable Entity",
        detail="request validation failed",
    )
    assert "private-secret" not in response.text


async def test_unhandled_exception_is_safe_problem_details() -> None:
    async def no_database_probe() -> None:
        return None

    app = create_app(settings=api_settings(), readiness_probe=no_database_probe, testing=True)

    @app.get("/test-unhandled")
    async def unhandled() -> None:
        raise RuntimeError("database password is private")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="https://testserver",
    ) as client:
        response = await client.get("/test-unhandled")

    assert_problem(
        response,
        status=500,
        title="Internal Server Error",
        detail="internal server error",
    )
    assert "database password" not in response.text
