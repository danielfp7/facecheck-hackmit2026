"""Live face swap in a plain full-screen window: the test attacker, without Deep-Live-Cam's UI.

  uv run --project server attack/live.py                      # swaps in attack/Deep-Live-Cam/victim.jpg
  uv run --project server attack/live.py --source a.jpg b.jpg c.jpg   # several photos of one person

Run it from the Terminal app: macOS gives camera permission per app, and anything started from
VS Code is refused. Same model as Deep-Live-Cam (inswapper_128), ~30 fps on this Mac.

Keys:  space  swap on/off      + / -  zoom (to present a life-size eye to the phone)
       h      show/hide the fps readout          q or Esc  quit

For defensive testing only, with the face of a teammate who has agreed to it.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from mac_capture import load_swapper  # noqa: E402

WIN = "live"
DEFAULT_SOURCE = Path(__file__).resolve().parent / "Deep-Live-Cam/victim.jpg"

NO_CAMERA = """Couldn't read from the camera.
  1. Run this from the Terminal app, not from VS Code.
  2. System Settings > Privacy & Security > Camera: turn Terminal on.
     If Terminal isn't listed, run `tccutil reset Camera com.apple.Terminal` and start this again
     so macOS asks.
  3. Close anything else using the camera (FaceTime, Zoom, a browser tab, Deep-Live-Cam)."""


def open_camera(index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    # The first frames after permission is granted can come back empty.
    for _ in range(50):
        ok, frame = cap.read()
        if ok and frame is not None and frame.mean() > 1:
            return cap
        time.sleep(0.1)
    sys.exit(NO_CAMERA)


class LatestFrame:
    """Always hands back the newest camera frame. Reading the camera directly queues frames
    whenever the swap runs slower than the camera, and the queue shows up as extra delay."""

    def __init__(self, cap: cv2.VideoCapture):
        self.cap, self.frame, self.lock, self.alive = cap, None, threading.Lock(), True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while self.alive:
            ok, frame = self.cap.read()
            if ok:
                with self.lock:
                    self.frame = frame

    def take(self):
        with self.lock:
            frame, self.frame = self.frame, None
        return frame


def zoomed(frame, zoom: float):
    if zoom <= 1.0:
        return frame
    h, w = frame.shape[:2]
    cw, ch = int(w / zoom), int(h / zoom)
    x, y = (w - cw) // 2, (h - ch) // 2
    return cv2.resize(frame[y:y + ch, x:x + cw], (w, h), interpolation=cv2.INTER_CUBIC)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", nargs="+", default=[str(DEFAULT_SOURCE)],
                    help="photo(s) of the face to swap in; several of the same person give a steadier likeness")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--windowed", action="store_true", help="don't go full screen")
    args = ap.parse_args()
    for path in args.source:
        if not Path(path).exists():
            sys.exit(f"no such photo: {path}")

    cap = open_camera(args.camera)          # before the models: a camera problem should fail fast
    print("loading the swap model (about 10 s the first time)...")
    swap = load_swapper(args.source)
    frames = LatestFrame(cap)

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    if not args.windowed:
        cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    on, hud, zoom, fps, last = True, False, 1.0, 0.0, time.monotonic()
    while True:
        frame = frames.take()
        if frame is None:
            time.sleep(0.002)
            continue
        if on:
            frame = swap(frame)
        frame = zoomed(frame, zoom)
        now = time.monotonic()
        fps, last = 0.9 * fps + 0.1 / max(now - last, 1e-6), now
        if hud:
            cv2.putText(frame, f"{'SWAP' if on else 'real'}  {fps:.0f} fps  x{zoom:.1f}", (24, 48),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow(WIN, frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key == ord(" "):
            on = not on
        elif key == ord("h"):
            hud = not hud
        elif key in (ord("+"), ord("=")):
            zoom = min(zoom + 0.25, 4.0)
        elif key in (ord("-"), ord("_")):
            zoom = max(zoom - 0.25, 1.0)
    frames.alive = False
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
