from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from competitor_scout.db import session_dependency
from competitor_scout.models.auth import User
from competitor_scout.security.csrf import csrf_valid
from competitor_scout.services.auth import AuthenticatedSession, resolve_session

DbSession = Annotated[AsyncSession, Depends(session_dependency)]


async def authenticated_session(request: Request, db: DbSession) -> AuthenticatedSession:
    settings = request.app.state.settings
    resolved = await resolve_session(
        db,
        request.cookies.get(settings.session_cookie_name),
    )
    if resolved is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return resolved


CurrentSession = Annotated[AuthenticatedSession, Depends(authenticated_session)]


async def current_user(auth: CurrentSession) -> User:
    return auth.user


CurrentUser = Annotated[User, Depends(current_user)]


async def require_csrf(
    request: Request,
    auth: CurrentSession,
    supplied: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    signing_secret = request.app.state.settings.csrf_secret.get_secret_value()
    if supplied is None or not csrf_valid(
        auth.session.id,
        auth.cookie_secret,
        supplied,
        signing_secret,
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


CsrfRequired = Annotated[None, Depends(require_csrf)]
