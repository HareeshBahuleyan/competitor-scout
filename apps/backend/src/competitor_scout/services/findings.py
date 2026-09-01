from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.agents.contracts import FindingCategory, SignificanceLevel
from competitor_scout.db import SessionFactory
from competitor_scout.models.intelligence import (
    AgentTask,
    AgentTaskRole,
    AgentTaskStatus,
    Competitor,
    CompetitorStatus,
    EvidenceItem,
    Finding,
    FindingEvidence,
    RunType,
    ScoutRun,
    ScoutRunStatus,
)
from competitor_scout.schemas.findings import EvidencePublication, FindingPublication


class PublicationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class FindingPage:
    items: list[Finding]
    next_cursor: str | None


@dataclass(frozen=True)
class EvidenceCitation:
    evidence: EvidenceItem
    citation_order: int
    is_primary: bool


@dataclass(frozen=True)
class EvidencePage:
    items: list[EvidenceCitation]
    next_cursor: str | None


@dataclass(frozen=True)
class _EvidenceDetails:
    index: int
    publication: EvidencePublication
    source_url: str
    source_domain: str
    quoted_text: str
    normalized_claim: str


def _cosmetic_normalize(value: str) -> str:
    unicode_normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", unicode_normalized.strip().casefold())


def _domain_normalize(value: str) -> str:
    try:
        return value.strip().rstrip(".").encode("idna").decode("ascii").casefold()
    except UnicodeError as error:
        raise ValueError("invalid domain") from error


def finding_duplicate_key(
    user_id: str,
    competitor_id: str,
    category: str,
    claim: str,
    domain: str,
) -> str:
    value = "|".join(
        [
            _cosmetic_normalize(user_id),
            _cosmetic_normalize(competitor_id),
            _cosmetic_normalize(category),
            _cosmetic_normalize(claim),
            _domain_normalize(domain),
        ]
    )
    return hashlib.sha256(value.encode()).hexdigest()


def normalized_claim_fingerprint(claim: str) -> str:
    return hashlib.sha256(_cosmetic_normalize(claim).encode()).hexdigest()


def _normalized_quote(value: str) -> str:
    without_controls = "".join(
        " " if unicodedata.category(character).startswith("C") else character for character in value
    )
    return " ".join(without_controls.split())


def _evidence_fingerprint(source_url: str, quoted_text: str) -> str:
    return hashlib.sha256(f"{source_url}\n{quoted_text}".encode()).hexdigest()


def public_source_domain(source_url: str) -> str:
    try:
        parsed = urlsplit(source_url)
        port = parsed.port
    except ValueError as error:
        raise PublicationValidationError("source URL is invalid") from error
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise PublicationValidationError("source URL is not a public HTTPS URL")
    domain = _domain_normalize(parsed.hostname)
    if domain == "localhost" or domain.endswith(".localhost"):
        raise PublicationValidationError("source URL is not a public HTTPS URL")
    try:
        address = ipaddress.ip_address(domain)
    except ValueError:
        if "." not in domain:
            raise PublicationValidationError("source URL is not a public HTTPS URL") from None
    else:
        if not address.is_global:
            raise PublicationValidationError("source URL is not a public HTTPS URL")
        domain = address.compressed
    return domain


def _encode_cursor(published_at: datetime, finding_id: uuid.UUID) -> str:
    payload = json.dumps([published_at.astimezone(UTC).isoformat(), str(finding_id)]).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw_time, raw_id = json.loads(base64.urlsafe_b64decode(padded).decode())
        published_at = datetime.fromisoformat(raw_time)
        if published_at.tzinfo is None:
            raise ValueError
        return published_at, uuid.UUID(raw_id)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid cursor") from error


