"""Transit: watch the phone travel from the arm's-length selfie to the eye.

The phone keeps ~10 small frames per second from the selfie until the flashes start.
Comparing only the two endpoints (selfie vs eye-check frames) leaves the middle
unobserved; this checks the whole move:

  1. Identity held: wherever a face is still detectable it must be the selfie person.
     A confidently different face at any point fails.
  2. One continuous view: each frame must look like the previous one, allowing for
     the zoom and drift of moving closer. A jump to another scene (phone swung from a
     laptop screen to a real face, a video source switched) fails, and so does a hole
     in the timestamps.
  3. The last frame must connect to the first frame of the eye-check video.

continuity.py still does the final link (partial-face recognition on the eye-check
frames), which covers the last stretch where the face is too cropped to detect.
"""
from __future__ import annotations

import struct

import cv2
import numpy as np

from signals import identity

THUMB_W = 192
DETAIL_SIGMA = 4.0
ZOOMS = (0.85, 0.92, 1.0, 1.08, 1.17, 1.27)     # frame-to-frame scale change when moving in
# Links are correlations of fine detail. Measured on real footage: continuous >= 0.70;
# a cut from one person to another 0.11-0.18. Coarse appearance was tried first and is
# useless: any close-up face lines up with any other (0.77-0.97 across a cut).
CUT_NCC = 0.20          # an isolated link below this is a jump to another view
CLEAR_NCC = 0.50        # neighbours must be at least this clear for a drop to count as isolated
BLUR_NCC = 0.30         # a run of links below this is motion/focus blur, not evidence
MAX_BLUR_S = 1.0
MAX_GAP_S = 0.6
SAME_PERSON = 0.30
OTHER_PERSON = 0.12


def unpack(blob: bytes) -> list[np.ndarray]:
    """Frames from the phone's container: repeated [uint32 little-endian length][JPEG]."""
    frames, i = [], 0
    while i + 4 <= len(blob):
        (n,) = struct.unpack_from("<I", blob, i)
        i += 4
        if n == 0 or i + n > len(blob):
            break
        img = cv2.imdecode(np.frombuffer(blob, np.uint8, n, i), cv2.IMREAD_COLOR)
        i += n
        if img is not None:
            frames.append(img)
    return frames


def _thumb(bgr: np.ndarray) -> np.ndarray:
    """Fine detail only (brow hairs, lashes, moles, hair strands): that is what differs
    between people and between sittings."""
    h = round(bgr.shape[0] * THUMB_W / bgr.shape[1])
    g = cv2.cvtColor(cv2.resize(bgr, (THUMB_W, h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g.astype(np.float32), (0, 0), 1.0)
    return g - cv2.GaussianBlur(g, (0, 0), DETAIL_SIGMA)


def _zoom(img: np.ndarray, z: float) -> np.ndarray:
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 0, z)
    return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)


def same_view(a: np.ndarray, b: np.ndarray) -> float:
    """Best normalised correlation between thumbnails a -> b over zoom and shift."""
    h, w = a.shape
    my, mx = int(h * 0.18), int(w * 0.18)
    best = -1.0
    for z in ZOOMS:
        core = _zoom(a, z)[my:h - my, mx:w - mx]           # centre of a, searched for inside b
        best = max(best, float(cv2.matchTemplate(b, core, cv2.TM_CCOEFF_NORMED).max()))
    return best


def analyze(frames: list[np.ndarray], ts: list[float], selfie_emb: np.ndarray | None,
            first_video_frame: np.ndarray | None = None, video_start_ts: float | None = None) -> dict:
    n = min(len(frames), len(ts))
    if n < 5:
        return {"ok": False, "reason": "the move from the selfie to the eye was not recorded"}
    frames, t = frames[:n], np.asarray(ts[:n], float)

    # 2. one continuous view
    thumbs = [_thumb(f) for f in frames]
    links = [same_view(thumbs[i], thumbs[i + 1]) for i in range(n - 1)]
    gaps = np.diff(t)
    worst_gap = float(gaps.max())
    # A hole in the frames is only a problem if the view doesn't match across it. If it
    # does (measured 0.83 across a real 9 s recording dropout), nothing changed unseen;
    # a swap during the hole shows up as a weak link and as a different face afterwards.
    unbridged = [float(g) for g, v in zip(gaps, links) if g > MAX_GAP_S and v < CLEAR_NCC]
    # A cut is an isolated collapse between two clear stretches. A run of weak links is
    # blur from moving or refocusing, which says nothing either way.
    def clear(j: int) -> bool:
        return j < 0 or j >= len(links) or links[j] >= CLEAR_NCC
    cuts = [i for i, v in enumerate(links) if v < CUT_NCC and clear(i - 1) and clear(i + 1)]
    blur_s, run = 0.0, 0.0
    for v, g in zip(links, gaps):
        run = run + float(g) if v < BLUR_NCC else 0.0
        blur_s = max(blur_s, run)

    # 3. hand-over to the eye-check video
    handover = None
    if first_video_frame is not None:
        handover = same_view(thumbs[-1], _thumb(first_video_frame))
        if video_start_ts is not None:
            join = float(video_start_ts - t[-1])
            worst_gap = max(worst_gap, join)
            if join > MAX_GAP_S and handover < CLEAR_NCC:
                unbridged.append(join)

    # 1. identity held while a face is detectable (every 2nd frame keeps this fast)
    sims: list[tuple[int, float]] = []
    if selfie_emb is not None:
        app = identity._app()
        for i in range(0, n, 2):
            faces = app.get(frames[i])
            if not faces:
                continue
            f = max(faces, key=lambda q: (q.bbox[2] - q.bbox[0]) * (q.bbox[3] - q.bbox[1]))
            if f.det_score >= 0.6:
                sims.append((i, float(np.dot(f.normed_embedding, selfie_emb))))
    vals = np.array([s for _, s in sims]) if sims else np.array([])
    strangers = [i for i, s in sims if s < OTHER_PERSON]

    return {
        "ok": True,
        "frames": n,
        "duration_s": round(float(t[-1] - t[0]), 2),
        "min_link": round(float(min(links)), 3),
        "median_link": round(float(np.median(links)), 3),
        "cuts": len(cuts),
        "cut_at_s": [round(float(t[i + 1] - t[0]), 2) for i in cuts[:3]],
        "worst_gap_s": round(worst_gap, 2),
        "unbridged_gap_s": round(max(unbridged), 2) if unbridged else 0.0,
        "longest_blur_s": round(blur_s, 2),
        "handover": None if handover is None else round(handover, 3),
        "faces_seen": len(sims),
        "identity_min": None if not len(vals) else round(float(vals.min()), 3),
        "identity_median": None if not len(vals) else round(float(np.median(vals)), 3),
        "identity_held": bool(len(vals) > 0 and np.mean(vals >= SAME_PERSON) >= 0.8 and not strangers),
        "stranger_frames": len(strangers),
    }
