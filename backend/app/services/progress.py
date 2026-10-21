"""Applies heartbeats to the stored watch record (the server side of the 90 % rule)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import clock
from app.models import LessonProgress
from app.services import watch


def record_heartbeat(
    db: Session,
    *,
    user_id: int,
    lesson_version_id: int,
    duration: float,
    ranges: Sequence[Sequence[float]],
    position_s: float,
) -> tuple[LessonProgress, list[watch.Range]]:
    """Credit one heartbeat under a row lock; returns the record and the ranges that counted.

    The first heartbeat for a lesson only starts the wall-clock baseline, so the
    player sends one (with no ranges) when the lesson opens.
    """
    now = clock.utcnow()
    db.execute(
        insert(LessonProgress)
        .values(user_id=user_id, lesson_version_id=lesson_version_id, started_at=now)
        .on_conflict_do_nothing(index_elements=["user_id", "lesson_version_id"])
    )
    progress = db.scalar(
        select(LessonProgress)
        .where(
            LessonProgress.user_id == user_id,
            LessonProgress.lesson_version_id == lesson_version_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    elapsed = (
        (now - progress.last_heartbeat_at).total_seconds() if progress.last_heartbeat_at else 0.0
    )
    completed = progress.completed_at is not None
    result = watch.credit(
        watched=progress.watched,
        incoming=ranges,
        duration=duration,
        max_position_s=progress.max_position_s,
        completed=completed,
        elapsed_s=elapsed,
    )
    progress.watched = [list(r) for r in result.watched]
    progress.watched_s = result.watched_s
    progress.max_position_s = result.max_position_s
    progress.last_heartbeat_at = now
    if not completed and watch.is_complete(result.watched_s, duration):
        progress.completed_at = now
    # Resume point; on a first viewing it can't be past the seek limit.
    limit = duration if progress.completed_at else progress.max_position_s
    progress.last_position_s = min(max(position_s, 0.0), limit)
    return progress, result.accepted
