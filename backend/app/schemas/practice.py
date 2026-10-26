"""Versioned, finite scenario language. No executable expressions or remote resources."""

from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    WrapValidator,
    model_validator,
)

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
    "heading",
    "paragraph",
    "date",
    "switch",
    "video",
    "file",
    "card",
    "passport",
    "loan",
    "products",
    "operations",
    "check_status",
    "dialog",
    "timer",
    "result",
)
INPUTS = {
    "text",
    "number",
    "select",
    "checkbox",
    "document",
    "tabs",
    "date",
    "switch",
    "file",
    "dialog",
}


class Strict(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, str_strip_whitespace=True
    )


class Localized(Strict):
    ru: str = Field(max_length=2000)
    uz: str = Field(max_length=2000)


class Option(Strict):
    value: str = Field(min_length=1, max_length=100)
    label: Localized


class Condition(Strict):
    field: Key | Literal[""] | None = None
    op: Literal[
        "eq",
        "ne",
        "gt",
        "lt",
        "gte",
        "lte",
        "present",
        "empty",
        "in",
        "contains",
        "all",
        "any",
    ] = "present"
    value: Scalar | list[str] = None
    task_value: bool = False
    children: list[Condition] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def operand(self):
        if self.op in ("all", "any"):
            if not self.children or self.field or self.task_value:
                raise ValueError("invalid condition group")
            if condition_depth(self) > 4 or len(condition_leaves(self)) > 100:
                raise ValueError("condition too complex")
            return self
        if not self.field or self.children:
            raise ValueError("condition field required")
        if self.task_value:
            if self.op in ("present", "empty", "in"):
                raise ValueError("task operand requires scalar comparison")
        elif self.op in ("gt", "lt", "gte", "lte") and type(self.value) not in (
            int,
            float,
        ):
            raise ValueError("numeric operand required")
        elif self.op == "in" and not isinstance(self.value, list):
            raise ValueError("list operand required")
        elif self.op in ("eq", "ne") and isinstance(self.value, list):
            raise ValueError("scalar operand required")
        return self


def condition_depth(c):
    return 1 + max((condition_depth(child) for child in c.children), default=0)


def condition_leaves(c):
    return (
        [leaf for child in c.children for leaf in condition_leaves(child)]
        if c.children
        else [c]
    )


class Effect(Strict):
    type: Literal[
        "goto",
        "message",
        "hint",
        "show",
        "hide",
        "set",
        "check",
        "award",
        "error",
        "finish",
    ]
    target: Key | None = None
    field: Key | None = None
    value: Scalar = None
    value_field: Key | None = None
    message: Localized | None = None
    points: int = Field(default=10, ge=0, le=100)


class EventBinding(Strict):
    id: Key
    on: Literal["click", "change", "submit", "enter", "success", "failure"] = "click"
    component_id: Key | None = None
    conditions: list[Condition] = Field(default_factory=list, max_length=20)
    actions: list[Effect] = Field(default_factory=list, max_length=20)
    otherwise: list[Effect] = Field(default_factory=list, max_length=20)


class Validation(Strict):
    kind: Literal[
        "min", "max", "min_length", "max_length", "email", "passport", "phone", "digits"
    ]
    value: float | None = None
    message: Localized | None = None


class LessonSettings(Strict):
    difficulty: Literal["beginner", "intermediate", "advanced"] = "beginner"
    estimated_minutes: int = Field(default=10, ge=1, le=480)
    default_mode: Mode = "guided"
    cover_asset_id: int | None = Field(default=None, gt=0)
    scoring: Literal["penalty", "points"] = "penalty"
    max_points: int = Field(default=100, ge=1, le=5000)
    time_limit_s: int | None = Field(default=None, ge=10, le=28800)


class Variable(Strict):
    id: Key
    label: Localized
    value: Scalar = None


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
        "heading",
        "paragraph",
        "date",
        "switch",
        "video",
        "file",
        "card",
        "passport",
        "loan",
        "products",
        "operations",
        "check_status",
        "dialog",
        "timer",
        "result",
    ]
    label: Localized
    hint: Localized | None = None
    required: bool = False
    placeholder: Localized | None = None
    default_value: Scalar = None
    editable: bool = True
    visible: bool = True
    visible_when: Condition | None = None
    validation: list[Validation] = Field(default_factory=list, max_length=10)
    binding: Key | None = None
    columns: list[Option] = Field(default_factory=list, max_length=15)
    width: Literal["full", "half"] = "full"
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
    events: list[EventBinding] = Field(default_factory=list, max_length=30)


