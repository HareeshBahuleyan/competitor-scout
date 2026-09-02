from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

EMPTY_BRIEF_TITLE = "No important changes found this week"
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


class CoveredCompetitor(BriefContract):
    competitor_id: UUID = Field(strict=False)
    competitor_name: str = Field(min_length=1, max_length=200)


class MonitoringCoverageReceipt(BriefContract):
    competitors: list[CoveredCompetitor] = Field(max_length=500)
    completed_scan_count: int = Field(ge=0)
    partial_scan_count: int = Field(ge=0)
    failed_scan_count: int = Field(ge=0)
    inspected_source_count: int = Field(ge=0)
    coverage_complete: bool

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        expected_complete = self.partial_scan_count == 0 and self.failed_scan_count == 0
        if self.coverage_complete is not expected_complete:
            raise ValueError("coverage completeness does not match partial and failed scan counts")
        competitor_ids = [item.competitor_id for item in self.competitors]
        if len(competitor_ids) != len(set(competitor_ids)):
            raise ValueError("coverage competitors must be distinct")
        return self


class BriefRead(WeeklyBriefResult):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    id: UUID
    scout_run_id: UUID
    period_start: date
    period_end: date
    coverage: MonitoringCoverageReceipt | None
    published_at: datetime
    created_at: datetime


class DigestCompetitorLink(BriefContract):
    competitor_id: UUID
    competitor_name: str = Field(min_length=1, max_length=200)
    status: Literal["discovering", "paused"]


class DigestRunningScan(BriefContract):
    run_id: UUID
    competitor_id: UUID
    competitor_name: str = Field(min_length=1, max_length=200)
    status: Literal["queued", "planning", "gathering", "synthesizing"]


class DigestSnapshotLink(BriefContract):
    snapshot_id: UUID
    competitor_id: UUID
    competitor_name: str = Field(min_length=1, max_length=200)


class DigestOverview(BriefContract):
    state: Literal[
        "setup_required",
        "setup_incomplete",
        "initial_scan_running",
        "awaiting_first_digest",
        "archive_available",
    ]
    next_digest_at: datetime | None
    active_competitor_count: int = Field(ge=0)
    approved_source_count: int = Field(ge=0)
    incomplete_competitor: DigestCompetitorLink | None
    running_scan: DigestRunningScan | None
    snapshots: list[DigestSnapshotLink] = Field(max_length=500)
    monitoring_issue_count: int = Field(ge=0)
    latest_brief: BriefRead | None


def empty_weekly_brief() -> WeeklyBriefResult:
    return WeeklyBriefResult(
        title=EMPTY_BRIEF_TITLE,
        executive_summary=EMPTY_BRIEF_EXECUTIVE_SUMMARY,
        sections=[],
    )
