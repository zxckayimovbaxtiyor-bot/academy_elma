from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt, IdPk, pg_enum
from app.models.enums import AccessRole, Language
from app.models.org import Branch, JobRole


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[IdPk]
    employee_id: Mapped[str] = mapped_column(String(32), unique=True)  # also the login
    full_name: Mapped[str] = mapped_column(String(200))
    branch_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("branch.id"), index=True)
    job_role_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("job_role.id"), index=True
    )
    access_role: Mapped[AccessRole] = mapped_column(
        pg_enum(AccessRole, "access_role"), default=AccessRole.learner
    )
    preferred_language: Mapped[Language] = mapped_column(
        pg_enum(Language, "language"), default=Language.uz
    )
    password_hash: Mapped[str] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    branch: Mapped[Branch | None] = relationship()
    job_role: Mapped[JobRole | None] = relationship()


class UserSession(Base):
    """Server-side session; the cookie holds a random token, only its SHA-256 is stored."""

    __tablename__ = "user_session"

    id: Mapped[IdPk]
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserImport(Base):
    """A validated CSV waiting for (or after) commit; see services/csv_import.py."""

    __tablename__ = "user_import"

    id: Mapped[IdPk]
    uploaded_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[CreatedAt]
    total_rows: Mapped[int] = mapped_column(Integer)
    valid_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_count: Mapped[int | None] = mapped_column(Integer)
    updated_count: Mapped[int | None] = mapped_column(Integer)


class AuditEvent(Base):
    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_event_target_at", "target_user_id", "at"),
        Index("ix_audit_event_entity", "entity", "entity_id"),
    )

    id: Mapped[IdPk]
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    action: Mapped[str] = mapped_column(String(64))
    target_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("app_user.id"))
    entity: Mapped[str | None] = mapped_column(String(48))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
