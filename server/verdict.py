"""Fuse the signals into verified / unverified / unverifiable, each with a reason.

Thresholds are starting points; replace them with values read off real-vs-attack
captures (see tools/replay.py) before the demo.
"""
from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"
BASELINES = DATA / "baselines.json"

THRESHOLDS = {
    "response_r2_min": 0.5,       # below: face doesn't follow the screen's light
    "diff_score_min": 0.5,
    # Genuine lag is display + camera pipeline, calibrated per device model.
    # Literature puts an adaptive deepfake pipeline at +150-300 ms end to end,
    # and genuine jitter at 1-2 frames, so +100 ms sits between the two.
    "lag_margin_ms": 100.0,
    "lag_default_baseline_ms": 70.0,
    "shape_accuracy_min": 0.6,    # chance is 0.33 with three shapes
    "position_corr_min": 0.5,
    "color_score_min": 0.5,
    "face_similarity_min": 0.35,
    "max_dropped_frames": 6,
}


def baseline_ms(device_model: str) -> float:
    if BASELINES.exists():
        table = json.loads(BASELINES.read_text())
        if device_model in table:
            return float(table[device_model])
    return THRESHOLDS["lag_default_baseline_ms"]


def _tile(name: str, status: str, headline: str, detail: str = "") -> dict:
    return {"name": name, "status": status, "headline": headline, "detail": detail}


def decide(lag: dict, cornea: dict, identity: dict, meta: dict, shape_mode: str = "shape") -> dict:
    """shape_mode: 'shape' scores the outline; 'layout' scores position + color only
    (fixed-focus front cameras can't resolve the outline at close range)."""
    T = THRESHOLDS
    tiles, failures, unverifiable = [], [], []

    if len(meta.get("dropped", [])) > T["max_dropped_frames"]:
        unverifiable.append("too many dropped camera frames")

    # Light response + lag
    if not lag.get("ok"):
        unverifiable.append(lag.get("reason", "light response could not be measured"))
        tiles.append(_tile("Light response", "yellow", "Not measured", lag.get("reason", "")))
    else:
        base = baseline_ms(meta.get("device_model", ""))
        limit = base + T["lag_margin_ms"]
        if lag["overexposed"]:
            unverifiable.append("too much ambient light to see the screen's effect")
            tiles.append(_tile("Light response", "yellow", "Overexposed"))
        elif lag["response_r2"] < T["response_r2_min"] or (lag["diff_score"] or 0) < T["diff_score_min"]:
            failures.append("no light response: the face did not follow the screen's colors")
            tiles.append(_tile("Light response", "red", "No response", f"match {lag['response_r2']:.2f}"))
        elif lag["lag_ms"] > limit:
            over = lag["lag_ms"] - base
            failures.append(f"response delayed by {over:.0f} ms beyond this phone's camera latency")
            tiles.append(_tile("Light response", "red", f"Lag {lag['lag_ms']:.0f} ms",
                               f"limit {limit:.0f} ms (baseline {base:.0f} + {T['lag_margin_ms']:.0f})"))
        else:
            tiles.append(_tile("Light response", "green", f"Lag {lag['lag_ms']:.0f} ms",
                               f"match {lag['response_r2']:.2f}, limit {limit:.0f} ms"))

    # Corneal reflection
    if not cornea.get("ok"):
        failures.append(cornea.get("reason", "no eye reflection found"))
        tiles.append(_tile("Eye reflection", "red", "Not found", cornea.get("reason", "")))
    else:
        shape_ok = shape_mode == "layout" or cornea["shape_accuracy"] >= T["shape_accuracy_min"]
        pos_ok = cornea["position_corr"] >= T["position_corr_min"]
        col_ok = cornea["color_score"] >= T["color_score_min"]
        if not cornea["geometry_ok"]:
            failures.append(f"reflection is {cornea['size_ratio']:.0f}x too large for a cornea (flat screen or print)")
            tiles.append(_tile("Eye reflection", "red", "Not an eye",
                               f"{cornea['reflection_width_mm']:.1f} mm wide, cornea gives ~3.4 mm"))
        elif not (shape_ok and pos_ok and col_ok):
            what = [n for n, ok in (("shape", shape_ok), ("position", pos_ok), ("color", col_ok)) if not ok]
            failures.append("eye reflection does not match the displayed " + "/".join(what))
            tiles.append(_tile("Eye reflection", "red", "Mismatch",
                               f"shapes {cornea['shape_accuracy']:.0%}, position {cornea['position_corr']:.2f}, color {cornea['color_score']:.2f}"))
        else:
            tiles.append(_tile("Eye reflection", "green", f"Shapes {cornea['shape_accuracy']:.0%}",
                               f"position {cornea['position_corr']:.2f}, color {cornea['color_score']:.2f}"))

    # Identity
    if identity.get("similarity") is None:
        unverifiable.append(identity.get("reason", "no face found in the selfie"))
        tiles.append(_tile("Face match", "yellow", "No face", identity.get("reason", "")))
    elif identity["similarity"] < T["face_similarity_min"]:
        failures.append("selfie does not match the enrolled face")
        tiles.append(_tile("Face match", "red", f"{identity['similarity']:.2f}", f"needs {T['face_similarity_min']:.2f}"))
    else:
        tiles.append(_tile("Face match", "green", f"{identity['similarity']:.2f}", f"needs {T['face_similarity_min']:.2f}"))

    if failures:
        verdict, reason = "unverified", failures[0]
    elif unverifiable:
        verdict, reason = "unverifiable", unverifiable[0]
    else:
        verdict, reason = "verified", "live human, matching the enrolled face"
    return {"verdict": verdict, "reason": reason, "all_reasons": failures + unverifiable, "tiles": tiles}
