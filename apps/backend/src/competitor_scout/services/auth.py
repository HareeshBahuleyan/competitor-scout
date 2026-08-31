import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import JsonWebToken
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from competitor_scout.config import Settings
from competitor_scout.models.auth import OAuthIdentity, Session, User, normalize_email

SESSION_ABSOLUTE_LIFETIME = timedelta(days=30)
SESSION_IDLE_LIFETIME = timedelta(days=7)
OAUTH_STATE_LIFETIME = timedelta(minutes=10)


class InvalidOAuthState(ValueError):
    pass


class OAuthProviderError(RuntimeError):
    pass


class UserCapacityReached(RuntimeError):
    pass


class UserAccountDisabled(RuntimeError):
    pass


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    display_name: str
    avatar_url: str | None
    nonce: str | None


@dataclass(frozen=True)
class AuthenticatedSession:
    session: Session
    user: User
    cookie_secret: str


class GoogleOAuthProvider(Protocol):
    async def authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
    ) -> str: ...

    async def exchange_code(self, *, code: str, redirect_uri: str) -> GoogleIdentity: ...


class AuthlibGoogleOAuthProvider:
    authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint = "https://oauth2.googleapis.com/token"
    jwks_endpoint = "https://www.googleapis.com/oauth2/v3/certs"

    def __init__(self, settings: Settings) -> None:
        self._client_id = settings.google_client_id
        self._client_secret = settings.google_client_secret.get_secret_value()

    def _client(self) -> AsyncOAuth2Client:
        return AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
            scope="openid email profile",
        )

    async def authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
    ) -> str:
        try:
            async with self._client() as client:
                url, _ = client.create_authorization_url(
                    self.authorization_endpoint,
                    redirect_uri=redirect_uri,
                    state=state,
                    nonce=nonce,
                )
                return url
        except Exception:
            raise OAuthProviderError("Google authentication is unavailable") from None

    async def exchange_code(self, *, code: str, redirect_uri: str) -> GoogleIdentity:
        try:
            async with self._client() as client:
                token = await client.fetch_token(
                    self.token_endpoint,
                    code=code,
                    redirect_uri=redirect_uri,
                )
                id_token = token.get("id_token")
                if not isinstance(id_token, str):
                    raise OAuthProviderError("Google authentication failed")
                response = await client.get(self.jwks_endpoint)
                response.raise_for_status()
                claims = JsonWebToken(["RS256"]).decode(
                    id_token,
                    response.json(),
                    claims_options={
                        "iss": {
                            "essential": True,
                            "values": ["accounts.google.com", "https://accounts.google.com"],
                        },
                        "aud": {"essential": True, "value": self._client_id},
                        "sub": {"essential": True},
                        "email": {"essential": True},
                        "nonce": {"essential": True},
                    },
                )
                claims.validate(leeway=60)
                if claims.get("email_verified") is not True:
                    raise OAuthProviderError("Google authentication failed")
                return GoogleIdentity(
                    subject=str(claims["sub"]),
                    email=str(claims["email"]),
                    display_name=str(claims.get("name") or claims["email"]),
                    avatar_url=str(claims["picture"]) if claims.get("picture") else None,
                    nonce=str(claims["nonce"]),
                )
        except Exception:
            raise OAuthProviderError("Google authentication failed") from None


def session_secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def parse_session_cookie(value: str | None) -> tuple[UUID, str] | None:
    if not value or value.count(".") != 1:
        return None
    raw_id, secret = value.split(".", 1)
    if not secret:
        return None
    try:
        session_id = UUID(raw_id)
    except ValueError:
        return None
    return session_id, secret


def _encode_state_payload(payload: dict[str, object]) -> str:
    document = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(document).rstrip(b"=").decode()


def _decode_state_payload(value: str) -> dict[str, object]:
    padded = value + "=" * (-len(value) % 4)
    document = base64.urlsafe_b64decode(padded.encode())
    payload = json.loads(document)
    if not isinstance(payload, dict):
        raise ValueError
    return payload


