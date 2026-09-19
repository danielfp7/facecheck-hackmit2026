"""Check 2: is the displayed shape and color mirrored in the cornea?

A cornea is a ~7.8 mm-radius convex mirror, so it shows a minified, left-right
flipped image of the screen. Diffuse surfaces (skin, a matte print) only follow
the *amount* of light; a specular surface follows *where* on the screen the light
is. That difference is how the eye is found without face landmarks, which don't
work when only one eye is in frame.
"""
from __future__ import annotations

import base64

import cv2
import numpy as np

from bundle import Bundle
from challenge import Challenge, COLORS, SHAPES, SHAPE_SPAN
from render import shape_mask, POSITION_Y

CORNEA_FOCAL_MM = 3.9          # R/2 for a 7.8 mm cornea
LOCALIZE_W = 540
SCALES = np.linspace(0.55, 1.7, 9)
ASPECTS = (0.65, 0.8, 1.0)     # off-axis compression of the reflection's height


def expected_glint_px(meta: dict, frame_w: int) -> tuple[float, float]:
    """(expected reflection width in source px, px per mm at the eye)."""
    d = float(meta.get("distance_mm", 76))
    fov = np.deg2rad(float(meta["camera"].get("fov_deg", 80)))
    px_per_mm = frame_w / (2 * d * np.tan(fov / 2))
    mag = CORNEA_FOCAL_MM / (d + CORNEA_FOCAL_MM)
    return float(meta["screen"].get("width_mm", 70)) * mag * px_per_mm, px_per_mm


def _assign(ts: np.ndarray, events, ch: Challenge, lag_s: float, guard: float) -> np.ndarray:
    """State index per frame (-1 settle, -2 unassigned/transition)."""
    out = np.full(len(ts), -2, dtype=int)
    bounds = [te for _, te in events] + [events[-1][1] + ch.states[-1].duration_s]
    for k, (si, _) in enumerate(events):
        a, b = bounds[k] + lag_s + guard, bounds[k + 1] + lag_s - guard
        out[(ts >= a) & (ts <= b)] = si
    return out


def _state_means(video_path, assign: np.ndarray, width: int | None = None,
                 box: tuple[int, int, int, int] | None = None) -> dict[int, np.ndarray]:
    """One pass over the video accumulating the mean RGB frame per state."""
    cap = cv2.VideoCapture(str(video_path))
    acc: dict[int, np.ndarray] = {}
    cnt: dict[int, int] = {}
    for si in assign:
        ok, frame = cap.read()
        if not ok:
            break
        if si == -2:
            continue
        if box is not None:
            x, y, w, h = box
            frame = frame[y:y + h, x:x + w]
        elif width is not None:
            hh = round(frame.shape[0] * width / frame.shape[1])
            frame = cv2.resize(frame, (width, hh), interpolation=cv2.INTER_AREA)
        f = frame[:, :, ::-1].astype(np.float32) / 255.0
        if si in acc:
            acc[si] += f
            cnt[si] += 1
        else:
            acc[si] = f.copy()
            cnt[si] = 1
    cap.release()
    return {si: acc[si] / cnt[si] for si in acc}


def _highpass(img: np.ndarray, sigma: float) -> np.ndarray:
    return img - cv2.GaussianBlur(img, (0, 0), sigma)


def localize(means: dict[int, np.ndarray], glint_px: float) -> dict:
    """Find where the image changes with the screen's *layout*, not just its level."""
    keys = sorted(means)
    lum = np.stack([means[k][:, :, :2].sum(axis=2) for k in keys])       # R+G, (K, h, w)
    hp = np.stack([_highpass(l, max(glint_px, 2.0)) for l in lum])
    level = lum.mean(axis=(1, 2))                                         # (K,)
    # Per-pixel fit hp = a + b*level; what's left is layout-dependent (specular).
    lc = level - level.mean()
    b = (hp * lc[:, None, None]).sum(axis=0) / max((lc ** 2).sum(), 1e-9)
    resid = hp - hp.mean(axis=0) - b[None] * lc[:, None, None]
    energy = cv2.GaussianBlur((resid ** 2).sum(axis=0), (0, 0), max(glint_px / 2, 1.5))

    peak = float(energy.max())
    floor = float(np.median(energy)) + 1e-12
    py, px = np.unravel_index(int(np.argmax(energy)), energy.shape)
    blob = (energy > floor + 0.35 * (peak - floor)).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(blob)
    lab = labels[py, px]
    x, y, w, h = stats[lab, :4] if lab > 0 else (px, py, 1, 1)
    return {"center": (int(px), int(py)), "bbox": (int(x), int(y), int(w), int(h)),
            "contrast": peak / floor}


def _templates(span_px: float):
    """Shape-only templates (mirror image is symmetric for all three shapes)."""
    out = []
    for s in SCALES:
        for a in ASPECTS:
            w = max(6, round(span_px * s))
            h = max(6, round(span_px * s * a))
            pad = max(2, round(0.2 * w))
            for shape in SHAPES:
                # Render on a square "screen" so the shape fills SHAPE_SPAN of it, then squash.
                side = round(w / SHAPE_SPAN)
                m = shape_mask(shape, "middle", side, side).astype(np.float32)
                ys, xs = np.where(m > 0)
                m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                m = cv2.resize(m, (w, max(4, round(m.shape[0] * h / m.shape[1]))), interpolation=cv2.INTER_AREA)
                m = cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
                out.append((shape, s, a, m))
    return out


def _jpeg_b64(rgb: np.ndarray, scale: int = 3) -> str:
    img = np.clip(rgb, 0, None)
    img = img / max(float(np.percentile(img, 99.5)), 1e-6)
    img = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    ok, buf = cv2.imencode(".jpg", img[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 90])
    return base64.b64encode(buf.tobytes()).decode()


