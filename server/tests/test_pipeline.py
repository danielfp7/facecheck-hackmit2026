"""End-to-end checks on synthetic captures with known ground truth."""
import json

import pytest

import bundle
import challenge
import synth
import verdict
from signals import cornea, lag


@pytest.fixture(scope="module")
def ch():
    return challenge.generate(seed="pytest")


@pytest.fixture(scope="module")
def cases(ch, tmp_path_factory):
    root = tmp_path_factory.mktemp("synth")
    specs = {
        "real": dict(lag_ms=60),
        "delayed": dict(lag_ms=260),
        "dead": dict(responsive=False),
        "flat": dict(lag_ms=5, flat_mirror=True),
        "noglint": dict(lag_ms=60, glint=False),
    }
    out = {}
    for name, kw in specs.items():
        v, m = synth.make(ch, root / name, **kw)
        out[name] = bundle.load(v, m)
    return out


def test_challenge_is_seizure_safe(ch):
    assert all(s.duration_s >= challenge.MIN_STATE_S for s in ch.states)
    # No pure red: R share of the "red" stays under the 0.8 saturated-red rule.
    r, g, b = challenge.COLORS["red"]
    assert r / (r + g + b) < 0.8


def test_challenge_roundtrip(ch):
    again = challenge.Challenge.from_dict(json.loads(json.dumps(ch.to_dict())))
    assert [s.shape for s in again.states] == [s.shape for s in ch.states]


def test_lag_recovered_within_a_frame(cases, ch):
    r = lag.analyze(cases["real"], ch)
    assert r["response_r2"] > 0.9
    assert abs(r["lag_ms"] - 60) < 1000 / 60


def test_added_delay_is_measured(cases, ch):
    real = lag.analyze(cases["real"], ch)["lag_ms"]
    slow = lag.analyze(cases["delayed"], ch)["lag_ms"]
    assert abs((slow - real) - 200) < 10


def test_unresponsive_video_has_no_response(cases, ch):
    assert lag.analyze(cases["dead"], ch)["response_r2"] < 0.2


def test_cornea_reads_shapes(cases, ch):
    l = lag.analyze(cases["real"], ch)
    r = cornea.analyze(cases["real"], ch, l["lag_ms"])
    assert r["ok"] and r["geometry_ok"] and r["inside_iris"]
    assert r["shape_readable"] and r["shape_accuracy"] >= 0.85
    assert r["position_corr"] > 0.8 and r["color_score"] > 0.8
    # The iris fit doubles as a ruler: synth draws a 70 px iris radius.
    assert abs(r["iris_radius_px"] - synth.IRIS_R) < 6


def test_flat_mirror_fails_geometry(cases, ch):
    l = lag.analyze(cases["flat"], ch)
    r = cornea.analyze(cases["flat"], ch, l["lag_ms"])
    assert not (r.get("ok") and r["geometry_ok"])


@pytest.mark.parametrize("name,expected,needle", [
    ("real", "verified", "live human"),
    ("delayed", "unverified", "delayed"),
    ("dead", "unverified", "no light response"),
    ("flat", "unverified", ""),
    ("noglint", "unverified", ""),
])
def test_verdicts(cases, ch, name, expected, needle):
    b = cases[name]
    l = lag.analyze(b, ch)
    c = cornea.analyze(b, ch, l["lag_ms"]) if l.get("ok") else {"ok": False}
    meta = dict(b.meta, device_model="synthetic")
    # Synthetic genuine lag is ~67 ms; the default 70 ms baseline applies.
    v = verdict.decide(l, c, {"similarity": 0.8}, meta)
    assert v["verdict"] == expected, v
    assert needle in v["reason"]


# ---------- heartbeat + vibration (pure signal tests, no video) ----------

def _rppg_meta(bpm=72.0, pulse_amp=0.004, seconds=8.0, fps=60, seed=1):
    import numpy as np
    rng = np.random.default_rng(seed)
    t = 500.0 + np.arange(int(seconds * fps)) / fps
    skin = np.array([0.62, 0.45, 0.38])
    beat = np.sin(2 * np.pi * bpm / 60 * t)
    # Blood volume changes absorb green most, then blue, then red.
    cells = []
    for c in range(24):
        base = skin * (0.85 + 0.3 * rng.random())
        cells.append(base * (1 + pulse_amp * beat[:, None] * np.array([0.35, 1.0, 0.6])) + rng.normal(0, 0.0012, (len(t), 3)))
    rgb = np.stack(cells, axis=1)
    rgb[:, 0] = [0.02, 0.02, 0.03]          # a dark background cell
    rgb[:, 1] = [0.99, 0.99, 0.99]          # a clipped cell
    return {"t": t.tolist(), "grid": [6, 4], "rgb": rgb.tolist()}


def test_rppg_recovers_heart_rate():
    from signals import rppg
    r = rppg.analyze(_rppg_meta(bpm=72))
    assert r["ok"] and abs(r["bpm"] - 72) < 4 and r["snr_db"] > 3


def test_rppg_print_has_no_pulse():
    from signals import rppg
    live = rppg.analyze(_rppg_meta(bpm=72))
    flat = rppg.analyze(_rppg_meta(pulse_amp=0.0))
    assert flat["ok"] and flat["snr_db"] < live["snr_db"] - 6


