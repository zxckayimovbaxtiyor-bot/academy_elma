import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";

import { csvUrl, reports } from "../../api/admin";
import type { LearnerDetail, ModuleProgress } from "../../api/adminTypes";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { CertBadge, ModuleBadge } from "../../components/Status";
import { date, dateTime, pct } from "../../lib/format";
import { name, pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";
import { PageHead } from "../ui";

/** One learner's modules, attempts and certificates (report drill-down). */
export function LearnerDetailView({ d, actions }: { d: LearnerDetail; actions?: React.ReactNode }) {
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <div className="stack-lg">
      <PageHead
        title={d.full_name}
        subtitle={[d.employee_id, name(d.branch, lang), name(d.job_role, lang), d.wave ? pick(d.wave, "name", lang) : ""]
          .filter(Boolean)
          .join(" · ")}
        actions={actions}
      />
      <div className="row wrap">
        <ModuleBadge state={d.status} />
        {d.overdue && <span className="chip chip-danger">{t("reports.overdue")}</span>}
        <span className="chip">
          {t("certs.operator_title")}: {t(`cert_status.${d.operator.status}`)}
          {d.operator.number && ` · ${d.operator.number}`}
        </span>
      </div>
      <section className="card table-card">
        <table className="table">
          <thead>
            <tr>
              <th>{t("reports.module")}</th>
              <th>{t("reports.col_status")}</th>
              <th className="num">{t("reports.col_lessons")}</th>
              <th className="num">{t("reports.col_attempts")}</th>
              <th>{t("reports.col_last_attempt")}</th>
              <th>{t("reports.col_certificate")}</th>
            </tr>
          </thead>
          <tbody>
            {d.modules.map((m: ModuleProgress) => (
              <tr key={m.module_id}>
                <td>
                  <strong>{pick(m, "title", lang)}</strong>
                  <span className="cell-sub">{m.code}</span>
                </td>
                <td>
                  <ModuleBadge state={m.state} locked={m.locked} />
                </td>
                <td className="num">
                  {m.lessons_completed} / {m.lessons_total}
                </td>
                <td className="num">
                  {m.attempts_used} / {m.attempts_max}
                </td>
                <td>
                  {m.last_attempt_at ? (
                    <>
                      {pct(m.last_score_pct) || "—"}
                      <span className="cell-sub">
                        {dateTime(m.last_attempt_at)}
                        {m.last_attempt_status === "in_progress" && ` · ${t("result.in_progress")}`}
                      </span>
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  {m.certificate ? (
                    <>
                      <CertBadge status={m.certificate.status} due={m.certificate.recert_due_at} />
                      <span className="cell-sub mono">
                        {m.certificate.number} · {date(m.certificate.issued_at)}
                        {m.certificate.release && ` · ${m.certificate.release}`}
                      </span>
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export function ReportUser() {
  const { t } = useTranslation();
  const lang = useLang();
  const id = Number(useParams().userId);
  const { data, error, loading, reload } = useApi(() => reports.user(id), [id]);
  if (loading && !data) return <PageLoader />;
  if (error || !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div className="stack">
      <Breadcrumbs items={[{ label: t("admin.nav.reports"), to: "/admin/reports?tab=users" }, { label: data.full_name }]} />
      <LearnerDetailView
        d={data}
        actions={
          <>
            <a className="btn" href={csvUrl(`/reports/users/${id}`, { lang })}>
              <Icon name="download" size={18} />
              {t("reports.csv")}
            </a>
            <Link className="btn btn-primary" to={`/admin/users/${id}`}>
              {t("reports.open_user")}
            </Link>
          </>
        }
      />
    </div>
  );
}
