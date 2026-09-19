"""Check 1: does the face respond to the screen's light, and how late?

Skin lit by the screen follows the displayed color with no physical delay; the
only genuine lag is display + camera pipeline, calibrated per device model. A
pipeline that has to see the flash, re-render and inject adds 150-300 ms on top.
"""
from __future__ import annotations

import numpy as np

from bundle import Bundle
from challenge import Challenge, COLORS

LAG_GRID_MS = np.arange(-60.0, 600.0, 2.0)
SPECULAR_DROP = 0.05  # brightest fraction of pixels ignored per frame


def diffuse_trace(small: np.ndarray) -> np.ndarray:
    """Per-frame mean RGB over diffuse pixels only, shape (N, 3).

    The brightest pixels are dropped so a mirror-like bounce (a glossy laptop
    screen reflecting our flashes at zero lag) can't pass as a skin response.
    """
    n = small.shape[0]
    flat = small.reshape(n, -1, 3)
    luma = flat @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    k = int(flat.shape[1] * (1 - SPECULAR_DROP))
    idx = np.argpartition(luma, k - 1, axis=1)[:, :k]
    kept = np.take_along_axis(flat, idx[:, :, None], axis=1)
    return kept.mean(axis=1)


def _state_rgb(ch: Challenge, state_index: int) -> np.ndarray:
    if state_index < 0:
        return np.array(COLORS[ch.settle_color], dtype=np.float64) / 255.0
    return np.array(ch.states[state_index].emitted_rgb(), dtype=np.float64)


class Expected:
    """The sent sequence as a step function, integrated over a frame window."""

    def __init__(self, ch: Challenge, events: list[tuple[int, float]]):
        self.t = np.array([t for _, t in events])
        self.rgb = np.stack([_state_rgb(ch, i) for i, _ in events])  # (K, 3)
        # Integral of the step function at the knots, for box averaging.
        dt = np.diff(self.t)
        self.cum = np.vstack([np.zeros(3), np.cumsum(self.rgb[:-1] * dt[:, None], axis=0)])

    def _integral(self, t: np.ndarray) -> np.ndarray:
        k = np.clip(np.searchsorted(self.t, t, side="right") - 1, 0, len(self.t) - 1)
        return self.cum[k] + self.rgb[k] * (t - self.t[k])[:, None]

    def sample(self, t: np.ndarray, window: float) -> np.ndarray:
        """Mean emitted RGB over [t - window/2, t + window/2], shape (N, 3)."""
        return (self._integral(t + window / 2) - self._integral(t - window / 2)) / window


def _fit_r2(m: np.ndarray, e: np.ndarray) -> tuple[float, np.ndarray]:
    """Per-channel m = a + b*e with b >= 0; pooled R^2 over channels.

    Pooling unnormalised residuals keeps a channel with no signal (blue) from
    dominating the score with its noise.
    """
    mc = m - m.mean(axis=0)
    ec = e - e.mean(axis=0)
    var_e = (ec ** 2).sum(axis=0)
    b = np.where(var_e > 1e-12, (mc * ec).sum(axis=0) / np.maximum(var_e, 1e-12), 0.0)
    b = np.maximum(b, 0.0)
    resid = ((mc - ec * b) ** 2).sum()
    total = (mc ** 2).sum()
    return (1.0 - resid / total if total > 1e-12 else 0.0), b


def _best_lag(m: np.ndarray, ts: np.ndarray, exp: Expected, window: float,
              grid_ms: np.ndarray = LAG_GRID_MS) -> tuple[float, float, np.ndarray]:
    scores = np.array([_fit_r2(m, exp.sample(ts - lag / 1000.0, window))[0] for lag in grid_ms])
    i = int(np.argmax(scores))
    lag = float(grid_ms[i])
    # Parabolic refinement around the peak.
    if 0 < i < len(scores) - 1:
        y0, y1, y2 = scores[i - 1], scores[i], scores[i + 1]
        denom = y0 - 2 * y1 + y2
        if abs(denom) > 1e-12:
            lag += float(0.5 * (y0 - y2) / denom * (grid_ms[1] - grid_ms[0]))
    _, gains = _fit_r2(m, exp.sample(ts - lag / 1000.0, window))
    return lag, float(scores[i]), gains


def analyze(bundle: Bundle, ch: Challenge) -> dict:
    events = bundle.events()
    ts = bundle.ts
    window = bundle.frame_period
    exp = Expected(ch, events)

    # Only score frames inside the challenge (plus a tail for late responses).
    t0, t1 = events[0][1], events[-1][1] + ch.states[-1].duration_s
    mask = (ts >= t0) & (ts <= t1 + 0.6)
    m_all = diffuse_trace(bundle.small)
    m, t = m_all[mask], ts[mask]
    if len(t) < 10:
        return {"ok": False, "reason": "too few frames inside the challenge window"}

    lag_ms, r2, gains = _best_lag(m, t, exp, window)

    # Per-transition lags from a local fit, for jitter.
    per = []
    for _, te in events[1:]:
        loc = (t >= te - 0.25) & (t <= te + 0.25 + max(lag_ms, 0) / 1000.0)
        if loc.sum() >= 6 and np.ptp(m[loc]) > 1e-4:
            l, s, _ = _best_lag(m[loc], t[loc], exp, window)
            if s > 0.5:
                per.append(l)
    per = np.array(per)
    jitter_ms = float(np.median(np.abs(per - np.median(per)))) if len(per) >= 3 else None

    # Tab 1's color score: sequential color *differences*, so a room color cast cancels.
    lag_s = lag_ms / 1000.0
    plateaus, sent = [], []
    bounds = [te for _, te in events] + [t1]
    for k, (si, te) in enumerate(events):
        a, b_ = bounds[k] + lag_s + window, bounds[k + 1] + lag_s - window
        sel = (t >= a) & (t <= b_)
        if sel.sum() >= 2:
            plateaus.append(m[sel].mean(axis=0))
            sent.append(_state_rgb(ch, si))
    diff_score = None
    if len(plateaus) >= 3:
        # Compare against the sent differences as the skin would show them (per-channel
        # gain applied). Dividing the measurement by the gains instead would blow up
        # noise in a channel the screen barely drives, such as blue.
        dm = np.diff(np.array(plateaus), axis=0)
        de = np.diff(np.array(sent), axis=0) * gains
        keep = np.linalg.norm(de, axis=1) > 1e-3
        num = (dm[keep] * de[keep]).sum(axis=1)
        den = np.linalg.norm(dm[keep], axis=1) * np.linalg.norm(de[keep], axis=1) + 1e-12
        diff_score = float(np.mean(num / den))

    expected_at_lag = exp.sample(t - lag_s, window) * gains + (m.mean(axis=0) - (exp.sample(t - lag_s, window) * gains).mean(axis=0))
    return {
        "ok": True,
        "lag_ms": round(lag_ms, 1),
        "lag_jitter_ms": None if jitter_ms is None else round(jitter_ms, 1),
        "response_r2": round(r2, 3),
        "diff_score": None if diff_score is None else round(diff_score, 3),
        "overexposed": bool(m.mean() > 0.92),
        "plot": {
            "t": np.round(t - t0, 4).tolist(),
            "measured": np.round(m, 4).tolist(),
            "expected": np.round(expected_at_lag, 4).tolist(),
        },
    }
