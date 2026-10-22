/** Keep the last picture visible until the decoder presents the sought frame. */
export class SeekFrame {
  private frame: number | null = null;
  private paint: number | null = null;
  private generation = 0;
  private presented: number | null = null;

  private readonly video: HTMLVideoElement;
  private readonly canvas: HTMLCanvasElement;
  private readonly animation: {
    request: (cb: FrameRequestCallback) => number;
    cancel: (id: number) => void;
  };

  constructor(
    video: HTMLVideoElement,
    canvas: HTMLCanvasElement,
    animation = {
      request: (cb: FrameRequestCallback) => requestAnimationFrame(cb),
      cancel: (id: number) => cancelAnimationFrame(id),
    },
  ) {
    this.video = video;
    this.canvas = canvas;
    this.animation = animation;
    video.addEventListener("seeked", this.settled);
    video.addEventListener("loadeddata", this.settled);
    video.addEventListener("error", this.clear);
    video.addEventListener("emptied", this.clear);
  }

  hold() {
    // Repeated slider events must keep the original picture, never capture a
    // partially decoded frame in the middle of the previous seek.
    if (this.canvas.hidden) {
      if (
        this.video.readyState < 2 ||
        !this.video.videoWidth ||
        this.video.seeking
      )
        return;
      const context = this.canvas.getContext("2d");
      if (!context) return;
      try {
        this.canvas.width = this.video.videoWidth;
        this.canvas.height = this.video.videoHeight;
        context.drawImage(this.video, 0, 0);
        this.canvas.hidden = false;
      } catch {
        return; // A capture failure must never interrupt native playback.
      }
    }
    this.cancel();
    this.presented = null;
    this.waitForFrame(this.generation);
  }

  private matches() {
    return (
      !this.video.seeking &&
      this.video.readyState >= 2 &&
      this.presented !== null &&
      Math.abs(this.presented - this.video.currentTime) < 0.25
    );
  }

  private waitForFrame(generation: number) {
    if (!this.video.requestVideoFrameCallback) return;
    this.frame = this.video.requestVideoFrameCallback((_now, metadata) => {
      if (generation !== this.generation) return;
      this.frame = null;
      this.presented = metadata.mediaTime;
      if (this.matches()) this.clear();
      else this.waitForFrame(generation);
    });
  }

  private settled = () => {
    if (this.canvas.hidden) return;
    if (this.paint !== null) this.animation.cancel(this.paint);
    const generation = this.generation;
    // Paused video may present its single frame before firing seeked. Give the
    // compositor a paint before revealing it; older browsers use this fallback.
    this.paint = this.animation.request(() => {
      this.paint = this.animation.request(() => {
        this.paint = null;
        if (generation !== this.generation) return;
        if (
          this.matches() ||
          (!this.video.requestVideoFrameCallback &&
            !this.video.seeking &&
            this.video.readyState >= 2)
        )
          this.clear();
      });
    });
  };

  private cancel() {
    this.generation++;
    if (this.frame !== null) this.video.cancelVideoFrameCallback(this.frame);
    if (this.paint !== null) this.animation.cancel(this.paint);
    this.frame = this.paint = null;
  }

  clear = () => {
    this.cancel();
    this.canvas.hidden = true;
    this.presented = null;
  };

  dispose() {
    this.clear();
    this.video.removeEventListener("seeked", this.settled);
    this.video.removeEventListener("loadeddata", this.settled);
    this.video.removeEventListener("error", this.clear);
    this.video.removeEventListener("emptied", this.clear);
  }
}
