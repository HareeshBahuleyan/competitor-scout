import logging
from collections.abc import Mapping

import structlog

SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "csrf_secret",
    "csrf_token",
    "database_url",
    "e2e_auth_secret",
    "google_client_secret",
    "id_token",
    "model_response",
    "oauth_token",
    "otari_ai_token",
    "page_content",
    "prompt",
    "quoted_evidence",
    "quoted_text",
    "refresh_token",
    "response_body",
    "session_secret",
    "source_content",
}


def _redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if str(key).casefold() in SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value


def redact_sensitive(_: object, __: str, event_dict: dict[str, object]) -> dict[str, object]:
    return _redact(event_dict)  # type: ignore[return-value]


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            redact_sensitive,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )
