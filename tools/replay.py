"""Re-run the pipeline over saved captures and print one row per capture.

Every /verify call is saved under server/data/captures/<time>_<label>_<id>/. Record
several of each kind from the phone (labels: real, screen-attack, replay, print), then:

  uv run --project server tools/replay.py                  # table, grouped by label
  uv run --project server tools/replay.py --set-baseline   # store median genuine lag per device

Read the thresholds off the gap between `real` and the attack rows and put them in
server/verdict.py THRESHOLDS.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER_DIR))

import bundle as bundle_mod  # noqa: E402
import challenge as challenge_mod  # noqa: E402
import verdict as verdict_mod  # noqa: E402
from signals import cornea, lag  # noqa: E402

CAPTURES = SERVER_DIR / "data" / "captures"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", help="only captures with this label")
    ap.add_argument("--set-baseline", action="store_true",
                    help="write median lag of 'real' captures per device model to baselines.json")
    ap.add_argument("--shape-mode", default="shape", choices=["shape", "layout"])
    args = ap.parse_args()

    rows = []
    for d in sorted(CAPTURES.glob("*")):
        videos = list(d.glob("video.*"))
        if not videos or not (d / "meta.json").exists():
            continue
        label = d.name.split("_")[1] if d.name.count("_") >= 2 else "?"
        if args.label and label != args.label:
            continue
        meta = json.loads((d / "meta.json").read_text())
        ch = challenge_mod.Challenge.from_dict(json.loads((d / "challenge.json").read_text()))
        b = bundle_mod.load(videos[0], meta)
        l = lag.analyze(b, ch)
        c = cornea.analyze(b, ch, l["lag_ms"]) if l.get("ok") else {"ok": False}
        v = verdict_mod.decide(l, c, {"similarity": 1.0}, meta, args.shape_mode)   # identity left out here
        rows.append((label, meta.get("device_model", "?"), d.name, l, c, v))

    fmt = "{:14} {:>7} {:>6} {:>6} {:>6} {:>6} {:>6} {:>6}  {:12} {}"
    print(fmt.format("label", "lag_ms", "jit", "r2", "shape", "pos", "color", "size", "verdict", "capture"))
    for label, _, name, l, c, v in sorted(rows, key=lambda r: r[0]):
        g = lambda d, k: "-" if d.get(k) is None else (f"{d[k]:.2f}" if isinstance(d[k], float) else str(d[k]))
        print(fmt.format(label, g(l, "lag_ms"), g(l, "lag_jitter_ms"), g(l, "response_r2"),
                         g(c, "shape_accuracy"), g(c, "position_corr"), g(c, "color_score"),
                         g(c, "size_ratio"), v["verdict"], name))

    if args.set_baseline:
        by_device = defaultdict(list)
        for label, device, _, l, _, _ in rows:
            if label == "real" and l.get("ok") and l["response_r2"] > 0.5:
                by_device[device].append(l["lag_ms"])
        if not by_device:
            sys.exit("no usable 'real' captures to calibrate from")
        path = verdict_mod.BASELINES
        table = json.loads(path.read_text()) if path.exists() else {}
        for device, lags in by_device.items():
            table[device] = round(statistics.median(lags), 1)
            print(f"baseline {device}: {table[device]} ms from {len(lags)} captures "
                  f"(range {min(lags):.0f}-{max(lags):.0f})")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(table, indent=2))


if __name__ == "__main__":
    main()
