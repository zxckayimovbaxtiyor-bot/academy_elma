"""Question bank: structure rules, the draft → approved → retired workflow, the test pool.

* A question is written against one lesson version (the open draft version of
  its lesson if there is one, otherwise the live one); its elma_release is that
  version's release.
* The test pool holds the approved questions linked to a live (published) version.
* Once approved, wording can be fixed but the answer key and option set can't
  change: retire the question and duplicate it instead, so item statistics keep
  describing the same question.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import clock
from app.errors import AppError
from app.models import Lesson, LessonVersion, Module, Question, QuestionOption
from app.models.enums import (
    LessonVersionStatus,
    ModuleType,
    QuestionOrigin,
    QuestionStatus,
    QuestionType,
    RetiredReason,
)
from app.services import audit, content

MIN_OPTIONS, MAX_OPTIONS = 2, 8
POOL_FACTOR = 3  # a test needs at least 3 x N approved questions
FLAG_MIN_ATTEMPTS = 30
FLAG_LOW_PCT, FLAG_HIGH_PCT = 20.0, 95.0


@dataclass(frozen=True)
class OptionData:
    text_uz: str
    text_ru: str
    is_correct: bool = False


@dataclass(frozen=True)
class PoolStatus:
    required: int
    approved_active: int
    by_difficulty: dict[int, int]
    drafts: int
    published: bool

    @property
    def publishable(self) -> bool:
        return self.approved_active >= self.required


def number(module: Module, question: Question) -> str:
    return f"{module.qprefix}-{question.seq:03d}"


def correct_pct(q: Question) -> float | None:
    return round(q.stat_correct / q.stat_attempts * 100, 1) if q.stat_attempts else None


def is_flagged(q: Question) -> bool:
    """Too hard or too easy to say anything about the learner: worth a methodologist's look."""
    pct = correct_pct(q)
    return (
        q.stat_attempts >= FLAG_MIN_ATTEMPTS
        and pct is not None
        and (pct < FLAG_LOW_PCT or pct > FLAG_HIGH_PCT)
    )


def structure_problems(q_type: QuestionType, options: list[OptionData]) -> list[str]:
    problems = []
    if not MIN_OPTIONS <= len(options) <= MAX_OPTIONS:
        problems.append("options_count")
    correct = sum(1 for o in options if o.is_correct)
    if q_type in (QuestionType.single, QuestionType.screenshot) and correct != 1:
        problems.append("needs_exactly_one_correct")
    if q_type == QuestionType.multiple and (correct < 2 or correct == len(options)):
        problems.append("needs_two_correct_and_one_wrong")
    return problems


def approval_problems(q: Question) -> list[str]:
    options = [OptionData(o.text_uz, o.text_ru, o.is_correct) for o in q.options]
    problems = structure_problems(q.type, options)
    if not (q.text_uz.strip() and q.text_ru.strip()):
        problems.append("text_missing")
    if not all(o.text_uz.strip() and o.text_ru.strip() for o in options):
        problems.append("option_text_missing")
    if not q.explanation_uz.strip():
        problems.append("explanation_uz_missing")
    if not q.explanation_ru.strip():
        problems.append("explanation_ru_missing")
    if q.type == QuestionType.screenshot and not q.image_path:
        problems.append("image_missing")
    return problems


def target_version(db: Session, lesson: Lesson) -> LessonVersion:
    """New questions follow the lesson's open draft version (the new video), else the live one."""
    draft = content.versions_by_lesson(db, [lesson.id], LessonVersionStatus.draft).get(lesson.id)
    version = draft or content.published_version(db, lesson.id)
    if version is None:
        raise AppError(409, "lesson.no_version")
    return version


def _next_seq(db: Session, module_id: int) -> int:
    db.scalar(select(Module.id).where(Module.id == module_id).with_for_update())  # serialise
    last = db.scalar(select(func.max(Question.seq)).where(Question.module_id == module_id))
    return (last or 0) + 1


def _check_timestamp(version: LessonVersion, ts: int) -> None:
    duration = content.duration_of(version)
    if duration is not None and ts > duration:
        raise AppError(400, "question.timestamp_after_video", {"duration": duration})