class Task(Strict):
    id: Key
    description: Localized
    expected: dict[Key, Scalar] = Field(default_factory=dict, max_length=50)
    data: dict[Key, Scalar] = Field(default_factory=dict, max_length=50)
    hint: Localized | None = None
    points: int = Field(default=100, ge=1, le=5000)


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
    metadata: LessonSettings = Field(default_factory=LessonSettings)
    variables: list[Variable] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def graph(self, info: ValidationInfo):
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 256_000:
            raise ValueError("scenario too large")
        if info.context and info.context.get("draft"):
            return self

        def bilingual(value):
            if isinstance(value, Localized) and (
                not value.ru.strip() or not value.uz.strip()
            ):
                raise ValueError("translation required")
            if isinstance(value, BaseModel):
                for nested in value.__dict__.values():
                    bilingual(nested)
            elif isinstance(value, (list, dict)):
                for nested in (value.values() if isinstance(value, dict) else value):
                    bilingual(nested)

        bilingual(self)
        screens = {s.id: s for s in self.screens}
        if (
            len(screens) != len(self.screens)
            or self.start not in screens
            or not set(self.completion) <= screens.keys()
        ):
            raise ValueError("invalid screen references")
        if self.start in self.completion:
            raise ValueError("start is terminal")
        fields, rules, events = {}, set(), set()
        component_ids = {c.id for s in self.screens for c in s.components}
        variable_ids = {v.id for v in self.variables}
        if len(variable_ids) != len(self.variables) or variable_ids & component_ids:
            raise ValueError("invalid variable")
        edges = {s.id: set() for s in self.screens}
        for s in self.screens:
            ids = [c.id for c in s.components]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate component")
            actions = {c.id for c in s.components if c.type in ("button", "transition")}
            for c in s.components:
                if c.type in INPUTS:
                    if c.id in fields and fields[c.id] != c.type:
                        raise ValueError("field type conflict")
                    fields[c.id] = c.type
                if c.type in ("select", "document", "tabs", "dialog") and not c.options:
                    raise ValueError("options required")
                if len({o.value for o in c.options}) != len(c.options):
                    raise ValueError("duplicate option")
                if c.type in ("image", "video") and c.asset_id is None:
                    raise ValueError("image needs asset")
                if any(h.action not in actions for h in c.hotspots):
                    raise ValueError("unknown hotspot action")
                candidate_values = (
                    [c.default_value] if c.default_value is not None else []
                ) + [
                    t.data[c.binding]
                    for t in self.tasks
                    if c.binding and c.binding in t.data
                ]
                for value in candidate_values:
                    if c.type == "number" and type(value) not in (int, float):
                        raise ValueError("numeric default required")
                    if c.type in ("checkbox", "switch") and type(value) is not bool:
                        raise ValueError("boolean default required")
                    if c.type in (
                        "select",
                        "document",
                        "tabs",
                        "dialog",
                    ) and value not in {o.value for o in c.options}:
                        raise ValueError("invalid default option")
                    if c.type in ("text", "date", "file") and not isinstance(
                        value, str
                    ):
                        raise ValueError("text default required")
                    if c.type == "date":
                        from datetime import date

                        date.fromisoformat(value)
                for validation in c.validation:
                    if (
                        validation.kind in ("min", "max", "min_length", "max_length")
                        and validation.value is None
                    ):
                        raise ValueError("validation value required")
            for r in s.rules:
                if r.id in rules:
                    raise ValueError("duplicate rule")
                rules.add(r.id)
            for tr in s.transitions:
                if tr.action not in actions or tr.target not in screens:
                    raise ValueError("invalid transition")
                edges[s.id].add(tr.target)
            for event in s.events:
                if event.id in events or (
                    event.component_id and event.component_id not in ids
                ):
                    raise ValueError("invalid event")
                events.add(event.id)
                for effect in [*event.actions, *event.otherwise]:
                    if effect.type == "goto":
                        if effect.target not in screens or s.id in self.completion:
                            raise ValueError("invalid transition")
                        edges[s.id].add(effect.target)
                    if (
                        effect.type in ("show", "hide")
                        and effect.target not in component_ids
                    ):
                        raise ValueError("unknown component")
                    if effect.type == "set" and effect.field not in variable_ids:
                        raise ValueError("unknown variable")
                    if (
                        effect.value_field
                        and effect.value_field not in component_ids | variable_ids
                    ):
                        raise ValueError("unknown rule field")
                    if (
                        effect.type in ("message", "hint", "error")
                        and effect.message is None
                    ):
                        raise ValueError("message required")
                    if effect.type == "finish":
                        edges[s.id].add(self.completion[0])
            if s.id not in self.completion and not edges[s.id]:
                raise ValueError("dead end")
            if s.id in self.completion and s.transitions:
                raise ValueError("terminal screen has transitions")
        for s in self.screens:
            conditions = (
                [r.condition for r in s.rules]
                + [c for tr in s.transitions for c in tr.conditions]
                + [c for event in s.events for c in event.conditions]
                + [c.visible_when for c in s.components if c.visible_when]
            )
            for condition in [leaf for c in conditions for leaf in condition_leaves(c)]:
                if condition.field not in fields.keys() | variable_ids:
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
                if kind in ("checkbox", "switch") and type(value) is not bool:
                    raise ValueError("boolean task value required")
                if kind in (
                    "text",
                    "select",
                    "document",
                    "tabs",
                    "date",
                    "file",
                    "dialog",
                ) and not isinstance(value, str):
                    raise ValueError("text task value required")
        reached = {self.start}
        while True:
            more = reached | {target for key in reached for target in edges[key]}
            if more == reached:
                break
            reached = more
        if reached != screens.keys():
            raise ValueError("unreachable screen")
        # Every screen needs a route to a terminal, including loops.
        finishable = set(self.completion)
        while True:
            more = finishable | {s.id for s in self.screens if edges[s.id] & finishable}
            if more == finishable:
                break
            finishable = more
        if finishable != screens.keys():
            raise ValueError("no completion path")
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 256_000:
            raise ValueError("scenario too large")
        return self


