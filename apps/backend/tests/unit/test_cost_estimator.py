from decimal import Decimal

from competitor_scout.agents.costs import ConfiguredCostEstimator
from competitor_scout.config import Settings


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
        estimated_main_request_cost_usd=Decimal("0.12"),
        estimated_child_request_cost_usd=Decimal("0.04"),
    )


def test_configured_estimator_is_conservative_and_model_specific() -> None:
    configured = settings()
    estimator = ConfiguredCostEstimator(configured)

    assert estimator(configured.otari_main_model, 4000, False) == Decimal("0.12")
    assert estimator(configured.otari_child_model, 3000, True) == Decimal("0.04")
    assert estimator("unknown-model", 1, False) == Decimal("0.12")
