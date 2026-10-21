import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { LearnerModuleDetail, TestInfo } from "../api/types";
import { pct } from "../lib/format";
import { useReasonText } from "../lib/reasons";
import { Icon } from "./Icon";

/** The module test: what it is, attempts, and either the way in or every reason it is closed. */
export function TestCard({ module, test, compact }: { module: LearnerModuleDetail; test: TestInfo; compact?: boolean }) {
  const { t } = useTranslation();
  const reasonText = useReasonText();
  const s = test.status;
  const open = s.can_start || s.open_attempt_id !== null;
  const passed = s.reasons.some((r) => r.code === "already_passed");
  const reasons = s.reasons.filter((r) => r.code !== "attempt_in_progress" && r.code !== "already_passed");
  const facts = t("test.facts", { count: test.question_count, minutes: test.time_limit_min });

  let action = null;
  if (s.open_attempt_id !== null) {
    action = (
      <Link className="btn btn-primary btn-block" to={`/attempts/${s.open_attempt_id}`}>
        {t("test.resume")}
      </Link>
    );
  } else if (s.can_start) {
    action = (
      <Link className="btn btn-primary btn-block" to={`/courses/${module.id}/test`}>
        {t("test.go")}
      </Link>
    );
  }

  if (compact) {
    const lessonsLeft = reasons.some((r) => r.code === "lessons_incomplete");
    const other = reasons.find((r) => r.code !== "lessons_incomplete");
    let line = facts;
    if (passed) line = t("test.passed_short");
    else if (lessonsLeft) line = t("test.after_lessons", { count: module.lessons_total, facts });
    else if (!open && other) line = reasonText(other); // e.g. fragments to re-watch, or the cooldown
    return (
      <div className={`test-mini ${open ? "open" : ""}`}>
        <Icon name={passed ? "check" : open ? "question" : "lock"} size={18} />
        <div className="grow stack-sm">
          <strong>{t("test.title")}</strong>
          <span className="muted small">{line}</span>
          {action}
        </div>
      </div>
    );
  }

  return (
    <div className="card card-pad stack test-card">
      <div className="row">
        <span className={`test-icon ${passed ? "passed" : open ? "open" : ""}`}>
          <Icon name={passed ? "check" : open ? "question" : "lock"} size={22} />
        </span>
        <div className="grow">
          <h3>{t("test.title")}</h3>
          <span className="muted small">
            {facts} · {t("test.pass_mark", { pass: test.pass_pct })}
          </span>
        </div>
      </div>
      <div className="test-meta">
        <span>{t("test.attempts", { used: s.attempts_used, max: s.attempts_max })}</span>
        {s.last_attempt_id !== null && s.last_score_pct !== null && (
          <span>
            {t(s.last_passed ? "test.last_passed" : "test.last_failed", { score: pct(s.last_score_pct) })}{" "}
            <Link to={`/attempts/${s.last_attempt_id}/result`}>{t("test.view_result")}</Link>
          </span>
        )}
      </div>
      {passed && (
        <div className="notice notice-success">
          <Icon name="check" />
          <span>
            {t("test.passed")} <Link to="/certificates">{t("test.to_certificates")}</Link>
          </span>
        </div>
      )}
      {action}
      {!open && reasons.length > 0 && (
        <ul className="reasons">
          {reasons.map((r) => (
            <li key={r.code}>{reasonText(r)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
