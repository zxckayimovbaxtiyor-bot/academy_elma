from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.enums import ModuleType
from app.schemas.common import Ref


class WaveStatus(StrEnum):
    planned = "planned"  # training has not started
    active = "active"  # from training start until go-live
    completed = "completed"  # after go-live


class WaveIn(BaseModel):
    name_uz: str = Field(min_length=1, max_length=200)
    name_ru: str = Field(min_length=1, max_length=200)
    training_start: date
    deadline: date  # certification deadline
    go_live: date


class WavePatch(BaseModel):
    name_uz: str | None = Field(None, min_length=1, max_length=200)
    name_ru: str | None = Field(None, min_length=1, max_length=200)
    training_start: date | None = None
    deadline: date | None = None
    go_live: date | None = None


class WaveOut(BaseModel):
    id: int
    name_uz: str
    name_ru: str
    training_start: date
    deadline: date
    go_live: date
    status: WaveStatus
    branches: int
    learners: int
    certified: int
    certified_pct: int


class BranchesIn(BaseModel):
    branch_ids: list[int] = Field(max_length=5000)


class AssignmentIn(BaseModel):
    job_role_id: int
    module_id: int


class AssignmentsIn(BaseModel):
    """Product modules per job role. Core is implicit for every role and is never sent."""

    items: list[AssignmentIn] = Field(max_length=1000)


class WaveBranchOut(Ref):
    learners: int


class MatrixRoleOut(Ref):
    learners: int  # learners with this job role in the wave's branches


class MatrixModuleOut(BaseModel):
    id: int
    code: str
    type: ModuleType
    title_uz: str
    title_ru: str


class WaveDetail(WaveOut):
    branch_list: list[WaveBranchOut]
    roles: list[MatrixRoleOut]
    modules: list[MatrixModuleOut]  # Core (always on) and the product modules
    assignments: list[AssignmentIn]
