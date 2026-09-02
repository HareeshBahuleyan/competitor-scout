from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.jobs.scheduler import (
    WEEKLY_RUN_TIME_LOCAL,
    WEEKLY_RUN_WEEKDAY,
    first_valid_local_occurrence,
)
from competitor_scout.models.briefs import WeeklyBrief
from competitor_scout.models.intelligence import (
    ApprovalStatus,
    Competitor,
    CompetitorStatus,
    MonitoredSource,
    RunType,
    ScoutRun,
    ScoutRunStatus,
)
from competitor_scout.models.snapshots import CompetitorStartingSnapshot
from competitor_scout.schemas.briefs import (
    BriefRead,
    DigestCompetitorLink,
    DigestOverview,
    DigestRunningScan,
    DigestSnapshotLink,
)


@dataclass(frozen=True)
class BriefPage:
    items: list[WeeklyBrief]
    next_cursor: str | None


def next_weekly_generation(now: datetime, timezone_name: str) -> datetime:
    if now.tzinfo is None:
        raise ValueError("digest overview clock must be timezone-aware")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("user timezone is invalid") from error
    current = now.astimezone(UTC)
    local_now = current.astimezone(zone)
    days_ahead = (WEEKLY_RUN_WEEKDAY - local_now.weekday()) % 7
    schedule_date = local_now.date() + timedelta(days=days_ahead)
    candidate = first_valid_local_occurrence(
        schedule_date,
        WEEKLY_RUN_TIME_LOCAL,
        timezone_name,
    ).astimezone(UTC)
    if candidate < current:
        candidate = first_valid_local_occurrence(
            schedule_date + timedelta(days=7),
            WEEKLY_RUN_TIME_LOCAL,
            timezone_name,
        ).astimezone(UTC)
    return candidate


