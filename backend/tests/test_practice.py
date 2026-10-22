"""Full practice lifecycle on real PostgreSQL, including adversarial requests."""

from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
import uuid

from PIL import Image
import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.errors import AppError
from app.models import Certificate
from app.models.enums import AccessRole
from app.models.practice import (
    PracticeAction,
    PracticeAssignment,
    PracticeScenarioVersion,
    PracticeSession,
)
from app.schemas.practice import AssignmentIn, Command, Definition, DraftIn, ScenarioIn
from app.services import practice, practice_engine
from app.services.practice_demo import demo_definition
from tests.factories import give_certificate, login, make_learner, make_user, make_wave


@pytest.fixture
def setup(db, reference):
    admin = make_user(db, role=AccessRole.admin)
    learner = make_learner(db, reference)
    make_wave(
        db,
        [reference.tashkent, reference.samarqand],
        {reference.roles["menejer"]: [reference.modules["CORE"]]},
    )
    row = practice.create(
        db,
        admin,
        ScenarioIn(
            module_id=reference.modules["CORE"].id, definition=demo_definition()
        ),
    )
    draft = practice.version(db, row.id, published=False)
    draft.preview_revision = draft.revision
    practice.publish(db, admin, row.id, draft.revision)
    db.flush()
    return admin, learner, row


def cmd(
    s, *, kind="action", action="next", values=None, request_id=None, revision=None
):
    return Command(
        request_id=request_id or uuid.uuid4().hex,
        expected_revision=s.revision if revision is None else revision,
        kind=kind,
        action=action,
        values=values or {},
    )


def advance(db, user, s, values=None, kind="action"):
    return practice.command(db, user, s.id, cmd(s, kind=kind, values=values))


def finish_demo(db, user, s):
    task = next(
        (t for t in demo_definition().tasks if t.id == s.state.get("task_id")),
        demo_definition().tasks[0],
    )
    inputs = {
        "search": {"client_id": "TEST-001"},
        "create": {"product": "consumer"},
        "form": task.expected,
        "documents": {"document": "passport", "verified": True},
        "review": {"consent": True},
    }
    for _ in range(15):
        if s.state["screen"] == "result":
            return advance(db, user, s, kind="finish")
        advance(db, user, s, inputs.get(s.state["screen"]))
    raise AssertionError("did not reach terminal")


def test_create_and_publish_requires_preview(db, reference):
    author = make_user(db, role=AccessRole.methodologist)
    row = practice.create(
        db,
        author,
        ScenarioIn(
            module_id=reference.modules["CORE"].id, definition=demo_definition()
        ),
    )
    with pytest.raises(AppError, match="preview_required"):
        practice.publish(db, author, row.id, 0)
    v = practice.version(db, row.id, published=False)
    v.preview_revision = 0
    practice.publish(db, author, row.id, 0)
    assert practice.version(db, row.id).published_by == author.id


def test_new_draft_preserves_published_definition_and_old_session(db, setup):
    admin, user, row = setup
    s = practice.start(db, user, row.id, "guided")
    original = practice.version(db, row.id)
    d = Definition.model_validate(original.definition)
    d.title.ru = "Новая версия"
    draft = practice.edit(db, admin, row.id, DraftIn(expected_revision=0, definition=d))
    assert draft.number == 2 and draft.revision == 1
    assert practice.version(db, row.id).definition["title"]["ru"] != "Новая версия"
    with pytest.raises(AppError, match="preview_required"):
        practice.publish(db, admin, row.id, 1)
    draft.preview_revision = 1
    practice.publish(db, admin, row.id, 1)
    assert practice.payload(db, s)["version"] == 1


def test_database_rejects_mutation_of_published_version(db, setup):
    _, _, row = setup
    v = practice.version(db, row.id)
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(
                text("UPDATE practice_scenario_version SET revision=99 WHERE id=:id"),
                {"id": v.id},
            )
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(
                text("DELETE FROM practice_scenario_version WHERE id=:id"), {"id": v.id}
            )


