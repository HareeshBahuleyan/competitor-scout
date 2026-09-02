"""Rename the canonical empty weekly-brief title to the interface vocabulary.

Revision ID: 0008_rename_empty_brief_title
Revises: 0007_remove_invite_allowlist
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_rename_empty_brief_title"
down_revision: str | Sequence[str] | None = "0007_remove_invite_allowlist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TITLE = "Weekly brief: no material changes"
NEW_TITLE = "Weekly digest: no material changes"

# `BriefRead` rejects a section-less brief whose title is not the current
# canonical value, so stored rows must move with the constant or reads fail.
RETITLE = sa.text(
    """
    UPDATE weekly_briefs
    SET title = :new_title
    WHERE title = :old_title
      AND sections = '[]'::jsonb
    """
)


def upgrade() -> None:
    op.get_bind().execute(RETITLE, {"new_title": NEW_TITLE, "old_title": OLD_TITLE})


def downgrade() -> None:
    op.get_bind().execute(RETITLE, {"new_title": OLD_TITLE, "old_title": NEW_TITLE})
