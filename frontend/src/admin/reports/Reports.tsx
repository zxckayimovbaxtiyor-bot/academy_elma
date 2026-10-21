import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { content, csvUrl, reference, reports, waves } from "../../api/admin";
import type { BranchReportRow, ReportFilters, Summary } from "../../api/adminTypes";
import type { ModuleState } from "../../api/types";
import { ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { dateTime } from "../../lib/format";
import { name, pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";
import { PageHead } from "../ui";

const STATES: ModuleState[] = ["certified", "in_progress", "not_started", "recert_required"];
const num = (v: string | null) => (v ? Number(v) : undefined);

/**
 * Readiness report (mockup 6). `branch` scope is the branch head's view: the server
 * limits every number to their own branch, so the filters for other branches go away.
 */
export function ReportView({ scope }: { scope: "admin" | "branch" }) {
  const { t } = useTranslation();
  const lang = useLang();
  const [search, setSearch] = useSearchParams();
  const admin = scope === "admin";
  const f: ReportFilters = admin
    ? {
        wave_id: num(search.get("wave")),
        region_id: num(search.get("region")),
        branch_id: num(search.get("branch")),
        module_id: num(search.get("module")),
        job_role_id: num(search.get("role")),
      }
    : {};
  const key = JSON.stringify(f);
  const tab = admin && search.get("tab") !== "users" ? "branches" : "users";

  const refs = useApi(
    () =>
      admin
        ? Promise.all([waves.list(), reference.regions(), content.modules(), reference.jobRoles(), reference.branches()])
        : Promise.resolve(null),
    [admin],
  );
  const summary = useApi(() => reports.summary(f), [key]);

  const set = (changes: Record<string, string | number | undefined>) => {
    const next = new URLSearchParams(search);
    for (const [k, v] of Object.entries(changes)) {
      if (v === undefined || v === "") next.delete(k);
      else next.set(k, String(v));
    }
    next.delete("page");
    setSearch(next, { replace: true });
  };

  const wavesList = refs.data?.[0] ?? [];
  const regions = refs.data?.[1] ?? [];
  const modules = refs.data?.[2] ?? [];
  const roles = refs.data?.[3] ?? [];
  const branches = refs.data?.[4] ?? [];
  const branchName = f.branch_id ? branches.find((b) => b.id === f.branch_id) : undefined;
  const exportHref =
    tab === "branches"
      ? csvUrl("/reports/branches", { ...f, lang })
      : csvUrl("/reports/users", { ...f, status: search.get("status"), overdue: search.get("overdue"), q: search.get("q"), lang });

  return (
    <div className="stack-lg">
      <PageHead
        title={t(admin ? "reports.title" : "reports.branch_title")}
        subtitle={t("reports.subtitle")}
        actions={
          <>
            <a className="btn" href={exportHref}>
              <Icon name="download" size={18} />
              {t("reports.csv")}
            </a>
            {admin && (
              <a className="btn btn-primary" href={reports.accessListUrl({ wave_id: f.wave_id, branch_id: f.branch_id, lang })}>
                <Icon name="lock" size={18} />
                {t("reports.access_list")}
              </a>
            )}
          </>
        }
      />

      {admin && (
        <div className="card card-pad filters">
          <label>
            <span>{t("reports.wave")}</span>
            <select className="input" value={f.wave_id ?? ""} onChange={(e) => set({ wave: e.target.value })}>
              <option value="">{t("reports.all_waves")}</option>
              {wavesList.map((w) => (
                <option key={w.id} value={w.id}>
                  {pick(w, "name", lang)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>{t("reports.region")}</span>
            <select className="input" value={f.region_id ?? ""} onChange={(e) => set({ region: e.target.value })}>
              <option value="">{t("reports.all")}</option>
              {regions.map((r) => (
                <option key={r.id} value={r.id}>
                  {name(r, lang)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>{t("reports.module")}</span>
            <select className="input" value={f.module_id ?? ""} onChange={(e) => set({ module: e.target.value })}>
              <option value="">{t("reports.all_assigned")}</option>
              {modules
                .filter((m) => m.type !== "faq")
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {pick(m, "title", lang)}
                  </option>
                ))}
            </select>
          </label>
          <label>
            <span>{t("reports.role")}</span>
            <select className="input" value={f.job_role_id ?? ""} onChange={(e) => set({ role: e.target.value })}>
              <option value="">{t("reports.all")}</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {name(r, lang)}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {summary.error ? (
        <ErrorState error={summary.error} onRetry={summary.reload} />
      ) : summary.data ? (
        <Kpis s={summary.data} onPick={(status, overdue) => set({ tab: "users", status, overdue: overdue ? "true" : undefined })} />
      ) : (
        <PageLoader />
      )}

      {admin && (
        <div className="tabs a-tabs" role="tablist">
          <button role="tab" aria-selected={tab === "branches"} onClick={() => set({ tab: undefined })}>
            {t("reports.by_branch")}
          </button>
          <button role="tab" aria-selected={tab === "users"} onClick={() => set({ tab: "users" })}>
            {t("reports.by_learner")}
          </button>
          {branchName && (
            <span className="chip chip-primary filter-chip">
              {name(branchName, lang)}
              <button aria-label={t("app.close")} onClick={() => set({ branch: undefined })}>
                <Icon name="close" size={14} />
              </button>
            </span>
          )}
        </div>
      )}

      {tab === "branches" ? (
        <BranchTable f={f} onPick={(id) => set({ branch: id, tab: "users" })} />
      ) : (
        <LearnerTable f={f} scope={scope} />
      )}
    </div>
  );
}

function Kpis({ s, onPick }: { s: Summary; onPick: (status?: ModuleState, overdue?: boolean) => void }) {
  const { t } = useTranslation();
  const tiles: { key: string; value: string | number; sub: string; tone: string; status?: ModuleState; overdue?: boolean }[] = [
    { key: "total", value: s.total, sub: t("reports.kpi_branches", { count: s.branches }), tone: "" },
    { key: "certified", value: `${s.certified_pct}%`, sub: t("reports.kpi_people", { count: s.certified }), tone: "success", status: "certified" },
    { key: "in_progress", value: s.in_progress, sub: t("reports.kpi_in_progress"), tone: "primary", status: "in_progress" },
    { key: "not_started", value: s.not_started, sub: t("reports.kpi_not_started"), tone: "danger", status: "not_started" },
    {
      key: "recert_required",
      value: s.recert_required,
      sub: s.latest_release ? t("reports.kpi_release", { release: s.latest_release }) : "",
      tone: "warning",
      status: "recert_required",
    },
    { key: "overdue", value: s.overdue, sub: t("reports.kpi_overdue"), tone: "danger", overdue: true },
  ];
  return (
    <div className="kpis">
      {tiles.map((x) => (
        <button key={x.key} className={`card kpi kpi-${x.tone}`} onClick={() => onPick(x.status, x.overdue)}>
          <span>{t(`reports.kpi.${x.key}`)}</span>
          <strong className="num">{x.value}</strong>
          <span className="muted">{x.sub}</span>
        </button>
      ))}
    </div>
  );
}

const READY_TONE = { ready: "chip-success", at_risk: "chip-warning", not_ready: "chip-danger" } as const;

function BranchTable({ f, onPick }: { f: ReportFilters; onPick: (branchId: number) => void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const rows = useApi(() => reports.branches(f), [JSON.stringify(f)]);
  if (rows.error) return <ErrorState error={rows.error} onRetry={rows.reload} />;
  if (!rows.data) return <PageLoader />;
  return (
    <section className="card table-card">
      <div className="card-head spread">
        <h2>{t("reports.by_branch")}</h2>
        <span className="muted small">{t("reports.ready_rule")}</span>
      </div>
      {rows.data.length === 0 ? (
        <p className="card-pad muted">{t("reports.empty")}</p>
      ) : (
        <table className="table table-click">
          <thead>
            <tr>
              <th>{t("reports.col_branch")}</th>
              <th className="num">{t("reports.col_learners")}</th>
              <th>{t("reports.col_certified")}</th>
              <th className="num">{t("reports.col_not_started")}</th>
              <th className="num">{t("reports.col_recert")}</th>
              <th className="num">{t("reports.col_overdue")}</th>
              <th>{t("reports.col_readiness")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.data.map((r: BranchReportRow) => (
              <tr key={r.branch.id} onClick={() => onPick(r.branch.id)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && onPick(r.branch.id)}>
                <td>
                  <strong>{name(r.branch, lang)}</strong>
                  <span className="cell-sub">{name(r.region, lang)}</span>
                </td>
                <td className="num">{r.total}</td>
                <td>
                  <div className="bar-cell">
                    <span className={`bar bar-${r.readiness}`}>
                      <span style={{ width: `${r.certified_pct}%` }} />
                    </span>
                    <strong className="num">{r.certified_pct}%</strong>
                  </div>
                </td>
                <td className="num">{r.not_started}</td>
                <td className="num">{r.recert_required}</td>
                <td className="num">{r.overdue}</td>
                <td>
                  <span className={`chip ${READY_TONE[r.readiness]}`}>{t(`reports.readiness.${r.readiness}`)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

const STATE_TONE: Record<ModuleState, string> = {
  certified: "chip-success",
  in_progress: "chip-primary",
  not_started: "",
  recert_required: "chip-warning",
};

function LearnerTable({ f, scope }: { f: ReportFilters; scope: "admin" | "branch" }) {
  const { t } = useTranslation();
  const lang = useLang();
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const [q, setQ] = useState(search.get("q") ?? "");
  const status = (search.get("status") as ModuleState | null) ?? undefined;
  const overdue = search.get("overdue") === "true" ? true : undefined;
  const page = Number(search.get("page") ?? 1);
  const filters = { ...f, status, overdue, q: search.get("q") ?? undefined, page, page_size: 50 };
  const rows = useApi(() => reports.users(filters), [JSON.stringify(filters)]);
  const set = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(search);
    for (const [k, v] of Object.entries(changes)) {
      if (v === undefined || v === "") next.delete(k);
      else next.set(k, v);
    }
    setSearch(next, { replace: true });
  };
  const base = scope === "admin" ? "/admin/reports/users" : "/reports/users";
  const pages = rows.data ? Math.max(1, Math.ceil(rows.data.total / rows.data.page_size)) : 1;
  return (
    <section className="card table-card">
      <div className="card-head row wrap">
        <h2 className="grow">{t("reports.by_learner")}</h2>
        <form
          className="search"
          onSubmit={(e) => {
            e.preventDefault();
            set({ q: q.trim() || undefined, page: undefined });
          }}
        >
          <Icon name="search" size={18} />
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("reports.search")} />
        </form>
        <select className="input" value={status ?? ""} onChange={(e) => set({ status: e.target.value, page: undefined })}>
          <option value="">{t("reports.all_statuses")}</option>
          {STATES.map((s) => (
            <option key={s} value={s}>
              {t(`state.${s}`)}
            </option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={overdue === true} onChange={(e) => set({ overdue: e.target.checked ? "true" : undefined, page: undefined })} />
          {t("reports.only_overdue")}
        </label>
      </div>
      {rows.error ? (
        <ErrorState error={rows.error} onRetry={rows.reload} />
      ) : !rows.data ? (
        <PageLoader />
      ) : rows.data.items.length === 0 ? (
        <p className="card-pad muted">{t("reports.empty")}</p>
      ) : (
        <>
          <table className="table table-click">
            <thead>
              <tr>
                <th>{t("reports.col_learner")}</th>
                <th>{t("reports.col_branch_role")}</th>
                <th>{t("reports.col_status")}</th>
                <th className="num">{t("reports.col_modules")}</th>
                <th>{t("reports.col_last_seen")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.data.items.map((r) => (
                <tr key={r.user_id} tabIndex={0} onClick={() => navigate(`${base}/${r.user_id}`)} onKeyDown={(e) => e.key === "Enter" && navigate(`${base}/${r.user_id}`)}>
                  <td>
                    <Link to={`${base}/${r.user_id}`} onClick={(e) => e.stopPropagation()}>
                      <strong>{r.full_name}</strong>
                    </Link>
                    <span className="cell-sub mono">{r.employee_id}</span>
                  </td>
                  <td>
                    {name(r.branch, lang)}
                    <span className="cell-sub">{name(r.job_role, lang)}</span>
                  </td>
                  <td>
                    <span className={`chip ${STATE_TONE[r.status]}`}>{t(`state.${r.status}`)}</span>
                    {r.overdue && <span className="chip chip-danger chip-gap">{t("reports.overdue")}</span>}
                  </td>
                  <td className="num">
                    {r.modules_certified} / {r.modules_total}
                  </td>
                  <td className="muted">{r.last_seen_at ? dateTime(r.last_seen_at) : t("reports.never")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {pages > 1 && (
            <div className="pager">
              <button className="btn btn-small" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>
                <Icon name="left" size={16} />
              </button>
              <span className="muted small">{t("reports.page", { page, pages, total: rows.data.total })}</span>
              <button className="btn btn-small" disabled={page >= pages} onClick={() => set({ page: String(page + 1) })}>
                <Icon name="right" size={16} />
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export function Reports() {
  return <ReportView scope="admin" />;
}