def test_resume_and_save_are_server_side(db, setup):
    _, user, row = setup
    s = practice.start(db, user, row.id, "guided")
    assert practice.start(db, user, row.id, "guided").id == s.id
    advance(db, user, s)
    advance(db, user, s)
    advance(db, user, s, {"client_id": "TEST-002"}, kind="save")
    db.flush()
    db.expire(s)
    assert (
        practice.payload(db, practice.owned(db, user, s.id))["values"]["client_id"]
        == "TEST-002"
    )
    assert s.state["screen"] == "search"


def test_invalid_document_feedback_and_exam_penalty(db, setup):
    _, user, row = setup
    guided = practice.start(db, user, row.id, "guided")
    advance(db, user, guided)
    advance(db, user, guided)
    out = advance(db, user, guided, {"client_id": "TEST-002"})
    assert out["feedback"][0]["message"]["ru"]
    assert guided.state["screen"] == "search"
    exam = practice.start(db, user, row.id, "exam")
    advance(db, user, exam)
    advance(db, user, exam)
    first = advance(db, user, exam, {"client_id": "TEST-002"})
    assert first["feedback"] == [{"id": "invalid"}]
    advance(db, user, exam, {"client_id": "TEST-002"})
    out = finish_demo(db, user, exam)
    assert out["result"]["score_pct"] == 90
    assert out["result"]["passed"] is True


def test_perfect_exam_and_finished_session(db, setup):
    _, user, row = setup
    s = practice.start(db, user, row.id, "exam")
    out = finish_demo(db, user, s)
    assert out["result"]["score_pct"] == 100 and out["status"] == "completed"
    with pytest.raises(AppError, match="finished"):
        advance(db, user, s)


def test_duplicate_request_is_idempotent_and_payload_bound(db, setup):
    _, user, row = setup
    s = practice.start(db, user, row.id, "exam")
    c = cmd(s)
    first = practice.command(db, user, s.id, c)
    second = practice.command(db, user, s.id, c)
    assert first == second
    assert (
        len(
            list(
                db.scalars(
                    select(PracticeAction).where(PracticeAction.session_id == s.id)
                )
            )
        )
        == 1
    )
    c.kind = "save"
    with pytest.raises(AppError, match="idempotency_conflict"):
        practice.command(db, user, s.id, c)


def test_stale_parallel_command_rejected(db, setup):
    _, user, row = setup
    s = practice.start(db, user, row.id, "guided")
    c = cmd(s)
    advance(db, user, s)
    with pytest.raises(AppError, match="conflict"):
        practice.command(db, user, s.id, c)
    assert s.state["screen"] == "lending"


@pytest.mark.parametrize(
    "values",
    [
        {"score_pct": 100},
        {"status": "completed"},
        {"client_id": "TEST-001"},
        {"passed": True},
    ],
)
def test_fields_from_other_screens_and_results_cannot_be_forged(db, setup, values):
    _, user, row = setup
    s = practice.start(db, user, row.id, "exam")
    with pytest.raises(AppError, match="invalid_values"):
        advance(db, user, s, values)


@pytest.mark.parametrize("kind", ["back", "reset", "finish"])
def test_exam_cannot_reset_back_or_skip_to_finish(db, setup, kind):
    _, user, row = setup
    s = practice.start(db, user, row.id, "exam")
    with pytest.raises(AppError):
        advance(db, user, s, kind=kind)


def test_sandbox_reset_and_guided_back(db, setup):
    _, user, row = setup
    s = practice.start(db, user, row.id, "sandbox")
    advance(db, user, s)
    advance(db, user, s)
    advance(db, user, s, kind="back")
    assert s.state["screen"] == "lending"
    advance(db, user, s, kind="reset")
    assert s.state["screen"] == "start" and s.state["values"] == {}
    assert (
        len(
            list(
                db.scalars(
                    select(PracticeAction).where(PracticeAction.session_id == s.id)
                )
            )
        )
        == 4
    )


