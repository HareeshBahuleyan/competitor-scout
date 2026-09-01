import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from competitor_scout.agents.client import OtariClient, OtariError
from competitor_scout.agents.contracts import ScoutPlan
from competitor_scout.config import Settings

FIXTURE = Path(__file__).parents[1] / "fixtures" / "otari" / "chat_completion.json"


def settings(*, ai_token: str = "hosted-ai-token") -> Settings:
    return Settings(
        environment="test",
        database_url="postgresql+asyncpg://test:test@localhost/test",
        public_base_url="https://testserver",
        session_secret="s" * 32,
        csrf_secret="c" * 32,
        google_client_id="google-id",
        google_client_secret="google-secret",
        otari_base_url="https://otari.invalid",
        otari_ai_token=ai_token,
    )


def fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


async def test_structured_completion_sends_hosted_contract_and_parses_usage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer hosted-ai-token"
        body = json.loads((await request.aread()).decode())
        assert body["model"] == "competitor-scout-main"
        assert body["session_label"] == "run:synthetic-001"
        assert body["max_completion_tokens"] == 2048
        assert body["reasoning_effort"] == "none"
        assert body["parallel_tool_calls"] is False
        assert body["max_tool_iterations"] == 3
        assert body["tools"] == [{"type": "otari_web_search"}]
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["strict"] is True
        schema = body["response_format"]["json_schema"]["schema"]
        assert schema["additionalProperties"] is False
        planned_task_schema = schema["$defs"]["PlannedChildTask"]
        source_url_schema = planned_task_schema["properties"]["source_urls"]["items"]
        assert "format" not in source_url_schema
        assert set(planned_task_schema["required"]) == set(planned_task_schema["properties"])
        serialized_schema = json.dumps(schema)
        for keyword in ("default", "format"):
            assert f'"{keyword}"' not in serialized_schema
        assert request.extensions["timeout"]["read"] == 12.0
        return httpx.Response(
            200,
            content=fixture_bytes(),
            headers={"Content-Type": "application/json", "X-Otari-Request-ID": "req_123"},
        )

    client = OtariClient(settings(), transport=httpx.MockTransport(handler))
    result, metadata = await client.structured_completion(
        model="competitor-scout-main",
        messages=[{"role": "user", "content": "Plan a synthetic competitor scan."}],
        output_type=ScoutPlan,
        session_label="run:synthetic-001",
        max_completion_tokens=2048,
        deadline_seconds=12,
        enable_web_search=True,
        max_tool_iterations=3,
    )
    await client.aclose()

    assert len(result.tasks) == 1
    assert metadata.request_id == "req_123"
    assert metadata.usage.input_tokens == 101
    assert metadata.usage.output_tokens == 37
    assert metadata.usage.tool_calls is None
    assert metadata.usage.cost_usd == Decimal("0.001234")
    assert metadata.usage.pricing_source == "hosted_catalog"


