"""Practice time stops on leave/finish and never includes a multi-day absence."""

from datetime import timedelta
from pathlib import Path

from alembic import command as migrate
from alembic.config import Config
from sqlalchemy import delete, select, text

from app.models.practice import PracticeAction, PracticeResult
from app.services import practice, practice_time
from tests.factories import login, make_learner
from tests.test_practice import (
    setup,
    finish_demo,
    advance,
)  # noqa: F401 -- shared fixture


def presence(
    client, session_id, active=True, sequence=1, client_id="browser-one", **extra
):
    return client.post(
        f"/api/v1/me/practice-sessions/{session_id}/activity",
        json={
            "client_id": client_id,
            "active": active,
            "sequence": sequence,
            **extra,
        },
    )


def test_pause_resume_across_days_and_finish_are_frozen(clock, db, setup, client):
    _, user, row = setup
    s = practice.start(db, user, row.id, "guided")
    started = s.started_at
    login(client, user)
    assert presence(client, s.id).json()["elapsed_s"] == 0
    clock.advance(seconds=12)
    assert presence(client, s.id, False, 2).json()["elapsed_s"] == 12
    clock.advance(days=4)
    login(client, user)
    assert presence(client, s.id, True, 3).json()["elapsed_s"] == 12
    clock.advance(seconds=8)
    assert presence(client, s.id, True, 4).json()["elapsed_s"] == 20
    finish_demo(db, user, s)
    result = practice.result_data(db, s.id)
    assert result["duration_s"] == 20 and not result["duration_estimated"]
    assert s.started_at == started
    clock.advance(days=2)
    login(client, user)
    assert presence(client, s.id, True, 5).json()["elapsed_s"] == 20
    assert practice.result_data(db, s.id) == result


def test_overlapping_tabs_count_once_and_pause_independently(clock, db, setup, client):
    _, user, row = setup
    s = practice.start(db, user, row.id, "guided")
    login(client, user)
    presence(client, s.id)
    clock.advance(seconds=10)
    presence(client, s.id, client_id="browser-two")
    clock.advance(seconds=10)
    assert presence(client, s.id, False, 2).json()["elapsed_s"] == 20
    clock.advance(seconds=10)
    assert presence(client, s.id, False, 2, "browser-two").json()["elapsed_s"] == 30
    clock.advance(minutes=5)
    assert practice.payload(db, s)["elapsed_s"] == 30
    assert s.revision == 0 and s.state["screen"] == "start"


def test_heartbeat_after_a_crash_counts_at_most_one_lease(clock, db, setup, client):
    _, user, row = setup
    s = practice.start(db, user, row.id, "guided")
    login(client, user)
    presence(client, s.id)
    clock.advance(days=4)
    login(client, user)
    assert presence(client, s.id, True, 2).json()["elapsed_s"] == practice_time.LEASE_S


def test_delayed_requests_cannot_restart_a_paused_clock(clock, db, setup, client):
    _, user, row = setup
    s = practice.start(db, user, row.id, "guided")
    login(client, user)
    presence(client, s.id, sequence=1)
    clock.advance(seconds=10)
    presence(client, s.id, False, 3)
    clock.advance(seconds=5)
    assert presence(client, s.id, True, 2).json()["elapsed_s"] == 10
    clock.advance(seconds=10)
    assert practice.payload(db, s)["elapsed_s"] == 10


def test_presence_uses_server_time_and_requires_ownership(
    clock, db, setup, client, reference
):
    _, user, row = setup
    s = practice.start(db, user, row.id, "guided")
    login(client, user)
    assert presence(client, s.id, elapsed_s=99999).status_code == 422
    assert presence(client, s.id, sequence=-1).status_code == 422
    assert presence(client, s.id, client_id="x").status_code == 422
    assert presence(client, s.id).status_code == 200
    advance(db, user, s, kind="save")  # heartbeats never invalidate command revisions
    stranger = make_learner(db, reference)
    login(client, stranger)
    assert presence(client, s.id).status_code == 404


def test_many_tabs_have_bounded_timer_storage(clock):
    timing = practice_time.initial(clock.now)
    for index in range(25):
        timing = practice_time.activity(timing, clock.now, f"browser-{index}", True, 1)
    assert len(timing["clients"]) == practice_time.MAX_CLIENTS


def test_historical_backfill_removes_days_and_preserves_original_duration(
    clock, db, setup
):
    _, user, row = setup
    s = practice.start(db, user, row.id, "guided")
    finish_demo(db, user, s)
    end = s.started_at + timedelta(days=4)
    s.finished_at = end
    result = db.scalar(select(PracticeResult).where(PracticeResult.session_id == s.id))
    result.duration_s = 4 * 86400
    db.execute(delete(PracticeAction).where(PracticeAction.session_id == s.id))
    for index, at in enumerate(
        (s.started_at + timedelta(seconds=10), end - timedelta(seconds=20))
    ):
        db.add(
            PracticeAction(
                session_id=s.id,
                request_id=f"historical-{index}",
                fingerprint="0" * 64,
                screen_id="start",
                kind="action",
                errors=[],
                response={},
                created_at=at,
            )
        )
    db.flush()
    sid = s.id
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.attributes.update(connection=db.connection(), configure_logger=False)
    migrate.downgrade(cfg, "0003")
    migrate.upgrade(cfg, "head")
    db.expire_all()
    s = practice.owned(db, user, sid)
    assert s.timing["estimated"] is True
    assert s.timing["legacy_wall_seconds"] == 4 * 86400
    assert practice.result_data(db, sid)["duration_s"] == 75  # 10 + bounded gap 45 + 20
    migrate.downgrade(cfg, "0003")
    assert (
        db.connection().scalar(
            text("SELECT duration_s FROM practice_result WHERE session_id=:id"),
            {"id": sid},
        )
        == 4 * 86400
    )
    migrate.upgrade(cfg, "head")
