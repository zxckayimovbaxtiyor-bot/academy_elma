"""Real ffmpeg runs (skipped where ffmpeg isn't installed)."""

from __future__ import annotations

import shutil
import subprocess
import uuid

import pytest
from sqlalchemy import select

from app.cli import seed_demo_content
from app.models import ElmaRelease, Job, LessonVersion, Module, VideoAsset
from app.models.enums import (
    AccessRole,
    JobKind,
    JobLane,
    JobStatus,
    LessonVersionStatus,
    ReleaseStatus,
    VideoStatus,
)
from app.services import media
from app.worker import runner
from app.worker.transcode import TranscodeError, transcode_asset
from tests.factories import make_asset, make_user

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg not installed"
)


def _clip(asset: VideoAsset, size: str, seconds: int = 3, audio: bool = True) -> None:
    target = media.original_path(asset.id)
    target.parent.mkdir(parents=True, exist_ok=True)
    inputs = ["-f", "lavfi", "-i", f"testsrc2=size={size}:rate=25"]
    if audio:
        inputs += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-t", str(seconds),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", *(["-c:a", "aac"] if audio else []),
         "-shortest", str(target)],
        check=True,
    )  # fmt: skip


def _uploaded_asset(db) -> VideoAsset:
    asset = make_asset(db, duration=None, status=VideoStatus.uploaded)
    return asset


def test_720p_source_becomes_three_hls_renditions(db):
    asset = _uploaded_asset(db)
    _clip(asset, "1280x720")
    result = transcode_asset(db, asset)
    assert result["renditions"] == [360, 480, 720]
    assert asset.status == VideoStatus.ready and asset.progress_pct == 100
    assert asset.duration_s == pytest.approx(3, abs=0.2)
    out = media.hls_dir(asset.id)
    master = (out / "master.m3u8").read_text()
    assert master.count("#EXT-X-STREAM-INF") == 3 and "RESOLUTION=1280x720" in master
    assert (out / "v0" / "index.m3u8").is_file() and list((out / "v0").glob("seg_*.ts"))


def test_small_or_silent_source_is_never_upscaled(db):
    asset = _uploaded_asset(db)
    _clip(asset, "640x360", audio=False)
    assert transcode_asset(db, asset)["renditions"] == [360]
    assert "RESOLUTION=640x360" in (media.hls_dir(asset.id) / "master.m3u8").read_text()


def test_unreadable_upload_marks_the_video_failed(db):
    asset = _uploaded_asset(db)
    path = media.original_path(asset.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not a video")
    with pytest.raises(TranscodeError):
        transcode_asset(db, asset)
    assert asset.status == VideoStatus.failed and asset.error == "video.unreadable"
    assert not media.hls_dir(asset.id).exists()


def test_worker_job_runs_the_transcode(db):
    asset = _uploaded_asset(db)
    _clip(asset, "854x480", seconds=2)
    runner.enqueue(db, JobKind.transcode, JobLane.media, {"video_asset_id": str(asset.id)})
    db.commit()
    job = runner.claim_next(db, JobLane.media)
    runner.run_job(db, job)
    assert job.status == JobStatus.done and job.result["renditions"] == [360, 480]
    assert db.get(VideoAsset, asset.id).status == VideoStatus.ready


def test_job_for_a_replaced_video_is_skipped(db):
    payload = {"video_asset_id": str(uuid.uuid4())}
    job = runner.enqueue(db, JobKind.transcode, JobLane.media, payload)
    db.commit()
    runner.run_job(db, runner.claim_next(db, JobLane.media))
    assert db.get(Job, job.id).result == {"skipped": "asset deleted"}


def test_demo_seed_publishes_generated_lessons(db, reference):
    admin = make_user(db, role=AccessRole.admin)
    assert seed_demo_content(db, admin.id, seconds=3) == {"lessons": 5, "questions": 90}
    release = db.scalar(select(ElmaRelease).where(ElmaRelease.code == "2026.11"))
    assert release.status == ReleaseStatus.published
    live = db.scalars(
        select(LessonVersion).where(LessonVersion.status == LessonVersionStatus.published)
    ).all()
    assert len(live) == 5 and all(v.vtt_uz_path and v.vtt_ru_path for v in live)
    codes = set(db.scalars(select(Module.code).where(Module.current_release_id == release.id)))
    assert codes == {"CORE", "FAROVON"}
    assert seed_demo_content(db, admin.id, seconds=3) == {"lessons": 0}  # idempotent
