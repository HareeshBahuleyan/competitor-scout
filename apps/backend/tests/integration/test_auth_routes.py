from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from competitor_scout.api.deps import current_user
from competitor_scout.config import Settings
from competitor_scout.db import session_dependency
from competitor_scout.main import create_app
from competitor_scout.models.auth import OAuthIdentity, Session, User
from competitor_scout.services.auth import (
    GoogleIdentity,
    create_session,
    resolve_session,
    session_secret_hash,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


class FakeGoogleOAuthProvider:
    def __init__(
        self,
        *,
        email: str = "founder@example.com",
        subject: str = "google-subject",
    ) -> None:
        self.email = email
        self.subject = subject
        self.nonce: str | None = None
        self.exchange_calls = 0
        self.override_nonce: str | None = None

    async def authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
    ) -> str:
        self.nonce = nonce
        return "https://accounts.example/authorize?" + urlencode(
            {"redirect_uri": redirect_uri, "state": state, "nonce": nonce}
        )

    async def exchange_code(self, *, code: str, redirect_uri: str) -> GoogleIdentity:
        self.exchange_calls += 1
        return GoogleIdentity(
            subject=self.subject,
            email=self.email,
            display_name="Founder",
            avatar_url="https://images.example/founder.png",
            nonce=self.override_nonce if self.override_nonce is not None else self.nonce,
        )


def auth_settings(*, max_active_users: int = 10) -> Settings:
    return Settings(
        environment="test",
        database_url="postgresql+asyncpg://test:test@localhost/test",
        public_base_url="https://testserver",
        session_secret="s" * 32,
        csrf_secret="c" * 32,
        google_client_id="google-id",
        google_client_secret="google-secret",
        otari_base_url="https://otari.invalid",
        otari_ai_token="test-token",
        max_active_users=max_active_users,
    )


async def make_client(db_session, provider: FakeGoogleOAuthProvider) -> AsyncClient:
    async def no_database_probe() -> None:
        return None

    async def override_session() -> AsyncIterator:
        yield db_session

    app = create_app(
        settings=auth_settings(),
        readiness_probe=no_database_probe,
        oauth_provider=provider,
        testing=True,
    )
    app.dependency_overrides[session_dependency] = override_session
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver")


async def begin_login(client: AsyncClient) -> str:
    response = await client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 307
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


async def test_login_sets_short_lived_browser_binding_cookie(db_session) -> None:
    provider = FakeGoogleOAuthProvider()

    async with await make_client(db_session, provider) as client:
        response = await client.get("/auth/google/login", follow_redirects=False)

    cookie_header = response.headers["set-cookie"]
    assert "competitor_scout_oauth_state=" in cookie_header
    assert "Max-Age=600" in cookie_header
    assert "Path=/auth/google" in cookie_header
    assert "Secure" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header


