from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.auth.sessions import COOKIE_NAME, AuthContext, resolve_session
from app.db import get_db
from app.errors import AppError
from app.models import AppUser
from app.models.enums import AccessRole


def current_context(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    token = request.cookies.get(COOKIE_NAME)
    ctx = resolve_session(db, token) if token else None
    if ctx is None:
        raise AppError(401, "auth.required")
    return ctx


def current_user_allow_password_change(ctx: AuthContext = Depends(current_context)) -> AppUser:
    """For the few endpoints usable before a temporary password has been replaced."""
    return ctx.user


def current_user(ctx: AuthContext = Depends(current_context)) -> AppUser:
    if ctx.user.must_change_password:
        raise AppError(403, "auth.password_change_required")
    return ctx.user


def require_roles(*roles: AccessRole) -> Callable[..., AppUser]:
    """Admin passes every role check ("everything" in the role spec)."""
    allowed = set(roles) | {AccessRole.admin}

    def dependency(user: AppUser = Depends(current_user)) -> AppUser:
        if user.access_role not in allowed:
            raise AppError(403, "auth.forbidden")
        return user

    return dependency
