from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import ElmaRelease, Lesson, LessonVersion, Module, VideoAsset
from app.models.enums import (
    LessonVersionStatus,
    ModuleType,
    ReleaseStatus,
    VideoStatus,
)
from app.services import media

Title = Field(min_length=1, max_length=200)


class ModuleIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,31}$")
    qprefix: str = Field(pattern=r"^[A-Z]{1,8}$")
    type: ModuleType
    title_uz: str = Title
    title_ru: str = Title


class ModulePatch(BaseModel):
    title_uz: str | None = Field(None, min_length=1, max_length=200)
    title_ru: str | None = Field(None, min_length=1, max_length=200)
    test_question_count: int | None = Field(None, ge=1, le=100)
    test_pass_pct: int | None = Field(None, ge=1, le=100)
    test_time_limit_min: int | None = Field(None, ge=1, le=240)
    test_max_attempts: int | None = Field(None, ge=1, le=20)
    test_cooldown_hours: int | None = Field(None, ge=0, le=720)


class ReorderIn(BaseModel):
    ids: list[int] = Field(min_length=1)


class ModuleAdminOut(BaseModel):
    id: int
    code: str
    qprefix: str
    type: ModuleType
    title_uz: str
    title_ru: str
    sort: int
    release_code: str | None
    lessons_total: int
    lessons_live: int
    test_question_count: int
    test_pass_pct: int
    test_time_limit_min: int
    test_max_attempts: int
    test_cooldown_hours: int
    test_published_at: datetime | None

    @classmethod
    def of(cls, m: Module, release_code: str | None, total: int, live: int) -> ModuleAdminOut:
        return cls(
            id=m.id, code=m.code, qprefix=m.qprefix, type=m.type, title_uz=m.title_uz,
            title_ru=m.title_ru, sort=m.sort, release_code=release_code, lessons_total=total,
            lessons_live=live, test_question_count=m.test_question_count,
            test_pass_pct=m.test_pass_pct, test_time_limit_min=m.test_time_limit_min,
            test_max_attempts=m.test_max_attempts, test_cooldown_hours=m.test_cooldown_hours,
            test_published_at=m.test_published_at,
        )  # fmt: skip


class LessonIn(BaseModel):
    title_uz: str = Field(min_length=1, max_length=300)
    title_ru: str = Field(min_length=1, max_length=300)


class LessonPatch(BaseModel):
    title_uz: str | None = Field(None, min_length=1, max_length=300)
    title_ru: str | None = Field(None, min_length=1, max_length=300)


class VideoOut(BaseModel):
    asset_id: uuid.UUID
    status: VideoStatus
    progress_pct: int
    duration_s: float | None
    error: str | None
    original_filename: str

    @classmethod
    def of(cls, a: VideoAsset) -> VideoOut:
        return cls(
            asset_id=a.id, status=a.status, progress_pct=a.progress_pct, duration_s=a.duration_s,
            error=a.error, original_filename=a.original_filename,
        )  # fmt: skip


class VersionOut(BaseModel):
    id: int
    release_id: int
    release_code: str
    status: LessonVersionStatus
    video: VideoOut | None
    vtt_uz_url: str | None
    vtt_ru_url: str | None
    pdf_uz_url: str | None
    pdf_ru_url: str | None
    published_at: datetime | None

    @classmethod
    def of(cls, v: LessonVersion, release_code: str) -> VersionOut:
        return cls(
            id=v.id, release_id=v.release_id, release_code=release_code, status=v.status,
            video=VideoOut.of(v.video_asset) if v.video_asset else None,
            vtt_uz_url=media.url(v.vtt_uz_path), vtt_ru_url=media.url(v.vtt_ru_path),
            pdf_uz_url=media.url(v.pdf_uz_path), pdf_ru_url=media.url(v.pdf_ru_path),
            published_at=v.published_at,
        )  # fmt: skip


class LessonAdminOut(BaseModel):
    id: int
    module_id: int
    sort: int
    title_uz: str
    title_ru: str
    published: VersionOut | None
    draft: VersionOut | None


class CueOut(BaseModel):
    start: float
    end: float
    text: str


class ReleaseIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    notes: str = Field("", max_length=2000)


class ReleasePatch(BaseModel):
    code: str | None = Field(None, min_length=1, max_length=32)
    notes: str | None = Field(None, max_length=2000)
    transition_days: int | None = Field(None, ge=0, le=365)


class ReleaseOut(BaseModel):
    id: int
    code: str
    notes: str
    status: ReleaseStatus
    transition_days: int
    created_at: datetime
    published_at: datetime | None
    lessons_count: int

    @classmethod
    def of(cls, r: ElmaRelease, lessons_count: int) -> ReleaseOut:
        return cls(
            id=r.id, code=r.code, notes=r.notes, status=r.status,
            transition_days=r.transition_days, created_at=r.created_at,
            published_at=r.published_at, lessons_count=lessons_count,
        )  # fmt: skip


class ReleaseLessonOut(BaseModel):
    lesson_id: int
    module_id: int
    title_uz: str
    title_ru: str
    change: str  # "changed" (new version of a live lesson) | "added" (new lesson)
    version: VersionOut
    problems: list[str]


class ReleaseModuleProblem(BaseModel):
    module_id: int
    code: str  # "pool_too_small"
    params: dict[str, Any]


class ReleaseImpact(BaseModel):
    module_id: int
    code: str
    title_uz: str
    title_ru: str
    changed_lessons: int
    added_lessons: int
    total_lessons: int  # once the release is live
    certificates: int  # current certificates that will need renewal
    learners: int
    questions_pending: int  # draft questions on this release's lessons
    pool_have: int | None  # None while the module's test is not published
    pool_need: int | None


class ReleaseDetail(ReleaseOut):
    lessons: list[ReleaseLessonOut]
    module_problems: list[ReleaseModuleProblem]
    impact: list[ReleaseImpact]  # draft releases only
    ready: bool


def lesson_admin_out(
    lesson: Lesson,
    published: LessonVersion | None,
    draft: LessonVersion | None,
    release_codes: dict[int, str],
) -> LessonAdminOut:
    return LessonAdminOut(
        id=lesson.id,
        module_id=lesson.module_id,
        sort=lesson.sort,
        title_uz=lesson.title_uz,
        title_ru=lesson.title_ru,
        published=VersionOut.of(published, release_codes[published.release_id])
        if published
        else None,
        draft=VersionOut.of(draft, release_codes[draft.release_id]) if draft else None,
    )
