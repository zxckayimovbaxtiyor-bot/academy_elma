from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.errors import AppError, not_found
from app.models import AppUser, Certificate, Lesson, Module
from app.models.enums import AccessRole
from app.models.practice import (
    PracticeAction,
    PracticeAssignment,
    PracticeAsset,
    PracticeResult,
    PracticeScenario,
    PracticeScenarioVersion,
    PracticeSession,
)
from app.schemas.practice import AssignmentIn, Command, Definition, DraftIn, ScenarioIn
from app.services import access, audit, practice_engine as engine
from app.services import practice_time


def scenario(db: Session, sid: int, lock=False) -> PracticeScenario:
    stmt = select(PracticeScenario).where(PracticeScenario.id == sid)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(stmt)
    if row is None:
        raise not_found("practice")
    return row


def version(db: Session, sid: int, *, published=True):
    stmt = select(PracticeScenarioVersion).where(
        PracticeScenarioVersion.scenario_id == sid
    )
    stmt = stmt.where(
        PracticeScenarioVersion.published_at.is_not(None)
        if published
        else PracticeScenarioVersion.published_at.is_(None)
    )
    return db.scalar(stmt.order_by(PracticeScenarioVersion.number.desc()).limit(1))


def policy(db, sid):
    row = db.get(PracticeAssignment, sid)
    return AssignmentIn.model_validate(row.policy if row else {}).model_dump()


def ensure_access(db, user, row, v=None):
    module = db.get(Module, row.module_id)
    if row.module_id not in {m.id for m in access.assigned_modules(db, user)}:
        raise not_found("practice")
    if access.is_locked(module, access.holds_core_certificate(db, user.id)):
        raise AppError(403, "module.locked")
    if v and user.access_role.value not in v.definition["roles"]:
        raise not_found("practice")


def validate_assets(db, sid, definition):
    ids = {
        c.asset_id
        for s in definition.screens
        for c in s.components
        if c.asset_id is not None
    }
    owned = set(
        db.scalars(
            select(PracticeAsset.id).where(
                PracticeAsset.scenario_id == sid, PracticeAsset.id.in_(ids or [0])
            )
        )
    )
    if ids != owned:
        raise AppError(422, "practice.invalid_asset")


def create(db: Session, user: AppUser, data: ScenarioIn):
    if db.get(Module, data.module_id) is None:
        raise not_found("module")
    if data.lesson_id:
        lesson = db.get(Lesson, data.lesson_id)
        if lesson is None or lesson.module_id != data.module_id:
            raise AppError(422, "practice.lesson_mismatch")
    row = PracticeScenario(
        module_id=data.module_id, lesson_id=data.lesson_id, created_by=user.id
    )
    db.add(row)
    db.flush()
    validate_assets(db, row.id, data.definition)
    db.add(
        PracticeScenarioVersion(
            scenario_id=row.id,
            number=1,
            revision=0,
            definition=data.definition.model_dump(),
        )
    )
    db.add(PracticeAssignment(scenario_id=row.id, policy=AssignmentIn().model_dump()))
    audit.record(
        db, "practice.created", actor_id=user.id, entity="practice", entity_id=row.id
    )
    db.flush()
    return row


def edit(db, user, sid, data: DraftIn):
    scenario(db, sid, lock=True)
    v = version(db, sid, published=False)
    if v is None:
        latest = version(db, sid)
        if data.expected_revision != latest.revision:
            raise AppError(409, "practice.conflict")
        v = PracticeScenarioVersion(
            scenario_id=sid,
            number=latest.number + 1,
            revision=latest.revision,
            definition=latest.definition,
        )
        db.add(v)
    if v.revision != data.expected_revision:
        raise AppError(409, "practice.conflict")
    validate_assets(db, sid, data.definition)
    v.definition = data.definition.model_dump()
    v.revision += 1
    v.preview_revision = None
    audit.record(
        db, "practice.draft_saved", actor_id=user.id, entity="practice", entity_id=sid
    )
    db.flush()
    return v


