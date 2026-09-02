from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from competitor_scout.jobs.notifications import NotificationHandler
from competitor_scout.models.auth import User
from competitor_scout.models.jobs import Job
from competitor_scout.models.notifications import NotificationOutbox, NotificationStatus
from competitor_scout.notifications.email import EmailDeliveryError

NOW = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


class FakeSender:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[dict[str, str]] = []

    async def send(self, **kwargs: str) -> None:
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures:
            raise EmailDeliveryError()


@pytest_asyncio.fixture
async def notification_store(migrated_database_url: str):
    engine = create_async_engine(migrated_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield sessions
    finally:
        async with sessions.begin() as session:
            await session.execute(
                delete(Job).where(Job.deduplication_key.like("email_notification:%"))
            )
            await session.execute(delete(NotificationOutbox))
            await session.execute(delete(User).where(User.email.like("notify-%")))
        await engine.dispose()


async def seed_outbox(sessions) -> uuid.UUID:
    async with sessions.begin() as session:
        user = User(email=f"notify-{uuid.uuid4().hex}@example.com", display_name="Owner")
        session.add(user)
        await session.flush()
        outbox = NotificationOutbox(
            user_id=user.id,
            notification_type="weekly_brief_email",
            deduplication_key=f"email:brief:{uuid.uuid4()}",
            payload={
                "brief_id": str(uuid.uuid4()),
                "title": "Weekly brief",
                "executive_summary": "No material changes this week.",
                "period_start": "2026-08-24",
                "period_end": "2026-08-30",
            },
        )
        session.add(outbox)
        await session.flush()
        return outbox.id


async def test_handler_marks_sent_and_already_sent_is_a_no_op(notification_store) -> None:
    outbox_id = await seed_outbox(notification_store)
    sender = FakeSender()
    handler = NotificationHandler(
        notification_store, sender=sender, public_base_url="https://scout.example", now=lambda: NOW
    )

    await handler.handle(outbox_id=outbox_id)
    await handler.handle(outbox_id=outbox_id)

    async with notification_store() as session:
        outbox = await session.get(NotificationOutbox, outbox_id)
        assert outbox is not None
        assert outbox.status is NotificationStatus.SENT
        assert outbox.attempt_count == 1
        assert outbox.sent_at == NOW
    assert len(sender.calls) == 1
    assert sender.calls[0]["idempotency_key"].startswith("email:brief:")


async def test_handler_schedules_two_bounded_retries_then_fails(notification_store) -> None:
    outbox_id = await seed_outbox(notification_store)
    sender = FakeSender(failures=3)
    handler = NotificationHandler(
        notification_store, sender=sender, public_base_url="https://scout.example", now=lambda: NOW
    )

    await handler.handle(outbox_id=outbox_id)
    await handler.handle(outbox_id=outbox_id)
    await handler.handle(outbox_id=outbox_id)

    async with notification_store() as session:
        outbox = await session.get(NotificationOutbox, outbox_id)
        assert outbox is not None
        assert outbox.status is NotificationStatus.FAILED
        assert outbox.attempt_count == 3
        assert outbox.failed_at == NOW
        job_filter = Job.deduplication_key.like(f"email_notification:{outbox_id}:%")
        assert await session.scalar(select(func.count(Job.id)).where(job_filter)) == 2
        keys = set((await session.scalars(select(Job.deduplication_key).where(job_filter))).all())
        assert keys == {
            f"email_notification:{outbox_id}:attempt:2",
            f"email_notification:{outbox_id}:attempt:3",
        }
    assert len({call["idempotency_key"] for call in sender.calls}) == 1
