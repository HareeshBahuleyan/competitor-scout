import asyncio
import json
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from types import TracebackType
from typing import Any, Self, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from competitor_scout.config import Settings

T = TypeVar("T", bound=BaseModel)

COST_LOOKUP_TIMEOUT_SECONDS = 3.0
"""Per-attempt budget for one settled-cost lookup.

Kept well inside the run's planning, child, and synthesis deadlines: an
unavailable settlement must not consume the deadline of the work it prices.
"""


def hosted_json_schema(output_type: type[BaseModel]) -> dict[str, Any]:
    schema = output_type.model_json_schema()
    unsupported_keywords = {"default", "format"}

    def enforce_hosted_subset(value: object) -> None:
        if isinstance(value, dict):
            for keyword in unsupported_keywords:
                value.pop(keyword, None)
            properties = value.get("properties")
            if isinstance(properties, dict):
                value["required"] = list(properties)
            for child in value.values():
                enforce_hosted_subset(child)
        elif isinstance(value, list):
            for child in value:
                enforce_hosted_subset(child)

    enforce_hosted_subset(schema)
    return schema


@dataclass(frozen=True)
class OtariUsage:
    input_tokens: int
    output_tokens: int
    tool_calls: int | None
    cost_usd: Decimal | None
    pricing_source: str | None


@dataclass(frozen=True)
class OtariMetadata:
    request_id: str | None
    usage: OtariUsage


class OtariError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool,
        status_code: int | None = None,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(f"Otari request failed ({code})")
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after = retry_after


class OtariClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        token = settings.otari_ai_token.get_secret_value()
        self._client = httpx.AsyncClient(
            base_url=str(settings.otari_base_url).rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(60.0),
            transport=transport,
        )
        self._cost_lookup_attempts = settings.otari_cost_lookup_attempts
        self._cost_lookup_delay_seconds = settings.otari_cost_lookup_delay_seconds

    @property
    def is_closed(self) -> bool:
        return self._client.is_closed

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def structured_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        output_type: type[T],
        session_label: str,
        max_completion_tokens: int,
        deadline_seconds: float,
        enable_web_search: bool = False,
        max_tool_iterations: int | None = None,
    ) -> tuple[T, OtariMetadata]:
        """Request a structured result.

        ``max_tool_iterations`` bounds the gateway's model/tool loop. It is not an exact
        web-search-call cap, so the application must still enforce its own search budget.
        """
        effective_tool_iterations = (
            (2 if enable_web_search else 1) if max_tool_iterations is None else max_tool_iterations
        )
        self._validate_request_bounds(
            model=model,
            messages=messages,
            session_label=session_label,
            max_completion_tokens=max_completion_tokens,
            deadline_seconds=deadline_seconds,
            max_tool_iterations=effective_tool_iterations,
            enable_web_search=enable_web_search,
        )
        body: dict[str, object] = {
            "model": model,
            "messages": messages,
            "session_label": session_label,
            "max_completion_tokens": max_completion_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_type.__name__,
                    "strict": True,
                    "schema": hosted_json_schema(output_type),
                },
            },
        }
        if enable_web_search:
            # Otari exposes managed web search as a function tool. The configured
            # OpenAI GPT-5.6 models reject function tools on /v1/chat/completions
            # unless reasoning_effort is explicitly "none".
            body["reasoning_effort"] = "none"
            body["parallel_tool_calls"] = False
            body["max_tool_iterations"] = effective_tool_iterations
            body["tools"] = [{"type": "otari_web_search"}]

        try:
            async with asyncio.timeout(deadline_seconds):
                response = await self._client.post(
                    "/v1/chat/completions",
                    json=body,
                    timeout=httpx.Timeout(deadline_seconds),
                )
        except (TimeoutError, httpx.TimeoutException):
            raise OtariError("otari_timeout", retryable=True) from None
        except httpx.RequestError:
            raise OtariError("otari_network_error", retryable=True) from None

        if response.status_code >= 400:
            raise self._http_error(response) from None

        document = self._response_document(response)
        content = self._structured_content(document)
        try:
            result = output_type.model_validate_json(content)
        except ValidationError as exc:
            code = (
                "otari_invalid_response"
                if any(error["type"] == "json_invalid" for error in exc.errors())
                else "otari_schema_error"
            )
            raise OtariError(code, retryable=False) from None

        request_id = response.headers.get("X-Otari-Request-ID")
        usage = self._usage(document)
        if usage.cost_usd is None and request_id:
            usage = await self._settled_usage(usage, request_id)

        return result, OtariMetadata(request_id=request_id, usage=usage)

    async def _settled_usage(self, usage: OtariUsage, request_id: str) -> OtariUsage:
        """Fill in the settled cost that the response did not carry inline.

        Otari attaches ``cost_usd`` to the completion only when the platform
        settles within the gateway's inline budget; otherwise the authoritative
        amount is served by ``/api/v1/request-costs/{request_id}``, which answers
        ``202`` while an attempt is still pending. A lookup that fails or stays
        pending leaves the cost unknown rather than recording a misleading zero.
        """
        settlement = await self._request_cost(request_id)
        if settlement is None:
            return usage
        cost_usd, pricing_source = settlement
        return replace(usage, cost_usd=cost_usd, pricing_source=pricing_source)

    async def _request_cost(self, request_id: str) -> tuple[Decimal, str] | None:
        for attempt in range(1, self._cost_lookup_attempts + 1):
            try:
                response = await self._client.get(
                    f"/api/v1/request-costs/{request_id}",
                    timeout=httpx.Timeout(COST_LOOKUP_TIMEOUT_SECONDS),
                )
            except httpx.HTTPError:
                return None
            if response.status_code == 200:
                return self._settlement(response)
            if response.status_code != 202:
                return None
            if attempt == self._cost_lookup_attempts:
                return None
            await asyncio.sleep(self._cost_lookup_delay_seconds)
        return None

    @classmethod
    def _settlement(cls, response: httpx.Response) -> tuple[Decimal, str] | None:
        try:
            document = json.loads(response.content, parse_float=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(document, dict) or document.get("usage_status") != "reported":
            return None
        pricing = document.get("pricing")
        pricing_source = pricing.get("source") if isinstance(pricing, dict) else None
        cost = cls._cost(document.get("cost_usd"))
        # An unpriced settlement reports a placeholder amount, so a missing
        # pricing source has to stay unknown instead of reading as a free call.
        if cost is None or not isinstance(pricing_source, str):
            return None
        return cost, pricing_source

    @staticmethod
    def _validate_request_bounds(
        *,
        model: str,
        messages: list[dict[str, str]],
        session_label: str,
        max_completion_tokens: int,
        deadline_seconds: float,
        max_tool_iterations: int,
        enable_web_search: bool,
    ) -> None:
        if not model or len(model) > 255:
            raise ValueError("model must contain at most 255 characters")
        if not messages or len(messages) > 100:
            raise ValueError("messages must contain between 1 and 100 items")
        if not session_label or len(session_label) > 255:
            raise ValueError("session_label must contain at most 255 characters")
        if not 1 <= max_completion_tokens <= 100_000:
            raise ValueError("max_completion_tokens is outside the allowed range")
        if not 0 < deadline_seconds <= 900:
            raise ValueError("deadline_seconds is outside the allowed range")
        if not 1 <= max_tool_iterations <= 25:
            raise ValueError("max_tool_iterations is outside the allowed range")
        if enable_web_search and max_tool_iterations < 2:
            raise ValueError("web search requires at least 2 max_tool_iterations")

    @staticmethod
    def _http_error(response: httpx.Response) -> OtariError:
        status = response.status_code
        code, retryable = {
            400: ("otari_bad_request", False),
            401: ("otari_authentication_error", False),
            402: ("otari_budget_or_pricing_error", False),
            403: ("otari_permission_denied", False),
            422: ("otari_invalid_request", False),
            429: ("otari_rate_limited", True),
        }.get(
            status,
            ("otari_upstream_error", status >= 500),
        )
        if status == 422 and OtariClient._is_tool_iteration_limit(response):
            code = "otari_tool_iteration_limit"
        return OtariError(
            code,
            retryable=retryable,
            status_code=status,
            retry_after=response.headers.get("Retry-After"),
        )

    @staticmethod
    def _is_tool_iteration_limit(response: httpx.Response) -> bool:
        try:
            document = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False
        if not isinstance(document, dict):
            return False
        detail = document.get("detail")
        if not isinstance(detail, str):
            return False
        prefix = "Exceeded max_tool_iterations="
        return detail.startswith(prefix) and detail.removeprefix(prefix).isdigit()

    @staticmethod
    def _response_document(response: httpx.Response) -> dict[str, Any]:
        try:
            document = json.loads(response.content, parse_float=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise OtariError("otari_invalid_response", retryable=False) from None
        if not isinstance(document, dict):
            raise OtariError("otari_invalid_response", retryable=False)
        return document

    @staticmethod
    def _structured_content(document: dict[str, Any]) -> str:
        try:
            choice = document["choices"][0]
            message = choice["message"]
            if message.get("refusal"):
                raise OtariError("otari_refusal", retryable=False)
            content = message["content"]
        except OtariError:
            raise
        except (IndexError, KeyError, TypeError):
            raise OtariError("otari_invalid_response", retryable=False) from None
        if not isinstance(content, str):
            raise OtariError("otari_invalid_response", retryable=False)
        return content

    @classmethod
    def _usage(cls, document: dict[str, Any]) -> OtariUsage:
        usage = document.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return OtariUsage(
            input_tokens=cls._non_negative_int(
                usage.get("input_tokens", usage.get("prompt_tokens"))
            )
            or 0,
            output_tokens=cls._non_negative_int(
                usage.get("output_tokens", usage.get("completion_tokens"))
            )
            or 0,
            tool_calls=cls._non_negative_int(usage.get("tool_calls")),
            cost_usd=cls._cost(usage.get("cost_usd")),
            pricing_source=(
                usage["pricing_source"] if isinstance(usage.get("pricing_source"), str) else None
            ),
        )

    @staticmethod
    def _non_negative_int(value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    @staticmethod
    def _cost(value: object) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            cost = value if isinstance(value, Decimal) else Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return cost if cost >= 0 else None
