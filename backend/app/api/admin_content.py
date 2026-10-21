"""Modules, lessons and lesson media (methodologist + admin; module create/reorder admin only)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import clock
from app.api.common import body_reader
from app.auth.deps import require_roles
from app.db import get_db
from app.errors import AppError, not_found
from app.models import (
    AppUser,
    Course,
    ElmaRelease,
    Lesson,
    LessonVersion,
    Module,
    VideoAsset,
)
from app.models.enums import (
    AccessRole,
    JobKind,
    JobLane,
    Language,
    LessonVersionStatus,
    ModuleType,
    VideoStatus,
)
from app.schemas.content import (
    CueOut,
    LessonAdminOut,
    LessonIn,
    LessonPatch,
    ModuleAdminOut,
    ModuleIn,
    ModulePatch,
    ReorderIn,
    VersionOut,
    VideoOut,
    lesson_admin_out,
)
from app.services import audit, content, media, questions, releases, vtt
from app.worker.runner import enqueue

router = APIRouter(prefix="/admin", tags=["admin: content"])
editor = require_roles(AccessRole.methodologist)
admin_only = require_roles()

MAX_VIDEO_BYTES = 2 * 1024**3
MAX_PDF_BYTES = 50 * 1024 * 1024
read_vtt = body_reader(vtt.MAX_BYTES, "vtt.too_large", editor)
read_pdf = body_reader(MAX_PDF_BYTES, "pdf.too_large", editor)


def _release_codes(db: Session) -> dict[int, str]:
    return dict(db.execute(select(ElmaRelease.id, ElmaRelease.code)).all())


def _module(db: Session, module_id: int) -> Module:
    module = db.get(Module, module_id)
    if module is None:
        raise not_found("module")
    return module


def _lesson(db: Session, lesson_id: int) -> Lesson:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise not_found("lesson")
    return lesson


def _version(db: Session, version_id: int) -> LessonVersion:
    version = db.scalar(
        select(LessonVersion)
        .options(selectinload(LessonVersion.video_asset))
        .where(LessonVersion.id == version_id)
    )
    if version is None:
        raise not_found("version")
    return version


def _editable_version(db: Session, version_id: int) -> LessonVersion:
    """Subtitles and PDFs can be fixed on draft and live versions, never on retired ones."""
    version = _version(db, version_id)
    if version.status == LessonVersionStatus.superseded:
        raise AppError(409, "version.superseded")
    return version


def _lesson_out(db: Session, lesson: Lesson) -> LessonAdminOut:
    published = content.versions_by_lesson(db, [lesson.id], LessonVersionStatus.published)
    draft = content.versions_by_lesson(db, [lesson.id], LessonVersionStatus.draft)
    return lesson_admin_out(
        lesson, published.get(lesson.id), draft.get(lesson.id), _release_codes(db)
    )


def _version_out(db: Session, version: LessonVersion) -> VersionOut:
    return VersionOut.of(version, _release_codes(db)[version.release_id])


def _modules_out(db: Session, modules: list[Module]) -> list[ModuleAdminOut]:
    totals = dict(
        db.execute(select(Lesson.module_id, func.count()).group_by(Lesson.module_id)).all()
    )
    live = dict(
        db.execute(
            select(Lesson.module_id, func.count())
            .join(LessonVersion, LessonVersion.lesson_id == Lesson.id)
            .where(LessonVersion.status == LessonVersionStatus.published)
            .group_by(Lesson.module_id)
        ).all()
    )
    codes = _release_codes(db)
    return [
        ModuleAdminOut.of(
            m, codes.get(m.current_release_id or 0), totals.get(m.id, 0), live.get(m.id, 0)
        )
        for m in modules
    ]


def _apply_order(items: dict[int, Lesson | Module], ids: list[int]) -> None:
    if len(ids) != len(set(ids)) or set(ids) != set(items):
        raise AppError(400, "reorder.mismatch")
    for position, item_id in enumerate(ids, start=1):
        items[item_id].sort = position


# --- modules ------------------------------------------------------------------------


@router.get("/modules", response_model=list[ModuleAdminOut])
def list_modules(db: Session = Depends(get_db), _: AppUser = Depends(editor)):
    return _modules_out(db, list(db.scalars(select(Module).order_by(Module.sort, Module.id))))


@router.post("/modules", response_model=ModuleAdminOut, status_code=201)
def create_module(
    body: ModuleIn, actor: AppUser = Depends(admin_only), db: Session = Depends(get_db)
):
    course = db.scalar(select(Course).order_by(Course.id))
    if course is None:
        raise AppError(409, "course.missing")
    if body.type == ModuleType.core and db.scalar(
        select(Module.id).where(Module.type == ModuleType.core)
    ):
        raise AppError(409, "module.core_exists")
    if db.scalar(select(Module.id).where(Module.code == body.code)):
        raise AppError(409, "module.code_taken")
    if db.scalar(select(Module.id).where(Module.qprefix == body.qprefix)):
        raise AppError(409, "module.qprefix_taken")
    last = db.scalar(select(func.max(Module.sort)))
    module = Module(course_id=course.id, sort=(last or 0) + 1, **body.model_dump())
    db.add(module)
    db.flush()
    audit.record(db, "module.created", actor_id=actor.id, entity="module", entity_id=module.id)
    db.commit()
    return _modules_out(db, [module])[0]


@router.post("/modules/reorder", status_code=204)
def reorder_modules(
    body: ReorderIn, _: AppUser = Depends(admin_only), db: Session = Depends(get_db)
) -> Response:
    _apply_order({m.id: m for m in db.scalars(select(Module))}, body.ids)
    db.commit()
    return Response(status_code=204)


@router.patch("/modules/{module_id}", response_model=ModuleAdminOut)
def patch_module(
    module_id: int,
    body: ModulePatch,
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
):
    module = _module(db, module_id)
    changes = body.model_dump(exclude_none=True)
    new_n = changes.get("test_question_count", module.test_question_count)
    if module.test_published_at is not None and new_n != module.test_question_count:
        pool = questions.pool_status(db, module, new_n)  # the published test keeps 3 x N
        if not pool.publishable:
            raise AppError(
                409, "test.pool_too_small", {"have": pool.approved_active, "need": pool.required}
            )
    for attr, value in changes.items():
        setattr(module, attr, value)
    if changes:
        audit.record(
            db, "module.updated", actor_id=actor.id, entity="module", entity_id=module.id,
            data=changes,
        )  # fmt: skip
    db.commit()
    return _modules_out(db, [module])[0]


# --- lessons ------------------------------------------------------------------------


@router.get("/modules/{module_id}/lessons", response_model=list[LessonAdminOut])
def module_lessons(module_id: int, db: Session = Depends(get_db), _: AppUser = Depends(editor)):
    _module(db, module_id)
    lessons = list(
        db.scalars(
            select(Lesson).where(Lesson.module_id == module_id).order_by(Lesson.sort, Lesson.id)
        )
    )
    ids = [lesson.id for lesson in lessons]
    published = content.versions_by_lesson(db, ids, LessonVersionStatus.published)
    draft = content.versions_by_lesson(db, ids, LessonVersionStatus.draft)
    codes = _release_codes(db)
    return [
        lesson_admin_out(lesson, published.get(lesson.id), draft.get(lesson.id), codes)
        for lesson in lessons
    ]


@router.post("/modules/{module_id}/lessons", response_model=LessonAdminOut, status_code=201)
def create_lesson(
    module_id: int,
    body: LessonIn,
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
):
    module = _module(db, module_id)
    lesson, _ = releases.create_lesson(db, module, body.title_uz, body.title_ru, actor.id)
    db.commit()
    return _lesson_out(db, lesson)


@router.post("/modules/{module_id}/lessons/reorder", status_code=204)
def reorder_lessons(
    module_id: int, body: ReorderIn, _: AppUser = Depends(editor), db: Session = Depends(get_db)
) -> Response:
    _module(db, module_id)
    lessons = db.scalars(select(Lesson).where(Lesson.module_id == module_id))
    _apply_order({lesson.id: lesson for lesson in lessons}, body.ids)
    db.commit()
    return Response(status_code=204)


@router.get("/lessons/{lesson_id}", response_model=LessonAdminOut)
def get_lesson(lesson_id: int, db: Session = Depends(get_db), _: AppUser = Depends(editor)):
    return _lesson_out(db, _lesson(db, lesson_id))


@router.patch("/lessons/{lesson_id}", response_model=LessonAdminOut)
def patch_lesson(
    lesson_id: int,
    body: LessonPatch,
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
):
    lesson = _lesson(db, lesson_id)
    changes = body.model_dump(exclude_none=True)
    for attr, value in changes.items():
        setattr(lesson, attr, value)
    if changes:
        audit.record(
            db, "lesson.updated", actor_id=actor.id, entity="lesson", entity_id=lesson.id,
            data=changes,
        )  # fmt: skip
    db.commit()
    return _lesson_out(db, lesson)


@router.delete("/lessons/{lesson_id}", status_code=204)
def delete_lesson(
    lesson_id: int, actor: AppUser = Depends(editor), db: Session = Depends(get_db)
) -> Response:
    """Only a lesson that never went live can be deleted."""
    lesson = _lesson(db, lesson_id)
    versions = list(db.scalars(select(LessonVersion).where(LessonVersion.lesson_id == lesson.id)))
    if any(v.status != LessonVersionStatus.draft for v in versions):
        raise AppError(409, "lesson.already_published")
    if content.has_questions(db, [v.id for v in versions]):
        raise AppError(409, "lesson.has_questions")
    for version in versions:
        content.delete_version(db, version)
    audit.record(
        db, "lesson.deleted", actor_id=actor.id, entity="lesson", entity_id=lesson.id,
        data={"title_uz": lesson.title_uz},
    )  # fmt: skip
    db.delete(lesson)
    db.commit()
    return Response(status_code=204)


# --- video ----------------------------------------------------------------------------


@dataclass
class _Received:
    path: Path
    size: int


def _video_target(
    version_id: int,
    synthetic_data_confirmed: bool = Query(False),
    _: AppUser = Depends(editor),
    db: Session = Depends(get_db),
) -> int:
    """Checked before a single byte of a (possibly 2 GB) upload is accepted."""
    if not synthetic_data_confirmed:
        raise AppError(400, "video.synthetic_confirmation_required")
    version = db.get(LessonVersion, version_id)
    if version is None:
        raise not_found("version")
    if version.status != LessonVersionStatus.draft:
        raise AppError(409, "version.not_draft")  # a live video changes only via a release
    db.rollback()  # no open transaction while the body streams in
    return version_id


async def _receive_video(request: Request, _: int = Depends(_video_target)) -> _Received:
    tmp = media.new_tmp_path()
    size = 0
    try:
        with tmp.open("wb") as fh:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_VIDEO_BYTES:
                    raise AppError(413, "video.too_large", {"max_gb": 2})
                fh.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise AppError(400, "video.empty")
    return _Received(tmp, size)


@router.put("/lesson-versions/{version_id}/video", response_model=VideoOut, status_code=202)
def upload_video(
    version_id: int,
    filename: str = Query("video.mp4", min_length=1, max_length=255),
    received: _Received = Depends(_receive_video),
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
):
    """Raw MP4 body (no multipart). Requires ?synthetic_data_confirmed=true."""
    try:
        version = db.scalar(
            select(LessonVersion).where(LessonVersion.id == version_id).with_for_update()
        )
        if version is None or version.status != LessonVersionStatus.draft:
            raise AppError(409, "version.not_draft")
        now = clock.utcnow()
        asset = VideoAsset(
            id=uuid.uuid4(),
            original_filename=filename,
            size_bytes=received.size,
            status=VideoStatus.uploaded,
            synthetic_confirmed_by=actor.id,
            synthetic_confirmed_at=now,
            uploaded_by=actor.id,
        )
        media.move_into_originals(received.path, asset.id)
    except BaseException:
        received.path.unlink(missing_ok=True)
        raise
    previous = version.video_asset_id
    db.add(asset)
    db.flush()
    version.video_asset_id = asset.id
    db.flush()
    content.drop_asset_if_unreferenced(db, previous)
    enqueue(db, JobKind.transcode, JobLane.media, {"video_asset_id": str(asset.id)}, actor.id)
    audit.record(
        db, "video.uploaded", actor_id=actor.id, entity="lesson_version", entity_id=version.id,
        data={"asset_id": str(asset.id), "filename": filename, "size_bytes": received.size,
              "synthetic_data_confirmed": True},
    )  # fmt: skip
    db.commit()
    return VideoOut.of(asset)


@router.get("/video-assets/{asset_id}", response_model=VideoOut)
def video_status(asset_id: uuid.UUID, db: Session = Depends(get_db), _: AppUser = Depends(editor)):
    asset = db.get(VideoAsset, asset_id)
    if asset is None:
        raise not_found("video")
    return VideoOut.of(asset)


# --- subtitles and reference PDFs -------------------------------------------------------


@router.put("/lesson-versions/{version_id}/subtitles/{lang}", response_model=VersionOut)
def upload_subtitles(
    version_id: int,
    lang: Language,
    data: bytes = Depends(read_vtt),
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
):
    version = _editable_version(db, version_id)
    try:
        text = vtt.decode(data)
        cues = vtt.parse(text)
    except vtt.VttError as exc:
        raise AppError(400, exc.code, {"line": exc.line}) from exc
    asset = version.video_asset
    if asset is not None and asset.status == VideoStatus.ready and asset.duration_s:
        last_end = vtt.last_cue_end(cues)
        if last_end > asset.duration_s + releases.VTT_OVERRUN_S:
            raise AppError(
                400, "vtt.exceeds_video", {"last_cue_end": last_end, "duration": asset.duration_s}
            )
    column = f"vtt_{lang.value}_path"
    previous = getattr(version, column)
    rel = media.write_new("vtt", f"{version.id}-{lang.value}", ".vtt", text.encode("utf-8"))
    setattr(version, column, rel)
    db.flush()
    content.drop_unreferenced_files(db, [previous])
    audit.record(
        db, "subtitles.uploaded", actor_id=actor.id, entity="lesson_version",
        entity_id=version.id, data={"lang": lang.value, "cues": len(cues)},
    )  # fmt: skip
    db.commit()
    return _version_out(db, version)


@router.put("/lesson-versions/{version_id}/pdf/{lang}", response_model=VersionOut)
def upload_pdf(
    version_id: int,
    lang: Language,
    data: bytes = Depends(read_pdf),
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
):
    version = _editable_version(db, version_id)
    if not data.startswith(b"%PDF-"):
        raise AppError(400, "pdf.invalid")
    column = f"pdf_{lang.value}_path"
    previous = getattr(version, column)
    setattr(version, column, media.write_new("pdf", f"{version.id}-{lang.value}", ".pdf", data))
    db.flush()
    content.drop_unreferenced_files(db, [previous])
    audit.record(
        db, "pdf.uploaded", actor_id=actor.id, entity="lesson_version", entity_id=version.id,
        data={"lang": lang.value, "size_bytes": len(data)},
    )  # fmt: skip
    db.commit()
    return _version_out(db, version)


@router.delete("/lesson-versions/{version_id}/pdf/{lang}", response_model=VersionOut)
def delete_pdf(
    version_id: int,
    lang: Language,
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
):
    version = _editable_version(db, version_id)
    column = f"pdf_{lang.value}_path"
    previous = getattr(version, column)
    setattr(version, column, None)
    db.flush()
    content.drop_unreferenced_files(db, [previous])
    audit.record(
        db, "pdf.deleted", actor_id=actor.id, entity="lesson_version", entity_id=version.id,
        data={"lang": lang.value},
    )  # fmt: skip
    db.commit()
    return _version_out(db, version)


@router.get("/lesson-versions/{version_id}/transcript", response_model=list[CueOut])
def transcript(
    version_id: int,
    lang: Language = Query(...),
    db: Session = Depends(get_db),
    _: AppUser = Depends(editor),
):
    path = getattr(_version(db, version_id), f"vtt_{lang.value}_path")
    if not path:
        raise not_found("subtitles")
    cues = vtt.parse(media.abs_path(path).read_text(encoding="utf-8-sig"))
    return [CueOut(start=c.start, end=c.end, text=c.text) for c in cues]
