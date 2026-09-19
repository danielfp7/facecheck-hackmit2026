"""Mac stand-in for the phone: run a challenge on this screen + webcam and upload it.

  uv run --project server tools/mac_capture.py --user daniel --enroll     # once
  uv run --project server tools/mac_capture.py --user daniel              # genuine run
  uv run --project server tools/mac_capture.py --user daniel --attack-delay-ms 200
  uv run --project server tools/mac_capture.py --user daniel --swap-source victim.jpg
  uv run --project server tools/mac_capture.py --synthetic --lag-ms 260   # no camera needed

Attack modes model an injection pipeline: each frame is stamped when it would
*arrive* at the app, i.e. after the attacker's processing, which is what shows up
as extra lag in Check 1. `--swap-source` runs the real inswapper model per frame,
so the delay is this machine's actual face-swap latency.

The webcam can't lock exposure and its reflection in the eye is only a few pixels,
so use this for the pipeline and the lag check, not for tuning Check 2.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import cv2
import httpx
import numpy as np

SERVER_DIR = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(SERVER_DIR))
sys.path.insert(0, str(SERVER_DIR / "tests"))

import challenge as challenge_mod  # noqa: E402
from render import render_color, render_state  # noqa: E402

WIN = "InHuman challenge"


def load_swapper(source_path: str):
    """inswapper from Deep-Live-Cam's models folder, plus the source identity."""
    import insightface
    from insightface.app import FaceAnalysis
    model = Path(__file__).resolve().parents[1] / "attack/Deep-Live-Cam/models/inswapper_128_fp16.onnx"
    if not model.exists():
        sys.exit(f"missing {model}; run attack/setup.sh first")
    providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    # The source face needs a full analysis once; per frame the swapper only needs detection.
    full = FaceAnalysis(name="buffalo_l", providers=providers)
    full.prepare(ctx_id=0, det_size=(640, 640))
    fa = FaceAnalysis(name="buffalo_l", providers=providers, allowed_modules=["detection"])
    fa.prepare(ctx_id=0, det_size=(640, 640))
    swapper = insightface.model_zoo.get_model(str(model), providers=providers)
    src_faces = full.get(cv2.imread(source_path))
    if not src_faces:
        sys.exit("no face in --swap-source image")
    src = src_faces[0]

    def swap(frame):
        for f in fa.get(frame):
            frame = swapper.get(frame, f, src, paste_back=True)
        return frame
    return swap


def capture(ch: challenge_mod.Challenge, args) -> tuple[Path, dict, bytes]:
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        sys.exit("cannot open webcam (grant camera permission to your terminal)")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    swap = load_swapper(args.swap_source) if args.swap_source else None

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    sw, sh = args.screen

    # Warm up and take the "arm's-length selfie" with the preview visible.
    t_end = time.monotonic() + 2.0
    selfie = None
    while time.monotonic() < t_end:
        ok, frame = cap.read()
        if ok:
            selfie = frame
            cv2.imshow(WIN, cv2.flip(frame, 1))
            cv2.waitKey(1)
    if selfie is None:
        sys.exit("webcam returned no frames")
    if swap:
        selfie = swap(selfie)
    selfie_jpg = cv2.imencode(".jpg", selfie)[1].tobytes()

    # Schedule: settle color, then the states.
    plan = [(-1, ch.settle_s)] + [(s.index, s.duration_s) for s in ch.states]
    images = {-1: render_color(ch.settle_color, sw, sh)[:, :, ::-1]}
    for s in ch.states:
        images[s.index] = render_state(s, sw, sh)[:, :, ::-1]

    frames, frame_ts, events = [], [], []
    start = time.monotonic()
    boundaries = np.cumsum([d for _, d in plan])
    total = float(boundaries[-1]) + 0.7
    shown = None
    while (now := time.monotonic() - start) < total:
        k = min(int(np.searchsorted(boundaries, now, side="right")), len(plan) - 1)
        if plan[k][0] != shown:
            shown = plan[k][0]
            cv2.imshow(WIN, images[shown])
            cv2.waitKey(1)
            events.append({"state_index": shown, "ts": time.monotonic()})
        ok, frame = cap.read()
        if not ok:
            continue
        if swap:
            frame = swap(frame)
        if args.attack_delay_ms:
            time.sleep(args.attack_delay_ms / 1000.0)
        frames.append(frame)
        frame_ts.append(time.monotonic())   # arrival time, after any attacker processing
    cap.release()
    cv2.destroyAllWindows()

    h, w = frames[0].shape[:2]
    fps = len(frames) / (frame_ts[-1] - frame_ts[0])
    out = Path(tempfile.mkdtemp(prefix="inhuman_")) / "video.mp4"
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), round(fps), (w, h))
    for f in frames:
        vw.write(f)
    vw.release()

    meta = {
        "schema": 1, "challenge_id": ch.id,
        "device_model": "mac-webcam" + ("-attack" if (swap or args.attack_delay_ms) else ""),
        "frames": frame_ts, "dropped": [], "display_events": events,
        "camera": {"width": w, "height": h, "fps": fps, "fov_deg": 60.0, "mirrored": False,
                   "iso": 0, "exposure_s": 0, "focus_locked": False, "exposure_locked": False, "min_focus_mm": -1},
        "screen": {"brightness": 1.0, "width_mm": 300, "height_mm": 190},
        "distance_mm": 400, "imu": [], "haptics": [],
    }
    print(f"captured {len(frames)} frames at {fps:.1f} fps")
    return out, meta, selfie_jpg


