"""Capture bundle: the video + meta.json uploaded by the phone (or tools/mac_capture.py).

meta.json schema (version 1):
{
  "schema": 1,
  "challenge_id": str,
  "device_model": str,              # e.g. "iPhone15,2" or "mac-webcam"
  "frames": [float, ...],           # host-clock seconds, one per video frame
  "dropped": [float, ...],          # host-clock seconds of dropped frames
  "display_events": [{"state_index": int, "ts": float}, ...],   # -1 = settle color
  "camera": {"width": int, "height": int, "fps": float, "fov_deg": float,
             "mirrored": bool, "iso": float, "exposure_s": float,
             "focus_locked": bool, "min_focus_mm": float},
  "screen": {"brightness": float, "width_mm": float, "height_mm": float},
  "distance_mm": float,             # instructed working distance
  "imu": [], "haptics": []          # reserved for the vibration test
}
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

SMALL_W = 160  # width of the downscaled frames kept in memory


class JpegSequence:
    """Frames the browser client captures itself: repeated [uint32 LE length][JPEG].

    A browser can't hand over a video file whose frames map 1:1 to capture timestamps,
    so the web app grabs each camera frame with its timestamp and packs them like this.
    Mimics the part of cv2.VideoCapture the pipeline uses.
    """

    def __init__(self, path):
        self.blob = Path(path).read_bytes()
        self.index: list[tuple[int, int]] = []
        i = 0
        while i + 4 <= len(self.blob):
            (n,) = struct.unpack_from("<I", self.blob, i)
            i += 4
            if n == 0 or i + n > len(self.blob):
                break
            self.index.append((i, n))
            i += n
        self.pos = 0
        self._size = None

    def isOpened(self) -> bool:
        return bool(self.index)

    def read(self):
        if self.pos >= len(self.index):
            return False, None
        off, n = self.index[self.pos]
        self.pos += 1
        img = cv2.imdecode(np.frombuffer(self.blob, np.uint8, n, off), cv2.IMREAD_COLOR)
        return (img is not None), img

    def get(self, prop):
        if self._size is None:
            keep, self.pos = self.pos, 0
            ok, img = self.read()
            self.pos = keep
            self._size = (img.shape[1], img.shape[0]) if ok else (0, 0)
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return self._size[0]
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return self._size[1]
        return 0

    def release(self):
        pass


def open_frames(path):
    """cv2.VideoCapture for video files, JpegSequence for the web client's .bin container."""
    return JpegSequence(path) if str(path).endswith(".bin") else cv2.VideoCapture(str(path))


@dataclass
class Bundle:
    video_path: Path
    meta: dict
    ts: np.ndarray          # (N,) host-clock seconds per frame
    small: np.ndarray       # (N, h, w, 3) float32 RGB 0..1, downscaled
    full_size: tuple[int, int]  # (width, height) of the source video

    @property
    def n(self) -> int:
        return len(self.ts)

    @property
    def frame_period(self) -> float:
        return float(np.median(np.diff(self.ts))) if self.n > 1 else 1 / 30

    def events(self) -> list[tuple[int, float]]:
        ev = [(int(e["state_index"]), float(e["ts"])) for e in self.meta["display_events"]]
        return sorted(ev, key=lambda e: e[1])

    def read_crops(self, box: tuple[int, int, int, int]) -> np.ndarray:
        """Second pass over the video returning full-resolution crops.

        box = (x, y, w, h) in source pixels. Returns (N, h, w, 3) float32 RGB 0..1.
        """
        x, y, w, h = box
        cap = open_frames(self.video_path)
        out = []
        while len(out) < self.n:
            ok, frame = cap.read()
            if not ok:
                break
            crop = frame[y:y + h, x:x + w, ::-1]
            out.append(crop.astype(np.float32) / 255.0)
        cap.release()
        return np.stack(out) if out else np.zeros((0, h, w, 3), np.float32)


def load(video_path: str | Path, meta: dict | str | Path) -> Bundle:
    video_path = Path(video_path)
    if not isinstance(meta, dict):
        meta = json.loads(Path(meta).read_text())

    cap = open_frames(video_path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {video_path}")
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    sh = max(1, round(H * SMALL_W / W))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(frame, (SMALL_W, sh), interpolation=cv2.INTER_AREA)
        frames.append(small[:, :, ::-1].astype(np.float32) / 255.0)
    cap.release()
    if not frames:
        raise ValueError("video has no frames")

    ts = np.asarray(meta["frames"], dtype=np.float64)
    # The writer can drop a trailing frame; keep the streams the same length.
    n = min(len(ts), len(frames))
    return Bundle(video_path, meta, ts[:n], np.stack(frames[:n]), (W, H))
