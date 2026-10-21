import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { learner } from "../../api/learner";
import type { Fragment, Heartbeat, Lang, LearnerLesson, LearnerModuleDetail, Player, Progress } from "../../api/types";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { ErrorState, PageLoader } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { LessonList } from "../../components/LessonList";
import { ProgressBar } from "../../components/Status";
import { TestCard } from "../../components/TestCard";
import { SEEK_TOLERANCE_S, VideoPlayer, type Cue, type PlayerHandle } from "../../components/VideoPlayer";
import { clock, minutes } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { useApi } from "../../lib/useApi";

interface Outline {
  lessons: LearnerLesson[];
  module: LearnerModuleDetail | null; // null for FAQ
}

/** Lesson page (mockup 2); with `faq` the same page plays FAQ videos, untracked. */
export default function Lesson({ faq = false }: { faq?: boolean }) {
  const params = useParams();
  const lessonId = Number(params.lessonId);
  const moduleId = Number(params.moduleId);
  const [search] = useSearchParams();
  const startAt = search.get("t") !== null ? Number(search.get("t")) : null;

  const lesson = useApi<Player>(() => (faq ? learner.faqLesson(lessonId) : learner.lesson(lessonId)), [lessonId, faq]);
  const outline = useApi<Outline>(
    () =>
      faq
        ? learner.faq().then((lessons) => ({ lessons, module: null }))
        : learner.module(moduleId).then((module) => ({ lessons: module.lessons, module })),
    [faq, moduleId],
  );

  if (lesson.loading && !lesson.data) return <PageLoader />;
  if (lesson.error || !lesson.data) return <ErrorState error={lesson.error} onRetry={lesson.reload} />;
  // Keyed: progress, cues and the seek limit belong to one lesson version and start fresh
  // with the next one (the current lesson stays on screen while the next one loads).
  return (
    <LessonView
      key={`${lesson.data.lesson_id}-${lesson.data.version_id}`}
      faq={faq}
      player={lesson.data}
      startAt={startAt}
      outline={outline.data}
      outlineLoading={outline.loading}
      reloadOutline={outline.reload}
      onVersionChanged={lesson.reload}
    />
  );
}

