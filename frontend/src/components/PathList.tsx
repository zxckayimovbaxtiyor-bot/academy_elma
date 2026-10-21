import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { LearnerModule } from "../api/types";
import { date, minutes, pct } from "../lib/format";
import { pick, useLang } from "../lib/lang";
import { Icon } from "./Icon";
import { ModuleBadge, ProgressBar } from "./Status";

/** One module of the learning path (mockup 1): number, status, what to do next. */
function PathItem({ m, n }: { m: LearnerModule; n: number }) {
  const { t } = useTranslation();
  const lang = useLang();
  const to = `/courses/${m.id}`;
  const left = m.lessons_total - m.lessons_completed;
  const lessons = t("path.lessons", { count: m.lessons_total });
  // A release changed the module: certified until the due date, then recertification.
  const renew = m.status === "recert_required" || (m.status === "certified" && m.recert_due_at !== null);
  let details: string[];
  let action: ReactNode;
  if (m.locked) {
    details = [lessons, t("path.locked")];
    action = (
      <span className="btn" aria-disabled="true">
        <Icon name="lock" size={18} />
        {t("path.action.locked")}
      </span>
    );
  } else if (renew) {
    const release = m.release_code ?? "";
    details = [left > 0 ? t("path.recert_lessons", { release, count: left }) : t("path.recert_test", { release })];
    if (m.recert_due_at) details.push(t("path.renew_by", { date: date(m.recert_due_at) }));
    action = (
      <Link className="btn" to={to}>
        {t("path.action.update")}
      </Link>
    );
  } else if (m.status === "certified") {
    details = [lessons];
    if (m.score_pct !== null) details.push(t("path.score", { score: pct(m.score_pct) }));
    if (m.release_code) details.push(t("path.release", { release: m.release_code }));
    action = (
      <Link className="btn" to="/certificates">
        {t("path.action.certificate")}
      </Link>
    );
  } else if (m.status === "in_progress") {
    details = [
      t("path.watched", { done: m.lessons_completed, total: m.lessons_total }),
      left > 0 ? t("path.test_after") : t("path.test_ready"),
    ];
    action = (
      <Link className="btn btn-primary" to={to}>
        {t("path.action.continue")}
      </Link>
    );
  } else {
    details = [lessons, t("path.duration", { count: minutes(m.duration_s) })];
    action = (
      <Link className="btn" to={to}>
        {t("path.action.start")}
      </Link>
    );
  }
  const tone = m.locked ? "locked" : renew ? "recert_required" : m.status;
  return (
    <li className={`path-item path-${tone}`}>
      <span className="path-num" aria-hidden="true">
        {m.locked ? <Icon name="lock" size={20} /> : n}
      </span>
      <div className="grow">
        <div className="path-title">
          <h3>{pick(m, "title", lang)}</h3>
          <ModuleBadge state={m.status} locked={m.locked} />
        </div>
        <p>{details.join(" · ")}</p>
        {m.status === "in_progress" && !m.locked && (
          <ProgressBar
            value={(m.lessons_completed / Math.max(1, m.lessons_total)) * 100}
            label={t("path.watched", { done: m.lessons_completed, total: m.lessons_total })}
          />
        )}
      </div>
      {action}
    </li>
  );
}

/** FAQ is open to everyone and has no test, so it is not part of the assigned path. */
function FaqItem() {
  const { t } = useTranslation();
  return (
    <li className="path-item path-faq">
      <span className="path-num" aria-hidden="true">
        ?
      </span>
      <div className="grow">
        <div className="path-title">
          <h3>{t("path.faq_title")}</h3>
          <span className="chip">{t("path.no_test")}</span>
        </div>
        <p>{t("path.faq_text")}</p>
      </div>
      <Link className="btn" to="/faq">
        {t("path.action.open")}
      </Link>
    </li>
  );
}

export function PathList({ modules }: { modules: LearnerModule[] }) {
  return (
    <ol className="path">
      {modules.map((m, i) => (
        <PathItem key={m.id} m={m} n={i + 1} />
      ))}
      <FaqItem />
    </ol>
  );
}
