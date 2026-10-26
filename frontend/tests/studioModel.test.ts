import { test } from "node:test";
import assert from "node:assert/strict";
import {
  blank,
  component,
  copyScreen,
  editableValues,
  lt,
  reorder,
  removeScreen,
} from "../src/practice/studioModel.ts";
test("studio reorders without mutating stable IDs or the original array", () => {
  const original = ["a", "b", "c"];
  assert.deepEqual(reorder(original, 0, 2), ["b", "c", "a"]);
  assert.deepEqual(original, ["a", "b", "c"]);
  assert.equal(reorder(original, -1, 2), original);
});
test("copied screens get new IDs and remap local rules, actions and conditions", () => {
  const d = blank();
  const s = d.screens[0];
  const c = component("number", lt("Сумма", "Summa"));
  s.components.unshift(c);
  s.rules.push({
    id: "rule",
    condition: { field: c.id, op: "gt", value: 0 },
    message: lt("Ошибка", "Xato"),
    points: 5,
  });
  s.events = [
    {
      id: "event",
      on: "change",
      component_id: c.id,
      conditions: [{ field: c.id, op: "gt", value: 1 }],
      actions: [{ type: "hide", target: c.id }],
      otherwise: [],
    },
  ];
  const copy = copyScreen(s);
  assert.notEqual(copy.id, s.id);
  assert.notEqual(copy.components[0].id, c.id);
  assert.equal(copy.rules[0].condition.field, copy.components[0].id);
  assert.equal(copy.events![0].component_id, copy.components[0].id);
  assert.equal(copy.events![0].actions[0].target, copy.components[0].id);
  assert.equal(copy.transitions[0].target, "result");
  assert.equal(s.components[0].id, c.id);
});
test("removing a screen cleans incoming edges and preserves valid start/end references", () => {
  const d = blank();
  const extra = copyScreen(d.screens[0]);
  d.screens.push(extra);
  d.screens[0].transitions[0].target = extra.id;
  const next = removeScreen(d, extra.id);
  assert.equal(next.screens.length, 2);
  assert.equal(next.screens[0].transitions.length, 0);
  assert.equal(next.start, d.start);
  assert.deepEqual(next.completion, ["result"]);
  assert.equal(removeScreen(next, "start"), next);
});
test("learner commands exclude readonly fields and fields on other screens", () => {
  const d = blank();
  const numeric = component("number", lt("Сумма", "Summa"));
  const fixed = { ...component("text", lt("Код", "Kod")), editable: false };
  d.screens[0].components.push(numeric, fixed);
  assert.deepEqual(
    editableValues(d.screens[0], {
      [numeric.id]: 50000,
      [fixed.id]: "TEST",
      unknown: true,
    }),
    { [numeric.id]: 50000 },
  );
});
test("a blank lesson has a complete executable route and bilingual labels", () => {
  const d = blank();
  assert.equal(d.screens[0].transitions[0].target, d.completion[0]);
  assert.ok(d.title.ru && d.title.uz);
  assert.notEqual(d.start, d.completion[0]);
});
import { clearOtherPracticeDrafts } from "../src/practice/draftStorage.ts";
test("author recovery drafts are cleared on account change and logout", () => {
  const map = new Map([
    ["practice-studio:1", "private"],
    ["practice-studio:2", "private2"],
    ["language", "ru"],
  ]);
  const storage = {
    get length() {
      return map.size;
    },
    key: (i: number) => Array.from(map.keys())[i] ?? null,
    removeItem: (key: string) => {
      map.delete(key);
    },
  };
  clearOtherPracticeDrafts(storage, 2);
  assert.equal(map.has("practice-studio:1"), false);
  assert.equal(map.has("practice-studio:2"), true);
  clearOtherPracticeDrafts(storage);
  assert.deepEqual(Array.from(map), [["language", "ru"]]);
});
test("blocked tab storage does not break login or logout", () => {
  assert.doesNotThrow(() =>
    clearOtherPracticeDrafts({
      get length(): number {
        throw Error("blocked");
      },
      key: () => null,
      removeItem: () => {},
    }),
  );
});
