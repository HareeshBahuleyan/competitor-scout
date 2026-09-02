from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from competitor_scout.db import Base
from competitor_scout.models.auth import User
from competitor_scout.models.intelligence import Competitor, ScoutRun


class CompetitorStartingSnapshot(Base):
    __tablename__ = "competitor_starting_snapshots"
    __table_args__ = (
        UniqueConstraint("competitor_id", name="uq_starting_snapshots_competitor"),
        UniqueConstraint("scout_run_id", name="uq_starting_snapshots_scout_run"),
        Index("ix_starting_snapshots_user_published", "user_id", "published_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    competitor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitors.id", ondelete="CASCADE"),
    )
    scout_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scout_runs.id", ondelete="CASCADE"),
    )
    executive_summary: Mapped[str] = mapped_column(Text)
    sections: Mapped[list[object]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    coverage: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()
    competitor: Mapped[Competitor] = relationship()
    scout_run: Mapped[ScoutRun] = relationship()
