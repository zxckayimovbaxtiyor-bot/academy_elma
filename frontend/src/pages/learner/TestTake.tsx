import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { learner } from "../../api/learner";
import type { AttemptQuestion } from "../../api/types";
import { Brand } from "../../components/Brand";
import { Confirm } from "../../components/Dialog";
import { ErrorLine, ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { QuestionView } from "../../components/QuestionView";
import { AnswerSaver, type SaveState } from "../../lib/answers";
import { countdown } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { useApi, useRemaining } from "../../lib/useApi";

/** Taking a test (mockup 3): navigator, server-timed countdown, autosave, finish. */
export function TestTake() {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const id = Number(useParams().attemptId);
  const { data, error, loading, reload } = useApi(() => learner.attempt(id), [id]);
  const [questions, setQuestions] = useState<AttemptQuestion[]>([]);
  const [current, setCurrent] = useState(0);
  const [offset, setOffset] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [saveError, setSaveError] = useState<unknown>(null);
  const finishing = useRef(false);

  const toResult = useCallback(() => navigate(`/attempts/${id}/result`, { replace: true }), [id, navigate]);
  const saver = useRef<AnswerSaver | null>(null);
  useEffect(() => {
    const s = new AnswerSaver(id, setSaveState, toResult, setSaveError);
    saver.current = s;
    return () => s.close();
  }, [id, toResult]);

  useEffect(() => {
    if (!data) return;
    if (data.status !== "in_progress") {
      toResult();
      return;
    }
    setQuestions(data.questions);
    setOffset(Date.parse(data.server_now) - Date.now()); // the server's clock owns the deadline
    const firstOpen = data.questions.findIndex((q) => q.answer === null);
    setCurrent(firstOpen >= 0 ? firstOpen : 0);
  }, [data, toResult]);

  const remaining = useRemaining(data?.status === "in_progress" ? data.expires_at : null, offset);

  const finish = useCallback(async () => {
    if (finishing.current) return;
    finishing.current = true;
    setSubmitting(true);
    setSubmitError(null);
    try {
      // Let the last answers reach the server first (but don't wait forever offline).
      const pending = saver.current?.flushed() ?? Promise.resolve();
      await Promise.race([pending, new Promise((resolve) => window.setTimeout(resolve, 8000))]);
      await learner.submit(id);
      saver.current?.close();
      toResult();
    } catch (err) {
      finishing.current = false;
      if (err instanceof ApiError && (err.code === "attempt.finished" || err.code === "attempt.expired")) toResult();
      else setSubmitError(err);
    } finally {
      setSubmitting(false);
    }
  }, [id, toResult]);

  useEffect(() => {
    if (remaining === 0) void finish(); // time is up: graded with what was saved
  }, [remaining, finish]);

  if (loading && !data) return <PageLoader />;
  if (error || !data) {
    return (
      <div className="container page">
        <ErrorState error={error} onRetry={reload} />
        <p className="center-box">
          <Link to="/">{t("nav.home")}</Link>
        </p>
      </div>
    );
  }
  if (questions.length === 0) return <PageLoader />;

  const q = questions[Math.min(current, questions.length - 1)];
  const answered = questions.filter((x) => x.answer !== null && x.answer.length > 0).length;
  const flagged = questions.filter((x) => x.flagged).length;
  const total = questions.length;
  const timerTone = remaining === null ? "" : remaining < 60_000 ? "danger" : remaining < 300_000 ? "warn" : "";

  const setAnswer = (value: number[] | null) => {
    setQuestions((list) => list.map((x) => (x.position === q.position ? { ...x, answer: value } : x)));
    setSaveError(null);
    saver.current?.push(q.position, { answer: value });
  };
  const toggleFlag = () => {
    const value = !q.flagged;
    setQuestions((list) => list.map((x) => (x.position === q.position ? { ...x, flagged: value } : x)));
    saver.current?.push(q.position, { flagged: value });
  };

  return (
    <div className="test-page">
      <header className="test-top">
        <div className="container test-top-inner">
          <Brand link={false} />
          <div className="test-title">
            <strong>{t("take.title", { module: pick(data, "module_title", lang) })}</strong>
            <span className="muted">
              {t("take.subtitle", { n: data.number, max: data.max_attempts, pass: data.pass_pct })}
            </span>
          </div>
          <div className={`timer ${timerTone}`} role="timer" aria-label={t("take.time_left")}>
            <Icon name="clock" size={22} />
            <span>{remaining === null ? "--:--" : countdown(remaining)}</span>
          </div>
          <button className="btn" onClick={() => setConfirming(true)} disabled={submitting}>
            {t("take.finish")}
          </button>
        </div>
      </header>

      <main className="container test-main">
        <aside className="card card-pad q-nav">
          <div className="spread">
            <strong>{t("take.questions")}</strong>
            <span className="muted small">{t("take.answered", { done: answered, total })}</span>
          </div>
          <div className="q-grid">
            {questions.map((x, i) => {
              const state = [
                x.answer !== null && x.answer.length > 0 ? "answered" : "",
                x.flagged ? "flagged" : "",
                i === current ? "current" : "",
              ].join(" ");
              return (
                <button
                  key={x.position}
                  className={`q-cell ${state}`}
                  onClick={() => setCurrent(i)}
                  aria-current={i === current ? "step" : undefined}
                  aria-label={t("take.go_to", { n: i + 1 })}
                >
                  {i + 1}
                </button>
              );
            })}
          </div>
          <hr className="divider" />
          <ul className="q-legend">
            <li>
              <span className="q-cell answered" />
              {t("take.legend_answered")}
            </li>
            <li>
              <span className="q-cell current" />
              {t("take.legend_current")}
            </li>
            <li>
              <span className="q-cell flagged" />
              {t("take.legend_flagged")}
            </li>
          </ul>
          <p className={`save-state ${saveState}`} role="status">
            {saveState === "saving" && t("take.saving")}
            {saveState === "saved" && (
              <>
                <Icon name="check" size={16} />
                {t("take.saved")}
              </>
            )}
            {saveState === "retrying" && t("take.retrying")}
          </p>
        </aside>

        <section className="card card-pad-lg">
          <QuestionView key={q.position} q={q} number={current + 1} onAnswer={setAnswer} />
          <ErrorLine error={saveError} />
          <div className="q-footer">
            <button className={`btn btn-flag ${q.flagged ? "on" : ""}`} aria-pressed={q.flagged} onClick={toggleFlag}>
              <Icon name="flag" size={18} />
              {t("take.flag")}
            </button>
            <div className="row">
              <button className="btn" disabled={current === 0} onClick={() => setCurrent(current - 1)}>
                <Icon name="arrowLeft" size={18} />
                {t("take.prev")}
              </button>
              {current < total - 1 ? (
                <button className="btn btn-primary" onClick={() => setCurrent(current + 1)}>
                  {t("take.next")}
                  <Icon name="arrowRight" size={18} />
                </button>
              ) : (
                <button className="btn btn-primary" onClick={() => setConfirming(true)}>
                  {t("take.finish")}
                </button>
              )}
            </div>
          </div>
        </section>
      </main>

      {confirming && (
        <Confirm
          title={t("take.confirm_title")}
          confirmLabel={t("take.finish")}
          busy={submitting}
          onConfirm={() => void finish()}
          onCancel={() => setConfirming(false)}
        >
          <p>{t("take.confirm_text", { done: answered, total })}</p>
          {answered < total && (
            <div className="notice notice-warning">{t("take.confirm_unanswered", { count: total - answered })}</div>
          )}
          {flagged > 0 && <p className="muted">{t("take.confirm_flagged", { count: flagged })}</p>}
          <ErrorLine error={submitError} />
        </Confirm>
      )}
      {!confirming && submitError !== null && (
        <div className="container">
          <ErrorLine error={submitError} />
        </div>
      )}
    </div>
  );
}
