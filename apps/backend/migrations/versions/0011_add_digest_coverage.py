"""Add immutable Weekly Digest monitoring coverage.

Revision ID: 0011_digest_coverage
Revises: 0010_starting_snapshots
Create Date: 2026-09-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_digest_coverage"
down_revision: str | None = "0010_starting_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_EMPTY_TITLE = "Weekly Digest: no material changes"
_NEW_EMPTY_TITLE = "No important changes found this week"


def upgrade() -> None:
    op.add_column(
        "weekly_briefs",
        sa.Column(
            "coverage",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE weekly_briefs SET title = :new_title "
            "WHERE title = :old_title AND sections = '[]'::jsonb"
        ).bindparams(new_title=_NEW_EMPTY_TITLE, old_title=_OLD_EMPTY_TITLE)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE weekly_briefs SET title = :old_title "
            "WHERE title = :new_title AND sections = '[]'::jsonb"
        ).bindparams(old_title=_OLD_EMPTY_TITLE, new_title=_NEW_EMPTY_TITLE)
    )
    op.drop_column("weekly_briefs", "coverage")
