"""Loopback-only development server for the built UI, API and protected media.

The Docker deployment continues to use app.main and nginx.
"""

from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.config import settings
from app.main import create_app
from app.db import get_db
from app.errors import AppError
from app.models import AppUser
from app.services import media_access

app = create_app()
dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
media = Path(settings.media_root).resolve()
app.mount("/assets", StaticFiles(directory=dist / "assets"), name="local-assets")


@app.get("/media/{folder}/{filename:path}", include_in_schema=False)
def media_file(folder: str, filename: str, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    target = (media / folder / filename).resolve()
    if folder not in {"hls", "vtt", "pdf", "img"} or not target.is_relative_to(media / folder):
        raise HTTPException(404)
    if not target.is_file():
        raise HTTPException(404)
    if not media_access.allowed(db, user, f"/media/{folder}/{filename}"):
        raise AppError(403, "auth.forbidden")
    types = {".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t", ".vtt": "text/vtt"}
    return FileResponse(target, media_type=types.get(target.suffix),
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path == "api" or path.startswith(("api/", "media/", "assets/")):
        raise HTTPException(404)
    if path == "favicon.svg":
        return FileResponse(dist / "favicon.svg")
    return FileResponse(dist / "index.html")
