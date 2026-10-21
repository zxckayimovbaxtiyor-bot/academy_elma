import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export function Confirm({
  title,
  children,
  confirmLabel,
  busy,
  onConfirm,
  onCancel,
}: {
  title: string;
  children?: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="backdrop" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="dialog stack">
        <h3 id="confirm-title">{title}</h3>
        {children}
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button className="btn" onClick={onCancel} disabled={busy}>
            {t("app.cancel")}
          </button>
          <button className="btn btn-primary" onClick={onConfirm} disabled={busy}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
