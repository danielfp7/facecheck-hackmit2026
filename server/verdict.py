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
    # Browser + webcam pipelines are slower and vary more; calibrate with replay.py --set-baseline.
    "lag_default_baseline_web_ms": 130.0,
    "shape_accuracy_min": 0.6,    # chance is 0.33 with three shapes
    "position_corr_min": 0.7,
    "color_score_min": 0.5,
    # With everything centred, colour is the challenge, so it has to clear a higher bar.
    # Measured on real captures: genuine 0.72-1.00, and a face swap cannot mirror the screen
    # at all, so it never gets a colour sequence to score.
    "color_score_alone_min": 0.62,
    "face_similarity_min": 0.35,
    "max_dropped_frames": 6,
    # Partial face in the eye-check frames vs the selfie. Measured: same person
    # 0.43-0.67, strangers <= 0.09.
    "continuity_min": 0.25,
    "max_selfie_to_check_s": 25.0,
    "transit_max_blur_s": 1.0,
}


def baseline_ms(device_model: str) -> float:
    if BASELINES.exists():
        table = json.loads(BASELINES.read_text())
        if device_model in table:
            return float(table[device_model])
    key = "lag_default_baseline_web_ms" if device_model.startswith("web") else "lag_default_baseline_ms"
    return THRESHOLDS[key]


def _tile(name: str, status: str, headline: str, detail: str = "") -> dict:
    return {"name": name, "status": status, "headline": headline, "detail": detail}