def test_attempt_limit_and_repeat_policy(db, setup):
    _, user, row = setup
    db.get(PracticeAssignment, row.id).policy = AssignmentIn(
        max_attempts=1
    ).model_dump()
    db.flush()
    finish_demo(db, user, practice.start(db, user, row.id, "exam"))
    with pytest.raises(AppError, match="attempts_exhausted"):
        practice.start(db, user, row.id, "exam")
    assert practice.start(db, user, row.id, "sandbox")


def test_exam_payload_hides_rules_and_hints(db, setup):
    _, user, row = setup
    s = practice.start(db, user, row.id, "exam")
    out = practice.payload(db, s)
    assert "transitions" not in out["screen"] and "rules" not in out["screen"]
    assert all("hint" not in c for c in out["screen"]["components"])
    assert out["mistakes"] == []


def test_session_isolation_and_revoked_assignment(db, setup, reference):
    _, user, row = setup
    other = make_learner(db, reference)
    s = practice.start(db, user, row.id, "exam")
    with pytest.raises(AppError, match="not_found"):
        practice.owned(db, other, s.id)
    user.branch_id = None
    with pytest.raises(AppError, match="not_found"):
        practice.owned(db, user, s.id)


def test_requirements_opt_in_and_guided_does_not_count(db, setup):
    _, user, row = setup
    assert practice.requirements_met(db, user.id, row.module_id, "before_test")
    db.get(PracticeAssignment, row.id).policy = AssignmentIn(required=True).model_dump()
    db.flush()
    finish_demo(db, user, practice.start(db, user, row.id, "guided"))
    assert not practice.requirements_met(db, user.id, row.module_id, "before_test")
    finish_demo(db, user, practice.start(db, user, row.id, "exam"))
    assert practice.requirements_met(db, user.id, row.module_id, "before_test")


def test_existing_certificate_not_retroactively_invalidated(db, setup, reference):
    _, user, row = setup
    c = give_certificate(db, user, reference.modules["CORE"])
    db.get(PracticeAssignment, row.id).policy = AssignmentIn(required=True).model_dump()
    db.flush()
    from app.services.certificates import module_status, CertStatus
    from app import clock

    assert module_status(c, clock.utcnow()) == CertStatus.valid
    assert db.scalar(select(Certificate.id).where(Certificate.id == c.id)) == c.id


def test_branch_head_analytics_cannot_escape_own_branch(db, setup, reference):
    admin, user, row = setup
    other = make_learner(db, reference, branch=reference.samarqand)
    practice.start(db, user, row.id, "exam")
    practice.start(db, other, row.id, "exam")
    head = make_user(db, role=AccessRole.branch_head, branch=reference.tashkent)
    assert practice.analytics(db, admin)["started"] == 2
    report = practice.analytics(db, head, branch_id=reference.samarqand.id)
    assert report["started"] == 1 and report["sessions"][0]["user_id"] == user.id


@pytest.mark.parametrize(
    "change",
    [
        "unknown_component",
        "bad_target",
        "unknown_field",
        "executable",
        "unreachable",
        "terminal_start",
    ],
)
def test_malformed_or_executable_scenario_rejected(change):
    d = demo_definition().model_dump()
    if change == "unknown_component":
        d["screens"][0]["components"][0]["type"] = "script"
    if change == "bad_target":
        d["screens"][0]["transitions"][0]["target"] = "missing"
    if change == "unknown_field":
        d["screens"][2]["rules"][0]["condition"]["field"] = "missing"
    if change == "executable":
        d["screens"][0]["components"][0]["onClick"] = "fetch('https://bank')"
    if change == "unreachable":
        d["screens"][0]["transitions"][0]["target"] = "search"
    if change == "terminal_start":
        d["completion"].append("start")
    with pytest.raises(ValidationError):
        Definition.model_validate(d)


