from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Sequence,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdPk, pg_enum
from app.models.enums import CertificateKind

# Feeds the running part of certificate numbers (YO-2026-000123).
certificate_number_seq = Sequence("certificate_number_seq", metadata=Base.metadata)


class Certificate(Base):
    __tablename__ = "certificate"
    __table_args__ = (
        Index(
            "ix_certificate_current",
            "user_id",
            "module_id",
            postgresql_where=text("superseded_at IS NULL"),
        ),
        CheckConstraint("(kind = 'module') = (module_id IS NOT NULL)", name="module_matches_kind"),
    )

    id: Mapped[IdPk]
    number: Mapped[str] = mapped_column(String(32), unique=True)
    # Printed on the certificate and embedded in the QR link; stops enumeration of numbers.
    verify_code: Mapped[str] = mapped_column(String(16))
    kind: Mapped[CertificateKind] = mapped_column(pg_enum(CertificateKind, "certificate_kind"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"), index=True)
    module_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("module.id"))
    release_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("elma_release.id"))
    attempt_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("test_attempt.id"))
    score_pct: Mapped[float | None] = mapped_column(Float)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recert_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("certificate.id")
    )
    # Operator certificate: ids of the module certificates it was issued on.
    covers: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), default=list, server_default="{}"
    )
    # Holder, branch, modules and releases at issue time; the PDF is rendered from this.
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    pdf_path: Mapped[str | None] = mapped_column(String(255))
