from decimal import Decimal

import pytest
from pydantic import ValidationError

from competitor_scout.config import Settings


def valid_values() -> dict[str, object]:
    return {
        "environment": "local",
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "public_base_url": "https://scout.example.com",
        "session_secret": "s" * 32,
        "csrf_secret": "c" * 32,
        "google_client_id": "google-id",
        "google_client_secret": "google-secret",
        "otari_base_url": "https://api.otari.example",
        "otari_ai_token": "otari-token",
    }


@pytest.mark.parametrize("field", ["session_secret", "csrf_secret"])
def test_settings_reject_short_secrets(field: str) -> None:
    values = valid_values() | {field: "short"}

    with pytest.raises(ValidationError):
        Settings(**values)


def test_operational_defaults_are_bounded() -> None:
    settings = Settings(**valid_values())

    assert settings.max_active_users == 10
    assert settings.max_active_competitors == 10
    assert settings.max_child_tasks_per_run == 8
    assert settings.max_concurrent_child_tasks == 4
    assert settings.max_child_search_calls == 4
    assert settings.max_source_discovery_search_calls == 8
    assert settings.main_input_token_limit == 32_000
    assert settings.main_output_token_limit == 4_000
    assert settings.child_input_token_limit == 16_000
    assert settings.child_output_token_limit == 3_000
    assert settings.planning_deadline_seconds == 60
    assert settings.child_deadline_seconds == 120
    assert settings.synthesis_deadline_seconds == 90
    assert settings.max_planning_repairs == 1
    assert settings.max_synthesis_repairs == 1
    assert settings.max_child_retries == 1
    assert settings.max_otari_concurrency == 8


def test_otari_models_use_suffix_free_environment_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTARI_MAIN_MODEL", "configured-main-model")
    monkeypatch.setenv("OTARI_CHILD_MODEL", "configured-child-model")

    settings = Settings(**valid_values())

    assert settings.otari_main_model == "configured-main-model"
    assert settings.otari_child_model == "configured-child-model"


def test_cost_limits_use_decimal_values() -> None:
    settings = Settings(**valid_values())

    assert settings.max_run_cost_usd == Decimal("2.25")
    assert settings.max_user_daily_cost_usd == Decimal("5.00")
    assert isinstance(settings.max_run_cost_usd, Decimal)


def test_active_user_limit_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(**(valid_values() | {"max_active_users": 0}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_child_search_calls", 0),
        ("max_source_discovery_search_calls", 0),
        ("max_source_discovery_search_calls", 25),
    ],
)
def test_search_budgets_are_bounded(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(**(valid_values() | {field: value}))


def test_otari_ai_token_is_required() -> None:
    values = valid_values()
    values.pop("otari_ai_token")

    with pytest.raises(ValidationError, match="otari_ai_token"):
        Settings(**(values | {"otari_ai_token": None}))


def test_e2e_auth_secret_is_rejected_outside_test() -> None:
    with pytest.raises(ValidationError, match="E2E_AUTH_SECRET"):
        Settings(**(valid_values() | {"e2e_auth_secret": "test-only-secret"}))


def test_e2e_auth_secret_is_allowed_in_test() -> None:
    settings = Settings(
        **(valid_values() | {"environment": "test", "e2e_auth_secret": "test-only-secret"})
    )

    assert settings.e2e_auth_secret is not None
