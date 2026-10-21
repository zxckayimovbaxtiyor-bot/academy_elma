from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_roles
from app.db import get_db
from app.models import AppUser, Branch, JobRole, Region
from app.schemas.common import Ref

router = APIRouter(prefix="/admin", tags=["admin: reference"])


class BranchOut(Ref):
    region_id: int


class JobRoleOut(Ref):
    is_branch_head: bool


@router.get("/regions", response_model=list[Ref])
def regions(db: Session = Depends(get_db), _: AppUser = Depends(require_roles())) -> list[Ref]:
    return [Ref.model_validate(r) for r in db.scalars(select(Region).order_by(Region.code))]


@router.get("/branches", response_model=list[BranchOut])
def branches(
    db: Session = Depends(get_db), _: AppUser = Depends(require_roles())
) -> list[BranchOut]:
    return [BranchOut.model_validate(b) for b in db.scalars(select(Branch).order_by(Branch.code))]


@router.get("/job-roles", response_model=list[JobRoleOut])
def job_roles(
    db: Session = Depends(get_db), _: AppUser = Depends(require_roles())
) -> list[JobRoleOut]:
    rows = db.scalars(select(JobRole).order_by(JobRole.sort, JobRole.code))
    return [JobRoleOut.model_validate(r) for r in rows]
