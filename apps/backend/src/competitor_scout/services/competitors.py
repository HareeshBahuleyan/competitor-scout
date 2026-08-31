from __future__ import annotations

import base64
import ipaddress
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.models.intelligence import (
    ApprovalStatus,
    Competitor,
    CompetitorStatus,
    MonitoredSource,
)
from competitor_scout.security.urls import UnsafeSourceUrl, same_registrable_domain

type SourceUrlValidator = Callable[[str], Awaitable[str]]


class CompetitorLimitReached(ValueError):
    pass


class DuplicateCompetitor(ValueError):
    pass


class InvalidPrimaryDomain(ValueError):
    pass


class CompetitorActivationNotAllowed(ValueError):
    pass


class SourceUrlNotAllowed(ValueError):
    pass


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None


def ensure_competitor_capacity(*, active_count: int, limit: int) -> None:
    if active_count >= limit:
        raise CompetitorLimitReached(f"active competitor limit of {limit} reached")


def normalize_primary_domain(value: str) -> str:
    stripped = value.strip()
    if not stripped or "\\" in stripped or any(character.isspace() for character in stripped):
        raise InvalidPrimaryDomain("primary domain is invalid")

    has_scheme = "://" in stripped
    candidate = stripped if has_scheme else f"//{stripped}"
    try:
        parsed = urlsplit(candidate)
        scheme = parsed.scheme.casefold()
        port = parsed.port
    except ValueError as error:
        raise InvalidPrimaryDomain("primary domain is invalid") from error

    if has_scheme and scheme not in {"http", "https"}:
        raise InvalidPrimaryDomain("primary domain must use HTTP or HTTPS")
    if parsed.hostname is None or parsed.username is not None or parsed.password is not None:
        raise InvalidPrimaryDomain("primary domain is invalid")
    if port is not None and (not has_scheme or port != (443 if scheme == "https" else 80)):
        raise InvalidPrimaryDomain("primary domain port is invalid")

    try:
        hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii").casefold()
    except UnicodeError as error:
        raise InvalidPrimaryDomain("primary domain is invalid") from error
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise InvalidPrimaryDomain("primary domain must be a domain name")

    labels = hostname.split(".")
    label_pattern = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
    if (
        hostname == "localhost"
        or len(hostname) > 253
        or len(labels) < 2
        or any(not label_pattern.fullmatch(label) for label in labels)
    ):
        raise InvalidPrimaryDomain("primary domain is invalid")
    return hostname


def _encode_cursor(created_at: datetime, record_id: uuid.UUID) -> str:
    payload = json.dumps([created_at.astimezone(UTC).isoformat(), str(record_id)]).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        raw_timestamp, raw_id = json.loads(base64.urlsafe_b64decode(padded).decode())
        timestamp = datetime.fromisoformat(raw_timestamp)
        if timestamp.tzinfo is None:
            raise ValueError
        return timestamp, uuid.UUID(raw_id)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid cursor") from error


async def create_competitor(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    primary_domain: str,
    description: str,
    daily_run_time_local: time,
    limit: int,
) -> Competitor:
    domain = normalize_primary_domain(primary_domain)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:user_id, 0))"),
        {"user_id": str(user_id)},
    )
    duplicate = await db.scalar(
        select(Competitor.id).where(
            Competitor.user_id == user_id,
            Competitor.primary_domain == domain,
            Competitor.status != CompetitorStatus.DELETED,
        )
    )
    if duplicate is not None:
        raise DuplicateCompetitor("active competitor domain already exists")
    active_count = await db.scalar(
        select(func.count(Competitor.id)).where(
            Competitor.user_id == user_id,
            Competitor.status != CompetitorStatus.DELETED,
        )
    )
    ensure_competitor_capacity(active_count=active_count or 0, limit=limit)
    competitor = Competitor(
        user_id=user_id,
        name=name,
        primary_domain=domain,
        description=description,
        daily_run_time_local=daily_run_time_local,
    )
    db.add(competitor)
    await db.flush()
    await db.refresh(competitor)
    return competitor