def test_api_roles_start_resume_and_tampered_grade(client, db, setup):
    admin, user, row = setup
    login(client, user)
    assert client.get("/api/v1/admin/practices").status_code == 403
    assert client.get("/api/v1/reports/practice").status_code == 403
    assert len(client.get("/api/v1/me/practices").json()) == 1
    out = client.post(f"/api/v1/me/practices/{row.id}/sessions", json={"mode": "exam"})
    assert out.status_code == 200
    sid = out.json()["id"]
    assert client.get(f"/api/v1/me/practice-sessions/{sid}").json()["revision"] == 0
    bad = client.post(
        f"/api/v1/me/practice-sessions/{sid}/commands",
        json={
            "request_id": "forged-request",
            "expected_revision": 0,
            "kind": "finish",
            "score_pct": 100,
        },
    )
    assert bad.status_code == 422
    assert client.get(f"/api/v1/me/practice-sessions/{sid}/result").status_code == 409


def test_author_create_edit_preview_publish_api(client, db, reference):
    author = make_user(db, role=AccessRole.methodologist)
    login(client, author)
    definition = demo_definition().model_dump()
    create = client.post(
        "/api/v1/admin/practices",
        json={"module_id": reference.modules["CORE"].id, "definition": definition},
    )
    assert create.status_code == 201
    sid = create.json()["id"]
    definition["title"]["ru"] = "Изменённый сценарий"
    saved = client.put(
        f"/api/v1/admin/practices/{sid}/draft",
        json={"expected_revision": 0, "definition": definition},
    )
    assert saved.json()["revision"] == 1
    assert (
        client.post(
            f"/api/v1/admin/practices/{sid}/publish", json={"expected_revision": 1}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/admin/practices/{sid}/preview", json={"expected_revision": 1}
        ).status_code
        == 200
    )
    pub = client.post(
        f"/api/v1/admin/practices/{sid}/publish", json={"expected_revision": 1}
    )
    assert pub.status_code == 200 and pub.json()["published"]


def test_screenshots_size_type_and_resource_access(client, db, setup, make_client):
    admin, user, row = setup
    login(client, admin)
    url = f"/api/v1/admin/practices/{row.id}/screenshots"
    assert client.put(url, content=b"not an image").status_code == 422
    assert (
        client.put(
            url + "?synthetic_data_confirmed=true", content=b"<svg onload='x()'/>"
        ).status_code
        == 422
    )
    assert (
        client.put(
            url + "?synthetic_data_confirmed=true", content=b"x" * (2 * 1024 * 1024 + 1)
        ).status_code
        == 413
    )
    stream = BytesIO()
    Image.new("RGB", (10, 10)).save(stream, format="PNG")
    response = client.put(
        url + "?synthetic_data_confirmed=true", content=stream.getvalue()
    )
    assert response.status_code == 201
    asset = response.json()["id"]
    assert (
        client.get(f"/api/v1/practice-assets/{asset}").headers["content-type"]
        == "image/png"
    )
    learner = make_client()
    login(learner, user)
    assert learner.get(f"/api/v1/practice-assets/{asset}").status_code == 404


def test_preview_uses_engine_and_never_creates_result(client, db, setup):
    admin, _, _ = setup
    login(client, admin)
    definition = demo_definition()
    p = client.post(
        "/api/v1/admin/practices/preview/step",
        json={
            "definition": definition.model_dump(),
            "state": practice_engine.initial(definition),
            "command": {
                "request_id": "preview-one",
                "expected_revision": 0,
                "kind": "action",
                "action": "next",
            },
        },
    )
    assert p.status_code == 200 and p.json()["screen"]["id"] == "lending"
    assert not list(db.scalars(select(PracticeSession)))


