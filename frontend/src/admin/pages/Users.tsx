import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { content, reference, users } from "../../api/admin";
import type { AuditEntry, ImportCommit, ImportProblem, ImportReport, ModuleAdmin, UserDetail, UserRow } from "../../api/adminTypes";
import type { AccessRole } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { ErrorLine, ErrorState, PageLoader, useErrorText } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { dateTime, initials } from "../../lib/format";
import { name, pick, useLang } from "../../lib/lang";
import { saveText } from "../../lib/transfer";
import { useApi } from "../../lib/useApi";
import { FilePick, PageHead, useToast } from "../ui";

const ROLES: AccessRole[] = ["learner", "branch_head", "methodologist", "admin"];

/** Staff list, HR CSV import and one person's page (mockup 10). */
export function Users() {
  const { t } = useTranslation();
  const selected = Number(useParams().userId) || null;
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [listKey, setListKey] = useState(0);

  const validate = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      setReport(await users.importValidate(file));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack-lg">
      <PageHead
        title={t("users.title")}
        subtitle={t("users.subtitle")}
        actions={
          <>
            <a className="btn" href={users.templateUrl}>
              <Icon name="download" size={18} />
              {t("users.template")}
            </a>
            <FilePick accept=".csv,text/csv" onFile={validate} className="btn btn-primary" disabled={busy}>
              <Icon name="upload" size={18} />
              {busy ? t("app.loading") : t("users.import")}
            </FilePick>
          </>
        }
      />
      <ErrorLine error={error} />
      {report && (
        <ImportCard
          report={report}
          onClose={() => setReport(null)}
          onDone={() => setListKey((k) => k + 1)}
        />
      )}
      <div className={selected ? "a-split" : ""}>
        <UserList key={listKey} selected={selected} />
        {selected && <UserPanel key={selected} id={selected} onChanged={() => setListKey((k) => k + 1)} />}
      </div>
    </div>
  );
}

// --- CSV import ---------------------------------------------------------------------------------

export function useProblemText() {
  const { t } = useTranslation();
  return (p: ImportProblem) => t(`import.${p.code}`, { ...p.params, defaultValue: p.code });
}

