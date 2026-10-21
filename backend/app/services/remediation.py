"""After a failed attempt: re-watch the fragments the missed questions point to (rule 7, D1).

Each missed question (wrong or unanswered) points to a moment in a lesson. Per
lesson, the fragment runs from 15 s before the earliest of those moments to 75 s
after the latest. It counts as watched once 90 % of it has been played after the
failure; the heartbeats credit it the same way they credit the lesson. Learners
are never shown the correct answers.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import clock
from app.models import LessonVersion, Question, RemediationItem, TestAttempt
from app.models.enums import LessonVersionStatus, RemediationResolution
from app.services import content, watch

WINDOW_BEFORE_S = 15.0
WINDOW_AFTER_S = 75.0
SATISFIED_RATIO = 0.9


def span(timestamps: Sequence[float], duration: float) -> tuple[float, float]:
    start = max(0.0, min(timestamps) - WINDOW_BEFORE_S)
    end = min(duration, max(timestamps) + WINDOW_AFTER_S)
    if end - start < 1.0:  # a timestamp at (or past) the very end
        start = max(0.0, end - 1.0)
    return start, end


def create_items(db: Session, attempt: TestAttempt, missed: Iterable[Question]) -> None:
    by_version: dict[int, list[Question]] = defaultdict(list)
    for q in missed:
        by_version[q.lesson_version_id].append(q)
    for version_id, items in by_version.items():
        version = db.get(LessonVersion, version_id)
        timestamps = [float(q.video_ts_s) for q in items]
        if version.status != LessonVersionStatus.published:
            # A release replaced the video mid-attempt: the old moments don't map, so
            # the whole new lesson must be watched (which the lesson rule enforces anyway).
            version = content.published_version(db, version.lesson_id) or version
            duration = content.duration_of(version) or 0.0
            start, end = 0.0, duration
        else:
            duration = content.duration_of(version) or 0.0
            start, end = span(timestamps, duration)
        db.add(
            RemediationItem(
                attempt_id=attempt.id,
                user_id=attempt.user_id,
                lesson_id=version.lesson_id,
                lesson_version_id=version.id,
                span_start_s=round(start, 3),
                span_end_s=round(end, 3),
                missed_count=len(items),
            )
        )
    db.flush()


def watched_ratio(item: RemediationItem) -> float:
    length = item.span_end_s - item.span_start_s
    return min(1.0, watch.total(item.watched) / length) if length > 0 else 1.0


def apply_heartbeat(
    db: Session, user_id: int, lesson_version_id: int, accepted: list[watch.Range]
) -> None:
    """Credit what a heartbeat counted to the open fragments of that lesson version."""
    if not accepted:
        return
    items = db.scalars(
        select(RemediationItem)
        .where(
            RemediationItem.user_id == user_id,
            RemediationItem.lesson_version_id == lesson_version_id,
            RemediationItem.satisfied_at.is_(None),
        )
        .with_for_update()
    )
    now = clock.utcnow()
    for item in items:
        inside = watch.intersect(accepted, item.span_start_s, item.span_end_s)
        if not inside:
            continue
        item.watched = [list(r) for r in watch.merge([*item.watched, *inside])]
        if watched_ratio(item) >= SATISFIED_RATIO - 1e-9:
            item.satisfied_at = now
            item.satisfied_reason = RemediationResolution.watched


def items_for(db: Session, attempt_id: int) -> list[RemediationItem]:
    return list(
        db.scalars(
            select(RemediationItem)
            .where(RemediationItem.attempt_id == attempt_id)
            .order_by(RemediationItem.lesson_id)
        )
    )


def close_for_superseded_versions(db: Session, version_ids: list[int]) -> None:
    """Release publish: the replaced lesson must be watched in full anyway."""
    db.execute(
        update(RemediationItem)
        .where(
            RemediationItem.lesson_version_id.in_(version_ids or [0]),
            RemediationItem.satisfied_at.is_(None),
        )
        .values(satisfied_at=clock.utcnow(), satisfied_reason=RemediationResolution.superseded)
    )
