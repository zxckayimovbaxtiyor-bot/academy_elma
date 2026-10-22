"""Pure finite-state interpreter. Only fields on the current screen can be edited."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.errors import AppError
from app.schemas.practice import Command, Condition, Definition

INPUTS = {"text", "number", "select", "checkbox", "document", "tabs"}


def matches(c: Condition, values: dict) -> bool:
    value = values.get(c.field)
    if c.op == "present":
        return (
            value is not None
            and value is not False
            and (not isinstance(value, str) or bool(value.strip()))
        )
    if c.op == "eq":
        return (
            (type(value) in (int, float) and type(c.value) in (int, float))
            or type(value) is type(c.value)
        ) and value == c.value
    if c.op == "ne":
        return not (
            (
                (type(value) in (int, float) and type(c.value) in (int, float))
                or type(value) is type(c.value)
            )
            and value == c.value
        )
    if c.op in ("gte", "lte"):
        if type(value) not in (int, float) or type(c.value) not in (int, float):
            return False
        return value >= c.value if c.op == "gte" else value <= c.value
    return isinstance(c.value, list) and isinstance(value, str) and value in c.value


def initial(definition: Definition) -> dict:
    return {
        "screen": definition.start,
        "values": {},
        "history": [],
        "visited": [definition.start],
        "mistakes": [],
        "task_id": definition.tasks[0].id if definition.tasks else None,
    }


def task_definition(definition: Definition, state: dict) -> Definition:
    task = next((t for t in definition.tasks if t.id == state.get("task_id")), None)
    if task is None:
        return definition
    definition = definition.model_copy(deep=True)
    for screen in definition.screens:
        for condition in [r.condition for r in screen.rules] + [
            c for tr in screen.transitions for c in tr.conditions
        ]:
            if condition.task_value:
                condition.value = task.expected[condition.field]
    return definition


def sync_record(state: dict, definition: Definition):
    for record in state.get("records", []):
        if record["id"] == state.get("record_id"):
            record.update(
                values=deepcopy(state["values"]),
                screen=state["screen"],
                status=(
                    "submitted" if state["screen"] in definition.completion else "draft"
                ),
            )


def workspace(definition: Definition, state: dict, command: Command) -> dict:
    sync_record(state, definition)
    records = state.get("records", [])
    if command.kind == "navigate":
        if command.target not in {s.id for s in definition.screens}:
            raise AppError(409, "practice.invalid_action")
        state["history"] = (state["history"] + [state["screen"]])[-100:]
        state["screen"] = command.target
        state["visited"] = list(dict.fromkeys([*state["visited"], command.target]))
        return state
    if command.kind == "new_record":
        if len(records) >= 20:
            raise AppError(409, "practice.record_limit")
        n = state.get("next_record", 1)
        record = {
            "id": f"application_{n}",
            "values": {},
            "screen": definition.start,
            "status": "draft",
        }
        records.append(record)
        state["next_record"] = n + 1
    else:
        record = next((r for r in records if r["id"] == command.target), None)
        if record is None:
            raise AppError(409, "practice.invalid_action")
        if command.kind == "delete_record":
            records.remove(record)
            record = records[0] if records else None
    state.update(initial(definition))
    state["records"] = records
    state["record_id"] = record["id"] if record else None
    if record:
        state["values"] = deepcopy(record["values"])
        state["screen"] = record["screen"]
    return state


def apply(
    definition: Definition, state: dict, command: Command, mode: str
) -> tuple[dict, list[dict], bool]:
    state = deepcopy(state)
    definition = task_definition(definition, state)
    screen = next(s for s in definition.screens if s.id == state["screen"])
    if command.kind in ("navigate", "new_record", "open_record", "delete_record"):
        if mode != "sandbox":
            raise AppError(409, "practice.invalid_action")
        return workspace(definition, state, command), [], False
    if command.kind == "reset":
        if mode != "sandbox":
            raise AppError(409, "practice.invalid_action")
        return initial(definition), [], False
    if command.kind == "back":
        if mode == "exam" or not state["history"]:
            raise AppError(409, "practice.invalid_action")
        state["screen"] = state["history"].pop()
        return state, [], False
    if command.kind == "finish":
        if state["screen"] not in definition.completion:
            raise AppError(409, "practice.incomplete")
    fields = {c.id: c for c in screen.components if c.type in INPUTS}
    if not command.values.keys() <= fields.keys():
        raise AppError(422, "practice.invalid_values")
    for key, value in command.values.items():
        c = fields[key]
        if value is None:
            state["values"].pop(key, None)
            continue
        valid = (
            (c.type == "number" and type(value) in (int, float))
            or (c.type == "checkbox" and type(value) is bool)
            or (c.type == "text" and isinstance(value, str))
            or (
                c.type in ("select", "document", "tabs")
                and isinstance(value, str)
                and value in {o.value for o in c.options}
            )
        )
        if not valid:
            raise AppError(422, "practice.invalid_values")
        state["values"][key] = value
    if command.kind == "save":
        return state, [], False
    transitions = [t for t in screen.transitions if t.action == command.action]
    if not transitions and command.kind != "finish":
        raise AppError(409, "practice.invalid_action")
    errors = []
    for c in fields.values():
        if c.required and not matches(Condition(field=c.id), state["values"]):
            errors.append(
                {
                    "id": f"required_{c.id}",
                    "field": c.id,
                    "screen": screen.id,
                    "message": None,
                    "points": 5,
                }
            )
    for rule in screen.rules:
        if not matches(rule.condition, state["values"]):
            errors.append(
                {
                    "id": rule.id,
                    "field": rule.condition.field,
                    "screen": screen.id,
                    "message": rule.message.model_dump(),
                    "points": rule.points,
                }
            )
    target = next(
        (
            t.target
            for t in transitions
            if all(matches(c, state["values"]) for c in t.conditions)
        ),
        None,
    )
    if not errors and target is None and command.kind != "finish":
        errors.append(
            {
                "id": "transition",
                "field": None,
                "screen": screen.id,
                "message": None,
                "points": 5,
            }
        )
    if errors:
        for error in errors:
            error["screen_title"] = screen.title.model_dump()
            field = fields.get(error["field"])
            error["field_label"] = field.label.model_dump() if field else None
        recorded = {(e["screen"], e["id"]) for e in state["mistakes"]}
        state["mistakes"].extend(
            e for e in errors if (e["screen"], e["id"]) not in recorded
        )
        return state, errors, False
    if command.kind == "finish":
        return state, [], True
    state["history"] = (state["history"] + [screen.id])[-100:]
    state["screen"] = target
    state["visited"] = list(dict.fromkeys([*state["visited"], target]))
    return state, [], False


def grade(
    definition: Definition, state: dict, mode: str, pass_pct: int
) -> tuple[float, bool]:
    # A mistake costs points only once, so a retried action cannot multiply its penalty.
    mistakes = {f'{e["screen"]}:{e["id"]}': e["points"] for e in state["mistakes"]}
    score = max(0.0, 100.0 - sum(mistakes.values())) if mode == "exam" else 100.0
    return score, score >= pass_pct


def public_state(
    definition: Definition, state: dict, mode: str, *, complete: bool = False
) -> dict[str, Any]:
    screen = next(s for s in definition.screens if s.id == state["screen"])
    data = screen.model_dump(exclude={"rules", "transitions"})
    # Never return grading rules, transition conditions or their expected values.
    if mode != "guided":
        for c in data["components"]:
            c.pop("hint", None)
        data["components"] = [c for c in data["components"] if c["type"] != "hint"]
    fields = {
        c.id: c for s in definition.screens for c in s.components if c.type in INPUTS
    }
    summary = []
    for key, value in state["values"].items():
        c = fields.get(key)
        if c:
            option = next(
                (o.label.model_dump() for o in c.options if o.value == value), None
            )
            summary.append(
                {"field": key, "label": c.label.model_dump(), "value": option or value}
            )
    return {
        "screen": data,
        "values": state["values"],
        "history": state["history"],
        "summary": summary,
        "task": next(
            (
                t.description.model_dump()
                for t in definition.tasks
                if t.id == state.get("task_id")
            ),
            None,
        ),
        "visited": state["visited"],
        "can_finish": screen.id in definition.completion,
        "progress": round(len(state["visited"]) / len(definition.screens) * 100),
        "navigation": [
            {
                "id": s.id,
                "title": s.title.model_dump(),
                "visited": s.id in state["visited"],
            }
            for s in definition.screens
        ],
        "mistakes": state["mistakes"] if complete else [],
    }
