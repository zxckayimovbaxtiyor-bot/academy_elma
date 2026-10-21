import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { content } from "../../api/admin";
import { ApiError } from "../../api/client";
import type { LessonAdmin, Version, Video } from "../../api/adminTypes";
import type { Lang, Player } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { Confirm } from "../../components/Dialog";
import { ErrorLine, ErrorState, PageLoader, useErrorText } from "../../components/Feedback";
import { Icon } from "../../components/Icon";
import { VideoPlayer, type PlayerHandle } from "../../components/VideoPlayer";
import { clock, dateTime } from "../../lib/format";
import { pick, useLang } from "../../lib/lang";
import { isAdmin } from "../../lib/roles";
import { uploadWithProgress } from "../../lib/transfer";
import { useApi } from "../../lib/useApi";
import { Field, FilePick, PageHead, useToast } from "../ui";
import { VideoChip } from "./Content";

const LANGS: Lang[] = ["uz", "ru"];

/** What still keeps a draft version from going live (as the release checklist says). */
export function versionProblems(v: Version): string[] {
  const out: string[] = [];
  if (!v.video) out.push("video_missing");
  else if (v.video.status !== "ready") out.push("video_not_ready");
  for (const lang of LANGS) if (!v[`vtt_${lang}_url`]) out.push(`vtt_${lang}_missing`);
  if (Boolean(v.pdf_uz_url) !== Boolean(v.pdf_ru_url)) out.push("pdf_pair_incomplete");
  return out;
}

/** One lesson: titles, the live version and the draft in the open release. */
export function LessonAdminPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const { me } = useAuth();
  const navigate = useNavigate();
  const id = Number(useParams().lessonId);
  const [search] = useSearchParams();
  const lesson = useApi(() => content.lesson(id), [id]);
  const modules = useApi(() => content.modules(), []);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<unknown>(null);

  if (lesson.loading && !lesson.data) return <PageLoader />;
  if (lesson.error || !lesson.data) return <ErrorState error={lesson.error} onRetry={lesson.reload} />;
  const l: LessonAdmin = lesson.data;
  const module = modules.data?.find((m) => m.id === l.module_id);
  const startAt = search.get("t") !== null ? Number(search.get("t")) : null;
  const neverLive = !l.published;

  return (
    <div className="stack-lg">
      <Breadcrumbs
        items={[
          { label: t("admin.nav.content"), to: "/admin/content" },
          { label: module ? pick(module, "title", lang) : "…", to: `/admin/content/modules/${l.module_id}` },
          { label: pick(l, "title", lang) },
        ]}
      />
      <PageHead
        title={pick(l, "title", lang)}
        subtitle={lang === "ru" ? l.title_uz : l.title_ru}
        actions={
          neverLive && (
            <button className="btn btn-danger-ghost" onClick={() => setDeleting(true)}>
              <Icon name="trash" size={18} />
              {t("lesson_admin.delete")}
            </button>
          )
        }
      />
      <ErrorLine error={error} />
      <Titles lesson={l} onSaved={lesson.reload} />
      {l.draft && <VersionPanel key={`d${l.draft.id}`} lesson={l} version={l.draft} draft onChanged={lesson.reload} startAt={startAt} />}
      {l.published && <VersionPanel key={`p${l.published.id}`} lesson={l} version={l.published} onChanged={lesson.reload} startAt={l.draft ? null : startAt} />}
      {!l.draft && l.published && (
        <div className="notice">
          <Icon name="info" />
          <span>
            {t("lesson_admin.replace_hint")}{" "}
            {isAdmin(me) && <Link to="/admin/releases">{t("admin.nav.releases")}</Link>}
          </span>
        </div>
      )}
      {deleting && (
        <Confirm
          title={t("lesson_admin.delete_title")}
          confirmLabel={t("lesson_admin.delete")}
          onCancel={() => setDeleting(false)}
          onConfirm={async () => {
            try {
              await content.deleteLesson(l.id);
              navigate(`/admin/content/modules/${l.module_id}`, { replace: true });
            } catch (err) {
              setDeleting(false);
              setError(err);
            }
          }}
        >
          <p>{t("lesson_admin.delete_text")}</p>
        </Confirm>
      )}
    </div>
  );
}

