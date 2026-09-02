import json
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from competitor_scout.agents.client import (
    OtariClient,
    OtariError,
    OtariMetadata,
    hosted_json_schema,
)
from competitor_scout.agents.contracts import ChildTaskPayload, ScoutPlan
from competitor_scout.config import Settings

FIXTURE = Path(__file__).parents[1] / "fixtures" / "otari" / "chat_completion.json"


def settings(*, ai_token: str = "hosted-ai-token", cost_lookup_attempts: int = 3) -> Settings:
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
        otari_cost_lookup_attempts=cost_lookup_attempts,
        otari_cost_lookup_delay_seconds=0.01,
    )


def fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def test_child_wire_schema_requires_provider_compatible_fields() -> None:
    schema = hosted_json_schema(ChildTaskPayload)
    evidence_schema = schema["$defs"]["ChildEvidencePayload"]

    assert set(schema["required"]) == set(schema["properties"])
    assert set(evidence_schema["required"]) == set(evidence_schema["properties"])
    assert evidence_schema["properties"]["source_url"]["type"] == "string"
    assert "format" not in evidence_schema["properties"]["source_url"]
    assert "format" not in json.dumps(evidence_schema["properties"]["published_at"])


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


async def test_mcp_server_ids_are_sent_as_top_level_field_not_a_tool() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads((await request.aread()).decode())
        assert body["mcp_server_ids"] == ["11111111-1111-1111-1111-111111111111"]
        assert "tools" not in body
        assert body["reasoning_effort"] == "none"
        assert body["parallel_tool_calls"] is False
        assert body["max_tool_iterations"] == 4
        assert "response_format" not in body
        document = json.loads(fixture_bytes())
        content = document["choices"][0]["message"]["content"]
        document["choices"][0]["message"]["content"] = f"```json\n{content}\n```"
        return httpx.Response(200, json=document)

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        await client.structured_completion(
            model="competitor-scout-child",
            messages=[{"role": "user", "content": "Review the assigned pages."}],
            output_type=ScoutPlan,
            session_label="run:firecrawl",
            max_completion_tokens=1024,
            deadline_seconds=5,
            mcp_server_ids=["11111111-1111-1111-1111-111111111111"],
            max_tool_iterations=4,
        )


async def test_web_search_and_mcp_server_ids_are_mutually_exclusive() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200))
    async with OtariClient(settings(), transport=transport) as client:
        with pytest.raises(ValueError, match="mutually exclusive"):
            await client.structured_completion(
                model="competitor-scout-child",
                messages=[{"role": "user", "content": "Review."}],
                output_type=ScoutPlan,
                session_label="run:conflict",
                max_completion_tokens=1024,
                deadline_seconds=5,
                enable_web_search=True,
                mcp_server_ids=["11111111-1111-1111-1111-111111111111"],
            )


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


async def test_tool_iteration_limit_is_classified_without_exposing_response_body() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={"detail": "Exceeded max_tool_iterations=6", "response_body": "secret"},
        )

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OtariError) as raised:
            await client.structured_completion(
                model="competitor-scout-main",
                messages=[{"role": "user", "content": "Discover."}],
                output_type=ScoutPlan,
                session_label="run:tool-limit",
                max_completion_tokens=100,
                deadline_seconds=5,
            )

    assert raised.value.code == "otari_tool_iteration_limit"
    assert raised.value.retryable is False
    assert "max_tool_iterations" not in str(raised.value)
    assert "secret" not in str(raised.value)


@pytest.mark.parametrize(
    "detail",
    [
        "Workspace USD budget exceeded: $5.00 spent of $5.00 daily limit. "
        "Contact your organization admin to raise the limit.",
        "API key request budget exceeded. Contact your organization admin to raise the limit.",
    ],
)
async def test_hosted_budget_exhaustion_is_classified_without_exposing_detail(
    detail: str,
) -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": detail, "response_body": "secret"})

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OtariError) as raised:
            await client.structured_completion(
                model="general-mzai-then-openai-models",
                messages=[{"role": "user", "content": "Plan."}],
                output_type=ScoutPlan,
                session_label="run:budget",
                max_completion_tokens=100,
                deadline_seconds=5,
            )

    assert raised.value.code == "otari_budget_exceeded"
    assert raised.value.retryable is False
    assert raised.value.status_code == 403
    assert detail not in str(raised.value)
    assert "secret" not in str(raised.value)


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


@pytest.mark.parametrize(
    "case", ["malformed_json", "missing_choice", "refusal", "truncated", "schema"]
)
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
        if case == "truncated":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {"content": '{"tasks": []}'},
                        }
                    ]
                },
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
    if case == "truncated":
        expected = "otari_output_truncated"
    assert raised.value.code == expected
    assert "provider detail" not in str(raised.value)


async def test_schema_error_retains_safe_response_metadata_and_validation_locations() -> None:
    invalid_content = json.dumps(
        {
            "tasks": [
                {
                    "kind": "private-provider-value",
                    "objective": "Research a bounded topic.",
                    "source_urls": [],
                    "search_query": "bounded topic",
                    "expected_category": "product",
                    "max_search_calls": 1,
                    "completion_criteria": "Return quoted evidence or none.",
                    "private-provider-field": "private-provider-detail",
                }
            ]
        }
    )

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": invalid_content},
                    }
                ],
                "usage": {
                    "prompt_tokens": 23,
                    "completion_tokens": 11,
                    "cost_usd": "0.0042",
                    "pricing_source": "hosted_catalog",
                },
            },
            headers={"X-Otari-Request-ID": "req_schema_failure"},
        )

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OtariError) as raised:
            await client.structured_completion(
                model="competitor-scout-main",
                messages=[{"role": "user", "content": "Plan."}],
                output_type=ScoutPlan,
                session_label="run:schema-metadata",
                max_completion_tokens=100,
                deadline_seconds=5,
            )

    error = raised.value
    assert error.code == "otari_schema_error"
    assert error.metadata is not None
    assert error.metadata.request_id == "req_schema_failure"
    assert error.metadata.finish_reason == "stop"
    assert error.metadata.usage.input_tokens == 23
    assert error.metadata.usage.output_tokens == 11
    assert "$.tasks[0].kind:enum" in error.validation_issues
    assert "$.tasks[0].<unexpected_field>:extra_forbidden" in error.validation_issues
    assert "private-provider-value" not in str(error.validation_issues)
    assert "private-provider-field" not in str(error.validation_issues)
    assert "private-provider-detail" not in str(error.validation_issues)
    assert "private-provider-value" not in str(error)


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


