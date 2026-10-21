"""Readiness reports (admin: everything; branch head: forced to their own branch).

Every report also comes as CSV (``?format=csv``): UTF-8 with BOM and ";" so Excel
in a ru or uz locale opens it directly. Headers follow ``lang`` or the user's
language.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import clock
from app.api.common import csv_response
from app.auth.deps import require_roles
from app.db import get_db
from app.errors import not_found
from app.models import AppUser, Branch, JobRole
from app.models.enums import AccessRole, Language
from app.schemas.common import Page, Ref
from app.schemas.reports import (
    BranchRowOut,
    LearnerDetailOut,
    ModuleCertOut,
    ModuleProgressOut,
    OperatorOut,
    SummaryOut,
    UserRowOut,
    WaveRef,
)
from app.services import csvio, reports
from app.services.certificates import CertStatus
from app.services.i18n import t
from app.services.reports import Filters, ModuleState

router = APIRouter(tags=["reports"])
viewer = require_roles(AccessRole.branch_head)  # admin passes every role check
Format = Literal["json", "csv"]


def filters(
    wave_id: int | None = None,
    region_id: int | None = None,
    branch_id: int | None = None,
    module_id: int | None = None,
    job_role_id: int | None = None,
) -> Filters:
    return Filters(wave_id, region_id, branch_id, module_id, job_role_id)


def _lang(user: AppUser, lang: Language | None) -> Language:
    return lang or user.preferred_language


def _name(row, lang: Language) -> str:
    return row.name_ru if lang == Language.ru else row.name_uz


def _local(moment: datetime | None) -> str:
    return moment.astimezone(clock.local_tz()).strftime("%d.%m.%Y %H:%M") if moment else ""


def _date(moment: datetime | None) -> str:
    return clock.local_date(moment).strftime("%d.%m.%Y") if moment else ""


def _wave(w) -> WaveRef:
    return WaveRef(id=w.id, name_uz=w.name_uz, name_ru=w.name_ru, deadline=w.deadline,
                   go_live=w.go_live)  # fmt: skip


def _summary(rows: list[reports.LearnerRow], latest: str | None) -> SummaryOut:
    c = reports.counts(rows)
    return SummaryOut(
        total=c["total"], branches=len({r.branch.id for r in rows}), certified=c["certified"],
        certified_pct=reports.pct(c["certified"], c["total"]),
        recert_required=c["recert_required"], in_progress=c["in_progress"],
        not_started=c["not_started"], overdue=c["overdue"], latest_release=latest,
    )  # fmt: skip


@router.get("/reports/summary", response_model=SummaryOut)
def summary(
    f: Filters = Depends(filters),
    format: Format = "json",
    lang: Language | None = None,
    user: AppUser = Depends(viewer),
    db: Session = Depends(get_db),
):
    rows = reports.learners(db, reports.scoped(user, f), clock.utcnow())
    out = _summary(rows, reports.latest_release_code(db))
    if format == "json":
        return out
    lg = _lang(user, lang)
    status = [(s.value, t(lg, f"report.status.{s.value}")) for s in ModuleState]
    lines = [
        (t(lg, "report.total"), out.total),
        (t(lg, "report.branches"), out.branches),
        *((label, getattr(out, key)) for key, label in status),
        (t(lg, "report.overdue"), out.overdue),
    ]
    return csv_response(csvio.to_csv([t(lg, "csv.metric"), t(lg, "csv.value")], lines),
                        "summary.csv")  # fmt: skip


@router.get("/reports/branches", response_model=list[BranchRowOut])
def branches(
    f: Filters = Depends(filters),
    format: Format = "json",
    lang: Language | None = None,
    user: AppUser = Depends(viewer),
    db: Session = Depends(get_db),
):
    rows = reports.branch_rows(reports.learners(db, reports.scoped(user, f), clock.utcnow()))
    if format == "json":
        return [
            BranchRowOut(
                branch=Ref.model_validate(r["branch"]), region=Ref.model_validate(r["region"]),
                wave=_wave(r["wave"]), total=r["total"], certified=r["certified"],
                certified_pct=r["certified_pct"], recert_required=r["recert_required"],
                in_progress=r["in_progress"], not_started=r["not_started"],
                overdue=r["overdue"], readiness=r["readiness"],
            )  # fmt: skip
            for r in rows
        ]
    lg = _lang(user, lang)
    header = [t(lg, f"csv.{k}") for k in (
        "branch_code", "branch", "region", "learners", "certified", "certified_pct",
        "in_progress", "not_started", "recert_required", "overdue", "readiness",
    )]  # fmt: skip
    lines = [
        [
            r["branch"].code, _name(r["branch"], lg), _name(r["region"], lg), r["total"],
            r["certified"], r["certified_pct"], r["in_progress"], r["not_started"],
            r["recert_required"], r["overdue"], t(lg, f"report.readiness.{r['readiness'].value}"),
        ]  # fmt: skip
        for r in rows
    ]
    return csv_response(csvio.to_csv(header, lines), "branches.csv")


@router.get("/reports/users", response_model=Page[UserRowOut])
def users(
    f: Filters = Depends(filters),
    status: ModuleState | None = None,
    overdue: bool | None = None,
    q: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    format: Format = "json",
    lang: Language | None = None,
    user: AppUser = Depends(viewer),
    db: Session = Depends(get_db),
):
    rows = reports.learners(db, reports.scoped(user, f), clock.utcnow())
    if status is not None:
        rows = [r for r in rows if r.status == status]
    if overdue is not None:
        rows = [r for r in rows if r.overdue == overdue]
    if q and q.strip():
        needle = q.strip().casefold()
        rows = [
            r for r in rows
            if needle in r.user.full_name.casefold() or needle in r.user.employee_id.casefold()
        ]  # fmt: skip
    if format == "csv":
        lg = _lang(user, lang)
        header = [t(lg, f"csv.{k}") for k in (
            "employee_id", "full_name", "branch_code", "branch", "region", "job_role", "status",
            "overdue", "modules_certified", "last_seen",
        )]  # fmt: skip
        lines = [
            [
                r.user.employee_id, r.user.full_name, r.branch.code, _name(r.branch, lg),
                _name(r.region, lg), _name(r.job_role, lg),
                t(lg, f"report.status.{r.status.value}"),
                t(lg, "report.yes" if r.overdue else "report.no"),
                f"{_certified(r)}/{len(r.states)}", _local(r.user.last_seen_at),
            ]  # fmt: skip
            for r in rows
        ]
        return csv_response(csvio.to_csv(header, lines), "learners.csv")
    chunk = rows[(page - 1) * page_size : page * page_size]
    items = [
        UserRowOut(
            user_id=r.user.id, employee_id=r.user.employee_id, full_name=r.user.full_name,
            branch=Ref.model_validate(r.branch), region=Ref.model_validate(r.region),
            job_role=Ref.model_validate(r.job_role), wave=_wave(r.wave), status=r.status,
            overdue=r.overdue, modules_certified=_certified(r), modules_total=len(r.states),
            last_seen_at=r.user.last_seen_at,
        )  # fmt: skip
        for r in chunk
    ]
    return Page(items=items, total=len(rows), page=page, page_size=page_size)


def _certified(row: reports.LearnerRow) -> int:
    return sum(1 for s in row.states.values() if s == ModuleState.certified)


def learner_detail_out(db: Session, target: AppUser) -> LearnerDetailOut:
    """Shared by the report drill-down and the admin user page."""
    d = reports.learner_detail(db, target, clock.utcnow())
    operator = d["operator"]
    branch = db.get(Branch, target.branch_id) if target.branch_id else None
    role = db.get(JobRole, target.job_role_id) if target.job_role_id else None
    modules = []
    for m in d["modules"]:
        module, cert, last = m["module"], m["certificate"], m["last_attempt"]
        modules.append(
            ModuleProgressOut(
                module_id=module.id, code=module.code, type=module.type,
                title_uz=module.title_uz, title_ru=module.title_ru, state=m["state"],
                locked=m["locked"], lessons_completed=m["lessons_completed"],
                lessons_total=m["lessons_total"], attempts_used=m["attempts_used"],
                attempts_max=m["attempts_max"],
                last_attempt_status=last.status if last else None,
                last_score_pct=last.score_pct if last else None,
                last_attempt_at=last.started_at if last else None,
                certificate=ModuleCertOut(
                    number=cert.number, status=m["certificate_status"],
                    release=m["release_code"], score_pct=cert.score_pct,
                    issued_at=cert.issued_at, recert_due_at=cert.recert_due_at,
                ) if cert else None,
            )
        )  # fmt: skip
    return LearnerDetailOut(
        user_id=target.id, employee_id=target.employee_id, full_name=target.full_name,
        branch=Ref.model_validate(branch) if branch else None,
        job_role=Ref.model_validate(role) if role else None,
        wave=_wave(d["wave"]) if d["wave"] else None, status=d["status"], overdue=d["overdue"],
        operator=OperatorOut(
            status=operator[1] if operator else CertStatus.missing,
            number=operator[0].number if operator else None,
            issued_at=operator[0].issued_at if operator else None,
        ),
        modules=modules,
    )  # fmt: skip


@router.get("/reports/users/{user_id}", response_model=LearnerDetailOut)
def user_detail(
    user_id: int,
    format: Format = "json",
    lang: Language | None = None,
    user: AppUser = Depends(viewer),
    db: Session = Depends(get_db),
):
    target = db.get(AppUser, user_id)
    in_scope = target is not None and (
        user.access_role != AccessRole.branch_head or target.branch_id == user.branch_id
    )
    if not in_scope:
        raise not_found("user")
    out = learner_detail_out(db, target)
    if format == "json":
        return out
    lg = _lang(user, lang)
    header = [t(lg, f"csv.{k}") for k in (
        "module", "status", "lessons", "attempts", "last_score", "certificate", "issued",
        "recertify_by",
    )]  # fmt: skip
    lines = [
        [
            m.title_ru if lg == Language.ru else m.title_uz,
            t(lg, f"report.status.{m.state.value}"),
            f"{m.lessons_completed}/{m.lessons_total}", f"{m.attempts_used}/{m.attempts_max}",
            m.last_score_pct, m.certificate.number if m.certificate else "",
            _date(m.certificate.issued_at) if m.certificate else "",
            _date(m.certificate.recert_due_at) if m.certificate else "",
        ]  # fmt: skip
        for m in out.modules
    ]
    return csv_response(csvio.to_csv(header, lines), f"{target.employee_id}.csv")


@router.get("/exports/access-list.csv")
def access_list(
    wave_id: int | None = None,
    branch_id: int | None = None,
    lang: Language | None = None,
    user: AppUser = Depends(require_roles()),
    db: Session = Depends(get_db),
):
    """Rule 13: who may get the Single Window role (fully certified learners only)."""
    lg = _lang(user, lang)
    rows = reports.access_list(db, wave_id, branch_id, clock.utcnow())
    header = [t(lg, f"csv.{k}") for k in (
        "employee_id", "full_name", "branch_code", "branch", "region", "job_role",
        "certificate", "issued", "recertify_by",
    )]  # fmt: skip
    lines = [
        [
            r.user.employee_id, r.user.full_name, r.branch.code, _name(r.branch, lg),
            _name(r.region, lg), _name(r.job_role, lg), cert.number, _date(cert.issued_at),
            _date(renew_by),
        ]  # fmt: skip
        for r, cert, renew_by in rows
    ]
    return csv_response(csvio.to_csv(header, lines), "access-list.csv")

