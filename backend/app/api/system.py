from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db import get_db
from app.models import AppUser
from app.errors import AppError
from app.services import media_access

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/internal/media-auth", status_code=204)
def media_auth(
    x_original_uri: str = Header(""),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    """nginx supplies the original resource URI on every protected file request."""
    if not media_access.allowed(db, user, x_original_uri):
        raise AppError(403, "auth.forbidden")
    return Response(status_code=204)
