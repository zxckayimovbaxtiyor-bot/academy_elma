import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { reference, waves } from "../../api/admin";
import type { Assignment, BranchRef, WaveDetail, WaveInput, WaveRow } from "../../api/adminTypes";
import { ErrorLine, ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { ProgressBar } from "../../components/Status";
import { date } from "../../lib/format";
import { name, pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";
import { Field, Modal, PageHead, useToast } from "../ui";

const STATUS_TONE = { planned: "", active: "chip-primary", completed: "chip-success" } as const;

/** Waves: dates, branches and the role × module matrix (mockup 9). */
export function Waves() {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const selected = Number(useParams().waveId) || null;
  const list = useApi(() => waves.list(), []);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!selected && list.data?.length) navigate(`/admin/waves/${list.data[list.data.length - 1].id}`, { replace: true });
  }, [selected, list.data, navigate]);

  return (
    <div className="stack-lg">
      <PageHead
        title={t("waves.title")}
        subtitle={t("waves.subtitle")}
        actions={
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <Icon name="plus" size={18} />
            {t("waves.new")}
          </button>
        }
      />
      {list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : !list.data ? (
        <PageLoader />
      ) : list.data.length === 0 ? (
        <div className="card card-pad muted">{t("waves.empty")}</div>
      ) : (
        <div className="a-master">
          <ol className="wave-list">
            {list.data.map((w: WaveRow) => (
              <li key={w.id}>
                <button className={`card wave-card ${w.id === selected ? "on" : ""}`} onClick={() => navigate(`/admin/waves/${w.id}`)}>
                  <span className="spread">
                    <strong>{pick(w, "name", lang)}</strong>
                    <span className={`chip ${STATUS_TONE[w.status]}`}>{t(`waves.status.${w.status}`)}</span>
                  </span>
                  <span className="muted small">
                    {t("waves.counts", { branches: w.branches, learners: w.learners })} · {date(w.deadline)}
                  </span>
                  <ProgressBar value={w.certified_pct} tone={w.certified_pct === 100 ? "success" : undefined} />
                  <span className="muted small">
                    {w.status === "planned" ? t("waves.not_started") : t("waves.certified_pct", { pct: w.certified_pct })}
                  </span>
                </button>
              </li>
            ))}
          </ol>
          {selected && <WaveEditor key={selected} id={selected} onChanged={list.reload} />}
        </div>
      )}
      {creating && (
        <WaveForm
          onClose={() => setCreating(false)}
          onSaved={(w) => {
            setCreating(false);
            list.reload();
            navigate(`/admin/waves/${w.id}`);
          }}
        />
      )}
    </div>
  );
}

function WaveForm({ onClose, onSaved }: { onClose: () => void; onSaved: (w: WaveRow) => void }) {
  const { t } = useTranslation();
  const [form, setForm] = useState<WaveInput>({ name_uz: "", name_ru: "", training_start: "", deadline: "", go_live: "" });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof WaveInput) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      onSaved(await waves.create(form));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const ready = form.name_uz.trim() && form.name_ru.trim() && form.training_start && form.deadline && form.go_live;
  return (
    <Modal
      title={t("waves.new")}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            {t("app.cancel")}
          </button>
          <button className="btn btn-primary" disabled={!ready || busy} onClick={save}>
            {t("admin.save")}
          </button>
        </>
      }
    >
      <div className="grid-2">
        <Field label={t("admin.name_uz")} htmlFor="w-uz">
          <input id="w-uz" className="input" value={form.name_uz} onChange={set("name_uz")} placeholder="3-toʻlqin · Toshkent shahri" />
        </Field>
        <Field label={t("admin.name_ru")} htmlFor="w-ru">
          <input id="w-ru" className="input" value={form.name_ru} onChange={set("name_ru")} placeholder="3-я волна · г. Ташкент" />
        </Field>
      </div>
      <div className="grid-3">
        <Field label={t("waves.training_start")} htmlFor="w-start">
          <input id="w-start" type="date" className="input" value={form.training_start} onChange={set("training_start")} />
        </Field>
        <Field label={t("waves.deadline")} htmlFor="w-deadline">
          <input id="w-deadline" type="date" className="input" value={form.deadline} onChange={set("deadline")} />
        </Field>
        <Field label={t("waves.go_live")} htmlFor="w-live">
          <input id="w-live" type="date" className="input" value={form.go_live} onChange={set("go_live")} />
        </Field>
      </div>
      <p className="muted small">{t("waves.dates_rule")}</p>
      <ErrorLine error={error} />
    </Modal>
  );
}