def synthetic(ch: challenge_mod.Challenge, args) -> tuple[Path, dict, bytes | None]:
    import synth
    out = Path(tempfile.mkdtemp(prefix="inhuman_synth_"))
    v, m = synth.make(ch, out, lag_ms=args.lag_ms, responsive=not args.dead, flat_mirror=args.flat)
    selfie = Path(args.selfie).read_bytes() if args.selfie else None
    return v, json.loads(m.read_text()), selfie


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="daniel")
    ap.add_argument("--enroll", action="store_true", help="enroll this user's face and exit")
    ap.add_argument("--request-id", help="answer a pending 2FA request; default: pick up the user's pending one")
    ap.add_argument("--label", default="mac", help="tag for the saved capture folder (e.g. real, dlc-attack)")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--screen", type=int, nargs=2, default=(1440, 900), metavar=("W", "H"))
    ap.add_argument("--attack-delay-ms", type=float, default=0)
    ap.add_argument("--swap-source", help="image of the face to swap in (runs inswapper per frame)")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--lag-ms", type=float, default=60)
    ap.add_argument("--dead", action="store_true", help="synthetic: video ignores the flashes")
    ap.add_argument("--flat", action="store_true", help="synthetic: flat-mirror reflection")
    ap.add_argument("--selfie", help="synthetic: selfie JPEG to send")
    args = ap.parse_args()

    http = httpx.Client(base_url=args.server, timeout=120)

    if args.enroll:
        cap = cv2.VideoCapture(args.camera)
        for _ in range(20):
            ok, frame = cap.read()
        cap.release()
        if not ok:
            sys.exit("cannot read webcam")
        r = http.post("/enroll", data={"user": args.user},
                      files={"selfie": ("selfie.jpg", cv2.imencode(".jpg", frame)[1].tobytes(), "image/jpeg")})
        print(r.status_code, r.text)
        return

    rid = args.request_id
    if not rid:
        pending = http.get("/auth/pending", params={"user": args.user}).json()["request"]
        rid = pending["id"] if pending else None
        print("answering request", rid) if rid else print("no pending request; running standalone")

    ch = challenge_mod.Challenge.from_dict(http.post("/challenge", json={}).json())
    video, meta, selfie = synthetic(ch, args) if args.synthetic else capture(ch, args)

    files = {"video": (video.name, video.read_bytes(), "video/mp4")}
    if selfie:
        files["selfie"] = ("selfie.jpg", selfie, "image/jpeg")
    data = {"challenge_id": ch.id, "meta": json.dumps(meta), "user": args.user, "label": args.label}
    if rid:
        data["request_id"] = rid
    t0 = time.time()
    r = http.post("/verify", data=data, files=files)
    r.raise_for_status()
    res = r.json()
    print(f"\n{res['verdict'].upper()}: {res['reason']}   ({time.time() - t0:.1f}s round trip)")
    for t in res["tiles"]:
        print(f"  [{t['status']:6}] {t['name']:15} {t['headline']:18} {t['detail']}")
    lag = res["signals"]["lag"]
    if lag.get("ok"):
        print(f"  lag {lag['lag_ms']} ms, jitter {lag['lag_jitter_ms']} ms, r2 {lag['response_r2']}")


if __name__ == "__main__":
    main()
