import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { learner } from "../../api/learner";
import type { CertStatus, Dashboard, DashboardCert, Resume } from "../../api/types";
import { ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { PathList } from "../../components/PathList";
import { date, minutes } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";

/** Home (mockup 1): wave banner, learning path, resume card, certificates, FAQ hint. */
export function Home() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useApi(() => learner.dashboard(), []);
  if (loading && !data) return <PageLoader />;
  if (error || !data) return <ErrorState error={error} onRetry={reload} />;
  return (
    <div className="stack-lg">
      <Banner d={data} />
      <div className="home-grid">
        <section>
          <div className="section-head">
            <h2>{t("home.path")}</h2>
            <span className="muted">{t("home.path_hint")}</span>
          </div>
          {data.path.length === 0 && <div className="notice">{t("home.no_modules")}</div>}
          <PathList modules={data.path} />
        </section>
        <aside className="stack">
          {data.resume && <ResumeCard r={data.resume} />}
          <CertificatesCard d={data} />
          <div className="card-soft card-pad stack-sm">
            <h3>{t("home.help_title")}</h3>
            <p className="muted">{t("home.help_text")}</p>
            <Link to="/faq" className="link-strong">
              {t("home.help_link")}
              <Icon name="arrowRight" size={16} />
            </Link>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Banner({ d }: { d: Dashboard }) {
  const { t } = useTranslation();
  const lang = useLang();
  const w = d.wave;
  const allDone = d.modules_assigned > 0 && d.modules_certified === d.modules_assigned;
  let days = "";
  if (w) {
    if (allDone) days = t("home.all_done");
    else if (d.overdue || w.days_left < 0) days = t("home.overdue");
    else if (w.days_left === 0) days = t("home.last_day");
    else days = t("home.days_left", { count: w.days_left });
  }
  return (
    <section className="banner">
      <div className="banner-text">
        {w && <p className="banner-kicker">{pick(w, "name", lang)}</p>}
        <h1>{t("home.welcome", { name: d.full_name })}</h1>
        <p>{w ? t("home.banner", { date: date(w.go_live) }) : t("home.no_wave")}</p>
      </div>
      {w && (
        <div className="banner-stats">
          <div className={`banner-stat ${d.overdue ? "overdue" : ""}`}>
            <span>{t("home.deadline")}</span>
            <strong>{date(w.deadline)}</strong>
            <span>{days}</span>
          </div>
          <div className="banner-stat">
            <span>{t("home.overall")}</span>
            <strong className="num">
              {d.modules_certified} / {d.modules_assigned}
            </strong>
            <span>{t("home.certified_modules")}</span>
          </div>
        </div>
      )}
    </section>
  );
}

function ResumeCard({ r }: { r: Resume }) {
  const { t } = useTranslation();
  const lang = useLang();
  const to = `/courses/${r.module_id}/lessons/${r.lesson_id}`;
  return (
    <div className="card resume">
      <Link to={to} className="resume-thumb" tabIndex={-1} aria-hidden="true">
        <span className="resume-play">
          <Icon name="play" size={30} />
        </span>
        <span className="resume-bar">
          <span style={{ width: `${r.watched_pct}%` }} />
        </span>
      </Link>
      <div className="card-pad stack-sm">
        <p className="caps">{t("home.resume")}</p>
        <h3>{t("home.resume_where", { module: pick(r, "module_title", lang), n: r.lesson_number })}</h3>
        <p className="muted">
          {pick(r, "title", lang)} · {t("common.min", { count: minutes(r.duration_s) })}
        </p>
        <Link className="btn btn-primary btn-block" to={to}>
          {t("home.resume_button")}
        </Link>
      </div>
    </div>
  );
}

function StatusText({ status, due }: { status: CertStatus; due?: string | null }) {
  const { t } = useTranslation();
  if (status === "valid" && due) return <span className="status-text warning">{t("cert_status.renew_by", { date: date(due) })}</span>;
  const tone = status === "valid" ? "success" : status === "recert_required" ? "warning" : "muted";
  return <span className={`status-text ${tone}`}>{t(`home.cert_${status}`)}</span>;
}

function CertificatesCard({ d }: { d: Dashboard }) {
  const { t } = useTranslation();
  const lang = useLang();
  const title = (c: DashboardCert) => (lang === "ru" ? c.title_ru : c.title_uz) ?? c.number;
  return (
    <div className="card card-pad stack">
      <p className="caps">{t("home.certificates")}</p>
      <ul className="mini-certs">
        <li>
          <span className="strong">{t("certs.operator_title")}</span>
          {d.operator_status === "missing" ? (
            <span className="status-text muted">{t("home.operator_missing")}</span>
          ) : (
            <StatusText status={d.operator_status} />
          )}
        </li>
        {d.certificates.map((c) => (
          <li key={c.number}>
            <span>{title(c)}</span>
            <StatusText status={c.status} due={c.recert_due_at} />
          </li>
        ))}
      </ul>
      <Link to="/certificates" className="link-strong">
        {t("home.all_certificates")}
        <Icon name="arrowRight" size={16} />
      </Link>
    </div>
  );
}
