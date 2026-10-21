"""Elma365 releases (admin): draft → mark changed lessons → checklist → publish."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.auth.deps import require_roles
from app.db import get_db
from app.errors import AppError, not_found
from app.models import AppUser, ElmaRelease, Lesson, LessonVersion
from app.models.enums import LessonVersionStatus, ReleaseStatus
from app.schemas.content import (
    LessonAdminOut,
    ReleaseDetail,
    ReleaseImpact,
    ReleaseIn,
    ReleaseLessonOut,
    ReleaseModuleProblem,
    ReleaseOut,
    ReleasePatch,
    VersionOut,
    lesson_admin_out,
)
from app.services import audit, content, releases

router = APIRouter(prefix="/admin/releases", tags=["admin: releases"])
admin_only = require_roles()


def _release(db: Session, release_id: int) -> ElmaRelease:
    release = db.get(ElmaRelease, release_id)
    if release is None:
        raise not_found("release")
    return release


def _draft(db: Session, release_id: int) -> ElmaRelease:
    release = _release(db, release_id)
    if release.status != ReleaseStatus.draft:
        raise AppError(409, "release.not_draft")
    return release


def _lesson(db: Session, lesson_id: int) -> Lesson:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise not_found("lesson")
    return lesson


def _version_counts(db: Session) -> dict[int, int]:
    return dict(
        db.execute(
            select(LessonVersion.release_id, func.count()).group_by(LessonVersion.release_id)
        ).all()
    )


@router.get("", response_model=list[ReleaseOut])
def list_releases(db: Session = Depends(get_db), _: AppUser = Depends(admin_only)):
    rows = db.scalars(
        select(ElmaRelease).order_by(
            (ElmaRelease.status == ReleaseStatus.draft).desc(),
            ElmaRelease.published_at.desc().nulls_last(),
            ElmaRelease.id.desc(),
        )
    )
    counts = _version_counts(db)
    return [ReleaseOut.of(r, counts.get(r.id, 0)) for r in rows]


@router.post("", response_model=ReleaseOut, status_code=201)
def create_release(
    body: ReleaseIn, actor: AppUser = Depends(admin_only), db: Session = Depends(get_db)
):
    release = releases.create_release(db, body.code, body.notes, actor.id)
    db.commit()
    return ReleaseOut.of(release, 0)


@router.get("/{release_id}", response_model=ReleaseDetail)
def get_release(release_id: int, db: Session = Depends(get_db), _: AppUser = Depends(admin_only)):
    release = _release(db, release_id)
    versions = list(
        db.scalars(
            select(LessonVersion)
            .options(selectinload(LessonVersion.video_asset), selectinload(LessonVersion.lesson))
            .where(LessonVersion.release_id == release.id)
            .order_by(LessonVersion.lesson_id)
        )
    )
    earlier = aliased(LessonVersion)
    drafts = [v for v in versions if v.status == LessonVersionStatus.draft]
    draft_problems = releases.lesson_problems(db, drafts)
    lessons_out = []
    for v in versions:
        changed = db.scalar(
            select(exists().where(earlier.lesson_id == v.lesson_id, earlier.id < v.id))
        )
        problems = draft_problems.get(v.id, [])
        lessons_out.append(
            ReleaseLessonOut(
                lesson_id=v.lesson_id,
                module_id=v.lesson.module_id,
                title_uz=v.lesson.title_uz,
                title_ru=v.lesson.title_ru,
                change="changed" if changed else "added",
                version=VersionOut.of(v, release.code),
                problems=problems,
            )
        )
    is_draft = release.status == ReleaseStatus.draft
    found = releases.module_problems(db, release, drafts) if is_draft else []
    module_problems = [ReleaseModuleProblem(**p) for p in found]
    impact = [ReleaseImpact(**i) for i in releases.impact_preview(db, release, drafts)]
    ready = (
        is_draft
        and bool(lessons_out)
        and all(not item.problems for item in lessons_out)
        and not module_problems
    )
    base = ReleaseOut.of(release, len(versions)).model_dump()
    return ReleaseDetail(
        **base, lessons=lessons_out, module_problems=module_problems, impact=impact, ready=ready
    )


@router.patch("/{release_id}", response_model=ReleaseOut)
def patch_release(
    release_id: int,
    body: ReleasePatch,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
):
    release = _draft(db, release_id)
    if body.code is not None and body.code.strip() != release.code:
        code = body.code.strip()
        if not releases.CODE_RE.match(code):
            raise AppError(400, "release.code_invalid")
        if db.scalar(select(ElmaRelease.id).where(ElmaRelease.code == code)):
            raise AppError(409, "release.code_taken")
        release.code = code
    if body.notes is not None:
        release.notes = body.notes
    if body.transition_days is not None:
        release.transition_days = body.transition_days
    audit.record(
        db, "release.updated", actor_id=actor.id, entity="release", entity_id=release.id,
        data=body.model_dump(exclude_none=True),
    )  # fmt: skip
    db.commit()
    return ReleaseOut.of(release, _version_counts(db).get(release.id, 0))


@router.delete("/{release_id}", status_code=204)
def delete_release(
    release_id: int, actor: AppUser = Depends(admin_only), db: Session = Depends(get_db)
) -> Response:
    release = _draft(db, release_id)
    if _version_counts(db).get(release.id):
        raise AppError(409, "release.not_empty")
    audit.record(db, "release.deleted", actor_id=actor.id, data={"code": release.code})
    db.delete(release)
    db.commit()
    return Response(status_code=204)


@router.post("/{release_id}/lessons/{lesson_id}", response_model=LessonAdminOut, status_code=201)
def mark_lesson_changed(
    release_id: int,
    lesson_id: int,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
):
    release = _release(db, release_id)
    lesson = _lesson(db, lesson_id)
    draft = releases.mark_changed(db, release, lesson, actor.id)
    db.commit()
    published = content.published_version(db, lesson.id)
    codes = dict(db.execute(select(ElmaRelease.id, ElmaRelease.code)).all())
    return lesson_admin_out(lesson, published, draft, codes)


@router.delete("/{release_id}/lessons/{lesson_id}", status_code=204)
def unmark_lesson(
    release_id: int,
    lesson_id: int,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
) -> Response:
    releases.unmark(db, _release(db, release_id), _lesson(db, lesson_id), actor.id)
    db.commit()
    return Response(status_code=204)


@router.post("/{release_id}/publish", response_model=ReleaseOut)
def publish_release(
    release_id: int, actor: AppUser = Depends(admin_only), db: Session = Depends(get_db)
):
    release = releases.publish(db, release_id, actor.id)
    db.commit()
    return ReleaseOut.of(release, _version_counts(db).get(release.id, 0))
