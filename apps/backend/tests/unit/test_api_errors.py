from __future__ import annotations

import logging

from starlette.requests import Request

from competitor_scout.api.errors import unhandled_exception_handler


async def test_unhandled_exception_logs_only_safe_error_type(caplog) -> None:
    secret = "Bearer super-secret-provider-token"
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/runs",
            "headers": [],
        }
    )

    with caplog.at_level(logging.ERROR, logger="competitor_scout.api.errors"):
        response = await unhandled_exception_handler(request, RuntimeError(secret))

    assert response.status_code == 500
    assert response.body is not None and secret.encode() not in response.body
    assert secret not in caplog.text
    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage() == "unhandled_request_error"
    assert caplog.records[0].error_type == "RuntimeError"
    assert caplog.records[0].exc_info is None
