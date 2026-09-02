import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from competitor_scout.api.deps import CurrentUser, DbSession
from competitor_scout.models.briefs import WeeklyBrief
from competitor_scout.schemas.briefs import BriefRead, DigestOverview
from competitor_scout.schemas.common import CursorPage
from competitor_scout.services.briefs import digest_overview, list_briefs, owned_brief

router = APIRouter(prefix="/api/v1/briefs", tags=["briefs"])
PageLimit = Annotated[int, Query(ge=1, le=100)]


@router.get("", response_model=CursorPage[BriefRead])
async def list_briefs_route(
    db: DbSession,
    user: CurrentUser,
    limit: PageLimit = 25,
    cursor: str | None = None,
) -> CursorPage[BriefRead]:
    try:
        page = await list_briefs(db, user_id=user.id, limit=limit, cursor=cursor)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    return CursorPage(items=page.items, next_cursor=page.next_cursor)


@router.get("/overview", response_model=DigestOverview)
async def get_digest_overview_route(
    db: DbSession,
    user: CurrentUser,
) -> DigestOverview:
    return await digest_overview(
        db,
        user_id=user.id,
        timezone_name=user.timezone,
    )


@router.get("/{brief_id}", response_model=BriefRead)
async def get_brief_route(
    brief_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> WeeklyBrief:
    brief = await owned_brief(db, user_id=user.id, brief_id=brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="brief not found")
    return brief
