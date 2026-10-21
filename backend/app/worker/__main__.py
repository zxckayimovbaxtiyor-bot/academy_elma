"""Worker process: ``python -m app.worker``.

Two lanes so a long transcode never holds up AI drafts, plus periodic sweeps.
"""

from __future__ import annotations

import logging
import signal
import threading

from app import clock
from app.auth.sessions import purge_expired
from app.db import SessionLocal
from app.models.enums import JobLane
from app.services.attempts import finalize_overdue
from app.worker import ai_draft, operator_certs, transcode  # noqa: F401  (register job handlers)
from app.worker.runner import claim_next, recover_interrupted, run_job

POLL_SECONDS = 2.0
SWEEP_SECONDS = 60.0
log = logging.getLogger("worker")


def lane_loop(lane: JobLane, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                job = claim_next(db, lane)
                if job is not None:
                    log.info("running job %s (%s)", job.id, job.kind)
                    run_job(db, job)
                    continue
        except Exception:  # database restart etc.: wait and retry
            log.exception("lane %s error", lane)
        stop.wait(POLL_SECONDS)


def sweep_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                removed = purge_expired(db)
                db.commit()
                if removed:
                    log.info("purged %s expired sessions", removed)
                graded = finalize_overdue(db, clock.utcnow())
                if graded:
                    log.info("graded %s abandoned attempts", graded)
        except Exception:
            log.exception("sweep error")
        stop.wait(SWEEP_SECONDS)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    with SessionLocal() as db:
        requeued = recover_interrupted(db)
    log.info("worker started (%s interrupted jobs requeued)", requeued)

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    threads = [
        threading.Thread(target=lane_loop, args=(JobLane.media, stop), name="lane-media"),
        threading.Thread(target=lane_loop, args=(JobLane.general, stop), name="lane-general"),
        threading.Thread(target=sweep_loop, args=(stop,), name="sweeps"),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    log.info("worker stopped")


if __name__ == "__main__":
    main()
