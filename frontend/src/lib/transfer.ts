import { ApiError } from "../api/client";

/**
 * Large uploads (lesson videos, up to 2 GB) go through XMLHttpRequest: unlike fetch,
 * it reports upload progress. Same headers and error shape as api().
 */
export function uploadWithProgress<T>(
  url: string,
  file: Blob,
  onProgress: (pct: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("X-Requested-With", "fetch");
    xhr.setRequestHeader("Content-Type", file.type || "video/mp4");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      let data: { error?: { code: string; params?: Record<string, unknown> } } | null = null;
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : null;
      } catch {
        data = null; // e.g. an HTML error page from nginx
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T);
      else reject(new ApiError(xhr.status, data?.error?.code ?? `http.${xhr.status}`, data?.error?.params ?? {}));
    };
    xhr.onerror = () => reject(new ApiError(0, "network"));
    xhr.onabort = () => reject(new ApiError(0, "aborted"));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(file);
  });
}

/** Offer text (e.g. the one-time password CSV) as a file to save; nothing is stored. */
export function saveText(filename: string, text: string, type = "text/csv;charset=utf-8"): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