function WaveEditor({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const toast = useToast();
  const detail = useApi(() => waves.get(id), [id]);
  const [form, setForm] = useState<WaveInput | null>(null);
  const [matrix, setMatrix] = useState<Set<string> | null>(null);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const w = detail.data;
    if (!w) return;
    setForm({ name_uz: w.name_uz, name_ru: w.name_ru, training_start: w.training_start, deadline: w.deadline, go_live: w.go_live });
    setMatrix(new Set(w.assignments.map((a) => `${a.job_role_id}:${a.module_id}`)));
  }, [detail.data]);

  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} />;
  if (!detail.data || !form || !matrix) return <PageLoader />;
  const w: WaveDetail = detail.data;
  const products = w.modules.filter((m) => m.type === "product");
  const core = w.modules.find((m) => m.type === "core");
  const original = new Set(w.assignments.map((a) => `${a.job_role_id}:${a.module_id}`));
  const matrixChanged = original.size !== matrix.size || [...matrix].some((k) => !original.has(k));
  const datesChanged = (Object.keys(form) as (keyof WaveInput)[]).some((k) => form[k] !== w[k]);

  const act = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      toast(message);
      detail.reload();
      onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const toggle = (roleId: number, moduleId: number) => {
    const key = `${roleId}:${moduleId}`;
    const next = new Set(matrix);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setMatrix(next);
  };
  const items: Assignment[] = [...matrix].map((k) => {
    const [job_role_id, module_id] = k.split(":").map(Number);
    return { job_role_id, module_id };
  });

  return (
    <div className="stack">
      <section className="card card-pad stack">
        <div className="row wrap">
          <h2>{pick(w, "name", lang)}</h2>
          <span className={`chip ${STATUS_TONE[w.status]}`}>{t(`waves.status.${w.status}`)}</span>
        </div>
        <div className="grid-2">
          <Field label={t("admin.name_uz")} htmlFor="e-uz">
            <input id="e-uz" className="input" value={form.name_uz} onChange={(e) => setForm({ ...form, name_uz: e.target.value })} />
          </Field>
          <Field label={t("admin.name_ru")} htmlFor="e-ru">
            <input id="e-ru" className="input" value={form.name_ru} onChange={(e) => setForm({ ...form, name_ru: e.target.value })} />
          </Field>
        </div>
        <div className="grid-3">
          <Field label={t("waves.training_start")} htmlFor="e-start">
            <input id="e-start" type="date" className="input" value={form.training_start} onChange={(e) => setForm({ ...form, training_start: e.target.value })} />
          </Field>
          <Field label={t("waves.deadline")} htmlFor="e-deadline">
            <input id="e-deadline" type="date" className="input" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} />
          </Field>
          <Field label={t("waves.go_live")} htmlFor="e-live">
            <input id="e-live" type="date" className="input" value={form.go_live} onChange={(e) => setForm({ ...form, go_live: e.target.value })} />
          </Field>
        </div>
        {datesChanged && (
          <div className="row a-actions">
            <button className="btn" onClick={() => setForm({ name_uz: w.name_uz, name_ru: w.name_ru, training_start: w.training_start, deadline: w.deadline, go_live: w.go_live })}>
              {t("app.cancel")}
            </button>
            <button className="btn btn-primary" disabled={busy} onClick={() => act(() => waves.patch(w.id, form), t("admin.saved"))}>
              {t("admin.save")}
            </button>
          </div>
        )}

        <div className="spread">
          <strong>{t("waves.branches", { count: w.branches, learners: w.learners })}</strong>
          <button className="btn btn-small" onClick={() => setPicking(true)}>
            <Icon name="plus" size={16} />
            {t("waves.add_branch")}
          </button>
        </div>
        {w.branch_list.length === 0 ? (
          <p className="muted small">{t("waves.no_branches")}</p>
        ) : (
          <div className="tags">
            {w.branch_list.map((b) => (
              <span key={b.id} className="tag">
                {name(b, lang)}
                <span className="muted"> · {b.learners}</span>
                <button
                  aria-label={t("waves.remove_branch", { branch: name(b, lang) })}
                  disabled={busy}
                  onClick={() =>
                    act(
                      () => waves.setBranches(w.id, w.branch_list.filter((x) => x.id !== b.id).map((x) => x.id)),
                      t("waves.branch_removed"),
                    )
                  }
                >
                  <Icon name="close" size={14} />
                </button>
              </span>
            ))}
          </div>
        )}
      </section>

      <section className="card table-card">
        <div className="card-head spread">
          <h2>{t("waves.matrix")}</h2>
          <span className="muted small">{t("waves.core_always")}</span>
        </div>
        <div className="scroll-x">
          <table className="table matrix">
            <thead>
              <tr>
                <th>{t("waves.role")}</th>
                {[...(core ? [core] : []), ...products].map((m) => (
                  <th key={m.id} className="center" title={pick(m, "title", lang)}>
                    {m.code}
                    <span className="th-sub">{pick(m, "title", lang)}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {w.roles.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{name(r, lang)}</strong>
                    <span className="cell-sub">{t("waves.learners", { count: r.learners })}</span>
                  </td>
                  {core && (
                    <td className="center">
                      <input type="checkbox" className="box" checked disabled aria-label={pick(core, "title", lang)} />
                    </td>
                  )}
                  {products.map((m) => (
                    <td key={m.id} className="center">
                      <input
                        type="checkbox"
                        className="box"
                        checked={matrix.has(`${r.id}:${m.id}`)}
                        onChange={() => toggle(r.id, m.id)}
                        aria-label={`${name(r, lang)} · ${pick(m, "title", lang)}`}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card-pad stack-sm">
          <p className="muted small">{t("waves.matrix_note")}</p>
          <ErrorLine error={error} />
          <div className="row a-actions">
            <button className="btn" disabled={!matrixChanged || busy} onClick={() => setMatrix(original)}>
              {t("app.cancel")}
            </button>
            <button className="btn btn-primary" disabled={!matrixChanged || busy} onClick={() => act(() => waves.setAssignments(w.id, items), t("admin.saved"))}>
              {t("admin.save")}
            </button>
          </div>
        </div>
      </section>
      {picking && (
        <BranchPicker
          wave={w}
          onClose={() => setPicking(false)}
          onSave={(ids) => {
            setPicking(false);
            void act(() => waves.setBranches(w.id, ids), t("waves.branches_saved"));
          }}
        />
      )}
    </div>
  );
}

/** Branches not yet in another wave (a branch goes live once). */
function BranchPicker({ wave, onClose, onSave }: { wave: WaveDetail; onClose: () => void; onSave: (ids: number[]) => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const data = useApi(async () => {
    const [branches, all] = await Promise.all([reference.branches(), waves.list()]);
    const others = await Promise.all(all.filter((x) => x.id !== wave.id).map((x) => waves.get(x.id)));
    const taken = new Map<number, string>();
    for (const o of others) for (const b of o.branch_list) taken.set(b.id, pick(o, "name", lang));
    return { branches, taken };
  }, [wave.id]);
  const [chosen, setChosen] = useState<Set<number>>(() => new Set(wave.branch_list.map((b) => b.id)));
  const [filter, setFilter] = useState("");
  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return (data.data?.branches ?? []).filter(
      (b: BranchRef) => !needle || b.code.toLowerCase().includes(needle) || name(b, lang).toLowerCase().includes(needle),
    );
  }, [data.data, filter, lang]);
  return (
    <Modal
      title={t("waves.add_branch")}
      onClose={onClose}
      wide
      footer={
        <>
          <span className="grow muted small">{t("waves.chosen", { count: chosen.size })}</span>
          <button className="btn" onClick={onClose}>
            {t("app.cancel")}
          </button>
          <button className="btn btn-primary" onClick={() => onSave([...chosen])}>
            {t("admin.save")}
          </button>
        </>
      }
    >
      <input className="input" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t("waves.branch_search")} autoFocus />
      {data.error ? (
        <ErrorState error={data.error} onRetry={data.reload} />
      ) : !data.data ? (
        <PageLoader />
      ) : (
        <ul className="pick-list">
          {shown.map((b) => {
            const other = data.data!.taken.get(b.id);
            return (
              <li key={b.id}>
                <label className={other ? "disabled" : ""}>
                  <input
                    type="checkbox"
                    className="box"
                    disabled={Boolean(other)}
                    checked={chosen.has(b.id)}
                    onChange={() => {
                      const next = new Set(chosen);
                      if (next.has(b.id)) next.delete(b.id);
                      else next.add(b.id);
                      setChosen(next);
                    }}
                  />
                  <span className="mono">{b.code}</span>
                  <span className="grow">{name(b, lang)}</span>
                  {other && <span className="muted small">{t("waves.in_wave", { wave: other })}</span>}
                </label>
              </li>
            );
          })}
        </ul>
      )}
    </Modal>
  );
}
