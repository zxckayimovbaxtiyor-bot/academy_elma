/**
 * Thin fetch wrapper. The API answers errors as {"error": {"code", "params"}} and never
 * sends user-facing text: the code is translated in the browser (errors.* in i18n).
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public params: Record<string, unknown> = {},
  ) {
    super(code);
  }
}

export const API = "/api/v1";
export const AUTH_LOST = "academy:auth-lost";

type Options = Omit<RequestInit, "body"> & { json?: unknown; body?: BodyInit };

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const { json, headers: extra, ...rest } = options;
  const headers = new Headers(extra);
  headers.set("X-Requested-With", "fetch"); // CSRF guard on every write
  let body = options.body;
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }
  let res: Response;
  try {
    res = await fetch(API + path, { ...rest, body, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "network");
  }
  if (res.status === 204) return undefined as T;
  const isJson = (res.headers.get("content-type") ?? "").includes("application/json");
  const data = isJson ? await res.json().catch(() => null) : null;
  if (!res.ok) {
    const err = data?.error ?? { code: `http.${res.status}`, params: {} };
    if (res.status === 401 && err.code === "auth.required") {
      window.dispatchEvent(new CustomEvent(AUTH_LOST));
    }
    throw new ApiError(res.status, err.code, err.params ?? {});
  }
  return data as T;
}

export const get = <T>(path: string) => api<T>(path);
export const post = <T>(path: string, json?: unknown) => api<T>(path, { method: "POST", json });
export const put = <T>(path: string, json?: unknown) => api<T>(path, { method: "PUT", json });
export const patch = <T>(path: string, json?: unknown) => api<T>(path, { method: "PATCH", json });
