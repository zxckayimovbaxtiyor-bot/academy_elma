"""Job queue on PostgreSQL: claim with FOR UPDATE SKIP LOCKED, run, record the outcome.

Handlers are registered per job kind by the phases that need them (transcode,
AI drafts, operator-certificate re-evaluation).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import clock
from app.models import Job
from app.models.enums import JobKind, JobLane, JobStatus

log = logging.getLogger("worker")

Handler = Callable[[Session, Job], dict[str, Any] | None]
HANDLERS: dict[JobKind, Handler] = {}
MAX_ATTEMPTS = 3


class JobError(Exception):
    """An expected failure with a stable code the admin UI can translate."""

    def __init__(self, code: str, params: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.params = params or {}


def enqueue(
    db: Session,
    kind: JobKind,
    lane: JobLane,
    payload: dict[str, Any],
    created_by: int | None = None,
) -> Job:
    job = Job(kind=kind, lane=lane, payload=payload, created_by=created_by)
    db.add(job)
    db.flush()
    return job


def claim_next(db: Session, lane: JobLane) -> Job | None:
    job = db.scalar(
        select(Job)
        .where(Job.status == JobStatus.queued, Job.lane == lane)
        .order_by(Job.created_at, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = JobStatus.running
    job.started_at = clock.utcnow()
    job.attempts += 1
    db.commit()
    return job


def run_job(db: Session, job: Job) -> None:
    handler = HANDLERS.get(job.kind)
    try:
        if handler is None:
            raise RuntimeError(f"no handler for job kind {job.kind}")
        result = handler(db, job)
        job.status = JobStatus.done
        job.result = result
        job.last_error = None
    except JobError as exc:
        db.rollback()
        log.warning("job %s (%s) failed: %s", job.id, job.kind, exc.code)
        job = db.get(Job, job.id)
        job.status = JobStatus.failed
        job.result = {"error": {"code": exc.code, "params": exc.params}}
        job.last_error = exc.code
    except Exception as exc:  # the job records the failure; the worker keeps running
        db.rollback()
        log.exception("job %s (%s) failed", job.id, job.kind)
        job = db.get(Job, job.id)
        job.status = JobStatus.failed
        job.last_error = repr(exc)[:4000]
    job.finished_at = clock.utcnow()
    db.commit()


def recover_interrupted(db: Session) -> int:
    """At startup, jobs left 'running' were cut off by a restart: retry or give up."""
    requeued = db.execute(
        update(Job)
        .where(Job.status == JobStatus.running, Job.attempts < MAX_ATTEMPTS)
        .values(status=JobStatus.queued, started_at=None)
    ).rowcount
    db.execute(
        update(Job)
        .where(Job.status == JobStatus.running)
        .values(status=JobStatus.failed, last_error="interrupted too many times")
    )
    db.commit()
    return requeued or 0
