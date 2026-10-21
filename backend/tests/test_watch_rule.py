"""Rule 3: a lesson is complete at ≥ 90 % watched, tracked on the server from heartbeats.

Seeking past the furthest point reached is blocked on the first viewing and free
after completion. The client never sends a completion flag.
"""

from __future__ import annotations

import pytest

from app.services import watch
from tests.factories import error_code, login, make_learner, make_live_lesson, make_wave

# --- the rule as pure functions -----------------------------------------------------------


def _beat(state: dict, ranges, elapsed: float = 10.0) -> watch.Credit:
    result = watch.credit(
        watched=state["watched"],
        incoming=ranges,
        duration=100.0,
        max_position_s=state["max"],
        completed=state["completed"],
        elapsed_s=elapsed,
    )
    state["watched"], state["max"] = result.watched, result.max_position_s
    state["completed"] = state["completed"] or watch.is_complete(result.watched_s, 100.0)
    return result


def _fresh() -> dict:
    return {"watched": [], "max": 0.0, "completed": False}


def test_merge_and_total():
    assert watch.merge([(10, 20), (0, 5), (5, 8), (19, 30)]) == [(0, 8), (10, 30)]
    assert watch.total([(0, 10), (5, 15), (20, 25)]) == 20


def test_watching_straight_through_completes_at_exactly_90_percent():
    state = _fresh()
    for start in range(0, 80, 10):
        _beat(state, [(start, start + 10)])
    result = _beat(state, [(80, 89.9)])
    assert result.watched_s == pytest.approx(89.9) and not state["completed"]
    _beat(state, [(89.9, 90.0)], elapsed=1)
    assert state["completed"]


def test_seeking_ahead_is_not_counted_on_first_viewing():
    state = _fresh()
    _beat(state, [(0, 10), (10, 20)], elapsed=20)
    result = _beat(state, [(60, 70)])  # jumped from 20 s to 60 s
    assert result.accepted == [] and result.watched_s == 20
    result = _beat(state, [(24, 34)])  # a small jump within the 5 s tolerance is fine
    assert result.accepted == [(24, 34)]


def test_after_completion_seeking_is_free():
    state = _fresh()
    for start in range(0, 90, 10):
        _beat(state, [(start, start + 10)])
    _beat(state, [(90, 91)], elapsed=1)
    assert state["completed"] and state["max"] == 91
    assert _beat(state, [(99, 100)], elapsed=1).accepted == [(99, 100)]


def test_credit_is_capped_by_wall_clock_time():
    state = _fresh()
    result = _beat(state, [(0, 60)], elapsed=10)  # claims 60 s of play after 10 s
    assert result.watched_s == pytest.approx(11.5)  # 10 s + 15 % tolerance


def test_a_long_pause_counts_as_at_most_30_seconds():
    state = _fresh()
    result = _beat(state, [(0, 100)], elapsed=2 * 24 * 3600)
    assert result.watched_s == pytest.approx(30 * 1.15)


def test_frequent_heartbeats_cannot_speed_up_crediting():
    state = _fresh()
    for second in range(60):  # a heartbeat every second, each claiming 3 s of play
        _beat(state, [(second * 3, second * 3 + 3)], elapsed=1)
    assert sum(b - a for a, b in state["watched"]) <= 60 * 1.15 + 1e-6


def test_two_tabs_share_one_clock():
    state = _fresh()
    for i in range(10):  # two tabs alternate, 5 s apart, each claiming 10 s
        _beat(state, [(i * 10, i * 10 + 10)], elapsed=5)
    assert watch.total(state["watched"]) <= 50 * 1.15 + 1e-6


def test_replaying_adds_no_coverage_and_speed_is_capped_after_completion():
    state = _fresh()
    _beat(state, [(0, 10)])
    assert _beat(state, [(0, 10)]).watched_s == 10
    state["completed"] = True
    result = _beat(state, [(10, 60)], elapsed=10)  # 2x allowed after completion
    assert sum(b - a for a, b in result.accepted) == pytest.approx(23)


