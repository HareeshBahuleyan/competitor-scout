import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from competitor_scout.api.deps import CurrentUser, DbSession
from competitor_scout.models.intelligence import RunType, ScoutRunStatus
from competitor_scout.schemas.common import CursorPage
from competitor_scout.schemas.runs import RunRead, RunUsageRead, TaskRead
from competitor_scout.services.runs import (
    list_run_tasks,
    list_runs,
    owned_run,
    run_read,
    run_usage,
)

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])
PageLimit = Annotated[int, Query(ge=1, le=100)]


def run_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="run not found")


@router.get("", response_model=CursorPage[RunRead])
async def list_runs_route(
    db: DbSession,
    user: CurrentUser,
    limit: PageLimit = 25,
    cursor: str | None = None,
    competitor_id: uuid.UUID | None = None,
    status: ScoutRunStatus | None = None,
    run_type: RunType | None = None,
) -> CursorPage[RunRead]:
    try:
        page = await list_runs(
            db,
            user_id=user.id,
            limit=limit,
            cursor=cursor,
            competitor_id=competitor_id,
            status=status,
            run_type=run_type,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    return CursorPage(items=page.items, next_cursor=page.next_cursor)


@router.get("/{run_id}", response_model=RunRead)
async def get_run_route(
    run_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> RunRead:
    run = await owned_run(db, user_id=user.id, run_id=run_id)
    if run is None:
        raise run_not_found()
    return run_read(run)


@router.get("/{run_id}/tasks", response_model=CursorPage[TaskRead])
async def get_run_tasks_route(
    run_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    limit: PageLimit = 25,
    cursor: str | None = None,
) -> CursorPage[TaskRead]:
    run = await owned_run(db, user_id=user.id, run_id=run_id)
    if run is None:
        raise run_not_found()
    try:
        page = await list_run_tasks(
            db,
            run_id=run.id,
            limit=limit,
            cursor=cursor,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid cursor") from None
    return CursorPage(items=page.items, next_cursor=page.next_cursor)


@router.get("/{run_id}/usage", response_model=RunUsageRead)
async def get_run_usage_route(
    run_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> RunUsageRead:
    run = await owned_run(db, user_id=user.id, run_id=run_id)
    if run is None:
        raise run_not_found()
    return await run_usage(db, run)
