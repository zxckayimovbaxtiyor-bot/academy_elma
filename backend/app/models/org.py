from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdPk


class Region(Base):
    __tablename__ = "region"

    id: Mapped[IdPk]
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name_uz: Mapped[str] = mapped_column(String(120))
    name_ru: Mapped[str] = mapped_column(String(120))


class Branch(Base):
    __tablename__ = "branch"

    id: Mapped[IdPk]
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name_uz: Mapped[str] = mapped_column(String(200))
    name_ru: Mapped[str] = mapped_column(String(200))
    region_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("region.id"), index=True)

    region: Mapped[Region] = relationship()


class JobRole(Base):
    """Job position from the HR file (Menejer, Anderrayter, ...); drives module assignment."""

    __tablename__ = "job_role"

    id: Mapped[IdPk]
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name_uz: Mapped[str] = mapped_column(String(120))
    name_ru: Mapped[str] = mapped_column(String(120))
    is_branch_head: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
