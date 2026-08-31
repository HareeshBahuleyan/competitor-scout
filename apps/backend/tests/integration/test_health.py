from collections.abc import Awaitable, Callable

from fastapi.testclient import TestClient

from competitor_scout.config import Settings
from competitor_scout.main import create_app


def make_test_settings() -> Settings:
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


def client_with_probe(probe: Callable[[], Awaitable[None]]) -> TestClient:
    return TestClient(create_app(settings=make_test_settings(), readiness_probe=probe))


def test_liveness_does_not_call_database_probe() -> None:
    async def database_probe() -> None:
        raise AssertionError("liveness called the database")

    response = client_with_probe(database_probe).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_database_unavailable_without_leaking_error() -> None:
    async def database_probe() -> None:
        raise ConnectionError("credentials and hostname must not leak")

    response = client_with_probe(database_probe).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "database unavailable"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "credentials" not in response.text
