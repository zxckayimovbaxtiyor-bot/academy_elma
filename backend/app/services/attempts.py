"""Test attempts (rules 4, 6, 7): who may start, the timer, answers, grading.

Attempts are counted per cycle. A cycle starts at the learner's latest certificate
for the module or the latest admin reset, whichever is later; earlier attempts
don't count. Within a cycle there is a maximum number of attempts. After a failed
attempt, the next one needs both the cooldown to have passed and every
remediation fragment watched. The server owns the clock: answers are accepted
until 30 s after the deadline (network latency), then the attempt is graded with
what was saved.
"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.errors import AppError, not_found
from app.models import (
    AppUser,
    AttemptQuestion,
    AttemptReset,
    Certificate,
    Lesson,
    LessonProgress,
    LessonVersion,
    Module,
    Question,
    TestAttempt,
)
from app.models.enums import (
    AttemptStatus,
    LessonVersionStatus,
    ModuleType,
    QuestionType,
)
from app.services import access, assembly, audit, certificates, grading, questions, remediation

GRACE_S = 30


@dataclass(frozen=True)
class Reason:
    code: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Eligibility:
    reasons: list[Reason]
    attempts_used: int
    attempts_max: int
    cooldown_until: datetime | None
    open_attempt_id: int | None
    last_attempt: TestAttempt | None

    @property
    def can_start(self) -> bool:
        return not self.reasons


# --- cycles -------------------------------------------------------------------------------


def cycle_starts(db: Session, user_id: int, module_id: int) -> list[datetime]:
    certs = db.scalars(
        select(Certificate.issued_at).where(
            Certificate.user_id == user_id, Certificate.module_id == module_id
        )
    )
    resets = db.scalars(
        select(AttemptReset.created_at).where(
            AttemptReset.user_id == user_id, AttemptReset.module_id == module_id
        )
    )
    return sorted([*certs, *resets])


def all_attempts(db: Session, user_id: int, module_id: int) -> list[TestAttempt]:
    return list(
        db.scalars(
            select(TestAttempt)
            .where(TestAttempt.user_id == user_id, TestAttempt.module_id == module_id)
            .order_by(TestAttempt.started_at, TestAttempt.id)
        )
    )


def cycle_attempts(db: Session, user_id: int, module_id: int) -> list[TestAttempt]:
    starts = cycle_starts(db, user_id, module_id)
    current = starts[-1] if starts else None
    return [
        a for a in all_attempts(db, user_id, module_id) if current is None or a.started_at > current
    ]


def numbered(db: Session, user_id: int, module_id: int) -> list[tuple[TestAttempt, int, int]]:
    """(attempt, cycle index, number within that cycle) for every attempt, oldest first."""
    starts = cycle_starts(db, user_id, module_id)
    out = []
    counts: dict[int, int] = defaultdict(int)
    for a in all_attempts(db, user_id, module_id):
        cycle = sum(1 for s in starts if a.started_at > s)
        counts[cycle] += 1
        out.append((a, cycle, counts[cycle]))
    return out


def numbers(db: Session, user_id: int, module_id: int) -> dict[int, int]:
    """Attempt number within its own cycle (attempt id → 1, 2, 3 ...)."""
    return {a.id: n for a, _, n in numbered(db, user_id, module_id)}


def latest_failed(attempts: list[TestAttempt]) -> TestAttempt | None:
    done = [a for a in attempts if a.status != AttemptStatus.in_progress and a.passed is False]
    return done[-1] if done else None


def open_remediation_attempt(db: Session, user_id: int, module_id: int) -> TestAttempt | None:
    """The failed attempt whose fragments stand between the learner and the next attempt."""
    attempts = cycle_attempts(db, user_id, module_id)
    if any(a.passed for a in attempts):
        return None
    return latest_failed(attempts)


def holds_current_certificate(db: Session, user_id: int, module_id: int) -> bool:
    """A certificate with no recertification pending: nothing left to prove."""
    return bool(
        db.scalar(
            select(Certificate.id).where(
                Certificate.user_id == user_id,
                Certificate.module_id == module_id,
                Certificate.superseded_at.is_(None),
                Certificate.recert_due_at.is_(None),
            )
        )
    )


def lesson_counts(db: Session, user_id: int, module_id: int) -> tuple[int, int]:
    """(completed, total) over the module's live lesson versions."""
    rows = db.execute(
        select(LessonVersion.id, LessonProgress.completed_at)
        .join(Lesson, Lesson.id == LessonVersion.lesson_id)
        .outerjoin(
            LessonProgress,
            and_(
                LessonProgress.lesson_version_id == LessonVersion.id,
                LessonProgress.user_id == user_id,
            ),
        )
        .where(Lesson.module_id == module_id, LessonVersion.status == LessonVersionStatus.published)
    ).all()
    return sum(1 for _, done in rows if done is not None), len(rows)


