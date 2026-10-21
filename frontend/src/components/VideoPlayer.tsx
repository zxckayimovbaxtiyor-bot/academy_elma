import Hls from "hls.js/light";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "../api/client";
import { learner } from "../api/learner";
import type { Fragment, Heartbeat, Lang, Player } from "../api/types";
import { clock } from "../lib/format";
import { useLang } from "../lib/lang";
import { PlayTracker } from "../lib/watch";
import { Icon } from "./Icon";

/**
 * Lesson video (mockup 2): HLS via hls.js (Safari plays it natively), own controls,
 * subtitles drawn from <track> cues, and heartbeats with what was actually played.
 *
 * The server decides what counts. The limits here (no seeking ahead and 1x speed on a
 * first viewing) only spare the learner from watching time that would not be credited.
 */

export const SEEK_TOLERANCE_S = 5; // as on the server (app/services/watch.py)
const HEARTBEAT_MS = 15_000; // the server credits at most 30 s of wall clock per heartbeat
const MAX_RANGES = 50; // per heartbeat (HeartbeatIn)
const SPEEDS = [1, 1.25, 1.5, 2]; // after completion the server credits up to 2x
const LANGS: Lang[] = ["uz", "ru"];

export interface Cue {
  start: number;
  end: number;
  text: string;
}

export interface PlayerHandle {
  seek: (seconds: number) => void;
}

interface Props {
  player: Player;
  startAt: number | null;
  fragments: Fragment[];
  onHeartbeat?: (hb: Heartbeat) => void;
  onVersionChanged?: () => void;
  onTime?: (seconds: number) => void;
  onLimit?: (limit: number | null) => void;
  onCues?: (lang: Lang, cues: Cue[]) => void;
}

const ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&nbsp;": " ",
  "&lrm;": "‎",
  "&rlm;": "‏",
};

/** Cue text without WebVTT markup (<i>, <v Name>, …). */
export function plain(text: string): string {
  return text
    .replace(/<[^>]*>/g, "")
    .replace(/&(amp|lt|gt|nbsp|lrm|rlm);/g, (m) => ENTITIES[m] ?? m)
    .trim();
}

function toCues(list: TextTrackCueList | null): Cue[] {
  if (!list) return [];
  return Array.from(list, (c) => ({ start: c.startTime, end: c.endTime, text: plain((c as VTTCue).text) }));
}

function speedLabel(rate: number): string {
  return `${Number.isInteger(rate) ? rate.toFixed(1) : rate}×`;
}

