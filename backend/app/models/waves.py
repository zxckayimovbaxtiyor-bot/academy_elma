from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt, IdPk


class Wave(Base):
    __tablename__ = "wave"

    id: Mapped[IdPk]
    name_uz: Mapped[str] = mapped_column(String(200))
    name_ru: Mapped[str] = mapped_column(String(200))
    training_start: Mapped[date] = mapped_column(Date)
    deadline: Mapped[date] = mapped_column(Date)  # certification deadline
    go_live: Mapped[date] = mapped_column(Date)  # Single Window go-live for these branches
    created_at: Mapped[CreatedAt]


class WaveBranch(Base):
    """A branch belongs to at most one wave (it goes live once)."""

    __tablename__ = "wave_branch"

    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), primary_key=True
    )
    wave_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("wave.id", ondelete="CASCADE"), index=True
    )


class WaveModuleRole(Base):
    """Role x module matrix of a wave. Core is implicit for every role and never stored."""

    __tablename__ = "wave_module_role"

    wave_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("wave.id", ondelete="CASCADE"), primary_key=True
    )
    module_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("module.id"), primary_key=True)
    job_role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("job_role.id"), primary_key=True
    )
