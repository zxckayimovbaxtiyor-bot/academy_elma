"""Regression tests for direct-file authorization and upload request ordering."""

import asyncio

import pytest
from sqlalchemy import select

from app.auth import sessions
from app.models import AttemptQuestion, TestAttempt
from app.models.enums import AccessRole, AttemptStatus, LessonVersionStatus
from tests.factories import (
    complete_lesson, give_certificate, login, make_learner, make_live_lesson,
    make_user, make_wave, ready_module,
)

AUTH = "/api/v1/internal/media-auth"


def _auth(client, rel):
    return client.get(AUTH, headers={"X-Original-URI": "/media/" + rel})


def test_direct_media_enforces_assignment_core_and_publication(db, client, reference):
    core = reference.modules["CORE"]
    product = reference.modules["FAROVON"]
    make_wave(db, [reference.tashkent], {reference.roles["menejer"]: [product]})
    _, c = make_live_lesson(db, core, pdf=True)
    _, p = make_live_lesson(db, product, pdf=True)
    _, other = make_live_lesson(db, reference.modules["LEGAL"])
    learner = make_learner(db, reference)
    login(client, learner)
    for rel in (f"hls/{c.video_asset_id}/master.m3u8", c.vtt_uz_path, c.pdf_ru_path):
        assert _auth(client, rel).status_code == 204
    for rel in (f"hls/{p.video_asset_id}/v0/seg_0000.ts", p.pdf_uz_path, other.vtt_ru_path):
        assert _auth(client, rel).status_code == 403
    give_certificate(db, learner, core)
    assert _auth(client, p.pdf_uz_path).status_code == 204
    p.status = LessonVersionStatus.draft
    db.flush()
    assert _auth(client, p.pdf_uz_path).status_code == 403
    p.status = LessonVersionStatus.superseded
    db.flush()
    assert _auth(client, p.pdf_uz_path).status_code == 403


def test_staff_preview_faq_and_revocation(db, client, reference):
    _, faq = make_live_lesson(db, reference.modules["FAQ"])
    _, draft = make_live_lesson(db, reference.modules["LEGAL"])
    draft.status = LessonVersionStatus.draft
    db.flush()
    user = make_user(db)
    login(client, user)
    assert _auth(client, faq.vtt_uz_path).status_code == 204
    assert _auth(client, draft.vtt_uz_path).status_code == 403
    user.access_role = AccessRole.methodologist
    db.flush()
    assert _auth(client, draft.vtt_uz_path).status_code == 204
    user.is_active = False
    db.flush()
    assert _auth(client, faq.vtt_uz_path).status_code == 401
    user.is_active = True
    db.flush()
    sessions.revoke_user_sessions(db, user.id)
    db.commit()
    assert _auth(client, faq.vtt_uz_path).status_code == 401


def test_question_images_are_only_for_the_owners_open_attempt(db, client, make_client, reference):
    core = reference.modules["CORE"]
    make_wave(db, [reference.tashkent], {})
    [(lesson, version)] = ready_module(db, core)
    user = make_learner(db, reference)
    complete_lesson(db, user, version)
    login(client, user)
    attempt_id = client.post(f"/api/v1/me/modules/{core.id}/attempts").json()["attempt_id"]
    from app.models import Question
    q = db.scalar(select(Question).join(AttemptQuestion).where(AttemptQuestion.attempt_id == attempt_id))
    q.image_path = "img/question.png"
    db.flush()
    assert _auth(client, q.image_path).status_code == 204
    stranger = make_client()
    login(stranger, make_learner(db, reference))
    assert _auth(stranger, q.image_path).status_code == 403
    db.get(TestAttempt, attempt_id).status = AttemptStatus.submitted
    db.flush()
    assert _auth(client, q.image_path).status_code == 403


@pytest.mark.parametrize("rel", ["originals/private.mp4", "certs/cert.pdf", "hls/not-a-uuid/master.m3u8",
    "vtt/../private.vtt", "vtt/%2e%2e/private.vtt", "vtt/a\\b", "pdf/unknown.pdf", "img/unknown.png"])
def test_unknown_and_unsafe_media_paths_are_refused(db, client, rel):
    login(client, make_user(db, role=AccessRole.admin))
    assert _auth(client, rel).status_code == 403


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/v1/admin/users/import"),
    ("PUT", "/api/v1/admin/lesson-versions/1/pdf/uz"),
    ("PUT", "/api/v1/admin/lesson-versions/1/subtitles/uz"),
    ("PUT", "/api/v1/admin/questions/1/image"),
])
def test_anonymous_uploads_are_rejected_before_reading_body(client, method, path):
    from app.main import app
    messages = []

    async def receive():
        raise AssertionError("Unauthorized upload body was read")

    async def send(message):
        messages.append(message)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "server": ("testserver", 80),
        "client": ("127.0.0.1", 1), "headers": [(b"x-requested-with", b"pytest")]}
    asyncio.run(app(scope, receive, send))
    assert messages[0]["status"] == 401


def test_private_headers_cover_success_errors_and_csrf(client, make_client):
    for response in (client.get("/api/v1/health"), client.get(AUTH),
                     make_client(csrf=False).post("/api/v1/auth/login")):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
