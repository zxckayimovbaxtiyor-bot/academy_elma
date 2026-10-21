"""Certificates (rule 8) and delta recertification after a release (rule 9)."""

from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import select

from app.models import AuditEvent, Certificate, Job, LessonVersion, TestAttempt
from app.models.enums import AccessRole, AttemptStatus, CertificateKind, JobKind, JobStatus
from app.services import certificates
from app.worker import operator_certs  # noqa: F401  (registers the job handler)
from app.worker.runner import run_job
from tests.factories import (
    complete_lesson,
    login,
    make_learner,
    make_live_lesson,
    make_user,
    make_wave,
    pass_test,
    publish_release,
    ready_module,
)

ME = "/api/v1/me"


def _status(client, module_id: int) -> dict:
    return client.get(f"{ME}/modules/{module_id}").json()["test"]["status"]


def _current(db, user, kind=CertificateKind.module, module=None) -> Certificate | None:
    stmt = select(Certificate).where(
        Certificate.user_id == user.id, Certificate.kind == kind,
        Certificate.superseded_at.is_(None),
    )  # fmt: skip
    if module is not None:
        stmt = stmt.where(Certificate.module_id == module.id)
    return db.scalar(stmt)


def _core_and_farovon(db, reference):
    """A menejer assigned Core + Farovon, both with live lessons and published tests.

    Farovon has two lessons; its pool sits on the second, so a release that replaces
    the first one keeps the pool intact.
    """
    core, farovon = reference.modules["CORE"], reference.modules["FAROVON"]
    make_wave(db, [reference.tashkent], {reference.roles["menejer"]: [farovon]})
    core_lessons = ready_module(db, core)
    farovon_lessons = ready_module(db, farovon, lessons=2)
    learner = make_learner(db, reference)
    for _, version in core_lessons + farovon_lessons:
        complete_lesson(db, learner, version)
    return core, farovon, farovon_lessons, learner


def test_passing_a_test_issues_a_numbered_module_certificate(db, client, reference, clock):
    core = reference.modules["CORE"]
    make_wave(db, [reference.tashkent], {})
    [(_, version)] = ready_module(db, core)
    learner = make_learner(db, reference)
    complete_lesson(db, learner, version)
    login(client, learner)

    result = pass_test(db, client, core.id)
    assert result["passed"] is True
    cert = _current(db, learner, module=core)
    assert re.fullmatch(r"YO-2026-\d{6}", cert.number)
    assert re.fullmatch(r"[A-HJ-NP-Z2-9]{10}", cert.verify_code)
    assert (cert.score_pct, cert.recert_due_at) == (100.0, None)
    assert cert.release_id == core.current_release_id
    holder = {"full_name": learner.full_name, "employee_id": learner.employee_id}
    assert cert.snapshot["holder"] == holder
    assert cert.snapshot["branch"]["code"] == "01-101" and cert.snapshot["region"]["code"] == "01"
    assert [m["code"] for m in cert.snapshot["modules"]] == ["CORE"]
    assert db.scalar(select(AuditEvent).where(AuditEvent.action == "cert.issued")) is not None

    listed = client.get(f"{ME}/certificates").json()
    # Core alone is everything this learner is assigned: the operator certificate follows.
    kinds = [(c["kind"], c["status"]) for c in listed]
    assert kinds == [("operator", "valid"), ("module", "valid")]
    assert listed[1]["number"] == cert.number and listed[1]["score_pct"] == 100.0
    assert listed[1]["verify_url"].endswith(f"/verify/{cert.number}?c={cert.verify_code}")
    assert [r["code"] for r in _status(client, core.id)["reasons"]] == ["already_passed"]


def test_operator_certificate_needs_core_and_every_assigned_module(db, client, reference, clock):
    core, farovon, _, learner = _core_and_farovon(db, reference)
    login(client, learner)

    pass_test(db, client, core.id)
    assert _current(db, learner, CertificateKind.operator) is None  # Farovon still missing
    clock.advance(minutes=5)
    pass_test(db, client, farovon.id)
    operator = _current(db, learner, CertificateKind.operator)
    covered = [_current(db, learner, module=core).id, _current(db, learner, module=farovon).id]
    assert sorted(operator.covers) == sorted(covered)
    assert [m["code"] for m in operator.snapshot["modules"]] == ["CORE", "FAROVON"]
    assert operator.module_id is None and operator.attempt_id is None
    statuses = {c["kind"]: c["status"] for c in client.get(f"{ME}/certificates").json()}
    assert statuses == {"operator": "valid", "module": "valid"}


