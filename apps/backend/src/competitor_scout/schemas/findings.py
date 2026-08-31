from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from competitor_scout.agents.contracts import FindingCategory, SignificanceLevel, SourceType

EvidenceIndex = Annotated[int, Field(ge=0)]


class EvidencePublication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_task_id: UUID
    source_url: HttpUrl
    source_title: str = Field(min_length=1, max_length=500)
    source_type: SourceType
    published_at: datetime | None = None
    captured_at: datetime
    quoted_text: str = Field(min_length=20, max_length=5000)
    normalized_claim: str = Field(min_length=1, max_length=1000)
    content_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class FindingPublication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: FindingCategory
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=3000)
    significance_explanation: str = Field(min_length=1, max_length=2000)
    significance_level: SignificanceLevel
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"), decimal_places=4)
    normalized_claim: str = Field(min_length=1, max_length=1000)
    material_change: bool
    evidence_indexes: list[EvidenceIndex] = Field(min_length=1, max_length=20)
    primary_evidence_index: EvidenceIndex
    decision_rationale: str = Field(min_length=1, max_length=2000)

    @field_validator("confidence", mode="before")
    @classmethod
    def quantize_confidence(cls, value: object) -> Decimal:
        try:
            confidence = value if isinstance(value, Decimal) else Decimal(str(value))
            return confidence.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError("confidence must be a finite decimal") from error

    @model_validator(mode="after")
    def validate_citations(self) -> Self:
        if len(self.evidence_indexes) != len(set(self.evidence_indexes)):
            raise ValueError("evidence indexes must be unique")
        if self.primary_evidence_index not in self.evidence_indexes:
            raise ValueError("primary evidence must be included in evidence indexes")
        return self


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    competitor_id: UUID
    originating_scout_run_id: UUID
    category: FindingCategory
    title: str
    summary: str
    significance_explanation: str
    significance_level: SignificanceLevel
    confidence: Decimal
    decision_rationale: str
    first_seen_at: datetime
    last_seen_at: datetime
    published_at: datetime


class FindingEvidenceRead(BaseModel):
    id: UUID
    source_url: HttpUrl
    source_domain: str
    source_title: str
    source_type: SourceType
    published_at: datetime | None
    captured_at: datetime
    quoted_text: str
    normalized_claim: str
    scout_run_id: UUID
    agent_task_id: UUID
    citation_order: int
    is_primary: bool