def _vibration_case(video_follows: bool, seed=2):
    import numpy as np
    rng = np.random.default_rng(seed)
    it = 100.0 + np.arange(0, 5.5, 0.01)
    gyro = np.stack([0.05 * np.sin(2 * np.pi * 1.3 * it), 0.04 * np.sin(2 * np.pi * 0.8 * it + 1), 0 * it], axis=1)
    gyro += rng.normal(0, 0.002, gyro.shape)
    accel = rng.normal(0, 0.003, (len(it), 3))
    haptics = [{"ts": 101.2, "duration_s": 0.15}, {"ts": 102.9, "duration_s": 0.15}, {"ts": 104.4, "duration_s": 0.15}]
    for h in haptics:
        sel = (it >= h["ts"]) & (it <= h["ts"] + 0.15)
        accel[sel] += rng.normal(0, 0.08, (sel.sum(), 3))
    ft = 100.0 + np.arange(0, 5.5, 1 / 60)
    f_px = 1280.0
    shifts = rng.normal(0, 0.03, (len(ft), 2))
    if video_follows:
        gy = np.stack([np.interp(ft, it, gyro[:, k]) for k in range(2)], axis=1)
        shifts += gy[:, ::-1] * f_px / 60 * np.array([1.0, -1.0])     # arbitrary axis convention
        for h in haptics:
            sel = (ft >= h["ts"]) & (ft <= h["ts"] + 0.15)
            shifts[sel] += rng.normal(0, 0.35, (sel.sum(), 2))
    imu = {"t": it.tolist(), "gyro": gyro.tolist(), "accel": accel.tolist()}
    return ft, shifts, imu, haptics, f_px


def test_vibration_genuine_camera_moves_with_phone():
    from signals import vibration
    r = vibration.score(*_vibration_case(video_follows=True))
    assert r["ok"] and r["imu_detected"] == 3 and r["video_detected"] >= 2 and r["motion_corr"] > 0.7


def test_vibration_injected_video_ignores_phone():
    from signals import vibration
    r = vibration.score(*_vibration_case(video_follows=False))
    assert r["imu_detected"] == 3 and r["video_detected"] == 0 and r["motion_corr"] < 0.3


# ---------- transit: the move from the selfie to the eye ----------

def _texture(seed, size=900):
    import cv2, numpy as np
    rng = np.random.default_rng(seed)
    img = cv2.GaussianBlur(rng.random((size, size, 3)).astype(np.float32), (0, 0), 2.0)
    img = (img - img.min()) / (img.max() - img.min())
    return (img * 255).astype(np.uint8)


def _move_in(tex, n, z0=1.0, z1=2.2):
    import cv2, numpy as np
    out = []
    for u in np.linspace(0, 1, n):
        z = z0 * (z1 / z0) ** u
        w, h = int(480 / z), int(640 / z)
        x0 = (tex.shape[1] - w) // 2 + int(6 * np.sin(5 * u)); y0 = (tex.shape[0] - h) // 2 + int(5 * np.cos(4 * u))
        out.append(cv2.resize(tex[y0:y0 + h, x0:x0 + w], (480, 640), interpolation=cv2.INTER_AREA))
    return out


def test_transit_continuous_move_has_no_cut():
    from signals import transit
    frames = _move_in(_texture(1), 30)
    r = transit.analyze(frames, [i * 0.1 for i in range(30)], None)
    assert r["ok"] and r["cuts"] == 0 and r["worst_gap_s"] < 0.2


def test_transit_detects_a_jump_to_another_scene():
    from signals import transit
    frames = _move_in(_texture(1), 15, 1.0, 1.5) + _move_in(_texture(2), 15, 1.5, 2.2)
    r = transit.analyze(frames, [i * 0.1 for i in range(30)], None)
    assert r["cuts"] == 1 and abs(r["cut_at_s"][0] - 1.5) < 0.11


def test_transit_flags_missing_frames():
    from signals import transit
    ts = [i * 0.1 for i in range(15)] + [3.0 + i * 0.1 for i in range(15)]
    r = transit.analyze(_move_in(_texture(1), 30), ts, None)
    assert r["worst_gap_s"] > 1.0


# ---------- webcam: auto-exposure can't be locked in a browser ----------

def test_lag_survives_auto_exposure(ch, tmp_path):
    v, m = synth.make(ch, tmp_path / "ae_real", lag_ms=90, auto_exposure=True)
    fast = lag.analyze(bundle.load(v, m), ch)
    v, m = synth.make(ch, tmp_path / "ae_slow", lag_ms=290, auto_exposure=True)
    slow = lag.analyze(bundle.load(v, m), ch)
    assert fast["mode"] == "chromaticity" and fast["response_r2"] > 0.8
    assert abs(fast["lag_ms"] - 90) < 25                    # within ~1.5 frames
    assert abs((slow["lag_ms"] - fast["lag_ms"]) - 200) < 20


def test_jpeg_container_reads_like_a_video(tmp_path):
    import struct
    import cv2
    import numpy as np
    blob = b""
    for i in range(5):
        img = np.full((48, 64, 3), 40 * i, np.uint8)
        jpg = cv2.imencode(".jpg", img)[1].tobytes()
        blob += struct.pack("<I", len(jpg)) + jpg
    path = tmp_path / "video.bin"
    path.write_bytes(blob)
    cap = bundle.open_frames(path)
    assert cap.isOpened() and int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) == 64
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    assert len(frames) == 5 and abs(int(frames[3].mean()) - 120) <= 2