def completion_without_cost() -> bytes:
    document = json.loads(FIXTURE.read_text())
    document["usage"] = {
        "prompt_tokens": 101,
        "completion_tokens": 37,
        "total_tokens": 138,
    }
    return json.dumps(document).encode()


def request_cost_document(
    *,
    cost_usd: str = "0.004210",
    usage_status: str = "reported",
    pricing_source: str | None = "genai_prices",
) -> dict[str, object]:
    return {
        "cost_usd": cost_usd,
        "currency": "USD",
        "request_id": "req_settle",
        "status": "completed",
        "outcome": "success",
        "usage_status": usage_status,
        "pricing": {"source": pricing_source, "reference": "openai:model", "version": "0.1.1"},
    }


async def completion_with_cost_lookup(
    lookup: Callable[[int], httpx.Response],
    *,
    settings_override: Settings | None = None,
) -> tuple[OtariMetadata, list[str]]:
    lookups: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                200,
                content=completion_without_cost(),
                headers={"X-Otari-Request-ID": "req_settle"},
            )
        lookups.append(request.url.path)
        assert request.headers["authorization"] == "Bearer hosted-ai-token"
        return lookup(len(lookups))

    async with OtariClient(
        settings_override or settings(),
        transport=httpx.MockTransport(handler),
    ) as client:
        _result, metadata = await client.structured_completion(
            model="competitor-scout-main",
            messages=[{"role": "user", "content": "Plan."}],
            output_type=ScoutPlan,
            session_label="run:settlement",
            max_completion_tokens=100,
            deadline_seconds=5,
        )

    return metadata, lookups


async def test_settled_cost_is_looked_up_when_the_response_omits_it() -> None:
    metadata, lookups = await completion_with_cost_lookup(
        lambda _attempt: httpx.Response(200, json=request_cost_document())
    )

    assert lookups == ["/api/v1/request-costs/req_settle"]
    assert metadata.usage.cost_usd == Decimal("0.004210")
    assert metadata.usage.pricing_source == "genai_prices"
    assert metadata.usage.input_tokens == 101
    assert metadata.usage.output_tokens == 37


async def test_pending_settlement_is_retried_until_it_completes() -> None:
    def lookup(attempt: int) -> httpx.Response:
        if attempt == 1:
            return httpx.Response(202, json={"status": "pending"})
        return httpx.Response(200, json=request_cost_document(cost_usd="0.000110"))

    metadata, lookups = await completion_with_cost_lookup(lookup)

    assert len(lookups) == 2
    assert metadata.usage.cost_usd == Decimal("0.000110")


async def test_settlement_that_stays_pending_leaves_the_cost_unknown() -> None:
    metadata, lookups = await completion_with_cost_lookup(
        lambda _attempt: httpx.Response(202, json={"status": "pending"}),
        settings_override=settings(cost_lookup_attempts=2),
    )

    assert len(lookups) == 2
    assert metadata.usage.cost_usd is None
    assert metadata.usage.pricing_source is None


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, json={"detail": "Not Found"}),
        httpx.Response(410, json={"detail": "Gone"}),
        httpx.Response(500, json={"detail": "boom"}),
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"cost_usd": "0.000110", "usage_status": "unavailable"}),
        httpx.Response(200, json=request_cost_document(pricing_source=None)),
        httpx.Response(200, json=request_cost_document(usage_status="unavailable")),
        httpx.Response(200, json=request_cost_document(cost_usd="not-a-number")),
    ],
)
async def test_unusable_settlements_never_record_a_cost(response: httpx.Response) -> None:
    metadata, lookups = await completion_with_cost_lookup(lambda _attempt: response)

    assert len(lookups) == 1
    assert metadata.usage.cost_usd is None
    assert metadata.usage.pricing_source is None


async def test_settlement_lookup_failure_does_not_fail_the_completion() -> None:
    def lookup(_attempt: int) -> httpx.Response:
        raise httpx.ConnectError("settlement lookup with hosted-ai-token")

    metadata, lookups = await completion_with_cost_lookup(lookup)

    assert len(lookups) == 1
    assert metadata.request_id == "req_settle"
    assert metadata.usage.cost_usd is None


async def test_inline_settled_cost_skips_the_lookup() -> None:
    lookups = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal lookups
        if request.url.path != "/v1/chat/completions":
            lookups += 1
        return httpx.Response(
            200,
            content=fixture_bytes(),
            headers={"X-Otari-Request-ID": "req_inline"},
        )

    async with OtariClient(settings(), transport=httpx.MockTransport(handler)) as client:
        _result, metadata = await client.structured_completion(
            model="competitor-scout-main",
            messages=[{"role": "user", "content": "Plan."}],
            output_type=ScoutPlan,
            session_label="run:inline-cost",
            max_completion_tokens=100,
            deadline_seconds=5,
        )

    assert lookups == 0
    assert metadata.usage.cost_usd == Decimal("0.001234")
    assert metadata.usage.pricing_source == "hosted_catalog"
