import { useTranslation } from "react-i18next";
import { Link, Navigate, useParams } from "react-router-dom";

import { learner } from "../../api/learner";
import type { HistoryRow, LearnerModuleDetail, RemediationItem, Result } from "../../api/types";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { Donut } from "../../components/Donut";
import { ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { clock, countdown, dateTime, pct } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { useApi, useRemaining } from "../../lib/useApi";

/** Result (mockup 4): score, attempts left, retake countdown, fragments to re-watch, history. */
export function TestResult() {
  const { t } = useTranslation();
  const lang = useLang();
  const id = Number(useParams().attemptId);
  const res = useApi(() => learner.result(id), [id]);
  const r = res.data;
  const mod = useApi<LearnerModuleDetail | null>(
    () => (r ? learner.module(r.module_id) : Promise.resolve(null)),
    [r?.module_id],
  );
  const wait = useRemaining(r?.next_attempt_at ?? null);

  if (res.error?.code === "attempt.in_progress") return <Navigate to={`/attempts/${id}`} replace />;
  if (res.loading && !r) return <PageLoader />;
  if (res.error || !r) return <ErrorState error={res.error} onRetry={res.reload} />;

  const module = mod.data ?? null;
  const moduleTitle = module ? pick(module, "title", lang) : "";
  // Attempts left, cooldown and retake describe the module now: they belong only on the
  // result of its latest attempt, not on an older one (or one before a pass).
  const current = module?.test?.status.last_attempt_id === r.attempt_id;
  const open = current && !r.passed;
  const cooling = wait !== null && wait > 0;
  const canRetake = open && r.attempts_left > 0 && r.remediation_complete && !cooling;
  const done = r.remediation.filter((i) => i.satisfied).length;

  let heading: string;
  let text: string;
  if (r.passed) {
    heading = t("result.passed_title");
    text = t("result.passed_text");
  } else if (r.remediation.length > 0) {
    heading = t("result.failed_title", { count: r.remediation.length });
    text = t("result.failed_text");
  } else {
    heading = t("result.failed_title_plain");
    text = t("result.failed_text_plain");
  }

  return (
    <div className="stack-lg narrow-wide">
      <Breadcrumbs
        items={[
          { label: t("nav.courses"), to: "/courses" },
          { label: moduleTitle || "…", to: `/courses/${r.module_id}` },
          { label: t("result.crumb", { n: r.number }) },
        ]}
      />
      <section className="card card-pad-lg result-head">
        <Donut
          value={r.score_pct}
          tone={r.passed ? "success" : "danger"}
          label={pct(r.score_pct)}
          sub={`${r.correct_count} / ${r.question_count}`}
        />
        <div className="grow stack">
          <div className="row wrap">
            <span className={`chip ${r.passed ? "chip-success" : "chip-danger"}`}>
              {t(r.passed ? "result.passed_chip" : "result.failed_chip", { pass: r.pass_pct })}
            </span>
            {r.status === "expired" && <span className="chip chip-warning">{t("result.expired")}</span>}
          </div>
          <h1>{heading}</h1>
          <p className="muted result-text">{text}</p>
          {r.passed && (
            <div className="row wrap">
              <Link className="btn btn-primary" to="/certificates">
                <Icon name="certificate" size={18} />
                {t("result.to_certificates")}
              </Link>
              <Link className="btn" to="/courses">
                {t("result.to_courses")}
              </Link>
            </div>
          )}
        </div>
        <div className="result-stats">
          {!open ? (
            <div className="stat">
              <span>{t("result.time_spent")}</span>
              <strong className="num">{r.time_spent_s !== null ? clock(r.time_spent_s) : "—"}</strong>
            </div>
          ) : (
            <div className="stat">
              <span>{t("result.attempts_left")}</span>
              <strong className="num">
                {r.attempts_left} / {r.attempts_max}
              </strong>
            </div>
          )}
          {open && cooling && r.attempts_left > 0 && (
            <div className="stat">
              <span>{t("result.retake_in")}</span>
              <strong className="num">{countdown(wait)}</strong>
              {t("result.retake_in_after") && <span>{t("result.retake_in_after")}</span>}
            </div>
          )}
        </div>
      </section>

      {open && r.attempts_left === 0 && (
        <div className="notice notice-warning">
          <Icon name="alert" />
          <span>{t("result.exhausted")}</span>
        </div>
      )}

      {open && r.attempts_left > 0 && (
        <section className="card card-pad-lg stack">
          {r.remediation.length > 0 && (
            <>
              <div className="spread">
                <h2>{t("result.rewatch_title")}</h2>
                <span className="muted">{t("result.rewatch_done", { done, total: r.remediation.length })}</span>
              </div>
              <ol className="remed">
                {r.remediation.map((item, i) => (
                  <RemediationRow
                    key={`${item.lesson_id}-${item.span_start_s}`}
                    item={item}
                    n={i + 1}
                    module={module}
                    result={r}
                    primary={!item.satisfied && r.remediation.findIndex((x) => !x.satisfied) === i}
                  />
                ))}
              </ol>
              <hr className="divider" />
            </>
          )}
          <div className="spread retake-row">
            <p className="muted">{t(r.remediation.length > 0 ? "result.retake_rule" : "result.retake_rule_wait")}</p>
            {canRetake ? (
              <Link className="btn btn-primary btn-lg" to={`/courses/${r.module_id}/test`}>
                {t("result.retake")}
              </Link>
            ) : (
              <button className="btn btn-lg" disabled>
                {t("result.retake")}
              </button>
            )}
          </div>
        </section>
      )}

      {!r.passed && !open && module && r.remediation.length > 0 && (
        <section className="card card-pad-lg stack">
          <h2>{t("result.rewatch_title")}</h2>
          <ol className="remed">
            {r.remediation.map((item, i) => (
              <RemediationRow key={`${item.lesson_id}-${item.span_start_s}`} item={item} n={i + 1} module={module}
                result={r} primary={false} readOnly />
            ))}
          </ol>
        </section>
      )}

      <History rows={r.history} currentId={r.attempt_id} />
    </div>
  );
}

function RemediationRow({
  item,
  n,
  module,
  result,
  primary,
  readOnly,
}: {
  item: RemediationItem;
  n: number;
  module: LearnerModuleDetail | null;
  result: Result;
  primary: boolean;
  readOnly?: boolean;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const number = module ? module.lessons.findIndex((l) => l.id === item.lesson_id) + 1 : 0;
  const title = pick(item, "lesson_title", lang);
  const details = [
    t("result.missed", { count: item.missed_count }),
    t("result.fragment", { from: clock(item.span_start_s), to: clock(item.span_end_s) }),
  ];
  if (!item.satisfied && item.watched_pct > 0) details.push(t("lesson.fragment_progress", { pct: item.watched_pct }));
  return (
    <li className={`remed-item ${item.satisfied ? "done" : ""}`}>
      <span className={`lesson-mark big ${item.satisfied ? "done" : ""}`} aria-hidden="true">
        {item.satisfied ? <Icon name="check" size={18} /> : n}
      </span>
      <div className="grow">
        <strong>{number > 0 ? `${number}. ${title}` : title}</strong>
        <p className="muted small">{details.join(" · ")}</p>
      </div>
      {readOnly ? null : item.satisfied ? (
        <span className="status-text success">{t("result.rewatched")}</span>
      ) : (
        <Link
          className={`btn ${primary ? "btn-primary" : ""}`}
          to={`/courses/${result.module_id}/lessons/${item.lesson_id}?t=${Math.floor(item.span_start_s)}`}
        >
          {t("result.watch_fragment")}
        </Link>
      )}
    </li>
  );
}

function History({ rows, currentId }: { rows: HistoryRow[]; currentId: number }) {
  const { t } = useTranslation();
  if (rows.length === 0) return null;
  return (
    <section className="stack-sm">
      <p className="caps">{t("result.history")}</p>
      <div className="card table-card">
        <table className="table">
          <thead>
            <tr>
              <th>{t("result.col_attempt")}</th>
              <th>{t("result.col_date")}</th>
              <th>{t("result.col_score")}</th>
              <th>{t("result.col_time")}</th>
              <th>{t("result.col_status")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((h) => (
              <tr key={h.attempt_id} className={h.attempt_id === currentId ? "current" : ""}>
                <td>
                  {h.status === "in_progress" ? (
                    <Link to={`/attempts/${h.attempt_id}`}>{h.number}</Link>
                  ) : h.attempt_id === currentId ? (
                    h.number
                  ) : (
                    <Link to={`/attempts/${h.attempt_id}/result`}>{h.number}</Link>
                  )}
                </td>
                <td>{dateTime(h.started_at)}</td>
                <td className="strong">{pct(h.score_pct)}</td>
                <td className="num">{h.time_spent_s !== null ? clock(h.time_spent_s) : "—"}</td>
                <td>
                  {h.status === "in_progress" ? (
                    <span className="status-text">{t("result.in_progress")}</span>
                  ) : (
                    <span className={`status-text ${h.passed ? "success" : "danger"}`}>
                      {t(h.passed ? "result.passed" : "result.failed")}
                      {h.status === "expired" && ` · ${t("result.expired_short")}`}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