# --- expiry ----------------------------------------------------------------------------------


def deadline_passed(attempt: TestAttempt, now: datetime) -> bool:
    return now > attempt.expires_at + timedelta(seconds=GRACE_S)


def expire_if_overdue(db: Session, attempt: TestAttempt, now: datetime) -> bool:
    if attempt.status == AttemptStatus.in_progress and deadline_passed(attempt, now):
        finalize(db, attempt, now, expired=True)
        return True
    return False


def expire_overdue_for(db: Session, user_id: int, module_id: int, now: datetime) -> int:
    return sum(expire_if_overdue(db, a, now) for a in all_attempts(db, user_id, module_id))


def finalize_overdue(db: Session, now: datetime) -> int:
    """Worker sweep: grade abandoned attempts so cooldown and remediation start."""
    cutoff = now - timedelta(seconds=GRACE_S)
    ids = list(
        db.scalars(
            select(TestAttempt.id).where(
                TestAttempt.status == AttemptStatus.in_progress, TestAttempt.expires_at < cutoff
            )
        )
    )
    for attempt_id in ids:
        finalize(db, db.get(TestAttempt, attempt_id), now, expired=True)
        db.commit()
    return len(ids)


# --- eligibility -------------------------------------------------------------------------------


def eligibility(db: Session, user: AppUser, module: Module, now: datetime) -> Eligibility:
    """Every reason the learner can't start now (all of them, so the UI can list them)."""
    reasons: list[Reason] = []
    if module.type == ModuleType.faq:
        reasons.append(Reason("module.no_test"))
    if module.type == ModuleType.product and not access.holds_core_certificate(db, user.id):
        reasons.append(Reason("prerequisite_core"))
    done, total = lesson_counts(db, user.id, module.id)
    if total == 0 or done < total:
        reasons.append(Reason("lessons_incomplete", {"completed": done, "total": total}))
    if module.test_published_at is None:
        reasons.append(Reason("test_not_published"))

    attempts = cycle_attempts(db, user.id, module.id)
    open_attempt = next((a for a in attempts if a.status == AttemptStatus.in_progress), None)
    if open_attempt is not None:
        reasons.append(Reason("attempt_in_progress", {"attempt_id": open_attempt.id}))
    cooldown_until = None
    # A pass ends the cycle; once Phase 4 issues the certificate a new cycle starts, and
    # only a pending recertification opens the test again.
    if any(a.passed for a in attempts) or holds_current_certificate(db, user.id, module.id):
        reasons.append(Reason("already_passed"))
    else:
        if len(attempts) >= module.test_max_attempts:
            reasons.append(Reason("attempts_exhausted", {"max": module.test_max_attempts}))
        failed = latest_failed(attempts)
        if failed is not None:
            until = failed.submitted_at + timedelta(hours=module.test_cooldown_hours)
            if now < until:
                cooldown_until = until
                reasons.append(Reason("cooldown", {"until": until.isoformat()}))
            items = remediation.items_for(db, failed.id)
            pending = [i for i in items if i.satisfied_at is None]
            if pending:
                reasons.append(
                    Reason(
                        "remediation_pending",
                        {"satisfied": len(items) - len(pending), "total": len(items)},
                    )
                )
    return Eligibility(
        reasons=reasons,
        attempts_used=len(attempts),
        attempts_max=module.test_max_attempts,
        cooldown_until=cooldown_until,
        open_attempt_id=open_attempt.id if open_attempt else None,
        last_attempt=attempts[-1] if attempts else None,
    )


