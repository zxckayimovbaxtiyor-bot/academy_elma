import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { learner } from "../../api/learner";
import { ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { minutes } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";

/** FAQ videos: open to everyone, untracked, no test. */
export function Faq() {
  const { t } = useTranslation();
  const lang = useLang();
  const { data, error, loading, reload } = useApi(() => learner.faq(), []);
  if (loading && !data) return <PageLoader />;
  if (error || !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div className="stack-lg narrow-wide">
      <div className="page-head">
        <h1>{t("faq.title")}</h1>
        <p className="muted">{t("faq.subtitle")}</p>
      </div>
      {data.length === 0 ? (
        <div className="card card-pad muted">{t("faq.empty")}</div>
      ) : (
        <ol className="card faq-list">
          {data.map((l) => (
            <li key={l.id}>
              <Link to={`/faq/${l.id}`} className="faq-row">
                <span className="faq-play" aria-hidden="true">
                  <Icon name="play" size={18} />
                </span>
                <span className="grow strong">{pick(l, "title", lang)}</span>
                <span className="muted small">{t("common.min", { count: minutes(l.duration_s) })}</span>
                <Icon name="right" />
              </Link>
            </li>
          ))}
        </ol>
      )}
      <div className="card-soft card-pad">{t("faq.contact")}</div>
    </div>
  );
}
