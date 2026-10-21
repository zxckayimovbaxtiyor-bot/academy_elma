"""Question bank and test publishing (methodologist + admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.common import body_reader
from app.auth.deps import require_roles
from app.db import get_db
from app.errors import AppError, not_found
from app.models import AppUser, ElmaRelease, Lesson, LessonVersion, Module, Question
from app.models.enums import AccessRole, QuestionOrigin, QuestionStatus, QuestionType
from app.schemas.questions import PoolOut, QuestionIn, QuestionOut, QuestionPatch
from app.services import audit, content, media, questions

router = APIRouter(prefix="/admin", tags=["admin: questions"])
editor = require_roles(AccessRole.methodologist)
MAX_IMAGE_BYTES = 5 * 1024 * 1024
read_image = body_reader(MAX_IMAGE_BYTES, "image.too_large", editor)
_IMAGE_TYPES = ((b"\x89PNG\r\n\x1a\n", ".png"), (b"\xff\xd8\xff", ".jpg"))


def _module(db: Session, module_id: int) -> Module:
    module = db.get(Module, module_id)
    if module is None:
        raise not_found("module")
    return module


def _question(db: Session, question_id: int) -> Question:
    q = db.scalar(
        select(Question).options(selectinload(Question.options)).where(Question.id == question_id)
    )
    if q is None:
        raise not_found("question")
    return q


def _out(db: Session, rows: list[Question]) -> list[QuestionOut]:
    if not rows:
        return []
    versions = {
        v.id: v
        for v in db.scalars(
            select(LessonVersion)
            .options(selectinload(LessonVersion.lesson))
            .where(LessonVersion.id.in_({q.lesson_version_id for q in rows}))
        )
    }
    modules = {m.id: m for m in db.scalars(select(Module))}
    codes = dict(db.execute(select(ElmaRelease.id, ElmaRelease.code)).all())
    out = []
    for q in rows:
        version = versions[q.lesson_version_id]
        out.append(
            QuestionOut.of(
                q, modules[q.module_id], version.lesson, version, codes[version.release_id]
            )
        )
    return out


def _one(db: Session, q: Question) -> QuestionOut:
    db.refresh(q)
    return _out(db, [q])[0]


def _pool_out(db: Session, module: Module) -> PoolOut:
    s = questions.pool_status(db, module)
    return PoolOut(
        question_count=module.test_question_count,
        required=s.required,
        approved_active=s.approved_active,
        by_difficulty=s.by_difficulty,
        drafts=s.drafts,
        publishable=s.publishable,
        test_published=s.published,
    )


@router.get("/modules/{module_id}/questions", response_model=list[QuestionOut])
def list_questions(
    module_id: int,
    status: QuestionStatus | None = None,
    lesson_id: int | None = None,
    origin: QuestionOrigin | None = None,
    flagged: bool | None = None,
    db: Session = Depends(get_db),
    _: AppUser = Depends(editor),
):
    _module(db, module_id)
    stmt = (
        select(Question)
        .options(selectinload(Question.options))
        .join(LessonVersion, LessonVersion.id == Question.lesson_version_id)
        .where(Question.module_id == module_id)
        .order_by(Question.seq)
    )
    if status is not None:
        stmt = stmt.where(Question.status == status)
    if lesson_id is not None:
        stmt = stmt.where(LessonVersion.lesson_id == lesson_id)
    if origin is not None:
        stmt = stmt.where(Question.origin == origin)
    rows = list(db.scalars(stmt))
    if flagged is not None:
        rows = [q for q in rows if questions.is_flagged(q) == flagged]
    return _out(db, rows)


@router.get("/modules/{module_id}/pool", response_model=PoolOut)
def pool(module_id: int, db: Session = Depends(get_db), _: AppUser = Depends(editor)):
    return _pool_out(db, _module(db, module_id))


@router.post("/modules/{module_id}/questions", response_model=QuestionOut, status_code=201)
def create_question(
    module_id: int,
    body: QuestionIn,
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
):
    module = _module(db, module_id)
    lesson = db.get(Lesson, body.lesson_id)
    if lesson is None:
        raise not_found("lesson")
    q = questions.create_draft(
        db,
        module=module,
        lesson=lesson,
        q_type=body.type,
        text_uz=body.text_uz,
        text_ru=body.text_ru,
        explanation_uz=body.explanation_uz,
        explanation_ru=body.explanation_ru,
        difficulty=body.difficulty,
        video_ts_s=body.video_ts_s,
        options=[questions.OptionData(o.text_uz, o.text_ru, o.is_correct) for o in body.options],
        actor_id=actor.id,
    )
    audit.record(db, "question.created", actor_id=actor.id, entity="question", entity_id=q.id)
    db.commit()
    return _one(db, q)


@router.get("/questions/{question_id}", response_model=QuestionOut)
def get_question(question_id: int, db: Session = Depends(get_db), _: AppUser = Depends(editor)):
    return _out(db, [_question(db, question_id)])[0]


@router.patch("/questions/{question_id}", response_model=QuestionOut)
def patch_question(
    question_id: int,
    body: QuestionPatch,
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
):
    q = _question(db, question_id)
    changes = body.model_dump(exclude_none=True, exclude={"options"})
    options = None
    if body.options is not None:
        options = [
            (o.id, questions.OptionData(o.text_uz, o.text_ru, o.is_correct)) for o in body.options
        ]
    questions.update(db, q, changes, options, actor.id)
    db.commit()
    return _one(db, q)


@router.put("/questions/{question_id}/image", response_model=QuestionOut)
def upload_image(
    question_id: int,
    data: bytes = Depends(read_image),
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
):
    """Screenshot for a screenshot question (PNG/JPEG). The image is part of the answer key."""
    q = _question(db, question_id)
    if q.status != QuestionStatus.draft:
        raise AppError(409, "question.answer_key_locked")
    if q.type != QuestionType.screenshot:
        raise AppError(400, "question.not_screenshot")
    suffix = next((ext for magic, ext in _IMAGE_TYPES if data.startswith(magic)), None)
    if suffix is None:
        raise AppError(400, "image.invalid")
    old = q.image_path
    q.image_path = media.write_new("img", f"q{q.id}", suffix, data)
    db.flush()
    content.drop_unreferenced_images(db, [old])
    audit.record(
        db, "question.image_uploaded", actor_id=actor.id, entity="question", entity_id=q.id
    )
    db.commit()
    return _one(db, q)


def _workflow(question_id: int, action, actor: AppUser, db: Session) -> QuestionOut:
    q = _question(db, question_id)
    action(db, q, actor.id)
    db.commit()
    return _one(db, q)


@router.post("/questions/{question_id}/approve", response_model=QuestionOut)
def approve(question_id: int, actor: AppUser = Depends(editor), db: Session = Depends(get_db)):
    return _workflow(question_id, questions.approve, actor, db)


@router.post("/questions/{question_id}/reject", response_model=QuestionOut)
def reject(question_id: int, actor: AppUser = Depends(editor), db: Session = Depends(get_db)):
    return _workflow(question_id, questions.reject, actor, db)


@router.post("/questions/{question_id}/retire", response_model=QuestionOut)
def retire(question_id: int, actor: AppUser = Depends(editor), db: Session = Depends(get_db)):
    return _workflow(question_id, questions.retire, actor, db)


@router.post("/questions/{question_id}/duplicate", response_model=QuestionOut, status_code=201)
def duplicate(question_id: int, actor: AppUser = Depends(editor), db: Session = Depends(get_db)):
    copy = questions.duplicate(db, _question(db, question_id), actor.id)
    db.commit()
    return _one(db, copy)


@router.post("/modules/{module_id}/test/publish", response_model=PoolOut)
def publish_test(module_id: int, actor: AppUser = Depends(editor), db: Session = Depends(get_db)):
    module = _module(db, module_id)
    questions.publish_test(db, module, actor.id)
    db.commit()
    return _pool_out(db, module)


@router.post("/modules/{module_id}/test/unpublish", response_model=PoolOut)
def unpublish_test(
    module_id: int, actor: AppUser = Depends(editor), db: Session = Depends(get_db)
):
    module = _module(db, module_id)
    questions.unpublish_test(db, module, actor.id)
    db.commit()
    return _pool_out(db, module)

