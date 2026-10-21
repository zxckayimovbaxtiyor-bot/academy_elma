"""Certificates (rule 8) and recertification after a release (rule 9).

* A module certificate is issued when a test is passed and supersedes the
  learner's previous certificate for that module.
* The operator certificate is issued once Core and every assigned module hold a
  valid certificate. Whenever the set it should cover changes (a recertification,
  or new assignments for a learner who is complete), it is reissued and the old
  one superseded.
* Status is derived on read:
  - module: superseded once replaced; recert_required once ``recert_due_at`` has
    passed; otherwise valid (with a "recertify by" date while it is ahead);
  - operator: superseded once replaced; recert_required if any certificate it
    covers is no longer valid; otherwise valid.
* Each certificate keeps a snapshot of holder, branch, modules and releases, so a
  later rename never changes an issued certificate. The PDF is drawn from it.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Iterable
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import distinct, func, or_, select, update
from sqlalchemy.orm import Session

from app import clock
from app.config import settings
from app.errors import not_found
from app.models import (
    AppUser,
    Branch,
    Certificate,
    ElmaRelease,
    Job,
    Module,
    Region,
    TestAttempt,
    certificate_number_seq,
)
from app.models.enums import CertificateKind, JobKind, JobLane
from app.services import access, audit
from app.worker import runner

# No 0/O or 1/I: the code is printed and may be typed in by hand.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 10


class CertStatus(StrEnum):
    valid = "valid"
    recert_required = "recert_required"
    superseded = "superseded"
    missing = "missing"


# --- status -----------------------------------------------------------------------------------


def module_status(cert: Certificate | None, now: datetime) -> CertStatus:
    if cert is None:
        return CertStatus.missing
    if cert.superseded_at is not None:
        return CertStatus.superseded
    if cert.recert_due_at is not None and cert.recert_due_at <= now:
        return CertStatus.recert_required
    return CertStatus.valid


def current_module_certs(
    db: Session, user_ids: Iterable[int], module_ids: Iterable[int] | None = None
) -> dict[tuple[int, int], Certificate]:
    """(user_id, module_id) → the certificate not yet superseded."""
    stmt = select(Certificate).where(
        Certificate.kind == CertificateKind.module,
        Certificate.superseded_at.is_(None),
        Certificate.user_id.in_(list(user_ids) or [0]),
    )
    if module_ids is not None:
        stmt = stmt.where(Certificate.module_id.in_(list(module_ids) or [0]))
    return {(c.user_id, c.module_id): c for c in db.scalars(stmt)}


def current_operator_certs(
    db: Session, user_ids: Iterable[int], now: datetime
) -> dict[int, tuple[Certificate, CertStatus]]:
    """user_id → (operator certificate not yet superseded, its status)."""
    certs = list(
        db.scalars(
            select(Certificate).where(
                Certificate.kind == CertificateKind.operator,
                Certificate.superseded_at.is_(None),
                Certificate.user_id.in_(list(user_ids) or [0]),
            )
        )
    )
    covered_ids = {cid for c in certs for cid in c.covers}
    rows = db.scalars(select(Certificate).where(Certificate.id.in_(covered_ids or [0])))
    covered = {c.id: c for c in rows}
    out = {}
    for cert in certs:
        parts = [covered.get(cid) for cid in cert.covers]
        ok = all(module_status(p, now) == CertStatus.valid for p in parts)
        out[cert.user_id] = (cert, CertStatus.valid if ok else CertStatus.recert_required)
    return out


def renewal_date(db: Session, operator: Certificate | None) -> datetime | None:
    """Earliest "recertify by" date among the certificates an operator certificate covers."""
    if operator is None:
        return None
    dates = db.scalars(
        select(Certificate.recert_due_at).where(
            Certificate.id.in_(operator.covers or [0]), Certificate.recert_due_at.is_not(None)
        )
    ).all()
    return min(dates) if dates else None


def certificate_status(db: Session, cert: Certificate, now: datetime) -> CertStatus:
    if cert.kind == CertificateKind.module or cert.superseded_at is not None:
        return module_status(cert, now)
    return current_operator_certs(db, [cert.user_id], now)[cert.user_id][1]


# --- issuing ----------------------------------------------------------------------------------


def _number(db: Session, issued_at: datetime) -> str:
    n = db.scalar(select(certificate_number_seq.next_value()))
    return f"YO-{clock.local_date(issued_at).year}-{n:06d}"


def _verify_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _snapshot(db: Session, user: AppUser, modules: list[tuple[Module, str | None]]) -> dict:
    branch = db.get(Branch, user.branch_id) if user.branch_id else None
    region = db.get(Region, branch.region_id) if branch else None

    def ref(row: Branch | Region | None) -> dict[str, str] | None:
        return {"code": row.code, "name_uz": row.name_uz, "name_ru": row.name_ru} if row else None

    return {
        "holder": {"full_name": user.full_name, "employee_id": user.employee_id},
        "branch": ref(branch),
        "region": ref(region),
        "modules": [
            {
                "id": m.id, "code": m.code, "type": m.type.value, "title_uz": m.title_uz,
                "title_ru": m.title_ru, "release": release_code,
            }  # fmt: skip
            for m, release_code in modules
        ],
        "signatory": settings.cert_signatory_name,
    }


def _issue(db: Session, user: AppUser, kind: CertificateKind, now: datetime, **values: Any):
    """Insert a certificate and supersede the holder's current one of the same kind/module."""
    previous = db.scalar(
        select(Certificate)
        .where(
            Certificate.user_id == user.id,
            Certificate.kind == kind,
            Certificate.module_id.is_(None)
            if kind == CertificateKind.operator
            else Certificate.module_id == values["module_id"],
            Certificate.superseded_at.is_(None),
        )
        .with_for_update()
    )
    cert = Certificate(
        number=_number(db, now), verify_code=_verify_code(), kind=kind, user_id=user.id,
        issued_at=now, **values,
    )  # fmt: skip
    db.add(cert)
    db.flush()
    if previous is not None:
        previous.superseded_at = now
        previous.superseded_by_id = cert.id
    audit.record(
        db, "cert.issued", target_user_id=user.id, entity="certificate", entity_id=cert.id,
        data={"number": cert.number, "kind": kind.value, "module_id": cert.module_id},
    )  # fmt: skip
    db.flush()
    return cert


