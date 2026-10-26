"""Pure finite-state interpreter. Only fields on the current screen can be edited."""

from __future__ import annotations

from copy import deepcopy
import re
from datetime import date
from typing import Any

from app.errors import AppError
from app.schemas.practice import (
    Command,
    Condition,
    Definition,
    INPUTS,
    condition_leaves,
)


def context(state):
    return {**state["values"], **state.get("variables", {})}


def visible(c, state):
    return not state.get("hidden", {}).get(c.id, not c.visible) and (
        c.visible_when is None or matches(c.visible_when, context(state))
    )


def matches(c: Condition, values: dict) -> bool:
    if c.op in ("all", "any"):
        return (all if c.op == "all" else any)(
            matches(child, values) for child in c.children
        )
    value = values.get(c.field)
    if c.op == "empty":
        return value is None or value is False or value == ""
    if c.op == "contains":
        return isinstance(value, str) and isinstance(c.value, str) and c.value in value
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
    if c.op in ("gt", "lt", "gte", "lte"):
        if type(value) not in (int, float) or type(c.value) not in (int, float):
            return False
        return {
            "gt": value > c.value,
            "lt": value < c.value,
            "gte": value >= c.value,
            "lte": value <= c.value,
        }[c.op]
    return isinstance(c.value, list) and isinstance(value, str) and value in c.value


def initial(definition: Definition, task_id=None, mode="guided") -> dict:
    state = {
        "screen": definition.start,
        "values": {},
        "history": [],
        "visited": [definition.start],
        "mistakes": [],
        "task_id": task_id or (definition.tasks[0].id if definition.tasks else None),
        "variables": {v.id: v.value for v in definition.variables},
        "hidden": {},
        "messages": [],
        "awards": {},
        "hints_used": [],
    }

    definition = task_definition(definition, state)
    enter(definition, state, mode, [32])
    return state


def defaults(definition, state):
    task = next((t for t in definition.tasks if t.id == state.get("task_id")), None)
    screen = next(s for s in definition.screens if s.id == state["screen"])
    for c in screen.components:
        if c.type in INPUTS and c.id not in state["values"]:
            value = task.data.get(c.binding) if task and c.binding else c.default_value
            if value is not None:
                state["values"][c.id] = value


def enter(definition, state, mode, budget):
    defaults(definition, state)
    errors, _ = dispatch(definition, state, "enter", None, mode, budget)
    if errors:
        screen = next(s for s in definition.screens if s.id == state["screen"])
        record_errors(state, errors, screen, {c.id: c for c in screen.components})
        state["messages"] = (
            state.get("messages", [])
            + [
                {"type": "error", "message": e["message"]}
                for e in errors
                if e.get("message")
            ]
        )[-20:]


def dispatch(definition, state, event, component, mode, budget):
    screen = next(s for s in definition.screens if s.id == state["screen"])
    finished, errors = False, []
    for binding in screen.events:
        if binding.on != event or (
            binding.component_id and binding.component_id != component
        ):
            continue
        good = all(matches(c, context(state)) for c in binding.conditions)
        effects = binding.actions if good else binding.otherwise
        for i, effect in enumerate(effects):
            budget[0] -= 1
            if budget[0] < 0:
                raise AppError(422, "practice.event_limit")
            if effect.type in ("message", "hint") and (
                effect.type != "hint" or mode == "guided"
            ):
                state.setdefault("messages", []).append(
                    {"type": effect.type, "message": effect.message.model_dump()}
                )
                state["messages"] = state["messages"][-20:]
            elif effect.type in ("show", "hide"):
                state.setdefault("hidden", {})[effect.target] = effect.type == "hide"
            elif effect.type == "set":
                state.setdefault("variables", {})[effect.field] = (
                    context(state).get(effect.value_field)
                    if effect.value_field
                    else effect.value
                )
            elif effect.type == "award":
                award_key = f"{binding.id}_{good}_{i}"
                state.setdefault("awards", {})[award_key] = effect.points
            elif effect.type == "error":
                errors.append(
                    {
                        "id": binding.id,
                        "screen": screen.id,
                        "field": None,
                        "points": effect.points,
                        "message": effect.message.model_dump(),
                    }
                )
            elif effect.type == "check":
                if event in ("success", "failure"):
                    raise AppError(422, "practice.event_limit")
                nested, done = dispatch(
                    definition,
                    state,
                    "success" if good else "failure",
                    component,
                    mode,
                    budget,
                )
                errors.extend(nested)
                finished = finished or done
            elif effect.type in ("goto", "finish"):
                if errors:
                    return errors, False
                target = (
                    effect.target if effect.type == "goto" else definition.completion[0]
                )
                state["history"] = (state["history"] + [state["screen"]])[-100:]
                state["screen"] = target
                state["visited"] = list(dict.fromkeys([*state["visited"], target]))
                enter(definition, state, mode, budget)
                return errors, effect.type == "finish" and not any(
                    c.required and not matches(Condition(field=c.id), context(state))
                    for s in definition.screens
                    if s.id == target
                    for c in s.components
                    if c.type in INPUTS
                )
    return errors, finished