def decide(lag: dict, cornea: dict, identity: dict, meta: dict, shape_mode: str = "auto",
           continuity: dict | None = None, vibration: dict | None = None,
           transit: dict | None = None) -> dict:
    """shape_mode: 'auto' scores the outline only when the reflection is large enough to
    read it; 'shape' always does; 'layout' never does (position + color only)."""
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
        why = cornea.get("reason", "no eye reflection found")
        if why == "no eye reflection found":
            why += (" (lean in closer to the camera)" if str(meta.get("device_model", "")).startswith("web")
                    else " (hold the phone closer, with one eye in the outline)")
        failures.append(why)
        tiles.append(_tile("Eye reflection", "red", "Not found", why))
    else:
        # The outline only counts when the reflection spans enough pixels to read it;
        # position and color always count.
        # Shapes are centred now, so usually there is no position to read and the colour
        # sequence carries the challenge. Older captures that moved the shape still score it.
        use_pos = cornea.get("position_varied") and cornea.get("position_corr") is not None
        pos_ok = not use_pos or cornea["position_corr"] >= T["position_corr_min"]
        col_ok = cornea["color_score"] >= (T["color_score_min"] if use_pos else T["color_score_alone_min"])
        # The outline is reported but never decisive on its own. Measured on real captures it
        # reads 43-100% correct against 33% for a guess: real evidence, too noisy to reject a
        # person on. It is a few dozen pixels of a blurred mirror image, and how well it reads
        # depends on eye shape, lashes and how wide the eye is open. The colour sequence is
        # what an attacker would have to reproduce, and that reads 0.70-0.91 on real captures.
        readable = shape_mode == "shape" or (shape_mode == "auto" and cornea.get("shape_readable"))
        shape_acc = cornea.get("shape_accuracy")
        use_shape = readable and use_pos            # only the old position protocol gates on it
        shape_ok = not use_shape or (shape_acc or 0) >= T["shape_accuracy_min"]
        summary = f"color {cornea['color_score']:.2f}"
        if use_pos:
            summary = f"position {cornea['position_corr']:.2f}, " + summary
        if readable and shape_acc is not None:
            summary = f"shapes {shape_acc:.0%}, " + summary
        where = f"{cornea['reflection_width_mm']:.1f} mm wide at {cornea['distance_mm']:.0f} mm"
        if not cornea["geometry_ok"]:
            if not cornea.get("inside_iris", True):
                failures.append("the reflection is not inside an iris")
            else:
                failures.append(f"reflection is {cornea['size_ratio']:.1f}x the size a cornea would give (flat screen or print)")
            tiles.append(_tile("Eye reflection", "red", "Not an eye",
                               f"{where}; a cornea gives ~{cornea['expected_width_mm']:.1f} mm"))
        elif not (shape_ok and pos_ok and col_ok):
            what = [n for n, ok in (("shape", shape_ok), ("position", pos_ok), ("color", col_ok)) if not ok]
            failures.append("eye reflection does not match the displayed " + "/".join(what))
            tiles.append(_tile("Eye reflection", "red", "Mismatch", summary))
        else:
            head = (f"{cornea['position_accuracy']:.0%} of positions read" if use_pos
                    else f"{cornea['color_score']:.0%} colour match")
            tiles.append(_tile("Eye reflection", "green", head, f"{summary}; {where}"))

    # Identity
    if identity.get("similarity") is None:
        unverifiable.append(identity.get("reason", "no face found in the selfie"))
        tiles.append(_tile("Face match", "yellow", "No face", identity.get("reason", "")))
    elif identity["similarity"] < T["face_similarity_min"]:
        failures.append("selfie does not match the enrolled face")
        tiles.append(_tile("Face match", "red", f"{identity['similarity']:.2f}", f"needs {T['face_similarity_min']:.2f}"))
    else:
        tiles.append(_tile("Face match", "green", f"{identity['similarity']:.2f}", f"needs {T['face_similarity_min']:.2f}"))

    # Continuity: the eye check must show the same person as the selfie, in one sitting.
    session = meta.get("session")
    if session:
        gap = float(session.get("challenge_start_ts", 0)) - float(session.get("selfie_ts", 0))
        if int(session.get("interruptions", 0)) > 0:
            failures.append("the app was left or the camera was interrupted between the selfie and the eye check")
        elif gap > T["max_selfie_to_check_s"] or gap < 0:
            failures.append(f"too long between the selfie and the eye check ({gap:.0f} s)")
    if continuity is not None:
        if not continuity.get("ok"):
            tiles.append(_tile("Continuity", "yellow", "Not checked", continuity.get("reason", "")))
            if cornea.get("ok"):
                unverifiable.append(continuity.get("reason", "continuity could not be checked"))
        elif continuity["similarity"] < T["continuity_min"]:
            failures.append("the face in the eye check is not the person in the selfie")
            tiles.append(_tile("Continuity", "red", f"{continuity['similarity']:.2f}",
                               f"eye-check frames vs selfie, needs {T['continuity_min']:.2f}"))
        else:
            detail = f"same person in selfie and eye check ({continuity['frames']} frames)"
            status = "green"
            if transit is not None and transit.get("ok"):
                detail += (f"; watched {transit['frames']} frames of the move, face matched in "
                           f"{transit['faces_seen']}, no jumps" if not transit["cuts"] else "")
                if not transit["identity_held"] and not transit["stranger_frames"]:
                    status = "yellow"
            tiles.append(_tile("Continuity", status, f"{continuity['similarity']:.2f}", detail))

    # Transit: the move from the selfie to the eye, watched frame by frame.
    if transit is not None:
        if not transit.get("ok"):
            unverifiable.append(transit.get("reason", "the move to the eye was not recorded"))
        elif transit["stranger_frames"] > 0:
            failures.append("a different face appeared between the selfie and the eye check")
        elif transit["cuts"] > 0:
            failures.append(f"the camera view jumped {transit['cut_at_s'][0]:.1f} s after the selfie (not one continuous move)")
        elif transit.get("unbridged_gap_s", 0) > 0:
            failures.append(f"{transit['unbridged_gap_s']:.1f} s of camera frames are missing between the selfie and the eye check, "
                            "and the view is different afterwards")
        elif transit["faces_seen"] < 2:
            unverifiable.append("no face was visible right after the selfie")
        elif transit["longest_blur_s"] > T["transit_max_blur_s"]:
            unverifiable.append("the move to the eye was too fast to follow; bring the phone in steadily")
        if transit.get("ok") and any(t["name"] == "Continuity" for t in tiles) and (
                transit["stranger_frames"] or transit["cuts"] or transit.get("unbridged_gap_s", 0) > 0):
            for t in tiles:
                if t["name"] == "Continuity":
                    t.update(status="red", headline="Broken", detail=failures[-1])

    # Vibration: informational until thresholds are set from real-vs-attack captures.
    if vibration is not None:
        if not vibration.get("ok"):
            tiles.append(_tile("Vibration", "yellow", "Not measured", vibration.get("reason", "")))
        else:
            n = vibration["n_bursts"]
            detail = f"sensor felt {vibration['imu_detected']}/{n}, camera saw {vibration['video_detected']}/{n}"
            if vibration.get("motion_corr") is not None:
                detail += f", video-gyro agreement {vibration['motion_corr']:.2f}"
            # We commanded the bursts, so whether the 100 Hz motion sensor resolved them is only a
            # cross-check (sharp bursts are above what it can follow). What matters is whether
            # the *camera* shook at those instants, or image motion follows the gyro.
            if vibration["video_detected"] >= max(1, n - 1) or (vibration.get("motion_corr") or 0) >= 0.5:
                tiles.append(_tile("Vibration", "green", "Camera moves with phone", detail))
            else:
                tiles.append(_tile("Vibration", "yellow", "Camera shake unclear", detail))

    if failures:
        verdict, reason = "unverified", failures[0]
    elif unverifiable:
        verdict, reason = "unverifiable", unverifiable[0]
    else:
        verdict, reason = "verified", "live human, matching the enrolled face"
    return {"verdict": verdict, "reason": reason, "all_reasons": failures + unverifiable, "tiles": tiles}
