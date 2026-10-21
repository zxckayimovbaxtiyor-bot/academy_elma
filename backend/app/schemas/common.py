from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Ref(BaseModel):
    """A named reference shown in both languages (branch, region, job role)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_uz: str
    name_ru: str


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
