from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class UserSettingsRead(BaseModel):
    display_name: str
    timezone: str
    default_daily_time: time
    email_findings_enabled: bool
    email_weekly_brief_enabled: bool
    email_delivery_available: bool


class UserSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    default_daily_time: time | None = None
    email_findings_enabled: StrictBool | None = None
    email_weekly_brief_enabled: StrictBool | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("display_name must not be null")
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_name must not be empty")
        return normalized

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("timezone must not be null")
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("timezone must be a valid IANA timezone") from None
        return value

    @field_validator("default_daily_time")
    @classmethod
    def daily_time_must_be_local(cls, value: time | None) -> time | None:
        if value is None:
            raise ValueError("default_daily_time must not be null")
        if value.tzinfo is not None:
            raise ValueError("default_daily_time must be a local time")
        return value

    @field_validator("email_findings_enabled", "email_weekly_brief_enabled")
    @classmethod
    def email_preferences_must_not_be_null(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("email preferences must not be null")
        return value


class UsageSummaryRow(BaseModel):
    date: date
    model: str
    input_tokens: int
    output_tokens: int
    tool_calls: int | None
    settled_cost_usd: Decimal | None


class UsageSummary(BaseModel):
    items: list[UsageSummaryRow]
