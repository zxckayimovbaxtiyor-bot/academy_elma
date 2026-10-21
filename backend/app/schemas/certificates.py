from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models import Certificate
from app.models.enums import CertificateKind, ModuleType
from app.services import certificates
from app.services.certificates import CertStatus


class CertModuleOut(BaseModel):
    """A module as printed on the certificate (from its snapshot)."""

    code: str
    title_uz: str
    title_ru: str
    release: str | None


class PlaceOut(BaseModel):
    code: str
    name_uz: str
    name_ru: str


class CertificateOut(BaseModel):
    number: str
    kind: CertificateKind
    status: CertStatus
    module_id: int | None
    modules: list[CertModuleOut]  # module certificate: one; operator: the ones it covers
    score_pct: float | None
    issued_at: datetime
    recert_due_at: datetime | None  # "recertify by" (module certificates)
    superseded_at: datetime | None
    pdf_url: str
    verify_url: str  # what the QR code on the PDF opens (number + printed code)

    @classmethod
    def of(cls, cert: Certificate, status: CertStatus) -> CertificateOut:
        return cls(
            number=cert.number, kind=cert.kind, status=status, module_id=cert.module_id,
            modules=[CertModuleOut(**_module(m)) for m in cert.snapshot.get("modules", [])],
            score_pct=cert.score_pct, issued_at=cert.issued_at,
            recert_due_at=cert.recert_due_at, superseded_at=cert.superseded_at,
            pdf_url=f"/api/v1/me/certificates/{cert.number}/pdf",
            verify_url=certificates.verify_url(cert),
        )  # fmt: skip


def _module(m: dict) -> dict:
    return {k: m.get(k) for k in ("code", "title_uz", "title_ru", "release")}


class VerifyOut(BaseModel):
    """Public verification page: what the certificate says and whether it still holds."""

    number: str
    kind: CertificateKind
    status: CertStatus
    holder: str
    branch: PlaceOut | None
    region: PlaceOut | None
    modules: list[CertModuleOut]
    issued_at: datetime
    recert_due_at: datetime | None
    superseded_at: datetime | None

    @classmethod
    def of(cls, cert: Certificate, status: CertStatus) -> VerifyOut:
        snap = cert.snapshot
        return cls(
            number=cert.number, kind=cert.kind, status=status,
            holder=snap["holder"]["full_name"],
            branch=PlaceOut(**snap["branch"]) if snap.get("branch") else None,
            region=PlaceOut(**snap["region"]) if snap.get("region") else None,
            modules=[CertModuleOut(**_module(m)) for m in snap.get("modules", [])],
            issued_at=cert.issued_at, recert_due_at=cert.recert_due_at,
            superseded_at=cert.superseded_at,
        )  # fmt: skip


class GateModuleOut(BaseModel):
    code: str
    type: ModuleType
    title_uz: str
    title_ru: str
    assigned: bool
    status: CertStatus  # valid · recert_required · missing
    number: str | None
    release: str | None
    issued_at: datetime | None
    recert_due_at: datetime | None


class GateOperatorOut(BaseModel):
    status: CertStatus  # valid · recert_required · missing
    number: str | None
    issued_at: datetime | None
    recert_due_at: datetime | None  # earliest renewal date among the covered certificates


class CertificationStatusOut(BaseModel):
    """Access gate (rule 13): read-only, for the team that grants Single Window roles."""

    employee_id: str
    full_name: str
    is_active: bool
    operator: GateOperatorOut
    modules: list[GateModuleOut]
    checked_at: datetime
