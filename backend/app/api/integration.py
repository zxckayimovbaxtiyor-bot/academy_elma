"""Access gate for Single Window roles (rule 13): read-only, behind an API key."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.config import settings
from app.db import get_db
from app.errors import AppError, not_found
from app.models import AppUser, ElmaRelease, Module
from app.models.enums import ModuleType
from app.schemas.certificates import CertificationStatusOut, GateModuleOut, GateOperatorOut
from app.services import access, certificates
from app.services.certificates import CertStatus
from app.services.users import normalize_employee_id

router = APIRouter(tags=["integration"])


def api_key(x_api_key: str | None = Header(None)) -> None:
    """Keys from CERT_STATUS_API_KEYS; every key is compared, in constant time."""
    supplied = (x_api_key or "").encode()
    matched = False
    for key in settings.cert_status_api_keys:
        matched |= hmac.compare_digest(supplied, key.encode())
    if not supplied or not matched:
        raise AppError(401, "api_key.invalid")


@router.get(
    "/certification-status",
    response_model=CertificationStatusOut,
    dependencies=[Depends(api_key)],
)
def certification_status(
    employee_id: str = Query(min_length=1, max_length=64), db: Session = Depends(get_db)
) -> CertificationStatusOut:
    user = db.scalar(
        select(AppUser).where(AppUser.employee_id == normalize_employee_id(employee_id))
    )
    if user is None:
        raise not_found("user")
    now = clock.utcnow()
    assigned = {m.id for m in access.assigned_modules(db, user)}
    modules = db.scalars(
        select(Module).where(Module.type != ModuleType.faq).order_by(Module.sort, Module.id)
    ).all()
    certs = certificates.current_module_certs(db, [user.id])
    codes = dict(db.execute(select(ElmaRelease.id, ElmaRelease.code)).all())
    items = []
    for m in modules:
        cert = certs.get((user.id, m.id))
        items.append(
            GateModuleOut(
                code=m.code, type=m.type, title_uz=m.title_uz, title_ru=m.title_ru,
                assigned=m.id in assigned, status=certificates.module_status(cert, now),
                number=cert.number if cert else None,
                release=codes.get(cert.release_id) if cert else None,
                issued_at=cert.issued_at if cert else None,
                recert_due_at=cert.recert_due_at if cert else None,
            )
        )  # fmt: skip
    operator, status = certificates.current_operator_certs(db, [user.id], now).get(
        user.id, (None, CertStatus.missing)
    )
    return CertificationStatusOut(
        employee_id=user.employee_id,
        full_name=user.full_name,
        is_active=user.is_active,
        operator=GateOperatorOut(
            status=status,
            number=operator.number if operator else None,
            issued_at=operator.issued_at if operator else None,
            recert_due_at=certificates.renewal_date(db, operator),
        ),
        modules=items,
        checked_at=now,
    )
