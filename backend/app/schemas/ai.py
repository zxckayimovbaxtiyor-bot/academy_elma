from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models import Job
from app.models.enums import JobKind, JobStatus

DraftType = Literal["single", "multiple", "ordering"]  # screenshot questions are manual


class AiStatusOut(BaseModel):
    enabled: bool  # False: the UI hides the feature
    model: str | None


class DraftRequestIn(BaseModel):
    source: Literal["transcript", "text"] = "transcript"
    text: str | None = Field(None, max_length=60_000)  # pasted source when source=text
    count: int = Field(10, ge=1, le=30)
    types: list[DraftType] = Field(default_factory=lambda: ["single", "multiple", "ordering"])
    include_lesson_pdf: bool = False  # the lesson's reference PDFs as documents
    reference_text: str | None = Field(None, max_length=60_000)

    @field_validator("types")
    @classmethod
    def _types(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one type")
        return sorted(set(value), key=value.index)


class JobOut(BaseModel):
    id: int
    kind: JobKind
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: dict[str, Any] | None  # failed jobs: {"error": {"code", "params"}}

    @classmethod
    def of(cls, job: Job) -> JobOut:
        return cls(
            id=job.id, kind=job.kind, status=job.status, created_at=job.created_at,
            started_at=job.started_at, finished_at=job.finished_at, result=job.result,
        )  # fmt: skip