# --- start, answer, finish ----------------------------------------------------------------------


def start(
    db: Session, user: AppUser, module: Module, now: datetime, rng: random.Random | None = None
) -> tuple[TestAttempt, bool]:
    """(attempt, created). An attempt already in progress is resumed, not duplicated."""
    elig = eligibility(db, user, module, now)
    if elig.open_attempt_id is not None:
        return db.get(TestAttempt, elig.open_attempt_id), False
    if elig.reasons:
        raise AppError(
            409,
            "test.not_available",
            {"reasons": [{"code": r.code, "params": r.params} for r in elig.reasons]},
        )
    rng = rng or random.SystemRandom()
    pool = questions.pool(db, module.id)
    by_difficulty: dict[int, list[int]] = defaultdict(list)
    for q in pool:
        by_difficulty[q.difficulty].append(q.id)
    chosen = assembly.draw(by_difficulty, module.test_question_count, rng)
    by_id = {q.id: q for q in pool}
    attempt = TestAttempt(
        user_id=user.id,
        module_id=module.id,
        release_id=module.current_release_id,
        status=AttemptStatus.in_progress,
        started_at=now,
        expires_at=now + timedelta(minutes=module.test_time_limit_min),
        question_count=module.test_question_count,
        pass_pct=module.test_pass_pct,
    )
    db.add(attempt)
    db.flush()  # the one-open-attempt unique index guards against a double start here
    for position, question_id in enumerate(chosen, start=1):
        q = by_id[question_id]
        db.add(
            AttemptQuestion(
                attempt_id=attempt.id,
                position=position,
                question_id=q.id,
                option_order=assembly.option_order(q.type, [o.id for o in q.options], rng),
            )
        )
    db.flush()
    return attempt, True


