import hashlib
import hmac
from uuid import UUID


def csrf_token(session_id: UUID, cookie_secret: str, signing_secret: str) -> str:
    message = f"{session_id}.{cookie_secret}"
    return hmac.new(signing_secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def csrf_valid(
    session_id: UUID,
    cookie_secret: str,
    supplied: str,
    signing_secret: str,
) -> bool:
    return hmac.compare_digest(
        csrf_token(session_id, cookie_secret, signing_secret),
        supplied,
    )
