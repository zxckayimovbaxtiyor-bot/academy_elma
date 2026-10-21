"""MP4 → adaptive HLS (360p/480p/720p, H.264 + AAC) with ffmpeg, reporting progress.

One ffmpeg pass decodes once and encodes every rendition. Keyframes every 2 s,
aligned across renditions, let hls.js switch quality at any 6 s segment boundary.
The bitrates are capped for screen recordings and slow branch links.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app import clock
from app.models import Job, VideoAsset
from app.models.enums import JobKind, VideoStatus
from app.services import media
from app.worker.runner import HANDLERS


@dataclass(frozen=True)
class Rendition:
    height: int
    video_kbps: int
    max_kbps: int


LADDER = (Rendition(360, 300, 400), Rendition(480, 500, 700), Rendition(720, 900, 1200))
AUDIO_KBPS = 64
SEGMENT_S = 6
GOP_S = 2
MAX_DURATION_S = 3600
PROGRESS_EVERY_S = 2.0


class TranscodeError(Exception):
    """``str(exc)`` is a stable code shown in the admin UI (details go to the job log)."""


@dataclass(frozen=True)
class Probe:
    duration: float
    width: int
    height: int
    has_audio: bool


def probe(path: Path) -> Probe:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
         str(path)],
        capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    if proc.returncode != 0:
        raise TranscodeError("video.unreadable")
    info = json.loads(proc.stdout or "{}")
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise TranscodeError("video.no_video_stream")
    try:
        duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    except ValueError:
        duration = 0.0
    if duration <= 0:
        raise TranscodeError("video.unreadable")
    if duration > MAX_DURATION_S:
        raise TranscodeError("video.too_long")
    return Probe(
        duration=duration,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def ladder_for(height: int) -> tuple[Rendition, ...]:
    """Never upscale; a source below 360p still gets one (360p) rendition."""
    fitting = tuple(r for r in LADDER if r.height <= height)
    return fitting or LADDER[:1]


def build_command(src: Path, info: Probe) -> list[str]:
    """ffmpeg arguments; run with cwd = the output folder (master.m3u8 lands there)."""
    ladder = ladder_for(info.height)
    n = len(ladder)
    graph = f"[0:v]split={n}" + "".join(f"[s{i}]" for i in range(n)) + ";" + ";".join(
        f"[s{i}]scale=-2:{r.height}[v{i}]" for i, r in enumerate(ladder)
    )
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(src),
           "-filter_complex", graph]  # fmt: skip
    for i, r in enumerate(ladder):
        cmd += ["-map", f"[v{i}]", f"-c:v:{i}", "libx264", f"-b:v:{i}", f"{r.video_kbps}k",
                f"-maxrate:v:{i}", f"{r.max_kbps}k",
                f"-bufsize:v:{i}", f"{2 * r.max_kbps}k"]  # fmt: skip
        if info.has_audio:
            cmd += ["-map", "0:a:0"]
    if info.has_audio:
        cmd += ["-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-ac", "1", "-ar", "44100"]
    streams = " ".join(f"v:{i},a:{i}" if info.has_audio else f"v:{i}" for i in range(n))
    cmd += [
        "-preset", "veryfast", "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-force_key_frames", f"expr:gte(t,n_forced*{GOP_S})", "-sc_threshold", "0",
        "-f", "hls", "-hls_time", str(SEGMENT_S), "-hls_playlist_type", "vod",
        "-hls_flags", "independent_segments",
        "-hls_segment_filename", "v%v/seg_%04d.ts",
        "-master_pl_name", "master.m3u8",
        "-var_stream_map", streams,
        "-progress", "pipe:1", "-nostats",
        "v%v/index.m3u8",
    ]  # fmt: skip
    return cmd


def run_ffmpeg(
    cmd: list[str], cwd: Path, duration: float, on_progress: Callable[[int], None]
) -> None:
    with tempfile.TemporaryFile(mode="w+") as errors:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=errors, text=True)
        last_report = 0.0
        assert proc.stdout is not None
        for line in proc.stdout:
            key, _, value = line.strip().partition("=")
            if key in ("out_time_us", "out_time_ms") and value.isdigit():
                now = time.monotonic()
                if now - last_report >= PROGRESS_EVERY_S:
                    last_report = now
                    on_progress(min(99, int(int(value) / 1_000_000 / duration * 100)))
        if proc.wait() != 0:
            errors.seek(0)
            raise TranscodeError("video.transcode_failed: " + errors.read()[-1500:])


def transcode_asset(db: Session, asset: VideoAsset) -> dict[str, Any]:
    """Transcode one uploaded video; marks the asset ready or failed (and commits)."""
    src = media.original_path(asset.id)
    out = media.hls_dir(asset.id)
    asset.status = VideoStatus.processing
    asset.progress_pct = 0
    asset.error = None
    db.commit()

    def report(pct: int) -> None:
        asset.progress_pct = pct
        db.commit()

    try:
        info = probe(src)
        ladder = ladder_for(info.height)
        shutil.rmtree(out, ignore_errors=True)
        for i in range(len(ladder)):
            (out / f"v{i}").mkdir(parents=True, exist_ok=True)
        run_ffmpeg(build_command(src, info), out, info.duration, report)
        if not (out / "master.m3u8").is_file():
            raise TranscodeError("video.transcode_failed: no master playlist")
    except (TranscodeError, OSError, subprocess.SubprocessError) as exc:
        shutil.rmtree(out, ignore_errors=True)
        code = "video.transcode_failed"
        if isinstance(exc, TranscodeError):
            code = str(exc).split(":", 1)[0]
        asset.status = VideoStatus.failed
        asset.error = code
        asset.finished_at = clock.utcnow()
        db.commit()
        raise
    asset.status = VideoStatus.ready
    asset.progress_pct = 100
    asset.duration_s = round(info.duration, 3)
    asset.width, asset.height = info.width, info.height
    asset.finished_at = clock.utcnow()
    db.commit()
    return {"duration_s": asset.duration_s, "renditions": [r.height for r in ladder]}


def handle_transcode(db: Session, job: Job) -> dict[str, Any]:
    asset = db.get(VideoAsset, uuid.UUID(job.payload["video_asset_id"]))
    if asset is None:  # replaced before the worker got to it
        return {"skipped": "asset deleted"}
    return transcode_asset(db, asset)


HANDLERS[JobKind.transcode] = handle_transcode
