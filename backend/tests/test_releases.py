"""Content reaches learners only when a release is published (Phase 2 part of rule 9)."""

from __future__ import annotations

from sqlalchemy import select

from app.models import LessonVersion, Module
from app.models.enums import AccessRole, LessonVersionStatus, VideoStatus
from tests.factories import (
    error_code,
    login,
    make_asset,
    make_learner,
    make_live_lesson,
    make_user,
    make_version_ready,
    make_wave,
)

RELEASES = "/api/v1/admin/releases"
_make_ready = make_version_ready


def _admin(db, client):
    login(client, make_user(db, role=AccessRole.admin))


def test_one_draft_release_at_a_time(db, client, reference):
    _admin(db, client)
    assert client.post(RELEASES, json={"code": "2026.12"}).status_code == 201
    again = client.post(RELEASES, json={"code": "2027.01"})
    assert again.status_code == 409 and error_code(again) == "release.draft_exists"
    assert error_code(client.post(RELEASES, json={"code": "bad code!"})) == "release.code_invalid"


def test_checklist_blocks_publishing_until_every_lesson_is_complete(db, client, reference):
    _admin(db, client)
    release = client.post(RELEASES, json={"code": "2026.12"}).json()
    empty = client.post(f"{RELEASES}/{release['id']}/publish")
    assert empty.status_code == 409
    problems = empty.json()["error"]["params"]["problems"]
    assert problems == [{"lesson_id": None, "code": "release_empty"}]

    module = reference.modules["FAROVON"]
    lesson = client.post(
        f"/api/v1/admin/modules/{module.id}/lessons",
        json={"title_uz": "Garov", "title_ru": "Залог"},
    ).json()
    detail = client.get(f"{RELEASES}/{release['id']}").json()
    assert detail["ready"] is False
    assert detail["lessons"][0]["change"] == "added"
    assert detail["lessons"][0]["problems"] == ["video_missing", "vtt_uz_missing", "vtt_ru_missing"]

    version = db.get(LessonVersion, lesson["draft"]["id"])
    version.video_asset_id = make_asset(db, 60, status=VideoStatus.processing).id
    db.flush()
    problems = client.get(f"{RELEASES}/{release['id']}").json()["lessons"][0]["problems"]
    assert problems[0] == "video_not_ready"


def test_publishing_makes_new_lessons_live(db, client, make_client, reference):
    _admin(db, client)
    make_wave(db, [reference.tashkent], {})
    release = client.post(RELEASES, json={"code": "2026.11"}).json()
    core = reference.modules["CORE"]
    lesson = client.post(
        f"/api/v1/admin/modules/{core.id}/lessons",
        json={"title_uz": "Kirish", "title_ru": "Введение"},
    ).json()
    _make_ready(db, client, lesson["draft"]["id"])

    learner = make_client()
    login(learner, make_learner(db, reference))
    assert learner.get("/api/v1/me/modules").json() == []  # drafts are invisible

    published = client.post(f"{RELEASES}/{release['id']}/publish")
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert db.get(Module, core.id).current_release_id == release["id"]
    assert [m["code"] for m in learner.get("/api/v1/me/modules").json()] == ["CORE"]
    again = client.post(f"{RELEASES}/{release['id']}/publish")
    assert error_code(again) == "release.not_draft"


def test_changed_lesson_gets_a_new_version_and_old_progress_stops_counting(
    db, client, make_client, reference, clock
):
    _admin(db, client)
    make_wave(db, [reference.tashkent], {})
    core = reference.modules["CORE"]
    lesson, old = make_live_lesson(db, core, duration=60, pdf=True)
    learner_client = make_client()
    login(learner_client, make_learner(db, reference))
    beat = f"/api/v1/me/lessons/{lesson.id}/heartbeat"
    learner_client.post(beat, json={"version_id": old.id, "ranges": []})
    clock.advance(seconds=30)
    learner_client.post(beat, json={"version_id": old.id, "ranges": [[0, 30]]})

    release = client.post(RELEASES, json={"code": "2026.12"}).json()
    marked = client.post(f"{RELEASES}/{release['id']}/lessons/{lesson.id}")
    assert marked.status_code == 201
    draft = marked.json()["draft"]
    assert draft["pdf_uz_url"] == marked.json()["published"]["pdf_uz_url"]  # PDFs carried over
    assert draft["vtt_uz_url"] is None and draft["video"] is None  # must be redone
    again = client.post(f"{RELEASES}/{release['id']}/lessons/{lesson.id}")
    assert error_code(again) == "lesson.already_in_release"

    _make_ready(db, client, draft["id"], duration=70)
    assert client.post(f"{RELEASES}/{release['id']}/publish").status_code == 200
    db.expire_all()
    assert db.get(LessonVersion, old.id).status == LessonVersionStatus.superseded
    assert db.get(LessonVersion, draft["id"]).status == LessonVersionStatus.published

    player = learner_client.get(f"/api/v1/me/lessons/{lesson.id}").json()
    assert player["version_id"] == draft["id"] and player["duration_s"] == 70
    assert player["progress"]["watched_s"] == 0  # the changed lesson must be watched again
    stale = learner_client.post(beat, json={"version_id": old.id, "ranges": []})
    assert error_code(stale) == "lesson.version_changed"
    detail = client.get(f"{RELEASES}/{release['id']}").json()
    assert detail["lessons"][0]["change"] == "changed"


def test_unmarking_keeps_files_still_used_by_the_live_version(db, client, reference, media_root):
    _admin(db, client)
    lesson, live = make_live_lesson(db, reference.modules["CORE"], pdf=True)
    (media_root / "pdf").mkdir()
    (media_root / live.pdf_uz_path).write_bytes(b"%PDF-1.7")
    release = client.post(RELEASES, json={"code": "2026.12"}).json()
    client.post(f"{RELEASES}/{release['id']}/lessons/{lesson.id}")
    assert client.delete(f"{RELEASES}/{release['id']}/lessons/{lesson.id}").status_code == 204
    assert (media_root / live.pdf_uz_path).is_file()
    remaining = db.scalars(select(LessonVersion).where(LessonVersion.lesson_id == lesson.id)).all()
    assert [v.id for v in remaining] == [live.id]


def test_new_lessons_cannot_be_unmarked_and_empty_drafts_can_be_deleted(db, client, reference):
    _admin(db, client)
    release = client.post(RELEASES, json={"code": "2026.12"}).json()
    module = reference.modules["CRM"]
    lesson = client.post(
        f"/api/v1/admin/modules/{module.id}/lessons", json={"title_uz": "CRM", "title_ru": "CRM"}
    ).json()
    resp = client.delete(f"{RELEASES}/{release['id']}/lessons/{lesson['id']}")
    assert error_code(resp) == "lesson.new_in_release"
    assert error_code(client.delete(f"{RELEASES}/{release['id']}")) == "release.not_empty"
    client.delete(f"/api/v1/admin/lessons/{lesson['id']}")
    assert client.delete(f"{RELEASES}/{release['id']}").status_code == 204


def test_releases_are_admin_only(db, client, reference):
    login(client, make_user(db, role=AccessRole.methodologist))
    assert client.get(RELEASES).status_code == 403
