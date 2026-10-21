"""AI drafting (methodologist + admin). Never imported by learner routes.

The request is validated here; the model call itself runs in the worker.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai import get_generator
from app.auth.deps import require_roles
from app.db import get_db
from app.errors import not_found
from app.models import AppUser, Job
from app.models.enums import AccessRole
from app.schemas.ai import AiStatusOut, DraftRequestIn, JobOut
from app.services import ai_drafts

router = APIRouter(prefix="/admin", tags=["admin: ai"])
editor = require_roles(AccessRole.methodologist)


@router.get("/ai/status", response_model=AiStatusOut)
def ai_status(_: AppUser = Depends(editor)) -> AiStatusOut:
    generator = get_generator()
    return AiStatusOut(enabled=generator.enabled, model=generator.model)


@router.post("/lesson-versions/{version_id}/ai-drafts", response_model=JobOut, status_code=202)
def request_drafts(
    version_id: int,
    body: DraftRequestIn,
    actor: AppUser = Depends(editor),
    db: Session = Depends(get_db),
) -> JobOut:
    job = ai_drafts.enqueue(db, version_id, body.model_dump(), get_generator(), actor.id)
    db.commit()
    return JobOut.of(job)


@router.get("/jobs/{job_id}", response_model=JobOut)
def job_status(job_id: int, db: Session = Depends(get_db), _: AppUser = Depends(editor)) -> JobOut:
    job = db.get(Job, job_id)
    if job is None:
        raise not_found("job")
    return JobOut.of(job)
