import { useTranslation } from "react-i18next";

import type { CertStatus, ModuleState } from "../api/types";
import { date } from "../lib/format";

const MODULE_TONE: Record<ModuleState | "locked", string> = {
  certified: "chip-success",
  in_progress: "chip-primary",
  not_started: "",
  recert_required: "chip-warning",
  locked: "",
};

export function ModuleBadge({ state, locked }: { state: ModuleState; locked?: boolean }) {
  const { t } = useTranslation();
  const key = locked ? "locked" : state;
  return <span className={`chip ${MODULE_TONE[key]}`}>{t(`state.${key}`)}</span>;
}

const CERT_TONE: Record<CertStatus, string> = {
  valid: "chip-success",
  recert_required: "chip-warning",
  superseded: "",
  missing: "",
};

/** A valid certificate with a due date is in a release's transition period: renew by then. */
export function CertBadge({ status, due }: { status: CertStatus; due?: string | null }) {
  const { t } = useTranslation();
  if (status === "valid" && due) {
    return <span className="chip chip-warning">{t("cert_status.renew_by", { date: date(due) })}</span>;
  }
  return <span className={`chip ${CERT_TONE[status]}`}>{t(`cert_status.${status}`)}</span>;
}

export function ProgressBar({ value, tone, label }: { value: number; tone?: "success"; label?: string }) {
  const width = Math.max(0, Math.min(100, value));
  return (
    <div
      className={`progress ${tone ?? ""}`}
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(width)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${width}%` }} />
    </div>
  );
}