def publish(db, user, sid, expected_revision):
    scenario(db, sid, lock=True)
    v = version(db, sid, published=False)
    if v is None:
        raise AppError(409, "practice.no_draft")
    if v.revision != expected_revision:
        raise AppError(409, "practice.conflict")
    if v.preview_revision != v.revision:
        raise AppError(409, "practice.preview_required")
    definition = Definition.model_validate(v.definition)
    validate_assets(db, sid, definition)
    v.published_at, v.published_by = clock.utcnow(), user.id
    audit.record(
        db,
        "practice.published",
        actor_id=user.id,
        entity="practice_version",
        entity_id=v.id,
    )
    db.flush()
    return v


def detail(db, row):
    v = version(db, row.id, published=False) or version(db, row.id)
    live = version(db, row.id)
    return {
        "id": row.id,
        "module_id": row.module_id,
        "lesson_id": row.lesson_id,
        "version_id": v.id,
        "number": v.number,
        "revision": v.revision,
        "published": v.published_at is not None,
        "live_version": live.number if live else None,
        "definition": v.definition,
        "policy": policy(db, row.id),
    }


def catalog(db, user, module_id=None, lesson_id=None):
    out = []
    for row in db.scalars(select(PracticeScenario).order_by(PracticeScenario.id)):
        if module_id and row.module_id != module_id:
            continue
        if lesson_id and row.lesson_id != lesson_id:
            continue
        v = version(db, row.id)
        if not v:
            continue
        try:
            ensure_access(db, user, row, v)
        except AppError:
            continue
        sessions = list(
            db.scalars(
                select(PracticeSession)
                .where(
                    PracticeSession.user_id == user.id,
                    PracticeSession.scenario_id == row.id,
                )
                .order_by(PracticeSession.id.desc())
            )
        )
        out.append(
            {
                "id": row.id,
                "module_id": row.module_id,
                "lesson_id": row.lesson_id,
                "title": v.definition["title"],
                "description": v.definition["description"],
                "number": v.number,
                "policy": policy(db, row.id),
                "sessions": [
                    {
                        "id": s.id,
                        "mode": s.mode,
                        "status": s.status,
                        "result": result_data(db, s.id),
                    }
                    for s in sessions
                ],
            }
        )
    return out


def start(db, user, sid, mode):
    # Serializes double starts and attempt-limit checks across tabs.
    db.scalar(select(AppUser.id).where(AppUser.id == user.id).with_for_update())
    row = scenario(db, sid)
    v = version(db, sid)
    if not v:
        raise not_found("practice")
    ensure_access(db, user, row, v)
    active = db.scalar(
        select(PracticeSession).where(
            PracticeSession.user_id == user.id,
            PracticeSession.scenario_id == sid,
            PracticeSession.mode == mode,
            PracticeSession.status == "active",
        )
    )
    if active:
        return active
    p = policy(db, sid)
    module = db.get(Module, row.module_id)
    if p["theory_first"]:
        from app.services.attempts import lesson_counts

        done, total = lesson_counts(db, user.id, module.id)
        if not total or done < total:
            raise AppError(409, "practice.theory_required")
    if mode == "exam":
        attempts = list(
            db.scalars(
                select(PracticeSession).where(
                    PracticeSession.user_id == user.id,
                    PracticeSession.scenario_id == sid,
                    PracticeSession.mode == "exam",
                    PracticeSession.version_id == v.id,
                    *(
                        [PracticeSession.release_id == module.current_release_id]
                        if p["repeat_on_material"]
                        else []
                    ),
                )
            )
        )
        if len(attempts) >= p["max_attempts"]:
            raise AppError(409, "practice.attempts_exhausted")
        if not p["allow_repeat"] and any(result_data(db, s.id) for s in attempts):
            raise AppError(409, "practice.repeat_disabled")
    s = PracticeSession(
        user_id=user.id,
        scenario_id=sid,
        version_id=v.id,
        release_id=module.current_release_id,
        mode=mode,
        state=engine.initial(Definition.model_validate(v.definition)),
        policy=p,
        started_at=clock.utcnow(),
        timing=practice_time.initial(clock.utcnow()),
    )
    if mode == "sandbox":
        s.state = engine.workspace(
            Definition.model_validate(v.definition),
            s.state,
            Command(
                request_id="initial-record", expected_revision=0, kind="new_record"
            ),
        )
    elif mode == "exam" and v.definition.get("tasks"):
        s.state["task_id"] = random.SystemRandom().choice(v.definition["tasks"])["id"]
    db.add(s)
    db.flush()
    audit.record(
        db,
        "practice.started",
        actor_id=user.id,
        entity="practice_session",
        entity_id=s.id,
    )
    return s