def draft_definition(value, _handler):
    return Definition.model_validate(value, context={"draft": True})


DraftDefinition = Annotated[Definition, WrapValidator(draft_definition)]


class ScenarioIn(Strict):
    module_id: int = Field(gt=0)
    lesson_id: int | None = Field(default=None, gt=0)
    definition: DraftDefinition


class DraftIn(Strict):
    expected_revision: int = Field(ge=0)
    definition: DraftDefinition


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


class ActivityIn(Strict):
    client_id: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    active: bool
    sequence: int = Field(ge=0)


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
        "event",
        "hint",
    ] = "action"
    action: Key | None = None
    event: Literal["click", "change", "submit"] | None = None
    target: Key | None = None
    values: dict[str, Scalar] = Field(default_factory=dict, max_length=50)

    @model_validator(mode="after")
    def bounded(self):
        if any(isinstance(v, str) and len(v) > 2000 for v in self.values.values()):
            raise ValueError("value too long")
        return self


class PreviewState(Strict):
    elapsed_s: int = Field(default=0, ge=0, le=28800)
    expired: bool = False
    screen: Key
    values: dict[Key, Scalar] = Field(default_factory=dict, max_length=2500)
    history: list[Key] = Field(default_factory=list, max_length=100)
    visited: list[Key] = Field(default_factory=list, max_length=50)
    mistakes: list[dict] = Field(default_factory=list, max_length=5000)
    task_id: Key | None = None
    variables: dict[Key, Scalar] = Field(default_factory=dict, max_length=50)
    hidden: dict[Key, bool] = Field(default_factory=dict, max_length=2500)
    messages: list[dict] = Field(default_factory=list, max_length=20)
    awards: dict[str, int] = Field(default_factory=dict, max_length=1000)
    hints_used: list[str] = Field(default_factory=list, max_length=1000)


class PreviewIn(Strict):
    pass_pct: int = Field(default=80, ge=1, le=100)
    mode: Mode = "guided"
    initialize: bool = False
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