async def list_competitors(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> Page[Competitor]:
    statement = select(Competitor).where(
        Competitor.user_id == user_id,
        Competitor.status != CompetitorStatus.DELETED,
    )
    if cursor is not None:
        created_at, record_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                Competitor.created_at > created_at,
                (Competitor.created_at == created_at) & (Competitor.id > record_id),
            )
        )
    records = list(
        (
            await db.scalars(
                statement.order_by(Competitor.created_at, Competitor.id).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(records) > limit
    items = records[:limit]
    next_cursor = _encode_cursor(items[-1].created_at, items[-1].id) if has_more else None
    return Page(items=items, next_cursor=next_cursor)


async def owned_competitor(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    competitor_id: uuid.UUID,
) -> Competitor | None:
    return await db.scalar(
        select(Competitor).where(
            Competitor.id == competitor_id,
            Competitor.user_id == user_id,
            Competitor.status != CompetitorStatus.DELETED,
        )
    )


async def soft_delete_competitor(db: AsyncSession, competitor: Competitor) -> None:
    competitor.status = CompetitorStatus.DELETED
    competitor.deleted_at = datetime.now(UTC)
    await db.flush()


async def update_competitor_status(
    db: AsyncSession,
    *,
    competitor: Competitor,
    status: CompetitorStatus,
) -> None:
    if status is CompetitorStatus.ACTIVE and competitor.status is not CompetitorStatus.ACTIVE:
        approved_source = await db.scalar(
            select(MonitoredSource.id).where(
                MonitoredSource.competitor_id == competitor.id,
                MonitoredSource.approval_status == ApprovalStatus.APPROVED,
            )
        )
        if approved_source is None:
            raise CompetitorActivationNotAllowed("approved source required to activate competitor")
    competitor.status = status


async def list_sources(
    db: AsyncSession,
    *,
    competitor_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> Page[MonitoredSource]:
    statement = select(MonitoredSource).where(MonitoredSource.competitor_id == competitor_id)
    if cursor is not None:
        created_at, record_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                MonitoredSource.created_at > created_at,
                (MonitoredSource.created_at == created_at) & (MonitoredSource.id > record_id),
            )
        )
    records = list(
        (
            await db.scalars(
                statement.order_by(MonitoredSource.created_at, MonitoredSource.id).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(records) > limit
    items = records[:limit]
    next_cursor = _encode_cursor(items[-1].created_at, items[-1].id) if has_more else None
    return Page(items=items, next_cursor=next_cursor)


async def update_source_approval(
    db: AsyncSession,
    *,
    competitor: Competitor,
    source_id: uuid.UUID,
    approval_status: ApprovalStatus,
    validator: SourceUrlValidator,
) -> MonitoredSource | None:
    source = await db.scalar(
        select(MonitoredSource).where(
            MonitoredSource.id == source_id,
            MonitoredSource.competitor_id == competitor.id,
        )
    )
    if source is None:
        return None

    if approval_status is ApprovalStatus.APPROVED:
        try:
            normalized_url = await validator(source.url)
        except (UnsafeSourceUrl, OSError, TimeoutError, ValueError) as error:
            raise SourceUrlNotAllowed("source URL is not allowed") from error
        if not same_registrable_domain(normalized_url, competitor.primary_domain):
            raise SourceUrlNotAllowed("source URL is outside the competitor domain")
        source.url = normalized_url
        source.normalized_url = normalized_url
        source.approval_status = ApprovalStatus.APPROVED
        if competitor.status is CompetitorStatus.DISCOVERING:
            competitor.status = CompetitorStatus.ACTIVE
    else:
        source.approval_status = ApprovalStatus.REJECTED
        await db.flush()
        approved_exists = await db.scalar(
            select(MonitoredSource.id).where(
                MonitoredSource.competitor_id == competitor.id,
                MonitoredSource.approval_status == ApprovalStatus.APPROVED,
            )
        )
        if approved_exists is None and competitor.status is CompetitorStatus.ACTIVE:
            competitor.status = CompetitorStatus.DISCOVERING
    await db.flush()
    await db.refresh(source)
    return source
