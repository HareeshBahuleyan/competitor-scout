from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from competitor_scout.db import SessionFactory
from competitor_scout.jobs.repository import enqueue_in_session
from competitor_scout.models.auth import User
from competitor_scout.models.notifications import NotificationOutbox, NotificationStatus
from competitor_scout.notifications.email import EmailSender, render_notification_email

RETRY_DELAYS = (timedelta(seconds=60), timedelta(seconds=300))
MAX_ATTEMPTS = 3


class NotificationHandler:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        sender: EmailSender,
        public_base_url: str,
        now=lambda: datetime.now(UTC),
    ) -> None:
        self._sessions = session_factory
        self._sender = sender
        self._public_base_url = public_base_url
        self._now = now

    async def handle(self, *, outbox_id: uuid.UUID) -> None:
        now = self._current_time()
        async with self._sessions.begin() as session:
            outbox = await session.scalar(
                select(NotificationOutbox)
                .where(NotificationOutbox.id == outbox_id)
                .with_for_update()
            )
            if outbox is None:
                raise ValueError("notification outbox row was not found")
            if outbox.status in {NotificationStatus.SENT, NotificationStatus.FAILED}:
                return
            user = await session.get(User, outbox.user_id)
            if user is None or user.disabled_at is not None:
                outbox.status = NotificationStatus.FAILED
                outbox.failed_at = now
                outbox.last_error_code = "notification_user_unavailable"
                return
            outbox.attempt_count += 1
            attempt = outbox.attempt_count
            recipient = user.email
            notification_type = outbox.notification_type
            payload = dict(outbox.payload)
            idempotency_key = outbox.deduplication_key

        subject, text, html = render_notification_email(
            notification_type,
            payload,
            public_base_url=self._public_base_url,
        )
        try:
            await self._sender.send(
                recipient=recipient,
                subject=subject,
                text=text,
                html=html,
                idempotency_key=idempotency_key,
            )
        except Exception as error:
            await self._record_failure(outbox_id, attempt, error, self._current_time())
            return

        async with self._sessions.begin() as session:
            outbox = await session.scalar(
                select(NotificationOutbox)
                .where(NotificationOutbox.id == outbox_id)
                .with_for_update()
            )
            if outbox is not None and outbox.status is NotificationStatus.PENDING:
                outbox.status = NotificationStatus.SENT
                outbox.sent_at = self._current_time()
                outbox.last_error_code = None

    async def _record_failure(
        self,
        outbox_id: uuid.UUID,
        attempt: int,
        error: Exception,
        failed_at: datetime,
    ) -> None:
        code = getattr(error, "code", None)
        safe_code = code if isinstance(code, str) and len(code) <= 100 else "email_delivery_failed"
        async with self._sessions.begin() as session:
            outbox = await session.scalar(
                select(NotificationOutbox)
                .where(NotificationOutbox.id == outbox_id)
                .with_for_update()
            )
            if outbox is None or outbox.status is not NotificationStatus.PENDING:
                return
            outbox.last_error_code = safe_code
            if attempt >= MAX_ATTEMPTS or getattr(error, "retryable", True) is False:
                outbox.status = NotificationStatus.FAILED
                outbox.failed_at = failed_at
                return
            next_attempt = attempt + 1
            await enqueue_in_session(
                session,
                "email_notification",
                f"email_notification:{outbox.id}:attempt:{next_attempt}",
                {"outbox_id": str(outbox.id)},
                available_at=failed_at + RETRY_DELAYS[attempt - 1],
            )

    def _current_time(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ValueError("notification clock must be timezone-aware")
        return value.astimezone(UTC)
