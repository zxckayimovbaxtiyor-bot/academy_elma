"""AI drafting jobs (general lane): the only place the model is called."""

from __future__ import annotations

from app.ai import get_generator
from app.models.enums import JobKind
from app.services import ai_drafts
from app.worker.runner import HANDLERS

HANDLERS[JobKind.ai_draft] = lambda db, job: ai_drafts.run(db, job, get_generator())
