"""Create competitors and monitored sources.

Revision ID: 0002_competitors
Revises: 0001_auth
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_competitors"
down_revision: str | Sequence[str] | None = "0001_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    competitor_status = postgresql.ENUM(
        "discovering",
        "active",
        "paused",
        "deleted",
        name="competitor_status",
    )
    source_category = postgresql.ENUM(
        "homepage",
        "pricing",
        "product",
        "features",
        "changelog",
        "documentation",
        "blog",
        "careers",
        "other",
        name="source_category",
    )
    approval_status = postgresql.ENUM(
        "suggested",
        "approved",
        "rejected",
        name="approval_status",
    )

    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("primary_domain", sa.String(length=253), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            competitor_status,
            server_default="discovering",
            nullable=False,
        ),
        sa.Column(
            "daily_run_time_local",
            sa.Time(timezone=False),
            server_default="08:00:00",
            nullable=False,
        ),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_competitors_user_id", "competitors", ["user_id"])
    op.create_index(
        "ix_competitors_user_created",
        "competitors",
        ["user_id", "created_at", "id"],
    )
    op.create_index(
        "uq_competitors_user_active_domain",
        "competitors",
        ["user_id", "primary_domain"],
        unique=True,
        postgresql_where=sa.text("status <> 'deleted'::competitor_status"),
    )

    op.create_table(
        "monitored_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("normalized_url", sa.String(length=2048), nullable=False),
        sa.Column("source_category", source_category, nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("discovery_reason", sa.Text(), nullable=False),
        sa.Column(
            "approval_status",
            approval_status,
            server_default="suggested",
            nullable=False,
        ),
        sa.Column("last_investigated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "competitor_id",
            "normalized_url",
            name="uq_monitored_sources_competitor_url",
        ),
    )
    op.create_index(
        "ix_monitored_sources_competitor_id",
        "monitored_sources",
        ["competitor_id"],
    )
    op.create_index(
        "ix_monitored_sources_competitor_created",
        "monitored_sources",
        ["competitor_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_monitored_sources_competitor_created",
        table_name="monitored_sources",
    )
    op.drop_index("ix_monitored_sources_competitor_id", table_name="monitored_sources")
    op.drop_table("monitored_sources")
    op.drop_index("uq_competitors_user_active_domain", table_name="competitors")
    op.drop_index("ix_competitors_user_created", table_name="competitors")
    op.drop_index("ix_competitors_user_id", table_name="competitors")
    op.drop_table("competitors")
    op.execute("DROP TYPE IF EXISTS approval_status")
    op.execute("DROP TYPE IF EXISTS source_category")
    op.execute("DROP TYPE IF EXISTS competitor_status")