def analyze(bundle: Bundle, ch: Challenge, lag_ms: float) -> dict:
    W, H = bundle.full_size
    glint_px, px_per_mm = expected_glint_px(bundle.meta, W)
    events = bundle.events()
    assign = _assign(bundle.ts, events, ch, lag_ms / 1000.0, guard=1.5 * bundle.frame_period)

    # Pass A: find the eye on reduced frames.
    k = LOCALIZE_W / W
    means_small = _state_means(bundle.video_path, assign, width=LOCALIZE_W)
    if len(means_small) < 4:
        return {"ok": False, "reason": "too few usable states"}
    loc = localize(means_small, glint_px * k)
    if loc["contrast"] < 6.0:
        return {"ok": False, "reason": "no eye reflection found", "contrast": round(loc["contrast"], 1)}

    # Geometry: a cornea minifies the screen; flat glass or a print does not.
    bx, by, bw, bh = loc["bbox"]
    measured_w_px = bw / k
    size_ratio = measured_w_px / glint_px
    geometry_ok = 0.35 <= size_ratio <= 2.5

    # Pass B: full-resolution crop around the reflection.
    half = int(max(2.2 * glint_px, 40))
    cx, cy = round(loc["center"][0] / k), round(loc["center"][1] / k)
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(W, cx + half), min(H, cy + half)
    box = (x0, y0, x1 - x0, y1 - y0)
    means = _state_means(bundle.video_path, assign, box=box)

    blacks = [means[s.index] for s in ch.states if s.shape is None and s.index in means]
    black = np.mean(blacks, axis=0) if blacks else np.zeros_like(next(iter(means.values())))

    span_px = SHAPE_SPAN * glint_px
    temps = _templates(span_px)
    per_state = []
    for s in ch.states:
        if s.shape is None or s.index not in means:
            continue
        d = means[s.index] - black
        fg = np.array(COLORS[s.shape_color if s.shape_color != "black" else s.background], np.float32)
        chan = d @ (fg / max(fg.sum(), 1))          # project on the lit color
        if s.shape_color == "black":
            chan = -chan                             # inverse polarity: dark shape on lit screen
        hp = _highpass(chan.astype(np.float32), glint_px)

        best: dict[str, tuple[float, tuple[int, int], np.ndarray]] = {}
        for shape, _, _, m in temps:
            if m.shape[0] >= hp.shape[0] or m.shape[1] >= hp.shape[1]:
                continue
            res = cv2.matchTemplate(hp, m, cv2.TM_CCOEFF_NORMED)
            _, v, _, p = cv2.minMaxLoc(res)
            if shape not in best or v > best[shape][0]:
                best[shape] = (float(v), p, m)
        if len(best) < 3:
            continue
        decoded = max(best, key=lambda q: best[q][0])
        v_true = best[s.shape][0]
        v_other = max(v for q, (v, _, _) in best.items() if q != s.shape)
        _, (mx, my), m = best[decoded]
        mask = m > 0.5
        region = d[my:my + m.shape[0], mx:mx + m.shape[1]]
        rgb = region[mask].mean(axis=0) if mask.any() else np.zeros(3)
        per_state.append({
            "state": s.index, "sent_shape": s.shape, "sent_color": s.shape_color,
            "sent_position": s.position, "decoded_shape": decoded,
            "score": round(v_true, 3), "margin": round(v_true - v_other, 3),
            "y": my + m.shape[0] / 2, "rgb": rgb,
            "crop_jpeg_b64": _jpeg_b64(means[s.index]),
        })

    if len(per_state) < 3:
        return {"ok": False, "reason": "reflection too small or blurred to read"}

    shape_acc = float(np.mean([p["decoded_shape"] == p["sent_shape"] for p in per_state]))
    shape_margin = float(np.mean([p["margin"] for p in per_state]))

    # Position: measured vertical location should follow the sent top/middle/bottom.
    ys = np.array([p["y"] for p in per_state])
    sent_y = np.array([POSITION_Y[p["sent_position"]] for p in per_state])
    position_corr = float(np.corrcoef(ys, sent_y)[0, 1]) if np.ptp(sent_y) > 0 and np.ptp(ys) > 0 else 0.0

    # Color from sequential differences of the red-vs-green balance (cast cancels).
    def balance(rgb):
        return float((rgb[0] - rgb[1]) / (abs(rgb[0]) + abs(rgb[1]) + 1e-6))
    sent_bal = {"red": balance(np.array(COLORS["red"], float)), "green": -1.0, "black": 0.0}
    mb = np.array([balance(p["rgb"]) for p in per_state])
    sb = np.array([sent_bal[p["sent_color"]] for p in per_state])
    dm, ds = np.diff(mb), np.diff(sb)
    keep = np.abs(ds) > 1e-3
    color_score = float((dm[keep] * ds[keep]).sum() / (np.linalg.norm(dm[keep]) * np.linalg.norm(ds[keep]) + 1e-9)) if keep.any() else 0.0

    for p in per_state:
        p.pop("rgb"); p.pop("y")
    return {
        "ok": True,
        "shape_accuracy": round(shape_acc, 3),
        "shape_margin": round(shape_margin, 3),
        "position_corr": round(position_corr, 3),
        "color_score": round(color_score, 3),
        "geometry_ok": bool(geometry_ok),
        "size_ratio": round(float(size_ratio), 2),
        "reflection_width_mm": round(float(measured_w_px / px_per_mm), 2),
        "contrast": round(loc["contrast"], 1),
        "roi": box,
        "states": per_state,
    }
