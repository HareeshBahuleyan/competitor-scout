from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from competitor_scout.agents.contracts import FindingCategory, SignificanceLevel, SourceType
from competitor_scout.schemas.findings import EvidencePublication, FindingPublication
from competitor_scout.services.findings import finding_duplicate_key

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def test_duplicate_key_ignores_cosmetic_case_whitespace_and_unicode_form() -> None:
    first = finding_duplicate_key(
        "USER",
        "COMPETITOR",
        "PRICING",
        "Raised Café Pro price",
        "Example.COM.",
    )
    second = finding_duplicate_key(
        "user",
        "competitor",
        "pricing",
        "  raised  café PRO\nprice ",
        "example.com",
    )
    assert first == second


def valid_evidence(**updates) -> dict[str, object]:
    values: dict[str, object] = {
        "agent_task_id": "00000000-0000-0000-0000-000000000001",
        "source_url": "https://example.com/pricing",
        "source_title": "Pricing",
        "source_type": SourceType.FIRST_PARTY,
        "published_at": NOW,
        "captured_at": NOW,
        "quoted_text": "The Pro plan now costs ninety-nine dollars per month.",
        "normalized_claim": "Pro plan costs $99 per month",
        "content_fingerprint": "a" * 64,
    }
    values.update(updates)
    return values


def valid_finding(**updates) -> dict[str, object]:
    values: dict[str, object] = {
        "category": FindingCategory.PRICING,
        "title": "Pro price increased",
        "summary": "The monthly Pro price is now $99.",
        "significance_explanation": "This changes the competitive price comparison.",
        "significance_level": SignificanceLevel.HIGH,
        "confidence": Decimal("0.9500"),
        "normalized_claim": "Pro plan costs $99 per month",
        "material_change": True,
        "evidence_indexes": [0],
        "primary_evidence_index": 0,
        "decision_rationale": "The first-party pricing page directly states the new price.",
    }
    values.update(updates)
    return values


@pytest.mark.parametrize("confidence", [Decimal("-0.0001"), Decimal("1.0001")])
def test_finding_schema_bounds_confidence(confidence: Decimal) -> None:
    with pytest.raises(ValidationError):
        FindingPublication.model_validate(valid_finding(confidence=confidence))


def test_finding_schema_quantizes_valid_float_confidence_without_binary_noise() -> None:
    publication = FindingPublication.model_validate(valid_finding(confidence=0.91235))

    assert publication.confidence == Decimal("0.9124")


def test_finding_schema_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        FindingPublication.model_validate(valid_finding(category="invented"))


@pytest.mark.parametrize(
    "updates",
    [
        {"evidence_indexes": []},
        {"evidence_indexes": [0, 0]},
        {"evidence_indexes": list(range(21))},
        {"evidence_indexes": [0], "primary_evidence_index": 1},
        {"evidence_indexes": [-1], "primary_evidence_index": -1},
    ],
)
def test_finding_schema_enforces_citation_bounds(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        FindingPublication.model_validate(valid_finding(**updates))


def test_evidence_schema_accepts_only_normalized_publication_fields() -> None:
    evidence = EvidencePublication.model_validate(valid_evidence())
    assert evidence.content_fingerprint == "a" * 64
    with pytest.raises(ValidationError):
        EvidencePublication.model_validate({**valid_evidence(), "raw_response": "hidden"})
