from __future__ import annotations

import enum
from datetime import datetime
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, Enum, Identity, MetaData, func
from sqlalchemy.orm import DeclarativeBase, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


IdPk = Annotated[int, mapped_column(BigInteger, Identity(), primary_key=True)]
CreatedAt = Annotated[
    datetime, mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
]
Timestamp = Annotated[datetime, mapped_column(DateTime(timezone=True))]


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """Native PostgreSQL enum that stores the lowercase values, not the member names."""
    return Enum(enum_cls, name=name, values_callable=lambda members: [m.value for m in members])