def create_draft(
    db: Session,
    *,
    module: Module,
    lesson: Lesson,
    q_type: QuestionType,
    text_uz: str,
    text_ru: str,
    explanation_uz: str,
    explanation_ru: str,
    difficulty: int,
    video_ts_s: int,
    options: list[OptionData],
    actor_id: int | None,
    origin: QuestionOrigin = QuestionOrigin.manual,
    extra: dict[str, Any] | None = None,
    version: LessonVersion | None = None,
) -> Question:
    if module.type == ModuleType.faq:
        raise AppError(400, "module.no_test")
    if lesson.module_id != module.id:
        raise AppError(400, "question.lesson_not_in_module")
    problems = structure_problems(q_type, options)
    if problems:
        raise AppError(400, "question.invalid", {"problems": problems})
    version = version or target_version(db, lesson)
    _check_timestamp(version, video_ts_s)
    q = Question(
        module_id=module.id,
        seq=_next_seq(db, module.id),
        lesson_version_id=version.id,
        video_ts_s=video_ts_s,
        type=q_type,
        text_uz=text_uz,
        text_ru=text_ru,
        explanation_uz=explanation_uz,
        explanation_ru=explanation_ru,
        difficulty=difficulty,
        origin=origin,
        created_by=actor_id,
        **(extra or {}),
    )
    q.options = [
        QuestionOption(sort=i, text_uz=o.text_uz, text_ru=o.text_ru, is_correct=o.is_correct)
        for i, o in enumerate(options, start=1)
    ]
    db.add(q)
    db.flush()
    return q


def update(
    db: Session,
    q: Question,
    changes: dict[str, Any],
    options: list[tuple[int | None, OptionData]] | None,
    actor_id: int,
) -> None:
    """Drafts: anything. Approved: wording, explanation, timestamp and difficulty only."""
    if q.status == QuestionStatus.retired:
        raise AppError(409, "question.retired")
    approved = q.status == QuestionStatus.approved
    if approved and ({"type", "lesson_id"} & changes.keys()):
        raise AppError(409, "question.answer_key_locked")
    if "lesson_id" in changes:
        lesson = db.get(Lesson, changes.pop("lesson_id"))
        if lesson is None or lesson.module_id != q.module_id:
            raise AppError(400, "question.lesson_not_in_module")
        q.lesson_version_id = target_version(db, lesson).id
    for attr, value in changes.items():
        setattr(q, attr, value)
    if options is not None:
        if approved:
            current = {o.id: o for o in q.options}
            if {oid for oid, _ in options} != set(current) or any(
                current[oid].is_correct != data.is_correct for oid, data in options
            ):
                raise AppError(409, "question.answer_key_locked")
            for oid, data in options:
                current[oid].text_uz, current[oid].text_ru = data.text_uz, data.text_ru
        else:
            q.options = [
                QuestionOption(
                    sort=i, text_uz=d.text_uz, text_ru=d.text_ru, is_correct=d.is_correct
                )
                for i, (_, d) in enumerate(options, start=1)
            ]
    data = [OptionData(o.text_uz, o.text_ru, o.is_correct) for o in q.options]
    problems = structure_problems(q.type, data)
    if problems:
        raise AppError(400, "question.invalid", {"problems": problems})
    version = db.get(LessonVersion, q.lesson_version_id)
    _check_timestamp(version, q.video_ts_s)
    db.flush()
    audit.record(
        db, "question.updated", actor_id=actor_id, entity="question", entity_id=q.id,
        data={"fields": sorted(changes) + (["options"] if options is not None else [])},
    )  # fmt: skip


def approve(db: Session, q: Question, actor_id: int) -> None:
    if q.status != QuestionStatus.draft:
        raise AppError(409, "question.not_draft")
    version = db.get(LessonVersion, q.lesson_version_id)
    if version.status == LessonVersionStatus.superseded:
        raise AppError(409, "question.lesson_version_retired")
    problems = approval_problems(q)
    if problems:
        raise AppError(400, "question.incomplete", {"problems": problems})
    q.status = QuestionStatus.approved
    q.approved_by, q.approved_at = actor_id, clock.utcnow()
    db.flush()  # sessions don't autoflush: pool counts later in this transaction must see it
    audit.record(db, "question.approved", actor_id=actor_id, entity="question", entity_id=q.id)


def reject(db: Session, q: Question, actor_id: int) -> None:
    if q.status != QuestionStatus.draft:
        raise AppError(409, "question.not_draft")
    _retire(db, q, RetiredReason.rejected, actor_id)
    audit.record(db, "question.rejected", actor_id=actor_id, entity="question", entity_id=q.id)


