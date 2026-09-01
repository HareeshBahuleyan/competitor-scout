import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from competitor_scout.api.deps import CsrfRequired, CurrentUser, DbSession
from competitor_scout.jobs.handlers import enqueue_source_discovery, utc_now
from competitor_scout.models.intelligence import Competitor, MonitoredSource
from competitor_scout.schemas.common import CursorPage
from competitor_scout.schemas.competitors import (
    CompetitorCreate,
    CompetitorRead,
    CompetitorUpdate,
    SourceApprovalUpdate,
    SourceRead,
)
from competitor_scout.schemas.runs import RunRead
from competitor_scout.services.competitors import (
    CompetitorActivationNotAllowed,
    CompetitorLimitReached,
    DuplicateCompetitor,
    InvalidPrimaryDomain,
    SourceUrlNotAllowed,
    create_competitor,
    list_competitors,
    list_sources,
    owned_competitor,
    soft_delete_competitor,
    update_competitor_status,
    update_source_approval,
)
from competitor_scout.services.runs import (
    ManualRunNotAllowed,
    RunNotFound,
    enqueue_manual_run,
    run_read,
)

router = APIRouter(prefix="/api/v1/competitors", tags=["competitors"])
PageLimit = Annotated[int, Query(ge=1, le=100)]


def competitor_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="competitor not found")


@router.post("", response_model=CompetitorRead, status_code=status.HTTP_201_CREATED)
async def create_competitor_route(
    payload: CompetitorCreate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    _csrf: CsrfRequired,
) -> Competitor:
    try:
        return await create_competitor(
            db,
            user_id=user.id,
            name=payload.name,
            primary_domain=payload.primary_domain,
            description=payload.description,
            daily_run_time_local=payload.daily_run_time_local,
            limit=request.app.state.settings.max_active_competitors,
        )
    except DuplicateCompetitor:
        raise HTTPException(status_code=409, detail="competitor already exists") from None
    except CompetitorLimitReached:
        raise HTTPException(status_code=422, detail="competitor limit reached") from None
    except InvalidPrimaryDomain:
        raise HTTPException(status_code=422, detail="primary domain is invalid") from None


@router.get("", response_model=CursorPage[CompetitorRead])
async def list_competitors_route(
    db: DbSession,
    user: CurrentUser,
    limit: PageLimit = 25,
    cursor: str | None = None,
) -> CursorPage[CompetitorRead]:
    try:
        page = await list_competitors(
            db,
            user_id=user.id,
            limit=limit,
            cursor=cursor,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    return CursorPage(items=page.items, next_cursor=page.next_cursor)


@router.get("/{competitor_id}", response_model=CompetitorRead)
async def get_competitor_route(
    competitor_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> Competitor:
    competitor = await owned_competitor(db, user_id=user.id, competitor_id=competitor_id)
    if competitor is None:
        raise competitor_not_found()
    return competitor


@router.patch("/{competitor_id}", response_model=CompetitorRead)
async def update_competitor_route(
    competitor_id: uuid.UUID,
    payload: CompetitorUpdate,
    db: DbSession,
    user: CurrentUser,
    _csrf: CsrfRequired,
) -> Competitor:
    competitor = await owned_competitor(db, user_id=user.id, competitor_id=competitor_id)
    if competitor is None:
        raise competitor_not_found()
    changes = payload.model_dump(exclude_unset=True)
    requested_status = changes.pop("status", None)
    if requested_status is not None:
        try:
            await update_competitor_status(
                db,
                competitor=competitor,
                status=requested_status,
            )
        except CompetitorActivationNotAllowed:
            raise HTTPException(
                status_code=422,
                detail="approved source required to activate competitor",
            ) from None
    for field, value in changes.items():
        setattr(competitor, field, value)
    await db.flush()
    await db.refresh(competitor)
    return competitor


@router.delete("/{competitor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_competitor_route(
    competitor_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    _csrf: CsrfRequired,
) -> Response:
    competitor = await owned_competitor(db, user_id=user.id, competitor_id=competitor_id)
    if competitor is None:
        raise competitor_not_found()
    await soft_delete_competitor(db, competitor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{competitor_id}/sources", response_model=CursorPage[SourceRead])
async def list_sources_route(
    competitor_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    limit: PageLimit = 25,
    cursor: str | None = None,
) -> CursorPage[SourceRead]:
    competitor = await owned_competitor(db, user_id=user.id, competitor_id=competitor_id)
    if competitor is None:
        raise competitor_not_found()
    try:
        page = await list_sources(
            db,
            competitor_id=competitor.id,
            limit=limit,
            cursor=cursor,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    return CursorPage(items=page.items, next_cursor=page.next_cursor)


@router.patch("/{competitor_id}/sources/{source_id}", response_model=SourceRead)
async def update_source_approval_route(
    competitor_id: uuid.UUID,
    source_id: uuid.UUID,
    payload: SourceApprovalUpdate,
    request: Request,
    db: DbSession,
    user: CurrentUser,
    _csrf: CsrfRequired,
) -> MonitoredSource:
    competitor = await owned_competitor(db, user_id=user.id, competitor_id=competitor_id)
    if competitor is None:
        raise competitor_not_found()
    try:
        source = await update_source_approval(
            db,
            competitor=competitor,
            source_id=source_id,
            approval_status=payload.approval_status,
            validator=request.app.state.source_url_validator,
        )
    except SourceUrlNotAllowed:
        raise HTTPException(status_code=422, detail="source URL is not allowed") from None
    if source is None:
        raise competitor_not_found()
    return source


@router.post(
    "/{competitor_id}/discover-sources",
    status_code=status.HTTP_202_ACCEPTED,
)
async def discover_sources_route(
    competitor_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    _csrf: CsrfRequired,
) -> dict[str, uuid.UUID]:
    competitor = await owned_competitor(db, user_id=user.id, competitor_id=competitor_id)
    if competitor is None:
        raise competitor_not_found()
    run = await enqueue_source_discovery(db, competitor=competitor, now=utc_now())
    return {"run_id": run.id}


@router.post(
    "/{competitor_id}/runs",
    response_model=RunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_manual_run_route(
    competitor_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    _csrf: CsrfRequired,
) -> RunRead:
    try:
        run = await enqueue_manual_run(
            db,
            user_id=user.id,
            competitor_id=competitor_id,
            now=utc_now(),
        )
    except RunNotFound:
        raise competitor_not_found() from None
    except ManualRunNotAllowed as error:
        detail = (
            "approved source required"
            if error.code == "approved_source_required"
            else "competitor must be active"
        )
        raise HTTPException(status_code=422, detail=detail) from None
    return run_read(run)
