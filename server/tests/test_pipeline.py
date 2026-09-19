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
