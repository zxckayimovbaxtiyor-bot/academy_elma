// Run with `npm test` (Node's built-in runner and type stripping; no test framework).
import assert from "node:assert/strict";
import { test } from "node:test";

import { merge, PlayTracker } from "../src/lib/watch.ts";

const play = (p: PlayTracker, from: number, to: number, rate = 1) => {
  for (let t = from; t <= to + 1e-9; t += 0.25 * rate) p.tick(t, rate);
};

test("merge joins overlapping and touching ranges and drops empty ones", () => {
  assert.deepEqual(merge([[5, 8], [0, 2], [2, 4], [7, 10], [12, 12]]), [[0, 4], [5, 10]]);
});

test("continuous playback is one range; take() continues the open range", () => {
  const p = new PlayTracker();
  play(p, 0, 10);
  assert.deepEqual(p.take(), [[0, 10]]);
  play(p, 10.25, 12);
  assert.deepEqual(p.take(), [[10, 12]]);
});

test("a seek forward or back closes the range", () => {
  const p = new PlayTracker();
  play(p, 0, 5);
  play(p, 20, 22); // jumped ahead
  play(p, 3, 4); // jumped back
  assert.deepEqual(p.take(), [[0, 5], [20, 22]]);
});

test("at 2x a bigger step still counts as continuous, at 1x it is a jump", () => {
  const fast = new PlayTracker();
  [0, 1.5, 3].forEach((t) => fast.tick(t, 2));
  assert.deepEqual(fast.take(), [[0, 3]]);
  const slow = new PlayTracker();
  [0, 2.5].forEach((t) => slow.tick(t, 1));
  assert.deepEqual(slow.take(), []);
});

test("pause closes the range and nothing is reported twice", () => {
  const p = new PlayTracker();
  play(p, 0, 1);
  p.close();
  assert.deepEqual(p.take(), [[0, 1]]);
  assert.deepEqual(p.take(), []);
});

test("a failed heartbeat's ranges go out with the next one", () => {
  const p = new PlayTracker();
  play(p, 0, 1);
  p.close();
  p.giveBack(p.take());
  play(p, 5, 6);
  assert.deepEqual(p.take(), [[0, 1], [5, 6]]);
});

test("ranges are rounded to milliseconds", () => {
  const p = new PlayTracker();
  p.tick(0.1234567, 1);
  p.tick(1.0000001, 1);
  assert.deepEqual(p.take(), [[0.123, 1]]);
});
