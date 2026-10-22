import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  practice,
  type Command,
  type Mode,
  type PSession,
  type Value,
} from "../api/practice";
import { ErrorLine, ErrorState, PageLoader } from "../components/Feedback";
import { ProgressBar } from "../components/Status";
import { useLang } from "../lib/lang";
import { useApi } from "../lib/useApi";
import { dateTime } from "../lib/format";
import { ScenarioScreen } from "./Renderer";

export function PracticeCatalog({
  moduleId,
  lessonId,
  compact = false,
}: {
  moduleId?: number;
  lessonId?: number;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const { data, error, loading, reload } = useApi(
    () => practice.list(moduleId, lessonId),
    [moduleId, lessonId],
  );
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const launch = async (id: number, mode: Mode) => {
    setBusy(true);
    setFailure(null);
    try {
      const s = await practice.start(id, mode);
      navigate(`/practice/sessions/${s.id}`);
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
    }
  };
  if (loading) return <PageLoader />;
  if (error || !data) return <ErrorState error={error} onRetry={reload} />;
  if (compact && !data.length) return null;
  return (
    <section className="stack">
      <header>
        <h1>{t("practice.title")}</h1>
        {!compact && <p className="muted">{t("practice.intro")}</p>}
      </header>
      <ErrorLine error={failure} />
      {!data.length && (
        <div className="card card-pad muted">{t("practice.empty")}</div>
      )}
      {data.map((s) => (
        <article key={s.id} className="card card-pad stack">
          <div className="spread">
            <h2>{s.title[lang]}</h2>
            <span className="chip">
              {t("practice.version", { number: s.number })}
            </span>
          </div>
          <p>{s.description[lang]}</p>
          <p className="muted">
            {t("practice.policy_summary", {
              score: s.policy.pass_pct,
              attempts: s.policy.max_attempts,
            })}
            {s.policy.required && ` · ${t("practice.required")}`}
          </p>
          <div className="row practice-wrap">
            {(["guided", "sandbox", "exam"] as Mode[]).map((mode) => (
              <button
                className={mode === "guided" ? "btn btn-primary" : "btn"}
                key={mode}
                disabled={busy}
                onClick={() => launch(s.id, mode)}
              >
                {t(`practice.mode.${mode}`)}
              </button>
            ))}
          </div>
          {s.sessions.length > 0 && (
            <details>
              <summary>{t("practice.attempt_history")}</summary>
              <ul className="practice-history">
                {s.sessions.map((a) => (
                  <li key={a.id}>
                    <Link to={`/practice/sessions/${a.id}`}>
                      {t(`practice.mode.${a.mode}`)} ·{" "}
                      {t(
                        a.status === "active"
                          ? "practice.resume"
                          : "practice.completed",
                      )}
                      {a.result ? ` · ${a.result.score_pct}%` : ""}
                    </Link>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </article>
      ))}
    </section>
  );
}

export function PracticeSessionPage() {
  const id = Number(useParams().sessionId);
  const { t } = useTranslation();
  const lang = useLang();
  const loaded = useApi(() => practice.session(id), [id]);
  const s = loaded.data;
  const [values, setValues] = useState<Record<string, Value>>({});
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const pending = useRef<Command | null>(null);
  const inFlight = useRef(false);
  useEffect(() => {
    if (s) {
      setValues(s.values);
      setDirty(false);
    }
  }, [s]);
  const send = async (
    kind: Command["kind"],
    action?: string,
    retry = false,
    target?: string,
  ) => {
    if (!s || inFlight.current) return;
    const cmd = retry
      ? pending.current
      : {
          request_id: crypto.randomUUID(),
          expected_revision: s.revision,
          kind,
          action,
          target,
          values: ["action", "save", "finish"].includes(kind)
            ? Object.fromEntries(
                Object.entries(values).filter(([key]) =>
                  s.screen.components.some(
                    (c) =>
                      c.id === key &&
                      [
                        "text",
                        "number",
                        "select",
                        "checkbox",
                        "document",
                        "tabs",
                      ].includes(c.type),
                  ),
                ),
              )
            : {},
        };
    if (!cmd) return;
    pending.current = cmd;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    try {
      const result = await practice.command(id, cmd);
      pending.current = null;
      loaded.setData(result);
    } catch (e) {
      setFailure(e);
      if (e instanceof ApiError && e.status === 409) {
        pending.current = null;
        loaded.reload();
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  useEffect(() => {
    if (!dirty || busy || !s || s.status !== "active" || pending.current)
      return;
    const timer = window.setTimeout(() => void send("save"), 1200);
    return () => window.clearTimeout(timer);
  }, [values, dirty, busy, s]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  if (loaded.loading && !s) return <PageLoader />;
  if (loaded.error || !s)
    return <ErrorState error={loaded.error} onRetry={loaded.reload} />;
  return (
    <div className="stack">
      <div className="spread practice-wrap">
        <Link to="/practice">← {t("practice.title")}</Link>
        <span className="chip chip-primary">{t("practice.synthetic")}</span>
      </div>
      <header className="spread practice-wrap">
        <div>
          <h1>{s.title[lang]}</h1>
          <p className="muted">
            {t(`practice.mode.${s.mode}`)} ·{" "}
            {t("practice.version", { number: s.version })}
          </p>
        </div>
        <span role="status" className="muted">
          {t(
            busy
              ? "practice.saving"
              : dirty
                ? "practice.unsaved"
                : "practice.saved",
          )}
        </span>
      </header>
      <ErrorLine error={failure} />
      {pending.current && Boolean(failure) && (
        <button
          className="btn"
          disabled={busy}
          onClick={() => send("save", undefined, true)}
        >
          {t("app.retry")}
        </button>
      )}
      <ProgressBar value={s.progress} />
      {s.task && <div className="notice">{s.task[lang]}</div>}
      {s.result ? (
        <Result s={s} />
      ) : (
        <div className="practice-shell">
          <aside className="practice-side">
            <strong>{t("practice.workspace")}</strong>
            <ol>
              {s.navigation.map((n) => (
                <li
                  key={n.id}
                  className={s.screen.id === n.id ? "active" : ""}
                  aria-current={s.screen.id === n.id ? "step" : undefined}
                >
                  {s.mode === "sandbox" ? (
                    <button
                      type="button"
                      className="btn"
                      disabled={busy || dirty || !!pending.current}
                      onClick={() => send("navigate", undefined, false, n.id)}
                    >
                      {n.title[lang]}
                    </button>
                  ) : (
                    <>
                      {n.visited ? "✓ " : ""}
                      {n.title[lang]}
                    </>
                  )}
                </li>
              ))}
            </ol>
            <span className="small muted">{t("practice.isolated")}</span>
          </aside>
          <div className="practice-main">
            <div className="practice-toolbar">
              <span className="chip">{t("practice.training_application")}</span>
              <span>
                {t("practice.progress", {
                  done: s.visited.length,
                  total: s.navigation.length,
                })}
              </span>
            </div>
            <ScenarioScreen
              summary={s.summary}
              screen={s.screen}
              values={values}
              setValues={(v) => {
                setValues(v);
                setDirty(true);
              }}
              onAction={(action) => send("action", action)}
              disabled={busy || !!pending.current}
              guided={s.mode === "guided"}
              feedback={s.feedback}
              sessionId={s.id}
            />
            {s.mode === "sandbox" && (
              <section className="practice-workspace stack">
                <div className="spread">
                  <h3>{t("practice.virtual_applications")}</h3>
                  <button
                    className="btn"
                    disabled={busy || dirty || !!pending.current}
                    onClick={() => send("new_record")}
                  >
                    {t("practice.new_application")}
                  </button>
                </div>
                <div className="practice-table">
                  <table>
                    <thead>
                      <tr>
                        <th>{t("practice.identifier")}</th>
                        <th>{t("practice.status")}</th>
                        <th>{t("practice.action")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.records.map((r) => (
                        <tr key={r.id}>
                          <td>{r.id}</td>
                          <td>
                            {t(
                              r.status === "submitted"
                                ? "practice.submitted"
                                : "practice.draft",
                            )}
                          </td>
                          <td>
                            <div className="row">
                              <button
                                className="btn"
                                disabled={
                                  busy ||
                                  dirty ||
                                  !!pending.current ||
                                  s.record_id === r.id
                                }
                                onClick={() =>
                                  send("open_record", undefined, false, r.id)
                                }
                              >
                                {t("practice.open")}
                              </button>
                              <button
                                className="btn"
                                disabled={busy || dirty || !!pending.current}
                                onClick={() =>
                                  send("delete_record", undefined, false, r.id)
                                }
                              >
                                {t("practice.remove")}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
            <footer className="row practice-wrap practice-footer">
              {s.mode !== "exam" && (
                <button
                  className="btn"
                  disabled={
                    busy || dirty || !s.history.length || !!pending.current
                  }
                  onClick={() => send("back")}
                >
                  {t("practice.back")}
                </button>
              )}
              <button
                className="btn"
                disabled={busy || !!pending.current}
                onClick={() => send("save")}
              >
                {t("practice.save_progress")}
              </button>
              {s.mode === "sandbox" && (
                <button
                  className="btn"
                  disabled={busy || !!pending.current}
                  onClick={() => send("reset")}
                >
                  {t("practice.reset")}
                </button>
              )}
              {s.can_finish && (
                <button
                  className="btn btn-primary"
                  disabled={busy || !!pending.current}
                  onClick={() => send("finish")}
                >
                  {t("practice.finish")}
                </button>
              )}
            </footer>
          </div>
        </div>
      )}
      <PracticeHistory id={s.id} revision={s.revision} />
    </div>
  );
}

function PracticeHistory({ id, revision }: { id: number; revision: number }) {
  const { t } = useTranslation();
  const { data, error } = useApi(() => practice.history(id), [id, revision]);
  return (
    <details className="card card-pad">
      <summary>{t("practice.action_history")}</summary>
      <ErrorLine error={error} />
      <ol className="practice-history">
        {data?.map((a) => (
          <li key={a.id}>
            {dateTime(a.at)} · {t(`practice.command.${a.kind}`)} · {a.screen_id}
            {a.invalid ? ` · ${t("practice.invalid_logged")}` : ""}
          </li>
        ))}
      </ol>
    </details>
  );
}

function Result({ s }: { s: PSession }) {
  const { t } = useTranslation();
  const lang = useLang();
  const r = s.result!;
  return (
    <article className="card card-pad stack">
      <h2>{t(r.passed ? "practice.passed" : "practice.failed")}</h2>
      <div className="practice-score">{r.score_pct}%</div>
      <p>{t("practice.duration", { seconds: r.duration_s })}</p>
      <p className="muted">{t("practice.result_note")}</p>
      {r.errors.length > 0 && (
        <>
          <h3>{t("practice.errors")}</h3>
          <ul>
            {r.errors.map((e, i) => (
              <li key={i}>
                {e.message?.[lang] ??
                  t("practice.required_field", {
                    field:
                      s.summary?.find((item) => item.field === e.field)?.label[
                        lang
                      ] ?? e.field,
                  })}{" "}
                ·{" "}
                {s.navigation.find((n) => n.id === e.screen)?.title[lang] ??
                  e.screen}
              </li>
            ))}
          </ul>
        </>
      )}
      <Link className="btn btn-primary" to="/practice">
        {t("practice.title")}
      </Link>
    </article>
  );
}
