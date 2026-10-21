import assert from "node:assert/strict";
import { test } from "node:test";

import { clock, countdown, date, dateTime } from "../src/lib/format.ts";

test("timestamps are shown in Tashkent time whatever the browser's zone", () => {
  assert.equal(date("2026-10-19T20:30:00Z"), "20.10.2026"); // 01:30 the next day in Tashkent
  assert.equal(dateTime("2026-10-19T09:05:00Z"), "19.10.2026, 14:05");
});

test("plain dates (wave deadlines) are not shifted", () => {
  assert.equal(date("2026-11-18"), "18.11.2026");
});

test("video and countdown clocks", () => {
  assert.equal(clock(65), "1:05");
  assert.equal(clock(3725), "1:02:05");
  assert.equal(countdown(61_000), "01:01");
  assert.equal(countdown(3_661_000), "1:01:01");
  assert.equal(countdown(-5), "00:00");
});