def task_definition(definition: Definition, state: dict) -> Definition:
    task = next((t for t in definition.tasks if t.id == state.get("task_id")), None)
    if task is None:
        return definition
    definition = definition.model_copy(deep=True)
    for screen in definition.screens:
        for condition in (
            [r.condition for r in screen.rules]
            + [c for tr in screen.transitions for c in tr.conditions]
            + [c for e in screen.events for c in e.conditions]
            + [c.visible_when for c in screen.components if c.visible_when]
        ):
            for leaf in condition_leaves(condition):
                if leaf.task_value:
                    leaf.value = task.expected[leaf.field]
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
    fields = {
        c.id: c
        for c in screen.components
        if c.type in INPUTS and visible(c, state) and c.editable
    }
    if not command.values.keys() <= fields.keys():
        raise AppError(422, "practice.invalid_values")
    changed = []
    for key, value in command.values.items():
        if state["values"].get(key) != value:
            changed.append(key)
        c = fields[key]
        if value is None:
            state["values"].pop(key, None)
            continue
        valid = (
            (c.type == "number" and type(value) in (int, float))
            or (c.type in ("checkbox", "switch") and type(value) is bool)
            or (c.type in ("text", "date", "file") and isinstance(value, str))
            or (
                c.type in ("select", "document", "tabs", "dialog")
                and isinstance(value, str)
                and value in {o.value for o in c.options}
            )
        )
        if c.type == "date" and valid:
            try:
                date.fromisoformat(value)
            except ValueError:
                valid = False
        if not valid:
            raise AppError(422, "practice.invalid_values")
        state["values"][key] = value
    if command.kind == "action" or (
        command.kind == "event" and command.event != "change"
    ):
        for key in changed:
            errors, finished = dispatch(definition, state, "change", key, mode, [32])
            record_errors(state, errors, screen, fields)
            if errors or finished or state["screen"] != screen.id:
                return state, errors, finished
    if command.kind == "save":
        return state, [], False
    if command.kind == "hint":
        c = next(
            (
                c
                for c in screen.components
                if c.id == command.action and (c.type == "hint" or c.hint)
            ),
            None,
        )
        if mode != "guided" or c is None or not visible(c, state):
            raise AppError(409, "practice.invalid_action")
        used = state.setdefault("hints_used", [])
        if c.id not in used:
            used.append(c.id)
        return state, [], False
    event = command.event or "click"
    if command.kind == "event" and event == "change":
        if command.action not in fields:
            raise AppError(409, "practice.invalid_action")
        errors, finished = dispatch(
            definition, state, event, command.action, mode, [32]
        )
        record_errors(state, errors, screen, fields)
        return state, errors, finished
    transitions = [t for t in screen.transitions if t.action == command.action]
    bindings = [
        e
        for e in screen.events
        if e.on == event and (not e.component_id or e.component_id == command.action)
    ]
    buttons = {
        c.id
        for c in screen.components
        if c.type in ("button", "transition") and visible(c, state) and c.editable
    }
    if command.kind != "finish" and command.action not in buttons:
        raise AppError(409, "practice.invalid_action")
    if not transitions and not bindings and command.kind != "finish":
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
    for c in fields.values():
        value = state["values"].get(c.id)
        if value is None or value == "":
            continue
        for v in c.validation:
            ok = True
            if v.kind in ("min", "max"):
                ok = type(value) in (int, float) and (
                    value >= v.value if v.kind == "min" else value <= v.value
                )
            elif v.kind in ("min_length", "max_length"):
                ok = isinstance(value, str) and (
                    len(value) >= v.value
                    if v.kind == "min_length"
                    else len(value) <= v.value
                )
            else:
                patterns = {
                    "email": r"[^\s@]+@[^\s@]+\.[^\s@]+",
                    "passport": r"[A-Z]{2}[0-9]{7}",
                    "phone": r"\+?[0-9 ()-]{7,20}",
                    "digits": r"[0-9]+",
                }
                ok = (
                    isinstance(value, str)
                    and re.fullmatch(patterns[v.kind], value) is not None
                )
            if not ok:
                errors.append(
                    {
                        "id": f"validation_{c.id}_{v.kind}",
                        "field": c.id,
                        "screen": screen.id,
                        "message": v.message.model_dump() if v.message else None,
                        "points": 5,
                    }
                )
    for rule in screen.rules:
        if not matches(rule.condition, context(state)):
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
            if all(matches(c, context(state)) for c in t.conditions)
        ),
        None,
    )
    if not errors and target is None and not bindings and command.kind != "finish":
        errors.append(
            {
                "id": "transition",
                "field": None,
                "screen": screen.id,
                "message": None,
                "points": 5,
            }
        )
    if not errors and command.kind != "finish":
        event_errors, done = dispatch(
            definition, state, "success", command.action, mode, [32]
        )
        errors.extend(event_errors)
        if not errors and (done or state["screen"] != screen.id):
            return state, [], done
    if not errors and bindings:
        event_errors, done = dispatch(
            definition, state, event, command.action, mode, [32]
        )
        errors.extend(event_errors)
        if not errors:
            return state, [], done
    if errors:
        failure_errors, _ = dispatch(
            definition, state, "failure", command.action, mode, [32]
        )
        errors.extend(failure_errors)
        record_errors(state, errors, screen, fields)
        return state, errors, False
    if command.kind == "finish":
        return state, [], True
    state["history"] = (state["history"] + [screen.id])[-100:]
    state["screen"] = target
    state["visited"] = list(dict.fromkeys([*state["visited"], target]))
    enter(definition, state, mode, [32])
    return state, [], False


