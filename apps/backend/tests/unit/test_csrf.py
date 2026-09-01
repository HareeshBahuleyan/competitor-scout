from uuid import uuid4

from competitor_scout.security.csrf import csrf_token, csrf_valid


def test_csrf_token_is_tied_to_session_and_cookie_secret() -> None:
    session_id = uuid4()
    token = csrf_token(session_id, "cookie-secret", "c" * 32)

    assert csrf_valid(session_id, "cookie-secret", token, "c" * 32)
    assert not csrf_valid(uuid4(), "cookie-secret", token, "c" * 32)
    assert not csrf_valid(session_id, "different-secret", token, "c" * 32)
