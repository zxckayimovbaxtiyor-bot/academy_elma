"""Versioned, finite scenario language. No executable expressions or remote resources."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Key = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
Scalar = str | int | float | bool | None
Mode = Literal["guided", "sandbox", "exam"]
COMPONENTS = (
    "button",
    "text",
    "number",
    "select",
    "table",
    "tabs",
    "checkbox",
    "modal",
    "document",
    "client",
    "status",
    "notification",
    "image",
    "hint",
    "transition",
)


class Strict(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, str_strip_whitespace=True
    )


class Localized(Strict):
    ru: str = Field(min_length=1, max_length=2000)
    uz: str = Field(min_length=1, max_length=2000)


class Option(Strict):
    value: str = Field(min_length=1, max_length=100)
    label: Localized


class Condition(Strict):
    field: Key
    op: Literal["eq", "ne", "gte", "lte", "present", "in"] = "present"
    value: Scalar | list[str] = None
    task_value: bool = False

    @model_validator(mode="after")
    def operand(self):
        if self.task_value:
            if self.op in ("present", "in"):
                raise ValueError("task operand requires scalar comparison")
        elif self.op in ("gte", "lte") and type(self.value) not in (int, float):
            raise ValueError("numeric operand required")
        elif self.op == "in" and not isinstance(self.value, list):
            raise ValueError("list operand required")
        elif self.op in ("eq", "ne") and isinstance(self.value, list):
            raise ValueError("scalar operand required")
        return self


class PracticeRule(Strict):
    id: Key
    condition: Condition
    message: Localized
    points: int = Field(default=10, ge=1, le=100)


class Component(Strict):
    id: Key
    type: Literal[
        "button",
        "text",
        "number",
        "select",
        "table",
        "tabs",
        "checkbox",
        "modal",
        "document",
        "client",
        "status",
        "notification",
        "image",
        "hint",
        "transition",
    ]
    label: Localized
    hint: Localized | None = None
    required: bool = False
    options: list[Option] = Field(default_factory=list, max_length=50)
    rows: list[dict[str, str]] = Field(default_factory=list, max_length=50)
    asset_id: int | None = Field(default=None, gt=0)
    # Percentage coordinates for interactive areas on an authorized screenshot.
    hotspots: list[Hotspot] = Field(default_factory=list, max_length=30)


class Hotspot(Strict):
    label: Localized
    action: Key
    x: float = Field(ge=0, le=95)
    y: float = Field(ge=0, le=95)
    width: float = Field(default=10, gt=0, le=100)
    height: float = Field(default=10, gt=0, le=100)

    @model_validator(mode="after")
    def bounds(self):
        if self.x + self.width > 100 or self.y + self.height > 100:
            raise ValueError("hotspot bounds")
        return self


Component.model_rebuild()


class Transition(Strict):
    action: Key
    target: Key
    conditions: list[Condition] = Field(default_factory=list, max_length=20)


class PracticeScreen(Strict):
    id: Key
    title: Localized
    description: Localized
    components: list[Component] = Field(default_factory=list, max_length=50)
    transitions: list[Transition] = Field(default_factory=list, max_length=30)
    rules: list[PracticeRule] = Field(default_factory=list, max_length=50)


class Task(Strict):
    id: Key
    description: Localized
    expected: dict[Key, Scalar] = Field(default_factory=dict, max_length=50)


class Definition(Strict):
    schema_version: Literal[1] = 1
    title: Localized
    description: Localized
    roles: list[Literal["learner", "branch_head", "methodologist", "admin"]] = Field(
        default_factory=lambda: ["learner", "branch_head"], min_length=1, max_length=4
    )
    start: Key
    screens: list[PracticeScreen] = Field(min_length=2, max_length=50)
    completion: list[Key] = Field(min_length=1, max_length=10)
    tasks: list[Task] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def graph(self):
        screens = {s.id: s for s in self.screens}
        if (
            len(screens) != len(self.screens)
            or self.start not in screens
            or not set(self.completion) <= screens.keys()
        ):
            raise ValueError("invalid screen references")
        if self.start in self.completion:
            raise ValueError("start is terminal")
        fields, rules = {}, set()
        for s in self.screens:
            ids = [c.id for c in s.components]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate component")
            actions = {c.id for c in s.components if c.type in ("button", "transition")}
            for c in s.components:
                if c.type in (
                    "text",
                    "number",
                    "select",
                    "checkbox",
                    "document",
                    "tabs",
                ):
                    if c.id in fields and fields[c.id] != c.type:
                        raise ValueError("field type conflict")
                    fields[c.id] = c.type
                if c.type in ("select", "document", "tabs") and not c.options:
                    raise ValueError("options required")
                if len({o.value for o in c.options}) != len(c.options):
                    raise ValueError("duplicate option")
                if c.type == "image" and c.asset_id is None:
                    raise ValueError("image needs asset")
                if any(h.action not in actions for h in c.hotspots):
                    raise ValueError("unknown hotspot action")
            for r in s.rules:
                if r.id in rules:
                    raise ValueError("duplicate rule")
                rules.add(r.id)
            for tr in s.transitions:
                if tr.action not in actions or tr.target not in screens:
                    raise ValueError("invalid transition")
            if s.id not in self.completion and not s.transitions:
                raise ValueError("dead end")
            if s.id in self.completion and s.transitions:
                raise ValueError("terminal screen has transitions")
        for s in self.screens:
            for condition in [r.condition for r in s.rules] + [
                c for tr in s.transitions for c in tr.conditions
            ]:
                if condition.field not in fields:
                    raise ValueError("unknown rule field")
                if condition.task_value and (
                    not self.tasks
                    or any(condition.field not in t.expected for t in self.tasks)
                ):
                    raise ValueError("missing task value")
        if len({t.id for t in self.tasks}) != len(self.tasks):
            raise ValueError("duplicate task")
        if any(not t.expected.keys() <= fields.keys() for t in self.tasks):
            raise ValueError("unknown task field")
        for task in self.tasks:
            for key, value in task.expected.items():
                kind = fields[key]
                if kind == "number" and type(value) not in (int, float):
                    raise ValueError("numeric task value required")
                if kind == "checkbox" and type(value) is not bool:
                    raise ValueError("boolean task value required")
                if kind in ("text", "select", "document", "tabs") and not isinstance(
                    value, str
                ):
                    raise ValueError("text task value required")
        reached = {self.start}
        while True:
            more = reached | {
                tr.target for key in reached for tr in screens[key].transitions
            }
            if more == reached:
                break
            reached = more
        if reached != screens.keys():
            raise ValueError("unreachable screen")
        # Every screen needs a route to a terminal, including loops.
        finishable = set(self.completion)
        while True:
            more = finishable | {
                s.id
                for s in self.screens
                if any(t.target in finishable for t in s.transitions)
            }
            if more == finishable:
                break
            finishable = more
        if finishable != screens.keys():
            raise ValueError("no completion path")
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 256_000:
            raise ValueError("scenario too large")
        return self


class ScenarioIn(Strict):
    module_id: int = Field(gt=0)
    lesson_id: int | None = Field(default=None, gt=0)
    definition: Definition


class DraftIn(Strict):
    expected_revision: int = Field(ge=0)
    definition: Definition


class PublishIn(Strict):
    expected_revision: int = Field(ge=0)


class AssignmentIn(Strict):
    required: bool = False
    require_pass: bool = True
    gate: Literal["before_test", "before_certificate"] = "before_test"
    max_attempts: int = Field(default=3, ge=1, le=20)
    pass_pct: int = Field(default=80, ge=1, le=100)
    allow_repeat: bool = True
    repeat_on_update: bool = False
    repeat_on_material: bool = False
    theory_first: bool = False


class StartIn(Strict):
    mode: Mode = "guided"


class Command(Strict):
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    expected_revision: int = Field(ge=0)
    kind: Literal[
        "action",
        "save",
        "back",
        "reset",
        "finish",
        "navigate",
        "new_record",
        "open_record",
        "delete_record",
    ] = "action"
    action: Key | None = None
    target: Key | None = None
    values: dict[str, Scalar] = Field(default_factory=dict, max_length=50)

    @model_validator(mode="after")
    def bounded(self):
        if any(isinstance(v, str) and len(v) > 2000 for v in self.values.values()):
            raise ValueError("value too long")
        return self


class PreviewState(Strict):
    screen: Key
    values: dict[Key, Scalar] = Field(default_factory=dict, max_length=2500)
    history: list[Key] = Field(default_factory=list, max_length=100)
    visited: list[Key] = Field(default_factory=list, max_length=50)
    mistakes: list[dict] = Field(default_factory=list, max_length=5000)
    task_id: Key | None = None


class PreviewIn(Strict):
    definition: Definition
    state: PreviewState
    command: Command

    @model_validator(mode="after")
    def state_bounds(self):
        if len(json.dumps(self.state.model_dump()).encode()) > 256_000:
            raise ValueError("state too large")
        screens = {screen.id for screen in self.definition.screens}
        if (
            self.state.screen not in screens
            or not set(self.state.history + self.state.visited) <= screens
        ):
            raise ValueError("unknown preview screen")
        if self.state.task_id and self.state.task_id not in {
            t.id for t in self.definition.tasks
        }:
            raise ValueError("unknown preview task")
        return self
