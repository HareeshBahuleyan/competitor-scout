"""Create evidence and published findings.

Revision ID: 0004_findings
Revises: 0003_runs_jobs
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_findings"
down_revision: str | Sequence[str] | None = "0003_runs_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    source_type = postgresql.ENUM("first_party", "news", name="source_type")
    finding_category = postgresql.ENUM(
        "pricing",
        "product",
        "feature",
        "positioning",
        "integration",
        "customer_win",
        "partnership",
        "leadership",
        "hiring",
        "market_expansion",
        "other",
        name="finding_category",
    )
    significance_level = postgresql.ENUM(
        "low",
        "medium",
        "high",
        "critical",
        name="significance_level",
    )

    op.create_table(
        "evidence_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scout_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("source_domain", sa.String(length=253), nullable=False),
        sa.Column("source_title", sa.String(length=500), nullable=False),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quoted_text", sa.Text(), nullable=False),
        sa.Column("normalized_claim", sa.Text(), nullable=False),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scout_run_id"], ["scout_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "competitor_id",
            "source_url",
            "content_fingerprint",
            name="uq_evidence_items_competitor_source_fingerprint",
        ),
    )
    op.create_index("ix_evidence_items_user_id", "evidence_items", ["user_id"])
    op.create_index("ix_evidence_items_competitor_id", "evidence_items", ["competitor_id"])
    op.create_index("ix_evidence_items_scout_run_id", "evidence_items", ["scout_run_id"])
    op.create_index("ix_evidence_items_agent_task_id", "evidence_items", ["agent_task_id"])
    op.create_index("ix_evidence_items_source_domain", "evidence_items", ["source_domain"])
    op.create_index(
        "ix_evidence_items_content_fingerprint",
        "evidence_items",
        ["content_fingerprint"],
    )
    op.create_index(
        "ix_evidence_items_competitor_created",
        "evidence_items",
        ["competitor_id", "created_at", "id"],
    )

    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("originating_scout_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", finding_category, nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("significance_explanation", sa.Text(), nullable=False),
        sa.Column("significance_level", significance_level, nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("decision_rationale", sa.Text(), nullable=False),
        sa.Column("normalized_claim_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("duplicate_key", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_findings_confidence_range",
        ),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["originating_scout_run_id"],
            ["scout_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_findings_user_id", "findings", ["user_id"])
    op.create_index("ix_findings_competitor_id", "findings", ["competitor_id"])
    op.create_index(
        "ix_findings_originating_scout_run_id",
        "findings",
        ["originating_scout_run_id"],
    )
    op.create_index(
        "ix_findings_normalized_claim_fingerprint",
        "findings",
        ["normalized_claim_fingerprint"],
    )
    op.create_index("uq_findings_duplicate_key", "findings", ["duplicate_key"], unique=True)
    op.create_index(
        "ix_findings_user_published",
        "findings",
        ["user_id", "published_at", "id"],
    )
    op.create_index(
        "ix_findings_competitor_published",
        "findings",
        ["competitor_id", "published_at", "id"],
    )
    op.create_index("ix_findings_category", "findings", ["category"])
    op.create_index("ix_findings_significance_level", "findings", ["significance_level"])

    op.create_table(
        "finding_evidence",
        sa.Column("finding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("citation_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint(
            "citation_order >= 1",
            name="ck_finding_evidence_citation_order",
        ),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("finding_id", "evidence_item_id"),
        sa.UniqueConstraint(
            "finding_id",
            "citation_order",
            name="uq_finding_evidence_citation_order",
        ),
    )
    op.create_index(
        "ix_finding_evidence_evidence_item_id",
        "finding_evidence",
        ["evidence_item_id"],
    )
    op.create_index(
        "uq_finding_evidence_primary",
        "finding_evidence",
        ["finding_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_index("uq_finding_evidence_primary", table_name="finding_evidence")
    op.drop_index("ix_finding_evidence_evidence_item_id", table_name="finding_evidence")
    op.drop_table("finding_evidence")

    op.drop_index("ix_findings_significance_level", table_name="findings")
    op.drop_index("ix_findings_category", table_name="findings")
    op.drop_index("ix_findings_competitor_published", table_name="findings")
    op.drop_index("ix_findings_user_published", table_name="findings")
    op.drop_index("uq_findings_duplicate_key", table_name="findings")
    op.drop_index("ix_findings_normalized_claim_fingerprint", table_name="findings")
    op.drop_index("ix_findings_originating_scout_run_id", table_name="findings")
    op.drop_index("ix_findings_competitor_id", table_name="findings")
    op.drop_index("ix_findings_user_id", table_name="findings")
    op.drop_table("findings")

    op.drop_index("ix_evidence_items_competitor_created", table_name="evidence_items")
    op.drop_index("ix_evidence_items_content_fingerprint", table_name="evidence_items")
    op.drop_index("ix_evidence_items_source_domain", table_name="evidence_items")
    op.drop_index("ix_evidence_items_agent_task_id", table_name="evidence_items")
    op.drop_index("ix_evidence_items_scout_run_id", table_name="evidence_items")
    op.drop_index("ix_evidence_items_competitor_id", table_name="evidence_items")
    op.drop_index("ix_evidence_items_user_id", table_name="evidence_items")
    op.drop_table("evidence_items")

    op.execute("DROP TYPE IF EXISTS significance_level")
    op.execute("DROP TYPE IF EXISTS finding_category")
    op.execute("DROP TYPE IF EXISTS source_type")
