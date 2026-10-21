"""Waves (admin): dates, branches, role x module matrix; the learner home page."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app import clock as app_clock
from app.models import Job
from app.models.enums import AccessRole, JobKind
from tests.factories import (
    complete_lesson,
    give_certificate,
    login,
    make_learner,
    make_live_lesson,
    make_user,
    make_wave,
)

WAVES = "/api/v1/admin/waves"


def _admin(db, client):
    login(client, make_user(db, role=AccessRole.admin))


def _body(start: date, **extra) -> dict:
    return {
        "name_uz": "2-toʻlqin · Toshkent shahri", "name_ru": "2-я волна · г. Ташкент",
        "training_start": str(start), "deadline": str(start + timedelta(days=30)),
        "go_live": str(start + timedelta(days=45)), **extra,
    }  # fmt: skip


def test_waves_have_three_ordered_dates_and_a_derived_status(db, client, reference, clock):
    _admin(db, client)
    today = app_clock.today()
    bad = client.post(WAVES, json=_body(today, deadline=str(today - timedelta(days=1))))
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "wave.dates_invalid"

    planned = client.post(WAVES, json=_body(today + timedelta(days=1)))
    assert planned.status_code == 201 and planned.json()["status"] == "planned"
    active = client.post(WAVES, json=_body(today)).json()
    assert active["status"] == "active" and active["learners"] == 0
    done = client.post(WAVES, json=_body(today - timedelta(days=60))).json()
    assert done["status"] == "completed"
    assert [w["status"] for w in client.get(WAVES).json()] == ["completed", "active", "planned"]

    patched = client.patch(f"{WAVES}/{active['id']}", json={"name_uz": "Yangi nom"})
    assert patched.status_code == 200 and patched.json()["name_uz"] == "Yangi nom"
    late = client.patch(f"{WAVES}/{active['id']}", json={"go_live": str(today)})
    assert late.status_code == 400  # go-live before the deadline


def test_a_branch_belongs_to_one_wave_at_a_time(db, client, reference, clock):
    _admin(db, client)
    today = app_clock.today()
    first = client.post(WAVES, json=_body(today)).json()
    second = client.post(WAVES, json=_body(today)).json()
    make_learner(db, reference)  # one menejer in Tashkent

    ok = client.put(f"{WAVES}/{first['id']}/branches", json={"branch_ids": [reference.tashkent.id]})
    assert ok.status_code == 200 and (ok.json()["branches"], ok.json()["learners"]) == (1, 1)
    clash = client.put(
        f"{WAVES}/{second['id']}/branches", json={"branch_ids": [reference.tashkent.id]}
    )
    assert clash.status_code == 409
    assert clash.json()["error"] == {
        "code": "wave.branch_in_other_wave", "params": {"branch_ids": [reference.tashkent.id]},
    }  # fmt: skip
    unknown = client.put(f"{WAVES}/{second['id']}/branches", json={"branch_ids": [999999]})
    assert unknown.status_code == 400

    jobs = db.scalars(select(Job).where(Job.kind == JobKind.operator_cert_eval)).all()
    assert len(jobs) == 1 and len(jobs[0].payload["user_ids"]) == 1
    detail = client.get(f"{WAVES}/{first['id']}").json()
    assert [(b["code"], b["learners"]) for b in detail["branch_list"]] == [("01-101", 1)]


def test_role_module_matrix_takes_product_modules_only(db, client, reference, clock):
    _admin(db, client)
    wave = client.post(WAVES, json=_body(app_clock.today())).json()
    client.put(f"{WAVES}/{wave['id']}/branches", json={"branch_ids": [reference.tashkent.id]})
    menejer = reference.roles["menejer"].id
    core = {"job_role_id": menejer, "module_id": reference.modules["CORE"].id}
    faq = {"job_role_id": menejer, "module_id": reference.modules["FAQ"].id}
    for item in (core, faq):
        resp = client.put(f"{WAVES}/{wave['id']}/assignments", json={"items": [item]})
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "wave.module_not_assignable"

    farovon = {"job_role_id": menejer, "module_id": reference.modules["FAROVON"].id}
    detail = client.put(f"{WAVES}/{wave['id']}/assignments", json={"items": [farovon, farovon]})
    assert detail.status_code == 200
    body = detail.json()
    assert body["assignments"] == [farovon]
    assert [m["code"] for m in body["modules"]][0] == "CORE" and "FAQ" not in {
        m["code"] for m in body["modules"]
    }
    assert {r["code"] for r in body["roles"]} >= {"menejer", "filial_rahbari"}


def test_waves_are_admin_only(db, client, reference):
    login(client, make_user(db, role=AccessRole.methodologist))
    assert client.get(WAVES).status_code == 403


def test_learner_home_page(db, client, reference, clock):
    core, farovon = reference.modules["CORE"], reference.modules["FAROVON"]
    wave = make_wave(db, [reference.tashkent], {reference.roles["menejer"]: [farovon]})
    wave.deadline = app_clock.today() + timedelta(days=12)
    wave.go_live = wave.deadline + timedelta(days=14)
    one, v1 = make_live_lesson(db, core, title="Kirish")
    two, v2 = make_live_lesson(db, core, title="Mijozni qidirish")
    make_live_lesson(db, farovon, title="Mahsulot")
    learner = make_learner(db, reference)
    complete_lesson(db, learner, v1)
    login(client, learner)
    beat = f"/api/v1/me/lessons/{two.id}/heartbeat"
    client.post(beat, json={"version_id": v2.id, "ranges": []})
    clock.advance(seconds=20)
    client.post(beat, json={"version_id": v2.id, "ranges": [[0, 20]]})

    home = client.get("/api/v1/me/dashboard").json()
    assert home["wave"]["days_left"] == 12 and home["overdue"] is False
    assert (home["modules_certified"], home["modules_assigned"]) == (0, 2)
    assert [(m["code"], m["status"], m["locked"]) for m in home["path"]] == [
        ("CORE", "in_progress", False), ("FAROVON", "not_started", True),
    ]  # fmt: skip
    assert home["resume"]["lesson_id"] == two.id and home["resume"]["lesson_number"] == 2
    assert home["resume"]["watched_pct"] == 20
    assert home["operator_status"] == "missing" and home["certificates"] == []

    give_certificate(db, learner, core)
    home = client.get("/api/v1/me/dashboard").json()
    assert home["modules_certified"] == 1 and home["path"][0]["status"] == "certified"
    assert home["path"][1]["locked"] is False  # Core certificate opens the products
    assert [c["title_uz"] for c in home["certificates"]] == [core.title_uz]

    clock.now = app_clock.end_of_day(wave.deadline)
    login(client, learner)
    assert client.get("/api/v1/me/dashboard").json()["overdue"] is True


def test_home_page_without_a_wave(db, client, reference):
    learner = make_learner(db, reference)  # branch not in any wave yet
    login(client, learner)
    home = client.get("/api/v1/me/dashboard").json()
    assert home["wave"] is None and home["path"] == [] and home["resume"] is None
    assert (home["modules_certified"], home["modules_assigned"], home["overdue"]) == (0, 0, False)