class FindingPublicationService:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        minimum_confidence: Decimal = Decimal("0.70"),
    ) -> None:
        self._session_factory = session_factory
        self._minimum_confidence = minimum_confidence

    async def publish(
        self,
        *,
        user_id: uuid.UUID,
        competitor_id: uuid.UUID,
        scout_run_id: uuid.UUID,
        finding: FindingPublication,
        evidence: list[EvidencePublication],
        published_at: datetime,
    ) -> Finding:
        if published_at.tzinfo is None:
            raise PublicationValidationError("publication time must be timezone-aware")
        if not finding.material_change:
            raise PublicationValidationError("finding is not a material change")
        if finding.confidence < self._minimum_confidence:
            raise PublicationValidationError("finding confidence is below publication threshold")
        if any(index >= len(evidence) for index in finding.evidence_indexes):
            raise PublicationValidationError("citation index is outside accepted evidence")

        all_source_details: list[_EvidenceDetails] = []
        for index, item in enumerate(evidence):
            source_url = str(item.source_url)
            quoted_text = _normalized_quote(item.quoted_text)
            fingerprint = _evidence_fingerprint(source_url, quoted_text)
            if not hmac.compare_digest(fingerprint, item.content_fingerprint):
                raise PublicationValidationError("evidence fingerprint does not match content")
            all_source_details.append(
                _EvidenceDetails(
                    index=index,
                    publication=item,
                    source_url=source_url,
                    source_domain=public_source_domain(source_url),
                    quoted_text=quoted_text,
                    normalized_claim=" ".join(item.normalized_claim.split()),
                )
            )
        source_details_by_index = {details.index: details for details in all_source_details}
        cited_source_details = [
            source_details_by_index[index] for index in finding.evidence_indexes
        ]
        async with self._session_factory.begin() as session:
            competitor = await session.scalar(
                select(Competitor).where(
                    Competitor.id == competitor_id,
                    Competitor.user_id == user_id,
                )
            )
            if competitor is None:
                raise PublicationValidationError("competitor ownership does not match")
            if competitor.status is CompetitorStatus.DELETED:
                raise PublicationValidationError("competitor lifecycle does not allow publication")
            run = await session.scalar(
                select(ScoutRun).where(
                    ScoutRun.id == scout_run_id,
                    ScoutRun.user_id == user_id,
                    ScoutRun.competitor_id == competitor_id,
                )
            )
            if run is None:
                raise PublicationValidationError("Scout Run ownership does not match")
            if (
                run.run_type not in {RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT}
                or run.status is not ScoutRunStatus.SYNTHESIZING
            ):
                raise PublicationValidationError("Scout Run lifecycle does not allow publication")
            task_ids = {details.publication.agent_task_id for details in all_source_details}
            owned_task_ids = set(
                (
                    await session.scalars(
                        select(AgentTask.id).where(
                            AgentTask.scout_run_id == scout_run_id,
                            AgentTask.id.in_(task_ids),
                        )
                    )
                ).all()
            )
            if owned_task_ids != task_ids:
                raise PublicationValidationError("evidence task ownership does not match")
            eligible_task_ids = set(
                (
                    await session.scalars(
                        select(AgentTask.id).where(
                            AgentTask.id.in_(task_ids),
                            AgentTask.role == AgentTaskRole.CHILD_RESEARCHER,
                            AgentTask.status == AgentTaskStatus.SUCCEEDED,
                        )
                    )
                ).all()
            )
            if eligible_task_ids != task_ids:
                raise PublicationValidationError(
                    "evidence task lifecycle does not allow publication"
                )
            return await self._persist(
                session,
                user_id=user_id,
                competitor_id=competitor_id,
                scout_run_id=scout_run_id,
                finding=finding,
                source_details=cited_source_details,
                published_at=published_at.astimezone(UTC),
            )

    async def _persist(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        competitor_id: uuid.UUID,
        scout_run_id: uuid.UUID,
        finding: FindingPublication,
        source_details: list[_EvidenceDetails],
        published_at: datetime,
    ) -> Finding:
        evidence_ids: dict[int, uuid.UUID] = {}
        for details in source_details:
            item = details.publication
            statement = (
                insert(EvidenceItem)
                .values(
                    user_id=user_id,
                    competitor_id=competitor_id,
                    scout_run_id=scout_run_id,
                    agent_task_id=item.agent_task_id,
                    source_url=details.source_url,
                    source_domain=details.source_domain,
                    source_title=item.source_title.strip(),
                    source_type=item.source_type,
                    published_at=item.published_at,
                    captured_at=item.captured_at,
                    quoted_text=details.quoted_text,
                    normalized_claim=details.normalized_claim,
                    content_fingerprint=item.content_fingerprint,
                )
                .on_conflict_do_nothing(
                    constraint="uq_evidence_items_competitor_source_fingerprint"
                )
                .returning(EvidenceItem.id)
            )
            evidence_id = await session.scalar(statement)
            if evidence_id is None:
                existing = await session.scalar(
                    select(EvidenceItem).where(
                        EvidenceItem.competitor_id == competitor_id,
                        EvidenceItem.source_url == details.source_url,
                        EvidenceItem.content_fingerprint == item.content_fingerprint,
                    )
                )
                if existing is None:
                    raise RuntimeError("evidence upsert did not resolve a row")
                if (
                    existing.source_domain != details.source_domain
                    or existing.source_type is not item.source_type
                    or existing.quoted_text != details.quoted_text
                    or existing.normalized_claim != details.normalized_claim
                ):
                    raise PublicationValidationError(
                        "evidence fingerprint conflicts with different content"
                    )
                # Evidence rows are content-addressed and retain first-observation
                # run/task provenance. A later exact observation safely reuses that row;
                # the finding's last_seen_at records its recurrence.
                evidence_id = existing.id
            evidence_ids[details.index] = evidence_id

        primary_source_domain = next(
            details.source_domain
            for details in source_details
            if details.index == finding.primary_evidence_index
        )
        duplicate_key = finding_duplicate_key(
            str(user_id),
            str(competitor_id),
            finding.category.value,
            finding.normalized_claim,
            primary_source_domain,
        )
        claim_fingerprint = normalized_claim_fingerprint(finding.normalized_claim)
        finding_statement = (
            insert(Finding)
            .values(
                user_id=user_id,
                competitor_id=competitor_id,
                originating_scout_run_id=scout_run_id,
                category=finding.category,
                title=finding.title,
                summary=finding.summary,
                significance_explanation=finding.significance_explanation,
                significance_level=finding.significance_level,
                confidence=finding.confidence,
                decision_rationale=finding.decision_rationale,
                normalized_claim_fingerprint=claim_fingerprint,
                duplicate_key=duplicate_key,
                first_seen_at=published_at,
                last_seen_at=published_at,
                published_at=published_at,
            )
            .on_conflict_do_update(
                index_elements=[Finding.duplicate_key],
                set_={
                    "last_seen_at": func.greatest(Finding.last_seen_at, published_at),
                    "updated_at": func.now(),
                },
            )
            .returning(Finding)
        )
        record = (await session.scalars(finding_statement)).one()
        if record.user_id != user_id or record.competitor_id != competitor_id:
            raise RuntimeError("finding duplicate key resolved outside publication scope")

        existing_links = list(
            (
                await session.scalars(
                    select(FindingEvidence).where(FindingEvidence.finding_id == record.id)
                )
            ).all()
        )
        existing_ids = {link.evidence_item_id for link in existing_links}
        next_order = max((link.citation_order for link in existing_links), default=0) + 1
        has_primary = any(link.is_primary for link in existing_links)
        for index in finding.evidence_indexes:
            evidence_id = evidence_ids[index]
            if evidence_id in existing_ids:
                continue
            is_primary = not has_primary and index == finding.primary_evidence_index
            await session.execute(
                insert(FindingEvidence)
                .values(
                    finding_id=record.id,
                    evidence_item_id=evidence_id,
                    citation_order=next_order,
                    is_primary=is_primary,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        FindingEvidence.finding_id,
                        FindingEvidence.evidence_item_id,
                    ]
                )
            )
            existing_ids.add(evidence_id)
            next_order += 1
            has_primary = has_primary or is_primary
        await session.refresh(record)
        return record


