import { ApiError } from "../api/client";
import { learner } from "../api/learner";

export type SaveState = "idle" | "saving" | "saved" | "retrying";
type Change = { answer?: number[] | null; flagged?: boolean };

const ENDED = new Set(["attempt.expired", "attempt.finished", "attempt.not_found"]);

/**
 * Autosave for one attempt. Changes go out one request at a time, the newest change
 * per question wins, and network failures are retried until they get through.
 */
export class AnswerSaver {
  private queue = new Map<number, Change>();
  private running = false;
  private closed = false;
  private waiters: (() => void)[] = [];

  constructor(
    private attemptId: number,
    private onState: (state: SaveState) => void,
    private onEnded: (error: ApiError) => void, // the attempt is over on the server
    private onRejected: (error: ApiError) => void, // this change was refused
  ) {}

  push(position: number, change: Change): void {
    if (this.closed) return;
    this.queue.set(position, { ...this.queue.get(position), ...change });
    void this.run();
  }

  /** Resolves once everything queued so far is saved (or can't be). */
  flushed(): Promise<void> {
    if (!this.running && this.queue.size === 0) return Promise.resolve();
    return new Promise((resolve) => this.waiters.push(resolve));
  }

  close(): void {
    this.closed = true;
    this.queue.clear();
  }

  private async run(): Promise<void> {
    if (this.running) return;
    this.running = true;
    while (this.queue.size > 0 && !this.closed) {
      const [position, change] = this.queue.entries().next().value as [number, Change];
      this.queue.delete(position);
      this.onState("saving");
      try {
        await learner.saveAnswer(this.attemptId, position, change);
      } catch (err) {
        const error = err instanceof ApiError ? err : new ApiError(0, "network");
        if (ENDED.has(error.code)) {
          this.close();
          this.onEnded(error);
        } else if (error.status === 0 || error.status >= 500) {
          // Keep it, unless a newer change to the same question is already waiting.
          this.queue.set(position, { ...change, ...this.queue.get(position) });
          this.onState("retrying");
          await new Promise((resolve) => window.setTimeout(resolve, 3000));
        } else {
          this.onRejected(error);
        }
      }
    }
    this.running = false;
    if (!this.closed) this.onState("saved");
    this.waiters.splice(0).forEach((resolve) => resolve());
  }
}
