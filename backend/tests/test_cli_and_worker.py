from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.auth.sessions import purge_expired
from app.cli import create_staff, import_branches, seed_reference, seed_synthetic
from app.models import (
    AppUser,
    Branch,
    Course,
    Job,
    JobRole,
    Module,
    Region,
    UserSession,
    Wave,
    WaveBranch,
    WaveModuleRole,
)
from app.models.enums import AccessRole, JobKind, JobLane, JobStatus, ModuleType
from app.worker import runner
from tests.factories import login, make_user


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_seed_reference_is_idempotent(db):
    first = seed_reference(db)
    assert {k: v.created for k, v in first.items()} == {
        "course": 1, "regions": 14, "job_roles": 5, "modules": 7,
    }  # fmt: skip
    second = seed_reference(db)
    assert all(c.created == 0 for c in second.values())
    assert (_count(db, Course), _count(db, Region), _count(db, JobRole), _count(db, Module)) == (
        1, 14, 5, 7,
    )  # fmt: skip
    types = dict(db.execute(select(Module.code, Module.type)).all())
    assert types["CORE"] == ModuleType.core and types["FAQ"] == ModuleType.faq


def test_seed_synthetic_builds_a_demo_wave(db, client):
    seed_reference(db)
    counts = seed_synthetic(db, password="Demo-parol-1")
    assert counts == {"branches": 25, "users": 245, "waves": 1}
    assert _count(db, WaveBranch) == 12  # Tashkent city branches
    assert _count(db, WaveModuleRole) == 16
    wave = db.scalar(select(Wave))
    assert wave.training_start < wave.deadline < wave.go_live
    heads = db.scalar(
        select(func.count()).where(AppUser.access_role == AccessRole.branch_head)
    )
    assert heads == 25  # one per branch
    assert seed_synthetic(db, password="x") == {"branches": 0, "users": 0, "waves": 0}
    assert login(client, "XB-100001", "Demo-parol-1").status_code == 200


def test_create_staff_prints_a_temporary_password(db, client):
    temp = create_staff(db, "adm-0001", "Akobir S.", AccessRole.admin)
    user = db.scalar(select(AppUser).where(AppUser.employee_id == "ADM-0001"))
    assert user.access_role == AccessRole.admin and user.must_change_password
    assert login(client, "ADM-0001", temp).status_code == 200
    with pytest.raises(ValueError):
        create_staff(db, "ADM-0001", "Again", AccessRole.admin)
    with pytest.raises(ValueError):
        create_staff(db, "ADM-0002", "Learner", AccessRole.learner)


def test_import_branches_upserts_and_reports_problems(db):
    seed_reference(db)
    data = (
        "code;name_uz;name_ru;region_code\n"
        "01-117;Olmazor BXM;ЦБУ Алмазар;01\n"
        "99-001;Yoʻq BXM;Нет;99\n"
    ).encode()
    assert import_branches(db, data) == (1, 0, ["line 3: 99-001: unknown region or empty name"])
    renamed = "code,name_uz,name_ru,region_code\n01-117,Olmazor BXM 2,ЦБУ Алмазар 2,01\n"
    assert import_branches(db, renamed.encode()) == (0, 1, [])
    assert db.scalar(select(Branch.name_uz).where(Branch.code == "01-117")) == "Olmazor BXM 2"


def test_job_queue_claims_runs_and_records_failures(db, monkeypatch):
    done = runner.enqueue(db, JobKind.transcode, JobLane.media, {"n": 1})
    orphan = runner.enqueue(db, JobKind.ai_draft, JobLane.general, {})
    db.commit()

    handler = lambda _db, job: {"ok": job.payload["n"]}  # noqa: E731
    monkeypatch.setitem(runner.HANDLERS, JobKind.transcode, handler)
    monkeypatch.delitem(runner.HANDLERS, JobKind.ai_draft, raising=False)  # a kind nobody handles
    job = runner.claim_next(db, JobLane.media)
    assert job.id == done.id and job.status == JobStatus.running and job.attempts == 1
    assert runner.claim_next(db, JobLane.media) is None  # nothing else queued in this lane
    runner.run_job(db, job)
    assert (job.status, job.result) == (JobStatus.done, {"ok": 1})

    job = runner.claim_next(db, JobLane.general)
    runner.run_job(db, job)
    failed = db.get(Job, orphan.id)
    assert failed.status == JobStatus.failed and "no handler" in failed.last_error