function Titles({ lesson, onSaved }: { lesson: LessonAdmin; onSaved: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const [uz, setUz] = useState(lesson.title_uz);
  const [ru, setRu] = useState(lesson.title_ru);
  const [error, setError] = useState<unknown>(null);
  const changed = uz.trim() !== lesson.title_uz || ru.trim() !== lesson.title_ru;
  return (
    <section className="card card-pad stack">
      <div className="grid-2">
        <Field label={t("admin.title_uz")} htmlFor="t-uz">
          <input id="t-uz" className="input" value={uz} onChange={(e) => setUz(e.target.value)} />
        </Field>
        <Field label={t("admin.title_ru")} htmlFor="t-ru">
          <input id="t-ru" className="input" value={ru} onChange={(e) => setRu(e.target.value)} />
        </Field>
      </div>
      <ErrorLine error={error} />
      {changed && (
        <div className="row a-actions">
          <button
            className="btn btn-primary"
            disabled={!uz.trim() || !ru.trim()}
            onClick={async () => {
              try {
                await content.patchLesson(lesson.id, { title_uz: uz.trim(), title_ru: ru.trim() });
                toast(t("admin.saved"));
                onSaved();
              } catch (err) {
                setError(err);
              }
            }}
          >
            {t("admin.save")}
          </button>
        </div>
      )}
    </section>
  );
}

function VersionPanel({
  lesson,
  version: v,
  draft,
  onChanged,
  startAt,
}: {
  lesson: LessonAdmin;
  version: Version;
  draft?: boolean;
  onChanged: () => void;
  startAt: number | null;
}) {
  const { t } = useTranslation();
  const toast = useToast();
  const errorText = useErrorText();
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<Lang>("uz");
  const player = useRef<PlayerHandle>(null);
  const problems = draft ? versionProblems(v) : [];
  const ready = v.video?.status === "ready";

  const run = async (fn: () => Promise<unknown>, message: string) => {
    setError(null);
    try {
      await fn();
      toast(message);
      onChanged();
    } catch (err) {
      setError(err);
    }
  };

  // The admin preview reuses the learner player, untracked and free to seek.
  const preview: Player | null =
    ready && v.video
      ? {
          lesson_id: lesson.id,
          module_id: lesson.module_id,
          module_type: "core",
          title_uz: lesson.title_uz,
          title_ru: lesson.title_ru,
          version_id: v.id,
          release_code: v.release_code,
          duration_s: v.video.duration_s ?? 0,
          hls_url: `/media/hls/${v.video.asset_id}/master.m3u8`,
          subtitles: { uz: v.vtt_uz_url, ru: v.vtt_ru_url },
          pdf: null,
          tracking: false,
          progress: null,
          seek_limit_s: null,
          speed_change_allowed: true,
          prev_lesson_id: null,
          next_lesson_id: null,
          remediation: [],
        }
      : null;

  return (
    <section className={`card card-pad stack ${draft ? "version-draft" : ""}`}>
      <div className="row wrap">
        <h2>{t(draft ? "lesson_admin.draft_version" : "lesson_admin.live_version")}</h2>
        <span className={`chip ${draft ? "chip-warning" : "chip-success"}`}>{t("lesson.release", { release: v.release_code })}</span>
        {v.published_at && <span className="muted small">{dateTime(v.published_at)}</span>}
        <span className="grow" />
        <VideoChip v={v} />
      </div>
      {draft && problems.length > 0 && (
        <div className="notice notice-warning">
          <Icon name="alert" />
          <span>
            {t("lesson_admin.blocks")} {problems.map((p) => t(`release.problem.${p}`)).join(" · ")}
          </span>
        </div>
      )}
      {draft && <VideoUpload version={v} onDone={onChanged} />}
      {preview && (
        <div className="preview">
          <VideoPlayer ref={player} player={preview} startAt={startAt} fragments={[]} />
        </div>
      )}
      <div className="grid-2">
        {LANGS.map((l) => {
          const url = v[`vtt_${l}_url`];
          return (
            <div key={l} className="file-box">
              <strong>{t(`lesson_admin.subtitles_${l}`)}</strong>
              <span className="muted small">{url ? t("lesson_admin.uploaded") : t("lesson_admin.not_uploaded")}</span>
              <div className="row wrap">
                {url && (
                  <a className="btn btn-small" href={url} target="_blank" rel="noopener">
                    {t("lesson_admin.open")}
                  </a>
                )}
                <FilePick accept=".vtt,text/vtt" className="btn btn-small" onFile={(f) => run(() => content.subtitles(v.id, l, f), t("lesson_admin.vtt_saved"))}>
                  <Icon name="upload" size={16} />
                  {url ? t("lesson_admin.replace") : t("lesson_admin.upload")}
                </FilePick>
              </div>
            </div>
          );
        })}
        {LANGS.map((l) => {
          const url = v[`pdf_${l}_url`];
          return (
            <div key={`pdf-${l}`} className="file-box">
              <strong>{t(`lesson_admin.pdf_${l}`)}</strong>
              <span className="muted small">{url ? t("lesson_admin.uploaded") : t("lesson_admin.optional")}</span>
              <div className="row wrap">
                {url && (
                  <a className="btn btn-small" href={url} target="_blank" rel="noopener">
                    {t("lesson_admin.open")}
                  </a>
                )}
                <FilePick accept=".pdf,application/pdf" className="btn btn-small" onFile={(f) => run(() => content.pdf(v.id, l, f), t("lesson_admin.pdf_saved"))}>
                  <Icon name="upload" size={16} />
                  {url ? t("lesson_admin.replace") : t("lesson_admin.upload")}
                </FilePick>
                {url && (
                  <button className="btn btn-small btn-ghost" onClick={() => run(() => content.deletePdf(v.id, l), t("lesson_admin.pdf_deleted"))}>
                    <Icon name="trash" size={16} />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <p className="muted small">{t("lesson_admin.pdf_rule")}</p>
      {error !== null && <div className="notice notice-danger">{errorText(error)}</div>}
      {(v.vtt_uz_url || v.vtt_ru_url) && (
        <div className="stack-sm">
          <div className="tabs">
            {LANGS.map((l) => (
              <button key={l} role="tab" aria-selected={tab === l} onClick={() => setTab(l)}>
                {t("lesson.tab_text")} · {l.toUpperCase()}
              </button>
            ))}
          </div>
          <Transcript versionId={v.id} lang={tab} available={Boolean(v[`vtt_${tab}_url`])} onSeek={(s) => player.current?.seek(s)} />
        </div>
      )}
    </section>
  );
}

function Transcript({ versionId, lang, available, onSeek }: { versionId: number; lang: Lang; available: boolean; onSeek: (s: number) => void }) {
  const { t } = useTranslation();
  const cues = useApi(() => (available ? content.transcript(versionId, lang) : Promise.resolve([])), [versionId, lang, available]);
  if (cues.error) return <ErrorState error={cues.error} onRetry={cues.reload} />;
  if (!cues.data) return <PageLoader />;
  if (cues.data.length === 0) return <p className="muted small">{t("lesson.no_text")}</p>;
  return (
    <ol className="transcript admin-transcript">
      {cues.data.map((c, i) => (
        <li key={i}>
          <button onClick={() => onSeek(c.start)}>
            <span className="ts">{clock(c.start)}</span>
            <span>{c.text}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}

/** MP4 upload with the mandatory synthetic-data confirmation, then the transcode status. */
function VideoUpload({ version, onDone }: { version: Version; onDone: () => void }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const [file, setFile] = useState<File | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [sent, setSent] = useState<number | null>(null);
  const [video, setVideo] = useState<Video | null>(version.video);
  const [error, setError] = useState<unknown>(null);
  // A ready video folds the drop zone away; replacing it is one click.
  const [replacing, setReplacing] = useState(false);
  const abort = useRef<AbortController | null>(null);

  // Follow the worker while it transcodes.
  useEffect(() => {
    if (!video || (video.status !== "uploaded" && video.status !== "processing")) return;
    const id = window.setInterval(async () => {
      try {
        const next = await content.video(video.asset_id);
        setVideo(next);
        if (next.status === "ready" || next.status === "failed") onDone();
      } catch {
        /* keep polling */
      }
    }, 2000);
    return () => window.clearInterval(id);
  }, [video, onDone]);
  useEffect(() => () => abort.current?.abort(), []);

  const start = async () => {
    if (!file || !confirmed) return;
    setError(null);
    setSent(0);
    abort.current = new AbortController();
    try {
      const out = await uploadWithProgress<Video>(content.videoUrl(version.id, file.name), file, setSent, abort.current.signal);
      setVideo(out);
      setFile(null);
      setConfirmed(false);
      setReplacing(false);
    } catch (err) {
      if (!(err instanceof ApiError && err.code === "aborted")) setError(err);
    } finally {
      setSent(null);
    }
  };

  const failedCode = video?.status === "failed" && video.error ? video.error.split(":")[0] : null;
  const busy = sent !== null;
  if (video?.status === "ready" && !replacing && !busy) {
    return (
      <div className="upload-box row wrap">
        <strong className="grow">{t("lesson_admin.video_upload")}</strong>
        <span className="muted small">
          {video.original_filename}
          {video.duration_s ? ` · ${clock(video.duration_s)}` : ""}
        </span>
        <button className="btn btn-small" onClick={() => setReplacing(true)}>
          <Icon name="upload" size={16} />
          {t("lesson_admin.replace")}
        </button>
      </div>
    );
  }
  return (
    <div className="upload-box stack-sm">
      <div className="row wrap">
        <strong className="grow">{t("lesson_admin.video_upload")}</strong>
        {video && (
          <span className="muted small">
            {video.original_filename}
            {video.duration_s ? ` · ${clock(video.duration_s)}` : ""}
          </span>
        )}
      </div>
      {video && (video.status === "processing" || video.status === "uploaded") && (
        <div className="stack-sm">
          <span className="small">{t("content.video_processing", { pct: video.progress_pct })}</span>
          <div className="progress">
            <span style={{ width: `${video.progress_pct}%` }} />
          </div>
        </div>
      )}
      {failedCode && <div className="notice notice-danger">{t(`errors.${failedCode}`, { defaultValue: video?.error ?? "" })}</div>}
      <label className="drop">
        <Icon name="upload" size={26} />
        <strong>{file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB` : t("lesson_admin.choose_mp4")}</strong>
        <span className="muted small">{t("lesson_admin.mp4_rule")}</span>
        <input type="file" accept="video/mp4,.mp4" hidden disabled={busy} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <label className="confirm-box">
        <input type="checkbox" className="box" checked={confirmed} disabled={busy} onChange={(e) => setConfirmed(e.target.checked)} />
        <span>
          <strong>{t("lesson_admin.mandatory")}</strong> {t("lesson_admin.synthetic")}
        </span>
      </label>
      {busy && (
        <div className="stack-sm">
          <span className="small">{t("lesson_admin.uploading", { pct: sent })}</span>
          <div className="progress">
            <span style={{ width: `${sent}%` }} />
          </div>
        </div>
      )}
      {error !== null && <div className="notice notice-danger">{errorText(error)}</div>}
      <div className="row a-actions">
        {busy && (
          <button className="btn" onClick={() => abort.current?.abort()}>
            {t("app.cancel")}
          </button>
        )}
        {!busy && replacing && (
          <button
            className="btn"
            onClick={() => {
              setReplacing(false);
              setFile(null);
              setConfirmed(false);
            }}
          >
            {t("app.cancel")}
          </button>
        )}
        <button className="btn btn-primary" disabled={!file || !confirmed || busy} onClick={start}>
          {t("lesson_admin.upload_start")}
        </button>
      </div>
    </div>
  );
}
