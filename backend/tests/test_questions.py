"""Question bank: structure rules, approval workflow, the 3 x N pool rule, item statistics."""

from __future__ import annotations

from app.models import Lesson, LessonVersion, Question
from app.models.enums import AccessRole, LessonVersionStatus, QuestionStatus, QuestionType
from tests.factories import (
    error_code,
    login,
    make_live_lesson,
    make_pool,
    make_question,
    make_release,
    make_user,
)

ADMIN = "/api/v1/admin"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _staff(db, client):
    login(client, make_user(db, role=AccessRole.methodologist))


def _body(lesson_id: int, q_type: str = "single", correct=(0,), n: int = 4, **extra) -> dict:
    return {
        "lesson_id": lesson_id,
        "type": q_type,
        "text_uz": "Ariza qaysi bosqichda tasdiqlanadi?",
        "text_ru": "На каком этапе утверждается заявка?",
        "explanation_uz": "Tasdiqlash anderrayter bosqichida.",
        "explanation_ru": "Утверждение на этапе андеррайтинга.",
        "difficulty": 2,
        "video_ts_s": 30,
        "options": [
            {"text_uz": f"V{i}", "text_ru": f"В{i}", "is_correct": i in correct} for i in range(n)
        ],
        **extra,
    }


def test_new_question_is_a_numbered_draft_with_a_valid_structure(db, client, reference):
    core = reference.modules["CORE"]
    lesson, version = make_live_lesson(db, core, duration=120)
    _staff(db, client)
    url = f"{ADMIN}/modules/{core.id}/questions"

    created = client.post(url, json=_body(lesson.id))
    assert created.status_code == 201, created.text
    q = created.json()
    assert (q["number"], q["status"], q["lesson_version_id"]) == ("A-001", "draft", version.id)
    assert q["release_code"] == "T-LIVE" and q["version_live"] is True
    assert client.post(url, json=_body(lesson.id)).json()["number"] == "A-002"

    cases = [
        (_body(lesson.id, correct=(0, 1)), "needs_exactly_one_correct"),
        (_body(lesson.id, "screenshot", correct=()), "needs_exactly_one_correct"),
        (_body(lesson.id, "multiple", correct=(0,)), "needs_two_correct_and_one_wrong"),
        (_body(lesson.id, "multiple", correct=(0, 1, 2, 3)), "needs_two_correct_and_one_wrong"),
    ]
    for body, problem in cases:
        resp = client.post(url, json=body)
        assert resp.status_code == 400 and error_code(resp) == "question.invalid"
        assert resp.json()["error"]["params"]["problems"] == [problem]

    late = client.post(url, json=_body(lesson.id, video_ts_s=121))
    assert error_code(late) == "question.timestamp_after_video"

    other, _ = make_live_lesson(db, reference.modules["FAROVON"])
    assert error_code(client.post(url, json=_body(other.id))) == "question.lesson_not_in_module"

    faq = reference.modules["FAQ"]
    faq_lesson, _ = make_live_lesson(db, faq)
    resp = client.post(f"{ADMIN}/modules/{faq.id}/questions", json=_body(faq_lesson.id))
    assert resp.status_code == 400 and error_code(resp) == "module.no_test"


def test_question_bank_is_for_methodologists_and_admins(db, client, make_client, reference):
    core = reference.modules["CORE"]
    login(client, make_user(db))
    assert client.get(f"{ADMIN}/modules/{core.id}/questions").status_code == 403
    admin = make_client()
    login(admin, make_user(db, role=AccessRole.admin))
    assert admin.get(f"{ADMIN}/modules/{core.id}/questions").status_code == 200


