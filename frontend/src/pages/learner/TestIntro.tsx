import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { learner } from "../../api/learner";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { ErrorLine, ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { useReasonText } from "../../lib/reasons";
import { pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";

/** Before a test: size, time, pass mark, attempts and the rules; then start. */
export function TestIntro() {
  const { t } = useTranslation();
  const lang = useLang();
  const reasonText = useReasonText();
  const navigate = useNavigate();
  const id = Number(useParams().moduleId);
  const { data: m, error, loading, reload } = useApi(() => learner.module(id), [id]);
  const [busy, setBusy] = useState(false);
  const [startError, setStartError] = useState<unknown>(null);
  if (loading && !m) return <PageLoader />;
  if (error || !m) return <ErrorState error={error} onRetry={reload} />;
  const test = m.test;
  const title = pick(m, "title", lang);
  if (!test) return <ErrorState error={null} />;
  const s = test.status;
  const next = s.open_attempt_id !== null ? s.attempts_used : Math.min(s.attempts_used + 1, s.attempts_max);
  const reasons = s.reasons.filter((r) => r.code !== "attempt_in_progress");

  const start = async () => {
    setBusy(true);
    setStartError(null);
    try {
      const started = await learner.startAttempt(id);
      navigate(`/attempts/${started.attempt_id}`, { replace: true });
    } catch (err) {
      setStartError(err);
      reload(); // the reasons may have changed meanwhile
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack-lg narrow">
      <Breadcrumbs
        items={[
          { label: t("nav.courses"), to: "/courses" },
          { label: title, to: `/courses/${m.id}` },
          { label: t("test.title") },
        ]}
      />
      <section className="card card-pad-lg stack">
        <p className="caps">{t("test.title")}</p>
        <h1>{title}</h1>
        <div className="facts">
          <div className="fact">
            <span>{t("intro.questions")}</span>
            <strong>{test.question_count}</strong>
          </div>
          <div className="fact">
            <span>{t("intro.time")}</span>
            <strong>{t("intro.minutes", { count: test.time_limit_min })}</strong>
          </div>
          <div className="fact">
            <span>{t("intro.pass")}</span>
            <strong>{test.pass_pct}%</strong>
          </div>
          <div className="fact">
            <span>{t("intro.attempt")}</span>
            <strong className="num">
              {next} / {s.attempts_max}
            </strong>
          </div>
        </div>
        <ul className="rules">
          {["random", "timer", "autosave", "unanswered", "no_answers", "after_fail"].map((k) => (
            <li key={k}>{t(`intro.rule_${k}`)}</li>
          ))}
        </ul>
        <ErrorLine error={startError} />
        {s.open_attempt_id !== null ? (
          <Link className="btn btn-primary btn-lg" to={`/attempts/${s.open_attempt_id}`}>
            {t("test.resume")}
          </Link>
        ) : s.can_start ? (
          <button className="btn btn-primary btn-lg" onClick={start} disabled={busy}>
            {t("intro.start")}
          </button>
        ) : (
          <div className="notice notice-warning">
            <Icon name="lock" />
            <div className="stack-sm">
              <strong>{t("intro.blocked")}</strong>
              <ul className="reasons">
                {reasons.map((r) => (
                  <li key={r.code}>{reasonText(r)}</li>
                ))}
              </ul>
              {s.last_attempt_id !== null && (
                <Link to={`/attempts/${s.last_attempt_id}/result`}>{t("test.view_result")}</Link>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
