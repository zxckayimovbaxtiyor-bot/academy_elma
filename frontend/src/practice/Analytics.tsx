import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { practice } from "../api/practice";
import { ErrorState, PageLoader } from "../components/Feedback";
import { useApi } from "../lib/useApi";
import { SessionReport } from "./SessionReport";
import { useLang } from "../lib/lang";
import "../styles/practice.css";

export function PracticeAnalytics({
  filters = {},
}: {
  filters?: Record<string, string | number | undefined>;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const [page, setPage] = useState(1);
  const [reportId, setReportId] = useState<number | null>(null);
  useEffect(() => setPage(1), [JSON.stringify(filters)]);
  const [expanded, setExpanded] = useState(false);
  const [mode, setMode] = useState("exam");
  const loaded = useApi(
    () =>
      practice.analytics({
        ...filters,
        mode: mode === "all" ? undefined : mode,
        page,
      }),
    [JSON.stringify(filters), mode, page],
  );
  if (loaded.loading) return <PageLoader />;
  if (loaded.error || !loaded.data)
    return <ErrorState error={loaded.error} onRetry={loaded.reload} />;
  const d = loaded.data;
  return (
    <section className="card card-pad stack">
      <div className="spread practice-wrap">
        <h2>{t("practice.analytics")}</h2>
        <button
          className="btn"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {t("practice.details")}
        </button>
      </div>
      <label>
        {t("practice.mode_label")}
        <select
          className="input"
          value={mode}
          onChange={(e) => {
            setMode(e.target.value);
            setPage(1);
          }}
        >
          <option value="all">{t("reports.all")}</option>
          {["guided", "exam"].map((m) => (
            <option value={m} key={m}>
              {t(`practice.mode.${m}`)}
            </option>
          ))}
        </select>
      </label>
      <div className="practice-kpis">
        {(
          [
            "started",
            "completed",
            "pass_rate",
            "average_seconds",
            "retries",
          ] as const
        ).map((k) => (
          <div key={k}>
            <span className="small muted">{t(`practice.metric.${k}`)}</span>
            <strong>
              {d[k]}
              {k === "pass_rate" ? "%" : ""}
            </strong>
          </div>
        ))}
      </div>
      {reportId !== null && (
        <SessionReport id={reportId} close={() => setReportId(null)} />
      )}
      {expanded && (
        <>
          <div className="practice-editor-grid">
            <div>
              <h3>{t("practice.frequent_errors")}</h3>
              <ul>
                {Object.entries(d.errors).map(([k, n]) => (
                  <li key={k}>
                    {d.error_labels[k]?.[lang] ?? k}: {n}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3>{t("practice.problem_stages")}</h3>
              <ul>
                {Object.entries(d.stages).map(([k, n]) => (
                  <li key={k}>
                    {d.stage_labels[k]?.[lang] ?? k}: {n}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          {(["branches", "roles"] as const).map((group) => (
            <div key={group}>
              <h3>{t(`practice.group.${group}`)}</h3>
              <div className="practice-table">
                <table>
                  <thead>
                    <tr>
                      <th>{t("practice.identifier")}</th>
                      <th>{t("practice.metric.started")}</th>
                      <th>{t("practice.metric.completed")}</th>
                      <th>{t("practice.metric.pass_rate")}</th>
                      <th>{t("practice.metric.average_seconds")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d[group].map((r) => (
                      <tr key={String(r.id)}>
                        <td>{r.title?.[lang] ?? r.id ?? "—"}</td>
                        <td>{r.started}</td>
                        <td>{r.completed}</td>
                        <td>{r.pass_rate}%</td>
                        <td>{r.average_seconds}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
          <div className="practice-table">
            <table>
              <thead>
                <tr>
                  {[
                    "employee",
                    "mode_label",
                    "status",
                    "score",
                    "duration_label",
                  ].map((k) => (
                    <th key={k}>{t(`practice.${k}`)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.sessions.map((s) => (
                  <tr key={s.id}>
                    <td>
                      {s.full_name}
                      <br />
                      <small>{s.employee_id}</small>
                      <br />
                      <button
                        className="back-link"
                        onClick={() => setReportId(s.id)}
                      >
                        {t("practice.details")}
                      </button>
                    </td>
                    <td>{t(`practice.mode.${s.mode}`)}</td>
                    <td>
                      {t(
                        s.status === "active"
                          ? "practice.in_progress"
                          : "practice.completed",
                      )}
                    </td>
                    <td>{s.score_pct === null ? "—" : `${s.score_pct}%`}</td>
                    <td>{s.duration_s ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row practice-wrap">
            <button
              className="btn"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              {t("practice.previous_page")}
            </button>
            <span>
              {t("practice.page_number", {
                page: d.page,
                total: Math.max(1, Math.ceil(d.total / d.page_size)),
              })}
            </span>
            <button
              className="btn"
              disabled={page * d.page_size >= d.total}
              onClick={() => setPage(page + 1)}
            >
              {t("practice.next_page")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
