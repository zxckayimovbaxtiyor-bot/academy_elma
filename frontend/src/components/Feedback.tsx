import { createContext, useContext } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "../api/client";
import { dateTime } from "../lib/format";

export function PageLoader() {
  const { t } = useTranslation();
  return (
    <div className="center-box" role="status">
      <div className="spinner" />
      <span className="muted">{t("app.loading")}</span>
    </div>
  );
}

/** Timestamps inside error parameters (e.g. auth.locked {until}) are shown in local time. */
function readable(params: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...params };
  for (const [key, value] of Object.entries(out)) {
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) out[key] = dateTime(value);
  }
  return out;
}

/** Staff screens can word an API error differently from the learner screens: a key under this
 *  prefix (e.g. "admin.errors") wins over the shared errors.* key for the same code. */
export const ErrorWording = createContext<string | null>(null);

/** An API error code, translated (errors.* keys), with its parameters. */
export function useErrorText() {
  const { t } = useTranslation();
  const prefix = useContext(ErrorWording);
  return (error: unknown): string => {
    if (!(error instanceof ApiError)) return t("errors.generic");
    const keys = [...(prefix ? [`${prefix}.${error.code}`] : []), `errors.${error.code}`];
    for (const key of keys) {
      const text = t(key, { ...readable(error.params), defaultValue: "" });
      if (typeof text === "string" && text) return text;
    }
    return t("errors.generic");
  };
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  const text = useErrorText();
  return (
    <div className="center-box" role="alert">
      <p className="strong">{text(error)}</p>
      {onRetry && (
        <button className="btn" onClick={onRetry}>
          {t("app.retry")}
        </button>
      )}
    </div>
  );
}

export function ErrorLine({ error }: { error: unknown }) {
  const text = useErrorText();
  if (!error) return null;
  return (
    <div className="notice notice-danger" role="alert">
      {text(error)}
    </div>
  );
}
