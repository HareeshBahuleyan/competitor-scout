from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.agents.contracts import SnapshotSectionCandidate, StartingSnapshotCandidate
from competitor_scout.db import SessionFactory
from competitor_scout.models.intelligence import (
    AgentTask,
    AgentTaskStatus,
    Competitor,
    EvidenceItem,
    EvidenceObservation,
    RunType,
    ScoutRun,
)
from competitor_scout.models.snapshots import CompetitorStartingSnapshot
from competitor_scout.schemas.snapshots import (
    SnapshotCoverage,
    SnapshotEvidenceRead,
    SnapshotSectionRead,
    StartingSnapshotRead,
)

_SECTION_ADAPTER = TypeAdapter(list[SnapshotSectionCandidate])


class SnapshotPublicationError(ValueError):
    pass


class SnapshotIntegrityError(RuntimeError):
    pass


class SnapshotPublicationService:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sessions = session_factory

    async def publish(
        self,
        *,
        user_id: uuid.UUID,
        competitor_id: uuid.UUID,
        scout_run_id: uuid.UUID,
        snapshot: StartingSnapshotCandidate,
        coverage: SnapshotCoverage,
        published_at: datetime,
    ) -> CompetitorStartingSnapshot:
        if published_at.tzinfo is None:
            raise SnapshotPublicationError("snapshot publication time must be timezone-aware")
        evidence_ids = {
            reference.evidence_id
            for section in snapshot.sections
            for reference in section.references
        }
        async with self._sessions.begin() as session:
            competitor = await session.scalar(
                select(Competitor)
                .where(Competitor.id == competitor_id, Competitor.user_id == user_id)
                .with_for_update()
            )
            run = await session.scalar(
                select(ScoutRun).where(
                    ScoutRun.id == scout_run_id,
                    ScoutRun.user_id == user_id,
                    ScoutRun.competitor_id == competitor_id,
                    ScoutRun.run_type.in_([RunType.DAILY_SCOUT, RunType.MANUAL_SCOUT]),
                )
            )
            if competitor is None or run is None:
                raise SnapshotPublicationError("snapshot ownership is invalid")
            existing = await session.scalar(
                select(CompetitorStartingSnapshot).where(
                    CompetitorStartingSnapshot.competitor_id == competitor_id,
                    CompetitorStartingSnapshot.user_id == user_id,
                )
            )
            if existing is not None:
                return existing
            if competitor.starting_snapshot_requested_at is None:
                raise SnapshotPublicationError("starting snapshot was not requested")

            observed_ids = set(
                (
                    await session.scalars(
                        select(EvidenceObservation.evidence_item_id)
                        .join(EvidenceItem, EvidenceItem.id == EvidenceObservation.evidence_item_id)
                        .join(AgentTask, AgentTask.id == EvidenceObservation.agent_task_id)
                        .where(
                            EvidenceObservation.scout_run_id == scout_run_id,
                            EvidenceObservation.evidence_item_id.in_(evidence_ids),
                            EvidenceItem.user_id == user_id,
                            EvidenceItem.competitor_id == competitor_id,
                            AgentTask.scout_run_id == scout_run_id,
                            AgentTask.status == AgentTaskStatus.SUCCEEDED,
                        )
                    )
                ).all()
            )
            if observed_ids != evidence_ids:
                raise SnapshotPublicationError("snapshot contains unaccepted evidence references")

            statement = (
                insert(CompetitorStartingSnapshot)
                .values(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    competitor_id=competitor_id,
                    scout_run_id=scout_run_id,
                    executive_summary=snapshot.executive_summary,
                    sections=snapshot.model_dump(mode="json")["sections"],
                    coverage=coverage.model_dump(mode="json"),
                    published_at=published_at.astimezone(UTC),
                )
                .on_conflict_do_nothing(constraint="uq_starting_snapshots_competitor")
                .returning(CompetitorStartingSnapshot)
            )
            created = (await session.scalars(statement)).one_or_none()
            if created is not None:
                return created
            resolved = await session.scalar(
                select(CompetitorStartingSnapshot).where(
                    CompetitorStartingSnapshot.competitor_id == competitor_id,
                    CompetitorStartingSnapshot.user_id == user_id,
                )
            )
            if resolved is None:
                raise RuntimeError("idempotent snapshot publication did not resolve a row")
            return resolved


async def owned_starting_snapshot(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    competitor_id: uuid.UUID,
) -> StartingSnapshotRead | None:
    row = (
        await db.execute(
            select(CompetitorStartingSnapshot, Competitor.name)
            .join(
                Competitor,
                (Competitor.id == CompetitorStartingSnapshot.competitor_id)
                & (Competitor.user_id == user_id),
            )
            .where(
                CompetitorStartingSnapshot.user_id == user_id,
                CompetitorStartingSnapshot.competitor_id == competitor_id,
            )
        )
    ).one_or_none()
    if row is None:
        return None
    snapshot, competitor_name = row
    try:
        sections = _SECTION_ADAPTER.validate_json(json.dumps(snapshot.sections))
        coverage = SnapshotCoverage.model_validate_json(json.dumps(snapshot.coverage))
    except ValidationError as error:
        raise SnapshotIntegrityError("stored starting snapshot is invalid") from error

    evidence_ids = {
        reference.evidence_id for section in sections for reference in section.references
    }
    evidence_rows = list(
        (
            await db.execute(
                select(EvidenceItem)
                .join(
                    EvidenceObservation,
                    EvidenceObservation.evidence_item_id == EvidenceItem.id,
                )
                .where(
                    EvidenceObservation.scout_run_id == snapshot.scout_run_id,
                    EvidenceItem.id.in_(evidence_ids),
                    EvidenceItem.user_id == user_id,
                    EvidenceItem.competitor_id == competitor_id,
                )
            )
        ).scalars()
    )
    evidence_by_id = {item.id: item for item in evidence_rows}
    if set(evidence_by_id) != evidence_ids:
        raise SnapshotIntegrityError("starting snapshot evidence could not be resolved")

    resolved_sections = [
        SnapshotSectionRead(
            topic=section.topic,
            narrative=section.narrative,
            references=[
                SnapshotEvidenceRead(
                    evidence_id=reference.evidence_id,
                    statement=reference.statement,
                    source_title=evidence_by_id[reference.evidence_id].source_title,
                    source_url=evidence_by_id[reference.evidence_id].source_url,
                    quoted_text=evidence_by_id[reference.evidence_id].quoted_text,
                    captured_at=evidence_by_id[reference.evidence_id].captured_at,
                )
                for reference in section.references
            ],
        )
        for section in sections
    ]
    return StartingSnapshotRead(
        id=snapshot.id,
        competitor_id=snapshot.competitor_id,
        competitor_name=competitor_name,
        scout_run_id=snapshot.scout_run_id,
        executive_summary=snapshot.executive_summary,
        sections=resolved_sections,
        coverage=coverage,
        published_at=snapshot.published_at,
        created_at=snapshot.created_at,
    )