def record_errors(state, errors, screen, fields):
    for error in errors:
        error["screen_title"] = screen.title.model_dump()
        field = fields.get(error.get("field"))
        error["field_label"] = field.label.model_dump() if field else None
    recorded = {(e["screen"], e["id"]) for e in state["mistakes"]}
    state["mistakes"].extend(
        e for e in errors if (e["screen"], e["id"]) not in recorded
    )


def grade(
    definition: Definition, state: dict, mode: str, pass_pct: int
) -> tuple[float, bool]:
    # A mistake costs points only once, so a retried action cannot multiply its penalty.
    mistakes = {f'{e["screen"]}:{e["id"]}': e["points"] for e in state["mistakes"]}
    score = max(0.0, 100.0 - sum(mistakes.values())) if mode == "exam" else 100.0
    if definition.metadata.scoring == "points":
        score = min(
            100.0,
            max(
                0.0,
                (sum(state.get("awards", {}).values()) - sum(mistakes.values()))
                / definition.metadata.max_points
                * 100,
            ),
        )
    if state.get("expired"):
        score = 0.0
    return score, score >= pass_pct


def public_state(
    definition: Definition, state: dict, mode: str, *, complete: bool = False
) -> dict[str, Any]:
    screen = next(s for s in definition.screens if s.id == state["screen"])
    definition = task_definition(definition, state)
    screen = next(s for s in definition.screens if s.id == state["screen"])
    data = screen.model_dump(exclude={"rules", "transitions", "events"})
    data["components"] = [
        c.model_dump(exclude={"visible_when", "validation", "binding", "default_value"})
        for c in screen.components
        if visible(c, state)
    ]
    for component in data["components"]:
        component["event_types"] = sorted(
            {e.on for e in screen.events if e.component_id == component["id"]}
        )
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
        "messages": state.get("messages", []),
        "hints_used": len(state.get("hints_used", [])),
        "time_limit_s": definition.metadata.time_limit_s,
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