def retire(db: Session, q: Question, actor_id: int) -> None:
    if q.status != QuestionStatus.approved:
        raise AppError(409, "question.not_approved")
    _retire(db, q, RetiredReason.manual, actor_id)
    audit.record(db, "question.retired", actor_id=actor_id, entity="question", entity_id=q.id)


def _retire(db: Session, q: Question, reason: RetiredReason, actor_id: int | None) -> None:
    q.status = QuestionStatus.retired
    q.retired_reason = reason
    q.retired_by, q.retired_at = actor_id, clock.utcnow()
    db.flush()


def duplicate(db: Session, q: Question, actor_id: int) -> Question:
    """A fresh draft copy (new number, zero statistics), aimed at the lesson's current target."""
    module = db.get(Module, q.module_id)
    lesson = db.get(Lesson, db.get(LessonVersion, q.lesson_version_id).lesson_id)
    copy = create_draft(
        db,
        module=module,
        lesson=lesson,
        q_type=q.type,
        text_uz=q.text_uz,
        text_ru=q.text_ru,
        explanation_uz=q.explanation_uz,
        explanation_ru=q.explanation_ru,
        difficulty=q.difficulty,
        video_ts_s=q.video_ts_s,
        options=[OptionData(o.text_uz, o.text_ru, o.is_correct) for o in q.options],
        actor_id=actor_id,
    )
    copy.image_path = q.image_path  # image files are immutable, so sharing is safe
    audit.record(
        db, "question.duplicated", actor_id=actor_id, entity="question", entity_id=copy.id,
        data={"from": q.id},
    )  # fmt: skip
    return copy


def pool_query(module_id: int):
    """Approved questions on live lesson versions: what a test can be drawn from."""
    return (
        select(Question)
        .join(LessonVersion, LessonVersion.id == Question.lesson_version_id)
        .where(
            Question.module_id == module_id,
            Question.status == QuestionStatus.approved,
            LessonVersion.status == LessonVersionStatus.published,
        )
    )


def pool(db: Session, module_id: int) -> list[Question]:
    return list(db.scalars(pool_query(module_id).options(selectinload(Question.options))))


def pool_status(db: Session, module: Module, question_count: int | None = None) -> PoolStatus:
    n = question_count or module.test_question_count
    counts = Counter(q.difficulty for q in db.scalars(pool_query(module.id)))
    drafts = db.scalar(
        select(func.count())
        .select_from(Question)
        .where(Question.module_id == module.id, Question.status == QuestionStatus.draft)
    )
    return PoolStatus(
        required=POOL_FACTOR * n,
        approved_active=sum(counts.values()),
        by_difficulty={d: counts.get(d, 0) for d in (1, 2, 3)},
        drafts=drafts or 0,
        published=module.test_published_at is not None,
    )


def pool_after_release(db: Session, module_id: int, release_id: int, changed: list[int]) -> int:
    """Approved questions that will be live once the draft release is published."""
    return db.scalar(
        select(func.count())
        .select_from(Question)
        .join(LessonVersion, LessonVersion.id == Question.lesson_version_id)
        .where(
            Question.module_id == module_id,
            Question.status == QuestionStatus.approved,
            or_(
                (LessonVersion.status == LessonVersionStatus.published)
                & LessonVersion.lesson_id.not_in(changed or [0]),
                (LessonVersion.release_id == release_id)
                & (LessonVersion.status == LessonVersionStatus.draft),
            ),
        )
    ) or 0


def publish_test(db: Session, module: Module, actor_id: int) -> None:
    if module.type == ModuleType.faq:
        raise AppError(400, "module.no_test")
    status = pool_status(db, module)
    if not status.publishable:
        raise AppError(
            409, "test.pool_too_small", {"have": status.approved_active, "need": status.required}
        )
    module.test_published_at = clock.utcnow()
    audit.record(db, "test.published", actor_id=actor_id, entity="module", entity_id=module.id)


def unpublish_test(db: Session, module: Module, actor_id: int) -> None:
    module.test_published_at = None
    audit.record(db, "test.unpublished", actor_id=actor_id, entity="module", entity_id=module.id)


def retire_for_superseded_versions(db: Session, version_ids: list[int]) -> int:
    """Release publish: questions about a replaced video describe the old screens."""
    rows = list(
        db.scalars(
            select(Question).where(
                Question.lesson_version_id.in_(version_ids or [0]),
                Question.status.in_([QuestionStatus.draft, QuestionStatus.approved]),
            )
        )
    )
    for q in rows:
        _retire(db, q, RetiredReason.lesson_changed, None)
    return len(rows)
