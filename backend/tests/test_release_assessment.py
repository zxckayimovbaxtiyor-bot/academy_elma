"""Release publish and the question bank (rule 9 steps 5–6, plus the 3 x N check of rule 6)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app import clock as app_clock
from app.models import Question, RemediationItem, TestAttempt
from app.models.enums import (
    AccessRole,
    AttemptStatus,
    QuestionStatus,
    RemediationResolution,
    RetiredReason,
)
from app.services import remediation
from tests.factories import (
    complete_lesson,
    error_code,
    login,
    make_learner,
    make_live_lesson,
    make_pool,
    make_question,
    make_user,
    make_version_ready,
    make_wave,
)

ADMIN = "/api/v1/admin"
RELEASES = f"{ADMIN}/releases"


def _question(lesson_id: int, difficulty: int) -> dict:
    return {
        "lesson_id": lesson_id, "type": "single", "difficulty": difficulty, "video_ts_s": 10,
        "text_uz": "Yangi ekranda qaysi tugma bor?", "text_ru": "Какая кнопка на новом экране?",
        "explanation_uz": "Izoh", "explanation_ru": "Пояснение",
        "options": [
            {"text_uz": "Saqlash", "text_ru": "Сохранить", "is_correct": True},
            {"text_uz": "Bekor qilish", "text_ru": "Отмена", "is_correct": False},
        ],
    }  # fmt: skip


def test_release_keeps_the_pool_rule_and_retires_questions_about_old_videos(
    db, client, make_client, reference, clock
):
    core = reference.modules["CORE"]
    core.test_question_count = 3  # the pool must hold 9
    make_wave(db, [reference.tashkent], {})
    one, v1 = make_live_lesson(db, core, duration=600, title="Ariza")
    _, v2 = make_live_lesson(db, core, duration=600, title="Garov")
    old_questions = [make_question(db, core, v1, difficulty=d, ts=100) for d in (1, 2, 3)]
    make_pool(db, core, v2, per_difficulty=2)
    login(client, make_user(db, role=AccessRole.admin))
    assert client.post(f"{ADMIN}/modules/{core.id}/test/publish").status_code == 200

    # One learner failed earlier and still has a fragment of the old video to re-watch...
    learner = make_learner(db, reference)
    for version in (v1, v2):
        complete_lesson(db, learner, version)
    now = app_clock.utcnow()
    failed = TestAttempt(
        user_id=learner.id, module_id=core.id, release_id=core.current_release_id,
        status=AttemptStatus.submitted, started_at=now, expires_at=now + timedelta(minutes=20),
        submitted_at=now, question_count=3, pass_pct=80, correct_count=0, score_pct=0.0,
        passed=False,
    )  # fmt: skip
    db.add(failed)
    db.flush()
    remediation.create_items(db, failed, old_questions[:1])
    # ...and another one is in the middle of a test when the release goes out.
    busy = make_learner(db, reference)
    for version in (v1, v2):
        complete_lesson(db, busy, version)
    busy_client = make_client()
    login(busy_client, busy)
    open_attempt = busy_client.post(f"/api/v1/me/modules/{core.id}/attempts").json()["attempt_id"]

    release = client.post(RELEASES, json={"code": "2026.12"}).json()
    marked = client.post(f"{RELEASES}/{release['id']}/lessons/{one.id}").json()
    make_version_ready(db, client, marked["draft"]["id"])

    detail = client.get(f"{RELEASES}/{release['id']}").json()
    pool_problem = {
        "module_id": core.id, "code": "pool_too_small", "params": {"have": 6, "need": 9},
    }  # fmt: skip
    assert detail["module_problems"] == [pool_problem] and detail["ready"] is False
    refused = client.post(f"{RELEASES}/{release['id']}/publish")
    assert refused.status_code == 409 and error_code(refused) == "release.not_ready"
    assert refused.json()["error"]["params"]["problems"] == [pool_problem]

    # Questions for the new video are drafts until reviewed; drafts block the release.
    url = f"{ADMIN}/modules/{core.id}/questions"
    new_ids = [client.post(url, json=_question(one.id, d)).json()["id"] for d in (1, 2, 3)]
    detail = client.get(f"{RELEASES}/{release['id']}").json()
    assert detail["lessons"][0]["problems"] == ["questions_pending"]
    assert detail["module_problems"] == [pool_problem]  # drafts don't count towards the pool
    for qid in new_ids:
        assert client.post(f"{ADMIN}/questions/{qid}/approve").status_code == 200
    detail = client.get(f"{RELEASES}/{release['id']}").json()
    assert detail["module_problems"] == [] and detail["ready"] is True

    clock.advance(minutes=5)
    assert client.post(f"{RELEASES}/{release['id']}/publish").status_code == 200
    db.expire_all()

    retired = (QuestionStatus.retired, RetiredReason.lesson_changed)
    assert [(q.status, q.retired_reason) for q in old_questions] == [retired] * 3
    pool = client.get(f"{ADMIN}/modules/{core.id}/pool").json()
    assert (pool["approved_active"], pool["publishable"], pool["test_published"]) == (9, True, True)
    new = db.scalars(select(Question).where(Question.id.in_(new_ids))).all()
    assert {q.lesson_version_id for q in new} == {marked["draft"]["id"]}

    item = db.scalar(select(RemediationItem).where(RemediationItem.attempt_id == failed.id))
    assert item.satisfied_reason == RemediationResolution.superseded

    # The attempt that was open during the publish is still graded on what it served.
    result = busy_client.post(f"/api/v1/me/attempts/{open_attempt}/submit")
    assert result.status_code == 200 and result.json()["question_count"] == 3

    # The replaced lesson has to be watched again before the next attempt.
    login(client, learner)
    status = client.get(f"/api/v1/me/modules/{core.id}").json()["test"]["status"]
    lessons = next(r for r in status["reasons"] if r["code"] == "lessons_incomplete")
    assert lessons["params"] == {"completed": 1, "total": 2}
    assert "remediation_pending" not in [r["code"] for r in status["reasons"]]
