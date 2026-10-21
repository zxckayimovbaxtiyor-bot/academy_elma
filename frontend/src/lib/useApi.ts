import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";

export interface Loaded<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
  setData: (value: T) => void;
}

/** Load once (and again when deps change); no global store, no cache. */
export function useApi<T>(load: () => Promise<T>, deps: unknown[]): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loader = useRef(load);
  loader.current = load;

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    loader
      .current()
      .then((value) => live && setData(value))
      .catch((err) => live && setError(err instanceof ApiError ? err : new ApiError(0, "network")))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [...deps, tick]); // the loader itself changes every render; deps decide reloads

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload, setData };
}

/** Milliseconds left until `target` (ISO), ticking every second; offset corrects the clock. */
export function useRemaining(target: string | null | undefined, offsetMs = 0): number | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!target) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [target]);
  if (!target) return null;
  return Math.max(0, new Date(target).getTime() - (now + offsetMs));
}
