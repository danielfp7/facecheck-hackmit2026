"""Heartbeat from skin color (rPPG), POS algorithm (Wang et al., IEEE TBME 2017).

Input is what the phone samples during the steady-white window: per-frame mean RGB
over a grid of cells. Sending those instead of 8 more seconds of video keeps the
upload small.

What this signal is worth: it catches photos and masks. It does NOT catch a replayed
recording or a good face swap: both carry the pulse of the real person who was filmed
(Seibold et al., "High-quality deepfakes have a heart!", 2025). So it is shown, and
never decides the verdict on its own.
"""
from __future__ import annotations

import numpy as np
from scipy import signal as sps

BAND_HZ = (0.7, 3.0)       # 42-180 bpm


def _skin_cells(rgb: np.ndarray) -> np.ndarray:
    """Boolean mask over grid cells that are well exposed and steady. rgb: (N, C, 3).

    No colour-order test: white balance is locked while the screen is green, which leaves
    skin with a magenta cast (blue > green) during the white window. On a real capture a
    red > green > blue rule threw away 22 of 24 cells.
    """
    mean = rgb.mean(axis=0)
    luma = mean @ np.array([0.299, 0.587, 0.114])
    exposed = (luma > 0.25) & (mean.max(axis=1) < 0.93)             # not dark (hair, background), not clipped
    if not exposed.any():
        return exposed
    # Cells crossed by hair/eye/background edges swing with every small movement.
    wobble = rgb.std(axis=0).mean(axis=1) / np.maximum(luma, 1e-6)
    return exposed & (wobble <= 1.35 * np.median(wobble[exposed]))


def pos(rgb: np.ndarray, fs: float, window_s: float = 1.6) -> np.ndarray:
    """Plane-Orthogonal-to-Skin pulse signal from an (N, 3) RGB trace."""
    n = len(rgb)
    w = max(int(round(window_s * fs)), 8)
    h = np.zeros(n)
    P = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])
    for start in range(0, n - w + 1):
        block = rgb[start:start + w]
        cn = block / np.maximum(block.mean(axis=0), 1e-9)          # temporal normalisation
        s = cn @ P.T
        p = s[:, 0] + (s[:, 0].std() / max(s[:, 1].std(), 1e-9)) * s[:, 1]
        h[start:start + w] += p - p.mean()
    return h


def analyze(rppg_meta: dict | None) -> dict:
    if not rppg_meta or not rppg_meta.get("t"):
        return {"ok": False, "reason": "no heartbeat window was recorded"}
    t = np.asarray(rppg_meta["t"], float)
    rgb = np.asarray(rppg_meta["rgb"], float)                       # (N, C, 3)
    if rgb.ndim != 3 or len(t) != len(rgb) or len(t) < 120:
        return {"ok": False, "reason": "heartbeat window too short"}

    # Skip the first 0.7 s: the screen just changed and the hand is still settling.
    keep = t >= t[0] + 0.7
    t, rgb = t[keep], rgb[keep]
    dur = float(t[-1] - t[0])
    if dur < 4.0:
        return {"ok": False, "reason": "heartbeat window too short"}

    cells = _skin_cells(rgb)
    if cells.sum() < 2:
        return {"ok": False, "reason": "not enough steadily lit skin in view"}
    trace = rgb[:, cells].mean(axis=1)

    # Camera frames aren't perfectly periodic; resample to a uniform 30 Hz grid.
    fs = 30.0
    tu = np.arange(t[0], t[-1], 1 / fs)
    trace_u = np.stack([np.interp(tu, t, trace[:, c]) for c in range(3)], axis=1)

    pulse = pos(trace_u, fs)
    b, a = sps.butter(3, [BAND_HZ[0] / (fs / 2), BAND_HZ[1] / (fs / 2)], btype="band")
    pulse = sps.filtfilt(b, a, pulse)

    nfft = 8192
    f = np.fft.rfftfreq(nfft, 1 / fs)
    spec = np.abs(np.fft.rfft(pulse * np.hanning(len(pulse)), nfft)) ** 2
    band = (f >= BAND_HZ[0]) & (f <= BAND_HZ[1])
    f_peak = float(f[band][np.argmax(spec[band])])
    # SNR (de Haan): power near the peak and its first harmonic vs the rest of the band.
    near = band & ((np.abs(f - f_peak) <= 0.12) | (np.abs(f - 2 * f_peak) <= 0.12))
    snr_db = float(10 * np.log10(max(spec[near].sum(), 1e-20) / max(spec[band & ~near].sum(), 1e-20)))

    # Motion is the main way this goes wrong: report how much the raw trace moved.
    motion = float(np.std(np.diff(trace_u.mean(axis=1))) / max(trace_u.mean(), 1e-9))

    scale = np.abs(pulse).max() or 1.0
    return {
        "ok": True,
        "bpm": round(f_peak * 60, 1),
        "snr_db": round(snr_db, 2),
        "duration_s": round(dur, 2),
        "skin_cells": int(cells.sum()),
        "motion": round(motion, 5),
        "plot": {"t": np.round(tu - tu[0], 3).tolist(), "wave": np.round(pulse / scale, 4).tolist()},
    }
