from __future__ import annotations

import uuid
from datetime import datetime, time
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from competitor_scout.agents.contracts import FindingCategory, SignificanceLevel, SourceType
from competitor_scout.db import Base
from competitor_scout.models.auth import User


class CompetitorStatus(StrEnum):
    DISCOVERING = "discovering"
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


class SourceCategory(StrEnum):
    HOMEPAGE = "homepage"
    PRICING = "pricing"
    PRODUCT = "product"
    FEATURES = "features"
    CHANGELOG = "changelog"
    DOCUMENTATION = "documentation"
    BLOG = "blog"
    CAREERS = "careers"
    OTHER = "other"


class ApprovalStatus(StrEnum):
    SUGGESTED = "suggested"
    APPROVED = "approved"
    REJECTED = "rejected"


class RunType(StrEnum):
    SOURCE_DISCOVERY = "source_discovery"
    DAILY_SCOUT = "daily_scout"
    MANUAL_SCOUT = "manual_scout"
    WEEKLY_BRIEF = "weekly_brief"


class ScoutRunStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    GATHERING = "gathering"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class AgentTaskRole(StrEnum):
    MAIN_PLANNER = "main_planner"
    CHILD_RESEARCHER = "child_researcher"
    MAIN_SYNTHESIZER = "main_synthesizer"


class AgentTaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_type]


