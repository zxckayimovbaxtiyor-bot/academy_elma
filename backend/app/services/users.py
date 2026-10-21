from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.auth import passwords
from app.models import AppUser, JobRole
from app.models.enums import AccessRole

EMPLOYEE_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")
# Roles only granted in the admin UI; the HR import never changes them.
STAFF_ROLES = {AccessRole.methodologist, AccessRole.admin}


def normalize_employee_id(raw: str) -> str:
    return raw.strip().upper()


def access_role_for(job_role: JobRole | None, current: AccessRole | None = None) -> AccessRole:
    """Permission level the HR file implies; methodologist/admin are never touched by it."""
    if current in STAFF_ROLES:
        return current
    if job_role is not None and job_role.is_branch_head:
        return AccessRole.branch_head
    return AccessRole.learner


def issue_temp_password(user: AppUser) -> str:
    """Give the user a new one-time password; they must change it at next login."""
    temp = passwords.generate_temp_password()
    user.password_hash = passwords.hash_temp_password(temp)
    user.must_change_password = True
    user.failed_logins = 0
    user.locked_until = None
    return temp


def get_user_or_none(db: Session, user_id: int) -> AppUser | None:
    return db.get(AppUser, user_id)