def test_release_touching_one_module_recertifies_only_that_module(
    db, client, make_client, reference, clock
):
    core, farovon, farovon_lessons, learner = _core_and_farovon(db, reference)
    login(client, learner)
    pass_test(db, client, core.id)
    pass_test(db, client, farovon.id)
    core_cert = _current(db, learner, module=core)
    old_farovon = _current(db, learner, module=farovon)
    old_operator = _current(db, learner, CertificateKind.operator)

    clock.advance(days=3)
    admin = make_client()
    login(admin, make_user(db, role=AccessRole.admin))
    changed_lesson = farovon_lessons[0][0]
    new_versions = publish_release(db, admin, [changed_lesson], "2026.12", transition_days=0)
    login(client, learner)  # three days later: a new session

    now = clock.now
    assert certificates.module_status(db.get(Certificate, core_cert.id), now) == "valid"
    assert db.get(Certificate, core_cert.id).recert_due_at is None  # Core untouched
    assert db.get(Certificate, old_farovon.id).recert_due_at == now
    assert certificates.module_status(db.get(Certificate, old_farovon.id), now) == "recert_required"
    assert certificates.certificate_status(db, old_operator, now) == "recert_required"
    statuses = {c["number"]: c["status"] for c in client.get(f"{ME}/certificates").json()}
    assert statuses == {
        core_cert.number: "valid", old_farovon.number: "recert_required",
        old_operator.number: "recert_required",
    }  # fmt: skip

    # Recertify: watch the replaced lesson, pass Farovon again in a fresh cycle.
    reasons = [r["code"] for r in _status(client, farovon.id)["reasons"]]
    assert reasons == ["lessons_incomplete"]
    complete_lesson(db, learner, db.get(LessonVersion, new_versions[changed_lesson.id]))
    assert _status(client, farovon.id)["can_start"] is True
    clock.advance(minutes=1)
    pass_test(db, client, farovon.id)

    new_farovon = _current(db, learner, module=farovon)
    new_operator = _current(db, learner, CertificateKind.operator)
    assert new_farovon.id != old_farovon.id and new_operator.id != old_operator.id
    assert db.get(Certificate, old_farovon.id).superseded_by_id == new_farovon.id
    assert db.get(Certificate, old_operator.id).superseded_by_id == new_operator.id
    assert sorted(new_operator.covers) == sorted([core_cert.id, new_farovon.id])
    assert _current(db, learner, module=core).id == core_cert.id  # never reissued
    statuses = {c["number"]: c["status"] for c in client.get(f"{ME}/certificates").json()}
    assert statuses[new_farovon.number] == statuses[new_operator.number] == "valid"
    assert statuses[old_farovon.number] == statuses[old_operator.number] == "superseded"


def test_transition_days_keep_the_certificate_valid_until_the_date(
    db, client, make_client, reference, clock
):
    core, farovon, farovon_lessons, learner = _core_and_farovon(db, reference)
    login(client, learner)
    pass_test(db, client, core.id)
    pass_test(db, client, farovon.id)
    farovon_cert = _current(db, learner, module=farovon)
    operator = _current(db, learner, CertificateKind.operator)

    clock.advance(days=1)
    admin, admin_user = make_client(), make_user(db, role=AccessRole.admin)
    login(admin, admin_user)
    published_at = clock.now
    publish_release(db, admin, [farovon_lessons[0][0]], "2026.12", transition_days=14)
    due = published_at + timedelta(days=14)
    assert db.get(Certificate, farovon_cert.id).recert_due_at == due
    assert certificates.module_status(db.get(Certificate, farovon_cert.id), clock.now) == "valid"
    assert certificates.certificate_status(db, operator, clock.now) == "valid"

    # A later release with a longer transition never pushes the date back.
    clock.advance(days=2)
    login(admin, admin_user)
    publish_release(db, admin, [farovon_lessons[0][0]], "2027.01", transition_days=30)
    assert db.get(Certificate, farovon_cert.id).recert_due_at == due

    clock.now = due - timedelta(seconds=1)
    assert certificates.certificate_status(db, operator, clock.now) == "valid"
    clock.now = due
    assert certificates.module_status(db.get(Certificate, farovon_cert.id), clock.now) == (
        "recert_required"
    )
    assert certificates.certificate_status(db, operator, clock.now) == "recert_required"


