"""Remove the invite-only Google authentication allowlist.

Revision ID: 0007_remove_invite_allowlist
Revises: 0006_user_settings_usage
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_remove_invite_allowlist"
down_revision: str | Sequence[str] | None = "0006_user_settings_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_invited_emails_email", table_name="invited_emails")
    op.drop_table("invited_emails")


def downgrade() -> None:
    op.create_table(
        "invited_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invited_emails_email", "invited_emails", ["email"], unique=True)
