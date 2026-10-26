"""Studio extensions and full HTTP lifecycle with real PostgreSQL."""

from copy import deepcopy
import json
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from app.errors import AppError
from app.models.practice import PracticeResult, PracticeSession, PracticeAsset
from app.schemas.practice import Command, Condition, Definition, DraftIn
from app.services import practice, practice_engine as engine
from app.services.practice_demo import demo_definition
from tests.test_practice import setup, finish_demo
from tests.factories import login, make_user
from app.models.enums import AccessRole


def cmd(kind="action", action="next", values=None, event=None):
    return Command(
        request_id="studio-request",
        expected_revision=0,
        kind=kind,
        action=action,
        values=values or {},
        event=event,
    )


def definition():
    d = demo_definition().model_dump()
    d["screens"][0]["components"].extend(
        [
            {
                "id": "birth_date",
                "type": "date",
                "label": {"ru": "Дата рождения", "uz": "Tugʻilgan sana"},
                "default_value": "2000-01-01",
            },
            {
                "id": "hidden_field",
                "type": "text",
                "label": {"ru": "Скрыто", "uz": "Yashirin"},
                "visible": False,
            },
            {
                "id": "fixed_field",
                "type": "text",
                "label": {"ru": "Карточка", "uz": "Kartochka"},
                "editable": False,
                "default_value": "TEST",
            },
        ]
    )
    return Definition.model_validate(d)


@pytest.mark.parametrize(
    "op,value,expected",
    [
        ("gt", 4, True),
        ("lt", 4, False),
        ("empty", None, True),
        ("contains", "TEST-001", True),
    ],
)
def test_extended_operators(op, value, expected):
    assert (
        engine.matches(
            Condition(field="field", op=op, value="TEST" if op == "contains" else 3),
            {"field": value},
        )
        is expected
    )


def test_nested_condition_groups_and_budget():
    c = Condition(
        op="all",
        children=[
            Condition(field="a", op="gt", value=1),
            Condition(
                op="any",
                children=[
                    Condition(field="b", op="empty"),
                    Condition(field="b", op="contains", value="ok"),
                ],
            ),
        ],
    )
    assert engine.matches(c, {"a": 2, "b": "ok"})
    assert not engine.matches(c, {"a": 0, "b": "ok"})
    for _ in range(4):
        with pytest.raises(ValidationError):
            Condition(
                op="all",
                children=[
                    Condition(op="all", children=[Condition(op="all", children=[c])])
                ],
            )


