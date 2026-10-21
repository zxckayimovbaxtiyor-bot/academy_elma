from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import AttemptStatus, ModuleType
from app.schemas.common import Ref
from app.services.certificates import CertStatus
from app.services.reports import ModuleState, Readiness


class SummaryOut(BaseModel):
    """KPI cards of mockup 6. Buckets are exclusive and add up to ``total``."""

    total: int
    branches: int
    certified: int
    certified_pct: int
    recert_required: int
    in_progress: int
    not_started: int
    overdue: int
    latest_release: str | None


class WaveRef(BaseModel):
    id: int
    name_uz: str
    name_ru: str
    deadline: date
    go_live: date


class BranchRowOut(BaseModel):
    branch: Ref
    region: Ref
    wave: WaveRef
    total: int
    certified: int
    certified_pct: int
    recert_required: int
    in_progress: int
    not_started: int
    overdue: int
    readiness: Readiness


class UserRowOut(BaseModel):
    user_id: int
    employee_id: str
    full_name: str
    branch: Ref
    region: Ref
    job_role: Ref
    wave: WaveRef
    status: ModuleState
    overdue: bool
    modules_certified: int
    modules_total: int
    last_seen_at: datetime | None


class ModuleCertOut(BaseModel):
    number: str
    status: CertStatus
    release: str | None
    score_pct: float | None
    issued_at: datetime
    recert_due_at: datetime | None


class ModuleProgressOut(BaseModel):
    module_id: int
    code: str
    type: ModuleType
    title_uz: str
    title_ru: str
    state: ModuleState
    locked: bool
    lessons_completed: int
    lessons_total: int
    attempts_used: int  # in the current cycle
    attempts_max: int
    last_attempt_status: AttemptStatus | None
    last_score_pct: float | None
    last_attempt_at: datetime | None
    certificate: ModuleCertOut | None


class OperatorOut(BaseModel):
    status: CertStatus
    number: str | None
    issued_at: datetime | None


class LearnerDetailOut(BaseModel):
    user_id: int
    employee_id: str
    full_name: str
    branch: Ref | None
    job_role: Ref | None
    wave: WaveRef | None
    status: ModuleState
    overdue: bool
    operator: OperatorOut
    modules: list[ModuleProgressOut]
