import { useTranslation } from "react-i18next";

import { learner } from "../../api/learner";
import { ErrorState, PageLoader } from "../../components/Feedback";
import { PathList } from "../../components/PathList";
import { useApi } from "../../lib/useApi";

export function Courses() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useApi(() => learner.modules(), []);
  if (loading && !data) return <PageLoader />;
  if (error || !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div className="stack-lg">
      <div className="page-head">
        <h1>{t("courses.title")}</h1>
        <p className="muted">{t("home.path_hint")}</p>
      </div>
      {data.length === 0 && <div className="notice">{t("home.no_modules")}</div>}
      <PathList modules={data} />
    </div>
  );
}
