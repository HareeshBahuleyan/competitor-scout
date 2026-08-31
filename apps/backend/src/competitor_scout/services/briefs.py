from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.models.briefs import WeeklyBrief


@dataclass(frozen=True)
class BriefPage:
    items: list[WeeklyBrief]
    next_cursor: str | None


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
