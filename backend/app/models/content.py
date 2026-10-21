from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IdPk, pg_enum
from app.models.enums import LessonVersionStatus, ModuleType, ReleaseStatus, VideoStatus


class Course(Base):
    __tablename__ = "course"

    id: Mapped[IdPk]
    code: Mapped[str] = mapped_column(String(48), unique=True)
    title_uz: Mapped[str] = mapped_column(String(200))
    title_ru: Mapped[str] = mapped_column(String(200))


class ElmaRelease(Base):
    """An Elma365 release; content changes go live only when a release is published."""

    __tablename__ = "elma_release"
    __table_args__ = (
        Index(
            "uq_elma_release_single_draft",
            "status",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
        CheckConstraint("transition_days BETWEEN 0 AND 365", name="transition_days"),
    )

    id: Mapped[IdPk]
    code: Mapped[str] = mapped_column(String(32), unique=True)
    notes: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[ReleaseStatus] = mapped_column(
        pg_enum(ReleaseStatus, "release_status"), default=ReleaseStatus.draft
    )
    # Days an older certificate stays valid after publish (0 = recertify immediately).
    transition_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    created_at: Mapped[CreatedAt]
    published_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Module(Base):
    __tablename__ = "module"
    __table_args__ = (
        # The content model has exactly one shared CORE module.
        Index("uq_module_single_core", "type", unique=True, postgresql_where=text("type = 'core'")),
        CheckConstraint("test_question_count BETWEEN 1 AND 100", name="test_question_count"),
        CheckConstraint("test_pass_pct BETWEEN 1 AND 100", name="test_pass_pct"),
        CheckConstraint("test_time_limit_min BETWEEN 1 AND 240", name="test_time_limit_min"),
        CheckConstraint("test_max_attempts BETWEEN 1 AND 20", name="test_max_attempts"),
        CheckConstraint("test_cooldown_hours BETWEEN 0 AND 720", name="test_cooldown_hours"),
    )

    id: Mapped[IdPk]
    course_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("course.id"))
    code: Mapped[str] = mapped_column(String(32), unique=True)
    qprefix: Mapped[str] = mapped_column(String(8), unique=True)  # question numbers: F-031
    type: Mapped[ModuleType] = mapped_column(pg_enum(ModuleType, "module_type"))
    title_uz: Mapped[str] = mapped_column(String(200))
    title_ru: Mapped[str] = mapped_column(String(200))
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    current_release_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("elma_release.id")
    )
    test_question_count: Mapped[int] = mapped_column(Integer, default=15, server_default="15")
    test_pass_pct: Mapped[int] = mapped_column(Integer, default=80, server_default="80")
    test_time_limit_min: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    test_max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    test_cooldown_hours: Mapped[int] = mapped_column(Integer, default=24, server_default="24")
    test_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lessons: Mapped[list[Lesson]] = relationship(back_populates="module", order_by="Lesson.sort")


class Lesson(Base):
    """A lesson's identity; its media lives in one LessonVersion per release that changed it."""

    __tablename__ = "lesson"

    id: Mapped[IdPk]
    module_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("module.id"), index=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    title_uz: Mapped[str] = mapped_column(String(300))
    title_ru: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[CreatedAt]

    module: Mapped[Module] = relationship(back_populates="lessons")


class VideoAsset(Base):
    __tablename__ = "video_asset"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[VideoStatus] = mapped_column(
        pg_enum(VideoStatus, "video_status"), default=VideoStatus.uploaded
    )
    progress_pct: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    duration_s: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    # Mandatory "recorded on test environment with synthetic client data only" confirmation.
    synthetic_confirmed_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    synthetic_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    uploaded_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    created_at: Mapped[CreatedAt]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LessonVersion(Base):
    __tablename__ = "lesson_version"
    __table_args__ = (
        UniqueConstraint("lesson_id", "release_id", name="uq_lesson_version_lesson_release"),
        Index(
            "uq_lesson_version_published",
            "lesson_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
        ),
        Index(
            "uq_lesson_version_draft",
            "lesson_id",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
    )

    id: Mapped[IdPk]
    lesson_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lesson.id", ondelete="CASCADE"), index=True
    )
    release_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("elma_release.id"), index=True
    )
    status: Mapped[LessonVersionStatus] = mapped_column(
        pg_enum(LessonVersionStatus, "lesson_version_status"), default=LessonVersionStatus.draft
    )
    video_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("video_asset.id"))
    vtt_uz_path: Mapped[str | None] = mapped_column(String(255))
    vtt_ru_path: Mapped[str | None] = mapped_column(String(255))
    pdf_uz_path: Mapped[str | None] = mapped_column(String(255))
    pdf_ru_path: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[CreatedAt]
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    lesson: Mapped[Lesson] = relationship()
    video_asset: Mapped[VideoAsset | None] = relationship()
