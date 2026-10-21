from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Response
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app import clock
from app.config import settings
from app.models import AppUser, UserSession

COOKIE_NAME = "ya_session"
# Avoid a write on every request (heartbeats arrive every 15 s).
_TOUCH_EVERY = timedelta(seconds=60)


@dataclass
class AuthContext:
    user: AppUser
    session: UserSession


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: AppUser) -> str:
    token = secrets.token_urlsafe(32)
    now = clock.utcnow()
    db.add(
        UserSession(
            token_hash=_hash(token),
            user_id=user.id,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(hours=settings.session_absolute_hours),
        )
    )
    user.last_seen_at = now
    return token


def resolve_session(db: Session, token: str) -> AuthContext | None:
    """Valid session for the cookie token, refreshing its idle timer; None if expired."""
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == _hash(token)))
    if sess is None:
        return None
    now = clock.utcnow()
    idle_limit = timedelta(minutes=settings.session_idle_minutes)
    if sess.expires_at <= now or sess.last_used_at + idle_limit <= now:
        db.delete(sess)
        db.commit()
        return None
    user = db.get(AppUser, sess.user_id)
    if user is None or not user.is_active:
        return None
    if now - sess.last_used_at >= _TOUCH_EVERY:
        sess.last_used_at = now
        user.last_seen_at = now
        db.commit()
    return AuthContext(user=user, session=sess)


def revoke_token(db: Session, token: str) -> None:
    db.execute(delete(UserSession).where(UserSession.token_hash == _hash(token)))


def revoke_user_sessions(db: Session, user_id: int, keep_session_id: int | None = None) -> None:
    stmt = delete(UserSession).where(UserSession.user_id == user_id)
    if keep_session_id is not None:
        stmt = stmt.where(UserSession.id != keep_session_id)
    db.execute(stmt)


def purge_expired(db: Session) -> int:
    now = clock.utcnow()
    idle_cutoff = now - timedelta(minutes=settings.session_idle_minutes)
    result = db.execute(
        delete(UserSession).where(
            or_(UserSession.expires_at <= now, UserSession.last_used_at <= idle_cutoff)
        )
    )
    return result.rowcount or 0


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_absolute_hours * 3600,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, samesite="strict", secure=settings.cookie_secure
    )
