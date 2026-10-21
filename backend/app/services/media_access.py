"""Authorize the exact media object, using the same assignments as lesson APIs."""

from __future__ import annotations

import uuid
from urllib.parse import unquote, urlsplit

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import AppUser, AttemptQuestion, Lesson, LessonVersion, Module, Question, TestAttempt
from app.models.enums import AccessRole, AttemptStatus, LessonVersionStatus, ModuleType
from app.services import access


def allowed(db: Session, user: AppUser, uri: str) -> bool:
    path = unquote(urlsplit(uri).path)
    if not path.startswith("/media/"):
        return False
    rel = path[len("/media/"):]
    parts = rel.split("/")
    if len(parts) < 2 or any(p in {"", ".", ".."} for p in parts) or "\\" in rel or "\x00" in rel:
        return False
    folder = parts[0]
    staff = user.access_role in {AccessRole.admin, AccessRole.methodologist}
    if folder == "img":
        stmt = select(Question.id).where(Question.image_path == rel)
        if not staff:
            # Images belong to a question actually served in this user's open test.
            stmt = (stmt.join(AttemptQuestion, AttemptQuestion.question_id == Question.id)
                    .join(TestAttempt, TestAttempt.id == AttemptQuestion.attempt_id)
                    .where(TestAttempt.user_id == user.id, TestAttempt.status == AttemptStatus.in_progress))
        return db.scalar(stmt.limit(1)) is not None
    stmt = select(Module).join(Lesson, Lesson.module_id == Module.id).join(
        LessonVersion, LessonVersion.lesson_id == Lesson.id)
    if folder == "hls":
        if len(parts) < 3:
            return False
        try:
            asset_id = uuid.UUID(parts[1])
        except ValueError:
            return False
        stmt = stmt.where(LessonVersion.video_asset_id == asset_id)
    elif folder in {"vtt", "pdf"}:
        columns = (getattr(LessonVersion, f"{folder}_{lang}_path") for lang in ("uz", "ru"))
        stmt = stmt.where(or_(*(column == rel for column in columns)))
    else:
        return False
    if staff:
        return db.scalar(stmt.limit(1)) is not None
    assigned = access.assigned_modules(db, user)
    stmt = stmt.where(LessonVersion.status == LessonVersionStatus.published)
    stmt = stmt.where(or_(Module.type == ModuleType.faq, Module.id.in_([m.id for m in assigned])))
    modules = db.scalars(stmt).all()
    if not modules:
        return False
    core_certified = access.holds_core_certificate(db, user.id)
    return any(not access.is_locked(module, core_certified) for module in modules)