def test_approval_needs_a_complete_question(db, client, reference):
    core = reference.modules["CORE"]
    lesson, _ = make_live_lesson(db, core)
    _staff(db, client)
    url = f"{ADMIN}/modules/{core.id}/questions"
    q = client.post(url, json=_body(lesson.id, explanation_uz="", explanation_ru="")).json()

    resp = client.post(f"{ADMIN}/questions/{q['id']}/approve")
    assert resp.status_code == 400 and error_code(resp) == "question.incomplete"
    problems = resp.json()["error"]["params"]["problems"]
    assert problems == ["explanation_uz_missing", "explanation_ru_missing"]

    shot = client.post(url, json=_body(lesson.id, "screenshot")).json()
    resp = client.post(f"{ADMIN}/questions/{shot['id']}/approve")
    assert resp.json()["error"]["params"]["problems"] == ["image_missing"]

    explained = {"explanation_uz": "Izoh", "explanation_ru": "Пояснение"}
    patched = client.patch(f"{ADMIN}/questions/{q['id']}", json=explained)
    assert patched.status_code == 200
    approved = client.post(f"{ADMIN}/questions/{q['id']}/approve").json()
    assert approved["status"] == "approved" and approved["approved_at"]
    again = client.post(f"{ADMIN}/questions/{q['id']}/approve")
    assert again.status_code == 409 and error_code(again) == "question.not_draft"


def test_screenshot_image_upload(db, client, reference, media_root):
    core = reference.modules["CORE"]
    lesson, _ = make_live_lesson(db, core)
    _staff(db, client)
    url = f"{ADMIN}/modules/{core.id}/questions"
    shot = client.post(url, json=_body(lesson.id, "screenshot")).json()
    single = client.post(url, json=_body(lesson.id)).json()

    bad = client.put(f"{ADMIN}/questions/{shot['id']}/image", content=b"GIF89a....")
    assert bad.status_code == 400 and error_code(bad) == "image.invalid"
    wrong = client.put(f"{ADMIN}/questions/{single['id']}/image", content=PNG)
    assert error_code(wrong) == "question.not_screenshot"

    first = client.put(f"{ADMIN}/questions/{shot['id']}/image", content=PNG).json()["image_url"]
    ok = client.put(f"{ADMIN}/questions/{shot['id']}/image", content=PNG)
    assert ok.status_code == 200 and ok.json()["image_url"].startswith("/media/img/")
    replaced = media_root / first.removeprefix("/media/")
    assert not replaced.exists()  # the replaced screenshot is not left behind
    assert (media_root / ok.json()["image_url"].removeprefix("/media/")).exists()
    assert client.post(f"{ADMIN}/questions/{shot['id']}/approve").json()["status"] == "approved"
    locked = client.put(f"{ADMIN}/questions/{shot['id']}/image", content=PNG)
    assert locked.status_code == 409 and error_code(locked) == "question.answer_key_locked"


def test_approved_question_keeps_its_answer_key(db, client, reference):
    core = reference.modules["CORE"]
    lesson, version = make_live_lesson(db, core)
    q = make_question(db, core, version, correct=(1,))
    _staff(db, client)
    url = f"{ADMIN}/questions/{q.id}"
    options = [
        {"id": o.id, "text_uz": o.text_uz, "text_ru": o.text_ru, "is_correct": o.is_correct}
        for o in q.options
    ]

    moved = [dict(o, is_correct=i == 0) for i, o in enumerate(options)]
    resp = client.patch(url, json={"options": moved})
    assert resp.status_code == 409 and error_code(resp) == "question.answer_key_locked"
    dropped = client.patch(url, json={"options": options[:3]})
    assert error_code(dropped) == "question.answer_key_locked"
    assert error_code(client.patch(url, json={"type": "multiple"})) == "question.answer_key_locked"

    reworded = [dict(o, text_uz=f"{o['text_uz']} (aniq)") for o in options]
    resp = client.patch(url, json={"text_uz": "Yangi matn", "options": reworded})
    assert resp.status_code == 200
    out = resp.json()
    assert out["text_uz"] == "Yangi matn" and out["options"][0]["text_uz"] == "Variant 1 (aniq)"
    assert [o["is_correct"] for o in out["options"]] == [False, True, False, False]


