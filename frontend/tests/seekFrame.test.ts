import assert from "node:assert/strict";
import { test } from "node:test";
import { SeekFrame } from "../src/lib/seekFrame.ts";

function fixture(nativeFrames = true) {
  let id = 0;
  let captures = 0;
  const callbacks = new Map<
    number,
    (time: number, metadata: { mediaTime: number }) => void
  >();
  const paints = new Map<number, FrameRequestCallback>();
  const events = new EventTarget();
  const video = Object.assign(events, {
    readyState: 4,
    videoWidth: 1280,
    videoHeight: 720,
    seeking: false,
    currentTime: 10,
    requestVideoFrameCallback: nativeFrames
      ? (cb: (time: number, metadata: { mediaTime: number }) => void) => {
          callbacks.set(++id, cb);
          return id;
        }
      : undefined,
    cancelVideoFrameCallback: (key: number) => {
      callbacks.delete(key);
    },
  });
  const canvas = {
    hidden: true,
    width: 0,
    height: 0,
    getContext: () => ({
      drawImage: () => {
        captures++;
      },
    }),
  };
  const held = new SeekFrame(
    video as unknown as HTMLVideoElement,
    canvas as unknown as HTMLCanvasElement,
    {
      request: (cb: FrameRequestCallback) => {
        paints.set(++id, cb);
        return id;
      },
      cancel: (key: number) => {
        paints.delete(key);
      },
    },
  );
  return {
    video,
    canvas,
    held,
    callbacks,
    paints,
    captures: () => captures,
    present(time: number) {
      const pending = [...callbacks.values()];
      callbacks.clear();
      pending.forEach((cb) => cb(0, { mediaTime: time }));
    },
    paint() {
      const pending = [...paints.values()];
      paints.clear();
      pending.forEach((cb) => cb(0));
    },
  };
}

test("keeps a picture through buffering and reveals only the decoded target", () => {
  const f = fixture();
  f.held.hold();
  f.video.currentTime = 25;
  f.video.seeking = true;
  f.present(10);
  assert.equal(f.canvas.hidden, false);
  f.video.seeking = false;
  f.present(25);
  assert.equal(f.canvas.hidden, true);
  assert.equal(f.callbacks.size, 0);
});

test("rapid seeking preserves the original picture and ignores stale callbacks", () => {
  const f = fixture();
  f.held.hold();
  const stale = [...f.callbacks.values()][0];
  f.video.currentTime = 20;
  f.video.seeking = true;
  f.held.hold();
  f.video.currentTime = 30;
  f.video.seeking = false;
  stale(0, { mediaTime: 30 });
  assert.equal(f.canvas.hidden, false);
  assert.equal(f.captures(), 1);
  f.present(20);
  assert.equal(f.canvas.hidden, false);
  f.present(30);
  assert.equal(f.canvas.hidden, true);
});

test("paused seeking handles a frame presented just before seeked", () => {
  const f = fixture();
  f.held.hold();
  f.video.currentTime = 5;
  f.video.seeking = true;
  f.present(5);
  f.video.seeking = false;
  f.video.dispatchEvent(new Event("seeked"));
  f.paint();
  f.paint();
  assert.equal(f.canvas.hidden, true);
});

test("fallback waits for seeked and a paint when frame callbacks are unavailable", () => {
  const f = fixture(false);
  f.held.hold();
  f.video.seeking = true;
  f.video.dispatchEvent(new Event("loadeddata"));
  f.paint();
  f.paint();
  assert.equal(f.canvas.hidden, false);
  f.video.seeking = false;
  f.video.dispatchEvent(new Event("seeked"));
  f.paint();
  assert.equal(f.canvas.hidden, false);
  f.paint();
  assert.equal(f.canvas.hidden, true);
});

test("does not capture unavailable video; disposal cancels callbacks and listeners", () => {
  const f = fixture();
  f.video.readyState = 1;
  f.held.hold();
  assert.equal(f.captures(), 0);
  assert.equal(f.canvas.hidden, true);
  f.video.readyState = 4;
  f.held.hold();
  f.held.dispose();
  assert.equal(f.canvas.hidden, true);
  assert.equal(f.callbacks.size, 0);
  f.video.dispatchEvent(new Event("seeked"));
  assert.equal(f.paints.size, 0);
});
