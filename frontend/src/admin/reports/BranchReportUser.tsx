import "../../styles/admin.css";

import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { csvUrl, reports } from "../../api/admin";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";
import { LearnerDetailView } from "./ReportUser";

export default function BranchReportUser() {
  const { t } = useTranslation();
  const lang = useLang();
  const id = Number(useParams().userId);
  const { data, error, loading, reload } = useApi(() => reports.user(id), [id]);
  if (loading && !data) return <PageLoader />;
  if (error || !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div className="stack">
      <Breadcrumbs items={[{ label: t("nav.reports"), to: "/reports" }, { label: data.full_name }]} />
      <LearnerDetailView
        d={data}
        actions={
          <a className="btn" href={csvUrl(`/reports/users/${id}`, { lang })}>
            <Icon name="download" size={18} />
            {t("reports.csv")}
          </a>
        }
      />
    </div>
  );
}
