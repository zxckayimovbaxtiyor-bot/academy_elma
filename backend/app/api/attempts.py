"""Learner side of tests: start, autosave answers, submit, result.

Nothing sent to a learner contains the answer key or the explanations, during
the attempt or after it (rule 7). The server's clock owns the deadline.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app import clock
from app.auth.deps import current_user
from app.db import get_db
from app.errors import AppError, not_found
from app.models import AppUser, AttemptQuestion, Lesson, Module, Question, TestAttempt
from app.models.enums import AttemptStatus
from app.schemas.learner import (
    AnswerIn,
    AnswerOut,
    AttemptOption,
    AttemptOut,
    AttemptQuestionOut,
    AttemptStarted,
    HistoryRow,
    RemediationOut,
    ResultOut,
)
from app.services import access, attempts, media, remediation

router = APIRouter(prefix="/me", tags=["learner: tests"])


def _assigned_module(db: Session, user: AppUser, module_id: int) -> Module:
    module = db.get(Module, module_id)
    if module is None or module.id not in {m.id for m in access.assigned_modules(db, user)}:
        raise not_found("module")  # FAQ is never assigned: it has no test
    return module


def _attempt_out(db: Session, user: AppUser, attempt: TestAttempt) -> AttemptOut:
    module = db.get(Module, attempt.module_id)
    items: list[AttemptQuestionOut] = []
    if attempt.status == AttemptStatus.in_progress:
        rows = db.execute(
            select(AttemptQuestion, Question)
            .join(Question, Question.id == AttemptQuestion.question_id)
            .options(selectinload(Question.options))
            .where(AttemptQuestion.attempt_id == attempt.id)
            .order_by(AttemptQuestion.position)
        ).all()
        for aq, q in rows:
            by_id = {o.id: o for o in q.options}
            shown = [by_id[oid] for oid in aq.option_order]
            index = {oid: i for i, oid in enumerate(aq.option_order)}
            items.append(
                AttemptQuestionOut(
                    position=aq.position,
                    type=q.type,
                    text_uz=q.text_uz,
                    text_ru=q.text_ru,
                    image_url=media.url(q.image_path),
                    options=[
                        AttemptOption(index=i, text_uz=o.text_uz, text_ru=o.text_ru)
                        for i, o in enumerate(shown)
                    ],
                    answer=[index[oid] for oid in aq.answer] if aq.answer else None,
                    flagged=aq.flagged,
                )
            )
    return AttemptOut(
        id=attempt.id,
        module_id=module.id,
        module_title_uz=module.title_uz,
        module_title_ru=module.title_ru,
        status=attempt.status,
        number=attempts.numbers(db, user.id, module.id)[attempt.id],
        max_attempts=module.test_max_attempts,
        question_count=attempt.question_count,
        pass_pct=attempt.pass_pct,
        started_at=attempt.started_at,
        expires_at=attempt.expires_at,
        server_now=clock.utcnow(),
        answered=attempts.answered_count(db, attempt.id),
        questions=items,
    )


def _result_out(db: Session, user: AppUser, attempt: TestAttempt) -> ResultOut:
    module = db.get(Module, attempt.module_id)
    elig = attempts.eligibility(db, user, module, clock.utcnow())
    numbered = attempts.numbered(db, user.id, module.id)
    cycle, number = next((c, n) for a, c, n in numbered if a.id == attempt.id)
    items = remediation.items_for(db, attempt.id)
    lessons = {
        lesson.id: lesson
        for lesson in db.scalars(select(Lesson).where(Lesson.id.in_({i.lesson_id for i in items})))
    }
    attempts_left = max(0, elig.attempts_max - elig.attempts_used)
    done = any(r.code == "already_passed" for r in elig.reasons)
    return ResultOut(
        attempt_id=attempt.id,
        module_id=module.id,
        status=attempt.status,
        number=number,
        score_pct=attempt.score_pct,
        correct_count=attempt.correct_count,
        question_count=attempt.question_count,
        pass_pct=attempt.pass_pct,
        passed=attempt.passed,
        time_spent_s=attempts.time_spent_s(attempt),
        attempts_used=elig.attempts_used,
        attempts_max=elig.attempts_max,
        attempts_left=attempts_left,
        next_attempt_at=elig.cooldown_until if attempts_left and not done else None,
        remediation=[
            RemediationOut(
                lesson_id=i.lesson_id,
                lesson_title_uz=lessons[i.lesson_id].title_uz,
                lesson_title_ru=lessons[i.lesson_id].title_ru,
                missed_count=i.missed_count,
                span_start_s=i.span_start_s,
                span_end_s=i.span_end_s,
                watched_pct=int(remediation.watched_ratio(i) * 100),
                satisfied=i.satisfied_at is not None,
            )
            for i in items
        ],
        remediation_complete=all(i.satisfied_at is not None for i in items),
        history=[
            HistoryRow(
                attempt_id=a.id,
                number=n,
                status=a.status,
                started_at=a.started_at,
                score_pct=a.score_pct,
                passed=a.passed,
                time_spent_s=attempts.time_spent_s(a),
            )
            for a, c, n in numbered
            if c == cycle
        ],
    )


@router.post("/modules/{module_id}/attempts", response_model=AttemptStarted)
def start_attempt(
    module_id: int,
    response: Response,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    """201 with a new attempt, or 200 with the one already in progress."""
    module = _assigned_module(db, user, module_id)
    now = clock.utcnow()
    if attempts.expire_overdue_for(db, user.id, module.id, now):
        db.commit()
    try:
        attempt, created = attempts.start(db, user, module, now)
        db.commit()
    except IntegrityError:  # a second click won the one-open-attempt index: resume that one
        db.rollback()
        attempt, created = attempts.start(db, user, module, now)
    response.status_code = 201 if created else 200
    return AttemptStarted(attempt_id=attempt.id, created=created)


@router.get("/attempts/{attempt_id}", response_model=AttemptOut)
def get_attempt(
    attempt_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
):
    attempt = attempts.owned(db, user, attempt_id)
    if attempts.expire_if_overdue(db, attempt, clock.utcnow()):
        db.commit()
    return _attempt_out(db, user, attempt)


@router.put("/attempts/{attempt_id}/answers/{position}", response_model=AnswerOut)
def save_answer(
    attempt_id: int,
    position: int,
    body: AnswerIn,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    attempt = attempts.owned(db, user, attempt_id, lock=True)
    aq = attempts.save_answer(
        db,
        attempt,
        position,
        answer_given="answer" in body.model_fields_set,
        answer=body.answer,
        flagged=body.flagged,
        now=clock.utcnow(),
    )
    db.commit()
    if aq is None:  # past the deadline: graded with what was saved before
        raise AppError(409, "attempt.expired", {"attempt_id": attempt.id})
    return AnswerOut(position=aq.position, answered=aq.answer is not None, flagged=aq.flagged)


@router.post("/attempts/{attempt_id}/submit", response_model=ResultOut)
def submit_attempt(
    attempt_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
):
    attempt = attempts.owned(db, user, attempt_id, lock=True)
    attempt = attempts.submit(db, attempt, clock.utcnow())  # a second submit just reads
    db.commit()
    return _result_out(db, user, attempt)


@router.get("/attempts/{attempt_id}/result", response_model=ResultOut)
def attempt_result(
    attempt_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
):
    attempt = attempts.owned(db, user, attempt_id)
    if attempts.expire_if_overdue(db, attempt, clock.utcnow()):
        db.commit()
    if attempt.status == AttemptStatus.in_progress:
        raise AppError(409, "attempt.in_progress")
    return _result_out(db, user, attempt)
