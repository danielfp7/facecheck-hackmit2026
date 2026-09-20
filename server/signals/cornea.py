"""Check 2: is the displayed shape, position and color mirrored in the cornea?

A cornea is a ~7.8 mm-radius convex mirror, so it shows a tiny, left-right flipped
image of the screen sitting inside the dark iris. The pipeline:

1. Find the eye: in every shape state, look for a small bright blob of the displayed
   color on a dark background. Only an eye produces one in the same neighbourhood in
   every state (face landmarks don't work this close; the face is cropped).
2. Fit the iris around it. Irises are ~11.7 mm across in everyone, so the fit doubles
   as a ruler: it gives px/mm at the eye and therefore the true distance.
3. Register every state to the iris (the eye drifts more between states than the
   distances being measured), then read the reflection's position, color and, when
   it spans enough pixels, its outline.
4. Geometry: the reflection must sit inside the iris and be cornea-sized. A flat
   screen or a print reflects at a completely different scale.
"""
from __future__ import annotations

import base64

import cv2
import numpy as np

from bundle import Bundle, open_frames
from challenge import Challenge, COLORS, SHAPES, SHAPE_SPAN
from render import shape_mask, POSITION_Y

CORNEA_FOCAL_MM = 3.9          # R/2 for a 7.8 mm cornea
IRIS_DIAMETER_MM = 11.7
LOCALIZE_W = 1080              # localisation runs with the frame's short side at most this
DRIFT_PX = 50                  # eye drift tolerated between states, at LOCALIZE_W scale. 70 was tried
                               # and locks onto the wrong spot on a real capture; don't widen without data.
CROP_HALF = 260                # eye crop half-size, at LOCALIZE_W scale
MIN_READABLE_SPAN_PX = 18      # below this the outline can't be told apart; score layout only
SCALES = np.linspace(0.6, 1.6, 8)
ASPECTS = (0.7, 0.85, 1.0)     # off-axis compression of the reflection's height
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def _blur(img: np.ndarray, sigma: float) -> np.ndarray:
    return cv2.GaussianBlur(img, (0, 0), sigma)


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
    cap = open_frames(video_path)
    acc: dict[int, np.ndarray] = {}
    cnt: dict[int, int] = {}
    for si in assign:
        ok, frame = cap.read()
        if not ok:
            break
        si = int(si)
        if si == -2:
            continue
        if box is not None:
            x, y, w, h = box
            frame = frame[y:y + h, x:x + w]
        elif width is not None and width != frame.shape[1]:
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


def _lit_color(state) -> np.ndarray:
    fg = np.array(COLORS[state.shape_color if state.shape_color != "black" else state.background], np.float32)
    return fg / max(float(fg.sum()), 1.0)


def _nearest_black(ch: Challenge, means: dict, idx: int) -> int | None:
    blacks = [s.index for s in ch.states if s.shape is None and s.index in means]
    return min(blacks, key=lambda b: abs(b - idx)) if blacks else None


def _glint_response(lit: np.ndarray, black: np.ndarray, state, scale: float) -> tuple[np.ndarray, np.ndarray]:
    """(score map, lit-color increment D). High where a compact blob of the displayed
    color appears on a dark background; smooth skin shading and bright skin score ~0."""
    D = np.clip((lit - black) @ _lit_color(state), 0, None)
    s = scale
    dog = np.maximum(_blur(D, 3 * s) - _blur(D, 7.5 * s), _blur(D, 8 * s) - _blur(D, 20 * s))
    base = _blur(black @ LUMA, 12 * s)
    dark = np.clip(1 - base / 0.45, 0, 1)
    return np.clip(dog, 0, None) * dark, D


def _kasa(P: np.ndarray) -> tuple[float, float, float]:
    A = np.c_[2 * P[:, 0], 2 * P[:, 1], np.ones(len(P))]
    (a, c, d), *_ = np.linalg.lstsq(A, (P ** 2).sum(axis=1), rcond=None)
    return float(a), float(c), float(np.sqrt(max(d + a * a + c * c, 1e-9)))


