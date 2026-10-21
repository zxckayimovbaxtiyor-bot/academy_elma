import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ai, content, questions } from "../../api/admin";
import { ApiError } from "../../api/client";
import type { Job, LessonAdmin, OptionInput, Pool, QuestionAdmin, QuestionInput } from "../../api/adminTypes";
import type { QuestionType } from "../../api/types";
import { Confirm } from "../../components/Dialog";
import { ErrorLine, ErrorState, PageLoader, useErrorText } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { clock } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";
import { useRefreshDrafts } from "../AdminLayout";
import { Field, FilePick, Modal, PageHead, parseClock, useToast } from "../ui";

const TYPES: QuestionType[] = ["single", "multiple", "ordering", "screenshot"];
const LETTERS = "ABCDEFGH";
type Filter = "draft" | "approved" | "retired" | "flagged" | "all";

/** Question bank of one module: review queue, editor, pool and test publishing (mockup 7). */
export function Questions() {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const moduleId = Number(useParams().moduleId) || null;
  const [search, setSearch] = useSearchParams();
  const modules = useApi(() => content.modules(), []);
  const testModules = (modules.data ?? []).filter((m) => m.type !== "faq");

  useEffect(() => {
    if (!moduleId && testModules.length) navigate(`/admin/questions/${testModules[0].id}`, { replace: true });
  }, [moduleId, testModules, navigate]);

  if (modules.error) return <ErrorState error={modules.error} onRetry={modules.reload} />;
  if (!modules.data || !moduleId) return <PageLoader />;
  const module = testModules.find((m) => m.id === moduleId);
  if (!module) return <ErrorState error={new ApiError(404, "module.not_found")} />;

  return (
    <Bank
      key={module.id}
      moduleId={module.id}
      title={
        <span className="row wrap title-select">
          {t("bank.title")} ·
          <select
            className="input"
            value={module.id}
            aria-label={t("reports.module")}
            onChange={(e) => navigate(`/admin/questions/${e.target.value}`)}
          >
            {testModules.map((m) => (
              <option key={m.id} value={m.id}>
                {pick(m, "title", lang)}
              </option>
            ))}
          </select>
        </span>
      }
      search={search}
      setSearch={setSearch}
    />
  );
}