function LessonView({
  faq,
  player,
  startAt,
  outline,
  outlineLoading,
  reloadOutline,
  onVersionChanged,
}: {
  faq: boolean;
  player: Player;
  startAt: number | null;
  outline: Outline | null;
  outlineLoading: boolean;
  reloadOutline: () => void;
  onVersionChanged: () => void;
}) {
  const { t } = useTranslation();
  const lang = useLang();
  const [progress, setProgress] = useState<Progress | null>(player.progress);
  const [fragments, setFragments] = useState<Fragment[]>(player.remediation);
  const [time, setTime] = useState(0);
  const [limit, setLimit] = useState<number | null>(player.seek_limit_s);
  const [cues, setCues] = useState<Partial<Record<Lang, Cue[]>>>({});
  const [tab, setTab] = useState<"text" | "pdf">("text");
  const handle = useRef<PlayerHandle>(null);
  const completed = useRef(Boolean(player.progress?.completed));
  const pendingFragments = useRef(false);
  pendingFragments.current = fragments.some((f) => !f.satisfied);

  const lessonId = player.lesson_id;
  const onHeartbeat = useCallback(
    (hb: Heartbeat) => {
      setProgress(hb);
      if (hb.completed && !completed.current) {
        completed.current = true;
        reloadOutline(); // ticks the lesson off and may open the test
      }
      // Fragment progress after a failed test is counted on the server: read it back.
      if (pendingFragments.current) {
        learner
          .lesson(lessonId)
          .then((p) => setFragments(p.remediation))
          .catch(() => undefined);
      }
    },
    [lessonId, reloadOutline],
  );
  const onCues = useCallback((l: Lang, list: Cue[]) => setCues((c) => ({ ...c, [l]: list })), []);

  const lessons = outline?.lessons ?? [];
  const module = outline?.module ?? null;
  const index = lessons.findIndex((l) => l.id === player.lesson_id);
  const number = index >= 0 ? index + 1 : null;
  const title = pick(player, "title", lang);
  const hrefFor = (id: number) => (faq ? `/faq/${id}` : `/courses/${player.module_id}/lessons/${id}`);
  const tracked = player.tracking;
  const done = Boolean(progress?.completed);
  // The current lesson's numbers come from the heartbeats, fresher than the outline.
  const sideLessons = lessons.map((l) =>
    l.id === player.lesson_id && progress
      ? { ...l, completed: progress.completed, watched_pct: progress.watched_pct }
      : l,
  );
  const doneCount = sideLessons.filter((l) => l.completed).length;
  const test = module?.test ?? null;
  const testOpen = test !== null && (test.status.can_start || test.status.open_attempt_id !== null);

  const crumbs = faq
    ? [{ label: t("nav.faq"), to: "/faq" }, { label: title }]
    : [
        { label: t("nav.courses"), to: "/courses" },
        { label: module ? pick(module, "title", lang) : "…", to: `/courses/${player.module_id}` },
        { label: number ? t("lesson.number", { n: number }) : title },
      ];

  return (
    <div className="stack">
      <Breadcrumbs items={crumbs} />
      <div className="lesson-grid">
        <div className="lesson-main">
          <VideoPlayer
            ref={handle}
            player={player}
            startAt={startAt}
            fragments={fragments}
            onHeartbeat={onHeartbeat}
            onVersionChanged={onVersionChanged}
            onTime={setTime}
            onLimit={setLimit}
            onCues={onCues}
          />

          {tracked &&
            (done ? (
              <div className="notice notice-success">
                <Icon name="check" />
                <span>{t("lesson.done")}</span>
              </div>
            ) : (
              <div className="notice notice-warning">
                <Icon name="info" />
                <span>
                  <Trans i18nKey="lesson.rule" components={{ b: <strong /> }} />
                  {progress && progress.watched_pct > 0 && ` ${t("lesson.watched_now", { pct: progress.watched_pct })}`}
                </span>
              </div>
            ))}

          {fragments.length > 0 && (
            <div className="card card-pad stack-sm">
              <strong>{t("lesson.fragments_title")}</strong>
              {fragments.map((f) => (
                <div key={f.span_start_s} className="fragment-row">
                  <span className={`lesson-mark ${f.satisfied ? "done" : ""}`} aria-hidden="true">
                    {f.satisfied ? <Icon name="check" size={16} /> : <Icon name="replay" size={16} />}
                  </span>
                  <span className="grow">
                    {t("result.fragment", { from: clock(f.span_start_s), to: clock(f.span_end_s) })}
                    {" · "}
                    {f.satisfied ? t("result.rewatched") : t("lesson.fragment_progress", { pct: f.watched_pct })}
                  </span>
                  {!f.satisfied && (
                    <button className="btn btn-small" onClick={() => handle.current?.seek(f.span_start_s)}>
                      {t("lesson.fragment_go")}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="lesson-head">
            <div>
              <h1>{number ? `${number}. ${title}` : title}</h1>
              <div className="chips">
                {!faq && player.release_code && (
                  <span className="chip chip-primary">{t("lesson.release", { release: player.release_code })}</span>
                )}
                <span className="chip">{t("lesson.minutes", { count: minutes(player.duration_s) })}</span>
                <span className="chip">{t("lesson.synthetic")}</span>
              </div>
            </div>
            <div className="row">
              {player.prev_lesson_id !== null ? (
                <Link className="btn" to={hrefFor(player.prev_lesson_id)}>
                  <Icon name="arrowLeft" size={18} />
                  {t("lesson.prev")}
                </Link>
              ) : (
                <span className="btn" aria-disabled="true">
                  <Icon name="arrowLeft" size={18} />
                  {t("lesson.prev")}
                </span>
              )}
              {player.next_lesson_id !== null ? (
                <Link className="btn" to={hrefFor(player.next_lesson_id)}>
                  {t("lesson.next")}
                  <Icon name="arrowRight" size={18} />
                </Link>
              ) : testOpen ? (
                <Link className="btn btn-primary" to={`/courses/${player.module_id}/test`}>
                  {t("lesson.to_test")}
                  <Icon name="arrowRight" size={18} />
                </Link>
              ) : (
                <span className="btn" aria-disabled="true">
                  {t("lesson.next")}
                  <Icon name="arrowRight" size={18} />
                </span>
              )}
            </div>
          </div>

          <div className="card tabs-card">
            <div className="tabs" role="tablist">
              <button role="tab" aria-selected={tab === "text"} onClick={() => setTab("text")}>
                {t("lesson.tab_text")}
              </button>
              {player.pdf && (
                <button role="tab" aria-selected={tab === "pdf"} onClick={() => setTab("pdf")}>
                  {t("lesson.tab_pdf")}
                </button>
              )}
            </div>
            {tab === "pdf" && player.pdf ? (
              <div className="card-pad stack">
                <p className="muted">{t("lesson.pdf_hint")}</p>
                <div className="row wrap">
                  {(["uz", "ru"] as Lang[]).map((l) => (
                    <a
                      key={l}
                      className={`btn ${l === lang ? "btn-primary" : ""}`}
                      href={player.pdf![l]}
                      target="_blank"
                      rel="noopener"
                    >
                      <Icon name="external" size={18} />
                      {t(`lesson.pdf_${l}`)}
                    </a>
                  ))}
                </div>
              </div>
            ) : (
              <Transcript
                cues={cues[lang] ?? null}
                time={time}
                limit={limit}
                onSeek={(s) => handle.current?.seek(s)}
              />
            )}
          </div>
        </div>

        <aside className="card lesson-side">
          <div className="side-head">
            <h3>{faq ? t("nav.faq") : module ? pick(module, "title", lang) : ""}</h3>
            {!faq && lessons.length > 0 && (
              <>
                <div className="spread small muted">
                  <span>{t("lesson.side_progress", { done: doneCount, total: lessons.length })}</span>
                  <span>{Math.round((doneCount / lessons.length) * 100)}%</span>
                </div>
                <ProgressBar value={(doneCount / lessons.length) * 100} />
              </>
            )}
          </div>
          {outlineLoading && !outline ? (
            <div className="card-pad muted">{t("app.loading")}</div>
          ) : (
            <LessonList lessons={sideLessons} hrefFor={hrefFor} currentId={player.lesson_id} tracked={!faq} />
          )}
          {module && test && <TestCard module={module} test={test} compact />}
        </aside>
      </div>
    </div>
  );
}

/** Subtitle cues as a clickable transcript; on a first viewing only up to the seek limit. */
function Transcript({
  cues,
  time,
  limit,
  onSeek,
}: {
  cues: Cue[] | null;
  time: number;
  limit: number | null;
  onSeek: (seconds: number) => void;
}) {
  const { t } = useTranslation();
  const list = useRef<HTMLOListElement>(null);
  const active = useMemo(() => {
    if (!cues) return -1;
    let found = -1;
    for (let i = 0; i < cues.length && cues[i].start <= time + 0.05; i++) found = i;
    return found;
  }, [cues, time]);

  useEffect(() => {
    // Keep the current line visible inside the transcript box (not the page).
    const box = list.current;
    const row = active >= 0 ? (box?.children[active] as HTMLElement | undefined) : undefined;
    if (!box || !row) return;
    if (row.offsetTop < box.scrollTop || row.offsetTop + row.offsetHeight > box.scrollTop + box.clientHeight) {
      box.scrollTop = row.offsetTop - box.clientHeight / 3;
    }
  }, [active]);

  if (cues === null) return <div className="card-pad muted">{t("app.loading")}</div>;
  if (cues.length === 0) return <div className="card-pad muted">{t("lesson.no_text")}</div>;
  return (
    <ol className="transcript" ref={list}>
      {cues.map((c, i) => {
        const locked = limit !== null && c.start > limit + SEEK_TOLERANCE_S;
        return (
          <li key={i} className={i === active ? "active" : ""}>
            <button disabled={locked} onClick={() => onSeek(c.start)} title={locked ? t("player.seek_blocked") : undefined}>
              <span className="ts">{clock(c.start)}</span>
              <span>{c.text}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
