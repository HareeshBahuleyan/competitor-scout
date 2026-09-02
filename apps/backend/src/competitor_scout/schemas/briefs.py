from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EMPTY_BRIEF_TITLE = "Weekly Digest: no material changes"
EMPTY_BRIEF_EXECUTIVE_SUMMARY = (
    "No accepted material changes were published during this weekly period."
)


class BriefContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BriefFindingReference(BriefContract):
    finding_id: UUID
    statement: str = Field(min_length=1, max_length=2000)


class BriefSection(BriefContract):
    heading: str = Field(min_length=1, max_length=200)
    narrative: str = Field(min_length=1, max_length=5000)
    references: list[BriefFindingReference] = Field(min_length=1, max_length=30)


class WeeklyBriefResult(BriefContract):
    title: str = Field(min_length=1, max_length=300)
    executive_summary: str = Field(min_length=1, max_length=5000)
    sections: list[BriefSection] = Field(max_length=20)

    @model_validator(mode="after")
    def require_canonical_empty_representation(self) -> Self:
        if not self.sections and (
            self.title != EMPTY_BRIEF_TITLE
            or self.executive_summary != EMPTY_BRIEF_EXECUTIVE_SUMMARY
        ):
            raise ValueError("empty brief representation must be deterministic")
        return self


class BriefRead(WeeklyBriefResult):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    id: UUID
    scout_run_id: UUID
    period_start: date
    period_end: date
    published_at: datetime
    created_at: datetime


def empty_weekly_brief() -> WeeklyBriefResult:
    return WeeklyBriefResult(
        title=EMPTY_BRIEF_TITLE,
        executive_summary=EMPTY_BRIEF_EXECUTIVE_SUMMARY,
        sections=[],
    )
