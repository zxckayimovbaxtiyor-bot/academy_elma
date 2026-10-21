"""Waves (admin): dates, branches and the role x module matrix (mockup 9).

Changing branches or the matrix changes who must hold which certificates, so the
operator certificates of the learners concerned are re-evaluated by the worker.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import clock
from app.auth.deps import require_roles
from app.db import get_db
from app.errors import AppError, not_found
from app.models import AppUser, Branch, JobRole, Module, Wave, WaveBranch, WaveModuleRole
from app.models.enums import ModuleType
from app.schemas.common import Ref
from app.schemas.waves import (
    AssignmentIn,
    AssignmentsIn,
    BranchesIn,
    MatrixModuleOut,
    MatrixRoleOut,
    WaveBranchOut,
    WaveDetail,
    WaveIn,
    WaveOut,
    WavePatch,
    WaveStatus,
)
from app.services import audit, certificates, reports
from app.services.reports import Filters, ModuleState

router = APIRouter(prefix="/admin/waves", tags=["admin: waves"])
admin_only = require_roles()


def _wave(db: Session, wave_id: int) -> Wave:
    wave = db.get(Wave, wave_id)
    if wave is None:
        raise not_found("wave")
    return wave


def _check_dates(training_start: date, deadline: date, go_live: date) -> None:
    if not training_start <= deadline <= go_live:
        raise AppError(400, "wave.dates_invalid")


def status_of(wave: Wave, today: date) -> WaveStatus:
    if today < wave.training_start:
        return WaveStatus.planned
    return WaveStatus.active if today <= wave.go_live else WaveStatus.completed


def _learner_ids(db: Session, branch_ids: list[int]) -> list[int]:
    return list(
        db.scalars(
            select(AppUser.id).where(
                AppUser.branch_id.in_(branch_ids or [0]),
                AppUser.access_role.in_(reports.LEARNER_ROLES),
            )
        )
    )


def _branch_ids(db: Session, wave_id: int) -> list[int]:
    return list(db.scalars(select(WaveBranch.branch_id).where(WaveBranch.wave_id == wave_id)))


def _out(wave: Wave, rows: list[reports.LearnerRow], branches: int) -> WaveOut:
    certified = sum(1 for r in rows if r.status == ModuleState.certified)
    return WaveOut(
        id=wave.id, name_uz=wave.name_uz, name_ru=wave.name_ru,
        training_start=wave.training_start, deadline=wave.deadline, go_live=wave.go_live,
        status=status_of(wave, clock.today()), branches=branches, learners=len(rows),
        certified=certified, certified_pct=reports.pct(certified, len(rows)),
    )  # fmt: skip


@router.get("", response_model=list[WaveOut])
def list_waves(db: Session = Depends(get_db), _: AppUser = Depends(admin_only)):
    rows = reports.learners(db, Filters(), clock.utcnow())
    by_wave: dict[int, list[reports.LearnerRow]] = {}
    for row in rows:
        by_wave.setdefault(row.wave.id, []).append(row)
    branch_counts = Counter(db.scalars(select(WaveBranch.wave_id)))
    waves = db.scalars(select(Wave).order_by(Wave.training_start, Wave.id))
    return [_out(w, by_wave.get(w.id, []), branch_counts.get(w.id, 0)) for w in waves]


@router.post("", response_model=WaveOut, status_code=201)
def create_wave(body: WaveIn, actor: AppUser = Depends(admin_only), db: Session = Depends(get_db)):
    _check_dates(body.training_start, body.deadline, body.go_live)
    wave = Wave(**body.model_dump())
    db.add(wave)
    db.flush()
    audit.record(db, "wave.created", actor_id=actor.id, entity="wave", entity_id=wave.id)
    db.commit()
    return _out(wave, [], 0)


@router.get("/{wave_id}", response_model=WaveDetail)
def get_wave(wave_id: int, db: Session = Depends(get_db), _: AppUser = Depends(admin_only)):
    wave = _wave(db, wave_id)
    rows = reports.learners(db, Filters(wave_id=wave.id), clock.utcnow())
    branches = db.scalars(
        select(Branch)
        .join(WaveBranch, WaveBranch.branch_id == Branch.id)
        .where(WaveBranch.wave_id == wave.id)
        .order_by(Branch.code)
    ).all()
    per_branch = Counter(r.branch.id for r in rows)
    per_role = Counter(r.job_role.id for r in rows)
    roles = db.scalars(select(JobRole).order_by(JobRole.sort, JobRole.code)).all()
    modules = db.scalars(
        select(Module).where(Module.type != ModuleType.faq).order_by(Module.sort, Module.id)
    ).all()
    assignments = db.execute(
        select(WaveModuleRole.job_role_id, WaveModuleRole.module_id)
        .where(WaveModuleRole.wave_id == wave.id)
        .order_by(WaveModuleRole.job_role_id, WaveModuleRole.module_id)
    ).all()
    base = _out(wave, rows, len(branches)).model_dump()
    return WaveDetail(
        **base,
        branch_list=[
            WaveBranchOut(**Ref.model_validate(b).model_dump(), learners=per_branch[b.id])
            for b in branches
        ],
        roles=[
            MatrixRoleOut(**Ref.model_validate(r).model_dump(), learners=per_role[r.id])
            for r in roles
        ],
        modules=[
            MatrixModuleOut(id=m.id, code=m.code, type=m.type, title_uz=m.title_uz,
                            title_ru=m.title_ru)  # fmt: skip
            for m in modules
        ],
        assignments=[AssignmentIn(job_role_id=r, module_id=m) for r, m in assignments],
    )


@router.patch("/{wave_id}", response_model=WaveOut)
def patch_wave(
    wave_id: int,
    body: WavePatch,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
):
    wave = _wave(db, wave_id)
    changes = body.model_dump(exclude_none=True)
    dates = ("training_start", "deadline", "go_live")
    merged = {k: changes.get(k, getattr(wave, k)) for k in dates}
    _check_dates(**merged)
    for attr, value in changes.items():
        setattr(wave, attr, value)
    audit.record(
        db, "wave.updated", actor_id=actor.id, entity="wave", entity_id=wave.id,
        data={k: str(v) for k, v in changes.items()},
    )  # fmt: skip
    db.commit()
    rows = reports.learners(db, Filters(wave_id=wave.id), clock.utcnow())
    return _out(wave, rows, len(_branch_ids(db, wave.id)))


@router.put("/{wave_id}/branches", response_model=WaveOut)
def set_branches(
    wave_id: int,
    body: BranchesIn,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
):
    """A branch goes live once, so it belongs to at most one wave."""
    wave = _wave(db, wave_id)
    wanted = set(body.branch_ids)
    known = set(db.scalars(select(Branch.id).where(Branch.id.in_(wanted or {0}))))
    if wanted - known:
        raise AppError(400, "wave.branch_unknown", {"branch_ids": sorted(wanted - known)})
    taken = sorted(
        db.scalars(
            select(WaveBranch.branch_id).where(
                WaveBranch.branch_id.in_(wanted or {0}), WaveBranch.wave_id != wave.id
            )
        )
    )
    if taken:
        raise AppError(409, "wave.branch_in_other_wave", {"branch_ids": taken})
    current = set(_branch_ids(db, wave.id))
    db.execute(
        delete(WaveBranch).where(
            WaveBranch.wave_id == wave.id, WaveBranch.branch_id.in_(current - wanted or {0})
        )
    )
    db.add_all(WaveBranch(wave_id=wave.id, branch_id=b) for b in sorted(wanted - current))
    db.flush()
    changed = sorted(current ^ wanted)
    certificates.enqueue_evaluation(db, _learner_ids(db, changed), actor.id)
    audit.record(
        db, "wave.branches_set", actor_id=actor.id, entity="wave", entity_id=wave.id,
        data={"added": sorted(wanted - current), "removed": sorted(current - wanted)},
    )  # fmt: skip
    db.commit()
    rows = reports.learners(db, Filters(wave_id=wave.id), clock.utcnow())
    return _out(wave, rows, len(wanted))


@router.put("/{wave_id}/assignments", response_model=WaveDetail)
def set_assignments(
    wave_id: int,
    body: AssignmentsIn,
    actor: AppUser = Depends(admin_only),
    db: Session = Depends(get_db),
):
    wave = _wave(db, wave_id)
    wanted = {(a.job_role_id, a.module_id) for a in body.items}
    roles = set(db.scalars(select(JobRole.id)))
    products = set(db.scalars(select(Module.id).where(Module.type == ModuleType.product)))
    if any(r not in roles for r, _ in wanted):
        raise AppError(400, "wave.job_role_unknown")
    if any(m not in products for _, m in wanted):
        raise AppError(400, "wave.module_not_assignable")  # Core is implicit, FAQ never
    db.execute(delete(WaveModuleRole).where(WaveModuleRole.wave_id == wave.id))
    db.add_all(
        WaveModuleRole(wave_id=wave.id, job_role_id=r, module_id=m) for r, m in sorted(wanted)
    )
    db.flush()
    certificates.enqueue_evaluation(db, _learner_ids(db, _branch_ids(db, wave.id)), actor.id)
    audit.record(
        db, "wave.assignments_set", actor_id=actor.id, entity="wave", entity_id=wave.id,
        data={"items": [[r, m] for r, m in sorted(wanted)]},
    )  # fmt: skip
    db.commit()
    return get_wave(wave.id, db, actor)
