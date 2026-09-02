from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from competitor_scout.agents.contracts import SnapshotTopic
from competitor_scout.models.intelligence import SourceCategory


class SnapshotContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SnapshotCoverage(SnapshotContract):
    approved_source_count: int = Field(ge=0)
    inspected_source_count: int = Field(ge=0)
    uninspected_source_count: int = Field(ge=0)
    inspected_source_categories: list[SourceCategory] = Field(max_length=9)
    coverage_complete: bool

    @model_validator(mode="after")
    def validate_counts(self) -> "SnapshotCoverage":
        if (
            self.inspected_source_count + self.uninspected_source_count
            != self.approved_source_count
        ):
            raise ValueError("snapshot coverage counts must reconcile")
        expected_complete = self.uninspected_source_count == 0
        if self.coverage_complete and not expected_complete:
            raise ValueError("complete snapshot coverage cannot have uninspected sources")
        return self


class SnapshotEvidenceRead(SnapshotContract):
    evidence_id: UUID
    statement: str = Field(min_length=1, max_length=2000)
    source_title: str = Field(min_length=1, max_length=500)
    source_url: HttpUrl
    quoted_text: str = Field(min_length=1, max_length=5000)
    captured_at: datetime


class SnapshotSectionRead(SnapshotContract):
    topic: SnapshotTopic
    narrative: str = Field(min_length=1, max_length=5000)
    references: list[SnapshotEvidenceRead] = Field(min_length=1, max_length=30)


class StartingSnapshotRead(SnapshotContract):
    id: UUID
    competitor_id: UUID
    competitor_name: str = Field(min_length=1, max_length=200)
    scout_run_id: UUID
    executive_summary: str = Field(min_length=1, max_length=5000)
    sections: list[SnapshotSectionRead] = Field(min_length=1, max_length=5)
    coverage: SnapshotCoverage
    published_at: datetime
    created_at: datetime
