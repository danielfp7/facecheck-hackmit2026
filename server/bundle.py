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
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

SMALL_W = 160  # width of the downscaled frames kept in memory


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
        cap = cv2.VideoCapture(str(self.video_path))
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

    cap = cv2.VideoCapture(str(video_path))
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
