from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import case, func, select

from competitor_scout.api.deps import CsrfRequired, CurrentUser, DbSession
from competitor_scout.models.auth import User
from competitor_scout.models.intelligence import UsageEvent
from competitor_scout.schemas.settings import (
    UsageSummary,
    UsageSummaryRow,
    UserSettingsRead,
    UserSettingsUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["settings"])


def settings_response(user: User, *, email_delivery_available: bool) -> UserSettingsRead:
    return UserSettingsRead(
        display_name=user.display_name,
        timezone=user.timezone,
        default_daily_time=user.default_daily_run_time_local,
        email_findings_enabled=user.email_findings_enabled,
        email_weekly_brief_enabled=user.email_weekly_brief_enabled,
        email_delivery_available=email_delivery_available,
    )


@router.get("/settings", response_model=UserSettingsRead)
async def get_settings_route(request: Request, user: CurrentUser) -> UserSettingsRead:
    return settings_response(
        user, email_delivery_available=request.app.state.settings.email_delivery_enabled
    )


@router.patch("/settings", response_model=UserSettingsRead)
async def update_settings_route(
    payload: UserSettingsUpdate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    _csrf: CsrfRequired,
) -> UserSettingsRead:
    changes = payload.model_dump(exclude_unset=True)
    default_daily_time = changes.pop("default_daily_time", None)
    for field, value in changes.items():
        setattr(user, field, value)
    if default_daily_time is not None:
        user.default_daily_run_time_local = default_daily_time
    await db.flush()
    await db.refresh(user)
    return settings_response(
        user, email_delivery_available=request.app.state.settings.email_delivery_enabled
    )


@router.get("/usage/summary", response_model=UsageSummary)
async def usage_summary_route(db: DbSession, user: CurrentUser) -> UsageSummary:
    utc_date = func.date(func.timezone("UTC", UsageEvent.occurred_at))
    row_count = func.count()
    tool_calls = case(
        (row_count == func.count(UsageEvent.tool_calls), func.sum(UsageEvent.tool_calls)),
        else_=None,
    )
    settled_cost = case(
        (
            row_count == func.count(UsageEvent.settled_cost_usd),
            func.sum(UsageEvent.settled_cost_usd),
        ),
        else_=None,
    )
    rows = (
        await db.execute(
            select(
                utc_date.label("date"),
                UsageEvent.model,
                func.sum(UsageEvent.input_tokens).label("input_tokens"),
                func.sum(UsageEvent.output_tokens).label("output_tokens"),
                tool_calls.label("tool_calls"),
                settled_cost.label("settled_cost_usd"),
            )
            .where(UsageEvent.user_id == user.id)
            .group_by(utc_date, UsageEvent.model)
            .order_by(utc_date.desc(), UsageEvent.model)
        )
    ).all()
    return UsageSummary(items=[UsageSummaryRow.model_validate(row._mapping) for row in rows])
