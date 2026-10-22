import { api, get, post, put } from "./client";

export type LText = { ru: string; uz: string };
export type Value = string | number | boolean | null;
export type SummaryItem = { field: string; label: LText; value: Value | LText };
export const componentTypes = [
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
] as const;
export type ComponentType = (typeof componentTypes)[number];
export type Mode = "guided" | "sandbox" | "exam";
export interface Condition {
  field: string;
  op: "eq" | "ne" | "gte" | "lte" | "present" | "in";
  value: Value | string[];
  task_value?: boolean;
}
export interface Rule {
  id: string;
  condition: Condition;
  message: LText;
  points: number;
}
export interface Hotspot {
  label: LText;
  action: string;
  x: number;
  y: number;
  width: number;
  height: number;
}
export interface PComponent {
  id: string;
  type: ComponentType;
  label: LText;
  hint?: LText | null;
  required: boolean;
  options: { value: string; label: LText }[];
  rows: Record<string, string>[];
  asset_id?: number | null;
  hotspots: Hotspot[];
}
export interface PScreen {
  id: string;
  title: LText;
  description: LText;
  components: PComponent[];
  transitions: { action: string; target: string; conditions: Condition[] }[];
  rules: Rule[];
}
export interface Definition {
  schema_version: 1;
  title: LText;
  description: LText;
  roles: string[];
  start: string;
  screens: PScreen[];
  completion: string[];
  tasks: { id: string; description: LText; expected: Record<string, Value> }[];
}
export interface Policy {
  required: boolean;
  require_pass: boolean;
  gate: "before_test" | "before_certificate";
  max_attempts: number;
  pass_pct: number;
  allow_repeat: boolean;
  repeat_on_update: boolean;
  repeat_on_material: boolean;
  theory_first: boolean;
}
export interface Mistake {
  id: string;
  field?: string;
  screen?: string;
  message?: LText | null;
  points?: number;
}
export interface PResult {
  score_pct: number;
  passed: boolean;
  duration_s: number;
  errors: Mistake[];
}
export interface PSummary {
  id: number;
  module_id: number;
  lesson_id: number | null;
  title: LText;
  description: LText;
  number: number;
  policy: Policy;
  sessions: {
    id: number;
    mode: Mode;
    status: string;
    result: PResult | null;
  }[];
}
export interface PSession {
  summary: SummaryItem[];
  id: number;
  scenario_id: number;
  version: number;
  mode: Mode;
  status: string;
  revision: number;
  title: LText;
  policy: Policy;
  screen: PScreen;
  values: Record<string, Value>;
  history: string[];
  visited: string[];
  can_finish: boolean;
  progress: number;
  navigation: { id: string; title: LText; visited: boolean }[];
  result: PResult | null;
  feedback?: Mistake[];
  records: {
    id: string;
    values: Record<string, Value>;
    screen: string;
    status: string;
  }[];
  record_id: string | null;
  task: LText | null;
}
export interface Scenario {
  id: number;
  module_id: number;
  lesson_id: number | null;
  version_id: number;
  number: number;
  revision: number;
  published: boolean;
  live_version: number | null;
  definition: Definition;
  policy: Policy;
}
export interface Command {
  request_id: string;
  expected_revision: number;
  kind:
    | "action"
    | "save"
    | "back"
    | "reset"
    | "finish"
    | "navigate"
    | "new_record"
    | "open_record"
    | "delete_record";
  action?: string;
  target?: string;
  values?: Record<string, Value>;
}
export interface Preview {
  task: LText | null;
  summary: SummaryItem[];
  state: Record<string, unknown>;
  screen: PScreen;
  values: Record<string, Value>;
  history: string[];
  can_finish: boolean;
  progress: number;
  feedback?: Mistake[];
  finished?: boolean;
}
export interface Metrics {
  started: number;
  completed: number;
  pass_rate: number;
  average_seconds: number;
}
export interface Analytics extends Metrics {
  total: number;
  page: number;
  page_size: number;
  error_labels: Record<string, LText | null>;
  stage_labels: Record<string, LText | null>;
  retries: number;
  errors: Record<string, number>;
  stages: Record<string, number>;
  branches: (Metrics & { id: number | null; title: LText | null })[];
  roles: (Metrics & { id: number | null; title: LText | null })[];
  employees: (Metrics & { id: number })[];
  sessions: {
    id: number;
    user_id: number;
    full_name: string;
    employee_id: string;
    branch_id: number | null;
    job_role_id: number | null;
    scenario_id: number;
    mode: Mode;
    status: string;
    score_pct: number | null;
    passed: boolean | null;
    duration_s: number | null;
  }[];
}
export const practice = {
  list: (moduleId?: number, lessonId?: number) =>
    get<PSummary[]>(
      `/me/practices?${new URLSearchParams({ ...(moduleId ? { module_id: String(moduleId) } : {}), ...(lessonId ? { lesson_id: String(lessonId) } : {}) })}`,
    ),
  start: (id: number, mode: Mode) =>
    post<PSession>(`/me/practices/${id}/sessions`, { mode }),
  session: (id: number) => get<PSession>(`/me/practice-sessions/${id}`),
  history: (id: number) =>
    get<
      {
        id: number;
        kind: Command["kind"];
        screen_id: string;
        at: string;
        invalid: boolean;
      }[]
    >(`/me/practice-sessions/${id}/actions`),
  command: (id: number, data: Command) =>
    post<PSession>(`/me/practice-sessions/${id}/commands`, data),
  scenarios: () => get<Scenario[]>("/admin/practices"),
  template: () => get<Definition>("/admin/practices/template"),
  create: (
    module_id: number,
    lesson_id: number | null,
    definition: Definition,
  ) => post<Scenario>("/admin/practices", { module_id, lesson_id, definition }),
  save: (id: number, expected_revision: number, definition: Definition) =>
    put<Scenario>(`/admin/practices/${id}/draft`, {
      expected_revision,
      definition,
    }),
  publish: (id: number, expected_revision: number) =>
    post<Scenario>(`/admin/practices/${id}/publish`, { expected_revision }),
  review: (id: number, expected_revision: number) =>
    post<{ revision: number }>(`/admin/practices/${id}/preview`, {
      expected_revision,
    }),
  assign: (id: number, policy: Policy) =>
    put<Policy>(`/admin/practices/${id}/assignment`, policy),
  preview: (
    definition: Definition,
    state: Record<string, unknown>,
    command: Command,
  ) =>
    post<Preview>("/admin/practices/preview/step", {
      definition,
      state,
      command,
    }),
  upload: (id: number, file: File) =>
    api<{ id: number }>(
      `/admin/practices/${id}/screenshots?synthetic_data_confirmed=true`,
      { method: "PUT", body: file },
    ),
  analytics: (filters: Record<string, string | number | undefined> = {}) =>
    get<Analytics>(
      `/reports/practice?${new URLSearchParams(
        Object.fromEntries(
          Object.entries(filters)
            .filter(([, v]) => v !== undefined)
            .map(([k, v]) => [k, String(v)]),
        ),
      )}`,
    ),
};
