"""Readiness reports, computed live (about 6,000 learners x 6 modules is small).

Per assigned module a learner is certified (valid certificate), recert_required
(the certificate's renewal date has passed), in_progress (watched something or
took the test) or not_started. Across modules the buckets are exclusive:
certified only if every assigned module is; otherwise recert_required if any
module needs renewal; otherwise in_progress if anything was started; otherwise
not_started. Overdue is separate: the wave deadline (end of that day, Tashkent)
has passed and the learner is not certified.

With a module filter, everything is computed for that module alone, over the
learners it is assigned to. Branch heads always get their own branch.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from sqlalchemy import select, union
from sqlalchemy.orm import Session

from app import clock
from app.models import (
    AppUser,
    Branch,
    ElmaRelease,
    JobRole,
    Lesson,
    LessonProgress,
    LessonVersion,
    Module,
    Region,
    TestAttempt,
    Wave,
    WaveBranch,
    WaveModuleRole,
)
from app.models.enums import AccessRole, ModuleType, ReleaseStatus
from app.services import certificates
from app.services.certificates import CertStatus

LEARNER_ROLES = (AccessRole.learner, AccessRole.branch_head)


class ModuleState(StrEnum):
    certified = "certified"
    recert_required = "recert_required"
    in_progress = "in_progress"
    not_started = "not_started"


class Readiness(StrEnum):
    ready = "ready"  # >= 90 % certified (mockup 6: "Tayyor")
    at_risk = "at_risk"  # 60-89 %
    not_ready = "not_ready"  # < 60 %


@dataclass(frozen=True)
class Filters:
    wave_id: int | None = None
    region_id: int | None = None
    branch_id: int | None = None
    module_id: int | None = None
    job_role_id: int | None = None


@dataclass
class LearnerRow:
    user: AppUser
    branch: Branch
    region: Region
    wave: Wave
    job_role: JobRole
    states: dict[int, ModuleState]  # module id → state, for the modules in scope
    status: ModuleState
    overdue: bool
    modules: list[int] = field(default_factory=list)  # every assigned module, in order


def scoped(user: AppUser, filters: Filters) -> Filters:
    """Branch heads see their own branch only, whatever they ask for."""
    if user.access_role == AccessRole.branch_head:
        return replace(filters, branch_id=user.branch_id or 0)
    return filters


def module_state(status: CertStatus, active: bool) -> ModuleState:
    if status == CertStatus.valid:
        return ModuleState.certified
    if status == CertStatus.recert_required:
        return ModuleState.recert_required
    return ModuleState.in_progress if active else ModuleState.not_started


def learner_state(states: Iterable[ModuleState]) -> ModuleState:
    states = list(states)
    if states and all(s == ModuleState.certified for s in states):
        return ModuleState.certified
    if ModuleState.recert_required in states:
        return ModuleState.recert_required
    if ModuleState.certified in states or ModuleState.in_progress in states:
        return ModuleState.in_progress
    return ModuleState.not_started


def readiness(certified: int, total: int) -> Readiness:
    if total and certified * 100 >= 90 * total:
        return Readiness.ready
    if total and certified * 100 >= 60 * total:
        return Readiness.at_risk
    return Readiness.not_ready


def pct(part: int, total: int) -> int:
    return round(part * 100 / total) if total else 0


def activity(db: Session, user_ids: list[int]) -> set[tuple[int, int]]:
    """(user_id, module_id) where the learner watched something or took the test."""
    ids = user_ids or [0]
    watched = (
        select(LessonProgress.user_id, Lesson.module_id)
        .join(LessonVersion, LessonVersion.id == LessonProgress.lesson_version_id)
        .join(Lesson, Lesson.id == LessonVersion.lesson_id)
        .where(LessonProgress.user_id.in_(ids))
    )
    tested = select(TestAttempt.user_id, TestAttempt.module_id).where(TestAttempt.user_id.in_(ids))
    return {(u, m) for u, m in db.execute(union(watched, tested)).all()}


def ordered_modules(db: Session) -> dict[int, Module]:
    rows = db.scalars(select(Module).order_by(Module.sort, Module.id))
    return {m.id: m for m in rows}


def learners(db: Session, filters: Filters, now: datetime) -> list[LearnerRow]:
    stmt = (
        select(AppUser, Branch, Region, Wave, JobRole)
        .join(Branch, Branch.id == AppUser.branch_id)
        .join(Region, Region.id == Branch.region_id)
        .join(WaveBranch, WaveBranch.branch_id == Branch.id)
        .join(Wave, Wave.id == WaveBranch.wave_id)
        .join(JobRole, JobRole.id == AppUser.job_role_id)
        .where(AppUser.is_active.is_(True), AppUser.access_role.in_(LEARNER_ROLES))
        .order_by(Branch.code, AppUser.full_name, AppUser.id)
    )
    for column, value in (
        (Wave.id, filters.wave_id),
        (Region.id, filters.region_id),
        (Branch.id, filters.branch_id),
        (JobRole.id, filters.job_role_id),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    rows = db.execute(stmt).all()
    modules = ordered_modules(db)
    order = {mid: i for i, mid in enumerate(modules)}
    core = [m.id for m in modules.values() if m.type == ModuleType.core]
    matrix: dict[tuple[int, int], set[int]] = defaultdict(set)
    for wave_id, module_id, role_id in db.execute(
        select(WaveModuleRole.wave_id, WaveModuleRole.module_id, WaveModuleRole.job_role_id)
        .join(Module, Module.id == WaveModuleRole.module_id)
        .where(Module.type == ModuleType.product)
    ).all():
        matrix[(wave_id, role_id)].add(module_id)

    user_ids = [user.id for user, *_ in rows]
    certs = certificates.current_module_certs(db, user_ids)
    active = activity(db, user_ids)
    out = []
    for user, branch, region, wave, role in rows:
        assigned = core + sorted(matrix[(wave.id, role.id)], key=order.__getitem__)
        if filters.module_id is not None and filters.module_id not in assigned:
            continue
        scope = [filters.module_id] if filters.module_id is not None else assigned
        states = {
            m: module_state(
                certificates.module_status(certs.get((user.id, m)), now), (user.id, m) in active
            )
            for m in scope
        }
        status = learner_state(states.values())
        overdue = status != ModuleState.certified and now >= clock.end_of_day(wave.deadline)
        out.append(
            LearnerRow(user, branch, region, wave, role, states, status, overdue, assigned)
        )
    return out


def latest_release_code(db: Session) -> str | None:
    return db.scalar(
        select(ElmaRelease.code)
        .where(ElmaRelease.status == ReleaseStatus.published)
        .order_by(ElmaRelease.published_at.desc(), ElmaRelease.id.desc())
        .limit(1)
    )


def counts(rows: list[LearnerRow]) -> dict[str, int]:
    out = {state.value: 0 for state in ModuleState}
    for row in rows:
        out[row.status.value] += 1
    out["overdue"] = sum(1 for row in rows if row.overdue)
    out["total"] = len(rows)
    return out


def branch_rows(rows: list[LearnerRow]) -> list[dict]:
    groups: dict[int, list[LearnerRow]] = defaultdict(list)
    for row in rows:
        groups[row.branch.id].append(row)
    out = []
    for members in groups.values():
        first = members[0]
        c = counts(members)
        out.append(
            {
                "branch": first.branch, "region": first.region, "wave": first.wave, **c,
                "certified_pct": pct(c["certified"], c["total"]),
                "readiness": readiness(c["certified"], c["total"]),
            }
        )  # fmt: skip
    out.sort(key=lambda r: (-r["certified"] / r["total"], r["branch"].code))
    return out


def access_list(db: Session, wave_id: int | None, branch_id: int | None, now: datetime):
    """Rule 13: learners whose operator certificate is valid and who hold a valid
    certificate for every module assigned to them now (a newly assigned module takes
    them off the list until they pass it)."""
    rows = [
        r
        for r in learners(db, Filters(wave_id=wave_id, branch_id=branch_id), now)
        if r.status == ModuleState.certified
    ]
    operators = certificates.current_operator_certs(db, [r.user.id for r in rows], now)
    out = []
    for row in rows:
        cert, status = operators.get(row.user.id, (None, CertStatus.missing))
        if status == CertStatus.valid:
            out.append((row, cert, certificates.renewal_date(db, cert)))
    return out


def learner_detail(db: Session, user: AppUser, now: datetime) -> dict:
    """Drill-down for one learner: per assigned module, progress, attempts, certificate."""
    from app.services import access, attempts  # attempts depends on certificates

    wave = access.user_wave(db, user)
    assigned = access.assigned_modules(db, user)
    certs = certificates.current_module_certs(db, [user.id], [m.id for m in assigned])
    active = activity(db, [user.id])
    core_certified = access.holds_core_certificate(db, user.id)
    codes = dict(db.execute(select(ElmaRelease.id, ElmaRelease.code)).all())
    modules = []
    for module in assigned:
        cert = certs.get((user.id, module.id))
        status = certificates.module_status(cert, now)
        done, total = attempts.lesson_counts(db, user.id, module.id)
        every = attempts.all_attempts(db, user.id, module.id)
        last = every[-1] if every else None
        modules.append(
            {
                "module": module,
                "state": module_state(status, (user.id, module.id) in active),
                "locked": access.is_locked(module, core_certified),
                "lessons_completed": done, "lessons_total": total,
                "attempts_used": len(attempts.cycle_attempts(db, user.id, module.id)),
                "attempts_max": module.test_max_attempts,
                "last_attempt": last,
                "certificate": cert, "certificate_status": status,
                "release_code": codes.get(cert.release_id) if cert else None,
            }
        )  # fmt: skip
    status = learner_state(m["state"] for m in modules)
    operator = certificates.current_operator_certs(db, [user.id], now).get(user.id)
    overdue = (
        wave is not None
        and status != ModuleState.certified
        and now >= clock.end_of_day(wave.deadline)
    )
    return {"wave": wave, "status": status, "overdue": overdue, "operator": operator,
            "modules": modules}  # fmt: skip
