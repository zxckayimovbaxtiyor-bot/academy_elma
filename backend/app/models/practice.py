from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, IdPk


class PracticeScenario(Base):
    __tablename__ = "practice_scenario"
    id: Mapped[IdPk]
    module_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("module.id"), index=True
    )
    lesson_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("lesson.id"), index=True
    )
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    created_at: Mapped[CreatedAt]


class PracticeScenarioVersion(Base):
    __tablename__ = "practice_scenario_version"
    __table_args__ = (
        UniqueConstraint("scenario_id", "number"),
        Index(
            "uq_practice_draft",
            "scenario_id",
            unique=True,
            postgresql_where=text("published_at IS NULL"),
        ),
    )
    id: Mapped[IdPk]
    scenario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("practice_scenario.id"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    preview_revision: Mapped[int | None] = mapped_column(Integer)
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[CreatedAt]
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id")
    )


class PracticeAssignment(Base):
    __tablename__ = "practice_assignment"
    scenario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("practice_scenario.id"), primary_key=True
    )
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB)


class PracticeSession(Base):
    __tablename__ = "practice_session"
    __table_args__ = (
        Index("ix_practice_session_user_scenario", "user_id", "scenario_id"),
        Index(
            "uq_practice_session_open",
            "user_id",
            "scenario_id",
            "mode",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        CheckConstraint("mode IN ('guided','sandbox','exam')", name="mode"),
        CheckConstraint("status IN ('active','completed','abandoned')", name="status"),
    )
    id: Mapped[IdPk]
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), index=True
    )
    scenario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("practice_scenario.id")
    )
    version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("practice_scenario_version.id")
    )
    release_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("elma_release.id")
    )
    mode: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(12), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    policy: Mapped[dict[str, Any]] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PracticeAction(Base):
    __tablename__ = "practice_action"
    __table_args__ = (UniqueConstraint("session_id", "request_id"),)
    id: Mapped[IdPk]
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("practice_session.id"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(80))
    fingerprint: Mapped[str] = mapped_column(String(64))
    screen_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    errors: Mapped[list] = mapped_column(JSONB)
    response: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[CreatedAt]


class PracticeResult(Base):
    __tablename__ = "practice_result"
    id: Mapped[IdPk]
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("practice_session.id"), unique=True
    )
    score_pct: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean)
    duration_s: Mapped[int] = mapped_column(Integer)
    errors: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[CreatedAt]


class PracticeAsset(Base):
    __tablename__ = "practice_asset"
    id: Mapped[IdPk]
    scenario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("practice_scenario.id"), index=True
    )
    data: Mapped[str] = mapped_column()  # re-encoded PNG as base64; max 2 MB source
    created_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    created_at: Mapped[CreatedAt]
