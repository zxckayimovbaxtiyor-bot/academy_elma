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
] as const;
export const inputTypes: readonly string[] = [
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
];
export type ComponentType = (typeof componentTypes)[number];
export type Mode = "guided" | "exam";
export interface Condition {
  field: string;
  op:
    | "eq"
    | "ne"
    | "gt"
    | "lt"
    | "gte"
    | "lte"
    | "present"
    | "empty"
    | "in"
    | "contains"
    | "all"
    | "any";
  children?: Condition[];
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
  event_types?: string[];
  upload_name?: string;
  placeholder?: LText | null;
  default_value?: Value;
  editable?: boolean;
  visible?: boolean;
  visible_when?: Condition | null;
  validation?: {
    kind:
      | "min"
      | "max"
      | "min_length"
      | "max_length"
      | "email"
      | "passport"
      | "phone"
      | "digits";
    value?: number | null;
    message?: LText | null;
  }[];
  binding?: string | null;
  columns?: { value: string; label: LText }[];
  width?: "full" | "half";
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
  events?: EventBinding[];
}
export interface Definition {
  schema_version: 1;
  title: LText;
  description: LText;
  roles: string[];
  start: string;
  screens: PScreen[];
  completion: string[];
  tasks: {
    id: string;
    description: LText;
    expected: Record<string, Value>;
    data?: Record<string, Value>;
    hint?: LText | null;
    points?: number;
  }[];
  metadata?: LessonSettings;
  variables?: { id: string; label: LText; value: Value }[];
}
export interface LessonSettings {
  difficulty: "beginner" | "intermediate" | "advanced";
  estimated_minutes: number;
  default_mode: Mode;
  cover_asset_id?: number | null;
  scoring: "penalty" | "points";
  max_points: number;
  time_limit_s?: number | null;
}
export interface Effect {
  type:
    | "goto"
    | "message"
    | "hint"
    | "show"
    | "hide"
    | "set"
    | "check"
    | "award"
    | "error"
    | "finish";
  target?: string | null;
  field?: string | null;
  value?: Value;
  value_field?: string | null;
  message?: LText | null;
  points?: number;
}
export interface EventBinding {
  id: string;
  on: "click" | "change" | "submit" | "enter" | "success" | "failure";
  component_id?: string | null;
  conditions: Condition[];
  actions: Effect[];
  otherwise: Effect[];
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
  duration_estimated?: boolean;
  expired?: boolean;
  errors: Mistake[];
}
export interface PSummary {
  metadata?: Partial<LessonSettings>;
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
  elapsed_s: number;
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
  messages?: { type: string; message: LText }[];
  hints_used?: number;
  time_limit_s?: number | null;
  task: LText | null;
}
export interface Scenario {
  archived?: boolean;
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
    | "finish"
    | "event"
    | "hint";
  event?: "click" | "change" | "submit";
  action?: string;
  values?: Record<string, Value>;
}
export interface Preview {
  result?: PResult | null;
  messages?: { type: string; message: LText }[];
  hints_used?: number;
  time_limit_s?: number | null;
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
    version_id: number;
    task_id: string | null;
    started_at: string;
    finished_at: string | null;
    hints_used: string[] | null;
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
  uploadFile: (id: number, field: string, file: File) =>
    api<{ value: string; filename: string }>(
      `/me/practice-sessions/${id}/files/${field}?filename=${encodeURIComponent(file.name)}`,
      { method: "PUT", body: file },
    ),
  session: (id: number) => get<PSession>(`/me/practice-sessions/${id}`),
  activity: (
    id: number,
    client_id: string,
    active: boolean,
    sequence: number,
    keepalive = false,
  ) =>
    api<{ elapsed_s: number }>(`/me/practice-sessions/${id}/activity`, {
      method: "POST",
      json: { client_id, active, sequence },
      keepalive,
    }),
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
  check: (definition: Definition) =>
    post<{
      valid: boolean;
      issues: { path: (string | number)[]; message: string; code?: string }[];
    }>("/admin/practices/check/definition", {
      definition,
      expected_revision: 0,
    }),
  copy: (id: number) => post<Scenario>(`/admin/practices/${id}/copy`, {}),
  archive: (id: number, archived: boolean) =>
    post<Scenario>(`/admin/practices/${id}/archive?archived=${archived}`, {}),
  uploadVideo: (id: number, file: File) =>
    api<{ id: number }>(
      `/admin/practices/${id}/video?synthetic_data_confirmed=true`,
      { method: "PUT", body: file },
    ),
  scenarios: () => get<Scenario[]>("/admin/practices"),
  template: (kind = "credit") =>
    get<Definition>(`/admin/practices/template?kind=${kind}`),
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
    mode: Mode = "guided",
    initialize = false,
    pass_pct = 80,
  ) =>
    post<Preview>("/admin/practices/preview/step", {
      definition,
      state,
      command,
      mode,
      initialize,
      pass_pct,
    }),
  upload: (id: number, file: File) =>
    api<{ id: number }>(
      `/admin/practices/${id}/screenshots?synthetic_data_confirmed=true`,
      { method: "PUT", body: file },
    ),
  sessionReport: (id: number) =>
    get<{
      version: number;
      task_id: string | null;
      task: LText | null;
      started_at: string;
      finished_at: string | null;
      hints_used: string[];
      result: PResult | null;
      actions: {
        id: number;
        at: string;
        screen: string;
        screen_title: LText | null;
        action_label: LText | null;
        values: SummaryItem[];
        kind: string;
        details: {
          action?: string;
          event?: string;
          values?: Record<string, Value>;
        };
        errors: Mistake[];
      }[];
    }>(`/reports/practice/sessions/${id}`),
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
