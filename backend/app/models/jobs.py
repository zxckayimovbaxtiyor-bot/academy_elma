from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, IdPk, pg_enum
from app.models.enums import JobKind, JobLane, JobStatus


class Job(Base):
    """Background work for the worker container, claimed with FOR UPDATE SKIP LOCKED."""

    __tablename__ = "job"
    __table_args__ = (
        Index(
            "ix_job_queue",
            "lane",
            "created_at",
            postgresql_where=text("status = 'queued'"),
        ),
    )

    id: Mapped[IdPk]
    kind: Mapped[JobKind] = mapped_column(pg_enum(JobKind, "job_kind"))
    lane: Mapped[JobLane] = mapped_column(pg_enum(JobLane, "job_lane"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    status: Mapped[JobStatus] = mapped_column(
        pg_enum(JobStatus, "job_status"), default=JobStatus.queued
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    created_at: Mapped[CreatedAt]
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