def owned(db, user, session_id, lock=False):
    stmt = select(PracticeSession).where(
        PracticeSession.id == session_id, PracticeSession.user_id == user.id
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    s = db.scalar(stmt)
    if s is None:
        raise not_found("practice")
    ensure_access(
        db,
        user,
        scenario(db, s.scenario_id),
        db.get(PracticeScenarioVersion, s.version_id),
    )
    return s


def result_data(db, session_id):
    r = db.scalar(select(PracticeResult).where(PracticeResult.session_id == session_id))
    return (
        {
            "score_pct": r.score_pct,
            "passed": r.passed,
            "duration_s": r.duration_s,
            "duration_estimated": bool(
                db.get(PracticeSession, session_id).timing.get("estimated")
            ),
            "errors": r.errors,
        }
        if r
        else None
    )


def payload(db, s):
    v = db.get(PracticeScenarioVersion, s.version_id)
    return {
        "id": s.id,
        "scenario_id": s.scenario_id,
        "version": v.number,
        "mode": s.mode,
        "status": s.status,
        "revision": s.revision,
        "title": v.definition["title"],
        "started_at": s.started_at.isoformat(),
        "elapsed_s": practice_time.seconds(s.timing, clock.utcnow()),
        "policy": s.policy,
        "records": s.state.get("records", []) if s.mode == "sandbox" else [],
        "record_id": s.state.get("record_id") if s.mode == "sandbox" else None,
        **engine.public_state(
            Definition.model_validate(v.definition),
            s.state,
            s.mode,
            complete=s.status == "completed",
        ),
        "result": result_data(db, s.id),
    }


def command(db, user, session_id, cmd: Command):
    s = owned(db, user, session_id, lock=True)
    fingerprint = hashlib.sha256(
        json.dumps(cmd.model_dump(), sort_keys=True).encode()
    ).hexdigest()
    previous = db.scalar(
        select(PracticeAction).where(
            PracticeAction.session_id == s.id,
            PracticeAction.request_id == cmd.request_id,
        )
    )
    if previous:
        if previous.fingerprint != fingerprint:
            raise AppError(409, "practice.idempotency_conflict")
        return previous.response
    if s.status != "active":
        raise AppError(409, "practice.finished")
    if s.revision != cmd.expected_revision:
        raise AppError(409, "practice.conflict")
    if s.revision >= 2000:
        raise AppError(409, "practice.action_limit")
    definition = Definition.model_validate(
        db.get(PracticeScenarioVersion, s.version_id).definition
    )
    old_screen = s.state["screen"]
    s.state, errors, finished = engine.apply(definition, s.state, cmd, s.mode)
    if s.mode == "sandbox":
        engine.sync_record(s.state, definition)
    now = clock.utcnow()
    s.timing = practice_time.command(s.timing, now, finished=finished)
    s.revision += 1
    if finished:
        s.status, s.finished_at = "completed", now
        score, passed = engine.grade(definition, s.state, s.mode, s.policy["pass_pct"])
        db.add(
            PracticeResult(
                session_id=s.id,
                score_pct=score,
                passed=passed,
                duration_s=practice_time.seconds(s.timing, now),
                errors=s.state["mistakes"],
            )
        )
        audit.record(
            db,
            "practice.completed",
            actor_id=user.id,
            entity="practice_session",
            entity_id=s.id,
            data={"score_pct": score, "passed": passed},
        )
    db.flush()
    response = payload(db, s)
    response["feedback"] = (
        errors if s.mode == "guided" else ([{"id": "invalid"}] if errors else [])
    )
    db.add(
        PracticeAction(
            session_id=s.id,
            request_id=cmd.request_id,
            fingerprint=fingerprint,
            screen_id=old_screen,
            kind=cmd.kind,
            errors=errors,
            response=response,
        )
    )
    db.flush()
    # A learner can pass a test with a certificate-stage practice still pending.
    if finished and s.mode == "exam":
        issue_pending_certificate(db, user, scenario(db, s.scenario_id).module_id)
    return response


def requirements_met(db, user_id, module_id, gate):
    module = db.get(Module, module_id)
    for row in db.scalars(
        select(PracticeScenario).where(PracticeScenario.module_id == module_id)
    ):
        p = policy(db, row.id)
        if not p["required"] or p["gate"] != gate:
            continue
        v = version(db, row.id)
        if v is None:
            continue
        stmt = (
            select(PracticeResult)
            .join(PracticeSession, PracticeSession.id == PracticeResult.session_id)
            .where(
                PracticeSession.user_id == user_id,
                PracticeSession.scenario_id == row.id,
                PracticeSession.mode == "exam",
            )
        )
        if p["require_pass"]:
            stmt = stmt.where(
                PracticeResult.passed.is_(True),
                PracticeResult.score_pct >= p["pass_pct"],
            )
        if p["repeat_on_update"]:
            stmt = stmt.where(PracticeSession.version_id == v.id)
        if p["repeat_on_material"]:
            stmt = stmt.where(PracticeSession.release_id == module.current_release_id)
        if db.scalar(stmt.limit(1)) is None:
            return False
    return True


def issue_pending_certificate(db, user, module_id):
    from app.models import TestAttempt
    from app.services import certificates

    db.scalar(select(AppUser.id).where(AppUser.id == user.id).with_for_update())
    if not requirements_met(db, user.id, module_id, "before_certificate"):
        return
    attempt = db.scalar(
        select(TestAttempt)
        .where(
            TestAttempt.user_id == user.id,
            TestAttempt.module_id == module_id,
            TestAttempt.passed.is_(True),
        )
        .order_by(TestAttempt.id.desc())
        .limit(1)
    )
    if attempt and not db.scalar(
        select(Certificate.id).where(Certificate.attempt_id == attempt.id)
    ):
        certificates.issue_module(db, attempt, clock.utcnow())


def analytics(
    db,
    viewer,
    module_id=None,
    user_id=None,
    branch_id=None,
    job_role_id=None,
    mode=None,
    wave_id=None,
    region_id=None,
    page=1,
    page_size=50,
):
    # Project only the small reporting fields; never hydrate a workspace or action response.
    stmt = (
        select(
            PracticeSession.id,
            PracticeSession.user_id,
            PracticeSession.scenario_id,
            PracticeSession.mode,
            PracticeSession.status,
            PracticeSession.state["mistakes"].label("mistakes"),
            AppUser.employee_id,
            AppUser.full_name,
            AppUser.branch_id,
            AppUser.job_role_id,
            PracticeResult.score_pct,
            PracticeResult.passed,
            PracticeResult.duration_s,
            PracticeResult.errors,
        )
        .join(AppUser, AppUser.id == PracticeSession.user_id)
        .join(PracticeScenario, PracticeScenario.id == PracticeSession.scenario_id)
        .outerjoin(PracticeResult, PracticeResult.session_id == PracticeSession.id)
    )
    if viewer.access_role == AccessRole.branch_head:
        stmt = stmt.where(AppUser.branch_id == (viewer.branch_id or 0))
    elif branch_id:
        stmt = stmt.where(AppUser.branch_id == branch_id)
    if module_id:
        stmt = stmt.where(PracticeScenario.module_id == module_id)
    if user_id:
        stmt = stmt.where(AppUser.id == user_id)
    if job_role_id:
        stmt = stmt.where(AppUser.job_role_id == job_role_id)
    if mode:
        stmt = stmt.where(PracticeSession.mode == mode)
    if wave_id:
        from app.models import WaveBranch

        stmt = stmt.where(
            AppUser.branch_id.in_(
                select(WaveBranch.branch_id).where(WaveBranch.wave_id == wave_id)
            )
        )
    if region_id:
        from app.models import Branch

        stmt = stmt.where(
            AppUser.branch_id.in_(
                select(Branch.id).where(Branch.region_id == region_id)
            )
        )
    errors, stages, cycles = Counter(), Counter(), Counter()
    error_labels, stage_labels = {}, {}
    branches, roles, people = defaultdict(list), defaultdict(list), defaultdict(list)
    outcomes, items = [], []
    rows = db.execute(
        stmt.order_by(PracticeSession.id.desc()).execution_options(yield_per=250)
    ).mappings()
    for index, r in enumerate(rows):
        cycles[(r["user_id"], r["scenario_id"], r["mode"])] += 1
        outcome = (r["passed"], r["duration_s"]) if r["score_pct"] is not None else None
        outcomes.append(outcome)
        branches[r["branch_id"]].append(outcome)
        roles[r["job_role_id"]].append(outcome)
        people[r["user_id"]].append(outcome)
        for error in r["errors"] if outcome else r["mistakes"] or []:
            error_id = f'{r["scenario_id"]}:{error["id"]}'
            stage_id = f'{r["scenario_id"]}:{error["screen"]}'
            errors[error_id] += 1
            stages[stage_id] += 1
            error_labels[error_id] = error.get("message") or error.get("field_label")
            stage_labels[stage_id] = error.get("screen_title")
        if (page - 1) * page_size <= index < page * page_size:
            items.append(
                {
                    k: r[k]
                    for k in (
                        "id",
                        "user_id",
                        "employee_id",
                        "full_name",
                        "branch_id",
                        "job_role_id",
                        "scenario_id",
                        "mode",
                        "status",
                        "score_pct",
                        "passed",
                        "duration_s",
                    )
                }
            )

    def aggregate(rs):
        done = [r for r in rs if r is not None]
        return {
            "started": len(rs),
            "completed": len(done),
            "pass_rate": (
                round(sum(r[0] for r in done) / len(done) * 100, 1) if done else 0
            ),
            "average_seconds": (
                round(sum(r[1] for r in done) / len(done)) if done else 0
            ),
        }

    from app.models import Branch, JobRole

    def grouped(groups, model):
        names = {
            row.id: {"ru": row.name_ru, "uz": row.name_uz}
            for row in db.scalars(
                select(model).where(model.id.in_([key for key in groups if key] or [0]))
            )
        }
        return [
            {"id": key, "title": names.get(key), **aggregate(values)}
            for key, values in groups.items()
        ]

    return {
        **aggregate(outcomes),
        "total": len(outcomes),
        "page": page,
        "page_size": page_size,
        "retries": sum(max(0, n - 1) for n in cycles.values()),
        "errors": dict(errors.most_common()),
        "error_labels": error_labels,
        "stages": dict(stages.most_common()),
        "stage_labels": stage_labels,
        "branches": grouped(branches, Branch),
        "roles": grouped(roles, JobRole),
        "employees": [
            {"id": key, **aggregate(values)} for key, values in people.items()
        ],
        "sessions": items,
    }