function ImportCard({ report, onClose, onDone }: { report: ImportReport; onClose: () => void; onDone: () => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const problem = useProblemText();
  const [done, setDone] = useState<ImportCommit | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const commit = async () => {
    setBusy(true);
    setError(null);
    try {
      setDone(await users.importCommit(report.import_id));
      onDone();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card card-pad stack">
      <div className="spread">
        <h2>
          {t("users.import_check")} · {report.filename}
        </h2>
        <div className="row wrap">
          <span className="chip">{t("users.rows", { count: report.total_rows })}</span>
          <span className="chip chip-success">{t("users.valid_rows", { count: report.valid_rows })}</span>
          {report.error_rows > 0 && <span className="chip chip-danger">{t("users.error_rows", { count: report.error_rows })}</span>}
          <button className="btn btn-ghost btn-small" onClick={onClose} aria-label={t("app.close")}>
            <Icon name="close" size={18} />
          </button>
        </div>
      </div>
      {done ? (
        <div className="stack">
          <div className="notice notice-success">
            <Icon name="check" />
            <span>
              {t("users.import_done", { created: done.created, updated: done.updated, unchanged: done.unchanged })}
              {done.skipped.length > 0 && ` ${t("users.import_skipped", { count: done.skipped.length })}`}
            </span>
          </div>
          {done.created > 0 && (
            <div className="notice notice-warning stack-sm">
              <strong>{t("users.passwords_title")}</strong>
              <span>{t("users.passwords_text")}</span>
              <div>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    saveText(`passwords_import_${done.import_id}.csv`, done.temp_passwords_csv);
                    setSaved(true);
                  }}
                >
                  <Icon name="download" size={18} />
                  {t("users.passwords_download")}
                </button>
                {saved && <span className="muted small"> {t("users.passwords_saved")}</span>}
              </div>
            </div>
          )}
        </div>
      ) : (
        <>
          {report.errors.length > 0 && (
            <div className="table-card bordered scroll-y">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t("users.col_row")}</th>
                    <th>employee_id</th>
                    <th>{t("users.col_problem")}</th>
                  </tr>
                </thead>
                <tbody>
                  {report.errors.slice(0, 300).map((e, i) => (
                    <tr key={i}>
                      <td className="num">{e.row}</td>
                      <td className="mono">{e.employee_id ?? "—"}</td>
                      <td className="text-danger">{problem(e)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted small">
            {t("users.import_rule", { create: report.to_create, update: report.to_update })}
          </p>
          <ErrorLine error={error} />
          <div className="row wrap a-actions">
            {report.error_rows > 0 && (
              <a className="btn" href={users.errorsUrl(report.import_id, lang)}>
                <Icon name="download" size={18} />
                {t("users.errors_download")}
              </a>
            )}
            <button className="btn btn-primary" disabled={busy || report.valid_rows === 0} onClick={commit}>
              {t("users.import_commit", { count: report.valid_rows })}
            </button>
          </div>
        </>
      )}
    </section>
  );
}

// --- list ---------------------------------------------------------------------------------------

function UserStatus({ u }: { u: UserRow }) {
  const { t } = useTranslation();
  if (!u.is_active) return <span className="chip">{t("users.inactive")}</span>;
  if (u.locked_until && new Date(u.locked_until) > new Date()) return <span className="chip chip-danger">{t("users.locked")}</span>;
  if (u.must_change_password) return <span className="chip chip-warning">{t("users.temp_password")}</span>;
  return <span className="chip chip-success">{t("users.active")}</span>;
}

function UserList({ selected }: { selected: number | null }) {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const [q, setQ] = useState(search.get("q") ?? "");
  const branches = useApi(() => reference.branches(), []);
  const filters = {
    q: search.get("q") ?? undefined,
    branch_id: search.get("branch") ? Number(search.get("branch")) : undefined,
    access_role: (search.get("role") as AccessRole | null) ?? undefined,
    is_active: search.get("active") === null ? undefined : search.get("active") === "true",
    page: Number(search.get("page") ?? 1),
    page_size: 50,
  };
  const list = useApi(() => users.list(filters), [JSON.stringify(filters)]);
  const set = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(search);
    for (const [k, v] of Object.entries(changes)) {
      if (v === undefined || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("page" in changes)) next.delete("page");
    setSearch(next, { replace: true });
  };
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.page_size)) : 1;
  const open = (id: number) => navigate({ pathname: `/admin/users/${id}`, search: search.toString() });

  return (
    <section className="card table-card">
      <div className="card-head row wrap list-filters">
        <h2 className="grow">{t("users.list")}</h2>
        <form
          className="search"
          onSubmit={(e) => {
            e.preventDefault();
            set({ q: q.trim() || undefined });
          }}
        >
          <Icon name="search" size={18} />
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("users.search")} />
        </form>
        <select className="input" value={search.get("branch") ?? ""} onChange={(e) => set({ branch: e.target.value })}>
          <option value="">{t("users.all_branches")}</option>
          {(branches.data ?? []).map((b) => (
            <option key={b.id} value={b.id}>
              {b.code} · {name(b, lang)}
            </option>
          ))}
        </select>
        <select className="input" value={search.get("role") ?? ""} onChange={(e) => set({ role: e.target.value })}>
          <option value="">{t("users.all_roles")}</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`roles.${r}`)}
            </option>
          ))}
        </select>
        <select className="input" value={search.get("active") ?? ""} onChange={(e) => set({ active: e.target.value })}>
          <option value="">{t("users.all_statuses")}</option>
          <option value="true">{t("users.active")}</option>
          <option value="false">{t("users.inactive")}</option>
        </select>
      </div>
      {list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : !list.data ? (
        <PageLoader />
      ) : list.data.items.length === 0 ? (
        <p className="card-pad muted">{t("users.empty")}</p>
      ) : (
        <>
          <table className="table table-click">
            <thead>
              <tr>
                <th>{t("users.col_person")}</th>
                <th>{t("users.col_branch_role")}</th>
                <th>{t("users.col_lang")}</th>
                <th>{t("users.col_status")}</th>
                <th>{t("users.col_last_seen")}</th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((u) => (
                <tr key={u.id} className={u.id === selected ? "selected" : ""} tabIndex={0} onClick={() => open(u.id)} onKeyDown={(e) => e.key === "Enter" && open(u.id)}>
                  <td>
                    <strong>{u.full_name}</strong>
                    <span className="cell-sub mono">{u.employee_id}</span>
                  </td>
                  <td>
                    {u.branch ? name(u.branch, lang) : <span className="muted">—</span>}
                    <span className="cell-sub">{u.job_role ? name(u.job_role, lang) : t(`roles.${u.access_role}`)}</span>
                  </td>
                  <td className="strong">{u.preferred_language.toUpperCase()}</td>
                  <td>
                    <UserStatus u={u} />
                  </td>
                  <td className="muted">{u.last_seen_at ? dateTime(u.last_seen_at) : t("reports.never")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {pages > 1 && (
            <div className="pager">
              <button className="btn btn-small" disabled={filters.page <= 1} onClick={() => set({ page: String(filters.page - 1) })}>
                <Icon name="left" size={16} />
              </button>
              <span className="muted small">{t("reports.page", { page: filters.page, pages, total: list.data.total })}</span>
              <button className="btn btn-small" disabled={filters.page >= pages} onClick={() => set({ page: String(filters.page + 1) })}>
                <Icon name="right" size={16} />
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

// --- one person ---------------------------------------------------------------------------------

type Action = "" | "password" | "role" | "active" | `reset:${number}`;

function UserPanel({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const { me } = useAuth();
  const toast = useToast();
  const errorText = useErrorText();
  const detail = useApi(() => users.get(id), [id]);
  const modules = useApi(() => content.modules(), []);
  const [action, setAction] = useState<Action>("");
  const [reason, setReason] = useState("");
  const [role, setRole] = useState<AccessRole>("learner");
  const [temp, setTemp] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  if (detail.loading && !detail.data) return <aside className="card card-pad"><PageLoader /></aside>;
  if (detail.error || !detail.data) return <aside className="card card-pad"><ErrorState error={detail.error} onRetry={detail.reload} /></aside>;
  const u: UserDetail = detail.data;
  const self = me?.id === u.id;
  const testModules = (modules.data ?? []).filter((m) => m.type !== "faq");

  const run = async () => {
    setBusy(true);
    setError(null);
    setTemp(null);
    try {
      if (action === "password") {
        setTemp((await users.resetPassword(u.id)).temp_password);
      } else if (action === "role") {
        await users.patch(u.id, { access_role: role });
        toast(t("users.done_role"));
      } else if (action === "active") {
        await users.patch(u.id, { is_active: !u.is_active });
        toast(t(u.is_active ? "users.done_deactivated" : "users.done_activated"));
      } else if (action.startsWith("reset:")) {
        await users.resetAttempts(u.id, Number(action.slice(6)), reason);
        toast(t("users.done_reset"));
        setReason("");
      }
      detail.reload();
      onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  const needsReason = action.startsWith("reset:");
  return (
    <aside className="card card-pad stack user-panel">
      <div className="row">
        <span className="avatar big">{initials(u.full_name)}</span>
        <div className="grow">
          <h3>{u.full_name}</h3>
          <span className="muted small">
            {[u.employee_id, u.branch ? name(u.branch, lang) : "", u.job_role ? name(u.job_role, lang) : "", u.preferred_language.toUpperCase()]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
      </div>
      <div className="row wrap">
        <span className="chip chip-primary">{t(`roles.${u.access_role}`)}</span>
        <UserStatus u={u} />
      </div>

      {u.learning.modules.length > 0 && (
        <ul className="kv">
          {u.learning.modules.map((m) => (
            <li key={m.module_id}>
              <span>{pick(m, "title", lang)}</span>
              <ModuleLine m={m} />
            </li>
          ))}
        </ul>
      )}
      {u.learning.modules.length > 0 && (
        <Link className="link-strong small" to={`/admin/reports/users/${u.id}`}>
          {t("users.open_report")}
          <Icon name="arrowRight" size={16} />
        </Link>
      )}

      <hr className="divider" />
      <h4>{t("users.actions")}</h4>
      <select
        className="input"
        value={action}
        aria-label={t("users.action")}
        onChange={(e) => {
          const next = e.target.value as Action;
          setAction(next);
          setTemp(null);
          if (next === "role") setRole(u.access_role);
        }}
      >
        <option value="">{t("users.choose_action")}</option>
        {testModules.map((m: ModuleAdmin) => (
          <option key={m.id} value={`reset:${m.id}`}>
            {t("users.action_reset", { module: pick(m, "title", lang) })}
          </option>
        ))}
        {!self && <option value="password">{t("users.action_password")}</option>}
        {!self && <option value="role">{t("users.action_role")}</option>}
        {!self && <option value="active">{t(u.is_active ? "users.action_deactivate" : "users.action_activate")}</option>}
      </select>
      {action === "role" && (
        <select className="input" value={role} onChange={(e) => setRole(e.target.value as AccessRole)} aria-label={t("users.action_role")}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`roles.${r}`)}
            </option>
          ))}
        </select>
      )}
      {needsReason && (
        <div className="field">
          <label htmlFor="reset-reason">{t("users.reason")}</label>
          <textarea id="reset-reason" className="input textarea" rows={3} value={reason} maxLength={1000}
            placeholder={t("users.reason_hint")} onChange={(e) => setReason(e.target.value)} />
        </div>
      )}
      {error !== null && <div className="notice notice-danger">{errorText(error)}</div>}
      {temp && (
        <div className="notice notice-warning stack-sm">
          <strong>{t("users.temp_shown_once")}</strong>
          <code className="temp">{temp}</code>
        </div>
      )}
      <button className="btn btn-primary btn-block" disabled={busy || !action || (needsReason && !reason.trim())} onClick={run}>
        {t("users.run")}
      </button>

      <hr className="divider" />
      <h4>{t("users.audit")}</h4>
      {u.audit.length === 0 ? (
        <p className="muted small">{t("users.audit_empty")}</p>
      ) : (
        <ul className="audit">
          {u.audit.map((e, i) => (
            <li key={i}>
              <span className="muted">{dateTime(e.at)}</span> · <AuditLine e={e} modules={modules.data ?? []} />
              {e.reason && <div className="muted small">«{e.reason}»</div>}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

function ModuleLine({ m }: { m: UserDetail["learning"]["modules"][number] }) {
  const { t } = useTranslation();
  if (m.state === "certified") return <span className="status-text success">{t("users.m_certified")}</span>;
  if (m.state === "recert_required") return <span className="status-text warning">{t("users.m_recert")}</span>;
  if (m.last_attempt_status && m.last_attempt_status !== "in_progress" && m.attempts_used > 0) {
    return <span className="status-text danger">{t("users.m_failed", { used: m.attempts_used, max: m.attempts_max })}</span>;
  }
  if (m.state === "in_progress") {
    return <span className="status-text">{t("users.m_lessons", { done: m.lessons_completed, total: m.lessons_total })}</span>;
  }
  return <span className="status-text muted">{t(m.locked ? "state.locked" : "state.not_started")}</span>;
}

function AuditLine({ e, modules }: { e: AuditEntry; modules: ModuleAdmin[] }) {
  const { t } = useTranslation();
  const lang = useLang();
  const d = e.data;
  const module = modules.find((m) => m.id === d.module_id);
  const title = module ? pick(module, "title", lang) : "";
  const params: Record<string, unknown> = { ...d, module: title };
  if (e.action === "user.role_changed") {
    params.from = t(`roles.${String(d.from)}`);
    params.to = t(`roles.${String(d.to)}`);
  }
  if (e.action === "user.created") params.source = t(`audit.source.${String(d.source ?? "admin")}`, { defaultValue: String(d.source ?? "") });
  if (e.action === "user.updated" && d.changes && typeof d.changes === "object") params.fields = Object.keys(d.changes).join(", ");
  if (e.action === "cert.issued") params.kind = t(d.kind === "operator" ? "certs.kind_operator" : "certs.kind_module");
  return <>{t(`audit.${e.action.replace(/\./g, "_")}`, { ...params, defaultValue: e.action })}</>;
}
