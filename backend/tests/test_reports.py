"""Readiness reports: buckets, overdue, filters, CSV, branch-head scoping, access list."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app import clock as app_clock
from app.models import WaveModuleRole
from app.models.enums import AccessRole
from app.services import certificates
from app.services.reports import Readiness, readiness
from tests.factories import (
    complete_lesson,
    give_certificate,
    login,
    make_learner,
    make_live_lesson,
    make_user,
    make_wave,
)


@pytest.fixture
def org(db, reference, clock):
    """Two branches in one wave: menejers take Core + Farovon, branch heads Core only."""
    core, farovon = reference.modules["CORE"], reference.modules["FAROVON"]
    wave = make_wave(
        db, [reference.tashkent, reference.samarqand], {reference.roles["menejer"]: [farovon]}
    )
    wave.deadline = app_clock.today() + timedelta(days=10)
    wave.go_live = wave.deadline + timedelta(days=15)
    _, core_v = make_live_lesson(db, core)
    make_live_lesson(db, farovon)
    people = {
        "certified": make_learner(db, reference),
        "recert": make_learner(db, reference),
        "progress": make_learner(db, reference),
        "idle": make_learner(db, reference),
        "head": make_learner(db, reference, "filial_rahbari"),
        "samarqand": make_learner(db, reference, branch=reference.samarqand),
    }
    people["head"].access_role = AccessRole.branch_head
    gone = make_learner(db, reference)
    gone.is_active = False  # left the bank: not counted
    for key in ("certified", "samarqand"):
        give_certificate(db, people[key], core)
        give_certificate(db, people[key], farovon)
    overdue_renewal = app_clock.utcnow() - timedelta(days=1)
    give_certificate(db, people["recert"], core, recert_due_at=overdue_renewal)
    give_certificate(db, people["recert"], farovon)
    give_certificate(db, people["head"], core)
    complete_lesson(db, people["progress"], core_v)
    for key in ("certified", "samarqand", "head"):
        certificates.evaluate_operator(db, people[key], app_clock.utcnow())
    db.flush()
    return {"wave": wave, "core": core, "farovon": farovon, **people}


def _admin(db, client):
    login(client, make_user(db, role=AccessRole.admin))


def test_buckets_are_exclusive_and_overdue_is_separate(db, client, reference, org, clock):
    _admin(db, client)
    summary = client.get("/api/v1/reports/summary").json()
    assert summary == {
        "total": 6, "branches": 2, "certified": 3, "certified_pct": 50, "recert_required": 1,
        "in_progress": 1, "not_started": 1, "overdue": 0, "latest_release": "T-LIVE",
    }  # fmt: skip

    # The deadline is a date: overdue starts at midnight after it, Tashkent time.
    end = app_clock.end_of_day(org["wave"].deadline)
    clock.now = end - timedelta(seconds=1)
    _admin(db, client)
    assert client.get("/api/v1/reports/summary").json()["overdue"] == 0
    clock.now = end
    _admin(db, client)
    assert client.get("/api/v1/reports/summary").json()["overdue"] == 3


def test_module_filter_reports_that_module_alone(db, client, reference, org):
    _admin(db, client)
    summary = client.get(
        "/api/v1/reports/summary", params={"module_id": org["farovon"].id}
    ).json()
    # Farovon is assigned to the five menejers only; two have not touched it.
    assert (summary["total"], summary["certified"], summary["not_started"]) == (5, 3, 2)
    by_region = client.get(
        "/api/v1/reports/summary", params={"region_id": reference.samarqand.region_id}
    ).json()
    assert (by_region["total"], by_region["certified"]) == (1, 1)


def test_branch_rows_carry_readiness(db, client, reference, org):
    _admin(db, client)
    rows = client.get("/api/v1/reports/branches").json()
    shown = [(r["branch"]["code"], r["total"], r["certified_pct"], r["readiness"]) for r in rows]
    assert shown == [
        ("11-101", 1, 100, "ready"),
        ("01-101", 5, 40, "not_ready"),
    ]
    assert rows[1]["recert_required"] == 1 and rows[1]["not_started"] == 1


def test_readiness_thresholds():
    assert readiness(9, 10) == readiness(90, 100) == Readiness.ready
    assert readiness(89, 100) == readiness(6, 10) == Readiness.at_risk
    assert readiness(59, 100) == readiness(0, 3) == readiness(0, 0) == Readiness.not_ready


def test_reports_export_as_excel_friendly_csv(db, client, reference, org):
    _admin(db, client)
    resp = client.get("/api/v1/reports/branches", params={"format": "csv", "lang": "ru"})
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/csv")
    text = resp.content.decode("utf-8")
    assert text.startswith("﻿")
    lines = text.lstrip("﻿").splitlines()
    assert lines[0].split(";")[:4] == ["Код филиала", "Филиал", "Регион", "Сотрудники"]
    assert lines[1].split(";")[0] == "11-101" and lines[1].endswith(";Готов")
    users = client.get("/api/v1/reports/users", params={"format": "csv"}).content.decode()
    assert users.lstrip("﻿").splitlines()[0].startswith("employee_id;F.I.Sh.;Filial kodi")
    assert len(users.strip().splitlines()) == 7  # header + 6 learners
    summary = client.get("/api/v1/reports/summary", params={"format": "csv"}).content.decode()
    assert "Sertifikatlangan;3" in summary


def test_user_rows_filter_and_page(db, client, reference, org):
    _admin(db, client)
    page = client.get("/api/v1/reports/users", params={"page_size": 2}).json()
    assert (page["total"], len(page["items"])) == (6, 2)
    recert = client.get("/api/v1/reports/users", params={"status": "recert_required"}).json()
    assert [u["user_id"] for u in recert["items"]] == [org["recert"].id]
    assert recert["items"][0]["modules_certified"] == 1 and recert["items"][0]["modules_total"] == 2
    found = client.get(
        "/api/v1/reports/users", params={"q": org["idle"].employee_id.lower()}
    ).json()
    assert [u["user_id"] for u in found["items"]] == [org["idle"].id]


def test_drill_down_shows_modules_attempts_and_certificates(db, client, reference, org):
    _admin(db, client)
    detail = client.get(f"/api/v1/reports/users/{org['certified'].id}").json()
    assert (detail["status"], detail["overdue"], detail["operator"]["status"]) == (
        "certified", False, "valid",
    )  # fmt: skip
    assert [(m["code"], m["state"]) for m in detail["modules"]] == [
        ("CORE", "certified"), ("FAROVON", "certified"),
    ]  # fmt: skip
    assert detail["modules"][0]["certificate"]["status"] == "valid"
    assert detail["modules"][0]["lessons_total"] == 1
    # The admin user page carries the same section.
    user_page = client.get(f"/api/v1/admin/users/{org['progress'].id}").json()
    assert [m["state"] for m in user_page["learning"]["modules"]] == ["in_progress", "not_started"]


def test_branch_heads_see_their_own_branch_only(db, client, make_client, reference, org):
    login(client, org["head"])
    other = {"branch_id": reference.samarqand.id}
    summary = client.get("/api/v1/reports/summary", params=other).json()
    assert summary["total"] == 5 and summary["branches"] == 1  # forced to 01-101
    codes = {r["branch"]["code"] for r in client.get("/api/v1/reports/branches").json()}
    assert codes == {"01-101"}
    assert client.get(f"/api/v1/reports/users/{org['samarqand'].id}").status_code == 404
    assert client.get(f"/api/v1/reports/users/{org['idle'].id}").status_code == 200
    assert client.get("/api/v1/exports/access-list.csv").status_code == 403

    learner = make_client()
    login(learner, org["idle"])
    assert learner.get("/api/v1/reports/summary").status_code == 403
    staff = make_client()
    login(staff, make_user(db, role=AccessRole.methodologist))
    assert staff.get("/api/v1/reports/summary").status_code == 403


def test_access_list_holds_only_fully_certified_learners(db, client, reference, org):
    _admin(db, client)

    def listed() -> list[str]:
        text = client.get("/api/v1/exports/access-list.csv").content.decode("utf-8")
        return sorted(line.split(";")[0] for line in text.lstrip("﻿").splitlines()[1:])

    expected = sorted(org[k].employee_id for k in ("certified", "samarqand", "head"))
    assert listed() == expected  # "recert" holds certificates but one needs renewal
    by_branch = client.get(
        "/api/v1/exports/access-list.csv", params={"branch_id": reference.samarqand.id}
    ).content.decode()
    assert org["samarqand"].employee_id in by_branch and org["head"].employee_id not in by_branch

    # A newly assigned module takes menejers off the list until they pass it.
    uzcard = reference.modules["UZCARD"]
    make_live_lesson(db, uzcard)
    db.add(WaveModuleRole(wave_id=org["wave"].id, module_id=uzcard.id,
                          job_role_id=reference.roles["menejer"].id))  # fmt: skip
    db.flush()
    assert listed() == [org["head"].employee_id]