function Bank({
  moduleId,
  title,
  search,
  setSearch,
}: {
  moduleId: number;
  title: React.ReactNode;
  search: URLSearchParams;
  setSearch: ReturnType<typeof useSearchParams>[1];
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const toast = useToast();
  const refreshDrafts = useRefreshDrafts();
  const filter = (search.get("show") as Filter | null) ?? "draft";
  const lessonFilter = search.get("lesson") ? Number(search.get("lesson")) : undefined;
  const selected = search.get("q") === "new" ? "new" : search.get("q") ? Number(search.get("q")) : null;
  const params = {
    status: filter === "draft" || filter === "approved" || filter === "retired" ? filter : undefined,
    flagged: filter === "flagged" ? true : undefined,
    lesson_id: lessonFilter,
  };
  const list = useApi(() => questions.list(moduleId, params), [moduleId, JSON.stringify(params)]);
  const pool = useApi(() => questions.pool(moduleId), [moduleId]);
  const lessons = useApi(() => content.lessons(moduleId), [moduleId]);
  const aiStatus = useApi(() => ai.status(), []);
  const [drafting, setDrafting] = useState(false);
  const [unpublishing, setUnpublishing] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const set = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(search);
    for (const [k, v] of Object.entries(changes)) {
      if (v === undefined || v === "") next.delete(k);
      else next.set(k, v);
    }
    setSearch(next, { replace: true });
  };
  const select = (id: number | "new" | null) => set({ q: id === null ? undefined : String(id) });
  const refresh = () => {
    list.reload();
    pool.reload();
    refreshDrafts();
  };
  const lessonNo = useMemo(() => new Map((lessons.data ?? []).map((l, i) => [l.id, i + 1])), [lessons.data]);

  const items = list.data ?? [];
  const current = typeof selected === "number" ? items.find((q) => q.id === selected) ?? null : null;
  const nextDraft = (id: number) => {
    const i = items.findIndex((q) => q.id === id);
    const rest = items.filter((q, j) => q.status === "draft" && q.id !== id && j > i);
    return rest[0]?.id ?? items.find((q) => q.status === "draft" && q.id !== id)?.id ?? null;
  };
  const testAction = async (fn: () => Promise<Pool>, message: string) => {
    setError(null);
    try {
      await fn();
      toast(message);
      pool.reload();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <div className="stack-lg">
      <PageHead
        title={title}
        subtitle={t("bank.subtitle")}
        actions={
          <>
            <button className="btn" onClick={() => select("new")}>
              <Icon name="plus" size={18} />
              {t("bank.new")}
            </button>
            {aiStatus.data?.enabled && (
              <button className="btn" onClick={() => setDrafting(true)}>
                <Icon name="sparkle" size={18} />
                {t("bank.ai_button")}
              </button>
            )}
          </>
        }
      />
      {pool.data && <PoolBanner pool={pool.data} onPublish={() => testAction(() => questions.publishTest(moduleId), t("bank.published"))} onUnpublish={() => setUnpublishing(true)} />}
      <ErrorLine error={error} />
      <div className="bank">
        <aside className="card bank-queue">
          <div className="card-head stack-sm">
            <div className="spread">
              <strong>{t(`bank.show.${filter}`)}</strong>
              <span className="muted small">{t("bank.count", { count: items.length })}</span>
            </div>
            <div className="row wrap">
              <select className="input input-small" value={filter} onChange={(e) => set({ show: e.target.value, q: undefined })} aria-label={t("bank.filter")}>
                {(["draft", "approved", "flagged", "retired", "all"] as Filter[]).map((f) => (
                  <option key={f} value={f}>
                    {t(`bank.show.${f}`)}
                  </option>
                ))}
              </select>
              <select className="input input-small" value={lessonFilter ?? ""} onChange={(e) => set({ lesson: e.target.value, q: undefined })} aria-label={t("bank.lesson")}>
                <option value="">{t("bank.all_lessons")}</option>
                {(lessons.data ?? []).map((l, i) => (
                  <option key={l.id} value={l.id}>
                    {i + 1}. {pick(l, "title", lang)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {list.error ? (
            <ErrorState error={list.error} onRetry={list.reload} />
          ) : !list.data ? (
            <PageLoader />
          ) : items.length === 0 ? (
            <p className="card-pad muted small">{t("bank.empty")}</p>
          ) : (
            <ol className="queue">
              {items.map((q) => (
                <li key={q.id} className={q.id === selected ? "on" : ""}>
                  <button onClick={() => select(q.id)}>
                    <span className="spread muted small">
                      <span>
                        {q.number} · {lessonNo.get(q.lesson_id) ?? "?"}. {pick(q, "lesson_title", lang)}
                      </span>
                      <span className="num">{clock(q.video_ts_s)}</span>
                    </span>
                    <span className="queue-text">{pick(q, "text", lang)}</span>
                    <span className="row wrap">
                      {q.origin === "ai" && <span className="chip chip-ai">{t("bank.ai")}</span>}
                      {filter === "all" && <span className="chip">{t(`bank.status.${q.status}`)}</span>}
                      {q.stats.flagged && <span className="chip chip-warning">{t("bank.flagged")}</span>}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </aside>
        {selected === "new" ? (
          <Editor
            key="new"
            moduleId={moduleId}
            question={null}
            lessons={lessons.data ?? []}
            onSaved={(q) => {
              refresh();
              set({ q: String(q.id), show: "draft" });
            }}
            onAdvance={(id) => select(id === "next" ? null : id)}
            onOpen={(id, show) => {
              refresh();
              set({ q: String(id), show });
            }}
          />
        ) : current ? (
          <Editor
            key={current.id}
            moduleId={moduleId}
            question={current}
            lessons={lessons.data ?? []}
            onSaved={() => refresh()}
            onAdvance={(id) => {
              const next = id === "next" ? nextDraft(current.id) : id;
              refresh();
              select(next);
            }}
            onOpen={(id, show) => {
              refresh();
              set({ q: String(id), show });
            }}
          />
        ) : (
          <div className="card card-pad muted center-box">{t("bank.pick")}</div>
        )}
      </div>
      {drafting && lessons.data && (
        <AiDraftDialog
          lessons={lessons.data}
          onClose={() => setDrafting(false)}
          onDone={() => {
            refresh();
            set({ show: "draft", q: undefined });
          }}
        />
      )}
      {unpublishing && (
        <Confirm
          title={t("bank.unpublish_title")}
          confirmLabel={t("bank.unpublish")}
          onCancel={() => setUnpublishing(false)}
          onConfirm={() => {
            setUnpublishing(false);
            void testAction(() => questions.unpublishTest(moduleId), t("bank.unpublished"));
          }}
        >
          <p>{t("bank.unpublish_text")}</p>
        </Confirm>
      )}
    </div>
  );
}

function PoolBanner({ pool, onPublish, onUnpublish }: { pool: Pool; onPublish: () => void; onUnpublish: () => void }) {
  const { t } = useTranslation();
  const pctDone = Math.min(100, (pool.approved_active / Math.max(1, pool.required)) * 100);
  if (pool.test_published) {
    return (
      <div className="notice notice-success pool-banner">
        <Icon name="check" />
        <span className="grow">{t("bank.test_live", { have: pool.approved_active, need: pool.required })}</span>
        <button className="btn btn-small" onClick={onUnpublish}>
          {t("bank.unpublish")}
        </button>
      </div>
    );
  }
  if (!pool.publishable) {
    return (
      <div className="notice notice-warning pool-banner">
        <Icon name="alert" />
        <span className="grow">
          <strong>{t("bank.cannot_publish")}</strong>{" "}
          {t("bank.pool_short", { have: pool.approved_active, need: pool.required, n: pool.question_count, missing: pool.required - pool.approved_active })}
        </span>
        <span className="pool-bar" aria-hidden="true">
          <span style={{ width: `${pctDone}%` }} />
        </span>
      </div>
    );
  }
  return (
    <div className="notice pool-banner">
      <Icon name="info" />
      <span className="grow">{t("bank.ready_to_publish", { have: pool.approved_active, need: pool.required })}</span>
      <button className="btn btn-primary btn-small" onClick={onPublish}>
        {t("bank.publish")}
      </button>
    </div>
  );
}

// --- editor -----------------------------------------------------------------------------------

interface Form extends QuestionInput {
  options: (OptionInput & { key: number })[];
}

let keySeq = 1;
const blankOption = (): Form["options"][number] => ({ key: keySeq++, text_uz: "", text_ru: "", is_correct: false });

function toForm(q: QuestionAdmin | null, lessons: LessonAdmin[]): Form {
  if (!q) {
    return {
      lesson_id: lessons[0]?.id ?? 0,
      video_ts_s: 0,
      type: "single",
      text_uz: "",
      text_ru: "",
      explanation_uz: "",
      explanation_ru: "",
      difficulty: 2,
      options: [blankOption(), blankOption(), blankOption(), blankOption()],
    };
  }
  return {
    lesson_id: q.lesson_id,
    video_ts_s: q.video_ts_s,
    type: q.type,
    text_uz: q.text_uz,
    text_ru: q.text_ru,
    explanation_uz: q.explanation_uz,
    explanation_ru: q.explanation_ru,
    difficulty: q.difficulty,
    options: q.options.map((o) => ({ key: keySeq++, id: o.id, text_uz: o.text_uz, text_ru: o.text_ru, is_correct: o.is_correct })),
  };
}

function useProblems() {
  const { t } = useTranslation();
  const errorText = useErrorText();
  return (err: unknown) => {
    if (err instanceof ApiError && Array.isArray(err.params.problems)) {
      return `${errorText(err)} ${(err.params.problems as string[]).map((p) => t(`bank.problem.${p}`, { defaultValue: p })).join(" · ")}`;
    }
    return errorText(err);
  };
}

function Editor({
  moduleId,
  question: q,
  lessons,
  onSaved,
  onAdvance,
  onOpen,
}: {
  moduleId: number;
  question: QuestionAdmin | null;
  lessons: LessonAdmin[];
  onSaved: (q: QuestionAdmin) => void;
  onAdvance: (id: number | "next" | null) => void;
  onOpen: (id: number, show: Filter) => void;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const toast = useToast();
  const problemText = useProblems();
  const [form, setForm] = useState<Form>(() => toForm(q, lessons));
  const [ts, setTs] = useState(() => clock(q?.video_ts_s ?? 0));
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [retiring, setRetiring] = useState(false);
  const draft = !q || q.status === "draft";
  const approved = q?.status === "approved";
  const retired = q?.status === "retired";
  const locked = !draft; // answer key, type and lesson
  const original = JSON.stringify(toComparable(toForm(q, lessons)));
  const dirty = JSON.stringify(toComparable(form)) !== original || (q !== null && parseClock(ts) !== q.video_ts_s);

  const body = (): Partial<QuestionInput> => {
    const seconds = parseClock(ts) ?? 0;
    const options = form.options.map((o) => ({
      id: approved ? o.id : undefined,
      text_uz: o.text_uz.trim(),
      text_ru: o.text_ru.trim(),
      is_correct: form.type === "ordering" ? false : o.is_correct,
    }));
    const common = {
      video_ts_s: seconds,
      text_uz: form.text_uz.trim(),
      text_ru: form.text_ru.trim(),
      explanation_uz: form.explanation_uz.trim(),
      explanation_ru: form.explanation_ru.trim(),
      difficulty: form.difficulty,
      options,
    };
    return approved ? common : { ...common, lesson_id: form.lesson_id, type: form.type };
  };

  const save = async (): Promise<QuestionAdmin | null> => {
    if (parseClock(ts) === null) {
      setError(new ApiError(400, "bank.bad_time"));
      return null;
    }
    setBusy(true);
    setError(null);
    try {
      const saved = q ? await questions.patch(q.id, body()) : await questions.create(moduleId, body() as QuestionInput);
      return saved;
    } catch (err) {
      setError(err);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const run = async (fn: () => Promise<unknown>, message: string, advance: number | "next" | null | undefined): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      toast(message);
      if (advance !== undefined) onAdvance(advance);
      else if (q) onSaved(q);
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const setOption = (i: number, patch: Partial<Form["options"][number]>) =>
    setForm({ ...form, options: form.options.map((o, j) => (j === i ? { ...o, ...patch } : o)) });
  const markCorrect = (i: number) => {
    if (form.type === "multiple") setOption(i, { is_correct: !form.options[i].is_correct });
    else setForm({ ...form, options: form.options.map((o, j) => ({ ...o, is_correct: j === i })) });
  };
  const moveOption = (i: number, by: number) => {
    const next = [...form.options];
    const [x] = next.splice(i, 1);
    next.splice(i + by, 0, x);
    setForm({ ...form, options: next });
  };

  return (
    <section className="card card-pad stack bank-editor">
      <div className="row wrap">
        <h2>{q ? t(draft ? "bank.draft_no" : "bank.question_no", { number: q.number }) : t("bank.new")}</h2>
        {q && <span className={`chip ${q.origin === "ai" ? "chip-ai" : ""}`}>{t(q.origin === "ai" ? "bank.ai_draft" : "bank.manual")}</span>}
        <span className="chip">{t(`bank.type.${form.type}`)}</span>
        {q && <span className="chip chip-primary">{t("path.release", { release: q.release_code })}</span>}
        {q && !draft && (
          <span className={`chip ${approved ? "chip-success" : ""}`}>
            {t(`bank.status.${q.status}`)}
            {q.retired_reason && ` · ${t(`bank.retired.${q.retired_reason}`)}`}
          </span>
        )}
      </div>
      {q && q.stats.attempts > 0 && (
        <p className={`small ${q.stats.flagged ? "text-warning" : "muted"}`}>
          {t("bank.stats", { attempts: q.stats.attempts, pct: q.stats.correct_pct ?? 0 })}
          {q.stats.flagged && ` · ${t("bank.flag_reason")}`}
        </p>
      )}

      {draft && (
        <Field label={t("bank.type_label")} htmlFor="q-type">
          <select
            id="q-type"
            className="input"
            value={form.type}
            onChange={(e) => {
              const type = e.target.value as QuestionType;
              const options = form.options.map((o) => ({ ...o, is_correct: type === "ordering" ? false : o.is_correct }));
              setForm({ ...form, type, options });
            }}
          >
            {TYPES.map((x) => (
              <option key={x} value={x}>
                {t(`bank.type.${x}`)}
              </option>
            ))}
          </select>
        </Field>
      )}

      <div className="grid-2">
        <Field label={t("bank.text_uz")} htmlFor="q-uz">
          <textarea id="q-uz" className="input textarea" rows={3} value={form.text_uz} disabled={retired} onChange={(e) => setForm({ ...form, text_uz: e.target.value })} />
        </Field>
        <Field label={t("bank.text_ru")} htmlFor="q-ru">
          <textarea id="q-ru" className="input textarea" rows={3} value={form.text_ru} disabled={retired} onChange={(e) => setForm({ ...form, text_ru: e.target.value })} />
        </Field>
      </div>

      {form.type === "screenshot" && (
        <div className="file-box">
          <strong>{t("bank.screenshot")}</strong>
          {q?.image_url ? <img className="shot" src={q.image_url} alt={t("q.image")} /> : <span className="muted small">{t("bank.no_image")}</span>}
          {q && draft ? (
            <FilePick accept="image/png,image/jpeg" className="btn btn-small" onFile={(f) => run(() => questions.image(q.id, f), t("bank.image_saved"), undefined)}>
              <Icon name="upload" size={16} />
              {t("bank.upload_image")}
            </FilePick>
          ) : (
            !q && <span className="muted small">{t("bank.image_after_save")}</span>
          )}
          <span className="muted small">{t("bank.screenshot_rule")}</span>
        </div>
      )}

      <div className="stack-sm">
        <strong className="small">
          {form.type === "ordering" ? t("bank.options_ordering") : t("bank.options")}
          {locked && ` · ${t("bank.key_locked")}`}
        </strong>
        {form.options.map((o, i) => (
          <div key={o.key} className={`opt-row ${o.is_correct ? "correct" : ""}`}>
            {form.type === "ordering" ? (
              <span className="order-num">{i + 1}</span>
            ) : (
              <input
                type={form.type === "multiple" ? "checkbox" : "radio"}
                className="box"
                name="correct"
                checked={o.is_correct}
                disabled={locked}
                onChange={() => markCorrect(i)}
                aria-label={t("bank.correct", { letter: LETTERS[i] })}
              />
            )}
            <span className="opt-letter">{LETTERS[i]}</span>
            <input className="input" value={o.text_uz} disabled={retired} placeholder="UZ" onChange={(e) => setOption(i, { text_uz: e.target.value })} aria-label={`${LETTERS[i]} UZ`} />
            <input className="input" value={o.text_ru} disabled={retired} placeholder="RU" onChange={(e) => setOption(i, { text_ru: e.target.value })} aria-label={`${LETTERS[i]} RU`} />
            {!locked && (
              <span className="reorder">
                {form.type === "ordering" && (
                  <>
                    <button className="btn btn-ghost btn-icon" disabled={i === 0} onClick={() => moveOption(i, -1)} aria-label={t("q.move_up")}>
                      <Icon name="up" size={16} />
                    </button>
                    <button className="btn btn-ghost btn-icon" disabled={i === form.options.length - 1} onClick={() => moveOption(i, 1)} aria-label={t("q.move_down")}>
                      <Icon name="down" size={16} />
                    </button>
                  </>
                )}
                <button
                  className="btn btn-ghost btn-icon"
                  disabled={form.options.length <= 2}
                  onClick={() => setForm({ ...form, options: form.options.filter((_, j) => j !== i) })}
                  aria-label={t("bank.remove_option")}
                >
                  <Icon name="trash" size={16} />
                </button>
              </span>
            )}
          </div>
        ))}
        {!locked && form.options.length < 8 && (
          <div>
            <button className="btn btn-small" onClick={() => setForm({ ...form, options: [...form.options, blankOption()] })}>
              <Icon name="plus" size={16} />
              {t("bank.add_option")}
            </button>
          </div>
        )}
        <span className="muted small">{t(`bank.rule.${form.type}`)}</span>
      </div>

      <div className="grid-3">
        <Field label={t("bank.lesson")} htmlFor="q-lesson">
          <select id="q-lesson" className="input" value={form.lesson_id} disabled={locked} onChange={(e) => setForm({ ...form, lesson_id: Number(e.target.value) })}>
            {lessons.map((l, i) => (
              <option key={l.id} value={l.id}>
                {i + 1}. {pick(l, "title", lang)}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("bank.video_time")} hint={t("bank.video_time_hint")} htmlFor="q-ts">
          <input id="q-ts" className="input num" value={ts} disabled={retired} onChange={(e) => setTs(e.target.value)} />
        </Field>
        <Field label={t("bank.difficulty")} htmlFor="q-diff">
          <select id="q-diff" className="input" value={form.difficulty} disabled={retired} onChange={(e) => setForm({ ...form, difficulty: Number(e.target.value) })}>
            {[1, 2, 3].map((d) => (
              <option key={d} value={d}>
                {t(`bank.difficulty_${d}`)}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <div className="grid-2">
        <Field label={t("bank.explanation_uz")} hint={t("bank.explanation_hint")} htmlFor="q-ex-uz">
          <textarea id="q-ex-uz" className="input textarea" rows={2} value={form.explanation_uz} disabled={retired} onChange={(e) => setForm({ ...form, explanation_uz: e.target.value })} />
        </Field>
        <Field label={t("bank.explanation_ru")} htmlFor="q-ex-ru">
          <textarea id="q-ex-ru" className="input textarea" rows={2} value={form.explanation_ru} disabled={retired} onChange={(e) => setForm({ ...form, explanation_ru: e.target.value })} />
        </Field>
      </div>

      {q?.origin === "ai" && (
        <div className="source-box">
          <div className="spread">
            <strong className="small">
              {t("bank.source", {
                from: clock(q.ai_source_start_s ?? q.video_ts_s),
                to: clock(q.ai_source_end_s ?? q.video_ts_s),
              })}
            </strong>
            <Link className="small" to={`/admin/content/lessons/${q.lesson_id}?t=${Math.floor(q.ai_source_start_s ?? q.video_ts_s)}`}>
              {t("bank.open_video")}
            </Link>
          </div>
          {q.ai_source_excerpt && <p className="small">«{q.ai_source_excerpt}»</p>}
        </div>
      )}

      {error !== null && <div className="notice notice-danger">{problemText(error)}</div>}
      <div className="row wrap bank-actions">
        {q && draft && (
          <button className="btn btn-danger-ghost" disabled={busy} onClick={() => run(() => questions.reject(q.id), t("bank.rejected"), "next")}>
            {t("bank.reject")}
          </button>
        )}
        {q && approved && (
          <button className="btn btn-danger-ghost" disabled={busy} onClick={() => setRetiring(true)}>
            {t("bank.retire")}
          </button>
        )}
        {q && !draft && (
          <button
            className="btn"
            disabled={busy}
            onClick={async () => {
              try {
                const copy = await questions.duplicate(q.id);
                toast(t("bank.duplicated"));
                onOpen(copy.id, "draft");
              } catch (err) {
                setError(err);
              }
            }}
          >
            {t("bank.duplicate")}
          </button>
        )}
        <span className="grow" />
        {!retired && (
          <button
            className="btn"
            disabled={busy || (!dirty && q !== null)}
            onClick={async () => {
              const saved = await save();
              if (saved) {
                toast(t("admin.saved"));
                onSaved(saved);
              }
            }}
          >
            {t("admin.save")}
          </button>
        )}
        {q && draft && (
          <button
            className="btn btn-success"
            disabled={busy}
            onClick={async () => {
              if (dirty && !(await save())) return;
              await run(() => questions.approve(q.id), t("bank.approved"), "next");
            }}
          >
            {t("bank.approve_next")}
            <Icon name="arrowRight" size={18} />
          </button>
        )}
      </div>
      {retiring && q && (
        <Confirm
          title={t("bank.retire_title", { number: q.number })}
          confirmLabel={t("bank.retire")}
          onCancel={() => setRetiring(false)}
          onConfirm={() => {
            setRetiring(false);
            void run(() => questions.retire(q.id), t("bank.retired_done"), undefined).then((ok) => ok && onOpen(q.id, "retired"));
          }}
        >
          <p>{t("bank.retire_text")}</p>
        </Confirm>
      )}
    </section>
  );
}

function toComparable(f: Form) {
  return { ...f, options: f.options.map(({ key: _key, ...o }) => o) };
}

// --- AI drafting --------------------------------------------------------------------------------

function AiDraftDialog({ lessons, onClose, onDone }: { lessons: LessonAdmin[]; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const errorText = useErrorText();
  const usable = lessons.filter((l) => l.draft ?? l.published);
  const [lessonId, setLessonId] = useState(usable[0]?.id ?? 0);
  const [source, setSource] = useState<"transcript" | "text">("transcript");
  const [text, setText] = useState("");
  const [count, setCount] = useState(10);
  const [types, setTypes] = useState<Set<"single" | "multiple" | "ordering">>(new Set(["single", "multiple", "ordering"]));
  const [pdf, setPdf] = useState(false);
  const [reference, setReference] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<unknown>(null);
  const lesson = usable.find((l) => l.id === lessonId);
  const version = lesson?.draft ?? lesson?.published ?? null;
  const hasPdf = Boolean(version?.pdf_uz_url || version?.pdf_ru_url);

  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const id = window.setInterval(async () => {
      try {
        const next = await ai.job(job.id);
        setJob(next);
        if (next.status === "done") onDone();
      } catch {
        /* keep polling */
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [job, onDone]);

  const start = async () => {
    if (!version) return;
    setError(null);
    try {
      setJob(
        await ai.draft(version.id, {
          source,
          text: source === "text" ? text : null,
          count,
          types: [...types],
          include_lesson_pdf: pdf && hasPdf,
          reference_text: reference.trim() || null,
        }),
      );
    } catch (err) {
      setError(err);
    }
  };

  const result = job?.result as { created?: number; dropped?: number; problems?: Record<string, number>; error?: { code: string; params?: Record<string, unknown> } } | null;
  const running = job !== null && (job.status === "queued" || job.status === "running");
  return (
    <Modal
      title={t("bank.ai_title")}
      onClose={onClose}
      wide
      footer={
        <>
          <button className="btn" onClick={onClose}>
            {job?.status === "done" ? t("app.close") : t("app.cancel")}
          </button>
          {!job && (
            <button className="btn btn-primary" disabled={!version || types.size === 0 || (source === "text" && !text.trim())} onClick={start}>
              <Icon name="sparkle" size={18} />
              {t("bank.ai_start")}
            </button>
          )}
        </>
      }
    >
      <p className="notice">{t("bank.ai_note")}</p>
      {!job ? (
        <>
          <div className="grid-2">
            <Field label={t("bank.lesson")} htmlFor="ai-lesson">
              <select id="ai-lesson" className="input" value={lessonId} onChange={(e) => setLessonId(Number(e.target.value))}>
                {usable.map((l, i) => (
                  <option key={l.id} value={l.id}>
                    {i + 1}. {pick(l, "title", lang)}
                    {l.draft ? ` · ${t("content.draft_in", { release: l.draft.release_code })}` : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("bank.ai_count")} htmlFor="ai-count">
              <input id="ai-count" type="number" className="input" min={1} max={30} value={count} onChange={(e) => setCount(Math.max(1, Math.min(30, Number(e.target.value))))} />
            </Field>
          </div>
          <div className="row wrap">
            <label className="check">
              <input type="radio" name="ai-source" checked={source === "transcript"} onChange={() => setSource("transcript")} />
              {t("bank.ai_source_transcript")}
            </label>
            <label className="check">
              <input type="radio" name="ai-source" checked={source === "text"} onChange={() => setSource("text")} />
              {t("bank.ai_source_text")}
            </label>
          </div>
          {source === "text" && (
            <textarea className="input textarea" rows={6} value={text} maxLength={60000} onChange={(e) => setText(e.target.value)} placeholder={t("bank.ai_text_hint")} />
          )}
          <div className="row wrap">
            <span className="small strong">{t("bank.ai_types")}</span>
            {(["single", "multiple", "ordering"] as const).map((x) => (
              <label key={x} className="check">
                <input
                  type="checkbox"
                  checked={types.has(x)}
                  onChange={() => {
                    const next = new Set(types);
                    if (next.has(x)) next.delete(x);
                    else next.add(x);
                    setTypes(next);
                  }}
                />
                {t(`bank.type.${x}`)}
              </label>
            ))}
          </div>
          <label className={`check ${hasPdf ? "" : "disabled"}`}>
            <input type="checkbox" checked={pdf && hasPdf} disabled={!hasPdf} onChange={(e) => setPdf(e.target.checked)} />
            {t(hasPdf ? "bank.ai_pdf" : "bank.ai_no_pdf")}
          </label>
          <Field label={t("bank.ai_reference")} htmlFor="ai-ref">
            <textarea id="ai-ref" className="input textarea" rows={3} value={reference} maxLength={60000} onChange={(e) => setReference(e.target.value)} />
          </Field>
          {error !== null && <div className="notice notice-danger">{errorText(error)}</div>}
        </>
      ) : running ? (
        <div className="center-box" role="status">
          <div className="spinner" />
          <span>{t("bank.ai_running")}</span>
        </div>
      ) : job.status === "done" ? (
        <div className="notice notice-success stack-sm">
          <strong>{t("bank.ai_done", { created: result?.created ?? 0, dropped: result?.dropped ?? 0 })}</strong>
          {result?.problems && Object.keys(result.problems).length > 0 && (
            <span className="small">
              {Object.entries(result.problems)
                .map(([k, v]) => `${t(`bank.ai_drop.${k}`, { defaultValue: k })}: ${v}`)
                .join(" · ")}
            </span>
          )}
        </div>
      ) : (
        <div className="notice notice-danger">
          {result?.error ? errorText(new ApiError(0, result.error.code, result.error.params ?? {})) : t("errors.generic")}
        </div>
      )}
    </Modal>
  );
}
