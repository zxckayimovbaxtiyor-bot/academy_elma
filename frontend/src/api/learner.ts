import { api, get, patch, post, put } from "./client";
import type {
  AnswerSaved,
  Attempt,
  Certificate,
  Dashboard,
  Heartbeat,
  Lang,
  LearnerLesson,
  LearnerModule,
  LearnerModuleDetail,
  Me,
  Player,
  Result,
  Verification,
} from "./types";

export const auth = {
  me: () => get<Me>("/auth/me"),
  login: (username: string, password: string) => post<Me>("/auth/login", { username, password }),
  logout: () => post<void>("/auth/logout"),
  changePassword: (current_password: string, new_password: string) =>
    post<void>("/auth/change-password", { current_password, new_password }),
  setLanguage: (preferred_language: Lang) => patch<Me>("/auth/me", { preferred_language }),
};

export const learner = {
  dashboard: () => get<Dashboard>("/me/dashboard"),
  modules: () => get<LearnerModule[]>("/me/modules"),
  module: (id: number) => get<LearnerModuleDetail>(`/me/modules/${id}`),
  lesson: (id: number) => get<Player>(`/me/lessons/${id}`),
  faq: () => get<LearnerLesson[]>("/me/faq"),
  faqLesson: (id: number) => get<Player>(`/me/faq/${id}`),
  heartbeat: (
    lessonId: number,
    body: { version_id: number; ranges: [number, number][]; position_s: number },
    keepalive = false,
  ) =>
    api<Heartbeat>(`/me/lessons/${lessonId}/heartbeat`, {
      method: "POST",
      json: body,
      keepalive, // still delivered when the tab is closing
    }),
  startAttempt: (moduleId: number) =>
    post<{ attempt_id: number; created: boolean }>(`/me/modules/${moduleId}/attempts`),
  attempt: (id: number) => get<Attempt>(`/me/attempts/${id}`),
  saveAnswer: (id: number, position: number, body: { answer?: number[] | null; flagged?: boolean }) =>
    put<AnswerSaved>(`/me/attempts/${id}/answers/${position}`, body),
  submit: (id: number) => post<Result>(`/me/attempts/${id}/submit`),
  result: (id: number) => get<Result>(`/me/attempts/${id}/result`),
  certificates: () => get<Certificate[]>("/me/certificates"),
};

export const verify = (number: string, code: string) =>
  get<Verification>(`/verify/${encodeURIComponent(number)}?c=${encodeURIComponent(code)}`);
