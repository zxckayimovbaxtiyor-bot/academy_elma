from __future__ import annotations

from sqlalchemy import select

from app.models import AuditEvent, Job, LessonVersion, VideoAsset
from app.models.enums import AccessRole, JobKind, LessonVersionStatus, ReleaseStatus
from app.services import media
from tests.factories import error_code, login, make_asset, make_live_lesson, make_release, make_user

ADMIN = "/api/v1/admin"
VTT = "WEBVTT\n\n00:00.000 --> 00:04.000\nKirish\n\n00:04.000 --> 00:09.000\nDavomi\n"


def _as(db, client, role=AccessRole.admin):
    user = make_user(db, role=role)
    login(client, user)
    return user


def _draft_lesson(db, client, reference, title="Yangi dars"):
    make_release(db, "2026.12", ReleaseStatus.draft)
    module = reference.modules["FAROVON"]
    resp = client.post(
        f"{ADMIN}/modules/{module.id}/lessons", json={"title_uz": title, "title_ru": title}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- modules -------------------------------------------------------------------------------


def test_admin_creates_modules_methodologist_edits_them(db, client, make_client, reference):
    _as(db, client)
    body = {"code": "MIKRO", "qprefix": "MK", "type": "product",
            "title_uz": "Mikroqarz", "title_ru": "Микрозайм"}  # fmt: skip
    created = client.post(f"{ADMIN}/modules", json=body)
    assert created.status_code == 201 and created.json()["sort"] == 8
    assert error_code(client.post(f"{ADMIN}/modules", json=body)) == "module.code_taken"
    core = {**body, "code": "CORE2", "qprefix": "CX", "type": "core"}
    assert error_code(client.post(f"{ADMIN}/modules", json=core)) == "module.core_exists"

    methodologist = make_client()
    _as(db, methodologist, AccessRole.methodologist)
    assert methodologist.post(f"{ADMIN}/modules", json={**body, "code": "X1"}).status_code == 403
    module_id = created.json()["id"]
    patched = methodologist.patch(
        f"{ADMIN}/modules/{module_id}",
        json={"title_ru": "Микрокредит", "test_question_count": 10, "test_cooldown_hours": 0},
    )
    assert patched.status_code == 200
    assert patched.json()["title_ru"] == "Микрокредит"
    assert patched.json()["test_question_count"] == 10
    too_many = methodologist.patch(f"{ADMIN}/modules/{module_id}", json={"test_pass_pct": 101})
    assert too_many.status_code == 422


def test_reorder_modules_must_list_every_module(db, client, reference):
    _as(db, client)
    ids = [m["id"] for m in client.get(f"{ADMIN}/modules").json()]
    assert client.post(f"{ADMIN}/modules/reorder", json={"ids": ids[1:]}).status_code == 400
    reversed_ids = list(reversed(ids))
    assert client.post(f"{ADMIN}/modules/reorder", json={"ids": reversed_ids}).status_code == 204
    assert [m["id"] for m in client.get(f"{ADMIN}/modules").json()] == reversed_ids


def test_learners_have_no_access_to_content_admin(db, client, reference):
    _as(db, client, AccessRole.learner)
    assert client.get(f"{ADMIN}/modules").status_code == 403


# --- lessons -------------------------------------------------------------------------------


def test_new_lessons_need_an_open_draft_release(db, client, reference):
    _as(db, client, AccessRole.methodologist)
    module = reference.modules["FAROVON"]
    url = f"{ADMIN}/modules/{module.id}/lessons"
    resp = client.post(url, json={"title_uz": "a", "title_ru": "a"})
    assert resp.status_code == 409 and error_code(resp) == "release.no_draft"
    lesson = _draft_lesson(db, client, reference)
    assert lesson["published"] is None
    assert lesson["draft"]["release_code"] == "2026.12" and lesson["draft"]["video"] is None


def test_lessons_reorder_within_a_module(db, client, reference):
    _as(db, client)
    first = _draft_lesson(db, client, reference, "Birinchi")
    module = reference.modules["FAROVON"]
    second = client.post(
        f"{ADMIN}/modules/{module.id}/lessons", json={"title_uz": "Ikkinchi", "title_ru": "Второй"}
    ).json()
    order = [second["id"], first["id"]]
    resp = client.post(f"{ADMIN}/modules/{module.id}/lessons/reorder", json={"ids": order})
    assert resp.status_code == 204
    listed = client.get(f"{ADMIN}/modules/{module.id}/lessons").json()
    assert [lesson["id"] for lesson in listed] == order


def test_only_never_published_lessons_can_be_deleted(db, client, reference, media_root):
    _as(db, client)
    lesson = _draft_lesson(db, client, reference)
    version_id = lesson["draft"]["id"]
    client.put(f"{ADMIN}/lesson-versions/{version_id}/subtitles/uz", content=VTT)
    stored = list((media_root / "vtt").iterdir())
    assert len(stored) == 1
    assert client.delete(f"{ADMIN}/lessons/{lesson['id']}").status_code == 204
    assert list((media_root / "vtt").iterdir()) == []

    live, _ = make_live_lesson(db, reference.modules["CORE"])
    resp = client.delete(f"{ADMIN}/lessons/{live.id}")
    assert resp.status_code == 409 and error_code(resp) == "lesson.already_published"


# --- subtitles, PDFs, transcript --------------------------------------------------------------


def test_subtitles_are_validated_stored_and_replaced(db, client, reference, media_root):
    _as(db, client, AccessRole.methodologist)
    version_id = _draft_lesson(db, client, reference)["draft"]["id"]
    bad = client.put(
        f"{ADMIN}/lesson-versions/{version_id}/subtitles/uz",
        content="WEBVTT\n\n00:00.000 -> 00:01.000\nx\n",
    )
    assert bad.status_code == 400
    assert error_code(bad) == "vtt.bad_timing" and bad.json()["error"]["params"]["line"] == 4

    first = client.put(f"{ADMIN}/lesson-versions/{version_id}/subtitles/uz", content=VTT).json()
    url = first["vtt_uz_url"]
    assert url.startswith("/media/vtt/") and (media_root / url.removeprefix("/media/")).is_file()
    second = client.put(f"{ADMIN}/lesson-versions/{version_id}/subtitles/uz", content=VTT).json()
    assert second["vtt_uz_url"] != url  # new file name, so caches never serve the old one
    assert not (media_root / url.removeprefix("/media/")).exists()

    cues = client.get(f"{ADMIN}/lesson-versions/{version_id}/transcript", params={"lang": "uz"})
    assert [c["text"] for c in cues.json()] == ["Kirish", "Davomi"]


def test_subtitles_cannot_run_past_the_video(db, client, reference):
    _as(db, client)
    version_id = _draft_lesson(db, client, reference)["draft"]["id"]
    version = db.get(LessonVersion, version_id)
    version.video_asset_id = make_asset(db, duration=5.0).id
    db.flush()
    resp = client.put(f"{ADMIN}/lesson-versions/{version_id}/subtitles/ru", content=VTT)
    assert resp.status_code == 400 and error_code(resp) == "vtt.exceeds_video"


def test_subtitles_can_be_fixed_on_a_live_lesson(db, client, reference):
    _as(db, client, AccessRole.methodologist)
    _, live = make_live_lesson(db, reference.modules["CORE"], duration=60)
    resp = client.put(f"{ADMIN}/lesson-versions/{live.id}/subtitles/ru", content=VTT)
    assert resp.status_code == 200 and resp.json()["status"] == "published"


def test_reference_pdf_upload_and_delete(db, client, reference):
    _as(db, client)
    version_id = _draft_lesson(db, client, reference)["draft"]["id"]
    bad = client.put(f"{ADMIN}/lesson-versions/{version_id}/pdf/uz", content=b"not a pdf")
    assert error_code(bad) == "pdf.invalid"
    ok = client.put(f"{ADMIN}/lesson-versions/{version_id}/pdf/uz", content=b"%PDF-1.7 demo")
    assert ok.json()["pdf_uz_url"].startswith("/media/pdf/")
    gone = client.delete(f"{ADMIN}/lesson-versions/{version_id}/pdf/uz")
    assert gone.json()["pdf_uz_url"] is None


# --- video upload -------------------------------------------------------------------------------


def _upload(client, version_id, data=b"\x00\x00\x00\x18ftypmp42 fake", confirm=True):
    params = {"filename": "garov.mp4"}
    if confirm:
        params["synthetic_data_confirmed"] = "true"
    return client.put(f"{ADMIN}/lesson-versions/{version_id}/video", params=params, content=data)


def test_video_upload_requires_the_synthetic_data_confirmation(db, client, reference, media_root):
    _as(db, client, AccessRole.methodologist)
    version_id = _draft_lesson(db, client, reference)["draft"]["id"]
    resp = _upload(client, version_id, confirm=False)
    assert resp.status_code == 400
    assert error_code(resp) == "video.synthetic_confirmation_required"
    assert not (media_root / "originals").exists()


def test_video_upload_stores_the_file_and_queues_a_transcode(db, client, reference, media_root):
    user = _as(db, client, AccessRole.methodologist)
    version_id = _draft_lesson(db, client, reference)["draft"]["id"]
    resp = _upload(client, version_id)
    assert resp.status_code == 202, resp.text
    video = resp.json()
    assert video["status"] == "uploaded" and video["original_filename"] == "garov.mp4"
    asset = db.get(VideoAsset, video["asset_id"])
    assert asset.synthetic_confirmed_by == user.id and asset.synthetic_confirmed_at is not None
    assert media.original_path(asset.id).read_bytes().endswith(b"fake")
    job = db.scalar(select(Job).where(Job.kind == JobKind.transcode))
    assert job.payload == {"video_asset_id": video["asset_id"]}
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "video.uploaded"))
    assert event.data["synthetic_data_confirmed"] is True
    assert list((media_root / "tmp").iterdir()) == []

    replaced = _upload(client, version_id).json()  # a second upload replaces the first
    assert replaced["asset_id"] != video["asset_id"]
    assert db.get(VideoAsset, video["asset_id"]) is None
    assert not media.original_path(asset.id).exists()


def test_live_videos_change_only_through_a_release(db, client, reference):
    _as(db, client)
    _, live = make_live_lesson(db, reference.modules["CORE"])
    resp = _upload(client, live.id)
    assert resp.status_code == 409 and error_code(resp) == "version.not_draft"


def test_oversized_upload_is_refused_and_cleaned_up(db, client, reference, media_root, monkeypatch):
    _as(db, client)
    version_id = _draft_lesson(db, client, reference)["draft"]["id"]
    monkeypatch.setattr("app.api.admin_content.MAX_VIDEO_BYTES", 10)
    resp = _upload(client, version_id, data=b"x" * 11)
    assert resp.status_code == 413 and error_code(resp) == "video.too_large"
    assert list((media_root / "tmp").iterdir()) == []
    assert db.get(LessonVersion, version_id).status == LessonVersionStatus.draft
