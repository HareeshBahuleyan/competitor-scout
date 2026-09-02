from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserSettingsRead(BaseModel):
    display_name: str
    timezone: str
    default_daily_time: time


class UserSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    default_daily_time: time | None = None

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


class UsageSummaryRow(BaseModel):
    date: date
    model: str
    input_tokens: int
    output_tokens: int
    settled_cost_usd: Decimal | None


class UsageSummary(BaseModel):
    items: list[UsageSummaryRow]
