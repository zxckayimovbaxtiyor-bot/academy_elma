import type {
  ComponentType,
  Definition,
  LText,
  PComponent,
  PScreen,
  Condition,
  LessonSettings,
} from "../api/practice";
export const lt = (ru = "", uz = ""): LText => ({ ru, uz });
export const uid = (prefix = "item") =>
  `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
export const settings: LessonSettings = {
  difficulty: "beginner",
  estimated_minutes: 10,
  default_mode: "guided",
  scoring: "penalty",
  max_points: 100,
};
export function component(type: ComponentType, label: LText): PComponent {
  return {
    id: uid("field"),
    type,
    label,
    required: false,
    options: ["select", "document", "tabs", "dialog"].includes(type)
      ? [{ value: "option_1", label: lt("Первый вариант", "Birinchi variant") }]
      : [],
    rows: [],
    hotspots: [],
    editable: true,
    visible: true,
    width: "full",
    validation: [],
  };
}
export function blank(): Definition {
  const next = component("button", lt("Продолжить", "Davom etish"));
  return {
    schema_version: 1,
    title: lt("Новый практический урок", "Yangi amaliy dars"),
    description: lt("Учебная банковская операция", "Oʻquv bank amaliyoti"),
    roles: ["learner", "branch_head"],
    start: "start",
    completion: ["result"],
    tasks: [],
    variables: [],
    metadata: { ...settings },
    screens: [
      {
        id: "start",
        title: lt("Начало", "Boshlanish"),
        description: lt(
          "Выполните учебное задание",
          "Oʻquv topshirigʻini bajaring",
        ),
        components: [next],
        transitions: [{ action: next.id, target: "result", conditions: [] }],
        rules: [],
        events: [],
      },
      {
        id: "result",
        title: lt("Результат", "Natija"),
        description: lt("Завершите практику", "Amaliyotni yakunlang"),
        components: [
          component("result", lt("Операция завершена", "Amaliyot yakunlandi")),
        ],
        transitions: [],
        rules: [],
        events: [],
      },
    ],
  };
}
export function reorder<T>(items: T[], from: number, to: number): T[] {
  if (
    from < 0 ||
    to < 0 ||
    from >= items.length ||
    to >= items.length ||
    from === to
  )
    return items;
  const out = [...items];
  const [item] = out.splice(from, 1);
  out.splice(to, 0, item);
  return out;
}
function remapCondition(c: Condition, ids: Map<string, string>): Condition {
  return {
    ...c,
    field: ids.get(c.field) ?? c.field,
    children: c.children?.map((child) => remapCondition(child, ids)),
  };
}
export function copyScreen(s: PScreen): PScreen {
  const out = structuredClone(s);
  out.id = uid("screen");
  out.title = lt(`${s.title.ru} — копия`, `${s.title.uz} — nusxa`);
  const ids = new Map(s.components.map((c) => [c.id, uid("field")]));
  out.components = out.components.map((c) => ({
    ...c,
    id: ids.get(c.id)!,
    visible_when: c.visible_when ? remapCondition(c.visible_when, ids) : null,
    hotspots: c.hotspots.map((h) => ({
      ...h,
      action: ids.get(h.action) ?? h.action,
    })),
  }));
  out.rules = out.rules.map((r) => ({
    ...r,
    id: uid("rule"),
    condition: remapCondition(r.condition, ids),
  }));
  out.transitions = out.transitions.map((t) => ({
    ...t,
    action: ids.get(t.action) ?? t.action,
    target: t.target === s.id ? out.id : t.target,
    conditions: t.conditions.map((c) => remapCondition(c, ids)),
  }));
  out.events = out.events?.map((e) => ({
    ...e,
    id: uid("event"),
    component_id: ids.get(e.component_id ?? "") ?? e.component_id,
    conditions: e.conditions.map((c) => remapCondition(c, ids)),
    actions: e.actions.map((a) => ({
      ...a,
      target:
        ids.get(a.target ?? "") ?? (a.target === s.id ? out.id : a.target),
      value_field: ids.get(a.value_field ?? "") ?? a.value_field,
    })),
    otherwise: e.otherwise.map((a) => ({
      ...a,
      target:
        ids.get(a.target ?? "") ?? (a.target === s.id ? out.id : a.target),
      value_field: ids.get(a.value_field ?? "") ?? a.value_field,
    })),
  }));
  return out;
}
export function removeScreen(d: Definition, id: string): Definition {
  if (d.screens.length <= 2) return d;
  const screens = d.screens
    .filter((s) => s.id !== id)
    .map((s) => ({
      ...s,
      transitions: s.transitions.filter((t) => t.target !== id),
      events: s.events?.map((e) => ({
        ...e,
        actions: e.actions.filter((a) => a.type !== "goto" || a.target !== id),
        otherwise: e.otherwise.filter(
          (a) => a.type !== "goto" || a.target !== id,
        ),
      })),
    }));
  return {
    ...d,
    screens,
    start: d.start === id ? screens[0].id : d.start,
    completion: d.completion.filter((c) => c !== id).length
      ? d.completion.filter((c) => c !== id)
      : [screens.at(-1)!.id],
  };
}
export function editableValues(
  screen: PScreen,
  values: Record<string, import("../api/practice").Value>,
) {
  return Object.fromEntries(
    Object.entries(values).filter(([id]) =>
      screen.components.some(
        (c) =>
          c.id === id &&
          c.editable !== false &&
          [
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
          ].includes(c.type),
      ),
    ),
  );
}
