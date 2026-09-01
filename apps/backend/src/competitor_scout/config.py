from decimal import Decimal
from functools import lru_cache
from typing import Literal, Self

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        extra="ignore",
        validate_default=True,
    )

    environment: Literal["local", "test", "production"] = "local"
    database_url: str
    public_base_url: AnyHttpUrl
    web_internal_api_url: AnyHttpUrl = "http://localhost:8000"
    session_cookie_name: str = "competitor_scout_session"
    session_secret: SecretStr = Field(min_length=32)
    csrf_secret: SecretStr = Field(min_length=32)
    google_client_id: str
    google_client_secret: SecretStr
    otari_base_url: AnyHttpUrl
    otari_ai_token: SecretStr = Field(min_length=1)
    otari_main_model: str = "competitor-scout-main"
    otari_child_model: str = "competitor-scout-child"

    max_active_users: int = Field(default=10, ge=1, le=100)
    max_active_competitors: int = Field(default=10, ge=1, le=100)
    max_child_tasks_per_run: int = Field(default=8, ge=1, le=20)
    max_concurrent_child_tasks: int = Field(default=4, ge=1, le=10)
    max_child_search_calls: int = Field(default=2, ge=1, le=10)
    main_input_token_limit: int = Field(default=32_000, ge=1, le=1_000_000)
    main_output_token_limit: int = Field(default=4_000, ge=1, le=100_000)
    child_input_token_limit: int = Field(default=16_000, ge=1, le=1_000_000)
    child_output_token_limit: int = Field(default=3_000, ge=1, le=100_000)
    planning_deadline_seconds: int = Field(default=60, ge=1, le=900)
    child_deadline_seconds: int = Field(default=120, ge=1, le=900)
    synthesis_deadline_seconds: int = Field(default=90, ge=1, le=900)
    max_planning_repairs: int = Field(default=1, ge=0, le=1)
    max_synthesis_repairs: int = Field(default=1, ge=0, le=1)
    max_child_retries: int = Field(default=1, ge=0, le=1)
    max_otari_concurrency: int = Field(default=8, ge=1, le=100)
    max_run_cost_usd: Decimal = Field(default=Decimal("2.25"), gt=0)
    max_user_daily_cost_usd: Decimal = Field(default=Decimal("5.00"), gt=0)
    estimated_main_request_cost_usd: Decimal = Field(default=Decimal("0.20"), gt=0)
    estimated_child_request_cost_usd: Decimal = Field(default=Decimal("0.10"), gt=0)
    estimated_web_search_cost_usd: Decimal = Field(default=Decimal("0.10"), ge=0)
    finding_confidence_threshold: float = Field(default=0.70, ge=0, le=1)
    e2e_auth_secret: SecretStr | None = None

    @field_validator("e2e_auth_secret", mode="before")
    @classmethod
    def empty_e2e_secret_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def reject_e2e_secret_outside_test(self) -> Self:
        if self.e2e_auth_secret is not None and self.environment != "test":
            raise ValueError("E2E_AUTH_SECRET may only be set when ENVIRONMENT=test")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
