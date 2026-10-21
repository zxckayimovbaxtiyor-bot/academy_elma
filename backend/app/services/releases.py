"""Elma365 releases: the only way content changes reach learners.

A draft release collects new lessons and new versions of changed lessons.
Publishing makes them live in one transaction: the new versions go live,
certificates of the affected modules (only those) need renewal, questions about
the replaced videos are retired and open remediation on them is closed. A module
with a published test keeps at least 3 x N questions in its pool.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app import clock
from app.errors import AppError
from app.models import ElmaRelease, Lesson, LessonVersion, Module, Question
from app.models.enums import LessonVersionStatus, QuestionStatus, ReleaseStatus, VideoStatus
from app.services import audit, certificates, content, media, questions, remediation, vtt

CODE_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,31}$")
# Subtitles may run a moment past the last frame.
VTT_OVERRUN_S = 1.0


def get_draft(db: Session) -> ElmaRelease | None:
    return db.scalar(select(ElmaRelease).where(ElmaRelease.status == ReleaseStatus.draft))


def require_draft(db: Session) -> ElmaRelease:
    release = get_draft(db)
    if release is None:
        raise AppError(409, "release.no_draft")
    return release


def create_release(db: Session, code: str, notes: str, actor_id: int) -> ElmaRelease:
    code = code.strip()
    if not CODE_RE.match(code):
        raise AppError(400, "release.code_invalid")
    if get_draft(db) is not None:
        raise AppError(409, "release.draft_exists")
    if db.scalar(select(ElmaRelease.id).where(ElmaRelease.code == code)) is not None:
        raise AppError(409, "release.code_taken")
    release = ElmaRelease(code=code, notes=notes, created_by=actor_id)
    db.add(release)
    db.flush()
    audit.record(db, "release.created", actor_id=actor_id, entity="release", entity_id=release.id)
    return release


def create_lesson(
    db: Session, module: Module, title_uz: str, title_ru: str, actor_id: int
) -> tuple[Lesson, LessonVersion]:
    """New lessons live in the open draft release until it is published."""
    release = require_draft(db)
    last = db.scalar(select(func.max(Lesson.sort)).where(Lesson.module_id == module.id))
    lesson = Lesson(module_id=module.id, sort=(last or 0) + 1, title_uz=title_uz, title_ru=title_ru)
    db.add(lesson)
    db.flush()
    version = LessonVersion(lesson_id=lesson.id, release_id=release.id)
    db.add(version)
    db.flush()
    audit.record(db, "lesson.created", actor_id=actor_id, entity="lesson", entity_id=lesson.id)
    return lesson, version


def mark_changed(db: Session, release: ElmaRelease, lesson: Lesson, actor_id: int) -> LessonVersion:
    """Open a new version of a live lesson whose screen or process changed in this release.

    The video and both subtitle files must be uploaded again; reference PDFs are
    carried over and can be replaced.
    """
    if release.status != ReleaseStatus.draft:
        raise AppError(409, "release.not_draft")
    live = content.published_version(db, lesson.id)
    if live is None:
        raise AppError(409, "lesson.not_published")
    if content.versions_by_lesson(db, [lesson.id], LessonVersionStatus.draft):
        raise AppError(409, "lesson.already_in_release")
    version = LessonVersion(
        lesson_id=lesson.id,
        release_id=release.id,
        pdf_uz_path=live.pdf_uz_path,
        pdf_ru_path=live.pdf_ru_path,
    )
    db.add(version)
    db.flush()
    audit.record(
        db,
        "release.lesson_marked",
        actor_id=actor_id,
        entity="release",
        entity_id=release.id,
        data={"lesson_id": lesson.id},
    )
    return version


def unmark(db: Session, release: ElmaRelease, lesson: Lesson, actor_id: int) -> None:
    if release.status != ReleaseStatus.draft:
        raise AppError(409, "release.not_draft")
    version = db.scalar(
        select(LessonVersion).where(
            LessonVersion.lesson_id == lesson.id,
            LessonVersion.release_id == release.id,
            LessonVersion.status == LessonVersionStatus.draft,
        )
    )
    if version is None:
        raise AppError(404, "release_lesson.not_found")
    if content.published_version(db, lesson.id) is None:
        raise AppError(409, "lesson.new_in_release")  # delete the lesson instead
    if content.has_questions(db, [version.id]):
        raise AppError(409, "lesson.has_questions")
    content.delete_version(db, version)
    audit.record(
        db,
        "release.lesson_unmarked",
        actor_id=actor_id,
        entity="release",
        entity_id=release.id,
        data={"lesson_id": lesson.id},
    )


def draft_versions(db: Session, release: ElmaRelease) -> list[LessonVersion]:
    return list(
        db.scalars(
            select(LessonVersion)
            .options(selectinload(LessonVersion.video_asset), selectinload(LessonVersion.lesson))
            .where(
                LessonVersion.release_id == release.id,
                LessonVersion.status == LessonVersionStatus.draft,
            )
            .order_by(LessonVersion.lesson_id)
        )
    )


def version_problems(version: LessonVersion) -> list[str]:
    """What still blocks this version from going live (empty list = ready)."""
    problems: list[str] = []
    asset = version.video_asset
    if asset is None:
        problems.append("video_missing")
    elif asset.status != VideoStatus.ready:
        problems.append("video_not_ready")
    for lang in ("uz", "ru"):
        path = getattr(version, f"vtt_{lang}_path")
        if not path:
            problems.append(f"vtt_{lang}_missing")
        elif asset is not None and asset.status == VideoStatus.ready and asset.duration_s:
            cues = vtt.parse(media.abs_path(path).read_text(encoding="utf-8-sig"))
            if vtt.last_cue_end(cues) > asset.duration_s + VTT_OVERRUN_S:
                problems.append(f"vtt_{lang}_exceeds_video")
    if bool(version.pdf_uz_path) != bool(version.pdf_ru_path):
        problems.append("pdf_pair_incomplete")
    return problems


def lesson_problems(db: Session, versions: list[LessonVersion]) -> dict[int, list[str]]:
    """Problems per draft version id, including questions nobody has reviewed yet."""
    pending = set(
        db.scalars(
            select(Question.lesson_version_id)
            .where(
                Question.lesson_version_id.in_([v.id for v in versions] or [0]),
                Question.status == QuestionStatus.draft,
            )
            .distinct()
        )
    )
    return {
        v.id: version_problems(v) + (["questions_pending"] if v.id in pending else [])
        for v in versions
    }


def module_problems(
    db: Session, release: ElmaRelease, versions: list[LessonVersion]
) -> list[dict[str, Any]]:
    """A published test must still have a 3 x N pool once the release is live."""
    changed = [v.lesson_id for v in versions]
    module_ids = {v.lesson.module_id for v in versions}
    out = []
    for module in db.scalars(
        select(Module)
        .where(Module.id.in_(module_ids or [0]), Module.test_published_at.is_not(None))
        .order_by(Module.sort, Module.id)
    ):
        have = questions.pool_after_release(db, module.id, release.id, changed)
        need = questions.POOL_FACTOR * module.test_question_count
        if have < need:
            params = {"have": have, "need": need}
            out.append({"module_id": module.id, "code": "pool_too_small", "params": params})
    return out


def impact_preview(
    db: Session, release: ElmaRelease, versions: list[LessonVersion]
) -> list[dict[str, Any]]:
    """Per affected module: what changes, who renews, and the pool once the release is live.

    Only these modules are touched; certificates elsewhere never change.
    """
    by_module: dict[int, list[LessonVersion]] = {}
    for v in versions:
        by_module.setdefault(v.lesson.module_id, []).append(v)
    live = set(
        db.scalars(
            select(LessonVersion.lesson_id).where(
                LessonVersion.lesson_id.in_([v.lesson_id for v in versions] or [0]),
                LessonVersion.status == LessonVersionStatus.published,
            )
        )
    )
    pending = dict(
        db.execute(
            select(Question.module_id, func.count())
            .where(
                Question.lesson_version_id.in_([v.id for v in versions] or [0]),
                Question.status == QuestionStatus.draft,
            )
            .group_by(Question.module_id)
        ).all()
    )
    renewals = certificates.impact(db, by_module)
    out = []
    for module in db.scalars(
        select(Module).where(Module.id.in_(by_module or [0])).order_by(Module.sort, Module.id)
    ):
        drafts = by_module[module.id]
        changed = sum(1 for v in drafts if v.lesson_id in live)
        total = len(content.published_lessons(db, module.id)) + len(drafts) - changed
        published = module.test_published_at is not None
        lessons = [v.lesson_id for v in versions]
        out.append(
            {
                "module_id": module.id, "code": module.code, "title_uz": module.title_uz,
                "title_ru": module.title_ru, "changed_lessons": changed,
                "added_lessons": len(drafts) - changed, "total_lessons": total,
                "certificates": renewals.get(module.id, (0, 0))[0],
                "learners": renewals.get(module.id, (0, 0))[1],
                "questions_pending": pending.get(module.id, 0),
                "pool_have": questions.pool_after_release(db, module.id, release.id, lessons)
                if published else None,
                "pool_need": questions.POOL_FACTOR * module.test_question_count
                if published else None,
            }
        )  # fmt: skip
    return out


def checklist(db: Session, release: ElmaRelease) -> list[dict[str, Any]]:
    versions = draft_versions(db, release)
    if not versions:
        return [{"lesson_id": None, "code": "release_empty"}]
    by_version = lesson_problems(db, versions)
    lessons = [{"lesson_id": v.lesson_id, "code": c} for v in versions for c in by_version[v.id]]
    return lessons + module_problems(db, release, versions)


def publish(db: Session, release_id: int, actor_id: int) -> ElmaRelease:
    release = db.scalar(
        select(ElmaRelease).where(ElmaRelease.id == release_id).with_for_update()
    )
    if release is None:
        raise AppError(404, "release.not_found")
    if release.status != ReleaseStatus.draft:
        raise AppError(409, "release.not_draft")
    problems = checklist(db, release)
    if problems:
        raise AppError(409, "release.not_ready", {"problems": problems})

    lesson_ids = [v.lesson_id for v in draft_versions(db, release)]
    replaced = list(
        db.scalars(
            select(LessonVersion.id).where(
                LessonVersion.lesson_id.in_(lesson_ids),
                LessonVersion.status == LessonVersionStatus.published,
            )
        )
    )
    now = clock.utcnow()
    # Retire the old live versions first: one published version per lesson is a DB rule.
    db.execute(
        update(LessonVersion)
        .where(
            LessonVersion.lesson_id.in_(lesson_ids),
            LessonVersion.status == LessonVersionStatus.published,
        )
        .values(status=LessonVersionStatus.superseded, superseded_at=now)
    )
    db.execute(
        update(LessonVersion)
        .where(
            LessonVersion.release_id == release.id,
            LessonVersion.status == LessonVersionStatus.draft,
        )
        .values(status=LessonVersionStatus.published, published_at=now)
    )
    module_ids = list(
        db.scalars(select(Lesson.module_id).where(Lesson.id.in_(lesson_ids)).distinct())
    )
    db.execute(
        update(Module).where(Module.id.in_(module_ids)).values(current_release_id=release.id)
    )
    flagged = certificates.flag_recert(db, release, module_ids, now)
    # Questions about the old videos describe old screens; their fragments no longer exist.
    retired = questions.retire_for_superseded_versions(db, replaced)
    remediation.close_for_superseded_versions(db, replaced)
    release.status = ReleaseStatus.published
    release.published_at = now
    release.published_by = actor_id
    audit.record(
        db,
        "release.published",
        actor_id=actor_id,
        entity="release",
        entity_id=release.id,
        data={
            "lessons": len(lesson_ids), "module_ids": module_ids, "questions_retired": retired,
            "certificates_flagged": flagged,
        },  # fmt: skip
    )
    db.flush()
    db.expire_all()
    return release
