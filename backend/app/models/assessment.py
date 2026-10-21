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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IdPk, pg_enum
from app.models.enums import (
    AttemptStatus,
    QuestionOrigin,
    QuestionStatus,
    QuestionType,
    RemediationResolution,
    RetiredReason,
)


class Question(Base):
    __tablename__ = "question"
    __table_args__ = (
        UniqueConstraint("module_id", "seq", name="uq_question_module_seq"),
        Index("ix_question_module_status", "module_id", "status"),
        CheckConstraint("difficulty BETWEEN 1 AND 3", name="difficulty"),
    )

    id: Mapped[IdPk]
    module_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("module.id"))
    seq: Mapped[int] = mapped_column(Integer)
    # The question is written against one lesson version; its elma_release is that version's.
    lesson_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("lesson_version.id"), index=True
    )
    video_ts_s: Mapped[int] = mapped_column(Integer, default=0)
    type: Mapped[QuestionType] = mapped_column(pg_enum(QuestionType, "question_type"))
    text_uz: Mapped[str] = mapped_column(Text)
    text_ru: Mapped[str] = mapped_column(Text)
    explanation_uz: Mapped[str] = mapped_column(Text, default="", server_default="")
    explanation_ru: Mapped[str] = mapped_column(Text, default="", server_default="")
    difficulty: Mapped[int] = mapped_column(SmallInteger, default=2)
    status: Mapped[QuestionStatus] = mapped_column(
        pg_enum(QuestionStatus, "question_status"), default=QuestionStatus.draft
    )
    retired_reason: Mapped[RetiredReason | None] = mapped_column(
        pg_enum(RetiredReason, "retired_reason")
    )
    image_path: Mapped[str | None] = mapped_column(String(255))
    origin: Mapped[QuestionOrigin] = mapped_column(
        pg_enum(QuestionOrigin, "question_origin"), default=QuestionOrigin.manual
    )
    ai_job_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("job.id"))
    ai_source_start_s: Mapped[float | None] = mapped_column(Float)
    ai_source_end_s: Mapped[float | None] = mapped_column(Float)
    ai_source_excerpt: Mapped[str | None] = mapped_column(Text)
    stat_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    stat_correct: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    approved_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    options: Mapped[list[QuestionOption]] = relationship(
        order_by="QuestionOption.sort", cascade="all, delete-orphan"
    )


class QuestionOption(Base):
    __tablename__ = "question_option"

    id: Mapped[IdPk]
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("question.id", ondelete="CASCADE"), index=True
    )
    # For ordering questions this is the correct step order.
    sort: Mapped[int] = mapped_column(Integer)
    text_uz: Mapped[str] = mapped_column(Text)
    text_ru: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)


class TestAttempt(Base):
    __test__ = False  # keep pytest from collecting this model as a test class
    __tablename__ = "test_attempt"
    __table_args__ = (
        Index("ix_test_attempt_user_module", "user_id", "module_id"),
        Index(
            "uq_test_attempt_open",
            "user_id",
            "module_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
        ),
    )

    id: Mapped[IdPk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    module_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("module.id"))
    release_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("elma_release.id"))
    status: Mapped[AttemptStatus] = mapped_column(
        pg_enum(AttemptStatus, "attempt_status"), default=AttemptStatus.in_progress
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Settings are copied from the module when the attempt starts.
    question_count: Mapped[int] = mapped_column(Integer)
    pass_pct: Mapped[int] = mapped_column(Integer)
    correct_count: Mapped[int | None] = mapped_column(Integer)
    score_pct: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool | None] = mapped_column(Boolean)


class AttemptQuestion(Base):
    __tablename__ = "attempt_question"

    attempt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("test_attempt.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    question_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("question.id"), index=True)
    option_order: Mapped[list[int]] = mapped_column(ARRAY(BigInteger))
    # SQL NULL (not JSON null) when unanswered or cleared.
    answer: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_correct: Mapped[bool | None] = mapped_column(Boolean)


class RemediationItem(Base):
    __tablename__ = "remediation_item"

    id: Mapped[IdPk]
    attempt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("test_attempt.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), index=True)
    lesson_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lesson.id"))
    lesson_version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lesson_version.id"))
    span_start_s: Mapped[float] = mapped_column(Float)
    span_end_s: Mapped[float] = mapped_column(Float)
    missed_count: Mapped[int] = mapped_column(Integer)
    watched: Mapped[list[list[float]]] = mapped_column(JSONB, default=list, server_default="[]")
    satisfied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    satisfied_reason: Mapped[RemediationResolution | None] = mapped_column(
        pg_enum(RemediationResolution, "remediation_resolution")
    )


class AttemptReset(Base):
    """Admin grants a fresh attempt cycle (mandatory reason, also written to audit)."""

    __tablename__ = "attempt_reset"
    __table_args__ = (
        Index("ix_attempt_reset_user_module", "user_id", "module_id"),
        CheckConstraint("length(btrim(reason)) > 0", name="reason_not_blank"),
    )

    id: Mapped[IdPk]
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    module_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("module.id"))
    reset_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
