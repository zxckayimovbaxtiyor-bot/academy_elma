"""Re-evaluates operator certificates after assignments change (general lane)."""

from __future__ import annotations

from app.models.enums import JobKind
from app.services.certificates import run_evaluation
from app.worker.runner import HANDLERS

HANDLERS[JobKind.operator_cert_eval] = run_evaluation