async def test_callback_rejects_valid_signed_state_without_browser_cookie(db_session) -> None:
    provider = FakeGoogleOAuthProvider()

    async with await make_client(db_session, provider) as login_client:
        state = await begin_login(login_client)

    async with await make_client(db_session, provider) as callback_client:
        response = await callback_client.get(
            "/auth/google/callback",
            params={"code": "provider-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "authentication failed"}
    assert provider.exchange_calls == 0


async def test_callback_rejects_mismatched_browser_cookie_and_clears_it(db_session) -> None:
    provider = FakeGoogleOAuthProvider()

    async with await make_client(db_session, provider) as login_client:
        state = await begin_login(login_client)

    async with await make_client(db_session, provider) as callback_client:
        callback_client.cookies.set("competitor_scout_oauth_state", "wrong-state-binding")
        response = await callback_client.get(
            "/auth/google/callback",
            params={"code": "provider-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "authentication failed"}
    assert provider.exchange_calls == 0
    assert "competitor_scout_oauth_state=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


async def test_callback_state_cannot_be_replayed_after_success(db_session) -> None:
    provider = FakeGoogleOAuthProvider()

    async with await make_client(db_session, provider) as client:
        state = await begin_login(client)
        first = await client.get(
            "/auth/google/callback",
            params={"code": "first-code", "state": state},
            follow_redirects=False,
        )
        replay = await client.get(
            "/auth/google/callback",
            params={"code": "second-code", "state": state},
            follow_redirects=False,
        )

    assert first.status_code == 307
    assert replay.status_code == 400
    assert replay.json() == {"detail": "authentication failed"}
    assert provider.exchange_calls == 1


async def test_session_resolution_rejects_disabled_revoked_expired_and_idle_sessions(
    db_session,
) -> None:
    for condition in ("disabled", "revoked", "expired", "idle"):
        user = User(
            email=f"{condition}@example.com",
            display_name=condition,
            disabled_at=NOW if condition == "disabled" else None,
        )
        session = Session(
            user=user,
            secret_hash="",
            expires_at=NOW if condition == "expired" else NOW + timedelta(days=1),
            last_seen_at=(
                NOW - timedelta(days=7) if condition == "idle" else NOW - timedelta(hours=1)
            ),
            revoked_at=NOW if condition == "revoked" else None,
        )
        secret = f"secret-{condition}"
        session.secret_hash = session_secret_hash(secret)
        db_session.add(session)
        await db_session.flush()

        assert await resolve_session(db_session, f"{session.id}.{secret}", now=NOW) is None


async def test_valid_session_refreshes_last_seen_without_storing_raw_secret(db_session) -> None:
    user = User(email="active@example.com", display_name="Active")
    db_session.add(user)
    await db_session.flush()
    session, secret = await create_session(db_session, user, now=NOW - timedelta(hours=1))

    resolved = await resolve_session(db_session, f"{session.id}.{secret}", now=NOW)

    assert resolved is not None
    assert resolved.user == user
    assert session.last_seen_at == NOW
    assert session.secret_hash != secret


async def test_google_callback_creates_user_and_delivers_csrf(db_session) -> None:
    provider = FakeGoogleOAuthProvider()

    async with await make_client(db_session, provider) as client:
        state = await begin_login(client)
        callback = await client.get(
            "/auth/google/callback",
            params={"code": "provider-code", "state": state},
            follow_redirects=False,
        )

        assert callback.status_code == 307
        cookie_header = callback.headers["set-cookie"]
        assert "Secure" in cookie_header
        assert "HttpOnly" in cookie_header
        assert "SameSite=lax" in cookie_header

        me = await client.get("/api/v1/me")
        assert me.status_code == 200
        assert me.json()["email"] == "founder@example.com"
        assert len(me.json()["csrf_token"]) == 64

    identity = await db_session.scalar(select(OAuthIdentity))
    assert identity is not None
    assert identity.provider_subject == "google-subject"


async def test_google_callback_rejects_eleventh_active_user(db_session) -> None:
    db_session.add_all(
        [
            User(email=f"user-{index}@example.com", display_name=f"User {index}")
            for index in range(10)
        ]
    )
    await db_session.flush()
    provider = FakeGoogleOAuthProvider(email="eleventh@example.com", subject="eleventh-subject")

    async with await make_client(db_session, provider) as client:
        state = await begin_login(client)
        response = await client.get(
            "/auth/google/callback",
            params={"code": "provider-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "registration is closed"}
    assert "competitor_scout_session" not in response.cookies
    assert await db_session.scalar(select(func.count(User.id))) == 10


async def test_existing_user_can_login_when_registration_is_full(db_session) -> None:
    existing = User(email="existing@example.com", display_name="Existing")
    db_session.add_all(
        [existing]
        + [
            User(email=f"user-{index}@example.com", display_name=f"User {index}")
            for index in range(9)
        ]
    )
    db_session.add(
        OAuthIdentity(provider="google", provider_subject="existing-subject", user=existing)
    )
    await db_session.flush()
    provider = FakeGoogleOAuthProvider(email=existing.email, subject="existing-subject")

    async with await make_client(db_session, provider) as client:
        state = await begin_login(client)
        response = await client.get(
            "/auth/google/callback",
            params={"code": "provider-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert "competitor_scout_session" in response.cookies
    assert await db_session.scalar(select(func.count(User.id))) == 10


async def test_disabled_users_do_not_consume_registration_capacity(db_session) -> None:
    db_session.add_all(
        [
            User(
                email=f"user-{index}@example.com",
                display_name=f"User {index}",
                disabled_at=NOW if index == 0 else None,
            )
            for index in range(10)
        ]
    )
    await db_session.flush()
    provider = FakeGoogleOAuthProvider(email="replacement@example.com", subject="replacement")

    async with await make_client(db_session, provider) as client:
        state = await begin_login(client)
        response = await client.get(
            "/auth/google/callback",
            params={"code": "provider-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 307
    active_users = await db_session.scalar(
        select(func.count(User.id)).where(User.disabled_at.is_(None))
    )
    assert active_users == 10


async def test_disabled_user_cannot_log_in(db_session) -> None:
    disabled = User(
        email="disabled@example.com",
        display_name="Disabled",
        disabled_at=NOW,
    )
    db_session.add(
        OAuthIdentity(provider="google", provider_subject="disabled-subject", user=disabled)
    )
    await db_session.flush()
    provider = FakeGoogleOAuthProvider(
        email=disabled.email,
        subject="disabled-subject",
    )

    async with await make_client(db_session, provider) as client:
        state = await begin_login(client)
        response = await client.get(
            "/auth/google/callback",
            params={"code": "provider-code", "state": state},
            follow_redirects=False,
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "account is disabled"}
    assert "competitor_scout_session" not in response.cookies


async def test_callback_rejects_invalid_state_before_provider_exchange(db_session) -> None:
    provider = FakeGoogleOAuthProvider()

    async with await make_client(db_session, provider) as client:
        response = await client.get(
            "/auth/google/callback",
            params={"code": "provider-code", "state": "tampered-state"},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "authentication failed"}
    assert provider.exchange_calls == 0


async def test_callback_rejects_nonce_mismatch(db_session) -> None:
    provider = FakeGoogleOAuthProvider()

    async with await make_client(db_session, provider) as client:
        state = await begin_login(client)
        provider.override_nonce = "wrong-nonce"
        response = await client.get(
            "/auth/google/callback",
            params={"code": "provider-code", "state": state},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "authentication failed"}


async def test_logout_requires_session_csrf_and_revokes_session(db_session) -> None:
    provider = FakeGoogleOAuthProvider()

    async with await make_client(db_session, provider) as client:
        state = await begin_login(client)
        await client.get(
            "/auth/google/callback",
            params={"code": "provider-code", "state": state},
        )
        me = await client.get("/api/v1/me")

        rejected = await client.post("/auth/logout")
        assert rejected.status_code == 403

        logout = await client.post(
            "/auth/logout",
            headers={"X-CSRF-Token": me.json()["csrf_token"]},
        )
        assert logout.status_code == 204

    session = await db_session.scalar(select(Session))
    assert session is not None
    assert session.revoked_at is not None


def test_current_user_override_is_rejected_outside_testing() -> None:
    async def override_user() -> User:
        raise AssertionError

    with pytest.raises(ValueError, match="testing=True"):
        create_app(
            settings=auth_settings(),
            readiness_probe=lambda: None,
            current_user_override=override_user,
        )

    app = create_app(
        settings=auth_settings(),
        readiness_probe=lambda: None,
        testing=True,
        current_user_override=override_user,
    )
    assert app.dependency_overrides[current_user] is override_user