def test_reject_retire_and_duplicate(db, client, reference):
    core = reference.modules["CORE"]
    lesson, version = make_live_lesson(db, core)
    draft = make_question(db, core, version, status=QuestionStatus.draft)
    approved = make_question(db, core, version)
    approved.stat_attempts, approved.stat_correct = 40, 30
    _staff(db, client)

    rejected = client.post(f"{ADMIN}/questions/{draft.id}/reject").json()
    assert (rejected["status"], rejected["retired_reason"]) == ("retired", "rejected")
    not_approved = client.post(f"{ADMIN}/questions/{draft.id}/retire")
    assert error_code(not_approved) == "question.not_approved"
    edit = client.patch(f"{ADMIN}/questions/{draft.id}", json={"text_uz": "x"})
    assert edit.status_code == 409 and error_code(edit) == "question.retired"

    copy = client.post(f"{ADMIN}/questions/{approved.id}/duplicate")
    assert copy.status_code == 201
    copy = copy.json()
    assert copy["status"] == "draft" and copy["number"] == "A-003"
    assert copy["text_uz"] == approved.text_uz and copy["stats"]["attempts"] == 0
    assert [o["is_correct"] for o in copy["options"]] == [True, False, False, False]

    retired = client.post(f"{ADMIN}/questions/{approved.id}/retire").json()
    assert (retired["status"], retired["retired_reason"]) == ("retired", "manual")


def test_publish_test_needs_a_pool_of_three_times_n(db, client, reference):
    core = reference.modules["CORE"]
    core.test_question_count = 2  # pool must hold 6
    lesson, version = make_live_lesson(db, core)
    for d in (1, 2, 3, 1, 2):
        make_question(db, core, version, difficulty=d)
    pending = make_question(db, core, version, status=QuestionStatus.draft)
    make_question(db, core, version, status=QuestionStatus.draft)
    make_question(db, core, version, status=QuestionStatus.retired)
    old = LessonVersion(
        lesson_id=lesson.id, release_id=make_release(db, "T-OLD").id,
        status=LessonVersionStatus.superseded,
    )  # fmt: skip
    db.add(old)
    db.flush()
    make_question(db, core, old)  # approved, but about a replaced video
    _staff(db, client)

    pool = client.get(f"{ADMIN}/modules/{core.id}/pool").json()
    assert pool == {
        "question_count": 2, "required": 6, "approved_active": 5,
        "by_difficulty": {"1": 2, "2": 2, "3": 1}, "drafts": 2, "publishable": False,
        "test_published": False,
    }  # fmt: skip
    refused = client.post(f"{ADMIN}/modules/{core.id}/test/publish")
    assert refused.status_code == 409 and error_code(refused) == "test.pool_too_small"
    assert refused.json()["error"]["params"] == {"have": 5, "need": 6}

    assert client.post(f"{ADMIN}/questions/{pending.id}/approve").status_code == 200
    published = client.post(f"{ADMIN}/modules/{core.id}/test/publish")
    assert published.status_code == 200
    assert published.json()["test_published"] is True and published.json()["approved_active"] == 6

    off = client.post(f"{ADMIN}/modules/{core.id}/test/unpublish").json()
    assert off["test_published"] is False

    faq = reference.modules["FAQ"]
    assert error_code(client.post(f"{ADMIN}/modules/{faq.id}/test/publish")) == "module.no_test"


def test_raising_n_on_a_published_test_keeps_the_pool_rule(db, client, reference):
    core = reference.modules["CORE"]
    core.test_question_count = 2
    _, version = make_live_lesson(db, core)
    make_pool(db, core, version, per_difficulty=2)  # 6 = 3 x 2
    _staff(db, client)
    assert client.post(f"{ADMIN}/modules/{core.id}/test/publish").status_code == 200

    resp = client.patch(f"{ADMIN}/modules/{core.id}", json={"test_question_count": 3})
    assert resp.status_code == 409 and error_code(resp) == "test.pool_too_small"
    assert resp.json()["error"]["params"] == {"have": 6, "need": 9}
    lower = client.patch(f"{ADMIN}/modules/{core.id}", json={"test_question_count": 1})
    assert lower.status_code == 200

    farovon = reference.modules["FAROVON"]  # unpublished test: N can change freely
    ok = client.patch(f"{ADMIN}/modules/{farovon.id}", json={"test_question_count": 20})
    assert ok.status_code == 200