def test_certificate_from_an_attempt_that_spanned_a_release_is_due_at_once(
    db, client, make_client, reference, clock
):
    core, farovon, farovon_lessons, learner = _core_and_farovon(db, reference)
    login(client, learner)
    pass_test(db, client, core.id)
    started = client.post(f"{ME}/modules/{farovon.id}/attempts").json()["attempt_id"]
    admin = make_client()
    login(admin, make_user(db, role=AccessRole.admin))
    publish_release(db, admin, [farovon_lessons[0][0]], "2026.12", transition_days=0)

    attempt = db.get(TestAttempt, started)
    attempt.status, attempt.passed, attempt.score_pct = AttemptStatus.submitted, True, 100.0
    cert = certificates.issue_module(db, attempt, clock.now)
    assert cert.release_id == attempt.release_id != farovon.current_release_id
    assert cert.recert_due_at == clock.now  # on the old content, like everyone else's


def test_assignment_changes_reissue_the_operator_certificate_through_the_worker(
    db, client, make_client, reference, clock
):
    core, farovon, _, learner = _core_and_farovon(db, reference)
    login(client, learner)
    pass_test(db, client, core.id)
    pass_test(db, client, farovon.id)
    first = _current(db, learner, CertificateKind.operator)
    wave_id = client.get(f"{ME}/dashboard").json()["wave"]["id"]

    clock.advance(days=1)
    admin = make_client()
    login(admin, make_user(db, role=AccessRole.admin))
    resp = admin.put(f"/api/v1/admin/waves/{wave_id}/assignments", json={"items": []})
    assert resp.status_code == 200, resp.text
    job = db.scalar(select(Job).where(Job.kind == JobKind.operator_cert_eval))
    assert learner.id in job.payload["user_ids"]
    run_job(db, job)
    assert (job.status, job.result) == (JobStatus.done, {"evaluated": 1, "issued": 1})
    second = _current(db, learner, CertificateKind.operator)
    assert second.id != first.id and second.covers == [_current(db, learner, module=core).id]
    assert db.get(Certificate, first.id).superseded_by_id == second.id

    # A newly assigned module the learner hasn't passed yet: nothing is reissued.
    uzcard = reference.modules["UZCARD"]
    make_live_lesson(db, uzcard)
    items = [{"job_role_id": reference.roles["menejer"].id, "module_id": uzcard.id}]
    admin.put(f"/api/v1/admin/waves/{wave_id}/assignments", json={"items": items})
    job = db.scalars(
        select(Job).where(Job.kind == JobKind.operator_cert_eval).order_by(Job.id.desc())
    ).first()
    run_job(db, job)
    assert job.result == {"evaluated": 1, "issued": 0}
    assert _current(db, learner, CertificateKind.operator).id == second.id


def test_release_detail_previews_who_must_renew(db, client, make_client, reference, clock):
    core, farovon, farovon_lessons, learner = _core_and_farovon(db, reference)
    login(client, learner)
    pass_test(db, client, core.id)
    pass_test(db, client, farovon.id)
    admin = make_client()
    login(admin, make_user(db, role=AccessRole.admin))
    release = admin.post("/api/v1/admin/releases", json={"code": "2026.12"}).json()
    admin.post(f"/api/v1/admin/releases/{release['id']}/lessons/{farovon_lessons[0][0].id}")

    detail = admin.get(f"/api/v1/admin/releases/{release['id']}").json()
    assert detail["impact"] == [
        {
            "module_id": farovon.id, "code": "FAROVON", "title_uz": farovon.title_uz,
            "title_ru": farovon.title_ru, "changed_lessons": 1, "added_lessons": 0,
            "total_lessons": 2, "certificates": 1, "learners": 1, "questions_pending": 0,
            "pool_have": 9, "pool_need": 9,
        }
    ]  # fmt: skip