def fit_iris(gray: np.ndarray, seed: tuple[float, float], rmin: float, rmax: float):
    """Circle through the iris/sclera edge, from rays cast over the lower arc only
    (the upper lid hides the top). Returns (cx, cy, r) or None."""
    g = _blur(gray, 2.5)
    h, w = g.shape
    cx, cy = seed
    fit = None
    for _ in range(3):
        pts = []
        for ang in np.deg2rad(np.arange(-25, 206, 6)):
            r = np.arange(rmin, rmax)
            xs, ys = cx + r * np.cos(ang), cy + r * np.sin(ang)   # image y points down
            ok = (xs >= 1) & (xs < w - 1) & (ys >= 1) & (ys < h - 1)
            if ok.sum() < 12:
                continue
            grad = np.gradient(g[ys[ok].astype(int), xs[ok].astype(int)])
            if grad.max() <= 0:
                continue
            k = int(np.argmax(grad >= 0.6 * grad.max()))          # first strong dark->bright edge
            pts.append((xs[ok][k], ys[ok][k]))
        if len(pts) < 12:
            return fit
        P = np.array(pts)
        for _ in range(3):                                         # trim outliers
            a, c, rad = _kasa(P)
            err = np.abs(np.hypot(P[:, 0] - a, P[:, 1] - c) - rad)
            keep = err <= max(2.0, np.percentile(err, 75))
            if keep.sum() < 10:
                break
            P = P[keep]
        a, c, rad = _kasa(P)
        err = np.abs(np.hypot(P[:, 0] - a, P[:, 1] - c) - rad)
        if not (rmin <= rad <= rmax) or np.median(err) > 0.08 * rad:
            return fit
        fit = (a, c, rad)
        cx, cy = a, c
    if fit is None:
        return None
    # An iris is darker than what surrounds it.
    a, c, rad = fit
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.hypot(xx - a, yy - c)
    lower = yy > c                                                  # ignore the lid/lash side
    inside = g[(rr < 0.8 * rad) & lower]
    ring = g[(rr > 1.15 * rad) & (rr < 1.6 * rad) & lower]
    if len(inside) < 20 or len(ring) < 20 or np.median(inside) > 0.8 * np.median(ring):
        return None
    return fit


def _templates(span_px: float):
    out = []
    for s in SCALES:
        for a in ASPECTS:
            w = max(6, round(span_px * s))
            pad = max(2, round(0.25 * w))
            for shape in SHAPES:
                side = round(w / SHAPE_SPAN)
                m = shape_mask(shape, "middle", side, side).astype(np.float32)
                ys, xs = np.where(m > 0)
                m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                m = cv2.resize(m, (w, max(4, round(m.shape[0] * a * w / m.shape[1]))), interpolation=cv2.INTER_AREA)
                out.append((shape, cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)))
    return out


def _jpeg_b64(rgb: np.ndarray, size: int = 220) -> str:
    img = np.clip(rgb, 0, None)
    img = img / max(float(np.percentile(img, 99.7)), 1e-6)
    img = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_CUBIC)
    _, buf = cv2.imencode(".jpg", img[:, :, ::-1], [cv2.IMWRITE_JPEG_QUALITY, 88])
    return base64.b64encode(buf.tobytes()).decode()


