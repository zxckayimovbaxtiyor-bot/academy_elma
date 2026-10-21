"""Certificates: the learner's own list and PDFs, and the public verification page."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth.deps import current_user
from app.db import get_db
from app.errors import not_found
from app.models import AppUser, Certificate
from app.pdf.certificate import render
from app.schemas.certificates import CertificateOut, VerifyOut
from app.services import certificates, media

router = APIRouter(tags=["certificates"])


@router.get("/me/certificates", response_model=list[CertificateOut])
def my_certificates(user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    """Current certificates first (newest on top), then the superseded ones."""
    rows = db.scalars(
        select(Certificate)
        .where(Certificate.user_id == user.id)
        .order_by(
            Certificate.superseded_at.is_not(None),
            Certificate.issued_at.desc(),
            Certificate.id.desc(),
        )
    )
    now = clock.utcnow()
    return [CertificateOut.of(c, certificates.certificate_status(db, c, now)) for c in rows]


@router.get("/me/certificates/{number}/pdf")
def certificate_pdf(
    number: str, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    cert = db.scalar(select(Certificate).where(Certificate.number == number))
    if cert is None or cert.user_id != user.id:
        raise not_found("certificate")
    path = media.abs_path(cert.pdf_path) if cert.pdf_path else None
    if path is not None and path.is_file():
        data = path.read_bytes()
    else:  # drawn on first download, then kept (the snapshot never changes)
        data = render(cert)
        cert.pdf_path = media.write_new("certs", cert.number, ".pdf", data)
        db.commit()
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{cert.number}.pdf"'},
    )


@router.get("/verify/{number}", response_model=VerifyOut)
def verify(
    number: str, c: str = Query("", max_length=32), db: Session = Depends(get_db)
) -> VerifyOut:
    """Public: needs the number and the printed code (numbers alone are sequential)."""
    cert = certificates.verify(db, number, c)
    return VerifyOut.of(cert, certificates.certificate_status(db, cert, clock.utcnow()))
