from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

ReadinessProbe = Callable[[], Awaitable[None]]

router = APIRouter(tags=["health"])


def get_readiness_probe(request: Request) -> ReadinessProbe:
    return request.app.state.readiness_probe


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(
    probe: Annotated[ReadinessProbe, Depends(get_readiness_probe)],
) -> dict[str, str]:
    try:
        await probe()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"status": "ready"}
