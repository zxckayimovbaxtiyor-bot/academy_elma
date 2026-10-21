import { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";

import { content, releases } from "../../api/admin";
import type { LessonAdmin, ModuleAdmin, ReleaseDetail, ReleaseRow } from "../../api/adminTypes";
import { Confirm } from "../../components/Dialog";
import { ErrorLine, ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { date } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";
import { Field, Modal, PageHead, useToast } from "../ui";

const TRANSITIONS = [0, 7, 14, 30];

/** Elma365 releases: mark changed lessons, see the impact, check, publish (mockup 11). */
export function Releases() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const selected = Number(useParams().releaseId) || null;
  const list = useApi(() => releases.list(), []);
  const [creating, setCreating] = useState(false);
  const draftExists = (list.data ?? []).some((r) => r.status === "draft");
  const current = (list.data ?? []).find((r) => r.status === "published");

  useEffect(() => {
    if (!selected && list.data?.length) navigate(`/admin/releases/${list.data[0].id}`, { replace: true });
  }, [selected, list.data, navigate]);

  return (
    <div className="stack-lg">
      <PageHead
        title={t("releases.title")}
        subtitle={t("releases.subtitle")}
        actions={
          <button className="btn btn-primary" disabled={draftExists} title={draftExists ? t("releases.one_draft") : undefined} onClick={() => setCreating(true)}>
            <Icon name="plus" size={18} />
            {t("releases.new")}
          </button>
        }
      />
      {list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : !list.data ? (
        <PageLoader />
      ) : list.data.length === 0 ? (
        <div className="card card-pad muted">{t("releases.empty")}</div>
      ) : (
        <div className="a-master">
          <ol className="card timeline">
            {list.data.map((r: ReleaseRow) => {
              const kind = r.status === "draft" ? "draft" : r.id === current?.id ? "current" : "archive";
              return (
                <li key={r.id} className={`tl-${kind} ${r.id === selected ? "on" : ""}`}>
                  <Link to={`/admin/releases/${r.id}`}>
                    <span className="tl-dot" aria-hidden="true" />
                    <span className="grow">
                      <span className="spread">
                        <strong>{r.code}</strong>
                        <span className={`chip ${kind === "draft" ? "chip-warning" : kind === "current" ? "chip-success" : ""}`}>
                          {t(`releases.kind.${kind}`)}
                        </span>
                      </span>
                      <span className="muted small">{r.notes || t("releases.lessons", { count: r.lessons_count })}</span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ol>
          {selected && (
            <ReleasePanel
              key={selected}
              id={selected}
              onChanged={list.reload}
              onDeleted={() => {
                list.reload();
                navigate("/admin/releases", { replace: true });
              }}
            />
          )}
        </div>
      )}
      {creating && (
        <ReleaseForm
          onClose={() => setCreating(false)}
          onSaved={(r) => {
            setCreating(false);
            list.reload();
            navigate(`/admin/releases/${r.id}`);
          }}
        />
      )}
    </div>
  );
}

function ReleaseForm({ onClose, onSaved }: { onClose: () => void; onSaved: (r: ReleaseRow) => void }) {
  const { t } = useTranslation();
  const [code, setCode] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<unknown>(null);
  const save = async () => {
    setError(null);
    try {
      onSaved(await releases.create(code.trim(), notes.trim()));
    } catch (err) {
      setError(err);
    }
  };
  return (
    <Modal
      title={t("releases.new")}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            {t("app.cancel")}
          </button>
          <button className="btn btn-primary" disabled={!code.trim()} onClick={save}>
            {t("admin.save")}
          </button>
        </>
      }
    >
      <Field label={t("releases.code")} hint={t("releases.code_hint")} htmlFor="r-code">
        <input id="r-code" className="input mono" value={code} maxLength={32} onChange={(e) => setCode(e.target.value)} placeholder="2026.12" autoFocus />
      </Field>
      <Field label={t("releases.notes")} htmlFor="r-notes">
        <input id="r-notes" className="input" value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)} placeholder={t("releases.notes_hint")} />
      </Field>
      <ErrorLine error={error} />
    </Modal>
  );
}

function ReleasePanel({ id, onChanged, onDeleted }: { id: number; onChanged: () => void; onDeleted: () => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const toast = useToast();
  const detail = useApi(() => releases.get(id), [id]);
  const tree = useApi(async () => {
    const modules = await content.modules();
    const lessons = await Promise.all(modules.map((m) => content.lessons(m.id)));
    return modules.map((m, i) => ({ module: m, lessons: lessons[i] }));
  }, [id]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [publishing, setPublishing] = useState(false);

  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} />;
  if (!detail.data) return <PageLoader />;
  const r: ReleaseDetail = detail.data;
  const draft = r.status === "draft";
  const inRelease = new Map(r.lessons.map((l) => [l.lesson_id, l]));

  const act = async (fn: () => Promise<unknown>, message?: string): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      if (message) toast(message);
      detail.reload();
      tree.reload();
      onChanged();
      return true;
    } catch (err) {
      setError(err);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const toggle = (l: LessonAdmin) =>
    act(() => (inRelease.has(l.id) ? releases.unmark(r.id, l.id) : releases.markChanged(r.id, l.id)));

  return (
    <div className="stack">
      <section className="card card-pad stack">
        <div className="row wrap">
          <h2>{t("releases.changed_title", { code: r.code })}</h2>
          <span className={`chip ${draft ? "chip-warning" : "chip-success"}`}>{t(draft ? "releases.kind.draft" : "releases.published_on", { date: date(r.published_at) })}</span>
          <span className="grow" />
          {draft && r.lessons.length === 0 && (
            <button className="btn btn-small btn-danger-ghost" disabled={busy} onClick={() => act(() => releases.remove(r.id)).then((ok) => ok && onDeleted())}>
              <Icon name="trash" size={16} />
              {t("releases.delete")}
            </button>
          )}
        </div>
        <p className="muted">{t(draft ? "releases.mark_hint" : "releases.published_hint")}</p>
        {r.notes && <p className="small">{r.notes}</p>}
        <ErrorLine error={error} />
        {!tree.data ? (
          <PageLoader />
        ) : (
          tree.data.map(({ module, lessons }: { module: ModuleAdmin; lessons: LessonAdmin[] }) => {
            const impact = r.impact.find((i) => i.module_id === module.id);
            const inModule = r.lessons.filter((x) => x.module_id === module.id).length;
            const listed = lessons.filter((l) => l.published || inRelease.has(l.id));
            if (!draft && !impact && inModule === 0) return null;
            if (listed.length === 0) return null;
            return (
              <div key={module.id} className={`rel-module ${impact ? "touched" : ""}`}>
                <div className="spread">
                  <strong>{pick(module, "title", lang)}</strong>
                  <span className="muted small">
                    {impact
                      ? t("releases.module_impact", { changed: impact.changed_lessons + impact.added_lessons, total: impact.total_lessons, certs: impact.certificates })
                      : inModule > 0
                        ? t("releases.lessons", { count: inModule })
                        : t("releases.no_change")}
                  </span>
                </div>
                <ul className="rel-lessons">
                  {listed.map((l, i) => {
                    const item = inRelease.get(l.id);
                    const added = item?.change === "added";
                    return (
                      <li key={l.id}>
                        <label className={!draft || added ? "disabled" : ""}>
                          <input type="checkbox" className="box" checked={Boolean(item)} disabled={!draft || added || busy} onChange={() => toggle(l)} />
                          {i + 1}. {pick(l, "title", lang)}
                          {added && <span className="chip chip-primary chip-gap">{t("releases.new_lesson")}</span>}
                        </label>
                        {item && item.problems.length > 0 && draft && (
                          <span className="rel-problems">
                            {item.problems.map((p) => t(`release.problem.${p}`)).join(" · ")}{" "}
                            <Link to={`/admin/content/lessons/${l.id}`}>{t("releases.open_lesson")}</Link>
                          </span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })
        )}
      </section>

      {draft && (
        <div className="grid-2 align-start">
          <section className="card card-pad stack">
            <h3>{t("releases.impact")}</h3>
            {r.impact.length === 0 ? (
              <p className="muted small">{t("releases.impact_none")}</p>
            ) : (
              r.impact.map((i) => (
                <div key={i.module_id} className="impact-box warn">
                  <strong className="big-num">{i.learners}</strong>
                  <span>
                    <Trans
                      i18nKey="releases.impact_text"
                      count={i.learners}
                      values={{ module: pick(i, "title", lang), lessons: i.changed_lessons + i.added_lessons }}
                      components={{ b: <strong /> }}
                    />
                  </span>
                </div>
              ))
            )}
            <div className="impact-box ok">
              <strong className="big-num">0</strong>
              <span>{t("releases.impact_others")}</span>
            </div>
            <Field label={t("releases.transition")} htmlFor="r-transition">
              <select
                id="r-transition"
                className="input"
                value={r.transition_days}
                disabled={busy}
                onChange={(e) => act(() => releases.patch(r.id, { transition_days: Number(e.target.value) }), t("admin.saved"))}
              >
                {[...new Set([...TRANSITIONS, r.transition_days])].sort((a, b) => a - b).map((d) => (
                  <option key={d} value={d}>
                    {d === 0 ? t("releases.transition_none") : t("releases.transition_days", { count: d })}
                  </option>
                ))}
              </select>
            </Field>
          </section>
          <Checklist r={r} busy={busy} onPublish={() => setPublishing(true)} />
        </div>
      )}
      {publishing && (
        <Confirm
          title={t("releases.publish_title", { code: r.code })}
          confirmLabel={t("releases.publish")}
          busy={busy}
          onCancel={() => setPublishing(false)}
          onConfirm={() => act(() => releases.publish(r.id), t("releases.published")).then(() => setPublishing(false))}
        >
          <p>{t("releases.publish_text", { count: r.impact.reduce((s, i) => s + i.certificates, 0) })}</p>
        </Confirm>
      )}
    </div>
  );
}

function Checklist({ r, busy, onPublish }: { r: ReleaseDetail; busy: boolean; onPublish: () => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const total = r.lessons.length;
  const videos = r.lessons.filter((l) => l.version.video?.status === "ready").length;
  const subtitles = r.lessons.reduce((s, l) => s + (l.version.vtt_uz_url ? 1 : 0) + (l.version.vtt_ru_url ? 1 : 0), 0);
  const pending = r.impact.reduce((s, i) => s + i.questions_pending, 0);
  const pools = r.module_problems.filter((p) => p.code === "pool_too_small");
  const items = [
    { ok: total > 0 && videos === total, title: t("releases.check_videos"), sub: t("releases.check_videos_sub", { done: videos, total }) },
    { ok: total > 0 && subtitles === total * 2, title: t("releases.check_subtitles"), sub: t("releases.check_files", { done: subtitles, total: total * 2 }) },
    { ok: pending === 0, title: t("releases.check_questions"), sub: pending ? t("releases.check_pending", { count: pending }) : t("releases.check_ok") },
    {
      ok: pools.length === 0,
      title: t("releases.check_pool"),
      sub:
        pools.length === 0
          ? r.impact
              .filter((i) => i.pool_need !== null)
              .map((i) => `${pick(i, "title", lang)}: ${i.pool_have} / ${i.pool_need}`)
              .join(" · ") || t("releases.check_ok")
          : pools
              .map((p) => {
                const i = r.impact.find((x) => x.module_id === p.module_id);
                return `${i ? pick(i, "title", lang) : p.module_id}: ${String(p.params.have)} / ${String(p.params.need)}`;
              })
              .join(" · "),
    },
  ];
  return (
    <section className="card card-pad stack">
      <h3>{t("releases.checklist")}</h3>
      <ul className="checklist">
        {items.map((x) => (
          <li key={x.title} className={x.ok ? "ok" : "bad"}>
            <span className="check-dot" aria-hidden="true">
              <Icon name={x.ok ? "check" : "alert"} size={16} />
            </span>
            <span>
              <strong>{x.title}</strong>
              <span className="muted small">{x.sub}</span>
            </span>
          </li>
        ))}
      </ul>
      <button className="btn btn-primary btn-block btn-lg" disabled={!r.ready || busy} onClick={onPublish}>
        {t("releases.publish")}
      </button>
      <p className="muted small center">{t("releases.publish_rule")}</p>
    </section>
  );
}