def create_oauth_state(signing_secret: str, *, now: datetime | None = None) -> tuple[str, str]:
    issued_at = now or datetime.now(UTC)
    nonce = secrets.token_urlsafe(32)
    encoded = _encode_state_payload(
        {
            "iat": int(issued_at.timestamp()),
            "jti": secrets.token_urlsafe(24),
            "nonce": nonce,
        }
    )
    signature = hmac.new(signing_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}", nonce


def validate_oauth_state(
    value: str,
    signing_secret: str,
    *,
    now: datetime | None = None,
) -> str:
    checked_at = now or datetime.now(UTC)
    try:
        encoded, supplied_signature = value.split(".", 1)
        expected_signature = hmac.new(
            signing_secret.encode(),
            encoded.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise ValueError
        payload = _decode_state_payload(encoded)
        issued_at = datetime.fromtimestamp(int(payload["iat"]), tz=UTC)
        nonce = payload["nonce"]
        if not isinstance(nonce, str) or not nonce:
            raise ValueError
        age = checked_at - issued_at
        if age < timedelta(seconds=-60) or age > OAUTH_STATE_LIFETIME:
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise InvalidOAuthState("invalid OAuth state") from None
    return nonce


async def create_session(
    db: AsyncSession,
    user: User,
    *,
    now: datetime | None = None,
) -> tuple[Session, str]:
    created_at = now or datetime.now(UTC)
    secret = secrets.token_urlsafe(32)
    row = Session(
        user=user,
        secret_hash=session_secret_hash(secret),
        expires_at=created_at + SESSION_ABSOLUTE_LIFETIME,
        last_seen_at=created_at,
    )
    db.add(row)
    await db.flush()
    return row, secret


async def resolve_session(
    db: AsyncSession,
    cookie_value: str | None,
    *,
    now: datetime | None = None,
) -> AuthenticatedSession | None:
    parsed = parse_session_cookie(cookie_value)
    if parsed is None:
        return None
    session_id, cookie_secret = parsed
    row = await db.scalar(
        select(Session).where(Session.id == session_id).options(selectinload(Session.user))
    )
    if row is None or not hmac.compare_digest(
        row.secret_hash,
        session_secret_hash(cookie_secret),
    ):
        return None

    checked_at = now or datetime.now(UTC)
    if (
        row.revoked_at is not None
        or row.user.disabled_at is not None
        or row.expires_at <= checked_at
        or row.last_seen_at <= checked_at - SESSION_IDLE_LIFETIME
    ):
        return None

    row.last_seen_at = checked_at
    await db.flush()
    return AuthenticatedSession(session=row, user=row.user, cookie_secret=cookie_secret)


async def upsert_google_user(
    db: AsyncSession,
    identity: GoogleIdentity,
    *,
    max_active_users: int,
    now: datetime | None = None,
) -> User:
    authenticated_at = now or datetime.now(UTC)

    # Serialize registration decisions so concurrent callbacks cannot both claim
    # the final available account slot. Existing users pass through the same
    # short transaction-level lock, which is acceptable for the bounded alpha.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "competitor-scout:google-registration-capacity"},
    )

    oauth_identity = await db.scalar(
        select(OAuthIdentity)
        .where(
            OAuthIdentity.provider == "google",
            OAuthIdentity.provider_subject == identity.subject,
        )
        .options(selectinload(OAuthIdentity.user))
    )
    if oauth_identity is None:
        user = await db.scalar(select(User).where(User.email == normalize_email(identity.email)))
        if user is None:
            active_user_count = await db.scalar(
                select(func.count(User.id)).where(User.disabled_at.is_(None))
            )
            if int(active_user_count or 0) >= max_active_users:
                raise UserCapacityReached
            user = User(
                email=identity.email,
                display_name=identity.display_name,
                avatar_url=identity.avatar_url,
            )
            db.add(user)
            await db.flush()
        if user.disabled_at is not None:
            raise UserAccountDisabled
        oauth_identity = OAuthIdentity(
            user=user,
            provider="google",
            provider_subject=identity.subject,
        )
        db.add(oauth_identity)
    else:
        user = oauth_identity.user
        if user.disabled_at is not None:
            raise UserAccountDisabled

    user.display_name = identity.display_name
    user.avatar_url = identity.avatar_url
    user.last_login_at = authenticated_at
    await db.flush()
    return user
