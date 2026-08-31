"""Create weekly briefs.

Revision ID: 0005_briefs
Revises: 0004_findings
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_briefs"
down_revision: str | Sequence[str] | None = "0004_findings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "weekly_briefs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scout_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column(
            "sections",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "period_start <= period_end",
            name="ck_weekly_briefs_period_order",
        ),
        sa.ForeignKeyConstraint(["scout_run_id"], ["scout_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scout_run_id", name="uq_weekly_briefs_scout_run"),
        sa.UniqueConstraint(
            "user_id",
            "period_start",
            "period_end",
            name="uq_weekly_briefs_user_period",
        ),
    )
    op.create_index("ix_weekly_briefs_user_id", "weekly_briefs", ["user_id"])
    op.create_index("ix_weekly_briefs_scout_run_id", "weekly_briefs", ["scout_run_id"])
    op.create_index(
        "ix_weekly_briefs_user_published",
        "weekly_briefs",
        ["user_id", "published_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_weekly_briefs_user_published", table_name="weekly_briefs")
    op.drop_index("ix_weekly_briefs_scout_run_id", table_name="weekly_briefs")
    op.drop_index("ix_weekly_briefs_user_id", table_name="weekly_briefs")
    op.drop_table("weekly_briefs")
