import { useEffect, useRef } from "react";
import "../styles/studio.css";
import { useTranslation } from "react-i18next";
import { practice } from "../api/practice";
import { useApi } from "../lib/useApi";
import { useLang } from "../lib/lang";
import { clock, dateTime } from "../lib/format";
import { ErrorState, PageLoader } from "../components/Feedback";
export function SessionReport({
  id,
  close,
}: {
  id: number;
  close: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  const { t } = useTranslation();
  const lang = useLang();
  const loaded = useApi(() => practice.sessionReport(id), [id]);
  return (
    <dialog
      ref={dialog}
      onCancel={close}
      className="studio-report"
      role="dialog"
      aria-modal="true"
      aria-label={t("practice.details")}
    >
      <div className="studio-report-card stack">
        <div className="spread">
          <h2>
            {t("practice.details")} #{id}
          </h2>
          <button className="btn" onClick={close}>
            {t("practice.close")}
          </button>
        </div>
        {loaded.loading ? (
          <PageLoader />
        ) : loaded.error || !loaded.data ? (
          <ErrorState error={loaded.error} onRetry={loaded.reload} />
        ) : (
          <>
            <div className="studio-two">
              <div>
                {t("practice.version", { number: loaded.data.version })}
                <br />
                {t("practice.tasks")}:{" "}
                {loaded.data.task?.[lang] ?? loaded.data.task_id ?? "—"}
              </div>
              <div>
                {dateTime(loaded.data.started_at)} →{" "}
                {loaded.data.finished_at
                  ? dateTime(loaded.data.finished_at)
                  : "—"}
              </div>
            </div>
            <p>
              {t("studio.hints_count", {
                count: loaded.data.hints_used.length,
              })}{" "}
              ·{" "}
              {loaded.data.result
                ? `${loaded.data.result.score_pct}% · ${clock(loaded.data.result.duration_s)}`
                : t("practice.in_progress")}
            </p>
            <ol className="studio-event-log">
              {loaded.data.actions.map((a) => (
                <li key={a.id}>
                  <div className="spread">
                    <strong>
                      {t(`practice.command.${a.kind}`, {
                        defaultValue: t("practice.command.action"),
                      })} ·{" "}
                      {a.screen_title?.[lang] ?? a.screen}
                      {a.action_label ? ` · ${a.action_label[lang]}` : ""}
                    </strong>
                    <small>{dateTime(a.at)}</small>
                  </div>
                  {a.values.length > 0 && (
                    <dl className="practice-summary">
                      {a.values.map(({ field: k, label, value: v }) => (
                        <div key={k}>
                          <dt>{label[lang]}</dt>
                          <dd>
                            {typeof v === "number"
                              ? v.toLocaleString("ru-RU")
                              : typeof v === "boolean"
                                ? t(v ? "practice.yes" : "practice.no")
                                : typeof v === "object" && v !== null
                                  ? v[lang]
                                  : (v ?? "—")}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                  {a.errors.map((e, i) => (
                    <p className="error-line" key={i}>
                      {e.message?.[lang] ?? t("practice.check_data")}
                    </p>
                  ))}
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </dialog>
  );
}
