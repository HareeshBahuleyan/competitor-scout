from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.db import SessionFactory
from competitor_scout.models.jobs import Job, JobStatus

type Clock = Callable[[], datetime]
type AfterClaimLock = Callable[[], Awaitable[None]]


class LeaseOwnershipError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


def json_safe_payload(payload: dict[str, object]) -> dict[str, object]:
    try:
        serialized = json.dumps(payload, allow_nan=False)
        decoded = json.loads(serialized)
    except (TypeError, ValueError) as error:
        raise ValueError("job payload must contain only JSON-safe values") from error
    if not isinstance(decoded, dict):
        raise ValueError("job payload must be a JSON object")
    return decoded


async def enqueue_in_session(
    session: AsyncSession,
    job_type: str,
    deduplication_key: str,
    payload: dict[str, object],
    *,
    available_at: datetime,
) -> Job:
    """Idempotently enqueue within the caller's existing transaction."""

    if available_at.tzinfo is None:
        raise ValueError("available_at must be timezone-aware")
    statement = (
        insert(Job)
        .values(
            job_type=job_type,
            deduplication_key=deduplication_key,
            payload=json_safe_payload(payload),
            available_at=available_at.astimezone(UTC),
        )
        .on_conflict_do_nothing(index_elements=[Job.deduplication_key])
        .returning(Job)
    )
    job = (await session.scalars(statement)).one_or_none()
    if job is None:
        job = await session.scalar(
            select(Job).where(Job.deduplication_key == deduplication_key)
        )
    if job is None:
        raise RuntimeError("idempotent job enqueue did not resolve a row")
    return job


class JobRepository:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        now: Clock = utc_now,
        after_claim_lock: AfterClaimLock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._now = now
        self._after_claim_lock = after_claim_lock

    def _current_time(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    async def enqueue(
        self,
        job_type: str,
        deduplication_key: str,
        payload: dict[str, object],
        *,
        available_at: datetime | None = None,
    ) -> Job:
        safe_payload = json_safe_payload(payload)
        scheduled_at = available_at or self._current_time()
        if scheduled_at.tzinfo is None:
            raise ValueError("available_at must be timezone-aware")
        async with self._session_factory.begin() as session:
            return await enqueue_in_session(
                session,
                job_type,
                deduplication_key,
                safe_payload,
                available_at=scheduled_at,
            )

    async def claim(self, lease_owner: str, *, lease_seconds: int) -> Job | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = self._current_time()
        async with self._session_factory.begin() as session:
            job = await session.scalar(
                select(Job)
                .where(
                    or_(
                        (Job.status == JobStatus.QUEUED) & (Job.available_at <= now),
                        (Job.status == JobStatus.LEASED) & (Job.lease_expires_at <= now),
                    )
                )
                .order_by(Job.available_at, Job.created_at, Job.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            if self._after_claim_lock is not None:
                await self._after_claim_lock()
            job.status = JobStatus.LEASED
            job.lease_owner = lease_owner
            job.lease_expires_at = now + timedelta(seconds=lease_seconds)
            job.attempt_count += 1
            return job

    async def renew(
        self,
        job_id: uuid.UUID,
        lease_owner: str,
        *,
        lease_seconds: int,
    ) -> Job:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = self._current_time()
        return await self._owned_update(
            job_id,
            lease_owner,
            now=now,
            values={"lease_expires_at": now + timedelta(seconds=lease_seconds)},
        )

    async def complete(self, job_id: uuid.UUID, lease_owner: str) -> Job:
        return await self._owned_update(
            job_id,
            lease_owner,
            now=self._current_time(),
            values={
                "status": JobStatus.COMPLETED,
                "lease_owner": None,
                "lease_expires_at": None,
            },
        )

    async def fail(
        self,
        job_id: uuid.UUID,
        lease_owner: str,
        *,
        error_code: str,
    ) -> Job:
        return await self._owned_update(
            job_id,
            lease_owner,
            now=self._current_time(),
            values={
                "status": JobStatus.FAILED,
                "lease_owner": None,
                "lease_expires_at": None,
                "last_error_code": error_code,
            },
        )

    async def _owned_update(
        self,
        job_id: uuid.UUID,
        lease_owner: str,
        *,
        now: datetime,
        values: dict[str, object],
    ) -> Job:
        statement = (
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == JobStatus.LEASED,
                Job.lease_owner == lease_owner,
                Job.lease_expires_at > now,
            )
            .values(**values)
            .returning(Job)
        )
        async with self._session_factory.begin() as session:
            job = (await session.scalars(statement)).one_or_none()
            if job is None:
                raise LeaseOwnershipError("job lease is not owned by this worker")
            return job
