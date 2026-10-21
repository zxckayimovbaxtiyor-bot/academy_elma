import { API, api, get, patch, post, put } from "./client";
import type {
  AiStatus,
  Assignment,
  BranchReportRow,
  BranchRef,
  Cue,
  DraftRequest,
  ImportCommit,
  ImportReport,
  Job,
  JobRoleRef,
  LearnerDetail,
  LearnerReportRow,
  LessonAdmin,
  ModuleAdmin,
  ModuleInput,
  ModulePatch,
  Page,
  Pool,
  QuestionAdmin,
  QuestionInput,
  ReleaseDetail,
  ReleaseRow,
  ReportFilters,
  Summary,
  UserDetail,
  UserRow,
  Version,
  Video,
  WaveDetail,
  WaveInput,
  WaveRow,
} from "./adminTypes";
import type { AccessRole, Lang, ModuleState, Ref } from "./types";

type Params = Record<string, string | number | boolean | null | undefined>;

/** ?a=1&b=2 without the empty ones. */
export function query(params: Params): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") qs.set(key, String(value));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

/** A raw-body upload (CSV, WebVTT, PDF, image): no multipart, as the API expects. */
const upload = <T>(method: "POST" | "PUT", path: string, file: Blob, type: string) =>
  api<T>(path, { method, body: file, headers: { "Content-Type": type } });

/** Address of a CSV export; the browser downloads it with the session cookie. */
export const csvUrl = (path: string, params: Params = {}) => `${API}${path}${query({ ...params, format: "csv" })}`;

export const reference = {
  regions: () => get<Ref[]>("/admin/regions"),
  branches: () => get<BranchRef[]>("/admin/branches"),
  jobRoles: () => get<JobRoleRef[]>("/admin/job-roles"),
};

export const users = {
  list: (p: { q?: string; branch_id?: number; access_role?: AccessRole; is_active?: boolean; page?: number; page_size?: number }) =>
    get<Page<UserRow>>(`/admin/users${query(p)}`),
  get: (id: number) => get<UserDetail>(`/admin/users/${id}`),
  patch: (id: number, body: { access_role?: AccessRole; is_active?: boolean }) => patch<UserRow>(`/admin/users/${id}`, body),
  resetPassword: (id: number) => post<{ temp_password: string }>(`/admin/users/${id}/reset-password`),
  resetAttempts: (id: number, module_id: number, reason: string) =>
    post<{ id: number }>(`/admin/users/${id}/reset-attempts`, { module_id, reason }),
  importValidate: (file: File) =>
    upload<ImportReport>("POST", `/admin/users/import${query({ filename: file.name })}`, file, "text/csv"),
  importCommit: (importId: number) => post<ImportCommit>(`/admin/users/import/${importId}/commit`),
  templateUrl: `${API}/admin/users/import/template.csv`,
  errorsUrl: (importId: number, lang: Lang) => `${API}/admin/users/import/${importId}/errors.csv${query({ lang })}`,
};

export const waves = {
  list: () => get<WaveRow[]>("/admin/waves"),
  get: (id: number) => get<WaveDetail>(`/admin/waves/${id}`),
  create: (body: WaveInput) => post<WaveRow>("/admin/waves", body),
  patch: (id: number, body: Partial<WaveInput>) => patch<WaveRow>(`/admin/waves/${id}`, body),
  setBranches: (id: number, branch_ids: number[]) => put<WaveRow>(`/admin/waves/${id}/branches`, { branch_ids }),
  setAssignments: (id: number, items: Assignment[]) => put<WaveDetail>(`/admin/waves/${id}/assignments`, { items }),
};

