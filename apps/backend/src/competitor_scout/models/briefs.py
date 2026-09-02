from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from competitor_scout.db import Base
from competitor_scout.models.auth import User
from competitor_scout.models.intelligence import ScoutRun


class WeeklyBrief(Base):
    __tablename__ = "weekly_briefs"
    __table_args__ = (
        CheckConstraint("period_start <= period_end", name="ck_weekly_briefs_period_order"),
        UniqueConstraint(
            "user_id",
            "period_start",
            "period_end",
            name="uq_weekly_briefs_user_period",
        ),
        UniqueConstraint("scout_run_id", name="uq_weekly_briefs_scout_run"),
        Index("ix_weekly_briefs_user_published", "user_id", "published_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    scout_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scout_runs.id", ondelete="CASCADE"),
        index=True,
    )
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(300))
    executive_summary: Mapped[str] = mapped_column(Text)
    sections: Mapped[list[object]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    coverage: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship()
    scout_run: Mapped[ScoutRun] = relationship()
