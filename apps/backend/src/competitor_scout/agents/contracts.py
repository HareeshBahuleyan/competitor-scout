from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

BoundedText = Annotated[str, Field(min_length=1, max_length=1000)]
EvidenceIndex = Annotated[int, Field(ge=0)]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ChildTaskKind(StrEnum):
    FIRST_PARTY_SOURCE_REVIEW = "first_party_source_review"
    NEWS_DISCOVERY = "news_discovery"


class FindingCategory(StrEnum):
    PRICING = "pricing"
    PRODUCT = "product"
    POSITIONING = "positioning"
    INTEGRATION = "integration"
    CUSTOMER_WIN = "customer_win"
    PARTNERSHIP = "partnership"
    LEADERSHIP = "leadership"
    HIRING = "hiring"
    MARKET_EXPANSION = "market_expansion"
    OTHER = "other"


FINDING_CATEGORY_DEFINITIONS: dict[FindingCategory, str] = {
    FindingCategory.PRICING: (
        "Prices, plans, packaging, usage limits, discounts, or which capabilities a plan includes."
    ),
    FindingCategory.PRODUCT: (
        "A product launch, built-in capability, feature, workflow, product improvement, or removal."
    ),
    FindingCategory.POSITIONING: (
        "A change in messaging, claimed differentiation, target customer, or stated "
        "market identity "
        "without a corresponding product change."
    ),
    FindingCategory.INTEGRATION: (
        "A connection, connector, interoperability announcement, or technical relationship with a "
        "named third-party product or platform."
    ),
    FindingCategory.CUSTOMER_WIN: (
        "A named organization newly selecting, buying, adopting, or publicly endorsing "
        "the competitor."
    ),
    FindingCategory.PARTNERSHIP: (
        "A two-way commercial, channel, implementation, or technology partnership that "
        "is not merely "
        "a customer purchase."
    ),
    FindingCategory.LEADERSHIP: (
        "An executive or board appointment, departure, promotion, or other named leadership change."
    ),
    FindingCategory.HIRING: (
        "New open roles, a material hiring push, headcount expansion, or a hiring slowdown."
    ),
    FindingCategory.MARKET_EXPANSION: (
        "Entry into or withdrawal from a geography or market, including a new regional office or "
        "localized availability."
    ),
    FindingCategory.OTHER: (
        "A material competitor change that does not fit any category above; use only as "
        "a last resort."
    ),
}


class SignificanceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceType(StrEnum):
    FIRST_PARTY = "first_party"
    NEWS = "news"


class DiscoveredSourceCategory(StrEnum):
    HOMEPAGE = "homepage"
    PRICING = "pricing"
    PRODUCT = "product"
    FEATURES = "features"
    CHANGELOG = "changelog"
    DOCUMENTATION = "documentation"
    BLOG = "blog"
    CAREERS = "careers"
    OTHER = "other"


class PlannedChildTask(StrictContract):
    kind: ChildTaskKind
    objective: BoundedText
    source_urls: list[HttpUrl] = Field(max_length=20)
    search_query: str | None = Field(default=None, min_length=1, max_length=400)
    expected_category: FindingCategory
    max_search_calls: int = Field(ge=0, le=10)
    completion_criteria: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def enforce_kind_scope(self) -> Self:
        if self.kind is ChildTaskKind.FIRST_PARTY_SOURCE_REVIEW:
            if not self.source_urls or self.search_query is not None or self.max_search_calls < 1:
                raise ValueError(
                    "first-party review requires source URLs, no search query, and a search budget"
                )
        elif self.source_urls or not self.search_query or self.max_search_calls < 1:
            raise ValueError(
                "news discovery requires a search query, no fixed URLs, and a search budget"
            )
        return self


class ScoutPlan(StrictContract):
    tasks: list[PlannedChildTask] = Field(min_length=1, max_length=8)


class DiscoveredSource(StrictContract):
    url: HttpUrl
    title: str = Field(min_length=1, max_length=500)
    category: DiscoveredSourceCategory
    reason: str = Field(min_length=1, max_length=1000)


class SourceDiscoveryResult(StrictContract):
    sources: list[DiscoveredSource] = Field(max_length=30)


class EvidenceCandidate(StrictContract):
    source_url: HttpUrl
    source_title: str = Field(min_length=1, max_length=500)
    source_type: SourceType
    quoted_text: str = Field(min_length=20, max_length=5000)
    normalized_claim: str = Field(min_length=1, max_length=1000)
    published_at: datetime | None = None
    confidence: float = Field(ge=0, le=1)
    limitations: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list,
        max_length=10,
    )


class ChildTaskResult(StrictContract):
    sources_inspected: list[HttpUrl] = Field(max_length=50)
    evidence: list[EvidenceCandidate] = Field(max_length=50)
    limitations: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list,
        max_length=10,
    )


class FindingCandidate(StrictContract):
    category: FindingCategory
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=3000)
    significance_explanation: str = Field(min_length=1, max_length=2000)
    significance_level: SignificanceLevel
    confidence: float = Field(ge=0, le=1)
    normalized_claim: str = Field(min_length=1, max_length=1000)
    material_change: bool
    evidence_indexes: list[EvidenceIndex] = Field(min_length=1, max_length=20)
    primary_evidence_index: EvidenceIndex
    decision_rationale: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_evidence_indexes(self) -> Self:
        if len(self.evidence_indexes) != len(set(self.evidence_indexes)):
            raise ValueError("evidence indexes must be unique")
        if self.primary_evidence_index not in self.evidence_indexes:
            raise ValueError("primary evidence must be included in evidence indexes")
        return self


class SynthesisResult(StrictContract):
    findings: list[FindingCandidate] = Field(max_length=50)
