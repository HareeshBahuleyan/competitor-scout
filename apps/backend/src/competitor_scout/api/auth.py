import hashlib
import hmac
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from competitor_scout.api.deps import CsrfRequired, CurrentSession, DbSession
from competitor_scout.security.csrf import csrf_token
from competitor_scout.services.auth import (
    GoogleOAuthProvider,
    InvalidOAuthState,
    OAuthProviderError,
    UserAccountDisabled,
    UserCapacityReached,
    create_oauth_state,
    create_session,
    upsert_google_user,
    validate_oauth_state,
)

router = APIRouter()

OAUTH_STATE_COOKIE_NAME = "competitor_scout_oauth_state"
OAUTH_STATE_COOKIE_PATH = "/auth/google"
OAUTH_STATE_MAX_AGE_SECONDS = 10 * 60


def oauth_provider(request: Request) -> GoogleOAuthProvider:
    return request.app.state.oauth_provider


OAuthProviderDependency = Annotated[GoogleOAuthProvider, Depends(oauth_provider)]


def callback_url(request: Request) -> str:
    base_url = str(request.app.state.settings.public_base_url).rstrip("/")
    return f"{base_url}/auth/google/callback"


def oauth_state_binding(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def clear_oauth_state_cookie(response: Response) -> None:
    response.delete_cookie(
        OAUTH_STATE_COOKIE_NAME,
        path=OAUTH_STATE_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="lax",
    )


def callback_error(status_code: int, detail: str) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content={"detail": detail})
    clear_oauth_state_cookie(response)
    return response


@router.get("/auth/google/login")
async def google_login(
    request: Request,
    provider: OAuthProviderDependency,
) -> RedirectResponse:
    signing_secret = request.app.state.settings.session_secret.get_secret_value()
    state, nonce = create_oauth_state(signing_secret)
    try:
        location = await provider.authorization_url(
            redirect_uri=callback_url(request),
            state=state,
            nonce=nonce,
        )
    except OAuthProviderError:
        raise HTTPException(status_code=503, detail="authentication unavailable") from None
    response = RedirectResponse(location)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE_NAME,
        value=oauth_state_binding(state),
        max_age=OAUTH_STATE_MAX_AGE_SECONDS,
        secure=True,
        httponly=True,
        samesite="lax",
        path=OAUTH_STATE_COOKIE_PATH,
    )
    return response


@router.get("/auth/google/callback")
async def google_callback(
    request: Request,
    db: DbSession,
    provider: OAuthProviderDependency,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
) -> Response:
    if not code or not state:
        return callback_error(400, "authentication failed")

    browser_binding = request.cookies.get(OAUTH_STATE_COOKIE_NAME)
    expected_binding = oauth_state_binding(state)
    if browser_binding is None or not hmac.compare_digest(browser_binding, expected_binding):
        return callback_error(400, "authentication failed")

    settings = request.app.state.settings
    try:
        expected_nonce = validate_oauth_state(
            state,
            settings.session_secret.get_secret_value(),
        )
        identity = await provider.exchange_code(code=code, redirect_uri=callback_url(request))
        if identity.nonce is None or not hmac.compare_digest(identity.nonce, expected_nonce):
            raise InvalidOAuthState("nonce mismatch")
    except (InvalidOAuthState, OAuthProviderError):
        return callback_error(400, "authentication failed")

    try:
        user = await upsert_google_user(
            db,
            identity,
            max_active_users=settings.max_active_users,
        )
    except UserCapacityReached:
        return callback_error(403, "registration is closed")
    except UserAccountDisabled:
        return callback_error(403, "account is disabled")

    session, secret = await create_session(db, user)
    response = RedirectResponse(str(settings.public_base_url))
    response.set_cookie(
        key=settings.session_cookie_name,
        value=f"{session.id}.{secret}",
        max_age=30 * 24 * 60 * 60,
        secure=True,
        httponly=True,
        samesite="lax",
        path="/",
    )
    clear_oauth_state_cookie(response)
    return response


@router.get("/api/v1/me")
async def me(request: Request, auth: CurrentSession) -> dict[str, object]:
    token = csrf_token(
        auth.session.id,
        auth.cookie_secret,
        request.app.state.settings.csrf_secret.get_secret_value(),
    )
    return {
        "id": auth.user.id,
        "email": auth.user.email,
        "display_name": auth.user.display_name,
        "avatar_url": auth.user.avatar_url,
        "timezone": auth.user.timezone,
        "csrf_token": token,
    }


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request,
    db: DbSession,
    auth: CurrentSession,
    _: CsrfRequired,
) -> Response:
    auth.session.revoked_at = datetime.now(UTC)
    await db.flush()
    response = Response(status_code=204)
    response.delete_cookie(
        request.app.state.settings.session_cookie_name,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return response
