"""Vibration / motion consistency: does the video move when the phone moves?

The phone fires haptic bursts at server-chosen random times and logs gyro +
accelerometer on the camera's clock. A genuine camera is bolted to that phone, so:
  1. the IMU must feel each burst (proves the bursts fired and the clocks line up),
  2. the video should jitter during the bursts, and
  3. across the whole capture, image motion should follow the gyro.
Injected video does none of 2 and 3: the picture doesn't know the phone moved.

The mechanical response is faster than one frame, so there is no lag to measure here;
the signal is presence and agreement, not timing.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy import signal as sps

from bundle import open_frames

CROP = 512


def measure_video(video_path, n_frames: int) -> np.ndarray:
    """Frame-to-frame global shift (dx, dy) in px from a central crop, shape (N, 2)."""
    cap = open_frames(video_path)
    shifts = np.zeros((n_frames, 2))
    prev, win = None, None
    for i in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        c = min(CROP, h, w)
        y0, x0 = (h - c) // 2, (w - c) // 2
        gray = cv2.cvtColor(frame[y0:y0 + c, x0:x0 + c], cv2.COLOR_BGR2GRAY).astype(np.float32)
        # The screen flashes change brightness between frames; remove level and gain.
        gray = (gray - gray.mean()) / (gray.std() + 1e-6)
        if win is None:
            win = cv2.createHanningWindow((c, c), cv2.CV_32F)
        if prev is not None:
            (dx, dy), _ = cv2.phaseCorrelate(prev, gray, win)
            shifts[i] = (dx, dy)
        prev = gray
    cap.release()
    return shifts


def _energy(x: np.ndarray, t: np.ndarray, width_s: float) -> np.ndarray:
    """Local RMS of the high-frequency part of a vector signal."""
    x = x - sps.medfilt(x, kernel_size=[9, 1]) if len(x) > 9 else x - x.mean(axis=0)
    mag2 = (x ** 2).sum(axis=1)
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.01
    k = max(int(round(width_s / dt)), 1)
    return np.sqrt(np.convolve(mag2, np.ones(k) / k, mode="same"))


def _burst_ratio(t: np.ndarray, e: np.ndarray, bursts: list[tuple[float, float]], pad: float) -> list[float]:
    inside = np.zeros(len(t), bool)
    for ts, dur in bursts:
        inside |= (t >= ts - 0.05) & (t <= ts + dur + pad + 0.1)
    base = float(np.median(e[~inside])) if (~inside).sum() > 5 else float(np.median(e))
    out = []
    for ts, dur in bursts:
        sel = (t >= ts) & (t <= ts + dur + pad)
        out.append(float(e[sel].max() / max(base, 1e-9)) if sel.any() else 0.0)
    return out


def score(frame_t: np.ndarray, shifts: np.ndarray, imu: dict, haptics: list[dict], f_px: float) -> dict:
    it = np.asarray(imu.get("t", []), float)
    if len(it) < 50:
        return {"ok": False, "reason": "no motion sensor data was recorded"}
    gyro = np.asarray(imu["gyro"], float)
    accel = np.asarray(imu["accel"], float)
    bursts = [(float(h["ts"]), float(h.get("duration_s", 0.15))) for h in haptics]

    # 1. IMU feels the bursts. At 100 Hz the ~150+ Hz motor is aliased, but its energy is still there.
    e_imu = _energy(accel, it, 0.05)
    imu_ratio = _burst_ratio(it, e_imu, bursts, pad=0.03)

    # 2. Video jitters during the bursts.
    e_vid = _energy(shifts, frame_t, 0.05)
    vid_ratio = _burst_ratio(frame_t, e_vid, bursts, pad=0.03)

    # 3. Image motion follows the gyro. Integrate rotation between frames, then fit the 2x2 map
    # from (rot_x, rot_y) to (dx, dy): it absorbs axis conventions and mirroring.
    ang = np.vstack([np.zeros(3), np.cumsum(0.5 * (gyro[1:] + gyro[:-1]) * np.diff(it)[:, None], axis=0)])
    ang_f = np.stack([np.interp(frame_t, it, ang[:, k]) for k in range(3)], axis=1)
    pred = np.diff(ang_f[:, :2], axis=0, prepend=ang_f[:1, :2]) * f_px
    fs = 1.0 / float(np.median(np.diff(frame_t)))
    hi = min(12.0, 0.45 * fs)
    b, a = sps.butter(2, [0.5 / (fs / 2), hi / (fs / 2)], btype="band")
    inside = (frame_t >= it[0]) & (frame_t <= it[-1])
    motion_corr, gyro_px = None, None
    if inside.sum() > 60:
        P = sps.filtfilt(b, a, pred[inside], axis=0)
        M = sps.filtfilt(b, a, shifts[inside], axis=0)
        A, *_ = np.linalg.lstsq(P, M, rcond=None)
        fit = P @ A
        denom = np.sqrt((fit ** 2).sum() * (M ** 2).sum())
        motion_corr = float((fit * M).sum() / denom) if denom > 0 else 0.0
        gyro_px = float(np.sqrt((P ** 2).sum(axis=1)).mean())

    t0 = frame_t[0]
    return {
        "ok": True,
        "bursts": [{"ts": round(ts - t0, 3), "imu_ratio": round(i, 1), "video_ratio": round(v, 1)}
                   for (ts, _), i, v in zip(bursts, imu_ratio, vid_ratio)],
        "imu_detected": int(sum(r >= 4.0 for r in imu_ratio)),
        "video_detected": int(sum(r >= 2.5 for r in vid_ratio)),
        "n_bursts": len(bursts),
        "motion_corr": None if motion_corr is None else round(motion_corr, 3),
        "gyro_motion_px": None if gyro_px is None else round(gyro_px, 3),
        "plot": {
            "t_imu": np.round(it - t0, 3).tolist(),
            "imu": np.round(e_imu / max(e_imu.max(), 1e-9), 4).tolist(),
            "t_video": np.round(frame_t - t0, 3).tolist(),
            "video": np.round(e_vid / max(e_vid.max(), 1e-9), 4).tolist(),
            "bursts": [round(ts - t0, 3) for ts, _ in bursts],
        },
    }


def analyze(bundle) -> dict:
    meta = bundle.meta
    imu = meta.get("imu") or {}
    haptics = meta.get("haptics") or []
    if not isinstance(imu, dict) or not imu.get("t"):
        return {"ok": False, "reason": "no motion sensor data was recorded"}
    W = bundle.full_size[0]
    fov = np.deg2rad(float(meta["camera"].get("fov_deg", 46)))
    f_px = (W / 2) / np.tan(fov / 2)
    shifts = measure_video(bundle.video_path, bundle.n)
    return score(bundle.ts, shifts, imu, haptics, f_px)
