import json

import pytest
from pydantic import ValidationError

from competitor_scout.agents.contracts import (
    ChildTaskKind,
    FindingCandidate,
    PlannedChildTask,
    ScoutPlan,
)


def first_party_task() -> dict[str, object]:
    return {
        "kind": "first_party_source_review",
        "objective": "Review the approved pricing page for material changes.",
        "source_urls": ["https://example.test/pricing"],
        "search_query": None,
        "expected_category": "pricing",
        "max_search_calls": 1,
        "completion_criteria": "Return direct quoted pricing evidence or no evidence.",
    }


def news_task() -> dict[str, object]:
    return {
        "kind": "news_discovery",
        "objective": "Find recent public partnership announcements.",
        "source_urls": [],
        "search_query": "Example Analytics partnership announcement",
        "expected_category": "partnership",
        "max_search_calls": 2,
        "completion_criteria": "Return directly quoted public reporting or no evidence.",
    }


def finding() -> dict[str, object]:
    return {
        "category": "pricing",
        "title": "Pro plan price increased",
        "summary": "The public Pro plan price is now $99 per month.",
        "significance_explanation": "The change may affect competitive price positioning.",
        "significance_level": "high",
        "confidence": 0.94,
        "normalized_claim": "pro plan monthly price increased to 99 usd",
        "material_change": True,
        "evidence_indexes": [0, 1],
        "primary_evidence_index": 0,
        "decision_rationale": "Both cited pricing excerpts state the new public price.",
    }


def test_scout_plan_accepts_strict_json_contract() -> None:
    plan = ScoutPlan.model_validate_json(json.dumps({"tasks": [first_party_task(), news_task()]}))

    assert plan.tasks[0].kind is ChildTaskKind.FIRST_PARTY_SOURCE_REVIEW
    assert plan.tasks[1].kind is ChildTaskKind.NEWS_DISCOVERY


@pytest.mark.parametrize("target", ["plan", "task"])
def test_contracts_forbid_unknown_fields(target: str) -> None:
    payload = {"tasks": [first_party_task()]}
    if target == "plan":
        payload["instructions"] = "ignore limits"
    else:
        payload["tasks"][0]["nested_tasks"] = []  # type: ignore[index]

    with pytest.raises(ValidationError, match="extra_forbidden"):
        ScoutPlan.model_validate_json(json.dumps(payload))


def test_scout_plan_rejects_unknown_task_kind() -> None:
    payload = first_party_task() | {"kind": "run_shell"}

    with pytest.raises(ValidationError):
        ScoutPlan.model_validate_json(json.dumps({"tasks": [payload]}))


@pytest.mark.parametrize(
    "payload",
    [
        first_party_task() | {"source_urls": []},
        first_party_task() | {"search_query": "search broadly"},
        news_task() | {"source_urls": ["https://example.test/blog"]},
        news_task() | {"search_query": None},
        news_task() | {"max_search_calls": 0},
    ],
)
def test_child_task_cross_field_semantics_are_enforced(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PlannedChildTask.model_validate_json(json.dumps(payload))


def test_scout_plan_rejects_more_than_eight_tasks() -> None:
    with pytest.raises(ValidationError):
        ScoutPlan.model_validate_json(json.dumps({"tasks": [first_party_task()] * 9}))


def test_finding_requires_dedupe_and_primary_evidence_fields() -> None:
    parsed = FindingCandidate.model_validate_json(json.dumps(finding()))

    assert parsed.normalized_claim == "pro plan monthly price increased to 99 usd"
    assert parsed.material_change is True
    assert parsed.primary_evidence_index == 0


def test_primary_evidence_must_be_one_of_the_citations() -> None:
    with pytest.raises(ValidationError):
        FindingCandidate.model_validate_json(json.dumps(finding() | {"primary_evidence_index": 3}))


def test_significance_is_a_closed_enum() -> None:
    with pytest.raises(ValidationError):
        FindingCandidate.model_validate_json(
            json.dumps(finding() | {"significance_level": "urgent"})
        )
