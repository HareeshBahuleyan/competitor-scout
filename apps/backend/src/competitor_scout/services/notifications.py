from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.jobs.repository import enqueue_in_session, json_safe_payload
from competitor_scout.models.notifications import NotificationOutbox


def finding_email_key(finding_id: uuid.UUID) -> str:
    return f"email:finding:{finding_id}"


def brief_email_key(brief_id: uuid.UUID) -> str:
    return f"email:brief:{brief_id}"


async def enqueue_email_notification(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    notification_type: str,
    deduplication_key: str,
    payload: dict[str, object],
    available_at: datetime,
) -> NotificationOutbox:
    if available_at.tzinfo is None:
        raise ValueError("notification time must be timezone-aware")
    safe_payload = json_safe_payload(payload)
    statement = (
        insert(NotificationOutbox)
        .values(
            user_id=user_id,
            notification_type=notification_type,
            deduplication_key=deduplication_key,
            payload=safe_payload,
        )
        .on_conflict_do_nothing(index_elements=[NotificationOutbox.deduplication_key])
        .returning(NotificationOutbox)
    )
    outbox = (await session.scalars(statement)).one_or_none()
    inserted = outbox is not None
    if outbox is None:
        outbox = await session.scalar(
            select(NotificationOutbox).where(
                NotificationOutbox.deduplication_key == deduplication_key
            )
        )
    if outbox is None:
        raise RuntimeError("notification outbox enqueue did not resolve a row")
    if inserted:
        await enqueue_in_session(
            session,
            "email_notification",
            f"email_notification:{outbox.id}:attempt:1",
            {"outbox_id": str(outbox.id)},
            available_at=available_at.astimezone(UTC),
        )
    return outbox
