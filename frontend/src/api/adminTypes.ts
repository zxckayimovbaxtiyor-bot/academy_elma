/** Shapes of the admin, methodologist and report APIs (backend/app/schemas). */

import type { AccessRole, AttemptStatus, CertStatus, Lang, ModuleState, ModuleType, QuestionType, Ref } from "./types";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// --- reference lists ------------------------------------------------------------------------

export interface BranchRef extends Ref {
  region_id: number;
}

export interface JobRoleRef extends Ref {
  is_branch_head: boolean;
}

// --- users ----------------------------------------------------------------------------------

export interface UserRow {
  id: number;
  employee_id: string;
  full_name: string;
  branch: Ref | null;
  region: Ref | null;
  job_role: Ref | null;
  access_role: AccessRole;
  preferred_language: Lang;
  is_active: boolean;
  must_change_password: boolean;
  locked_until: string | null;
  last_seen_at: string | null;
}

export interface AuditEntry {
  at: string;
  action: string;
  actor_id: number | null;
  reason: string | null;
  data: Record<string, unknown>;
}

export interface UserDetail extends UserRow {
  audit: AuditEntry[];
  learning: LearnerDetail;
}

export interface ImportProblem {
  row: number;
  employee_id: string | null;
  code: string;
  params: Record<string, unknown>;
}

export interface ImportReport {
  import_id: number;
  filename: string;
  total_rows: number;
  valid_rows: number;
  error_rows: number;
  to_create: number;
  to_update: number;
  errors: ImportProblem[];
}

export interface ImportCommit {
  import_id: number;
  created: number;
  updated: number;
  unchanged: number;
  skipped: ImportProblem[];
  temp_passwords_csv: string;
}

// --- waves ----------------------------------------------------------------------------------

export type WaveStatus = "planned" | "active" | "completed";

export interface WaveRow {
  id: number;
  name_uz: string;
  name_ru: string;
  training_start: string;
  deadline: string;
  go_live: string;
  status: WaveStatus;
  branches: number;
  learners: number;
  certified: number;
  certified_pct: number;
}

export interface WaveInput {
  name_uz: string;
  name_ru: string;
  training_start: string;
  deadline: string;
  go_live: string;
}

export interface Assignment {
  job_role_id: number;
  module_id: number;
}

export interface WaveDetail extends WaveRow {
  branch_list: (Ref & { learners: number })[];
  roles: (Ref & { learners: number })[];
  modules: { id: number; code: string; type: ModuleType; title_uz: string; title_ru: string }[];
  assignments: Assignment[];
}

// --- content --------------------------------------------------------------------------------

export interface ModuleAdmin {
  id: number;
  code: string;
  qprefix: string;
  type: ModuleType;
  title_uz: string;
  title_ru: string;
  sort: number;
  release_code: string | null;
  lessons_total: number;
  lessons_live: number;
  test_question_count: number;
  test_pass_pct: number;
  test_time_limit_min: number;
  test_max_attempts: number;
  test_cooldown_hours: number;
  test_published_at: string | null;
}

export interface ModuleInput {
  code: string;
  qprefix: string;
  type: ModuleType;
  title_uz: string;
  title_ru: string;
}

export type ModulePatch = Partial<
  Pick<
    ModuleAdmin,
    "title_uz" | "title_ru" | "test_question_count" | "test_pass_pct" | "test_time_limit_min" | "test_max_attempts" | "test_cooldown_hours"
  >
>;

export type VideoStatus = "uploaded" | "processing" | "ready" | "failed";

export interface Video {
  asset_id: string;
  status: VideoStatus;
  progress_pct: number;
  duration_s: number | null;
  error: string | null;
  original_filename: string;
}

export type VersionStatus = "draft" | "published" | "superseded";

export interface Version {
  id: number;
  release_id: number;
  release_code: string;
  status: VersionStatus;
  video: Video | null;
  vtt_uz_url: string | null;
  vtt_ru_url: string | null;
  pdf_uz_url: string | null;
  pdf_ru_url: string | null;
  published_at: string | null;
}

export interface LessonAdmin {
  id: number;
  module_id: number;
  sort: number;
  title_uz: string;
  title_ru: string;
  published: Version | null;
  draft: Version | null;
}

export interface Cue {
  start: number;
  end: number;
  text: string;
}

// --- releases -------------------------------------------------------------------------------

export interface ReleaseRow {
  id: number;
  code: string;
  notes: string;
  status: "draft" | "published";
  transition_days: number;
  created_at: string;
  published_at: string | null;
  lessons_count: number;
}

export interface ReleaseLesson {
  lesson_id: number;
  module_id: number;
  title_uz: string;
  title_ru: string;
  change: "changed" | "added";
  version: Version;
  problems: string[];
}

