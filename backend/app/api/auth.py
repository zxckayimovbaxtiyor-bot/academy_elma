from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.auth import passwords, sessions
from app.auth.backend import AuthBackend, get_auth_backend
from app.auth.deps import current_context, current_user_allow_password_change
from app.auth.sessions import COOKIE_NAME, AuthContext
from app.db import get_db
from app.errors import AppError
from app.models import AppUser
from app.schemas.auth import ChangePasswordIn, LoginIn, MeOut, MePatchIn
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=MeOut)
def login(
    body: LoginIn,
    response: Response,
    db: Session = Depends(get_db),
    backend: AuthBackend = Depends(get_auth_backend),
) -> MeOut:
    outcome = backend.authenticate(db, body.username, body.password)
    if outcome.user is None:
        db.commit()  # keep the failure counter / lock
        if outcome.error == "auth.locked" and outcome.locked_until is not None:
            raise AppError(403, "auth.locked", {"until": outcome.locked_until.isoformat()})
        raise AppError(401, "auth.invalid_credentials")
    token = sessions.create_session(db, outcome.user)
    db.commit()
    sessions.set_session_cookie(response, token)
    return MeOut.of(outcome.user)


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        sessions.revoke_token(db, token)
        db.commit()
    resp = Response(status_code=204)
    sessions.clear_session_cookie(resp)
    return resp


@router.get("/me", response_model=MeOut)
def me(user: AppUser = Depends(current_user_allow_password_change)) -> MeOut:
    return MeOut.of(user)


@router.patch("/me", response_model=MeOut)
def patch_me(
    body: MePatchIn,
    user: AppUser = Depends(current_user_allow_password_change),
    db: Session = Depends(get_db),
) -> MeOut:
    user.preferred_language = body.preferred_language
    db.commit()
    return MeOut.of(user)


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordIn,
    ctx: AuthContext = Depends(current_context),
    db: Session = Depends(get_db),
) -> Response:
    user = ctx.user
    if not passwords.verify_password(user.password_hash, body.current_password):
        raise AppError(400, "password.current_invalid")
    problem = passwords.new_password_problem(body.new_password, user.employee_id)
    if problem:
        raise AppError(400, problem)
    if body.new_password == body.current_password:
        raise AppError(400, "password.same_as_current")
    user.password_hash = passwords.hash_password(body.new_password)
    user.must_change_password = False
    sessions.revoke_user_sessions(db, user.id, keep_session_id=ctx.session.id)
    audit.record(db, "user.password_changed", actor_id=user.id, target_user_id=user.id)
    db.commit()
    return Response(status_code=204)
