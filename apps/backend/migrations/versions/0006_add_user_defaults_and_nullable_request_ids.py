"""Persist user schedule defaults and nullable usage request IDs.

Revision ID: 0006_user_settings_usage
Revises: 0005_briefs
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_user_settings_usage"
down_revision: str | Sequence[str] | None = "0005_briefs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "default_daily_run_time_local",
            sa.Time(timezone=False),
            server_default="08:00:00",
            nullable=False,
        ),
    )
    op.alter_column(
        "usage_events",
        "provider_request_id",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE usage_events "
        "SET provider_request_id = 'missing:' || id::text "
        "WHERE provider_request_id IS NULL"
    )
    op.alter_column(
        "usage_events",
        "provider_request_id",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.drop_column("users", "default_daily_run_time_local")
