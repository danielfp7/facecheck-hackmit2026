"""Continuity: is the face in the eye-check video the same person as the selfie?

Without this, an attacker could show a deepfake for the selfie (identity passes), then
switch it off and present their own real eye for the liveness checks.

Comparing the eye region itself does not work: measured on real captures, a person's
own eye scored 0.47-0.70 against their selfie while strangers' eyes scored up to 0.82.
What does work is face recognition on the liveness frames. At 4-6 inches the frame
still holds part of the face (an eye, nose, cheek). Face detectors fail on a face
cropped that hard, but Check 2 already knows where the eye is and, from the iris, its
scale, so the partial face can be aligned by hand into the recognition model's
template. Measured: same person 0.43-0.67, strangers <= 0.09.
"""
from __future__ import annotations

import cv2
import numpy as np

from signals import identity

# ArcFace's 112x112 alignment template: where the two eyes go. 35.2 px between the eyes
# corresponds to a typical 63 mm interpupillary distance.
EYE_SLOTS = {"left": (38.29, 51.70), "right": (73.53, 51.50)}
TEMPLATE_PX_PER_MM = 35.2 / 63.0
IRIS_DIAMETER_MM = 11.7


def _aligned(frame_rgb: np.ndarray, eye_xy: tuple[float, float], iris_r: float, slot: tuple[float, float]) -> np.ndarray:
    px_per_mm = 2 * iris_r / IRIS_DIAMETER_MM
    sc = TEMPLATE_PX_PER_MM / px_per_mm
    M = np.float32([[sc, 0, slot[0] - sc * eye_xy[0]], [0, sc, slot[1] - sc * eye_xy[1]]])
    img = np.clip(frame_rgb, 0, 1)
    # Liveness frames are lit by a black or colored screen; bring them to a normal exposure.
    med = float(np.median(img @ np.array([0.299, 0.587, 0.114], np.float32)))
    if med > 1e-3:
        img = np.clip(img * min(0.45 / med, 4.0), 0, 1)
    bgr = (img[:, :, ::-1] * 255).astype(np.uint8)
    return cv2.warpAffine(bgr, M, (112, 112), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_CONSTANT)


def _embed_aligned(bgr112: np.ndarray) -> np.ndarray:
    rec = identity._app().models["recognition"]
    e = rec.get_feat(bgr112).flatten()
    return e / (np.linalg.norm(e) + 1e-9)


def analyze(stash: dict, selfie_emb: np.ndarray | None, enrolled_emb: np.ndarray | None) -> dict:
    """`stash` is what cornea.analyze leaves behind: frames, iris fit, per-state eye offsets."""
    if not stash or "iris" not in stash:
        return {"ok": False, "reason": "no eye was found to anchor the comparison"}
    if selfie_emb is None:
        return {"ok": False, "reason": "no face found in the selfie"}

    k = stash["frame_scale"]                      # frames are stored at this scale of full-res
    icx, icy, ir = stash["iris"]
    x0, y0 = stash["origin"]
    # Reference (black) state plus every shape state, each with its own eye position.
    wanted = {stash["ref_state"]: (0.0, 0.0), **stash.get("offsets", {})}

    per_slot: dict[str, list[float]] = {name: [] for name in EYE_SLOTS}
    for si, (ox, oy) in wanted.items():
        frame = stash["frames"].get(si)
        if frame is None:
            continue
        eye = ((x0 + icx + ox) * k, (y0 + icy + oy) * k)
        for name, slot in EYE_SLOTS.items():
            emb = _embed_aligned(_aligned(frame, eye, ir * k, slot))
            per_slot[name].append(float(emb @ selfie_emb))
    if not any(per_slot.values()):
        return {"ok": False, "reason": "no frames available for the comparison"}

    # We don't know which eye is in view: the right slot is the one that scores higher.
    med = {name: float(np.median(v)) for name, v in per_slot.items() if v}
    slot = max(med, key=med.get)
    sims = np.array(per_slot[slot])
    out = {
        "ok": True,
        "similarity": round(float(np.median(sims)), 3),
        "best": round(float(sims.max()), 3),
        "frames": int(len(sims)),
        "eye_slot": slot,
    }
    if enrolled_emb is not None:
        frame = stash["frames"].get(stash["ref_state"])
        if frame is not None:
            eye = ((x0 + icx) * k, (y0 + icy) * k)
            emb = _embed_aligned(_aligned(frame, eye, ir * k, EYE_SLOTS[slot]))
            out["similarity_to_enrolled"] = round(float(emb @ enrolled_emb), 3)
    return out
