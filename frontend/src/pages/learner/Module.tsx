import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { learner } from "../../api/learner";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { LessonList } from "../../components/LessonList";
import { ModuleBadge, ProgressBar } from "../../components/Status";
import { TestCard } from "../../components/TestCard";
import { date, minutes } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";

export function ModulePage() {
  const { t } = useTranslation();
  const lang = useLang();
  const id = Number(useParams().moduleId);
  const { data: m, error, loading, reload } = useApi(() => learner.module(id), [id]);
  if (loading && !m) return <PageLoader />;
  if (error || !m) return <ErrorState error={error} onRetry={reload} />;
  const title = pick(m, "title", lang);
  const done = m.lessons_completed;
  const total = m.lessons_total;
  const renew = m.status === "recert_required" || (m.status === "certified" && m.recert_due_at !== null);
  return (
    <div className="stack-lg">
      <Breadcrumbs items={[{ label: t("nav.courses"), to: "/courses" }, { label: title }]} />
      <header className="page-head">
        <div className="path-title">
          <h1>{title}</h1>
          <ModuleBadge state={m.status} locked={m.locked} />
        </div>
        <div className="chips">
          {m.release_code && <span className="chip chip-primary">{t("lesson.release", { release: m.release_code })}</span>}
          <span className="chip">{t("path.lessons", { count: total })}</span>
          <span className="chip">{t("path.duration", { count: minutes(m.duration_s) })}</span>
        </div>
      </header>
      {m.locked && (
        <div className="notice">
          <Icon name="lock" />
          <span>{t("module.locked")}</span>
        </div>
      )}
      {renew && (
        <div className="notice notice-warning">
          <Icon name="alert" />
          <span>
            {t("module.recert", { release: m.release_code ?? "" })}
            {m.recert_due_at && ` ${t("module.recert_due", { date: date(m.recert_due_at) })}`}
          </span>
        </div>
      )}
      <div className="module-grid">
        <section className="card">
          <div className="side-head">
            <div className="spread">
              <h2>{t("module.lessons")}</h2>
              <span className="muted">{t("lesson.side_progress", { done, total })}</span>
            </div>
            <ProgressBar value={(done / Math.max(1, total)) * 100} tone={done === total ? "success" : undefined} />
          </div>
          <LessonList
            lessons={m.lessons}
            locked={m.locked}
            hrefFor={(lessonId) => `/courses/${m.id}/lessons/${lessonId}`}
          />
        </section>
        <aside className="stack">{m.test && <TestCard module={m} test={m.test} />}</aside>
      </div>
    </div>
  );
}
