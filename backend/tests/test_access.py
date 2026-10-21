"""Rule 2 and assignments: Core must be certified before any product module unlocks;
learners see only the modules assigned to their job role in their branch's wave."""

from __future__ import annotations

from datetime import timedelta

from app import clock
from tests.factories import (
    error_code,
    give_certificate,
    login,
    make_learner,
    make_live_lesson,
    make_wave,
)


def _setup(db, reference):
    m = reference.modules
    make_wave(
        db, [reference.tashkent], {reference.roles["menejer"]: [m["FAROVON"], m["UZCARD"]]}
    )
    core_lesson, _ = make_live_lesson(db, m["CORE"], title="Kirish")
    farovon_lesson, _ = make_live_lesson(db, m["FAROVON"], title="Mahsulot")
    make_live_lesson(db, m["LEGAL"], title="Yuridik")  # live, but not assigned to Menejer
    return core_lesson, farovon_lesson


def _modules(client) -> dict[str, dict]:
    return {m["code"]: m for m in client.get("/api/v1/me/modules").json()}


def test_learner_sees_core_plus_the_modules_of_their_role(db, client, reference):
    _setup(db, reference)
    login(client, make_learner(db, reference))
    # UZCARD is assigned but has no live lessons yet, so it is hidden.
    assert list(_modules(client)) == ["CORE", "FAROVON"]


def test_branch_outside_any_wave_sees_no_modules(db, client, reference):
    _setup(db, reference)
    login(client, make_learner(db, reference, branch=reference.samarqand))
    assert client.get("/api/v1/me/modules").json() == []


def test_product_module_unlocks_only_after_the_core_certificate(db, client, reference):
    core_lesson, farovon_lesson = _setup(db, reference)
    learner = make_learner(db, reference)
    login(client, learner)

    modules = _modules(client)
    assert modules["CORE"]["locked"] is False
    assert modules["FAROVON"]["locked"] is True
    assert client.get(f"/api/v1/me/lessons/{core_lesson.id}").status_code == 200
    blocked = client.get(f"/api/v1/me/lessons/{farovon_lesson.id}")
    assert blocked.status_code == 403
    assert error_code(blocked) == "module.locked"
    beat = client.post(
        f"/api/v1/me/lessons/{farovon_lesson.id}/heartbeat", json={"version_id": 1, "ranges": []}
    )
    assert beat.status_code == 403

    give_certificate(db, learner, reference.modules["CORE"])
    assert _modules(client)["FAROVON"]["locked"] is False
    assert client.get(f"/api/v1/me/lessons/{farovon_lesson.id}").status_code == 200


def test_core_awaiting_recertification_keeps_products_open(db, client, reference):
    _, farovon_lesson = _setup(db, reference)
    learner = make_learner(db, reference)
    give_certificate(
        db, learner, reference.modules["CORE"], recert_due_at=clock.utcnow() - timedelta(days=1)
    )
    login(client, learner)
    assert client.get(f"/api/v1/me/lessons/{farovon_lesson.id}").status_code == 200


def test_a_superseded_core_certificate_alone_does_not_unlock(db, client, reference):
    _, farovon_lesson = _setup(db, reference)
    learner = make_learner(db, reference)
    give_certificate(db, learner, reference.modules["CORE"], superseded=True)
    login(client, learner)
    assert client.get(f"/api/v1/me/lessons/{farovon_lesson.id}").status_code == 403


def test_a_product_certificate_does_not_unlock_other_products(db, client, reference):
    _, farovon_lesson = _setup(db, reference)
    learner = make_learner(db, reference)
    give_certificate(db, learner, reference.modules["UZCARD"])
    login(client, learner)
    assert client.get(f"/api/v1/me/lessons/{farovon_lesson.id}").status_code == 403


def test_unassigned_modules_and_their_lessons_are_hidden(db, client, reference):
    _setup(db, reference)
    legal = reference.modules["LEGAL"]
    learner = make_learner(db, reference)
    give_certificate(db, learner, reference.modules["CORE"])
    login(client, learner)
    assert client.get(f"/api/v1/me/modules/{legal.id}").status_code == 404
    legal_lesson = legal.lessons[0]
    assert client.get(f"/api/v1/me/lessons/{legal_lesson.id}").status_code == 404


def test_role_decides_the_product_modules(db, client, reference):
    m = reference.modules
    make_wave(
        db,
        [reference.tashkent],
        {
            reference.roles["menejer"]: [m["FAROVON"]],
            reference.roles["korporativ_menejer"]: [m["LEGAL"]],
        },
    )
    for module in (m["CORE"], m["FAROVON"], m["LEGAL"]):
        make_live_lesson(db, module)
    login(client, make_learner(db, reference, role_code="korporativ_menejer"))
    assert list(_modules(client)) == ["CORE", "LEGAL"]