async def list_findings(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    limit: int,
    cursor: str | None = None,
    competitor_id: uuid.UUID | None = None,
    category: FindingCategory | None = None,
    significance: SignificanceLevel | None = None,
    confidence_min: Decimal | None = None,
    published_from: datetime | None = None,
    published_to: datetime | None = None,
) -> FindingPage:
    statement = select(Finding).where(Finding.user_id == user_id)
    if competitor_id is not None:
        statement = statement.where(Finding.competitor_id == competitor_id)
    if category is not None:
        statement = statement.where(Finding.category == category)
    if significance is not None:
        statement = statement.where(Finding.significance_level == significance)
    if confidence_min is not None:
        statement = statement.where(Finding.confidence >= confidence_min)
    if published_from is not None:
        statement = statement.where(Finding.published_at >= published_from)
    if published_to is not None:
        statement = statement.where(Finding.published_at <= published_to)
    if cursor is not None:
        published_at, finding_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                Finding.published_at < published_at,
                (Finding.published_at == published_at) & (Finding.id < finding_id),
            )
        )
    records = list(
        (
            await db.scalars(
                statement.order_by(Finding.published_at.desc(), Finding.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    has_more = len(records) > limit
    items = records[:limit]
    next_cursor = _encode_cursor(items[-1].published_at, items[-1].id) if has_more else None
    return FindingPage(items=items, next_cursor=next_cursor)


async def owned_finding(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    finding_id: uuid.UUID,
) -> Finding | None:
    return await db.scalar(
        select(Finding).where(Finding.id == finding_id, Finding.user_id == user_id)
    )


async def list_finding_evidence(
    db: AsyncSession,
    *,
    finding_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> EvidencePage:
    after_order = 0
    if cursor is not None:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            after_order = int(base64.urlsafe_b64decode(padded).decode())
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError("invalid cursor") from error
    rows = (
        await db.execute(
            select(FindingEvidence, EvidenceItem)
            .join(EvidenceItem, EvidenceItem.id == FindingEvidence.evidence_item_id)
            .where(
                FindingEvidence.finding_id == finding_id,
                FindingEvidence.citation_order > after_order,
            )
            .order_by(FindingEvidence.citation_order)
            .limit(limit + 1)
        )
    ).all()
    has_more = len(rows) > limit
    selected = rows[:limit]
    items = [
        EvidenceCitation(
            evidence=evidence_item,
            citation_order=link.citation_order,
            is_primary=link.is_primary,
        )
        for link, evidence_item in selected
    ]
    next_cursor = (
        base64.urlsafe_b64encode(str(items[-1].citation_order).encode()).decode().rstrip("=")
        if has_more
        else None
    )
    return EvidencePage(items=items, next_cursor=next_cursor)