def _shift_crop(img: np.ndarray, cx: float, cy: float, half: int) -> np.ndarray:
    """Square crop centred on (cx, cy) with sub-pixel accuracy."""
    M = np.float32([[1, 0, half - cx], [0, 1, half - cy]])
    return cv2.warpAffine(img, M, (2 * half, 2 * half), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def _measure_glint(p: dict, gx: int, gy: int, fs: float) -> dict:
    """Sub-pixel centre, size and colour of the blob at (gx, gy)."""
    D, q = p["D"], int(round(10 * fs))
    y0, x0 = max(gy - q, 0), max(gx - q, 0)
    patch = D[y0:gy + q + 1, x0:gx + q + 1]
    blob = patch >= 0.5 * patch.max() if patch.size and patch.max() > 0 else np.zeros_like(patch, bool)
    if not blob.any():
        return {"g": (float(gx), float(gy)), "diameter": 0.0, "rgb": np.zeros(3), "peak": 0.0}
    yy, xx = np.nonzero(blob)
    wts = patch[blob]
    rgb = p["diff"][y0:gy + q + 1, x0:gx + q + 1][blob].mean(axis=0)
    return {"g": (x0 + float((xx * wts).sum() / wts.sum()), y0 + float((yy * wts).sum() / wts.sum())),
            "diameter": float(2.0 * np.sqrt(blob.sum() / np.pi)), "rgb": rgb,
            "peak": float(p["score"][gy, gx])}


def _eye_hint(meta: dict, k: float, bundle, ch, assign) -> tuple[float, float] | None:
    """Where the client's face tracker saw the eye, at LOCALIZE_W scale.

    meta["eye_track"] holds one entry per recorded frame: [x, y, iris_radius] in
    full-resolution video pixels, or null where the tracker lost the face. Only frames
    belonging to a shape state count: people are still moving in on the early frames, and
    a median over all of them lands between where they started and where they ended up.
    """
    track = meta.get("eye_track") or []
    if len(track) < 5:
        return None
    lit = {s.index for s in ch.states if s.shape is not None}
    pts = [e for i, e in enumerate(track)
           if e and len(e) >= 2 and i < len(assign) and assign[i] in lit]
    if len(pts) < 5:                       # fall back to every frame that tracked
        pts = [e for e in track if e and len(e) >= 2]
    if len(pts) < 5:
        return None
    cx, cy = np.median(np.array([[float(e[0]), float(e[1])] for e in pts]), axis=0)
    return cx * k, cy * k


def analyze(bundle: Bundle, ch: Challenge, lag_ms: float, stash: dict | None = None) -> dict:
    """`stash`, if given, receives the reference eye crop and iris fit for the continuity check."""
    W, H = bundle.full_size
    meta = bundle.meta
    events = bundle.events()
    assign = _assign(bundle.ts, events, ch, lag_ms / 1000.0, guard=1.5 * bundle.frame_period)
    shape_states = [s for s in ch.states if s.shape is not None]

    # ---- 1. find the eye on frames at most LOCALIZE_W wide
    k = min(1.0, LOCALIZE_W / min(W, H))     # short side: a landscape webcam frame is not shrunk
    lw = round(W * k)
    means = _state_means(bundle.video_path, assign, width=lw)
    usable = [s for s in shape_states if s.index in means and _nearest_black(ch, means, s.index) is not None]
    if len(usable) < 4:
        return {"ok": False, "reason": "too few usable states"}

    R = DRIFT_PX
    acc = None
    responses = {}
    for s in usable:
        score, _ = _glint_response(means[s.index], means[_nearest_black(ch, means, s.index)], s, 1.0)
        responses[s.index] = score
        spread = cv2.dilate(np.sqrt(score), np.ones((2 * R + 1, 2 * R + 1), np.uint8))
        acc = spread if acc is None else acc + spread

    def probe(px: int, py: int):
        """Strongest reflection near (px, py) per state, and how many states show a real one."""
        found, glints = 0, []
        for s in usable:
            score = responses[s.index]
            y0, x0 = max(py - R, 0), max(px - R, 0)
            win = score[y0:py + R + 1, x0:px + R + 1]
            if win.size == 0:
                glints.append((px, py))
                continue
            wy, wx = np.unravel_index(int(np.argmax(win)), win.shape)
            glints.append((x0 + wx, y0 + wy))
            if win.max() > 3.0 * (np.percentile(score, 99.9) + 1e-9):
                found += 1
        return found, glints

    # First try the spot whose brightness follows the flashes, which is what a cornea does.
    need = max(3, len(usable) // 2)
    py, px = np.unravel_index(int(np.argmax(acc)), acc.shape)
    found, glints = probe(int(px), int(py))

    # If that search came up short, try where the client's face tracker says the eye is.
    # It fails on faint reflections and reports "no eye reflection found" with the eye in
    # plain view, which is the single biggest cause of genuine users being turned away.
    # Only ever a second chance: a fake with no reflection still finds nothing here.
    hinted = False
    if found < need:
        hint = _eye_hint(meta, k, bundle, ch, assign)
        if hint is not None:
            hx = int(np.clip(hint[0], 0, acc.shape[1] - 1))
            hy = int(np.clip(hint[1], 0, acc.shape[0] - 1))
            f2, g2 = probe(hx, hy)
            if f2 > found:
                found, glints, hinted = f2, g2, True
    if found < need:
        return {"ok": False, "reason": "no eye reflection found", "states_with_reflection": found}
    ex, ey = np.median(np.array(glints), axis=0)      # eye position at LOCALIZE_W scale

    # ---- 2. full-resolution eye crops
    half = int(round(CROP_HALF / k))
    cx, cy = int(round(ex / k)), int(round(ey / k))
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(W, cx + half), min(H, cy + half)
    if k < 1:
        crops = _state_means(bundle.video_path, assign, box=(x0, y0, x1 - x0, y1 - y0))
    else:
        crops = {si: m[y0:y1, x0:x1] for si, m in means.items()}
    frames_lw = means
    seed = (cx - x0, cy - y0)
    fs = 1.0 / k                                      # px scale relative to LOCALIZE_W

    ref_idx = _nearest_black(ch, crops, usable[len(usable) // 2].index)
    ref = crops[ref_idx]
    ref_gray = (ref @ LUMA).astype(np.float32)

    # Glint per state, in crop coordinates. First pass: anywhere near the eye, which is
    # only good enough to seed the iris fit (the median shrugs off a bad state).
    per = []
    for s in usable:
        black = crops[_nearest_black(ch, crops, s.index)]
        score, D = _glint_response(crops[s.index], black, s, fs)
        r = int(R * fs)
        ya, xa = max(int(seed[1]) - r, 0), max(int(seed[0]) - r, 0)
        win = score[ya:int(seed[1]) + r + 1, xa:int(seed[0]) + r + 1]
        wy, wx = np.unravel_index(int(np.argmax(win)), win.shape)
        p = {"s": s, "D": D, "score": score, "diff": crops[s.index] - black}
        p.update(_measure_glint(p, xa + wx, ya + wy, fs))
        per.append(p)

    # Coarse size check before anything else: flat glass or a print reflects far too large.
    seed_med = np.median(np.array([p["g"] for p in per]), axis=0)
    # Smallest believable iris, from the distance the client asked for (people hold it up to
    # ~2x further). A fixed small minimum lets the fit lock onto the pupil edge instead,
    # which reads as twice the true distance.
    fov = np.deg2rad(float(meta["camera"].get("fov_deg", 46)))
    asked_px_per_mm = W / (2 * float(meta.get("distance_mm", 120)) * np.tan(fov / 2))
    rmin = max(12.0, 0.3 * (IRIS_DIAMETER_MM / 2) * asked_px_per_mm)
    iris = fit_iris(ref_gray, (float(seed_med[0]), float(seed_med[1])), rmin=rmin, rmax=140 * fs)

    if iris is not None:
        px_per_mm = 2 * iris[2] / IRIS_DIAMETER_MM
        distance_mm = W / (2 * px_per_mm * np.tan(fov / 2))
    else:
        distance_mm = float(meta.get("distance_mm", 120))
        px_per_mm = W / (2 * distance_mm * np.tan(fov / 2))
    mag = CORNEA_FOCAL_MM / (distance_mm + CORNEA_FOCAL_MM)
    # Phones draw the shape at SHAPE_SPAN of the screen width; the web client, on a wide
    # screen, sizes it from the height instead and says so.
    screen = meta.get("screen", {})
    span_mm = float(screen.get("shape_span_mm") or SHAPE_SPAN * float(screen.get("width_mm", 65)))
    span_px = span_mm * mag * px_per_mm
    measured_px = float(np.median([p["diameter"] for p in per]))
    # Blur and pixelation put a floor of a few px under any measured blob.
    size_ratio = measured_px / max(span_px, 4.0 * fs)

    if iris is None:
        reason = ("reflection is far too large for a cornea (flat screen or print)" if size_ratio > 4
                  else "found a reflection but no iris around it")
        return {"ok": False, "reason": reason, "size_ratio": round(size_ratio, 2), "geometry_ok": False}

    # ---- 3. register every state to the reference iris
    icx, icy, ir = iris
    if stash is not None:
        stash.update(iris=iris, origin=(x0, y0), ref_state=ref_idx, frames=frames_lw, frame_scale=k, offsets={})
    T = int(min(1.5 * ir, min(ref_gray.shape) / 2 - 12 * fs))
    tx, ty = int(round(icx)), int(round(icy))
    tx = int(np.clip(tx, T, ref_gray.shape[1] - T))
    ty = int(np.clip(ty, T, ref_gray.shape[0] - T))
    tmpl = ref_gray[ty - T:ty + T, tx - T:tx + T]
    states_out, us, vs = [], [], []
    temps = _templates(span_px) if span_px >= MIN_READABLE_SPAN_PX else []
    for p in per:
        s = p["s"]
        gray = (crops[s.index] @ LUMA).astype(np.float32)
        res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
        _, _, _, loc = cv2.minMaxLoc(res)
        ox, oy = loc[0] - (tx - T), loc[1] - (ty - T)          # how far the eye moved vs reference
        # Second pass: a corneal reflection is inside the iris, so only look there. Without
        # this a blink sends the search to whatever else is bright nearby (seen on a real
        # capture: one state landed 2.3 iris radii away and sank an otherwise perfect read).
        yy, xx = np.ogrid[:gray.shape[0], :gray.shape[1]]
        disk = (xx - (icx + ox)) ** 2 + (yy - (icy + oy)) ** 2 <= (0.95 * ir) ** 2
        inside = np.where(disk, p["score"], 0.0)
        gy, gx = np.unravel_index(int(np.argmax(inside)), inside.shape)
        p["peak_anywhere"] = p["peak"]
        p.update(_measure_glint(p, int(gx), int(gy), fs))
        if stash is not None:
            stash["offsets"][s.index] = (ox, oy)
        u = (p["g"][0] - ox - icx) / ir                          # reflection position in iris radii
        v = (p["g"][1] - oy - icy) / ir
        us.append(u); vs.append(v)

        decoded_shape, score, margin = None, None, None
        if temps:
            q = int(round(1.2 * span_px))
            view = _shift_crop(p["D"], p["g"][0], p["g"][1], q)
            view = view - _blur(view, span_px)
            best: dict[str, float] = {}
            for shape, m in temps:
                if m.shape[0] >= view.shape[0] or m.shape[1] >= view.shape[1]:
                    continue
                val = float(cv2.matchTemplate(view, m, cv2.TM_CCOEFF_NORMED).max())
                best[shape] = max(best.get(shape, -1.0), val)
            if len(best) == 3:
                decoded_shape = max(best, key=best.get)
                score = best[s.shape]
                margin = score - max(val for q_, val in best.items() if q_ != s.shape)

        view_half = int(round(1.35 * ir))
        states_out.append({
            "state": s.index, "sent_shape": s.shape, "sent_color": s.shape_color,
            "sent_position": s.position, "decoded_shape": decoded_shape or "?",
            "score": round(score, 3) if score is not None else 0.0,
            "margin": round(margin, 3) if margin is not None else 0.0,
            "u": round(float(u), 3), "v": round(float(v), 3),
            "crop_jpeg_b64": _jpeg_b64(_shift_crop(crops[s.index], icx + ox, icy + oy, view_half)),
        })

    us, vs = np.array(us), np.array(vs)
    sent_y = np.array([POSITION_Y[p["s"].position] for p in per])
    # A state only counts if its reflection is there: a blink leaves nothing in the iris, and
    # whatever noise is found instead must not vote. Compared within a colour, since the
    # orange-red reflection is always fainter than the green one.
    peaks = np.array([p["peak"] for p in per])
    valid = np.zeros(len(per), bool)
    for colour in {p["s"].shape_color for p in per}:
        idx = np.array([i for i, p in enumerate(per) if p["s"].shape_color == colour])
        valid[idx] = peaks[idx] >= 0.25 * np.median(peaks[idx])
    for so, ok in zip(states_out, valid):
        so["valid"] = bool(ok)
    if valid.sum() < max(4, int(np.ceil(0.6 * len(per)))) or np.ptp(sent_y[valid]) == 0:
        return {"ok": False, "reason": "the eye reflection was missing in too many flashes (keep the eye open and still)",
                "valid_states": int(valid.sum())}

    # Phones place the shape top/middle/bottom; a wide laptop screen has no vertical room,
    # so the web client places it left/middle/right and the reflection moves along x.
    # A cornea mirrors left-right and browsers deliver the camera unmirrored, so a shape on the
    # screen's left shows up on the image's right: the relationship along x is negative.
    # Measured -0.994 on a real Safari run. Requiring the sign halves what a guess can score.
    axis = screen.get("position_axis", "y")
    along, across = (us, vs) if axis == "x" else (vs, us)
    position_corr = float(np.corrcoef(along[valid], sent_y[valid])[0, 1]) if np.ptp(along[valid]) > 1e-6 else 0.0
    position_corr_signed = position_corr
    if axis == "x":
        position_corr = -position_corr
    # Decode each state's level from the fitted line, for the results tile.
    slope, icpt = np.polyfit(sent_y[valid], along[valid], 1)
    levels = {name: icpt + slope * y for name, y in POSITION_Y.items()}
    for so, v in zip(states_out, along):
        so["decoded_position"] = min(levels, key=lambda n: abs(levels[n] - v))
    shape_readable = bool(temps) and all(so["decoded_shape"] != "?" for so in states_out)
    counted = [so for so in states_out if so["valid"]]
    shape_acc = float(np.mean([so["decoded_shape"] == so["sent_shape"] for so in counted])) if shape_readable else None
    for so in states_out:
        ok_pos = so.get("decoded_position") == so["sent_position"]
        so["match"] = bool(so["valid"] and ok_pos and (not shape_readable or so["decoded_shape"] == so["sent_shape"]))

    # Color from sequential differences of the red-vs-green balance, so a color cast cancels.
    def balance(rgb):
        return float((rgb[0] - rgb[1]) / (abs(rgb[0]) + abs(rgb[1]) + 1e-6))
    sent_bal = {"red": balance(np.array(COLORS["red"], float)), "green": -1.0, "black": 0.0}
    mb = np.array([balance(p["rgb"]) for p, ok in zip(per, valid) if ok])
    sb = np.array([sent_bal[p["s"].shape_color] for p, ok in zip(per, valid) if ok])
    dm, ds = np.diff(mb), np.diff(sb)
    keep = np.abs(ds) > 1e-3
    color_score = float((dm[keep] * ds[keep]).sum() / (np.linalg.norm(dm[keep]) * np.linalg.norm(ds[keep]) + 1e-9)) if keep.any() else 0.0

    # The search above is confined to the iris, so ask instead whether the strongest blob
    # found *anywhere* near the eye was that same one. For a flat screen or print it isn't.
    same_blob = np.array([p["peak"] >= 0.5 * p["peak_anywhere"] for p in per])
    inside_iris = bool(same_blob[valid].mean() >= 0.6)
    geometry_ok = bool(inside_iris and 0.3 <= size_ratio <= 3.0)
    return {
        "ok": True,
        "shape_readable": shape_readable,
        "shape_accuracy": None if shape_acc is None else round(shape_acc, 3),
        "position_corr": round(position_corr, 3),
        "position_accuracy": round(float(np.mean([so["decoded_position"] == so["sent_position"] for so in counted])), 3),
        "valid_states": int(valid.sum()),
        "color_score": round(color_score, 3),
        "geometry_ok": geometry_ok,
        "inside_iris": inside_iris,
        "size_ratio": round(float(size_ratio), 2),
        "reflection_width_mm": round(float(measured_px / px_per_mm), 2),
        "expected_width_mm": round(float(span_px / px_per_mm), 2),
        "expected_span_px": round(float(span_px), 1),
        "iris_radius_px": round(float(ir), 1),
        "distance_mm": round(float(distance_mm)),
        "position_axis": axis,
        "position_corr_signed": round(position_corr_signed, 3),
        "x_spread": round(float(np.std(across[valid])), 3),
        "states": states_out,
    }
