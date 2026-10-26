import { useEffect, useRef, useState } from "react";
import { practice } from "../api/practice";

/** The display is local; the server measures and stores the authoritative time. */
export function usePracticeTimer(id: number, active: boolean, seed: number) {
  const [elapsed, setElapsed] = useState(seed);
  const value = useRef({
    seconds: seed,
    at: performance.now(),
    running: false,
  });
  useEffect(() => {
    value.current = { ...value.current, seconds: seed, at: performance.now() };
    setElapsed(seed);
  }, [id, seed]);
  useEffect(() => {
    if (!active) {
      value.current.running = false;
      return;
    }
    const clientId = crypto.randomUUID();
    let disposed = false;
    let sequence = 0;
    const current = () =>
      value.current.seconds +
      (value.current.running
        ? Math.max(0, performance.now() - value.current.at) / 1000
        : 0);
    const send = async (visible: boolean, keepalive = false) => {
      const request = ++sequence;
      try {
        const result = await practice.activity(
          id,
          clientId,
          visible,
          request,
          keepalive,
        );
        if (!disposed && sequence === request) {
          value.current = {
            seconds: result.elapsed_s,
            at: performance.now(),
            running: visible,
          };
          setElapsed(result.elapsed_s);
        }
      } catch {
        // Server leases bound disconnected time; the next response resynchronizes.
      }
    };
    const visibility = () => {
      const visible = document.visibilityState === "visible";
      value.current = {
        seconds: current(),
        at: performance.now(),
        running: visible,
      };
      setElapsed(Math.floor(value.current.seconds));
      void send(visible, !visible);
    };
    const leaving = () => {
      value.current = {
        seconds: current(),
        at: performance.now(),
        running: false,
      };
      void send(false, true);
    };
    visibility();
    const heartbeat = window.setInterval(() => {
      if (document.visibilityState === "visible") void send(true);
    }, 15_000);
    const display = window.setInterval(
      () => setElapsed(Math.floor(current())),
      1000,
    );
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", leaving);
    return () => {
      disposed = true;
      leaving();
      window.clearInterval(heartbeat);
      window.clearInterval(display);
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", leaving);
    };
  }, [id, active]);
  return elapsed;
}
