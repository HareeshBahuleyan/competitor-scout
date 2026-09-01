from __future__ import annotations

import logging
import uuid
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


def _title(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP Error"


def problem_response(
    *,
    status_code: int,
    detail: str,
    request_id: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        headers=headers,
        content={
            "type": "about:blank",
            "title": _title(status_code),
            "status": status_code,
            "detail": detail,
            "request_id": request_id,
        },
    )


def _request_id(request: Request) -> str:
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str) and existing:
        return existing
    generated = str(uuid.uuid4())
    request.state.request_id = generated
    return generated


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else _title(exc.status_code)
    return problem_response(
        status_code=exc.status_code,
        detail=detail,
        request_id=_request_id(request),
        headers=exc.headers,
    )


async def validation_exception_handler(
    request: Request,
    _exc: RequestValidationError,
) -> JSONResponse:
    return problem_response(
        status_code=422,
        detail="request validation failed",
        request_id=_request_id(request),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_request_error",
        extra={"error_type": type(exc).__name__},
    )
    return problem_response(
        status_code=500,
        detail="internal server error",
        request_id=_request_id(request),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
