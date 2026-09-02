import hashlib
import unicodedata
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import datetime

from pydantic import HttpUrl, TypeAdapter, ValidationError

from competitor_scout.agents.contracts import (
    ChildTaskKind,
    ChildTaskPayload,
    ChildTaskResult,
    EvidenceCandidate,
    SourceType,
)
from competitor_scout.security.urls import UnsafeSourceUrl, validate_public_https_url

type UrlValidator = Callable[[str], Awaitable[str]]

NEWS_SCOPE_GUARD_NOTE = (
    "Inspected-URL membership is an offline app guard only; real hosted web-search "
    "provenance remains staging-gated before production enablement."
)
HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


@dataclass(frozen=True)
class NormalizedEvidence:
    source_url: str
    source_title: str
    source_type: SourceType
    quoted_text: str
    normalized_claim: str
    published_at: datetime | None
    confidence: float
    limitations: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True)
class RejectedEvidence:
    index: int
    source_url: str
    reason: str


def _validation_reason(prefix: str, error: ValidationError) -> str:
    first = error.errors(include_url=False, include_context=False, include_input=False)[0]
    location = prefix
    for part in first["loc"]:
        location += f"[{part}]" if isinstance(part, int) else f".{part}"
    return f"{location}:{first['type']}"


def normalize_child_payload(
    payload: ChildTaskPayload,
) -> tuple[ChildTaskResult, list[str]]:
    """Convert provider-compatible child output into the strict domain contract.

    URL and datetime formats are not available in the hosted schema subset, so
    invalid individual values are rejected here without discarding unrelated
    evidence from the same bounded response.
    """

    sources_inspected: list[HttpUrl] = []
    evidence: list[EvidenceCandidate] = []
    rejected: list[str] = []

    for index, value in enumerate(payload.sources_inspected):
        try:
            sources_inspected.append(HTTP_URL_ADAPTER.validate_python(value))
        except ValidationError as error:
            rejected.append(_validation_reason(f"sources_inspected[{index}]", error))

    for index, candidate in enumerate(payload.evidence):
        try:
            evidence.append(EvidenceCandidate.model_validate(candidate.model_dump(), strict=False))
        except ValidationError as error:
            rejected.append(_validation_reason(f"evidence[{index}]", error))

    return (
        ChildTaskResult(
            sources_inspected=sources_inspected,
            evidence=evidence,
            limitations=payload.limitations,
        ),
        rejected,
    )


def _normalized_quote(value: str) -> str:
    without_controls = "".join(
        " " if unicodedata.category(character).startswith("C") else character for character in value
    )
    return " ".join(without_controls.split())


async def _canonical_scope(
    values: Iterable[str],
    *,
    url_validator: UrlValidator,
) -> set[str]:
    canonical: set[str] = set()
    for value in sorted(str(item) for item in values):
        try:
            normalized = await url_validator(value)
        except (UnsafeSourceUrl, TypeError, ValueError):
            continue
        if isinstance(normalized, str) and normalized:
            canonical.add(normalized)
    return canonical


async def validate_evidence_scope(
    candidates: Iterable[EvidenceCandidate],
    *,
    approved_urls: Iterable[str],
    inspected_urls: Iterable[str],
    task_kind: ChildTaskKind | str,
    url_validator: UrlValidator = validate_public_https_url,
) -> tuple[list[NormalizedEvidence], list[RejectedEvidence]]:
    """Normalize and scope evidence without fetching source content.

    For news tasks, inspected-URL membership is only the local/offline application
    guard described by ``NEWS_SCOPE_GUARD_NOTE``. Hosted search provenance must remain
    staging-gated independently.
    """

    try:
        kind = ChildTaskKind(task_kind)
    except ValueError:
        raise ValueError("unsupported child task kind") from None

    allowed = await _canonical_scope(
        approved_urls if kind is ChildTaskKind.FIRST_PARTY_SOURCE_REVIEW else inspected_urls,
        url_validator=url_validator,
    )
    accepted: list[NormalizedEvidence] = []
    rejected: list[RejectedEvidence] = []
    fingerprints: set[str] = set()

    for index, candidate in enumerate(candidates):
        source_url = str(candidate.source_url)
        try:
            canonical_url = await url_validator(source_url)
        except UnsafeSourceUrl:
            rejected.append(RejectedEvidence(index, source_url, "unsafe_url"))
            continue
        except (TypeError, ValueError):
            rejected.append(RejectedEvidence(index, source_url, "malformed_url"))
            continue
        if not isinstance(canonical_url, str) or not canonical_url:
            rejected.append(RejectedEvidence(index, source_url, "malformed_url"))
            continue

        scope_reason = (
            "outside_approved_scope"
            if kind is ChildTaskKind.FIRST_PARTY_SOURCE_REVIEW
            else "outside_inspected_scope"
        )
        if canonical_url not in allowed:
            rejected.append(RejectedEvidence(index, source_url, scope_reason))
            continue

        expected_source_type = (
            SourceType.FIRST_PARTY
            if kind is ChildTaskKind.FIRST_PARTY_SOURCE_REVIEW
            else SourceType.NEWS
        )
        if candidate.source_type is not expected_source_type:
            rejected.append(RejectedEvidence(index, source_url, "source_type_mismatch"))
            continue

        quote = _normalized_quote(candidate.quoted_text)
        if not quote:
            rejected.append(RejectedEvidence(index, source_url, "empty_quote"))
            continue
        if len(quote) < 20:
            rejected.append(RejectedEvidence(index, source_url, "quote_too_short"))
            continue

        fingerprint = hashlib.sha256(f"{canonical_url}\n{quote}".encode()).hexdigest()
        if fingerprint in fingerprints:
            rejected.append(RejectedEvidence(index, source_url, "duplicate_evidence"))
            continue
        fingerprints.add(fingerprint)
        accepted.append(
            NormalizedEvidence(
                source_url=canonical_url,
                source_title=candidate.source_title.strip(),
                source_type=candidate.source_type,
                quoted_text=quote,
                normalized_claim=" ".join(candidate.normalized_claim.split()),
                published_at=candidate.published_at,
                confidence=candidate.confidence,
                limitations=tuple(
                    normalized
                    for limitation in candidate.limitations
                    if (normalized := " ".join(limitation.split()))
                ),
                fingerprint=fingerprint,
            )
        )

    return accepted, rejected
