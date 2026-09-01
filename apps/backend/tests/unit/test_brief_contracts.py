import json
import uuid

import pytest
from pydantic import ValidationError

from competitor_scout.schemas.briefs import (
    EMPTY_BRIEF_EXECUTIVE_SUMMARY,
    EMPTY_BRIEF_TITLE,
    BriefSection,
    WeeklyBriefResult,
    empty_weekly_brief,
)


def test_weekly_brief_contract_is_strict_and_requires_grounded_sections() -> None:
    finding_id = uuid.uuid4()
    parsed = WeeklyBriefResult.model_validate_json(
        json.dumps(
            {
                "title": "Competitive changes",
                "executive_summary": "Two material changes deserve attention.",
                "sections": [
                    {
                        "heading": "Pricing",
                        "narrative": "A competitor changed its entry tier.",
                        "references": [
                            {
                                "finding_id": str(finding_id),
                                "statement": "The entry tier price changed.",
                            }
                        ],
                    }
                ],
            }
        )
    )
    assert parsed.sections[0].references[0].finding_id == finding_id

    with pytest.raises(ValidationError, match="extra_forbidden"):
        WeeklyBriefResult.model_validate(
            {
                **parsed.model_dump(),
                "prompt": "must never be retained",
            }
        )
    with pytest.raises(ValidationError):
        BriefSection(heading="Pricing", narrative="Narrative", references=[])


def test_empty_week_has_one_deterministic_representation_without_references() -> None:
    first = empty_weekly_brief()
    second = empty_weekly_brief()

    assert first == second
    assert first.title == EMPTY_BRIEF_TITLE
    assert first.executive_summary == EMPTY_BRIEF_EXECUTIVE_SUMMARY
    assert first.sections == []
    with pytest.raises(ValidationError, match="empty brief representation"):
        WeeklyBriefResult(
            title="Invented empty title",
            executive_summary="No changes.",
            sections=[],
        )