export interface ReleaseImpact {
  module_id: number;
  code: string;
  title_uz: string;
  title_ru: string;
  changed_lessons: number;
  added_lessons: number;
  total_lessons: number;
  certificates: number;
  learners: number;
  questions_pending: number;
  pool_have: number | null;
  pool_need: number | null;
}

export interface ReleaseDetail extends ReleaseRow {
  lessons: ReleaseLesson[];
  module_problems: { module_id: number; code: string; params: Record<string, unknown> }[];
  impact: ReleaseImpact[];
  ready: boolean;
}

// --- questions ------------------------------------------------------------------------------

export type QuestionStatus = "draft" | "approved" | "retired";

export interface OptionAdmin {
  id: number;
  sort: number;
  text_uz: string;
  text_ru: string;
  is_correct: boolean;
}

export interface QuestionAdmin {
  id: number;
  number: string;
  module_id: number;
  status: QuestionStatus;
  retired_reason: "rejected" | "manual" | "lesson_changed" | null;
  type: QuestionType;
  difficulty: number;
  lesson_id: number;
  lesson_title_uz: string;
  lesson_title_ru: string;
  lesson_version_id: number;
  release_code: string;
  version_live: boolean;
  video_ts_s: number;
  text_uz: string;
  text_ru: string;
  explanation_uz: string;
  explanation_ru: string;
  options: OptionAdmin[];
  image_url: string | null;
  origin: "manual" | "ai";
  ai_source_start_s: number | null;
  ai_source_end_s: number | null;
  ai_source_excerpt: string | null;
  stats: { attempts: number; correct: number; correct_pct: number | null; flagged: boolean };
  created_at: string;
  approved_at: string | null;
  retired_at: string | null;
}

export interface OptionInput {
  id?: number | null;
  text_uz: string;
  text_ru: string;
  is_correct: boolean;
}

export interface QuestionInput {
  lesson_id: number;
  video_ts_s: number;
  type: QuestionType;
  text_uz: string;
  text_ru: string;
  explanation_uz: string;
  explanation_ru: string;
  difficulty: number;
  options: OptionInput[];
}

export interface Pool {
  question_count: number;
  required: number;
  approved_active: number;
  by_difficulty: Record<string, number>;
  drafts: number;
  publishable: boolean;
  test_published: boolean;
}

export interface AiStatus {
  enabled: boolean;
  model: string | null;
}

export interface DraftRequest {
  source: "transcript" | "text";
  text?: string | null;
  count: number;
  types: ("single" | "multiple" | "ordering")[];
  include_lesson_pdf: boolean;
  reference_text?: string | null;
}

export interface Job {
  id: number;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: Record<string, unknown> | null;
}

// --- reports --------------------------------------------------------------------------------

export type Readiness = "ready" | "at_risk" | "not_ready";

export interface ReportFilters {
  wave_id?: number;
  region_id?: number;
  branch_id?: number;
  module_id?: number;
  job_role_id?: number;
}

export interface Summary {
  total: number;
  branches: number;
  certified: number;
  certified_pct: number;
  recert_required: number;
  in_progress: number;
  not_started: number;
  overdue: number;
  latest_release: string | null;
}

export interface WaveRef {
  id: number;
  name_uz: string;
  name_ru: string;
  deadline: string;
  go_live: string;
}

export interface BranchReportRow {
  branch: Ref;
  region: Ref;
  wave: WaveRef;
  total: number;
  certified: number;
  certified_pct: number;
  recert_required: number;
  in_progress: number;
  not_started: number;
  overdue: number;
  readiness: Readiness;
}

export interface LearnerReportRow {
  user_id: number;
  employee_id: string;
  full_name: string;
  branch: Ref;
  region: Ref;
  job_role: Ref;
  wave: WaveRef;
  status: ModuleState;
  overdue: boolean;
  modules_certified: number;
  modules_total: number;
  last_seen_at: string | null;
}

export interface ModuleProgress {
  module_id: number;
  code: string;
  type: ModuleType;
  title_uz: string;
  title_ru: string;
  state: ModuleState;
  locked: boolean;
  lessons_completed: number;
  lessons_total: number;
  attempts_used: number;
  attempts_max: number;
  last_attempt_status: AttemptStatus | null;
  last_score_pct: number | null;
  last_attempt_at: string | null;
  certificate: {
    number: string;
    status: CertStatus;
    release: string | null;
    score_pct: number | null;
    issued_at: string;
    recert_due_at: string | null;
  } | null;
}

export interface LearnerDetail {
  user_id: number;
  employee_id: string;
  full_name: string;
  branch: Ref | null;
  job_role: Ref | null;
  wave: WaveRef | null;
  status: ModuleState;
  overdue: boolean;
  operator: { status: CertStatus; number: string | null; issued_at: string | null };
  modules: ModuleProgress[];
}
