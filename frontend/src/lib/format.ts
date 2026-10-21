/** Times are shown in the bank's time zone, whatever the browser's setting. */

export const TZ = "Asia/Tashkent";

function parts(iso: string): Record<string, string> {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  return Object.fromEntries(fmt.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
}

/** 19.10.2026 */
export function date(iso: string | null | undefined): string {
  if (!iso) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [y, m, d] = iso.split("-");
    return `${d}.${m}.${y}`; // plain dates (wave deadlines) have no time zone
  }
  const p = parts(iso);
  return `${p.day}.${p.month}.${p.year}`;
}

/** 19.10.2026, 14:05 */
export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const p = parts(iso);
  return `${p.day}.${p.month}.${p.year}, ${p.hour}:${p.minute}`;
}

/** 4:05 or 1:02:03 */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

/** 23:41:08, for countdowns */
export function countdown(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const hh = Math.floor(s / 3600);
  const mm = String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return hh ? `${hh}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function minutes(seconds: number): number {
  return Math.max(1, Math.round(seconds / 60));
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return "";
  return `${Math.round(value)}%`;
}
