"""Authentication behind one interface so LDAP/AD can be added later without touching callers.

Only the local backend exists. An LDAP backend would verify the password against
the directory and map the account to ``app_user`` by employee_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth import passwords
from app.config import settings
from app.models import AppUser
from app.services.users import normalize_employee_id


@dataclass
class AuthOutcome:
    user: AppUser | None
    error: str | None = None  # "auth.invalid_credentials" | "auth.locked"
    locked_until: datetime | None = None


class AuthBackend(Protocol):
    def authenticate(self, db: Session, username: str, password: str) -> AuthOutcome: ...


class LocalAuthBackend:
    """employee_id + argon2id password, with an account lock after repeated failures."""

    def authenticate(self, db: Session, username: str, password: str) -> AuthOutcome:
        employee_id = normalize_employee_id(username)
        user = db.scalar(
            select(AppUser).where(AppUser.employee_id == employee_id).with_for_update()
        )
        if user is None or not user.is_active:
            passwords.verify_password(passwords.dummy_hash(), password)
            return AuthOutcome(None, "auth.invalid_credentials")

        now = clock.utcnow()
        if user.locked_until is not None and user.locked_until > now:
            return AuthOutcome(None, "auth.locked", user.locked_until)

        if not passwords.verify_password(user.password_hash, password):
            user.failed_logins += 1
            if user.failed_logins >= settings.login_max_failures:
                user.failed_logins = 0
                user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            return AuthOutcome(None, "auth.invalid_credentials")

        user.failed_logins = 0
        user.locked_until = None
        # A temporary password is about to be replaced anyway.
        if not user.must_change_password and passwords.needs_rehash(user.password_hash):
            user.password_hash = passwords.hash_password(password)
        return AuthOutcome(user)


def get_auth_backend() -> AuthBackend:
    return LocalAuthBackend()
