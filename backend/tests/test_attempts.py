"""Taking a test (rules 6 and 7): eligibility, the timer, grading, attempt cycles, remediation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app import clock as app_clock
from app.errors import AppError
from app.models import (
    AppUser,
    AttemptQuestion,
    AuditEvent,
    Lesson,
    LessonVersion,
    Module,
    Question,
    QuestionOption,
    RemediationItem,
    TestAttempt,
)
from app.models.enums import (
    AccessRole,
    AttemptStatus,
    QuestionType,
    RemediationResolution,
)
from app.services import attempts
from tests.factories import (
    answer_key,
    complete_lesson,
    error_code,
    login,
    make_learner,
    make_live_lesson,
    make_pool,
    make_question,
    make_user,
    make_wave,
    wrong_answer,
)

ME = "/api/v1/me"


@dataclass
class Ready:
    module: Module
    lessons: list[Lesson]
    versions: list[LessonVersion]
    learner: AppUser


def _ready(db, reference, *, n: int = 15, per_difficulty: int | None = None) -> Ready:
    """Core with one fully watched 600 s lesson and a published test of N from a 3 x N pool."""
    core = reference.modules["CORE"]
    core.test_question_count = n
    make_wave(db, [reference.tashkent], {})
    lesson, version = make_live_lesson(db, core, duration=600, title="Mijoz kartasi")
    make_pool(db, core, version, per_difficulty=per_difficulty or n)
    core.test_published_at = app_clock.utcnow()
    learner = make_learner(db, reference)
    complete_lesson(db, learner, version)
    return Ready(core, [lesson], [version], learner)


def _start(client, module_id: int) -> int:
    resp = client.post(f"{ME}/modules/{module_id}/attempts")
    assert resp.status_code == 201, resp.text
    return resp.json()["attempt_id"]


def _answer(client, attempt_id: int, position: int, answer, **extra):
    url = f"{ME}/attempts/{attempt_id}/answers/{position}"
    return client.put(url, json={"answer": answer, **extra})


def _take(db, client, module_id: int, correct: int, answered: int | None = None) -> dict:
    """Start, answer ``correct`` questions right and the rest of ``answered`` wrong, submit."""
    attempt_id = _start(client, module_id)
    key = answer_key(db, attempt_id)
    for i, position in enumerate(sorted(key)[:answered]):
        given = key[position] if i < correct else wrong_answer(db, attempt_id, position)
        assert _answer(client, attempt_id, position, given).status_code == 200
    result = client.post(f"{ME}/attempts/{attempt_id}/submit")
    assert result.status_code == 200, result.text
    return result.json()


def _status(client, module_id: int) -> dict:
    return client.get(f"{ME}/modules/{module_id}").json()["test"]["status"]


def _wait(clock, client, user: AppUser, **delta: float) -> None:
    """Move the frozen clock on; past the 60 min idle limit the browser logs in again."""
    clock.advance(**delta)
    login(client, user)


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _reason_codes(status: dict) -> list[str]:
    return [r["code"] for r in status["reasons"]]


def _watch_all_fragments(db, attempt_id: int) -> None:
    for item in db.scalars(select(RemediationItem).where(RemediationItem.attempt_id == attempt_id)):
        item.satisfied_at = app_clock.utcnow()
        item.satisfied_reason = RemediationResolution.watched
    db.flush()


# --- eligibility -----------------------------------------------------------------------------


def test_eligibility_lists_every_blocking_reason(db, client, reference, clock):
    farovon = reference.modules["FAROVON"]
    make_wave(db, [reference.tashkent], {reference.roles["menejer"]: [farovon]})
    lesson, version = make_live_lesson(db, farovon)
    make_live_lesson(db, farovon)
    learner = make_learner(db, reference)
    complete_lesson(db, learner, version)
    login(client, learner)

    status = _status(client, farovon.id)
    assert status["can_start"] is False
    expected = ["prerequisite_core", "lessons_incomplete", "test_not_published"]
    assert _reason_codes(status) == expected
    assert status["reasons"][1]["params"] == {"completed": 1, "total": 2}

    refused = client.post(f"{ME}/modules/{farovon.id}/attempts")
    assert refused.status_code == 409 and error_code(refused) == "test.not_available"
    assert [r["code"] for r in refused.json()["error"]["params"]["reasons"]] == expected

    unassigned = reference.modules["UZCARD"]
    assert client.post(f"{ME}/modules/{unassigned.id}/attempts").status_code == 404
    faq = reference.modules["FAQ"]
    assert client.post(f"{ME}/modules/{faq.id}/attempts").status_code == 404


def test_start_draws_a_balanced_test_without_the_answer_key(
    db, client, make_client, reference, clock
):
    ready = _ready(db, reference)
    login(client, ready.learner)
    assert _status(client, ready.module.id)["can_start"] is True

    started = client.post(f"{ME}/modules/{ready.module.id}/attempts")
    assert started.status_code == 201 and started.json()["created"] is True
    attempt_id = started.json()["attempt_id"]
    again = client.post(f"{ME}/modules/{ready.module.id}/attempts")
    assert again.status_code == 200 and again.json() == {"attempt_id": attempt_id, "created": False}

    view = client.get(f"{ME}/attempts/{attempt_id}")
    assert view.status_code == 200
    body = view.json()
    assert (body["status"], body["number"], body["question_count"]) == ("in_progress", 1, 15)
    assert _ts(body["expires_at"]) == clock.now + timedelta(minutes=20)
    assert [q["position"] for q in body["questions"]] == list(range(1, 16))
    for leak in ("is_correct", "explanation", "Izoh", "Пояснение", "difficulty"):
        assert leak not in view.text  # rule 7: no answer key, ever

    served = db.scalars(
        select(Question.difficulty)
        .join(AttemptQuestion, AttemptQuestion.question_id == Question.id)
        .where(AttemptQuestion.attempt_id == attempt_id)
    ).all()
    assert sorted(served) == [1] * 5 + [2] * 5 + [3] * 5
    shown = [[o["text_uz"] for o in q["options"]] for q in body["questions"]]
    authored = ["Variant 1", "Variant 2", "Variant 3", "Variant 4"]
    assert any(texts != authored for texts in shown)  # options are shuffled
    # Option ids follow the authored order, so they are never sent; only display positions.
    assert {tuple(o) for q in body["questions"] for o in q["options"]} == {
        ("index", "text_uz", "text_ru")
    }

    status = _status(client, ready.module.id)
    assert status["open_attempt_id"] == attempt_id
    assert _reason_codes(status) == ["attempt_in_progress"]

    stranger = make_client()
    login(stranger, make_learner(db, reference))
    hidden = stranger.get(f"{ME}/attempts/{attempt_id}")
    assert hidden.status_code == 404 and error_code(hidden) == "attempt.not_found"


def test_answers_are_validated_and_autosaved(db, client, reference, clock):
    ready = _ready(db, reference, n=3)
    login(client, ready.learner)
    attempt_id = _start(client, ready.module.id)
    key = answer_key(db, attempt_id)

    view = client.get(f"{ME}/attempts/{attempt_id}").json()
    assert [o["index"] for o in view["questions"][0]["options"]] == [0, 1, 2, 3]
    beyond = _answer(client, attempt_id, 1, [4])  # four options: indices 0-3
    assert beyond.status_code == 400 and error_code(beyond) == "attempt.answer_invalid"
    assert _answer(client, attempt_id, 1, [-1]).status_code == 422
    assert _answer(client, attempt_id, 1, [0, 1]).status_code == 400  # single: one option only

    saved = _answer(client, attempt_id, 1, key[1])
    assert saved.json() == {"position": 1, "answered": True, "flagged": False}
    flagged = client.put(f"{ME}/attempts/{attempt_id}/answers/1", json={"flagged": True})
    assert flagged.json() == {"position": 1, "answered": True, "flagged": True}  # answer kept
    view = client.get(f"{ME}/attempts/{attempt_id}").json()
    assert view["questions"][0]["answer"] == key[1] and view["answered"] == 1

    cleared = _answer(client, attempt_id, 1, None)
    assert cleared.json() == {"position": 1, "answered": False, "flagged": True}
    assert _answer(client, attempt_id, 1, []).json()["answered"] is False
    assert _answer(client, attempt_id, 9, key[1]).status_code == 404
    extra = client.put(f"{ME}/attempts/{attempt_id}/answers/1", json={"answer": None, "x": 1})
    assert extra.status_code == 422


def test_ordering_and_multiple_questions_are_answered_by_display_position(
    db, client, reference, clock
):
    core = reference.modules["CORE"]
    core.test_question_count = 2  # targets: one of difficulty 1, one of difficulty 2
    make_wave(db, [reference.tashkent], {})
    _, version = make_live_lesson(db, core)
    steps = make_question(db, core, version, q_type=QuestionType.ordering, options=3, difficulty=1)
    make_question(db, core, version, q_type=QuestionType.multiple, correct=(0, 2), difficulty=2)
    core.test_published_at = app_clock.utcnow()
    learner = make_learner(db, reference)
    complete_lesson(db, learner, version)
    login(client, learner)

    attempt_id = _start(client, core.id)
    view = client.get(f"{ME}/attempts/{attempt_id}").json()
    ordering = next(q for q in view["questions"] if q["type"] == "ordering")
    authored = [o.text_uz for o in steps.options]
    assert [o["text_uz"] for o in ordering["options"]] != authored  # never shown solved

    key = answer_key(db, attempt_id)
    for position, answer in key.items():
        saved = _answer(client, attempt_id, position, answer)
        assert saved.status_code == 200, saved.text
    reread = client.get(f"{ME}/attempts/{attempt_id}").json()
    assert {q["position"]: q["answer"] for q in reread["questions"]} == key
    result = client.post(f"{ME}/attempts/{attempt_id}/submit").json()
    assert (result["correct_count"], result["passed"]) == (2, True)


def test_multiple_and_ordering_answers_must_be_complete_sets():
    def question(q_type: QuestionType, n: int) -> Question:
        q = Question(type=q_type)
        q.options = [QuestionOption(id=i, sort=i, is_correct=False) for i in range(1, n + 1)]
        return q

    multiple = question(QuestionType.multiple, 4)
    assert attempts.validate_answer(multiple, [3, 1]) == [3, 1]
    ordering = question(QuestionType.ordering, 3)
    assert attempts.validate_answer(ordering, [3, 1, 2]) == [3, 1, 2]
    cases = [(multiple, [1, 1]), (multiple, [1, 9]), (ordering, [1, 2]), (ordering, [1, 2, 2])]
    for q, bad in cases:
        with pytest.raises(AppError) as err:
            attempts.validate_answer(q, bad)
        assert err.value.code == "attempt.answer_invalid"


# --- grading -----------------------------------------------------------------------------


def test_pass_threshold_12_of_15_passes_and_11_fails(db, client, make_client, reference, clock):
    ready = _ready(db, reference)
    login(client, ready.learner)
    passed = _take(db, client, ready.module.id, correct=12)
    assert (passed["passed"], passed["score_pct"], passed["correct_count"]) == (True, 80.0, 12)
    assert passed["remediation"] == [] and passed["remediation_complete"] is True
    assert passed["next_attempt_at"] is None
    assert _reason_codes(_status(client, ready.module.id)) == ["already_passed"]
    refused = client.post(f"{ME}/modules/{ready.module.id}/attempts")
    assert [r["code"] for r in refused.json()["error"]["params"]["reasons"]] == ["already_passed"]

    other = make_client()
    second = make_learner(db, reference)
    complete_lesson(db, second, ready.versions[0])
    login(other, second)
    failed = _take(db, other, ready.module.id, correct=11)
    assert (failed["passed"], failed["score_pct"], failed["correct_count"]) == (False, 73.33, 11)

    third = make_client()
    unanswered = make_learner(db, reference)
    complete_lesson(db, unanswered, ready.versions[0])
    login(third, unanswered)
    partial = _take(db, third, ready.module.id, correct=12, answered=12)  # 3 left blank
    assert (partial["passed"], partial["score_pct"]) == (True, 80.0)  # blanks counted wrong
    blank = make_client()
    fourth = make_learner(db, reference)
    complete_lesson(db, fourth, ready.versions[0])
    login(blank, fourth)
    assert _take(db, blank, ready.module.id, correct=11, answered=11)["passed"] is False


def test_submitting_twice_returns_the_same_result(db, client, reference, clock):
    ready = _ready(db, reference, n=3)
    login(client, ready.learner)
    attempt_id = _start(client, ready.module.id)
    early = client.get(f"{ME}/attempts/{attempt_id}/result")
    assert early.status_code == 409 and error_code(early) == "attempt.in_progress"
    first = client.post(f"{ME}/attempts/{attempt_id}/submit").json()
    clock.advance(minutes=1)
    second = client.post(f"{ME}/attempts/{attempt_id}/submit").json()
    assert first == second
    assert client.get(f"{ME}/attempts/{attempt_id}/result").json() == first
    finished = client.get(f"{ME}/attempts/{attempt_id}").json()
    assert finished["status"] == "submitted" and finished["questions"] == []
    late = _answer(client, attempt_id, 1, None)
    assert late.status_code == 409 and error_code(late) == "attempt.finished"


def test_answers_count_until_30_s_after_the_deadline(db, client, reference, clock):
    ready = _ready(db, reference, n=3)
    login(client, ready.learner)
    attempt_id = _start(client, ready.module.id)
    key = answer_key(db, attempt_id)
    deadline = clock.now + timedelta(minutes=20)

    clock.now = deadline + timedelta(seconds=29)
    assert _answer(client, attempt_id, 1, key[1]).status_code == 200  # network latency grace
    clock.now = deadline + timedelta(seconds=31)
    late = _answer(client, attempt_id, 2, key[2])
    assert late.status_code == 409 and error_code(late) == "attempt.expired"

    result = client.get(f"{ME}/attempts/{attempt_id}/result").json()
    assert (result["status"], result["correct_count"], result["passed"]) == ("expired", 1, False)
    assert result["time_spent_s"] == 20 * 60
    attempt = db.get(TestAttempt, attempt_id)
    assert attempt.submitted_at == deadline  # the cooldown runs from the deadline


def test_worker_sweep_grades_abandoned_attempts_and_updates_item_statistics(
    db, client, reference, clock
):
    ready = _ready(db, reference, n=3, per_difficulty=1)  # the pool is exactly the test
    login(client, ready.learner)
    attempt_id = _start(client, ready.module.id)
    key = answer_key(db, attempt_id)
    _answer(client, attempt_id, 1, key[1])
    _answer(client, attempt_id, 2, wrong_answer(db, attempt_id, 2))

    clock.advance(minutes=20, seconds=20)
    assert attempts.finalize_overdue(db, clock.now) == 0  # still inside the grace period
    clock.advance(seconds=20)
    assert attempts.finalize_overdue(db, clock.now) == 1
    attempt = db.get(TestAttempt, attempt_id)
    assert (attempt.status, attempt.correct_count, attempt.passed) == (
        AttemptStatus.expired, 1, False,
    )  # fmt: skip

    db.expire_all()  # statistics are bumped in SQL, not through the loaded objects
    served = {
        p: db.get(Question, db.get(AttemptQuestion, (attempt_id, p)).question_id) for p in key
    }
    assert [(served[p].stat_attempts, served[p].stat_correct) for p in (1, 2, 3)] == [
        (1, 1), (1, 0), (1, 0),
    ]  # fmt: skip


# --- attempt cycles --------------------------------------------------------------------------


def test_attempt_limit_and_24_hour_cooldown(db, client, make_client, reference, clock):
    ready = _ready(db, reference, n=3)
    login(client, ready.learner)
    first = _take(db, client, ready.module.id, correct=0)
    assert (first["number"], first["attempts_used"], first["attempts_left"]) == (1, 1, 2)
    assert _ts(first["next_attempt_at"]) == clock.now + timedelta(hours=24)
    status = _status(client, ready.module.id)
    assert _reason_codes(status) == ["cooldown", "remediation_pending"]

    _watch_all_fragments(db, first["attempt_id"])
    _wait(clock, client, ready.learner, hours=23, minutes=59)
    refused = client.post(f"{ME}/modules/{ready.module.id}/attempts")
    assert refused.status_code == 409
    assert [r["code"] for r in refused.json()["error"]["params"]["reasons"]] == ["cooldown"]
    clock.advance(minutes=1)  # exactly 24 h after the failed attempt
    second = _take(db, client, ready.module.id, correct=1)
    assert (second["number"], second["passed"]) == (2, False)

    _watch_all_fragments(db, second["attempt_id"])
    _wait(clock, client, ready.learner, hours=24)
    third = _take(db, client, ready.module.id, correct=2)
    assert (third["number"], third["attempts_left"], third["next_attempt_at"]) == (3, 0, None)
    assert [h["number"] for h in third["history"]] == [1, 2, 3]

    _watch_all_fragments(db, third["attempt_id"])
    _wait(clock, client, ready.learner, hours=24)
    status = _status(client, ready.module.id)
    assert _reason_codes(status) == ["attempts_exhausted"]  # the 4th attempt is refused
    assert status["reasons"][0]["params"] == {"max": 3} and status["attempts_used"] == 3
    assert client.post(f"{ME}/modules/{ready.module.id}/attempts").status_code == 409

    admin = make_client()
    login(admin, make_user(db, role=AccessRole.admin))
    reset = admin.post(
        f"/api/v1/admin/users/{ready.learner.id}/reset-attempts",
        json={"module_id": ready.module.id, "reason": "Tizim nosozligi, 2026-10-22"},
    )
    assert reset.status_code == 201, reset.text
    clock.advance(minutes=1)
    status = _status(client, ready.module.id)
    assert status["can_start"] is True and status["attempts_used"] == 0
    fresh = _take(db, client, ready.module.id, correct=0)
    assert (fresh["number"], fresh["attempts_used"]) == (1, 1)
    assert [h["attempt_id"] for h in fresh["history"]] == [fresh["attempt_id"]]  # new cycle


def test_cooldown_and_remediation_are_both_required(db, client, reference, clock):
    ready = _ready(db, reference, n=3)
    login(client, ready.learner)
    failed = _take(db, client, ready.module.id, correct=0)
    _wait(clock, client, ready.learner, hours=25)
    status = _status(client, ready.module.id)
    assert _reason_codes(status) == ["remediation_pending"]
    assert status["reasons"][0]["params"] == {"satisfied": 0, "total": 1}
    assert client.post(f"{ME}/modules/{ready.module.id}/attempts").status_code == 409
    _watch_all_fragments(db, failed["attempt_id"])
    assert _status(client, ready.module.id)["can_start"] is True


def test_reset_is_admin_only_needs_a_reason_and_is_audited(
    db, client, make_client, reference, clock
):
    ready = _ready(db, reference, n=3)
    login(client, ready.learner)
    attempt_id = _start(client, ready.module.id)  # left open: the reset grades it
    url = f"/api/v1/admin/users/{ready.learner.id}/reset-attempts"

    staff = make_client()
    login(staff, make_user(db, role=AccessRole.methodologist))
    body = {"module_id": ready.module.id, "reason": "Sabab"}
    assert staff.post(url, json=body).status_code == 403

    admin = make_client()
    login(admin, make_user(db, role=AccessRole.admin))
    blank = admin.post(url, json={"module_id": ready.module.id, "reason": "   "})
    assert blank.status_code == 400 and error_code(blank) == "reset.reason_required"
    assert admin.post(url, json={"module_id": ready.module.id}).status_code == 422
    faq = {"module_id": reference.modules["FAQ"].id, "reason": "Sabab"}
    assert admin.post(url, json=faq).status_code == 404

    clock.advance(minutes=5)
    done = admin.post(url, json={"module_id": ready.module.id, "reason": "  Elektr uzildi  "})
    assert done.status_code == 201 and done.json()["reason"] == "Elektr uzildi"
    assert db.get(TestAttempt, attempt_id).status == AttemptStatus.expired
    event = db.scalar(select(AuditEvent).where(AuditEvent.action == "attempts.reset"))
    assert (event.target_user_id, event.reason) == (ready.learner.id, "Elektr uzildi")
    detail = admin.get(f"/api/v1/admin/users/{ready.learner.id}").json()
    assert detail["audit"][0]["action"] == "attempts.reset"


# --- remediation -----------------------------------------------------------------------------


def _remediation_setup(db, reference):
    """N = 3 from exactly three questions: two in lesson 1 (ts 100 and 130), one in lesson 2."""
    core = reference.modules["CORE"]
    core.test_question_count = 3
    make_wave(db, [reference.tashkent], {})
    one, v1 = make_live_lesson(db, core, duration=600, title="Ariza")
    two, v2 = make_live_lesson(db, core, duration=300, title="Garov")
    make_question(db, core, v1, difficulty=1, ts=100)
    make_question(db, core, v1, difficulty=2, ts=130)
    make_question(db, core, v2, difficulty=3, ts=280)
    core.test_published_at = app_clock.utcnow()
    learner = make_learner(db, reference)
    complete_lesson(db, learner, v1)
    complete_lesson(db, learner, v2)
    return core, (one, v1), (two, v2), learner


def test_failed_test_assigns_fragments_without_revealing_answers(db, client, reference, clock):
    core, (one, v1), (two, v2), learner = _remediation_setup(db, reference)
    login(client, learner)
    attempt_id = _start(client, core.id)
    for position in (1, 2, 3):
        _answer(client, attempt_id, position, wrong_answer(db, attempt_id, position))
    resp = client.post(f"{ME}/attempts/{attempt_id}/submit")
    result = resp.json()
    assert result["passed"] is False and result["remediation_complete"] is False
    assert result["remediation"] == [
        {
            "lesson_id": one.id, "lesson_title_uz": "Ariza", "lesson_title_ru": "Ariza (ru)",
            "missed_count": 2, "span_start_s": 85.0, "span_end_s": 205.0, "watched_pct": 0,
            "satisfied": False,
        },
        {
            "lesson_id": two.id, "lesson_title_uz": "Garov", "lesson_title_ru": "Garov (ru)",
            "missed_count": 1, "span_start_s": 265.0, "span_end_s": 300.0, "watched_pct": 0,
            "satisfied": False,
        },
    ]  # fmt: skip
    for leak in ("is_correct", "explanation", "Izoh", "Пояснение", "Variant"):
        assert leak not in resp.text

    player = client.get(f"{ME}/lessons/{one.id}").json()
    assert player["remediation"] == [
        {"span_start_s": 85.0, "span_end_s": 205.0, "watched_pct": 0, "satisfied": False}
    ]


def test_fragment_counts_once_90_percent_is_replayed_after_the_fail(db, client, reference, clock):
    core, (one, v1), (two, v2), learner = _remediation_setup(db, reference)
    login(client, learner)  # both lessons were fully watched before the test
    attempt_id = _start(client, core.id)
    client.post(f"{ME}/attempts/{attempt_id}/submit")  # nothing answered: all three missed
    assert _reason_codes(_status(client, core.id)) == ["cooldown", "remediation_pending"]

    beat = f"{ME}/lessons/{one.id}/heartbeat"

    def play(*ranges):
        clock.advance(seconds=30)
        resp = client.post(beat, json={"version_id": v1.id, "ranges": list(ranges)})
        assert resp.status_code == 200, resp.text

    client.post(beat, json={"version_id": v1.id, "ranges": []})  # starts the clock
    play([300, 360])  # outside the fragment [85, 205]
    play([85, 145])
    play([145, 192])
    fragment = client.get(f"{ME}/lessons/{one.id}").json()["remediation"][0]
    assert (fragment["watched_pct"], fragment["satisfied"]) == (89, False)  # 107 of 120 s
    play([192, 194])
    fragment = client.get(f"{ME}/lessons/{one.id}").json()["remediation"][0]
    assert fragment["satisfied"] is True

    status = _status(client, core.id)
    assert status["reasons"][1] == {
        "code": "remediation_pending", "params": {"satisfied": 1, "total": 2},
    }  # fmt: skip

    beat2 = f"{ME}/lessons/{two.id}/heartbeat"
    client.post(beat2, json={"version_id": v2.id, "ranges": []})
    clock.advance(seconds=30)
    client.post(beat2, json={"version_id": v2.id, "ranges": [[265, 300]]})
    result = client.get(f"{ME}/attempts/{attempt_id}/result").json()
    assert result["remediation_complete"] is True
    assert [r["satisfied"] for r in result["remediation"]] == [True, True]
    _wait(clock, client, learner, hours=24)
    assert _status(client, core.id)["can_start"] is True


def test_fragment_at_the_very_end_of_a_video_is_still_watchable():
    from app.services import remediation

    assert remediation.span([590.0], 600.0) == (575.0, 600.0)
    assert remediation.span([600.0], 600.0) == (585.0, 600.0)
    assert remediation.span([700.0], 600.0) == (599.0, 600.0)  # stale timestamp: last second
    assert remediation.span([0], 30.0) == (0.0, 30.0)
    assert remediation.span([10, 400], 1000.0) == (0.0, 475.0)
