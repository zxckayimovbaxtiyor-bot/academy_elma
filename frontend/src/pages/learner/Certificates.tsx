import { useTranslation } from "react-i18next";

import { learner } from "../../api/learner";
import type { Certificate } from "../../api/types";
import { ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { CertBadge } from "../../components/Status";
import { date, pct } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";

/** The learner's certificates: current ones first, then the superseded ones. */
export function Certificates() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useApi(() => learner.certificates(), []);
  if (loading && !data) return <PageLoader />;
  if (error || !data) return <ErrorState error={error} onRetry={reload} />;
  const current = data.filter((c) => c.superseded_at === null);
  const previous = data.filter((c) => c.superseded_at !== null);
  return (
    <div className="stack-lg">
      <div className="page-head">
        <h1>{t("certs.title")}</h1>
        <p className="muted">{t("certs.subtitle")}</p>
      </div>
      {data.length === 0 && (
        <div className="card card-pad center-box">
          <Icon name="certificate" size={40} />
          <p className="muted">{t("certs.empty")}</p>
        </div>
      )}
      {current.length > 0 && (
        <div className="cert-grid">
          {current.map((c) => (
            <CertificateCard key={c.number} c={c} />
          ))}
        </div>
      )}
      {previous.length > 0 && (
        <section className="stack">
          <h2>{t("certs.previous")}</h2>
          <div className="cert-grid">
            {previous.map((c) => (
              <CertificateCard key={c.number} c={c} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function CertificateCard({ c }: { c: Certificate }) {
  const { t } = useTranslation();
  const lang = useLang();
  const operator = c.kind === "operator";
  const first = c.modules[0];
  const title = operator ? t("certs.operator_title") : first ? pick(first, "title", lang) : c.number;
  // In-app link to the verification page, whatever host the QR code points at.
  const verify = new URL(c.verify_url, window.location.origin);
  return (
    <article className={`card cert-card ${operator ? "operator" : ""} ${c.superseded_at ? "old" : ""}`}>
      <div className="cert-card-head">
        <span className="cert-icon">
          <Icon name="certificate" size={26} />
        </span>
        <div className="grow">
          <p className="caps">{t(operator ? "certs.kind_operator" : "certs.kind_module")}</p>
          <h3>{title}</h3>
        </div>
        <CertBadge status={c.status} due={c.superseded_at ? null : c.recert_due_at} />
      </div>
      <dl className="cert-facts">
        <div>
          <dt>{t("certs.number")}</dt>
          <dd className="num">{c.number}</dd>
        </div>
        <div>
          <dt>{t("certs.issued")}</dt>
          <dd>{date(c.issued_at)}</dd>
        </div>
        {c.score_pct !== null && (
          <div>
            <dt>{t("certs.score")}</dt>
            <dd>{pct(c.score_pct)}</dd>
          </div>
        )}
        {!operator && first?.release && (
          <div>
            <dt>{t("certs.release")}</dt>
            <dd>{first.release}</dd>
          </div>
        )}
        {c.recert_due_at && !c.superseded_at && (
          <div>
            <dt>{t("certs.recert_due")}</dt>
            <dd>{date(c.recert_due_at)}</dd>
          </div>
        )}
        {c.superseded_at && (
          <div>
            <dt>{t("certs.superseded")}</dt>
            <dd>{date(c.superseded_at)}</dd>
          </div>
        )}
      </dl>
      {operator && (
        <ul className="cert-modules">
          {c.modules.map((m) => (
            <li key={m.code}>
              <Icon name="check" size={16} />
              <span>
                {pick(m, "title", lang)}
                {m.release && <span className="muted"> · {m.release}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <div className="row wrap">
        <a className="btn btn-primary" href={c.pdf_url} download>
          <Icon name="download" size={18} />
          {t("certs.download")}
        </a>
        <a className="btn" href={verify.pathname + verify.search} target="_blank" rel="noopener">
          {t("certs.verify")}
          <Icon name="external" size={16} />
        </a>
      </div>
    </article>
  );
}
