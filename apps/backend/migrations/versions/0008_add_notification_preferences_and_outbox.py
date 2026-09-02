"""Add opt-in notification preferences and transactional outbox.

Revision ID: 0008_notification_outbox
Revises: 0007_remove_invite_allowlist
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_notification_outbox"
down_revision: str | Sequence[str] | None = "0007_remove_invite_allowlist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

notification_status = postgresql.ENUM(
    "pending", "sent", "failed", name="notification_status", create_type=False
)


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_findings_enabled", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_weekly_brief_enabled", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    notification_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "notification_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_type", sa.String(length=100), nullable=False),
        sa.Column("deduplication_key", sa.String(length=500), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", notification_status, server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notification_outbox_deduplication_key",
        "notification_outbox",
        ["deduplication_key"],
        unique=True,
    )
    op.create_index(
        "ix_notification_outbox_claimable",
        "notification_outbox",
        ["status", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_claimable", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_deduplication_key", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    notification_status.drop(op.get_bind(), checkfirst=True)
    op.drop_column("users", "email_weekly_brief_enabled")
    op.drop_column("users", "email_findings_enabled")