export const content = {
  modules: () => get<ModuleAdmin[]>("/admin/modules"),
  createModule: (body: ModuleInput) => post<ModuleAdmin>("/admin/modules", body),
  patchModule: (id: number, body: ModulePatch) => patch<ModuleAdmin>(`/admin/modules/${id}`, body),
  reorderModules: (ids: number[]) => post<void>("/admin/modules/reorder", { ids }),
  lessons: (moduleId: number) => get<LessonAdmin[]>(`/admin/modules/${moduleId}/lessons`),
  createLesson: (moduleId: number, title_uz: string, title_ru: string) =>
    post<LessonAdmin>(`/admin/modules/${moduleId}/lessons`, { title_uz, title_ru }),
  reorderLessons: (moduleId: number, ids: number[]) => post<void>(`/admin/modules/${moduleId}/lessons/reorder`, { ids }),
  lesson: (id: number) => get<LessonAdmin>(`/admin/lessons/${id}`),
  patchLesson: (id: number, body: { title_uz?: string; title_ru?: string }) => patch<LessonAdmin>(`/admin/lessons/${id}`, body),
  deleteLesson: (id: number) => api<void>(`/admin/lessons/${id}`, { method: "DELETE" }),
  videoUrl: (versionId: number, filename: string) =>
    `${API}/admin/lesson-versions/${versionId}/video${query({ synthetic_data_confirmed: true, filename })}`,
  video: (assetId: string) => get<Video>(`/admin/video-assets/${assetId}`),
  subtitles: (versionId: number, lang: Lang, file: File) =>
    upload<Version>("PUT", `/admin/lesson-versions/${versionId}/subtitles/${lang}`, file, "text/vtt"),
  pdf: (versionId: number, lang: Lang, file: File) =>
    upload<Version>("PUT", `/admin/lesson-versions/${versionId}/pdf/${lang}`, file, "application/pdf"),
  deletePdf: (versionId: number, lang: Lang) => api<Version>(`/admin/lesson-versions/${versionId}/pdf/${lang}`, { method: "DELETE" }),
  transcript: (versionId: number, lang: Lang) => get<Cue[]>(`/admin/lesson-versions/${versionId}/transcript${query({ lang })}`),
};

export const releases = {
  list: () => get<ReleaseRow[]>("/admin/releases"),
  get: (id: number) => get<ReleaseDetail>(`/admin/releases/${id}`),
  create: (code: string, notes: string) => post<ReleaseRow>("/admin/releases", { code, notes }),
  patch: (id: number, body: { code?: string; notes?: string; transition_days?: number }) =>
    patch<ReleaseRow>(`/admin/releases/${id}`, body),
  remove: (id: number) => api<void>(`/admin/releases/${id}`, { method: "DELETE" }),
  markChanged: (id: number, lessonId: number) => post<LessonAdmin>(`/admin/releases/${id}/lessons/${lessonId}`),
  unmark: (id: number, lessonId: number) => api<void>(`/admin/releases/${id}/lessons/${lessonId}`, { method: "DELETE" }),
  publish: (id: number) => post<ReleaseRow>(`/admin/releases/${id}/publish`),
};

export const questions = {
  list: (moduleId: number, p: { status?: string; lesson_id?: number; origin?: string; flagged?: boolean } = {}) =>
    get<QuestionAdmin[]>(`/admin/modules/${moduleId}/questions${query(p)}`),
  pool: (moduleId: number) => get<Pool>(`/admin/modules/${moduleId}/pool`),
  create: (moduleId: number, body: QuestionInput) => post<QuestionAdmin>(`/admin/modules/${moduleId}/questions`, body),
  get: (id: number) => get<QuestionAdmin>(`/admin/questions/${id}`),
  patch: (id: number, body: Partial<QuestionInput>) => patch<QuestionAdmin>(`/admin/questions/${id}`, body),
  image: (id: number, file: File) => upload<QuestionAdmin>("PUT", `/admin/questions/${id}/image`, file, file.type || "image/png"),
  approve: (id: number) => post<QuestionAdmin>(`/admin/questions/${id}/approve`),
  reject: (id: number) => post<QuestionAdmin>(`/admin/questions/${id}/reject`),
  retire: (id: number) => post<QuestionAdmin>(`/admin/questions/${id}/retire`),
  duplicate: (id: number) => post<QuestionAdmin>(`/admin/questions/${id}/duplicate`),
  publishTest: (moduleId: number) => post<Pool>(`/admin/modules/${moduleId}/test/publish`),
  unpublishTest: (moduleId: number) => post<Pool>(`/admin/modules/${moduleId}/test/unpublish`),
};

export const ai = {
  status: () => get<AiStatus>("/admin/ai/status"),
  draft: (versionId: number, body: DraftRequest) => post<Job>(`/admin/lesson-versions/${versionId}/ai-drafts`, body),
  job: (id: number) => get<Job>(`/admin/jobs/${id}`),
};

type UserFilters = ReportFilters & { status?: ModuleState; overdue?: boolean; q?: string; page?: number; page_size?: number };

export const reports = {
  summary: (f: ReportFilters) => get<Summary>(`/reports/summary${query({ ...f })}`),
  branches: (f: ReportFilters) => get<BranchReportRow[]>(`/reports/branches${query({ ...f })}`),
  users: (f: UserFilters) => get<Page<LearnerReportRow>>(`/reports/users${query({ ...f })}`),
  user: (id: number) => get<LearnerDetail>(`/reports/users/${id}`),
  accessListUrl: (p: { wave_id?: number; branch_id?: number; lang: Lang }) => `${API}/exports/access-list.csv${query(p)}`,
};