export const VideoPlayer = forwardRef<PlayerHandle, Props>(function VideoPlayer(props, ref) {
  const { player, startAt, fragments } = props;
  const { t } = useTranslation();
  const uiLang = useLang();
  const box = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const hls = useRef<Hls | null>(null);
  const tracker = useRef(new PlayTracker());
  const callbacks = useRef(props);
  callbacks.current = props; // latest handlers without re-running effects
  const tracked = player.tracking;
  const duration = player.duration_s;

  // Seek limit on a first viewing; null means free seeking (FAQ or completed lesson).
  const limitRef = useRef<number | null>(player.seek_limit_s);
  const [limit, setLimitState] = useState<number | null>(player.seek_limit_s);
  const setLimit = useCallback((value: number | null) => {
    limitRef.current = value;
    setLimitState(value);
    callbacks.current.onLimit?.(value);
  }, []);
  const speedFree = useRef(player.speed_change_allowed);
  const [speedAllowed, setSpeedAllowed] = useState(player.speed_change_allowed);

  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [waiting, setWaiting] = useState(false);
  const [rate, setRate] = useState(1);
  const [sub, setSub] = useState<Lang | null>(uiLang);
  const [caption, setCaption] = useState("");
  const [levels, setLevels] = useState<number[]>([]); // height per hls.js level
  const [level, setLevel] = useState(-1); // -1: automatic
  const [shownHeight, setShownHeight] = useState<number | null>(null);
  const [menu, setMenu] = useState<"speed" | "quality" | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const toastTimer = useRef<number>();
  const sending = useRef(false);
  const again = useRef(false);
  const stopped = useRef(false); // a release replaced the video: no more heartbeats

  // Where to start: ?t= (a remediation fragment), else where the learner left off.
  const start = useMemo(() => {
    const lim = player.seek_limit_s;
    const ok = (s: number) => s > 0 && s < duration - 2 && (lim === null || s <= lim + SEEK_TOLERANCE_S);
    if (startAt !== null && Number.isFinite(startAt) && ok(startAt)) return startAt;
    const last = player.progress?.last_position_s ?? 0;
    return last > 3 && ok(last) ? last : 0;
  }, []); // once per mount: later progress must not move the start
  const resumeAt = useRef(start);

  const flash = useCallback((message: string) => {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 3000);
  }, []);
  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  // --- loading the stream -----------------------------------------------------------------

  useEffect(() => {
    const el = video.current;
    if (!el) return;
    setFailed(false);
    const from = resumeAt.current;
    if (Hls.isSupported()) {
      const h = new Hls({ startPosition: from > 0 ? from : -1 });
      hls.current = h;
      let recoveries = 0;
      h.on(Hls.Events.MANIFEST_PARSED, (_e, data) => setLevels(data.levels.map((l) => l.height)));
      h.on(Hls.Events.LEVEL_SWITCHED, (_e, data) => setShownHeight(h.levels[data.level]?.height ?? null));
      h.on(Hls.Events.ERROR, (_e, data) => {
        if (!data.fatal) return; // hls.js retries these itself
        if (recoveries++ < 3) {
          if (data.type === Hls.ErrorTypes.MEDIA_ERROR) h.recoverMediaError();
          else h.startLoad();
          return;
        }
        setFailed(true);
      });
      h.loadSource(player.hls_url);
      h.attachMedia(el);
      return () => {
        h.destroy();
        hls.current = null;
      };
    }
    if (el.canPlayType("application/vnd.apple.mpegurl")) {
      const seekStart = () => {
        if (from > 0) el.currentTime = from;
      };
      el.addEventListener("loadedmetadata", seekStart, { once: true });
      el.src = player.hls_url;
      return () => {
        el.removeEventListener("loadedmetadata", seekStart);
        el.removeAttribute("src");
        el.load();
      };
    }
    setFailed(true);
  }, [player.hls_url, retry]);

  // --- subtitles and transcript cues ------------------------------------------------------

  useEffect(() => {
    const el = video.current;
    if (!el) return;
    const off: (() => void)[] = [];
    for (const trackEl of Array.from(el.querySelectorAll("track"))) {
      const lang = trackEl.srclang as Lang;
      trackEl.track.mode = "hidden"; // loads the cues; we draw them ourselves
      const publish = () => callbacks.current.onCues?.(lang, toCues(trackEl.track.cues));
      if (trackEl.readyState === HTMLTrackElement.LOADED) publish();
      trackEl.addEventListener("load", publish);
      off.push(() => trackEl.removeEventListener("load", publish));
    }
    return () => off.forEach((f) => f());
  }, [player.version_id]);

  useEffect(() => {
    const el = video.current;
    const track = el ? Array.from(el.textTracks).find((tt) => tt.language === sub) : undefined;
    if (!track) {
      setCaption("");
      return;
    }
    const update = () => setCaption(Array.from(track.activeCues ?? [], (c) => plain((c as VTTCue).text)).join("\n"));
    update();
    track.addEventListener("cuechange", update);
    return () => track.removeEventListener("cuechange", update);
  }, [sub, player.version_id]);

  // --- heartbeats ---------------------------------------------------------------------------

  const send = useCallback(
    async (keepalive = false) => {
      if (!tracked || stopped.current) return;
      if (sending.current && !keepalive) {
        again.current = true; // one at a time; the next one carries everything since
        return;
      }
      const ranges = tracker.current.take();
      const batch = ranges.slice(0, MAX_RANGES);
      if (ranges.length > MAX_RANGES) tracker.current.giveBack(ranges.slice(MAX_RANGES));
      sending.current = true;
      try {
        const hb = await learner.heartbeat(
          player.lesson_id,
          { version_id: player.version_id, ranges: batch, position_s: video.current?.currentTime ?? 0 },
          keepalive,
        );
        if (hb.completed) {
          if (limitRef.current !== null) setLimit(null);
          speedFree.current = true;
          setSpeedAllowed(true);
        } else if (limitRef.current !== null && hb.max_position_s > limitRef.current) {
          setLimit(hb.max_position_s);
        }
        callbacks.current.onHeartbeat?.(hb);
      } catch (err) {
        if (err instanceof ApiError && err.code === "lesson.version_changed") {
          stopped.current = true;
          callbacks.current.onVersionChanged?.();
        } else if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500) {
          tracker.current.giveBack(batch); // try again with the next heartbeat
        }
      } finally {
        sending.current = false;
        if (again.current) {
          again.current = false;
          void send();
        }
      }
    },
    [tracked, player.lesson_id, player.version_id, setLimit],
  );

  useEffect(() => {
    if (!tracked) return;
    void send(); // baseline: starts the server's wall clock for this viewing
    const onVisibility = () => {
      if (document.visibilityState === "hidden") void send(true);
    };
    const onPageHide = () => void send(true);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pagehide", onPageHide);
    const played = tracker.current;
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pagehide", onPageHide);
      played.close();
      void send(true); // leaving the lesson
    };
  }, [tracked, send]);

  useEffect(() => {
    if (!tracked || !playing) return;
    const id = window.setInterval(() => void send(), HEARTBEAT_MS);
    return () => window.clearInterval(id);
  }, [tracked, playing, send]);

  // --- media events -------------------------------------------------------------------------

  const onTimeUpdate = () => {
    const el = video.current;
    if (!el) return;
    const now = el.currentTime;
    if (!el.paused && !el.seeking) {
      tracker.current.tick(now, el.playbackRate);
      // Playing on from the furthest point moves it, as on the server.
      if (limitRef.current !== null && now > limitRef.current) setLimit(now);
    }
    resumeAt.current = now;
    setTime(now);
    callbacks.current.onTime?.(now);
  };

  const onSeeking = () => {
    const el = video.current;
    if (!el) return;
    tracker.current.close(); // the range before the jump is finished
    const lim = limitRef.current;
    if (lim !== null && el.currentTime > lim + SEEK_TOLERANCE_S) {
      el.currentTime = lim;
      flash(t("player.seek_blocked"));
    }
  };

  const onStop = () => {
    setPlaying(false);
    tracker.current.close();
    void send();
  };

  const onRateChange = () => {
    const el = video.current;
    if (!el) return;
    if (!speedFree.current && el.playbackRate !== 1) el.playbackRate = 1;
    setRate(el.playbackRate);
  };

  // --- controls -----------------------------------------------------------------------------

  const toggle = () => {
    const el = video.current;
    if (!el) return;
    if (el.paused) void el.play().catch(() => undefined);
    else el.pause();
  };

  const seek = useCallback(
    (to: number) => {
      const el = video.current;
      if (!el) return;
      let target = Math.max(0, Math.min(to, duration));
      const lim = limitRef.current;
      if (lim !== null && target > lim + SEEK_TOLERANCE_S) {
        target = lim;
        flash(t("player.seek_blocked"));
      }
      el.currentTime = target;
    },
    [duration, flash, t],
  );

  useImperativeHandle(
    ref,
    () => ({
      seek: (seconds: number) => {
        seek(seconds);
        void video.current?.play().catch(() => undefined);
      },
    }),
    [seek],
  );

  const chooseSpeed = (value: number) => {
    setMenu(null);
    if (speedFree.current && video.current) video.current.playbackRate = value;
  };

  const chooseLevel = (index: number) => {
    setMenu(null);
    if (!hls.current) return;
    hls.current.currentLevel = index;
    setLevel(index);
  };

  const fullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void box.current?.requestFullscreen?.();
  };

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => {
      if (!(e.target as HTMLElement).closest(".pmenu")) setMenu(null);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if ((e.target as HTMLElement).closest("button, input")) return; // their own keys
    const el = video.current;
    if (!el) return;
    if (e.key === " " || e.key === "k") toggle();
    else if (e.key === "ArrowLeft") seek(el.currentTime - 5);
    else if (e.key === "ArrowRight") seek(el.currentTime + 5);
    else if (e.key === "f") fullscreen();
    else return;
    e.preventDefault();
  };

  const at = (seconds: number) => `${(Math.max(0, Math.min(seconds, duration)) / duration) * 100}%`;
  const quality =
    level === -1 ? `${t("player.auto")}${shownHeight ? ` · ${shownHeight}p` : ""}` : `${levels[level]}p`;
  const qualityOptions = levels.map((h, i) => ({ h, i })).sort((a, b) => b.h - a.h);

  return (
    <div className="player" ref={box} tabIndex={0} onKeyDown={onKeyDown} aria-label={t("player.label")}>
      <video
        ref={video}
        playsInline
        disablePictureInPicture
        preload="auto"
        onClick={toggle}
        onPlay={() => setPlaying(true)}
        onPause={onStop}
        onEnded={onStop}
        onTimeUpdate={onTimeUpdate}
        onSeeking={onSeeking}
        onRateChange={onRateChange}
        onWaiting={() => setWaiting(true)}
        onPlaying={() => setWaiting(false)}
        onCanPlay={() => setWaiting(false)}
        onError={() => !hls.current && setFailed(true)}
      >
        {LANGS.map((l) =>
          player.subtitles[l] ? (
            <track key={l} kind="subtitles" srcLang={l} label={t(`player.sub_${l}`)} src={player.subtitles[l]!} />
          ) : null,
        )}
      </video>

      {failed ? (
        <div className="player-overlay">
          <p>{t("player.failed")}</p>
          <button className="btn" onClick={() => setRetry((n) => n + 1)}>
            {t("app.retry")}
          </button>
        </div>
      ) : waiting && playing ? (
        <div className="player-overlay" role="status">
          <div className="spinner" />
        </div>
      ) : (
        !playing && (
          <button className="player-big" onClick={toggle} aria-label={t("player.play")}>
            <Icon name="play" size={40} />
          </button>
        )
      )}
      {sub && caption && <div className="player-caption">{caption}</div>}
      {toast && (
        <div className="player-toast" role="status">
          {toast}
        </div>
      )}

      <div className="player-bar">
        <div className="seek">
          <div className="seek-track">
            {limit !== null && <span className="seek-locked" style={{ left: at(limit + SEEK_TOLERANCE_S) }} />}
            {fragments.map((f) => (
              <span
                key={f.span_start_s}
                className={`seek-fragment ${f.satisfied ? "done" : ""}`}
                style={{ left: at(f.span_start_s), width: `calc(${at(f.span_end_s)} - ${at(f.span_start_s)})` }}
              />
            ))}
            <span className="seek-fill" style={{ width: at(time) }} />
          </div>
          <input
            type="range"
            min={0}
            max={duration}
            step={0.5}
            value={Math.min(time, duration)}
            onChange={(e) => seek(Number(e.target.value))}
            aria-label={t("player.seek")}
            aria-valuetext={`${clock(time)} / ${clock(duration)}`}
          />
        </div>
        <div className="player-controls">
          <button className="pbtn icon" onClick={toggle} aria-label={t(playing ? "player.pause" : "player.play")}>
            <Icon name={playing ? "pause" : "play"} />
          </button>
          <button className="pbtn icon" onClick={() => seek(time - 10)} aria-label={t("player.back10")} title={t("player.back10")}>
            <Icon name="replay" />
          </button>
          <span className="player-time">
            {clock(time)} / {clock(duration)}
          </span>
          <span className="grow" />
          {LANGS.filter((l) => player.subtitles[l]).map((l) => (
            <button
              key={l}
              className={`pbtn ${sub === l ? "on" : ""}`}
              aria-pressed={sub === l}
              onClick={() => setSub(sub === l ? null : l)}
              title={t(`player.sub_${l}`)}
            >
              {t(`player.sub_short_${l}`)}
            </button>
          ))}
          <div className="pmenu">
            <button
              className="pbtn"
              disabled={!speedAllowed}
              aria-expanded={menu === "speed"}
              title={speedAllowed ? t("player.speed") : t("player.speed_locked")}
              onClick={() => setMenu(menu === "speed" ? null : "speed")}
            >
              {speedLabel(rate)}
            </button>
            {menu === "speed" && (
              <div className="pmenu-list" role="menu">
                {SPEEDS.map((s) => (
                  <button key={s} role="menuitemradio" aria-checked={rate === s} onClick={() => chooseSpeed(s)}>
                    {speedLabel(s)}
                  </button>
                ))}
              </div>
            )}
          </div>
          {levels.length > 1 && (
            <div className="pmenu">
              <button
                className="pbtn"
                aria-expanded={menu === "quality"}
                title={t("player.quality")}
                onClick={() => setMenu(menu === "quality" ? null : "quality")}
              >
                {quality}
              </button>
              {menu === "quality" && (
                <div className="pmenu-list" role="menu">
                  <button role="menuitemradio" aria-checked={level === -1} onClick={() => chooseLevel(-1)}>
                    {t("player.auto")}
                  </button>
                  {qualityOptions.map(({ h, i }) => (
                    <button key={i} role="menuitemradio" aria-checked={level === i} onClick={() => chooseLevel(i)}>
                      {h}p
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          <button className="pbtn icon" onClick={fullscreen} aria-label={t("player.fullscreen")} title={t("player.fullscreen")}>
            <Icon name="fullscreen" />
          </button>
        </div>
      </div>
    </div>
  );
});
