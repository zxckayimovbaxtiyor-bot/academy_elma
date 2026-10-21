from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LessonProgress(Base):
    """Server-side watch record for one learner and one lesson version (the 90 % rule)."""

    __tablename__ = "lesson_progress"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), primary_key=True)
    lesson_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lesson_version.id"), primary_key=True, index=True
    )
    # Merged, sorted [[start_s, end_s], ...] of what was actually played.
    watched: Mapped[list[list[float]]] = mapped_column(JSONB, default=list, server_default="[]")
    watched_s: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    max_position_s: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    last_position_s: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
