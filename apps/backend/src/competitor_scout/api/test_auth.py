from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from sqlalchemy import select, text

from competitor_scout.api.deps import DbSession
from competitor_scout.models.auth import User
from competitor_scout.services.auth import create_session

router = APIRouter(prefix="/api/test", tags=["test-auth"], include_in_schema=False)
E2E_FIXTURE_EMAIL = "e2e-fixture@example.test"


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
async def e2e_login(
    request: Request,
    db: DbSession,
    supplied_secret: Annotated[str | None, Header(alias="X-E2E-Secret")] = None,
) -> Response:
    settings = request.app.state.settings
    configured_secret = settings.e2e_auth_secret
    if settings.environment != "test" or configured_secret is None:
        raise HTTPException(status_code=404, detail="not found")
    expected = configured_secret.get_secret_value()
    if supplied_secret is None or not hmac.compare_digest(supplied_secret, expected):
        raise HTTPException(status_code=403, detail="test authentication unavailable")

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "competitor-scout:e2e-fixture-user"},
    )
    user = await db.scalar(select(User).where(User.email == E2E_FIXTURE_EMAIL))
    if user is None:
        user = User(
            email=E2E_FIXTURE_EMAIL,
            display_name="E2E Fixture User",
            timezone="UTC",
        )
        db.add(user)
        await db.flush()
    session, cookie_secret = await create_session(db, user)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=f"{session.id}.{cookie_secret}",
        max_age=30 * 24 * 60 * 60,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response