def issue_module(db: Session, attempt: TestAttempt, now: datetime) -> Certificate:
    """A passed test: new module certificate, then the operator certificate is re-evaluated."""
    user = db.get(AppUser, attempt.user_id)
    module = db.get(Module, attempt.module_id)
    release = db.get(ElmaRelease, attempt.release_id)
    recert_due_at = None
    if module.current_release_id != attempt.release_id:
        # A release replaced lessons while this attempt was running: the certificate is
        # on the older content, exactly as if it had existed when the release went out.
        current = db.get(ElmaRelease, module.current_release_id)
        recert_due_at = now + timedelta(days=current.transition_days)
    cert = _issue(
        db, user, CertificateKind.module, now, module_id=module.id, release_id=release.id,
        attempt_id=attempt.id, score_pct=attempt.score_pct, recert_due_at=recert_due_at,
        snapshot=_snapshot(db, user, [(module, release.code)]),
    )  # fmt: skip
    evaluate_operator(db, user, now)
    return cert


def evaluate_operator(db: Session, user: AppUser, now: datetime) -> Certificate | None:
    """Issue or reissue the operator certificate when due; returns the new one, if any."""
    # One evaluation per learner at a time (two passes at once, or a pass during a job).
    db.scalar(select(AppUser.id).where(AppUser.id == user.id).with_for_update())
    assigned = access.assigned_modules(db, user)
    if not assigned:
        return None
    certs = current_module_certs(db, [user.id], [m.id for m in assigned])
    covered = [(m, certs.get((user.id, m.id))) for m in assigned]
    if any(module_status(c, now) != CertStatus.valid for _, c in covered):
        return None  # not complete: an existing operator certificate stays as it is
    ids = sorted(c.id for _, c in covered)
    current = current_operator_certs(db, [user.id], now).get(user.id)
    if current is not None and sorted(current[0].covers) == ids:
        return None
    codes = dict(db.execute(select(ElmaRelease.id, ElmaRelease.code)).all())
    return _issue(
        db, user, CertificateKind.operator, now, covers=ids,
        snapshot=_snapshot(db, user, [(m, codes.get(c.release_id)) for m, c in covered]),
    )  # fmt: skip


def enqueue_evaluation(db: Session, user_ids: Iterable[int], actor_id: int | None) -> Job | None:
    """Assignments changed for these users: re-evaluate their operator certificates."""
    ids = sorted(set(user_ids))
    if not ids:
        return None
    return runner.enqueue(
        db, JobKind.operator_cert_eval, JobLane.general, {"user_ids": ids}, actor_id
    )


def run_evaluation(db: Session, job: Job) -> dict[str, int]:
    issued = 0
    for user_id in job.payload.get("user_ids", []):
        user = db.get(AppUser, user_id)
        if user is not None and evaluate_operator(db, user, clock.utcnow()) is not None:
            issued += 1
    return {"evaluated": len(job.payload.get("user_ids", [])), "issued": issued}


# --- releases ---------------------------------------------------------------------------------


def flag_recert(db: Session, release: ElmaRelease, module_ids: list[int], now: datetime) -> int:
    """Release publish (rule 9 step 4): certificates in the affected modules need renewal.

    An earlier "recertify by" date is never pushed back by a later release.
    """
    due = now + timedelta(days=release.transition_days)
    result = db.execute(
        update(Certificate)
        .where(
            Certificate.kind == CertificateKind.module,
            Certificate.module_id.in_(module_ids or [0]),
            Certificate.superseded_at.is_(None),
            Certificate.release_id.is_distinct_from(release.id),
            or_(Certificate.recert_due_at.is_(None), Certificate.recert_due_at > due),
        )
        .values(recert_due_at=due)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount


def impact(db: Session, module_ids: Iterable[int]) -> dict[int, tuple[int, int]]:
    """module_id → (certificates, learners) that a release touching it sends to renewal."""
    rows = db.execute(
        select(Certificate.module_id, func.count(), func.count(distinct(Certificate.user_id)))
        .where(
            Certificate.kind == CertificateKind.module,
            Certificate.module_id.in_(list(module_ids) or [0]),
            Certificate.superseded_at.is_(None),
        )
        .group_by(Certificate.module_id)
    ).all()
    return {module_id: (certs, learners) for module_id, certs, learners in rows}


# --- lookups ----------------------------------------------------------------------------------


def verify(db: Session, number: str, code: str) -> Certificate:
    """Public check: the number alone reveals nothing, the printed code is required too."""
    cert = db.scalar(select(Certificate).where(Certificate.number == number.strip().upper()))
    supplied = code.strip().upper().encode()
    if cert is None or not hmac.compare_digest(cert.verify_code.encode(), supplied):
        raise not_found("certificate")
    return cert


def verify_url(cert: Certificate) -> str:
    return f"{settings.public_base_url}/verify/{cert.number}?c={cert.verify_code}"
