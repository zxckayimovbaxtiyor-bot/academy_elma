/**
 * What the player actually played, as [start, end] ranges in seconds, for heartbeats.
 *
 * The server decides what counts (90 % rule, seek block, wall-clock cap); this only
 * reports honestly. A jump in time (seek, stall recovery) closes the current range.
 */

export type Range = [number, number];

export function merge(ranges: Range[]): Range[] {
  const sorted = ranges.filter(([a, b]) => b > a).sort((x, y) => x[0] - y[0]);
  const out: Range[] = [];
  for (const [a, b] of sorted) {
    const last = out[out.length - 1];
    if (last && a <= last[1] + 0.001) last[1] = Math.max(last[1], b);
    else out.push([a, b]);
  }
  return out;
}

export class PlayTracker {
  private done: Range[] = [];
  private start: number | null = null;
  private last = 0;

  /** Call on every timeupdate while playing. */
  tick(t: number, rate: number): void {
    if (this.start === null) {
      this.start = this.last = t;
      return;
    }
    const step = t - this.last;
    if (step < 0 || step > 1.5 * Math.max(rate, 1) + 0.5) {
      this.close(); // not continuous playback
      this.start = this.last = t;
      return;
    }
    this.last = t;
  }

  /** Pause, seek or end: the current range is finished. */
  close(): void {
    if (this.start !== null && this.last > this.start) this.done.push([this.start, this.last]);
    this.start = null;
  }

  /** Everything played since the last take(); the open range continues from here. */
  take(): Range[] {
    const out = [...this.done];
    if (this.start !== null && this.last > this.start) {
      out.push([this.start, this.last]);
      this.start = this.last;
    }
    this.done = [];
    return merge(out).map(([a, b]) => [round(a), round(b)]);
  }

  /** A heartbeat failed: keep its ranges for the next one. */
  giveBack(ranges: Range[]): void {
    this.done.unshift(...ranges);
  }
}

function round(x: number): number {
  return Math.round(x * 1000) / 1000;
}
