import assert from "node:assert/strict";
import { test } from "node:test";
import { reserveChunkReload } from "../src/lib/chunkRecovery.ts";

function memory() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
  };
}

test("a missing lazy chunk can trigger one reload, without an infinite loop", () => {
  const storage = memory();
  assert.equal(reserveChunkReload(storage, 1_000), true);
  assert.equal(reserveChunkReload(storage, 1_001), false);
  assert.equal(reserveChunkReload(storage, 60_999), false);
  assert.equal(reserveChunkReload(storage, 61_000), true);
});

test("a blocked storage read or write leaves the explicit retry available", () => {
  assert.equal(
    reserveChunkReload({
      getItem: () => {
        throw Error("blocked");
      },
      setItem: () => {},
    }),
    false,
  );
  assert.equal(
    reserveChunkReload({
      getItem: () => null,
      setItem: () => {
        throw Error("blocked");
      },
    }),
    false,
  );
});

test("clock rollback does not permanently prevent recovery", () => {
  const storage = memory();
  assert.equal(reserveChunkReload(storage, 100_000), true);
  assert.equal(reserveChunkReload(storage, 10_000), true);
});
