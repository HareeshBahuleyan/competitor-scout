from __future__ import annotations

import json
from pathlib import Path

from competitor_scout.agents.contracts import (
    ChildTaskKind,
    EvidenceCandidate,
    FindingCategory,
    SourceType,
)
from competitor_scout.agents.validation import validate_evidence_scope
from competitor_scout.schemas.findings import FindingPublication
from competitor_scout.services.findings import finding_duplicate_key

CORPUS_PATH = Path(__file__).resolve().parents[4] / "evals" / "competitor-signals-v1.json"


def load_corpus() -> list[dict[str, object]]:
    return json.loads(CORPUS_PATH.read_text())


def test_versioned_corpus_has_broad_unique_coverage() -> None:
    cases = load_corpus()
    ids = [case["id"] for case in cases]
    supported_categories = {
        case["expected_category"]
        for case in cases
        if case["expected_publish"] is True
    }

    assert len(cases) >= 20
    assert len(ids) == len(set(ids))
    assert supported_categories == {category.value for category in FindingCategory}
    assert all(str(case["source_url"]).startswith("https://") for case in cases)


async def test_offline_fixture_thresholds_and_citations() -> None:
    cases = load_corpus()
    publishable = [case for case in cases if case["expected_publish"] is True]
    rejected = [case for case in cases if case["expected_publish"] is False]

    unsupported_rejection = sum(case["fixture_finding"] is None for case in rejected)
    valid_citations = 0
    correct_categories = 0
    for case in publishable:
        finding = case["fixture_finding"]
        assert isinstance(finding, dict)
        evidence = case["fixture_evidence"]
        assert isinstance(evidence, list)
        indexes = finding["evidence_indexes"]
        assert isinstance(indexes, list)
        publication = FindingPublication.model_validate(
            {
                "category": finding["category"],
                "title": f"Fixture: {case['id']}",
                "summary": str(finding["normalized_claim"]),
                "significance_explanation": "Synthetic material-change fixture",
                "significance_level": "medium",
                "confidence": "0.9000",
                "normalized_claim": finding["normalized_claim"],
                "material_change": True,
                "evidence_indexes": indexes,
                "primary_evidence_index": indexes[0],
                "decision_rationale": "Direct quoted synthetic evidence",
            }
        )
        candidates = [
            EvidenceCandidate.model_validate(
                {
                    **item,
                    "source_title": "Synthetic fixture",
                    "source_type": SourceType.FIRST_PARTY,
                    "normalized_claim": finding["normalized_claim"],
                    "confidence": 0.9,
                }
            )
            for item in evidence
        ]

        async def canonical(value: str) -> str:
            return value

        accepted, rejected_evidence = await validate_evidence_scope(
            candidates,
            approved_urls=[str(case["source_url"])],
            inspected_urls=[],
            task_kind=ChildTaskKind.FIRST_PARTY_SOURCE_REVIEW,
            url_validator=canonical,
        )
        if publication.evidence_indexes and all(
            index < len(accepted) for index in publication.evidence_indexes
        ) and not rejected_evidence:
            valid_citations += 1
        if publication.category.value == case["expected_category"]:
            correct_categories += 1
        required_quote = case["required_quote_fragment"]
        assert isinstance(required_quote, str)
        assert any(required_quote in str(item["quoted_text"]) for item in evidence)

    assert unsupported_rejection / len(rejected) == 1
    assert valid_citations / len(publishable) == 1
    assert correct_categories / len(publishable) >= 0.9


def test_duplicate_groups_resolve_to_one_publication_key() -> None:
    duplicate_cases = [
        case for case in load_corpus() if case.get("duplicate_group") is not None
    ]
    grouped: dict[str, set[str]] = {}
    for case in duplicate_cases:
        finding = case["fixture_finding"]
        assert isinstance(finding, dict)
        grouped.setdefault(str(case["duplicate_group"]), set()).add(
            finding_duplicate_key(
                "fixture-user",
                "fixture-competitor",
                str(finding["category"]),
                str(finding["normalized_claim"]),
                "example.test",
            )
        )

    assert grouped
    assert all(len(keys) == 1 for keys in grouped.values())
