import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { LearnerLesson } from "../api/types";
import { minutes } from "../lib/format";
import { pick, useLang } from "../lib/lang";
import { Icon } from "./Icon";

/** Numbered lessons with completion marks (mockup 2, side panel). */
export function LessonList({
  lessons,
  hrefFor,
  currentId,
  locked,
  tracked = true,
}: {
  lessons: LearnerLesson[];
  hrefFor: (id: number) => string;
  currentId?: number;
  locked?: boolean;
  tracked?: boolean;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  return (
    <ol className="lessons">
      {lessons.map((l, i) => {
        const current = l.id === currentId;
        const meta = [t("common.min", { count: minutes(l.duration_s) })];
        if (tracked && l.completed) meta.push(t("lesson.completed"));
        else if (tracked && l.watched_pct > 0) meta.push(t("lesson.watched_pct", { pct: l.watched_pct }));
        const done = tracked && l.completed;
        const body = (
          <>
            <span className={`lesson-mark ${done ? "done" : ""}`} aria-hidden="true">
              {done ? <Icon name="check" size={16} /> : i + 1}
            </span>
            <span className="grow">
              <span className="lesson-title">
                {i + 1}. {pick(l, "title", lang)}
              </span>
              <span className="lesson-meta">{meta.join(" · ")}</span>
            </span>
          </>
        );
        return (
          <li key={l.id} className={current ? "current" : ""}>
            {locked ? (
              <div className="lesson-row disabled">{body}</div>
            ) : (
              <Link className="lesson-row" to={hrefFor(l.id)} aria-current={current ? "page" : undefined}>
                {body}
              </Link>
            )}
          </li>
        );
      })}
    </ol>
  );
}