def test_sandbox_multiple_records_are_persisted_and_isolated(db, setup, reference):
    _, user, row = setup
    s = practice.start(db, user, row.id, "sandbox")
    first = s.state["record_id"]
    practice.command(
        db,
        user,
        s.id,
        Command(
            request_id=uuid.uuid4().hex,
            expected_revision=s.revision,
            kind="navigate",
            target="form",
        ),
    )
    advance(db, user, s, {"amount": 1000, "months": 1}, kind="save")
    practice.command(db, user, s.id, cmd(s, kind="new_record"))
    assert len(s.state["records"]) == 2 and s.state["values"] == {}
    practice.command(
        db,
        user,
        s.id,
        Command(
            request_id=uuid.uuid4().hex,
            expected_revision=s.revision,
            kind="open_record",
            target=first,
        ),
    )
    assert s.state["values"]["amount"] == 1000 and s.state["screen"] == "form"
    other = make_learner(db, reference)
    assert practice.start(db, other, row.id, "sandbox").state["values"] == {}
    practice.command(
        db,
        user,
        s.id,
        Command(
            request_id=uuid.uuid4().hex,
            expected_revision=s.revision,
            kind="delete_record",
            target=first,
        ),
    )
    assert len(s.state["records"]) == 1


def test_individual_exam_task_is_server_selected_and_frozen(db, setup, monkeypatch):
    _, user, row = setup
    monkeypatch.setattr(
        "app.services.practice.random.SystemRandom.choice",
        lambda self, tasks: tasks[-1],
    )
    s = practice.start(db, user, row.id, "exam")
    assert s.state["task_id"] == "task_3"
    assert (
        practice.payload(db, s)["task"]
        == demo_definition().tasks[-1].description.model_dump()
    )
    assert finish_demo(db, user, s)["result"]["passed"]


def test_terminal_fields_cannot_be_bypassed():
    from app.schemas.practice import Component, Localized

    definition = demo_definition()
    definition.screens[-1].components.append(
        Component(
            id="confirmation",
            type="checkbox",
            label=Localized(ru="Подтверждаю", uz="Tasdiqlayman"),
            required=True,
        )
    )
    state = practice_engine.initial(definition)
    state["screen"] = "result"
    _, errors, finished = practice_engine.apply(
        definition,
        state,
        Command(request_id="finish-empty", expected_revision=0, kind="finish"),
        "exam",
    )
    assert errors and not finished


def test_before_test_policy_appears_in_existing_eligibility(db, setup):
    from app.services import attempts
    from app.models import Module
    from app import clock

    _, user, row = setup
    module = db.get(Module, row.module_id)
    assert "practice_required" not in {
        r.code for r in attempts.eligibility(db, user, module, clock.utcnow()).reasons
    }
    db.get(PracticeAssignment, row.id).policy = AssignmentIn(required=True).model_dump()
    db.flush()
    assert "practice_required" in {
        r.code for r in attempts.eligibility(db, user, module, clock.utcnow()).reasons
    }
    finish_demo(db, user, practice.start(db, user, row.id, "exam"))
    assert "practice_required" not in {
        r.code for r in attempts.eligibility(db, user, module, clock.utcnow()).reasons
    }


def test_certificate_stage_defers_and_then_issues_certificate(
    db, setup, reference, client
):
    from tests.factories import ready_module, complete_lesson, pass_test

    _, user, row = setup
    [(_, version)] = ready_module(db, reference.modules["CORE"])
    complete_lesson(db, user, version)
    db.get(PracticeAssignment, row.id).policy = AssignmentIn(
        required=True, gate="before_certificate"
    ).model_dump()
    db.flush()
    login(client, user)
    assert pass_test(db, client, row.module_id)["passed"]
    assert not db.scalar(select(Certificate.id).where(Certificate.user_id == user.id))
    finish_demo(db, user, practice.start(db, user, row.id, "exam"))
    assert db.scalar(select(Certificate.id).where(Certificate.user_id == user.id))