def owned(db: Session, user: AppUser, attempt_id: int, lock: bool = False) -> TestAttempt:
    stmt = select(TestAttempt).where(TestAttempt.id == attempt_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    attempt = db.scalar(stmt)
    if attempt is None or attempt.user_id != user.id:
        raise not_found("attempt")
    return attempt


def validate_answer(q: Question, answer: list[int]) -> list[int]:
    option_ids = {o.id for o in q.options}
    if len(set(answer)) != len(answer) or not set(answer) <= option_ids:
        raise AppError(400, "attempt.answer_invalid")
    if q.type in (QuestionType.single, QuestionType.screenshot) and len(answer) > 1:
        raise AppError(400, "attempt.answer_invalid")
    if q.type == QuestionType.ordering and set(answer) != option_ids:
        raise AppError(400, "attempt.answer_invalid")  # a full order is required
    return answer


def save_answer(
    db: Session,
    attempt: TestAttempt,
    position: int,
    *,
    answer_given: bool,
    answer: list[int] | None,
    flagged: bool | None,
    now: datetime,
) -> AttemptQuestion | None:
    """Autosave one answer, given as display indices; it is stored as option ids.

    Returns None when the deadline has passed (the attempt is graded instead).
    """
    if attempt.status != AttemptStatus.in_progress:
        raise AppError(409, "attempt.finished")
    if deadline_passed(attempt, now):
        finalize(db, attempt, now, expired=True)
        return None
    aq = db.get(AttemptQuestion, (attempt.id, position))
    if aq is None:
        raise not_found("attempt_question")
    if answer_given:
        if answer:
            if max(answer) >= len(aq.option_order):
                raise AppError(400, "attempt.answer_invalid")
            q = db.scalar(
                select(Question)
                .options(selectinload(Question.options))
                .where(Question.id == aq.question_id)
            )
            aq.answer = validate_answer(q, [aq.option_order[i] for i in answer])
            aq.answered_at = now
        else:
            aq.answer, aq.answered_at = None, None
    if flagged is not None:
        aq.flagged = flagged
    return aq


def submit(db: Session, attempt: TestAttempt, now: datetime) -> TestAttempt:
    if attempt.status != AttemptStatus.in_progress:
        return attempt
    return finalize(db, attempt, now, expired=deadline_passed(attempt, now))


def finalize(db: Session, attempt: TestAttempt, now: datetime, *, expired: bool) -> TestAttempt:
    """Grade with the saved answers and update item statistics.

    A pass issues the module certificate; a fail opens remediation.
    """
    attempt = db.scalar(
        select(TestAttempt)
        .where(TestAttempt.id == attempt.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if attempt.status != AttemptStatus.in_progress:
        return attempt  # graded meanwhile (submit and the sweep can race)
    rows = db.execute(
        select(AttemptQuestion, Question)
        .join(Question, Question.id == AttemptQuestion.question_id)
        .options(selectinload(Question.options))
        .where(AttemptQuestion.attempt_id == attempt.id)
        .order_by(AttemptQuestion.position)
    ).all()
    right: list[Question] = []
    missed: list[Question] = []
    for aq, q in rows:
        ok = grading.is_correct(
            q.type,
            [o.id for o in q.options],
            {o.id for o in q.options if o.is_correct},
            aq.answer,
        )
        aq.is_correct = ok
        (right if ok else missed).append(q)
    served = [q.id for _, q in rows]
    db.execute(
        update(Question)
        .where(Question.id.in_(served))
        .values(stat_attempts=Question.stat_attempts + 1)
        .execution_options(synchronize_session=False)
    )
    if right:
        db.execute(
            update(Question)
            .where(Question.id.in_([q.id for q in right]))
            .values(stat_correct=Question.stat_correct + 1)
            .execution_options(synchronize_session=False)
        )
    attempt.correct_count = len(right)
    attempt.score_pct = grading.score_pct(len(right), attempt.question_count)
    attempt.passed = grading.passed(len(right), attempt.question_count, attempt.pass_pct)
    attempt.status = AttemptStatus.expired if expired else AttemptStatus.submitted
    attempt.submitted_at = min(now, attempt.expires_at) if expired else now
    db.flush()
    if attempt.passed:
        certificates.issue_module(db, attempt, now)
    else:
        remediation.create_items(db, attempt, missed)
    db.flush()
    return attempt


def reset(
    db: Session, user: AppUser, module: Module, reason: str, actor_id: int, now: datetime
) -> AttemptReset:
    """Admin grants a fresh cycle (D4): attempts, cooldown and remediation start over."""
    for attempt in all_attempts(db, user.id, module.id):
        if attempt.status == AttemptStatus.in_progress:
            finalize(db, attempt, now, expired=True)
    row = AttemptReset(
        user_id=user.id, module_id=module.id, reset_by=actor_id, reason=reason, created_at=now
    )
    db.add(row)
    db.flush()
    audit.record(
        db, "attempts.reset", actor_id=actor_id, target_user_id=user.id, entity="module",
        entity_id=module.id, reason=reason, data={"module_id": module.id},
    )  # fmt: skip
    return row


def time_spent_s(attempt: TestAttempt) -> int | None:
    if attempt.submitted_at is None:
        return None
    end = min(attempt.submitted_at, attempt.expires_at)
    return max(0, int((end - attempt.started_at).total_seconds()))


def answered_count(db: Session, attempt_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(AttemptQuestion)
        .where(AttemptQuestion.attempt_id == attempt_id, AttemptQuestion.answer.is_not(None))
    ) or 0
