import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from competitor_scout.agents.contracts import FindingCategory, SignificanceLevel
from competitor_scout.api.deps import CurrentUser, DbSession
from competitor_scout.models.intelligence import Finding
from competitor_scout.schemas.common import CursorPage
from competitor_scout.schemas.findings import FindingEvidenceRead, FindingRead
from competitor_scout.services.findings import (
    list_finding_evidence,
    list_findings,
    owned_finding,
)

router = APIRouter(prefix="/api/v1/findings", tags=["findings"])
PageLimit = Annotated[int, Query(ge=1, le=100)]
ConfidenceMinimum = Annotated[Decimal | None, Query(ge=0, le=1)]


def finding_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="finding not found")


@router.get("", response_model=CursorPage[FindingRead])
async def list_findings_route(
    db: DbSession,
    user: CurrentUser,
    limit: PageLimit = 25,
    cursor: str | None = None,
    competitor_id: uuid.UUID | None = None,
    category: FindingCategory | None = None,
    significance: SignificanceLevel | None = None,
    confidence_min: ConfidenceMinimum = None,
    published_from: datetime | None = None,
    published_to: datetime | None = None,
) -> CursorPage[FindingRead]:
    try:
        page = await list_findings(
            db,
            user_id=user.id,
            limit=limit,
            cursor=cursor,
            competitor_id=competitor_id,
            category=category,
            significance=significance,
            confidence_min=confidence_min,
            published_from=published_from,
            published_to=published_to,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    return CursorPage(items=page.items, next_cursor=page.next_cursor)


@router.get("/{finding_id}", response_model=FindingRead)
async def get_finding_route(
    finding_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> Finding:
    record = await owned_finding(db, user_id=user.id, finding_id=finding_id)
    if record is None:
        raise finding_not_found()
    return record


@router.get("/{finding_id}/evidence", response_model=CursorPage[FindingEvidenceRead])
async def get_finding_evidence_route(
    finding_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    limit: PageLimit = 25,
    cursor: str | None = None,
) -> CursorPage[FindingEvidenceRead]:
    record = await owned_finding(db, user_id=user.id, finding_id=finding_id)
    if record is None:
        raise finding_not_found()
    try:
        page = await list_finding_evidence(
            db,
            finding_id=record.id,
            limit=limit,
            cursor=cursor,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    items = [
        FindingEvidenceRead(
            id=item.evidence.id,
            source_url=item.evidence.source_url,
            source_domain=item.evidence.source_domain,
            source_title=item.evidence.source_title,
            source_type=item.evidence.source_type,
            published_at=item.evidence.published_at,
            captured_at=item.evidence.captured_at,
            quoted_text=item.evidence.quoted_text,
            normalized_claim=item.evidence.normalized_claim,
            scout_run_id=item.evidence.scout_run_id,
            agent_task_id=item.evidence.agent_task_id,
            citation_order=item.citation_order,
            is_primary=item.is_primary,
        )
        for item in page.items
    ]
    return CursorPage(items=items, next_cursor=page.next_cursor)
