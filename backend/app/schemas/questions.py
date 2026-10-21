from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models import Lesson, LessonVersion, Module, Question
from app.models.enums import QuestionOrigin, QuestionStatus, QuestionType, RetiredReason
from app.services import media, questions


class OptionIn(BaseModel):
    id: int | None = None  # existing option (required when editing an approved question)
    text_uz: str = Field(min_length=1, max_length=1000)
    text_ru: str = Field(min_length=1, max_length=1000)
    is_correct: bool = False


class QuestionIn(BaseModel):
    lesson_id: int
    video_ts_s: int = Field(0, ge=0, le=36000)
    type: QuestionType
    text_uz: str = Field(min_length=1, max_length=2000)
    text_ru: str = Field(min_length=1, max_length=2000)
    explanation_uz: str = Field("", max_length=2000)
    explanation_ru: str = Field("", max_length=2000)
    difficulty: int = Field(2, ge=1, le=3)
    options: list[OptionIn] = Field(min_length=2, max_length=8)


class QuestionPatch(BaseModel):
    lesson_id: int | None = None
    video_ts_s: int | None = Field(None, ge=0, le=36000)
    type: QuestionType | None = None
    text_uz: str | None = Field(None, min_length=1, max_length=2000)
    text_ru: str | None = Field(None, min_length=1, max_length=2000)
    explanation_uz: str | None = Field(None, max_length=2000)
    explanation_ru: str | None = Field(None, max_length=2000)
    difficulty: int | None = Field(None, ge=1, le=3)
    options: list[OptionIn] | None = Field(None, min_length=2, max_length=8)


class OptionOut(BaseModel):
    id: int
    sort: int
    text_uz: str
    text_ru: str
    is_correct: bool


class StatsOut(BaseModel):
    attempts: int
    correct: int
    correct_pct: float | None
    flagged: bool


class QuestionOut(BaseModel):
    id: int
    number: str
    module_id: int
    status: QuestionStatus
    retired_reason: RetiredReason | None
    type: QuestionType
    difficulty: int
    lesson_id: int
    lesson_title_uz: str
    lesson_title_ru: str
    lesson_version_id: int
    release_code: str
    version_live: bool
    video_ts_s: int
    text_uz: str
    text_ru: str
    explanation_uz: str
    explanation_ru: str
    options: list[OptionOut]
    image_url: str | None
    origin: QuestionOrigin
    ai_source_start_s: float | None
    ai_source_end_s: float | None
    ai_source_excerpt: str | None
    stats: StatsOut
    created_at: datetime
    approved_at: datetime | None
    retired_at: datetime | None

    @classmethod
    def of(
        cls, q: Question, module: Module, lesson: Lesson, version: LessonVersion, release_code: str
    ) -> QuestionOut:
        return cls(
            id=q.id, number=questions.number(module, q), module_id=q.module_id, status=q.status,
            retired_reason=q.retired_reason, type=q.type, difficulty=q.difficulty,
            lesson_id=lesson.id, lesson_title_uz=lesson.title_uz, lesson_title_ru=lesson.title_ru,
            lesson_version_id=version.id, release_code=release_code,
            version_live=version.status == "published", video_ts_s=q.video_ts_s,
            text_uz=q.text_uz, text_ru=q.text_ru, explanation_uz=q.explanation_uz,
            explanation_ru=q.explanation_ru,
            options=[OptionOut(id=o.id, sort=o.sort, text_uz=o.text_uz, text_ru=o.text_ru,
                               is_correct=o.is_correct) for o in q.options],
            image_url=media.url(q.image_path), origin=q.origin,
            ai_source_start_s=q.ai_source_start_s, ai_source_end_s=q.ai_source_end_s,
            ai_source_excerpt=q.ai_source_excerpt,
            stats=StatsOut(attempts=q.stat_attempts, correct=q.stat_correct,
                           correct_pct=questions.correct_pct(q), flagged=questions.is_flagged(q)),
            created_at=q.created_at, approved_at=q.approved_at, retired_at=q.retired_at,
        )  # fmt: skip


class PoolOut(BaseModel):
    question_count: int
    required: int
    approved_active: int
    by_difficulty: dict[int, int]
    drafts: int
    publishable: bool
    test_published: bool
