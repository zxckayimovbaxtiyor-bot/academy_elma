const KEY = "academy:chunk-reload-at";
const COOLDOWN_MS = 60_000;

/** A deployment may remove a lazy chunk still referenced by an open tab. */
export function reserveChunkReload(
  storage: Pick<Storage, "getItem" | "setItem">,
  now = Date.now(),
): boolean {
  try {
    const previous = Number(storage.getItem(KEY));
    if (previous > 0 && now >= previous && now - previous < COOLDOWN_MS)
      return false;
    storage.setItem(KEY, String(now));
    return true;
  } catch {
    // If storage is unavailable, show the retry screen instead of risking a loop.
    return false;
  }
}
