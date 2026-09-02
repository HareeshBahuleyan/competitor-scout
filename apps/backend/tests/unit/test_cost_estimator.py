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
        otari_main_model="general-mzai-then-openai-models",
        otari_child_model="general-mzai-then-openai-models",
        estimated_main_request_cost_usd=Decimal("0.12"),
        estimated_child_request_cost_usd=Decimal("0.04"),
    )


def test_configured_estimator_is_conservative_and_role_specific() -> None:
    configured = settings()
    estimator = ConfiguredCostEstimator(configured)

    assert configured.otari_main_model == configured.otari_child_model
    assert estimator("main") == Decimal("0.12")
    assert estimator("child") == Decimal("0.04")