def test_partial_draft_saves_but_cannot_publish(client, db, setup):
    admin, user, row = setup
    login(client, admin)
    d = demo_definition().model_dump()
    d["title"]["uz"] = ""
    d["screens"].append(
        {
            "id": "unfinished",
            "title": {"ru": "Новый", "uz": ""},
            "description": {"ru": "", "uz": ""},
            "components": [],
            "transitions": [],
            "rules": [],
        }
    )
    assert DraftIn(expected_revision=0, definition=d).definition.title.uz == ""
    saved = client.put(
        f"/api/v1/admin/practices/{row.id}/draft",
        json={"expected_revision": 0, "definition": d},
    )
    assert saved.status_code == 200
    check = client.post(
        "/api/v1/admin/practices/check/definition",
        json={"expected_revision": 0, "definition": d},
    ).json()
    assert not check["valid"] and check["issues"]
    assert (
        client.post(
            f"/api/v1/admin/practices/{row.id}/preview", json={"expected_revision": 1}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/admin/practices/{row.id}/publish", json={"expected_revision": 1}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "field,value",
    [("hidden_field", "hacked"), ("fixed_field", "hacked"), ("birth_date", "bad-date")],
)
def test_hidden_readonly_and_typed_date_rejected(field, value):
    d = definition()
    s = engine.initial(d)
    with pytest.raises(AppError):
        engine.apply(d, s, cmd("save", values={field: value}), "exam")


def test_defaults_and_private_properties():
    d = definition()
    s = engine.initial(d)
    assert s["values"]["birth_date"] == "2000-01-01"
    public = engine.public_state(d, s, "exam")
    assert "hidden_field" not in {c["id"] for c in public["screen"]["components"]}
    dumped = json.dumps(public)
    for key in [
        '"events"',
        '"validation"',
        '"visible_when"',
        '"binding"',
        '"expected"',
        '"default_value"',
    ]:
        assert key not in dumped


def event_definition():
    d = definition().model_dump()
    s = next(s for s in d["screens"] if s["id"] == "search")
    d["variables"] = [
        {
            "id": "verified_var",
            "label": {"ru": "Проверка", "uz": "Tekshiruv"},
            "value": False,
        }
    ]
    s["transitions"] = []
    s["rules"] = []
    s["events"] = [
        {
            "id": "approve",
            "on": "click",
            "component_id": "next",
            "conditions": [{"field": "client_id", "op": "eq", "value": "TEST-001"}],
            "actions": [
                {"type": "set", "field": "verified_var", "value": True},
                {"type": "show", "target": "hidden_field"},
                {"type": "award", "points": 20},
                {"type": "goto", "target": "client"},
            ],
            "otherwise": [
                {
                    "type": "error",
                    "message": {"ru": "Неверный клиент", "uz": "Notoʻgʻri mijoz"},
                    "points": 10,
                }
            ],
        }
    ]
    return Definition.model_validate(d)


def test_event_branches_unique_score_and_server_variables():
    d = event_definition()
    s = engine.initial(d)
    s, _, _ = engine.apply(d, s, cmd(), "exam")
    s, _, _ = engine.apply(d, s, cmd(), "exam")
    s, errors, done = engine.apply(d, s, cmd(values={"client_id": "TEST-002"}), "exam")
    assert errors and s["screen"] == "search" and not done
    s, errors, done = engine.apply(d, s, cmd(values={"client_id": "TEST-001"}), "exam")
    assert (
        not errors
        and s["screen"] == "client"
        and s["variables"]["verified_var"] is True
    )
    assert sum(s["awards"].values()) == 20 and len(s["mistakes"]) == 1
    s["screen"] = "search"
    s, _, _ = engine.apply(d, s, cmd(values={"client_id": "TEST-001"}), "exam")
    assert sum(s["awards"].values()) == 20
    with pytest.raises(AppError):
        engine.apply(d, s, cmd("save", values={"verified_var": True}), "exam")


def test_automatic_transition_cycle_is_bounded():
    d = event_definition().model_dump()
    d["screens"][0]["events"].append(
        {"id": "cycle", "on": "enter", "actions": [{"type": "goto", "target": "start"}]}
    )
    d = Definition.model_validate(d)
    with pytest.raises(AppError, match="practice.event_limit"):
        engine.initial(d)


def test_task_public_binding_does_not_read_expected():
    d = definition().model_dump()
    next(c for c in d["screens"][0]["components"] if c["id"] == "birth_date")[
        "binding"
    ] = "training_date"
    for t in d["tasks"]:
        t["data"] = {"training_date": "2001-02-03"}
    d = Definition.model_validate(d)
    s = engine.initial(d, d.tasks[-1].id)
    assert s["values"]["birth_date"] == "2001-02-03"
    assert "expected" not in json.dumps(engine.public_state(d, s, "exam"))


def test_full_credit_studio_http_lifecycle(client, db, setup, make_client):
    admin, user, original = setup
    login(client, admin)
    d = demo_definition().model_dump()
    created = client.post(
        "/api/v1/admin/practices",
        json={"module_id": original.module_id, "definition": d},
    )
    assert created.status_code == 201
    row = created.json()
    sid = row["id"]
    assert client.post(
        "/api/v1/admin/practices/check/definition",
        json={"expected_revision": 0, "definition": d},
    ).json()["valid"]
    preview = client.post(
        "/api/v1/admin/practices/preview/step",
        json={
            "definition": d,
            "state": engine.initial(demo_definition()),
            "initialize": True,
            "mode": "exam",
            "command": cmd("save").model_dump(),
        },
    )
    assert preview.status_code == 200 and preview.json()["state"]["screen"] == "start"
    assert db.scalar(select(PracticeResult.id)) is None
    assert (
        client.post(
            f"/api/v1/admin/practices/{sid}/preview", json={"expected_revision": 0}
        ).status_code
        == 200
    )
    assert client.post(
        f"/api/v1/admin/practices/{sid}/publish", json={"expected_revision": 0}
    ).json()["published"]
    learner = make_client()
    login(learner, user)
    session = learner.post(
        f"/api/v1/me/practices/{sid}/sessions", json={"mode": "exam"}
    ).json()
    task = next(
        t
        for t in d["tasks"]
        if t["id"] == db.get(PracticeSession, session["id"]).state["task_id"]
    )
    values = {
        "search": {"client_id": "TEST-001"},
        "create": {"product": "consumer"},
        "form": task["expected"],
        "documents": {"document": "passport", "verified": True},
        "review": {"consent": True},
    }
    for n in range(15):
        terminal = session["can_finish"]
        response = learner.post(
            f'/api/v1/me/practice-sessions/{session["id"]}/commands',
            json={
                "request_id": f"lifecycle-{n}",
                "expected_revision": session["revision"],
                "kind": "finish" if terminal else "action",
                "action": "next",
                "values": values.get(session["screen"]["id"], {}),
            },
        )
        assert response.status_code == 200, response.text
        session = response.json()
        if terminal:
            break
    assert session["result"]["passed"] and session["result"]["score_pct"] == 100
    report = client.get(f'/api/v1/reports/practice/sessions/{session["id"]}').json()
    assert (
        report["version"] == 1
        and report["task_id"] == task["id"]
        and report["finished_at"]
    )
    assert (
        len(report["actions"]) >= 6
        and next(a for a in report["actions"] if "client_id" in a["details"]["values"])[
            "details"
        ]["values"]["client_id"]
        == "TEST-001"
    )
    copied = client.post(f"/api/v1/admin/practices/{sid}/copy", json={}).json()
    assert copied["id"] != sid and not copied["published"]
    assert client.post(f"/api/v1/admin/practices/{sid}/archive").json()["archived"]
    assert sid not in {s["id"] for s in learner.get("/api/v1/me/practices").json()}
    assert learner.get(f'/api/v1/me/practice-sessions/{session["id"]}').json()[
        "result"
    ]["passed"]
    assert not client.post(
        f"/api/v1/admin/practices/{sid}/archive?archived=false"
    ).json()["archived"]
    assert learner.post(f"/api/v1/admin/practices/{sid}/copy").status_code == 403


def test_real_file_upload_ownership_and_preview_isolation(
    client, db, setup, make_client
):
    admin, user, row = setup
    d = demo_definition().model_dump()
    d["screens"][0]["components"].append(
        {
            "id": "attachment",
            "type": "file",
            "label": {"ru": "Документ", "uz": "Hujjat"},
        }
    )
    practice.edit(db, admin, row.id, DraftIn(expected_revision=0, definition=d))
    v = practice.version(db, row.id, published=False)
    v.preview_revision = v.revision
    practice.publish(db, admin, row.id, v.revision)
    learner = make_client()
    login(learner, user)
    s = learner.post(
        f"/api/v1/me/practices/{row.id}/sessions", json={"mode": "guided"}
    ).json()
    url = f'/api/v1/me/practice-sessions/{s["id"]}'
    assert (
        learner.put(url + "/files/attachment", content=b"<html>bad</html>").status_code
        == 422
    )
    upload = learner.put(
        url + "/files/attachment?filename=training.pdf", content=b"%PDF-1.7\nsynthetic"
    ).json()
    assert upload["value"].startswith("upload_")
    response = learner.post(
        url + "/commands",
        json={
            "request_id": "upload-test",
            "expected_revision": s["revision"],
            "kind": "save",
            "values": {"attachment": upload["value"]},
        },
    )
    assert response.status_code == 200
    assert response.json()["screen"]["components"][-1]["upload_name"] == "training.pdf"
    assert (
        learner.get(url + "/files/" + upload["value"].removeprefix("upload_"))
        .headers["content-disposition"]
        .startswith("attachment;")
    )
    assert (
        learner.post(
            url + "/commands",
            json={
                "request_id": "forged-file",
                "expected_revision": response.json()["revision"],
                "kind": "save",
                "values": {"attachment": "upload_999999"},
            },
        ).status_code
        == 422
    )


@pytest.mark.parametrize("kind", ["credit", "client", "transfer", "deposit"])
def test_banking_templates_are_editable_valid_scenarios(kind):
    from app.services.practice_templates import template_definition

    d = template_definition(kind)
    assert d.title.ru and d.title.uz and len(d.screens) >= 4
    assert engine.initial(d)["screen"] == d.start
    assert Definition.model_validate(d.model_dump())


def test_positive_scoring_and_hints_only_in_guided_mode():
    d = event_definition().model_dump()
    d["metadata"]["scoring"] = "points"
    d["metadata"]["max_points"] = 20
    d = Definition.model_validate(d)
    s = engine.initial(d)
    s, _, _ = engine.apply(d, s, cmd(), "guided")
    s, _, _ = engine.apply(d, s, cmd(), "guided")
    s, _, _ = engine.apply(d, s, cmd(values={"client_id": "TEST-001"}), "guided")
    assert engine.grade(d, s, "exam", 80) == (100, True)
    s["expired"] = True
    assert engine.grade(d, s, "exam", 80) == (0, False)
    s = engine.initial(d)
    s, _, _ = engine.apply(d, s, cmd("hint", action="next"), "guided")
    assert s["hints_used"] == ["next"]
    with pytest.raises(AppError):
        engine.apply(d, s, cmd("hint", action="next"), "exam")


def test_validation_message_and_recursive_task_condition():
    d = event_definition().model_dump()
    search = next(s for s in d["screens"] if s["id"] == "search")
    search["events"][0]["conditions"] = [
        {
            "op": "all",
            "children": [{"field": "client_id", "op": "eq", "value": "TEST-001"}],
        }
    ]
    c = next(c for c in d["screens"][0]["components"] if c["id"] == "birth_date")
    c["validation"] = [
        {
            "kind": "min_length",
            "value": 20,
            "message": {"ru": "Слишком коротко", "uz": "Juda qisqa"},
        }
    ]
    d = Definition.model_validate(d)
    s = engine.initial(d)
    s, errors, done = engine.apply(d, s, cmd(), "exam")
    assert errors and not done and s["screen"] == "start"
    assert errors[0]["message"]["ru"] == "Слишком коротко"


def test_active_time_limit_is_enforced_on_server(db, setup, clock):
    admin, user, row = setup
    d = demo_definition().model_dump()
    d["metadata"]["time_limit_s"] = 10
    practice.edit(db, admin, row.id, DraftIn(expected_revision=0, definition=d))
    v = practice.version(db, row.id, published=False)
    v.preview_revision = v.revision
    practice.publish(db, admin, row.id, v.revision)
    s = practice.start(db, user, row.id, "exam")
    clock.advance(seconds=11)
    result = practice.command(
        db,
        user,
        s.id,
        Command(request_id="expired-attempt", expected_revision=0, kind="save"),
    )
    assert result["status"] == "completed" and result["result"]["score_pct"] == 0
    assert result["result"]["passed"] is False and result["result"]["duration_s"] == 11


def test_new_private_report_respects_branch_boundary(client, db, setup):
    admin, user, row = setup
    from tests.factories import Reference
    from app.models import Branch

    s = practice.start(db, user, row.id, "guided")
    other = db.scalar(select(Branch).where(Branch.id != user.branch_id))
    head = make_user(db, role=AccessRole.branch_head, branch=other)
    login(client, head)
    assert client.get(f"/api/v1/reports/practice/sessions/{s.id}").status_code == 404


def test_preview_timer_result_has_no_real_statistics(client, db, setup):
    admin, user, row = setup
    login(client, admin)
    d = demo_definition().model_dump()
    d["metadata"]["time_limit_s"] = 10
    state = engine.initial(demo_definition())
    state["elapsed_s"] = 11
    response = client.post(
        "/api/v1/admin/practices/preview/step",
        json={
            "definition": d,
            "mode": "exam",
            "state": state,
            "command": cmd("save").model_dump(),
        },
    )
    assert response.status_code == 200
    assert response.json()["finished"] and response.json()["result"]["score_pct"] == 0
    assert response.json()["result"]["expired"] is True
    assert db.scalar(select(PracticeResult.id)) is None
    assert db.scalar(select(PracticeSession.id)) is None


def test_opening_hint_preserves_unsaved_input_and_default_can_be_cleared():
    d = definition()
    s = engine.initial(d)
    s, errors, _ = engine.apply(
        d, s, cmd("hint", action="next", values={"birth_date": "2001-02-03"}), "guided"
    )
    assert s["values"]["birth_date"] == "2001-02-03" and not errors
    s, _, _ = engine.apply(d, s, cmd("save", values={"birth_date": None}), "guided")
    assert "birth_date" not in s["values"]