class Competitor(Base):
    __tablename__ = "competitors"
    __table_args__ = (
        Index(
            "uq_competitors_user_active_domain",
            "user_id",
            "primary_domain",
            unique=True,
            postgresql_where=text("status <> 'deleted'::competitor_status"),
        ),
        Index("ix_competitors_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    primary_domain: Mapped[str] = mapped_column(String(253))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[CompetitorStatus] = mapped_column(
        Enum(
            CompetitorStatus,
            name="competitor_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=CompetitorStatus.DISCOVERING,
        server_default=CompetitorStatus.DISCOVERING.value,
    )
    daily_run_time_local: Mapped[time] = mapped_column(
        Time(timezone=False),
        default=time(hour=8),
        server_default="08:00:00",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
    sources: Mapped[list[MonitoredSource]] = relationship(
        back_populates="competitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MonitoredSource(Base):
    __tablename__ = "monitored_sources"
    __table_args__ = (
        UniqueConstraint(
            "competitor_id",
            "normalized_url",
            name="uq_monitored_sources_competitor_url",
        ),
        Index("ix_monitored_sources_competitor_created", "competitor_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitors.id", ondelete="CASCADE"),
        index=True,
    )
    url: Mapped[str] = mapped_column(String(2048))
    normalized_url: Mapped[str] = mapped_column(String(2048))
    source_category: Mapped[SourceCategory] = mapped_column(
        Enum(
            SourceCategory,
            name="source_category",
            values_callable=enum_values,
            validate_strings=True,
        )
    )
    title: Mapped[str] = mapped_column(String(500))
    discovery_reason: Mapped[str] = mapped_column(Text)
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(
            ApprovalStatus,
            name="approval_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=ApprovalStatus.SUGGESTED,
        server_default=ApprovalStatus.SUGGESTED.value,
    )
    last_investigated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_successful_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    competitor: Mapped[Competitor] = relationship(back_populates="sources")


class ScoutRun(Base):
    __tablename__ = "scout_runs"
    __table_args__ = (
        CheckConstraint(
            "(run_type = 'weekly_brief' AND competitor_id IS NULL) "
            "OR (run_type <> 'weekly_brief' AND competitor_id IS NOT NULL)",
            name="ck_scout_runs_competitor_scope",
        ),
        Index(
            "uq_scout_runs_active_competitor_scout",
            "competitor_id",
            unique=True,
            postgresql_where=text(
                "competitor_id IS NOT NULL "
                "AND run_type IN ('daily_scout', 'manual_scout') "
                "AND status IN ('queued', 'planning', 'gathering', 'synthesizing')"
            ),
        ),
        Index(
            "uq_scout_runs_competitor_schedule",
            "run_type",
            "competitor_id",
            "scheduled_for",
            unique=True,
            postgresql_where=text("competitor_id IS NOT NULL"),
        ),
        Index(
            "uq_scout_runs_weekly_schedule",
            "run_type",
            "user_id",
            "scheduled_for",
            unique=True,
            postgresql_where=text("competitor_id IS NULL AND run_type = 'weekly_brief'"),
        ),
        Index("ix_scout_runs_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    competitor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competitors.id", ondelete="CASCADE"),
        index=True,
    )
    run_type: Mapped[RunType] = mapped_column(
        Enum(RunType, name="run_type", values_callable=enum_values, validate_strings=True)
    )
    status: Mapped[ScoutRunStatus] = mapped_column(
        Enum(
            ScoutRunStatus,
            name="scout_run_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=ScoutRunStatus.QUEUED,
        server_default=ScoutRunStatus.QUEUED.value,
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_summary: Mapped[str | None] = mapped_column(Text)
    partial_reasons: Mapped[list[object]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tool_calls: Mapped[int | None] = mapped_column(Integer)
    settled_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()
    competitor: Mapped[Competitor | None] = relationship()
    tasks: Mapped[list[AgentTask]] = relationship(
        back_populates="scout_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    usage_events: Mapped[list[UsageEvent]] = relationship(
        back_populates="scout_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scout_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scout_runs.id", ondelete="CASCADE"),
        index=True,
    )
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"),
        index=True,
    )
    role: Mapped[AgentTaskRole] = mapped_column(
        Enum(
            AgentTaskRole,
            name="agent_task_role",
            values_callable=enum_values,
            validate_strings=True,
        )
    )
    task_kind: Mapped[str] = mapped_column(String(100))
    status: Mapped[AgentTaskStatus] = mapped_column(
        Enum(
            AgentTaskStatus,
            name="agent_task_status",
            values_callable=enum_values,
            validate_strings=True,
        ),
        default=AgentTaskStatus.QUEUED,
        server_default=AgentTaskStatus.QUEUED.value,
    )
    model: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(Text)
    source_scope: Mapped[list[object]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otari_request_id: Mapped[str | None] = mapped_column(String(255), index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tool_calls: Mapped[int | None] = mapped_column(Integer)
    settled_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    pricing_source: Mapped[str | None] = mapped_column(String(100))
    validated_output: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scout_run: Mapped[ScoutRun] = relationship(back_populates="tasks")
    parent_task: Mapped[AgentTask | None] = relationship(
        remote_side="AgentTask.id",
        back_populates="child_tasks",
    )
    child_tasks: Mapped[list[AgentTask]] = relationship(back_populates="parent_task")
    usage_events: Mapped[list[UsageEvent]] = relationship(
        back_populates="agent_task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_events_user_occurred", "user_id", "occurred_at", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    scout_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scout_runs.id", ondelete="CASCADE"),
        index=True,
    )
    agent_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="CASCADE"),
        index=True,
    )
    provider_request_id: Mapped[str | None] = mapped_column(String(255), index=True)
    model: Mapped[str] = mapped_column(String(200))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    tool_calls: Mapped[int | None] = mapped_column(Integer)
    settled_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    pricing_source: Mapped[str | None] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    user: Mapped[User] = relationship()
    scout_run: Mapped[ScoutRun] = relationship(back_populates="usage_events")
    agent_task: Mapped[AgentTask] = relationship(back_populates="usage_events")


class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint(
            "competitor_id",
            "source_url",
            "content_fingerprint",
            name="uq_evidence_items_competitor_source_fingerprint",
        ),
        Index("ix_evidence_items_competitor_created", "competitor_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitors.id", ondelete="CASCADE"),
        index=True,
    )
    scout_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scout_runs.id", ondelete="CASCADE"),
        index=True,
    )
    agent_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="CASCADE"),
        index=True,
    )
    source_url: Mapped[str] = mapped_column(String(2048))
    source_domain: Mapped[str] = mapped_column(String(253), index=True)
    source_title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type", values_callable=enum_values, validate_strings=True)
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quoted_text: Mapped[str] = mapped_column(Text)
    normalized_claim: Mapped[str] = mapped_column(Text)
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()
    competitor: Mapped[Competitor] = relationship()
    scout_run: Mapped[ScoutRun] = relationship()
    agent_task: Mapped[AgentTask] = relationship()
    finding_links: Mapped[list[FindingEvidence]] = relationship(
        back_populates="evidence_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_findings_confidence_range",
        ),
        Index("uq_findings_duplicate_key", "duplicate_key", unique=True),
        Index("ix_findings_user_published", "user_id", "published_at", "id"),
        Index("ix_findings_competitor_published", "competitor_id", "published_at", "id"),
        Index("ix_findings_category", "category"),
        Index("ix_findings_significance_level", "significance_level"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitors.id", ondelete="CASCADE"),
        index=True,
    )
    originating_scout_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scout_runs.id", ondelete="CASCADE"),
        index=True,
    )
    category: Mapped[FindingCategory] = mapped_column(
        Enum(
            FindingCategory,
            name="finding_category",
            values_callable=enum_values,
            validate_strings=True,
        ),
    )
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    significance_explanation: Mapped[str] = mapped_column(Text)
    significance_level: Mapped[SignificanceLevel] = mapped_column(
        Enum(
            SignificanceLevel,
            name="significance_level",
            values_callable=enum_values,
            validate_strings=True,
        ),
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    decision_rationale: Mapped[str] = mapped_column(Text)
    normalized_claim_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    duplicate_key: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship()
    competitor: Mapped[Competitor] = relationship()
    originating_scout_run: Mapped[ScoutRun] = relationship()
    evidence_links: Mapped[list[FindingEvidence]] = relationship(
        back_populates="finding",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FindingEvidence.citation_order",
    )


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    __table_args__ = (
        CheckConstraint("citation_order >= 1", name="ck_finding_evidence_citation_order"),
        UniqueConstraint(
            "finding_id",
            "citation_order",
            name="uq_finding_evidence_citation_order",
        ),
        Index(
            "uq_finding_evidence_primary",
            "finding_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    finding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("findings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    citation_order: Mapped[int] = mapped_column(Integer)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    finding: Mapped[Finding] = relationship(back_populates="evidence_links")
    evidence_item: Mapped[EvidenceItem] = relationship(back_populates="finding_links")