def test_item_statistics_flag_too_hard_and_too_easy_questions(db, client, reference):
    core = reference.modules["CORE"]
    _, version = make_live_lesson(db, core)
    hard = make_question(db, core, version)
    easy = make_question(db, core, version)
    fine = make_question(db, core, version)
    young = make_question(db, core, version)
    hard.stat_attempts, hard.stat_correct = 30, 5  # 16.7 %
    easy.stat_attempts, easy.stat_correct = 30, 29  # 96.7 %
    fine.stat_attempts, fine.stat_correct = 30, 15
    young.stat_attempts, young.stat_correct = 29, 0  # too few answers to judge
    db.flush()
    _staff(db, client)

    flagged = client.get(f"{ADMIN}/modules/{core.id}/questions", params={"flagged": True}).json()
    assert [q["id"] for q in flagged] == [hard.id, easy.id]
    assert flagged[0]["stats"] == {
        "attempts": 30, "correct": 5, "correct_pct": 16.7, "flagged": True,
    }  # fmt: skip
    every = client.get(f"{ADMIN}/modules/{core.id}/questions").json()
    assert len(every) == 4
    drafts = client.get(f"{ADMIN}/modules/{core.id}/questions", params={"status": "draft"}).json()
    assert drafts == []


def test_questions_written_during_a_release_follow_the_new_video(
    db, client, make_client, reference
):
    core = reference.modules["CORE"]
    lesson, live = make_live_lesson(db, core)
    admin = make_client()
    login(admin, make_user(db, role=AccessRole.admin))
    release = admin.post(f"{ADMIN}/releases", json={"code": "2026.12"}).json()
    marked = admin.post(f"{ADMIN}/releases/{release['id']}/lessons/{lesson.id}")
    draft_version_id = marked.json()["draft"]["id"]
    _staff(db, client)

    q = client.post(f"{ADMIN}/modules/{core.id}/questions", json=_body(lesson.id, video_ts_s=0))
    q = q.json()
    assert q["lesson_version_id"] == draft_version_id != live.id
    assert (q["release_code"], q["version_live"]) == ("2026.12", False)


def test_ordering_question_needs_only_options(db, client, reference):
    core = reference.modules["CORE"]
    lesson, _ = make_live_lesson(db, core)
    _staff(db, client)
    body = _body(lesson.id, "ordering", correct=(), n=3)
    resp = client.post(f"{ADMIN}/modules/{core.id}/questions", json=body)
    assert resp.status_code == 201 and resp.json()["type"] == QuestionType.ordering
    approve = client.post(f"{ADMIN}/questions/{resp.json()['id']}/approve")
    assert approve.json()["status"] == "approved"


def test_new_lesson_with_only_rejected_questions_can_still_be_deleted(
    db, client, make_client, reference
):
    core = reference.modules["CORE"]
    admin = make_client()
    login(admin, make_user(db, role=AccessRole.admin))
    admin.post(f"{ADMIN}/releases", json={"code": "2026.12"})
    lesson = admin.post(
        f"{ADMIN}/modules/{core.id}/lessons", json={"title_uz": "Yangi", "title_ru": "Новый"}
    ).json()
    _staff(db, client)
    q = client.post(f"{ADMIN}/modules/{core.id}/questions", json=_body(lesson["id"], video_ts_s=0))
    assert q.status_code == 201, q.text

    blocked = admin.delete(f"{ADMIN}/lessons/{lesson['id']}")
    assert blocked.status_code == 409 and error_code(blocked) == "lesson.has_questions"
    client.post(f"{ADMIN}/questions/{q.json()['id']}/reject")
    assert admin.delete(f"{ADMIN}/lessons/{lesson['id']}").status_code == 204
    assert db.get(Lesson, lesson["id"]) is None
    assert db.get(Question, q.json()["id"]) is None  # never served: nothing to keep