async def digest_overview(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    timezone_name: str,
    now: datetime | None = None,
) -> DigestOverview:
    current = now or datetime.now(UTC)
    latest = await db.scalar(
        select(WeeklyBrief)
        .where(WeeklyBrief.user_id == user_id)
        .order_by(WeeklyBrief.published_at.desc(), WeeklyBrief.id.desc())
        .limit(1)
    )
    competitors = list(
        (
            await db.scalars(
                select(Competitor)
                .where(
                    Competitor.user_id == user_id,
                    Competitor.status != CompetitorStatus.DELETED,
                )
                .order_by(Competitor.updated_at.desc(), Competitor.id.desc())
            )
        ).all()
    )
    active = [item for item in competitors if item.status is CompetitorStatus.ACTIVE]
    incomplete = next(
        (
            item
            for item in competitors
            if item.status in {CompetitorStatus.DISCOVERING, CompetitorStatus.PAUSED}
        ),
        None,
    )
    approved_source_count = int(
        await db.scalar(
            select(func.count(MonitoredSource.id))
            .join(Competitor, Competitor.id == MonitoredSource.competitor_id)
            .where(
                Competitor.user_id == user_id,
                Competitor.status == CompetitorStatus.ACTIVE,
                MonitoredSource.approval_status == ApprovalStatus.APPROVED,
            )
        )
        or 0
    )
    running_row = (
        await db.execute(
            select(ScoutRun, Competitor)
            .join(Competitor, Competitor.id == ScoutRun.competitor_id)
            .where(
                ScoutRun.user_id == user_id,
                ScoutRun.run_type.in_([RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT]),
                ScoutRun.status.in_(
                    [
                        ScoutRunStatus.QUEUED,
                        ScoutRunStatus.PLANNING,
                        ScoutRunStatus.GATHERING,
                        ScoutRunStatus.SYNTHESIZING,
                    ]
                ),
                Competitor.starting_snapshot_requested_at.is_not(None),
                ~select(CompetitorStartingSnapshot.id)
                .where(CompetitorStartingSnapshot.competitor_id == Competitor.id)
                .exists(),
            )
            .order_by(ScoutRun.created_at.desc(), ScoutRun.id.desc())
            .limit(1)
        )
    ).one_or_none()
    snapshot_rows = (
        await db.execute(
            select(CompetitorStartingSnapshot, Competitor)
            .join(Competitor, Competitor.id == CompetitorStartingSnapshot.competitor_id)
            .where(
                CompetitorStartingSnapshot.user_id == user_id,
                Competitor.status != CompetitorStatus.DELETED,
            )
            .order_by(
                CompetitorStartingSnapshot.published_at.desc(),
                CompetitorStartingSnapshot.id.desc(),
            )
        )
    ).all()
    monitoring_issue_count = int(
        await db.scalar(
            select(func.count(func.distinct(ScoutRun.competitor_id)))
            .join(Competitor, Competitor.id == ScoutRun.competitor_id)
            .where(
                ScoutRun.user_id == user_id,
                Competitor.status == CompetitorStatus.ACTIVE,
                ScoutRun.run_type.in_([RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT]),
                ScoutRun.status.in_([ScoutRunStatus.PARTIAL, ScoutRunStatus.FAILED]),
            )
        )
        or 0
    )

    if latest is not None:
        state = "archive_available"
    elif not competitors:
        state = "setup_required"
    elif running_row is not None and len(active) == 1:
        state = "initial_scan_running"
    elif active:
        state = "awaiting_first_digest"
    else:
        state = "setup_incomplete"

    running_scan = None
    if running_row is not None:
        run, competitor = running_row
        running_scan = DigestRunningScan(
            run_id=run.id,
            competitor_id=competitor.id,
            competitor_name=competitor.name,
            status=run.status.value,
        )
    incomplete_link = None
    if incomplete is not None:
        incomplete_link = DigestCompetitorLink(
            competitor_id=incomplete.id,
            competitor_name=incomplete.name,
            status=incomplete.status.value,
        )
    snapshots = [
        DigestSnapshotLink(
            snapshot_id=snapshot.id,
            competitor_id=competitor.id,
            competitor_name=competitor.name,
        )
        for snapshot, competitor in snapshot_rows
    ]
    return DigestOverview(
        state=state,
        next_digest_at=(next_weekly_generation(current, timezone_name) if active else None),
        active_competitor_count=len(active),
        approved_source_count=approved_source_count,
        incomplete_competitor=incomplete_link,
        running_scan=running_scan,
        snapshots=snapshots,
        monitoring_issue_count=monitoring_issue_count,
        latest_brief=BriefRead.model_validate(latest) if latest is not None else None,
    )


def _encode_cursor(published_at: datetime, brief_id: uuid.UUID) -> str:
    payload = json.dumps([published_at.astimezone(UTC).isoformat(), str(brief_id)]).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw_time, raw_id = json.loads(base64.urlsafe_b64decode(padded).decode())
        published_at = datetime.fromisoformat(raw_time)
        if published_at.tzinfo is None:
            raise ValueError
        return published_at.astimezone(UTC), uuid.UUID(raw_id)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid cursor") from error


async def list_briefs(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> BriefPage:
    statement = select(WeeklyBrief).where(WeeklyBrief.user_id == user_id)
    if cursor is not None:
        published_at, brief_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                WeeklyBrief.published_at < published_at,
                (WeeklyBrief.published_at == published_at) & (WeeklyBrief.id < brief_id),
            )
        )
    records = list(
        (
            await db.scalars(
                statement.order_by(
                    WeeklyBrief.published_at.desc(),
                    WeeklyBrief.id.desc(),
                ).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(records) > limit
    items = records[:limit]
    next_cursor = _encode_cursor(items[-1].published_at, items[-1].id) if has_more else None
    return BriefPage(items=items, next_cursor=next_cursor)


async def owned_brief(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    brief_id: uuid.UUID,
) -> WeeklyBrief | None:
    return await db.scalar(
        select(WeeklyBrief).where(
            WeeklyBrief.id == brief_id,
            WeeklyBrief.user_id == user_id,
        )
    )
