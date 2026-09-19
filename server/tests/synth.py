"""Synthetic capture bundles with known ground truth.

Simulates what the phone sees at close range: screen-lit skin, a dark iris, and a
minified mirror image of the screen on the cornea. `lag_ms` delays everything the
camera sees relative to the logged display events, like an attacker's pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from challenge import Challenge
from render import render_state, render_color

W, H, FPS = 720, 1280, 60
SKIN = np.array([0.85, 0.58, 0.47])
IRIS = np.array([0.18, 0.11, 0.07])
AMBIENT = 0.35              # bright room, like the real captures
SCREEN_GAIN = 0.55
GLINT_W, GLINT_H = 40, 52   # px: ~3.4 x 4.5 mm corneal image at 1080p-ish scale
EYE_C = (380, 560)
IRIS_R = 70


def make(ch: Challenge, out_dir: Path, lag_ms: float = 60.0, responsive: bool = True,
         glint: bool = True, flat_mirror: bool = False, seed: int = 0) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    video = out_dir / "video.mp4"
    vw = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))

    t_start = 1000.0            # arbitrary host-clock origin
    settle = 0.5
    events = [(-1, t_start)]
    t = t_start + settle
    for s in ch.states:
        events.append((s.index, t))
        t += s.duration_s
    t_end = t + 0.7

    def screen_at(tq: float) -> np.ndarray:
        """Screen image (small) showing at time tq."""
        idx = -1
        for si, te in events:
            if tq >= te:
                idx = si
        if tq >= t_end - 0.7:
            idx = ch.states[-1].index
        if idx < 0:
            return render_color(ch.settle_color, 90, 195)
        return render_state(ch.states[idx], 90, 195)

    yy, xx = np.mgrid[0:H, 0:W]
    iris_mask = (xx - EYE_C[0]) ** 2 + (yy - EYE_C[1]) ** 2 < IRIS_R ** 2
    # Smooth shading so the face isn't perfectly flat.
    shade = 0.85 + 0.15 * np.cos((xx - W / 2) / W * 2.2) * np.cos((yy - H / 2) / H * 1.6)

    frame_ts = []
    n = int((t_end - t_start) * FPS)
    sub = 4  # sub-frame samples to mimic exposure/rolling-shutter integration
    for i in range(n):
        tf = t_start + i / FPS
        frame_ts.append(tf)
        acc_rgb = np.zeros(3)
        acc_scr = np.zeros((195, 90, 3))
        for k in range(sub):
            tq = tf - lag_ms / 1000.0 - (k / sub) / FPS
            scr = screen_at(tq).astype(np.float64) / 255.0
            if not responsive:
                scr = scr * 0
            acc_rgb += scr.mean(axis=(0, 1))
            acc_scr += scr
        emitted = acc_rgb / sub
        scr = acc_scr / sub

        light = AMBIENT + SCREEN_GAIN * emitted
        img = shade[:, :, None] * SKIN[None, None, :] * light[None, None, :]
        img[iris_mask] = IRIS * light * 0.9

        if glint and responsive:
            if flat_mirror:
                gw, gh = 300, 650   # flat glass: reflection is not minified
            else:
                gw, gh = GLINT_W, GLINT_H
            g = cv2.resize(scr[:, ::-1], (gw, gh), interpolation=cv2.INTER_AREA)
            x0, y0 = EYE_C[0] - gw // 2, EYE_C[1] - gh // 2
            region = img[y0:y0 + gh, x0:x0 + gw]
            img[y0:y0 + gh, x0:x0 + gw] = region + 0.55 * g

        img = img + rng.normal(0, 0.006, img.shape)
        bgr = (np.clip(img, 0, 1)[:, :, ::-1] * 255).astype(np.uint8)
        vw.write(bgr)
    vw.release()

    meta = {
        "schema": 1,
        "challenge_id": ch.id,
        "device_model": "synthetic",
        "frames": frame_ts,
        "dropped": [],
        "display_events": [{"state_index": si, "ts": te} for si, te in events],
        "camera": {"width": W, "height": H, "fps": FPS, "fov_deg": 45.0, "mirrored": False,
                   "iso": 100, "exposure_s": 1 / 120, "focus_locked": True, "min_focus_mm": 60},
        "screen": {"brightness": 1.0, "width_mm": 70, "height_mm": 150},
        "distance_mm": 76,
        "imu": [], "haptics": [],
    }
    meta_path = out_dir / "meta.json"
    meta_path.write_text(json.dumps(meta))
    return video, meta_path