def test_ranges_are_clipped_to_the_video():
    state = _fresh()
    result = _beat(state, [(-5, 3), (98, 120)], elapsed=30)
    assert result.accepted == [(0, 3)]  # 98-120 starts beyond the first-viewing limit
    assert watch.clean([(-5, 3), (98, 120)], 100) == [(0, 3), (98, 100)]


# --- the rule through the API -------------------------------------------------------------


@pytest.fixture
def lesson_setup(db, reference):
    core = reference.modules["CORE"]
    make_wave(db, [reference.tashkent], {})
    lesson, version = make_live_lesson(db, core, duration=100.0)
    return make_learner(db, reference), lesson, version


def _heartbeat(client, lesson, version, ranges, position=0.0):
    return client.post(
        f"/api/v1/me/lessons/{lesson.id}/heartbeat",
        json={"version_id": version.id, "ranges": ranges, "position_s": position},
    )


def test_heartbeats_complete_a_lesson_on_the_server(db, client, clock, lesson_setup):
    learner, lesson, version = lesson_setup
    login(client, learner)
    player = client.get(f"/api/v1/me/lessons/{lesson.id}").json()
    assert player["tracking"] and player["seek_limit_s"] == 0
    assert player["speed_change_allowed"] is False

    assert _heartbeat(client, lesson, version, []).status_code == 200  # starts the clock
    for start in range(0, 90, 10):
        clock.advance(seconds=10)
        body = _heartbeat(client, lesson, version, [[start, start + 10]], start + 10).json()
    assert body["completed"] is True and body["watched_pct"] == 90

    player = client.get(f"/api/v1/me/lessons/{lesson.id}").json()
    assert player["progress"]["completed"] is True
    assert player["seek_limit_s"] is None and player["speed_change_allowed"] is True


def test_client_cannot_claim_completion(db, client, clock, lesson_setup):
    learner, lesson, version = lesson_setup
    login(client, learner)
    forged = client.post(
        f"/api/v1/me/lessons/{lesson.id}/heartbeat",
        json={"version_id": version.id, "ranges": [], "completed": True},
    )
    assert forged.status_code == 422  # unknown fields are rejected
    _heartbeat(client, lesson, version, [])
    clock.advance(seconds=1)
    body = _heartbeat(client, lesson, version, [[0, 100]]).json()
    assert body["completed"] is False and body["watched_s"] == pytest.approx(1.15)


def test_seek_limit_follows_the_furthest_point_watched(db, client, clock, lesson_setup):
    learner, lesson, version = lesson_setup
    login(client, learner)
    _heartbeat(client, lesson, version, [])
    for start in (0, 10, 20):
        clock.advance(seconds=10)
        _heartbeat(client, lesson, version, [[start, start + 10]], start + 10)
    clock.advance(seconds=10)
    skipped = _heartbeat(client, lesson, version, [[70, 80]], 80).json()
    assert skipped["watched_s"] == 30
    player = client.get(f"/api/v1/me/lessons/{lesson.id}").json()
    assert player["seek_limit_s"] == 30
    assert player["progress"]["last_position_s"] == 30  # resume point clamped to the limit


def test_heartbeat_for_a_replaced_version_is_rejected(db, client, lesson_setup):
    learner, lesson, version = lesson_setup
    login(client, learner)
    resp = client.post(
        f"/api/v1/me/lessons/{lesson.id}/heartbeat",
        json={"version_id": version.id + 999, "ranges": []},
    )
    assert resp.status_code == 409
    assert error_code(resp) == "lesson.version_changed"
    assert resp.json()["error"]["params"]["current_version_id"] == version.id


def test_faq_lessons_are_open_and_untracked(db, client, reference):
    lesson, version = make_live_lesson(db, reference.modules["FAQ"], duration=60)
    learner = make_learner(db, reference)  # no wave needed for FAQ
    login(client, learner)
    player = client.get(f"/api/v1/me/lessons/{lesson.id}").json()
    assert player["tracking"] is False and player["seek_limit_s"] is None
    resp = _heartbeat(client, lesson, version, [[0, 10]])
    assert resp.status_code == 400
    assert error_code(resp) == "lesson.not_tracked"
    assert [item["id"] for item in client.get("/api/v1/me/faq").json()] == [lesson.id]