def test_interrupted_jobs_are_retried_then_given_up(db):
    retry = runner.enqueue(db, JobKind.transcode, JobLane.media, {})
    give_up = runner.enqueue(db, JobKind.transcode, JobLane.media, {})
    retry.status, retry.attempts = JobStatus.running, 1
    give_up.status, give_up.attempts = JobStatus.running, runner.MAX_ATTEMPTS
    db.commit()
    assert runner.recover_interrupted(db) == 1
    db.refresh(retry)
    db.refresh(give_up)
    assert retry.status == JobStatus.queued
    assert give_up.status == JobStatus.failed


def test_sweep_purges_only_expired_sessions(db, client, make_client, clock):
    login(client, make_user(db))
    clock.advance(minutes=45)
    login(make_client(), make_user(db))
    clock.advance(minutes=20)  # first session idle 65 min, second 20 min
    assert purge_expired(db) == 1
    assert _count(db, UserSession) == 1
    clock.advance(hours=13)
    assert purge_expired(db) == 1


def test_seeded_wave_assignments_match_mockup(db):
    seed_reference(db)
    seed_synthetic(db, password="Demo-parol-1")
    rows = db.execute(
        select(JobRole.code, Module.code)
        .join(WaveModuleRole, WaveModuleRole.job_role_id == JobRole.id)
        .join(Module, Module.id == WaveModuleRole.module_id)
    ).all()
    by_role: dict[str, set[str]] = {}
    for role, module in rows:
        by_role.setdefault(role, set()).add(module)
    assert by_role["korporativ_menejer"] == {"LEGAL", "CRM"}
    assert "CORE" not in set().union(*by_role.values())  # Core is implicit, never stored
    wave = db.scalar(select(Wave))
    assert wave.go_live - wave.training_start == timedelta(days=59)


def test_demo_questions_fill_a_3n_pool_and_publish_the_demo_tests(db, client, reference, clock):
    from app.cli import seed_demo_questions
    from app.models import Question
    from app.models.enums import QuestionStatus, QuestionType
    from app.services import questions
    from tests.factories import (
        answer_key,
        complete_lesson,
        make_learner,
        make_live_lesson,
        make_wave,
    )

    core, farovon = reference.modules["CORE"], reference.modules["FAROVON"]
    versions = [make_live_lesson(db, core, duration=40)[1] for _ in range(3)]
    make_live_lesson(db, farovon, duration=40)
    admin = make_user(db, role=AccessRole.admin)

    assert seed_demo_questions(db, admin.id) == 90
    for module in (core, farovon):
        pool = questions.pool_status(db, module)
        assert (pool.approved_active, pool.by_difficulty) == (45, {1: 15, 2: 15, 3: 15})
        assert module.test_published_at is not None and module.test_cooldown_hours == 0
    bank = db.scalars(select(Question).where(Question.module_id == core.id)).all()
    assert {q.status for q in bank} == {QuestionStatus.approved}
    assert {q.lesson_version_id for q in bank} == {v.id for v in versions}
    for q in bank:  # the arithmetic really has the marked answer
        if q.type == QuestionType.single:
            a, b = (int(x) for x in q.text_uz.split("]")[1].split("nechaga")[0].split("+"))
            assert [o.text_uz for o in q.options if o.is_correct] == [str(a + b)]
        elif q.type == QuestionType.ordering:
            values = [int(o.text_uz) for o in q.options]
            assert values == sorted(values)

    make_wave(db, [reference.tashkent], {})
    learner = make_learner(db, reference)
    for version in versions:
        complete_lesson(db, learner, version)
    login(client, learner)
    attempt_id = client.post(f"/api/v1/me/modules/{core.id}/attempts").json()["attempt_id"]
    for position, answer in answer_key(db, attempt_id).items():
        client.put(f"/api/v1/me/attempts/{attempt_id}/answers/{position}", json={"answer": answer})
    result = client.post(f"/api/v1/me/attempts/{attempt_id}/submit").json()
    assert (result["score_pct"], result["passed"]) == (100.0, True)


def test_demo_learner_takes_exactly_core_and_farovon(db, reference, clock):
    from app.cli import seed_demo_learner
    from app.services import access

    temp = seed_demo_learner(db)
    assert temp and seed_demo_learner(db) is None  # second run: already there
    learner = db.scalar(select(AppUser).where(AppUser.employee_id == "DEMO-0001"))
    assert learner.must_change_password and learner.access_role == AccessRole.learner
    assert [m.code for m in access.assigned_modules(db, learner)] == ["CORE", "FAROVON"]
