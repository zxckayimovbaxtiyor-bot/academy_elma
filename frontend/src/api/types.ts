/** Shapes of the learner API (backend/app/schemas). Bilingual fields come as *_uz / *_ru. */

export type Lang = "uz" | "ru";
export type AccessRole = "learner" | "branch_head" | "methodologist" | "admin";
export type ModuleType = "core" | "product" | "faq";
export type ModuleState = "certified" | "recert_required" | "in_progress" | "not_started";
export type CertStatus = "valid" | "recert_required" | "superseded" | "missing";
export type QuestionType = "single" | "multiple" | "ordering" | "screenshot";
export type AttemptStatus = "in_progress" | "submitted" | "expired";

export interface Ref {
  id: number;
  code: string;
  name_uz: string;
  name_ru: string;
}

export interface Me {
  id: number;
  employee_id: string;
  full_name: string;
  access_role: AccessRole;
  preferred_language: Lang;
  must_change_password: boolean;
  branch: Ref | null;
  region: Ref | null;
  job_role: Ref | null;
}

export interface LearnerModule {
  id: number;
  code: string;
  type: ModuleType;
  title_uz: string;
  title_ru: string;
  sort: number;
  locked: boolean;
  release_code: string | null;
  lessons_total: number;
  lessons_completed: number;
  duration_s: number;
  status: ModuleState;
  score_pct: number | null;
  recert_due_at: string | null;
}

export interface LearnerLesson {
  id: number;
  sort: number;
  title_uz: string;
  title_ru: string;
  duration_s: number;
  completed: boolean;
  watched_pct: number;
}

export interface Reason {
  code: string;
  params: Record<string, unknown>;
}

export interface TestStatus {
  can_start: boolean;
  reasons: Reason[];
  attempts_used: number;
  attempts_max: number;
  cooldown_until: string | null;
  open_attempt_id: number | null;
  last_attempt_id: number | null;
  last_score_pct: number | null;
  last_passed: boolean | null;
}

export interface TestInfo {
  question_count: number;
  pass_pct: number;
  time_limit_min: number;
  max_attempts: number;
  published: boolean;
  lessons_complete: boolean;
  status: TestStatus;
}

export interface LearnerModuleDetail extends LearnerModule {
  lessons: LearnerLesson[];
  test: TestInfo | null;
}

export interface Progress {
  watched_s: number;
  watched_pct: number;
  max_position_s: number;
  last_position_s: number;
  completed: boolean;
}

export interface Fragment {
  span_start_s: number;
  span_end_s: number;
  watched_pct: number;
  satisfied: boolean;
}

export interface Player {
  lesson_id: number;
  module_id: number;
  module_type: ModuleType;
  title_uz: string;
  title_ru: string;
  version_id: number;
  release_code: string;
  duration_s: number;
  hls_url: string;
  subtitles: Partial<Record<Lang, string | null>>;
  pdf: Record<Lang, string> | null;
  tracking: boolean;
  progress: Progress | null;
  seek_limit_s: number | null;
  speed_change_allowed: boolean;
  prev_lesson_id: number | null;
  next_lesson_id: number | null;
  remediation: Fragment[];
}

export interface Heartbeat extends Progress {
  duration_s: number;
}

export interface AttemptOption {
  index: number;
  text_uz: string;
  text_ru: string;
}

export interface AttemptQuestion {
  position: number;
  type: QuestionType;
  text_uz: string;
  text_ru: string;
  image_url: string | null;
  options: AttemptOption[];
  answer: number[] | null;
  flagged: boolean;
}

export interface Attempt {
  id: number;
  module_id: number;
  module_title_uz: string;
  module_title_ru: string;
  status: AttemptStatus;
  number: number;
  max_attempts: number;
  question_count: number;
  pass_pct: number;
  started_at: string;
  expires_at: string;
  server_now: string;
  answered: number;
  questions: AttemptQuestion[];
}

export interface AnswerSaved {
  position: number;
  answered: boolean;
  flagged: boolean;
}

export interface RemediationItem {
  lesson_id: number;
  lesson_title_uz: string;
  lesson_title_ru: string;
  missed_count: number;
  span_start_s: number;
  span_end_s: number;
  watched_pct: number;
  satisfied: boolean;
}

export interface HistoryRow {
  attempt_id: number;
  number: number;
  status: AttemptStatus;
  started_at: string;
  score_pct: number | null;
  passed: boolean | null;
  time_spent_s: number | null;
}

export interface Result {
  attempt_id: number;
  module_id: number;
  status: AttemptStatus;
  number: number;
  score_pct: number;
  correct_count: number;
  question_count: number;
  pass_pct: number;
  passed: boolean;
  time_spent_s: number | null;
  attempts_used: number;
  attempts_max: number;
  attempts_left: number;
  next_attempt_at: string | null;
  remediation: RemediationItem[];
  remediation_complete: boolean;
  history: HistoryRow[];
}

export interface DashboardWave {
  id: number;
  name_uz: string;
  name_ru: string;
  training_start: string;
  deadline: string;
  go_live: string;
  days_left: number;
}

export interface Resume {
  lesson_id: number;
  module_id: number;
  module_title_uz: string;
  module_title_ru: string;
  lesson_number: number;
  title_uz: string;
  title_ru: string;
  duration_s: number;
  watched_pct: number;
}

export interface DashboardCert {
  number: string;
  kind: "module" | "operator";
  module_id: number | null;
  title_uz: string | null;
  title_ru: string | null;
  status: CertStatus;
  recert_due_at: string | null;
}

export interface Dashboard {
  full_name: string;
  branch: Ref | null;
  job_role: Ref | null;
  wave: DashboardWave | null;
  modules_certified: number;
  modules_assigned: number;
  overdue: boolean;
  path: LearnerModule[];
  resume: Resume | null;
  operator_status: CertStatus;
  certificates: DashboardCert[];
}

export interface CertModule {
  code: string;
  title_uz: string;
  title_ru: string;
  release: string | null;
}

export interface Certificate {
  number: string;
  kind: "module" | "operator";
  status: CertStatus;
  module_id: number | null;
  modules: CertModule[];
  score_pct: number | null;
  issued_at: string;
  recert_due_at: string | null;
  superseded_at: string | null;
  pdf_url: string;
  verify_url: string;
}

export interface Place {
  code: string;
  name_uz: string;
  name_ru: string;
}

export interface Verification {
  number: string;
  kind: "module" | "operator";
  status: CertStatus;
  holder: string;
  branch: Place | null;
  region: Place | null;
  modules: CertModule[];
  issued_at: string;
  recert_due_at: string | null;
  superseded_at: string | null;
}
