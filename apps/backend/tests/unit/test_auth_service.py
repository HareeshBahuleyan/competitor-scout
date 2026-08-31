from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from competitor_scout.services.auth import (
    InvalidOAuthState,
    create_oauth_state,
    normalize_email,
    parse_session_cookie,
    session_secret_hash,
    validate_oauth_state,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def test_email_normalization_is_stable() -> None:
    assert normalize_email(" Founder@Example.COM ") == "founder@example.com"


def test_session_hash_does_not_store_secret() -> None:
    digest = session_secret_hash("secret-value")

    assert digest != "secret-value"
    assert len(digest) == 64


def test_opaque_cookie_parses_uuid_and_secret() -> None:
    session_id = uuid4()

    assert parse_session_cookie(f"{session_id}.cookie-secret") == (
        session_id,
        "cookie-secret",
    )


@pytest.mark.parametrize(
    "value",
    [None, "", "not-a-uuid.secret", f"{uuid4()}.", f"{uuid4()}.secret.extra"],
)
def test_malformed_opaque_cookie_is_rejected(value: str | None) -> None:
    assert parse_session_cookie(value) is None


def test_oauth_state_round_trip_returns_nonce() -> None:
    state, nonce = create_oauth_state("s" * 32, now=NOW)

    assert validate_oauth_state(state, "s" * 32, now=NOW + timedelta(minutes=1)) == nonce


def test_oauth_state_rejects_tampering_and_expiry() -> None:
    state, _ = create_oauth_state("s" * 32, now=NOW)

    with pytest.raises(InvalidOAuthState):
        validate_oauth_state(f"{state}x", "s" * 32, now=NOW)
    with pytest.raises(InvalidOAuthState):
        validate_oauth_state(state, "s" * 32, now=NOW + timedelta(minutes=11))
