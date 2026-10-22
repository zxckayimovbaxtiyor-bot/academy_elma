import assert from "node:assert/strict";
import { test } from "node:test";
import { editNumber, numberText } from "../src/lib/numberInput.ts";

test("groups typed and pasted numbers while keeping numeric values", () => {
  assert.deepEqual(editNumber("", "50000", 5), {
    text: "50 000",
    value: 50000,
    caret: 6,
  });
  assert.equal(editNumber("", "12\u00a0000\u202f000", 10)?.value, 12000000);
  assert.equal(numberText(12000000), "12 000 000");
});
test("preserves decimals, sign and empty input", () => {
  assert.equal(editNumber("", "-50000,50", 9)?.text, "-50 000,50");
  assert.equal(editNumber("", "-50000,50", 9)?.value, -50000.5);
  assert.equal(editNumber("", "50000.", 6)?.text, "50 000.");
  assert.equal(editNumber("", "", 0)?.value, null);
  assert.equal(editNumber("", "-", 1)?.text, "-");
  assert.equal(editNumber("", "abc", 3), null);
});
test("keeps the caret near edits and deletes digits at grouping boundaries", () => {
  assert.deepEqual(editNumber("50 000", "510 000", 2), {
    text: "510 000",
    value: 510000,
    caret: 2,
  });
  assert.deepEqual(editNumber("50 000", "50000", 2, "deleteContentBackward"), {
    text: "5 000",
    value: 5000,
    caret: 1,
  });
  assert.deepEqual(editNumber("50 000", "50000", 2, "deleteContentForward"), {
    text: "5 000",
    value: 5000,
    caret: 3,
  });
});