async def test_omits_optional_tool_when_web_search_is_disabled() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer hosted-ai-token"
        body = json.loads((await request.aread()).decode())
        assert "tools" not in body
        assert "reasoning_effort" not in body
        assert "parallel_tool_calls" not in body
        assert "max_tool_iterations" not in body
        return httpx.Response(200, content=fixture_bytes())

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        await client.structured_completion(
            model="competitor-scout-main",
            messages=[{"role": "user", "content": "Plan."}],
            output_type=ScoutPlan,
            session_label="run:no-search",
            max_completion_tokens=1024,
            deadline_seconds=5,
            enable_web_search=False,
            max_tool_iterations=1,
        )

    assert client.is_closed


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (400, "otari_bad_request", False),
        (401, "otari_authentication_error", False),
        (402, "otari_budget_or_pricing_error", False),
        (403, "otari_permission_denied", False),
        (422, "otari_invalid_request", False),
        (429, "otari_rate_limited", True),
        (500, "otari_upstream_error", True),
        (503, "otari_upstream_error", True),
    ],
)
async def test_http_errors_are_safely_mapped(
    status: int,
    code: str,
    retryable: bool,
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": {"message": "provider-body-secret"}},
            headers={"Retry-After": "7"},
        )

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OtariError) as raised:
            await client.structured_completion(
                model="competitor-scout-main",
                messages=[{"role": "user", "content": "Plan."}],
                output_type=ScoutPlan,
                session_label="run:error",
                max_completion_tokens=100,
                deadline_seconds=5,
            )

    assert raised.value.code == code
    assert raised.value.retryable is retryable
    assert raised.value.status_code == status
    assert raised.value.retry_after == "7"
    assert "provider-body-secret" not in str(raised.value)
    assert "hosted-ai-token" not in str(raised.value)


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (httpx.ReadTimeout("upstream timeout with hosted-ai-token"), "otari_timeout"),
        (httpx.ConnectError("network failure with hosted-ai-token"), "otari_network_error"),
    ],
)
async def test_transport_errors_are_retryable_and_sanitized(
    exception: httpx.RequestError,
    code: str,
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        raise exception

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OtariError) as raised:
            await client.structured_completion(
                model="competitor-scout-main",
                messages=[{"role": "user", "content": "Plan."}],
                output_type=ScoutPlan,
                session_label="run:transport-error",
                max_completion_tokens=100,
                deadline_seconds=5,
            )

    assert raised.value.code == code
    assert raised.value.retryable is True
    assert "hosted-ai-token" not in str(raised.value)
    assert raised.value.__cause__ is None


@pytest.mark.parametrize("case", ["malformed_json", "missing_choice", "refusal", "schema"])
async def test_invalid_success_responses_fail_safely(case: str) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        if case == "malformed_json":
            return httpx.Response(200, content=b"not-json")
        if case == "missing_choice":
            return httpx.Response(200, json={"usage": {}})
        if case == "refusal":
            return httpx.Response(
                200,
                json={"choices": [{"message": {"refusal": "provider detail", "content": None}}]},
            )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"tasks": [{"kind": "run_shell"}]}'}}]},
        )

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OtariError) as raised:
            await client.structured_completion(
                model="competitor-scout-main",
                messages=[{"role": "user", "content": "Plan."}],
                output_type=ScoutPlan,
                session_label="run:invalid-response",
                max_completion_tokens=100,
                deadline_seconds=5,
            )

    expected = "otari_refusal" if case == "refusal" else "otari_invalid_response"
    if case == "schema":
        expected = "otari_schema_error"
    assert raised.value.code == expected
    assert "provider detail" not in str(raised.value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"session_label": "x" * 256},
        {"max_completion_tokens": 0},
        {"deadline_seconds": 0},
        {"max_tool_iterations": 0},
        {"max_tool_iterations": 26},
    ],
)
async def test_request_bounds_are_checked_before_transport(kwargs: dict[str, object]) -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=fixture_bytes())

    arguments = {
        "model": "competitor-scout-main",
        "messages": [{"role": "user", "content": "Plan."}],
        "output_type": ScoutPlan,
        "session_label": "run:bounded",
        "max_completion_tokens": 100,
        "deadline_seconds": 5,
        "max_tool_iterations": 1,
    }
    arguments.update(kwargs)
    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            await client.structured_completion(**arguments)  # type: ignore[arg-type]

    assert calls == 0


async def test_web_search_requires_a_tool_round_and_final_response_iteration() -> None:
    calls = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=fixture_bytes())

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="at least 2"):
            await client.structured_completion(
                model="competitor-scout-main",
                messages=[{"role": "user", "content": "Plan."}],
                output_type=ScoutPlan,
                session_label="run:web-search",
                max_completion_tokens=100,
                deadline_seconds=5,
                enable_web_search=True,
                max_tool_iterations=1,
            )

    assert calls == 0


async def test_web_search_defaults_to_two_tool_iterations() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads((await request.aread()).decode())
        assert body["max_tool_iterations"] == 2
        return httpx.Response(200, content=fixture_bytes())

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        await client.structured_completion(
            model="competitor-scout-main",
            messages=[{"role": "user", "content": "Plan."}],
            output_type=ScoutPlan,
            session_label="run:web-search-default",
            max_completion_tokens=100,
            deadline_seconds=5,
            enable_web_search=True,
        )
