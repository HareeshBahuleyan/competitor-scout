"""Add starting snapshots and per-run evidence observations.

Revision ID: 0010_starting_snapshots
Revises: 0009_merge_feature_into_product
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_starting_snapshots"
down_revision: str | Sequence[str] | None = "0009_merge_feature_into_product"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "competitors",
        sa.Column("starting_snapshot_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "evidence_observations",
        sa.Column("scout_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["agent_task_id"], ["agent_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scout_run_id"], ["scout_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("scout_run_id", "evidence_item_id"),
    )
    op.create_index(
        "ix_evidence_observations_evidence_item",
        "evidence_observations",
        ["evidence_item_id"],
    )
    op.create_table(
        "competitor_starting_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scout_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("coverage", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scout_run_id"], ["scout_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("competitor_id", name="uq_starting_snapshots_competitor"),
        sa.UniqueConstraint("scout_run_id", name="uq_starting_snapshots_scout_run"),
    )
    op.create_index(
        "ix_competitor_starting_snapshots_user_id",
        "competitor_starting_snapshots",
        ["user_id"],
    )
    op.create_index(
        "ix_starting_snapshots_user_published",
        "competitor_starting_snapshots",
        ["user_id", "published_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_starting_snapshots_user_published",
        table_name="competitor_starting_snapshots",
    )
    op.drop_index(
        "ix_competitor_starting_snapshots_user_id",
        table_name="competitor_starting_snapshots",
    )
    op.drop_table("competitor_starting_snapshots")
    op.drop_index("ix_evidence_observations_evidence_item", table_name="evidence_observations")
    op.drop_table("evidence_observations")
    op.drop_column("competitors", "starting_snapshot_requested_at")