def test_new_version_recertification_policy_is_opt_in(db, setup):
    admin, user, row = setup
    finish_demo(db, user, practice.start(db, user, row.id, "exam"))
    db.get(PracticeAssignment, row.id).policy = AssignmentIn(
        required=True, repeat_on_update=True
    ).model_dump()
    db.flush()
    assert practice.requirements_met(db, user.id, row.module_id, "before_test")
    v = practice.edit(
        db, admin, row.id, DraftIn(expected_revision=0, definition=demo_definition())
    )
    v.preview_revision = v.revision
    practice.publish(db, admin, row.id, v.revision)
    assert not practice.requirements_met(db, user.id, row.module_id, "before_test")


def test_repeat_disabled_independent_of_limit(db, setup):
    _, user, row = setup
    db.get(PracticeAssignment, row.id).policy = AssignmentIn(
        allow_repeat=False, max_attempts=20
    ).model_dump()
    db.flush()
    finish_demo(db, user, practice.start(db, user, row.id, "exam"))
    with pytest.raises(AppError, match="repeat_disabled"):
        practice.start(db, user, row.id, "exam")


def test_analytics_filters_apply_to_totals(db, setup):
    admin, user, row = setup
    practice.start(db, user, row.id, "guided")
    practice.start(db, user, row.id, "exam")
    assert practice.analytics(db, admin, mode="exam")["started"] == 1
    assert practice.analytics(db, admin, user_id=-1)["started"] == 0
    assert practice.analytics(db, admin, wave_id=-1)["started"] == 0


def test_history_contains_events_without_private_grading_rules(client, db, setup):
    _, user, row = setup
    login(client, user)
    s = practice.start(db, user, row.id, "exam")
    advance(db, user, s)
    response = client.get(f"/api/v1/me/practice-sessions/{s.id}/actions")
    assert response.status_code == 200
    assert response.json()[0]["kind"] == "action"
    assert "fingerprint" not in response.text and "definition" not in response.text


def test_repeated_error_spam_cannot_hide_later_penalties():
    definition = demo_definition()
    state = practice_engine.initial(definition)
    state["screen"] = "search"
    for index in range(501):
        state, _, _ = practice_engine.apply(
            definition,
            state,
            Command(
                request_id=f"spam-{index:08}",
                expected_revision=index,
                action="next",
                values={"client_id": "TEST-002"},
            ),
            "exam",
        )
    state["screen"] = "create"
    state, _, _ = practice_engine.apply(
        definition,
        state,
        Command(
            request_id="later-error",
            expected_revision=502,
            action="next",
            values={"product": "mortgage"},
        ),
        "exam",
    )
    assert len(state["mistakes"]) == 2
    assert practice_engine.grade(definition, state, "exam", 80) == (80.0, True)


def test_analytics_paginates_rows_without_changing_totals(db, setup):
    admin, user, row = setup
    practice.start(db, user, row.id, "guided")
    practice.start(db, user, row.id, "exam")
    first = practice.analytics(db, admin, page=1, page_size=1)
    second = practice.analytics(db, admin, page=2, page_size=1)
    assert first["started"] == second["started"] == 2
    assert len(first["sessions"]) == len(second["sessions"]) == 1
    assert first["sessions"][0]["id"] != second["sessions"][0]["id"]


def test_practice_migration_roundtrip_on_test_database(engine):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    assert engine.url.database.endswith("_test")
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.downgrade(cfg, "0001")
        command.upgrade(cfg, "head")
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
        )


@pytest.mark.parametrize(
    "state",
    [
        {"screen": "missing", "values": {}},
        {"screen": "start", "values": []},
        {"screen": "start", "history": ["missing"]},
    ],
)
def test_malformed_preview_state_returns_validation_error(client, db, setup, state):
    author, _, _ = setup
    login(client, author)
    response = client.post(
        "/api/v1/admin/practices/preview/step",
        json={
            "definition": demo_definition().model_dump(),
            "state": state,
            "command": {
                "request_id": "bad-preview",
                "expected_revision": 0,
                "kind": "save",
            },
        },
    )
    assert response.status_code == 422
