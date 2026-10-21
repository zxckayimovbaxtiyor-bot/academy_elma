from __future__ import annotations

from pydantic import BaseModel, Field

from app.models import AppUser
from app.models.enums import AccessRole, Language
from app.schemas.common import Ref


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)  # employee_id
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class MePatchIn(BaseModel):
    preferred_language: Language


class MeOut(BaseModel):
    id: int
    employee_id: str
    full_name: str
    access_role: AccessRole
    preferred_language: Language
    must_change_password: bool
    branch: Ref | None
    region: Ref | None
    job_role: Ref | None

    @classmethod
    def of(cls, user: AppUser) -> MeOut:
        branch = user.branch
        return cls(
            id=user.id,
            employee_id=user.employee_id,
            full_name=user.full_name,
            access_role=user.access_role,
            preferred_language=user.preferred_language,
            must_change_password=user.must_change_password,
            branch=Ref.model_validate(branch) if branch else None,
            region=Ref.model_validate(branch.region) if branch else None,
            job_role=Ref.model_validate(user.job_role) if user.job_role else None,
        )
