"""Merge the feature finding category into product.

Revision ID: 0009_merge_feature_into_product
Revises: 0008_rename_empty_brief_title
Create Date: 2026-09-02
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_merge_feature_into_product"
down_revision: str | Sequence[str] | None = "0008_rename_empty_brief_title"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_VALUES = (
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
)
CURRENT_VALUES = tuple(value for value in LEGACY_VALUES if value != "feature")


def _replace_finding_category(values: tuple[str, ...]) -> None:
    op.execute("ALTER TABLE findings ALTER COLUMN category TYPE TEXT USING category::text")
    op.execute("DROP TYPE finding_category")
    postgresql.ENUM(*values, name="finding_category").create(op.get_bind())
    op.execute(
        "ALTER TABLE findings ALTER COLUMN category TYPE finding_category "
        "USING category::finding_category"
    )


def upgrade() -> None:
    # Preserve every historical finding while applying the merged taxonomy.
    op.execute("UPDATE findings SET category = 'product' WHERE category = 'feature'")
    _replace_finding_category(CURRENT_VALUES)


def downgrade() -> None:
    # The legacy enum can be restored, but merged rows remain product because
    # there is no reliable way to distinguish their former category.
    _replace_finding_category(LEGACY_VALUES)
