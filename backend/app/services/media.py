"""Files under MEDIA_ROOT.

Database rows store paths relative to MEDIA_ROOT. nginx serves hls/, vtt/, pdf/ and
img/ at /media/... to logged-in users; originals/ and tmp/ are never served.
Uploaded files get a random name and are never modified in place, so a browser
cache can't serve an outdated subtitle or PDF.
"""

from __future__ import annotations

import os
import secrets
import shutil
import uuid
from pathlib import Path

from app.config import settings


def root() -> Path:
    return Path(settings.media_root)


def abs_path(rel: str) -> Path:
    return root() / rel


def url(rel: str | None) -> str | None:
    return f"/media/{rel}" if rel else None


def original_path(asset_id: uuid.UUID) -> Path:
    return root() / "originals" / f"{asset_id}.mp4"


def hls_dir(asset_id: uuid.UUID) -> Path:
    return root() / "hls" / str(asset_id)


def hls_url(asset_id: uuid.UUID) -> str:
    return f"/media/hls/{asset_id}/master.m3u8"


def new_tmp_path() -> Path:
    folder = root() / "tmp"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{uuid.uuid4()}.part"


def write_new(folder: str, stem: str, suffix: str, data: bytes) -> str:
    """Write a new immutable file and return its path relative to MEDIA_ROOT."""
    rel = f"{folder}/{stem}-{secrets.token_hex(6)}{suffix}"
    target = abs_path(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return rel


def move_into_originals(tmp: Path, asset_id: uuid.UUID) -> None:
    target = original_path(asset_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, target)


def delete_rel(rel: str | None) -> None:
    if rel:
        abs_path(rel).unlink(missing_ok=True)


def delete_asset_files(asset_id: uuid.UUID) -> None:
    original_path(asset_id).unlink(missing_ok=True)
    shutil.rmtree(hls_dir(asset_id), ignore_errors=True)
