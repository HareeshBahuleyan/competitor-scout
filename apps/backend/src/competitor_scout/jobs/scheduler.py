from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.jobs.repository import enqueue_in_session
from competitor_scout.models.auth import User
from competitor_scout.models.intelligence import (
    Competitor,
    CompetitorStatus,
    RunType,
    ScoutRun,
    ScoutRunStatus,
)

WEEKLY_RUN_WEEKDAY = 0  # Monday
WEEKLY_RUN_TIME_LOCAL = time(8, 0)


def daily_deduplication_key(competitor_id: str, local_date: date) -> str:
    return f"daily_scout:{competitor_id}:{local_date.isoformat()}"


def weekly_deduplication_key(user_id: str, period_end: date) -> str:
    return f"weekly_brief:{user_id}:{period_end.isoformat()}"


def first_valid_local_occurrence(
    local_date: date,
    local_time: time,
    timezone_name: str,
) -> datetime:
    """Return fold zero, advancing through a DST gap to its first valid minute."""

    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("user timezone is invalid") from error
    naive = datetime.combine(local_date, local_time.replace(tzinfo=None))
    for offset in range(181):
        wall = naive + timedelta(minutes=offset)
        candidate = wall.replace(tzinfo=zone, fold=0)
        round_trip = candidate.astimezone(UTC).astimezone(zone)
        if round_trip.replace(tzinfo=None) == wall and round_trip.fold == 0:
            return candidate
    raise ValueError("configured local run time has no valid occurrence")


async def schedule_due_daily_runs(
    session: AsyncSession,
    *,
    now: datetime,
) -> list[ScoutRun]:
    if now.tzinfo is None:
        raise ValueError("scheduler clock must be timezone-aware")
    current = now.astimezone(UTC)
    rows = (
        await session.execute(
            select(Competitor, User)
            .join(User, User.id == Competitor.user_id)
            .where(
                Competitor.status == CompetitorStatus.ACTIVE,
                User.disabled_at.is_(None),
            )
        )
    ).all()
    scheduled: list[ScoutRun] = []
    for competitor, user in rows:
        try:
            zone = ZoneInfo(user.timezone)
            local_date = current.astimezone(zone).date()
            scheduled_for = first_valid_local_occurrence(
                local_date,
                competitor.daily_run_time_local,
                user.timezone,
            ).astimezone(UTC)
        except ValueError:
            continue
        if scheduled_for > current:
            continue

        statement = (
            insert(ScoutRun)
            .values(
                id=uuid.uuid4(),
                user_id=user.id,
                competitor_id=competitor.id,
                run_type=RunType.DAILY_SCOUT,
                status=ScoutRunStatus.QUEUED,
                scheduled_for=scheduled_for,
            )
            .on_conflict_do_nothing()
            .returning(ScoutRun)
        )
        run = (await session.scalars(statement)).one_or_none()
        if run is None:
            run = await session.scalar(
                select(ScoutRun).where(
                    ScoutRun.run_type == RunType.DAILY_SCOUT,
                    ScoutRun.competitor_id == competitor.id,
                    ScoutRun.scheduled_for == scheduled_for,
                )
            )
        if run is None:
            continue
        await enqueue_in_session(
            session,
            "daily_scout",
            daily_deduplication_key(str(competitor.id), local_date),
            {"run_id": str(run.id)},
            available_at=scheduled_for,
        )
        scheduled.append(run)
    return scheduled


async def schedule_due_weekly_briefs(
    session: AsyncSession,
    *,
    now: datetime,
) -> list[ScoutRun]:
    """Schedule the prior Monday-Sunday brief each Monday at 08:00 user-local time."""

    if now.tzinfo is None:
        raise ValueError("scheduler clock must be timezone-aware")
    current = now.astimezone(UTC)
    users = list((await session.scalars(select(User).where(User.disabled_at.is_(None)))).all())
    scheduled: list[ScoutRun] = []
    for user in users:
        try:
            zone = ZoneInfo(user.timezone)
            local_now = current.astimezone(zone)
            days_since_schedule = (local_now.weekday() - WEEKLY_RUN_WEEKDAY) % 7
            local_schedule_date = local_now.date() - timedelta(days=days_since_schedule)
            scheduled_for = first_valid_local_occurrence(
                local_schedule_date,
                WEEKLY_RUN_TIME_LOCAL,
                user.timezone,
            ).astimezone(UTC)
        except ValueError:
            continue
        if scheduled_for > current:
            continue

        period_start = datetime.combine(
            local_schedule_date - timedelta(days=7),
            time.min,
            tzinfo=zone,
        ).astimezone(UTC)
        period_end_exclusive = datetime.combine(
            local_schedule_date,
            time.min,
            tzinfo=zone,
        ).astimezone(UTC)
        scout_activity = await session.scalar(
            select(ScoutRun.id)
            .where(
                ScoutRun.user_id == user.id,
                ScoutRun.run_type.in_([RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT]),
                ScoutRun.scheduled_for >= period_start,
                ScoutRun.scheduled_for < period_end_exclusive,
            )
            .limit(1)
        )
        if scout_activity is None:
            continue

        statement = (
            insert(ScoutRun)
            .values(
                id=uuid.uuid4(),
                user_id=user.id,
                competitor_id=None,
                run_type=RunType.WEEKLY_BRIEF,
                status=ScoutRunStatus.QUEUED,
                scheduled_for=scheduled_for,
            )
            .on_conflict_do_nothing()
            .returning(ScoutRun)
        )
        run = (await session.scalars(statement)).one_or_none()
        if run is None:
            run = await session.scalar(
                select(ScoutRun).where(
                    ScoutRun.run_type == RunType.WEEKLY_BRIEF,
                    ScoutRun.user_id == user.id,
                    ScoutRun.scheduled_for == scheduled_for,
                )
            )
        if run is None:
            continue

        period_end = local_schedule_date - timedelta(days=1)
        await enqueue_in_session(
            session,
            "weekly_brief",
            weekly_deduplication_key(str(user.id), period_end),
            {"run_id": str(run.id)},
            available_at=scheduled_for,
        )
        scheduled.append(run)
    return scheduled
