import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { content, questions } from "../../api/admin";
import type { LessonAdmin, ModuleAdmin, ModuleInput, ModulePatch, QuestionAdmin, Version } from "../../api/adminTypes";
import type { ModuleType } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { ErrorLine, ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { clock } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { isAdmin } from "../../lib/roles";
import { useApi } from "../../lib/useApi";
import { Field, Modal, PageHead, useToast } from "../ui";

const TYPE_CHIP: Record<ModuleType, string> = { core: "chip-core", product: "chip-primary", faq: "" };

/** Modules, their lessons and test settings (mockup 8). */
export function Content() {
  const { t } = useTranslation();
  const lang = useLang();
  const { me } = useAuth();
  const navigate = useNavigate();
  const selected = Number(useParams().moduleId) || null;
  const modules = useApi(() => content.modules(), []);
  const [creating, setCreating] = useState(false);
  const admin = isAdmin(me);

  useEffect(() => {
    if (!selected && modules.data?.length) navigate(`/admin/content/modules/${modules.data[0].id}`, { replace: true });
  }, [selected, modules.data, navigate]);

  const move = async (index: number, by: number) => {
    const list = [...(modules.data ?? [])];
    const [item] = list.splice(index, 1);
    list.splice(index + by, 0, item);
    await content.reorderModules(list.map((m) => m.id)).catch(() => undefined);
    modules.reload();
  };

  return (
    <div className="stack-lg">
      <PageHead
        title={t("content.title")}
        subtitle={t("content.subtitle")}
        actions={
          admin && (
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              <Icon name="plus" size={18} />
              {t("content.new_module")}
            </button>
          )
        }
      />
      {modules.error ? (
        <ErrorState error={modules.error} onRetry={modules.reload} />
      ) : !modules.data ? (
        <PageLoader />
      ) : (
        <div className="a-master">
          <section className="card side-list">
            <div className="card-head">
              <h3>{t("content.modules")}</h3>
            </div>
            <ol>
              {modules.data.map((m, i) => (
                <li key={m.id} className={m.id === selected ? "on" : ""}>
                  <Link to={`/admin/content/modules/${m.id}`}>
                    <span className="grow">
                      <strong>{pick(m, "title", lang)}</strong>
                      <span className="muted small">
                        {t("content.module_meta", { lessons: m.lessons_total })}
                        {m.release_code && ` · ${t("path.release", { release: m.release_code })}`}
                      </span>
                    </span>
                    <span className={`chip type-chip ${TYPE_CHIP[m.type]}`}>{t(`content.type.${m.type}`)}</span>
                  </Link>
                  {admin && (
                    <span className="reorder">
                      <button className="btn btn-ghost btn-icon" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t("q.move_up")}>
                        <Icon name="up" size={16} />
                      </button>
                      <button className="btn btn-ghost btn-icon" disabled={i === modules.data!.length - 1} onClick={() => move(i, 1)} aria-label={t("q.move_down")}>
                        <Icon name="down" size={16} />
                      </button>
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </section>
          {selected && modules.data.find((m) => m.id === selected) && (
            <ModulePanel key={selected} module={modules.data.find((m) => m.id === selected)!} onChanged={modules.reload} />
          )}
        </div>
      )}
      {creating && (
        <ModuleForm
          onClose={() => setCreating(false)}
          onSaved={(m) => {
            setCreating(false);
            modules.reload();
            navigate(`/admin/content/modules/${m.id}`);
          }}
        />
      )}
    </div>
  );
}

function ModuleForm({ onClose, onSaved }: { onClose: () => void; onSaved: (m: ModuleAdmin) => void }) {
  const { t } = useTranslation();
  const [form, setForm] = useState<ModuleInput>({ code: "", qprefix: "", type: "product", title_uz: "", title_ru: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onSaved(await content.createModule({ ...form, code: form.code.toUpperCase(), qprefix: form.qprefix.toUpperCase() }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={t("content.new_module")}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            {t("app.cancel")}
          </button>
          <button className="btn btn-primary" disabled={busy || !form.code || !form.qprefix || !form.title_uz || !form.title_ru} onClick={save}>
            {t("admin.save")}
          </button>
        </>
      }
    >
      <div className="grid-2">
        <Field label={t("admin.title_uz")} htmlFor="m-uz">
          <input id="m-uz" className="input" value={form.title_uz} onChange={(e) => setForm({ ...form, title_uz: e.target.value })} />
        </Field>
        <Field label={t("admin.title_ru")} htmlFor="m-ru">
          <input id="m-ru" className="input" value={form.title_ru} onChange={(e) => setForm({ ...form, title_ru: e.target.value })} />
        </Field>
      </div>
      <div className="grid-3">
        <Field label={t("content.code")} hint={t("content.code_hint")} htmlFor="m-code">
          <input id="m-code" className="input mono" value={form.code} maxLength={32} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="UZCARD" />
        </Field>
        <Field label={t("content.qprefix")} hint={t("content.qprefix_hint")} htmlFor="m-prefix">
          <input id="m-prefix" className="input mono" value={form.qprefix} maxLength={8} onChange={(e) => setForm({ ...form, qprefix: e.target.value })} placeholder="U" />
        </Field>
        <Field label={t("content.type_label")} htmlFor="m-type">
          <select id="m-type" className="input" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as ModuleType })}>
            {(["product", "core", "faq"] as ModuleType[]).map((x) => (
              <option key={x} value={x}>
                {t(`content.type_long.${x}`)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <ErrorLine error={error} />
    </Modal>
  );
}

function ModulePanel({ module, onChanged }: { module: ModuleAdmin; onChanged: () => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const toast = useToast();
  const navigate = useNavigate();
  const lessons = useApi(() => content.lessons(module.id), [module.id]);
  const bank = useApi(
    () => (module.type === "faq" ? Promise.resolve(null) : Promise.all([questions.list(module.id), questions.pool(module.id)])),
    [module.id],
  );
  const [adding, setAdding] = useState(false);
  const [renaming, setRenaming] = useState(false);

  const move = async (index: number, by: number) => {
    const list = [...(lessons.data ?? [])];
    const [item] = list.splice(index, 1);
    list.splice(index + by, 0, item);
    await content.reorderLessons(module.id, list.map((l) => l.id)).catch(() => undefined);
    lessons.reload();
  };

  const counts = new Map<number, { approved: number; drafts: number }>();
  for (const q of (bank.data?.[0] ?? []) as QuestionAdmin[]) {
    const c = counts.get(q.lesson_id) ?? { approved: 0, drafts: 0 };
    if (q.status === "approved") c.approved++;
    if (q.status === "draft") c.drafts++;
    counts.set(q.lesson_id, c);
  }

  return (
    <div className="stack">
      <section className="card">
        <div className="card-head row wrap">
          <h2>{pick(module, "title", lang)}</h2>
          <span className={`chip ${TYPE_CHIP[module.type]}`}>{t(`content.type_long.${module.type}`)}</span>
          {module.type === "product" && <span className="chip">{t("content.requires_core")}</span>}
          <span className="grow" />
          <button className="btn btn-small" onClick={() => setRenaming(true)}>
            {t("content.rename")}
          </button>
          <button className="btn btn-small" onClick={() => setAdding(true)}>
            <Icon name="plus" size={16} />
            {t("content.add_lesson")}
          </button>
        </div>
        {lessons.error ? (
          <ErrorState error={lessons.error} onRetry={lessons.reload} />
        ) : !lessons.data ? (
          <PageLoader />
        ) : lessons.data.length === 0 ? (
          <p className="card-pad muted">{t("content.no_lessons")}</p>
        ) : (
          <div className="scroll-x">
            <table className="table table-click">
              <thead>
                <tr>
                  <th aria-label={t("content.order")} />
                  <th>{t("content.col_lesson")}</th>
                  <th>{t("content.col_duration")}</th>
                  <th>{t("content.col_video")}</th>
                  <th>{t("content.col_subtitles")}</th>
                  {module.type !== "faq" && <th>{t("content.col_questions")}</th>}
                  <th>{t("content.col_release")}</th>
                </tr>
              </thead>
              <tbody>
                {lessons.data.map((l: LessonAdmin, i) => {
                  const v = l.draft ?? l.published;
                  const c = counts.get(l.id);
                  const open = () => navigate(`/admin/content/lessons/${l.id}`);
                  return (
                    <tr key={l.id} tabIndex={0} onClick={open} onKeyDown={(e) => e.key === "Enter" && open()}>
                      <td onClick={(e) => e.stopPropagation()}>
                        <span className="reorder col">
                          <button className="btn btn-ghost btn-icon" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t("q.move_up")}>
                            <Icon name="up" size={16} />
                          </button>
                          <button className="btn btn-ghost btn-icon" disabled={i === lessons.data!.length - 1} onClick={() => move(i, 1)} aria-label={t("q.move_down")}>
                            <Icon name="down" size={16} />
                          </button>
                        </span>
                      </td>
                      <td>
                        <strong>
                          {i + 1}. {l.title_uz}
                        </strong>
                        <span className="cell-sub">
                          {i + 1}. {l.title_ru}
                        </span>
                      </td>
                      <td className="num">{v?.video?.duration_s ? clock(v.video.duration_s) : "—"}</td>
                      <td>
                        <VideoChip v={v} />
                      </td>
                      <td>
                        <SubtitleMarks v={v} />
                      </td>
                      {module.type !== "faq" && (
                        <td className="small">
                          {c ? (
                            <>
                              {c.approved} <Icon name="check" size={14} />
                              {c.drafts > 0 && <span className="cell-sub">{t("content.drafts", { count: c.drafts })}</span>}
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                      )}
                      <td className="small">
                        {l.published?.release_code ?? "—"}
                        {l.draft && <span className="cell-sub">{t("content.draft_in", { release: l.draft.release_code })}</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {module.type !== "faq" && (
        <TestSettings
          module={module}
          pool={bank.data?.[1] ?? null}
          onSaved={() => {
            toast(t("admin.saved"));
            onChanged();
            bank.reload();
          }}
        />
      )}
      {adding && (
        <LessonForm
          moduleId={module.id}
          onClose={() => setAdding(false)}
          onSaved={(l) => {
            setAdding(false);
            lessons.reload();
            onChanged();
            navigate(`/admin/content/lessons/${l.id}`);
          }}
        />
      )}
      {renaming && (
        <RenameModule
          module={module}
          onClose={() => setRenaming(false)}
          onSaved={() => {
            setRenaming(false);
            toast(t("admin.saved"));
            onChanged();
          }}
        />
      )}
    </div>
  );
}

export function VideoChip({ v }: { v: Version | null }) {
  const { t } = useTranslation();
  const video = v?.video;
  if (!video) return <span className="chip chip-danger">{t("content.video_missing")}</span>;
  if (video.status === "ready") return <span className="chip chip-success">{t("content.video_ready")}</span>;
  if (video.status === "failed") return <span className="chip chip-danger">{t("content.video_failed")}</span>;
  return <span className="chip chip-primary">{t("content.video_processing", { pct: video.progress_pct })}</span>;
}

export function SubtitleMarks({ v }: { v: Version | null }) {
  return (
    <span className="small nowrap">
      UZ {v?.vtt_uz_url ? "✓" : "—"} · RU {v?.vtt_ru_url ? "✓" : "—"}
    </span>
  );
}

function TestSettings({ module, pool, onSaved }: { module: ModuleAdmin; pool: { approved_active: number; required: number } | null; onSaved: () => void }) {
  const { t } = useTranslation();
  const initial = {
    test_question_count: module.test_question_count,
    test_pass_pct: module.test_pass_pct,
    test_time_limit_min: module.test_time_limit_min,
    test_max_attempts: module.test_max_attempts,
    test_cooldown_hours: module.test_cooldown_hours,
  };
  const [form, setForm] = useState(initial);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const changed = (Object.keys(initial) as (keyof typeof initial)[]).some((k) => form[k] !== initial[k]);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await content.patchModule(module.id, form as ModulePatch);
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const input = (key: keyof typeof initial, min: number, max: number) => (
    <input
      type="number"
      className="input"
      min={min}
      max={max}
      value={form[key]}
      onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
    />
  );
  const need = form.test_question_count * 3;
  return (
    <section className="card card-pad stack">
      <div className="spread">
        <h3>{t("content.test_settings")}</h3>
        {module.test_published_at ? (
          <span className="chip chip-success">{t("content.test_published")}</span>
        ) : (
          <span className="chip">{t("content.test_not_published")}</span>
        )}
      </div>
      <div className="grid-3">
        <Field label={t("content.questions_n")}>{input("test_question_count", 1, 100)}</Field>
        <Field label={t("content.pass_pct")}>{input("test_pass_pct", 1, 100)}</Field>
        <Field label={t("content.time_min")}>{input("test_time_limit_min", 1, 240)}</Field>
        <Field label={t("content.attempts")}>{input("test_max_attempts", 1, 20)}</Field>
        <Field label={t("content.cooldown_h")}>{input("test_cooldown_hours", 0, 720)}</Field>
        <Field label={t("content.bank_needed")}>
          <span className={`input input-static ${pool && pool.approved_active < need ? "warn" : "ok"}`}>
            {pool ? `${pool.approved_active} / ${need}` : "…"}
          </span>
        </Field>
      </div>
      <p className="muted small">{t("content.bank_rule")}</p>
      <ErrorLine error={error} />
      <div className="row a-actions">
        <Link className="btn" to={`/admin/questions/${module.id}`}>
          {t("content.to_bank")}
        </Link>
        <button className="btn btn-primary" disabled={!changed || busy} onClick={save}>
          {t("admin.save")}
        </button>
      </div>
    </section>
  );
}

function LessonForm({ moduleId, onClose, onSaved }: { moduleId: number; onClose: () => void; onSaved: (l: LessonAdmin) => void }) {
  const { t } = useTranslation();
  const [uz, setUz] = useState("");
  const [ru, setRu] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onSaved(await content.createLesson(moduleId, uz.trim(), ru.trim()));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={t("content.add_lesson")}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            {t("app.cancel")}
          </button>
          <button className="btn btn-primary" disabled={busy || !uz.trim() || !ru.trim()} onClick={save}>
            {t("admin.save")}
          </button>
        </>
      }
    >
      <p className="muted small">{t("content.lesson_in_draft")}</p>
      <Field label={t("admin.title_uz")} htmlFor="l-uz">
        <input id="l-uz" className="input" value={uz} onChange={(e) => setUz(e.target.value)} autoFocus />
      </Field>
      <Field label={t("admin.title_ru")} htmlFor="l-ru">
        <input id="l-ru" className="input" value={ru} onChange={(e) => setRu(e.target.value)} />
      </Field>
      <ErrorLine error={error} />
    </Modal>
  );
}

function RenameModule({ module, onClose, onSaved }: { module: ModuleAdmin; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const [uz, setUz] = useState(module.title_uz);
  const [ru, setRu] = useState(module.title_ru);
  const [error, setError] = useState<unknown>(null);
  const save = async () => {
    try {
      await content.patchModule(module.id, { title_uz: uz.trim(), title_ru: ru.trim() });
      onSaved();
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      title={t("content.rename")}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            {t("app.cancel")}
          </button>
          <button className="btn btn-primary" disabled={!uz.trim() || !ru.trim()} onClick={save}>
            {t("admin.save")}
          </button>
        </>
      }
    >
      <Field label={t("admin.title_uz")} htmlFor="r-uz">
        <input id="r-uz" className="input" value={uz} onChange={(e) => setUz(e.target.value)} />
      </Field>
      <Field label={t("admin.title_ru")} htmlFor="r-ru">
        <input id="r-ru" className="input" value={ru} onChange={(e) => setRu(e.target.value)} />
      </Field>
      <ErrorLine error={error} />
    </Modal>
  );
}
