"""FaceCheck verification server.

Run:  uv run uvicorn main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import bundle as bundle_mod
import challenge as challenge_mod
import verdict as verdict_mod
import cv2

from signals import continuity, cornea, identity, lag, transit, vibration

ROOT = Path(__file__).parent
DATA = ROOT / "data"
USERS = DATA / "users"
CAPTURES = DATA / "captures"
WEB = ROOT.parent / "web"
for d in (USERS, CAPTURES):
    d.mkdir(parents=True, exist_ok=True)

# 'auto' scores the outline when the reflection is big enough to read; 'shape' always; 'layout' never.
SHAPE_MODE = os.environ.get("FACECHECK_SHAPE_MODE", "auto")
CHALLENGE_TTL_S = 90

app = FastAPI(title="FaceCheck")

# A copy of the web client hosted elsewhere (Vercel) calls this server directly rather than
# through the host that served it: a check uploads 8-80 MB of frames and static hosts cap a
# proxied body far below that. Origins are restricted to *.vercel.app plus localhost;
# credentials are off, and nothing here is authenticated by cookie.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://[a-z0-9-]+\.vercel\.app|http://localhost(:\d+)?|http://127\.0\.0\.1(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# In-memory state: fine for a demo, lost on restart.
challenges: dict[str, tuple[float, challenge_mod.Challenge]] = {}
requests_: dict[str, dict] = {}


def _safe(name: str) -> str:
    out = "".join(c for c in name if c.isalnum() or c in "-_")
    if not out:
        raise HTTPException(400, "bad user name")
    return out


# ---------- enrollment ----------

@app.post("/enroll")
def enroll(user: str = Form(...), selfie: UploadFile = File(...)):
    user = _safe(user)
    data = selfie.file.read()
    emb = identity.embed(data)
    if emb is None:
        raise HTTPException(422, "no face found in the selfie")
    (USERS / f"{user}.jpg").write_bytes(data)
    np.save(USERS / f"{user}.npy", emb)
    return {"user": user, "enrolled": True}


@app.get("/users/{user}")
def user_status(user: str):
    return {"user": _safe(user), "enrolled": (USERS / f"{_safe(user)}.npy").exists()}


# ---------- relying-party side of the 2FA loop ----------

class AuthRequest(BaseModel):
    user: str
    app_name: str = "Demo Bank"
    device: str = "any"          # "phone", "web" (this computer's webcam) or "any"


@app.post("/auth/requests")
def create_request(req: AuthRequest):
    rid = secrets.token_hex(6)
    device = req.device if req.device in ("phone", "web", "any") else "any"
    requests_[rid] = {"id": rid, "user": _safe(req.user), "app_name": req.app_name, "device": device,
                      "status": "pending", "created": time.time(), "result": None}
    return requests_[rid]


@app.get("/auth/requests/{rid}")
def get_request(rid: str):
    if rid not in requests_:
        raise HTTPException(404, "unknown request")
    return requests_[rid]


@app.get("/auth/pending")
def pending(user: str, device: str = "phone"):
    """Polled by the clients every 2 s; stands in for a push notification. A request aimed
    at one device is invisible to the other, so the phone and the web app don't race."""
    user = _safe(user)
    now = time.time()
    for r in sorted(requests_.values(), key=lambda r: r["created"]):
        if (r["user"] == user and r["status"] == "pending" and now - r["created"] < 120
                and r.get("device", "any") in ("any", device)):
            return {"request": r}
    return {"request": None}


@app.post("/auth/requests/{rid}/deny")
def deny(rid: str):
    if rid not in requests_:
        raise HTTPException(404, "unknown request")
    requests_[rid].update(status="done", result={"verdict": "denied", "reason": "denied on the phone"})
    return requests_[rid]


# ---------- challenge + verification ----------

class ChallengeRequest(BaseModel):
    inverse: bool = False


@app.post("/challenge")
def new_challenge(req: ChallengeRequest | None = None):
    ch = challenge_mod.generate(inverse=bool(req and req.inverse))
    challenges[ch.id] = (time.time(), ch)
    for cid in [c for c, (t, _) in challenges.items() if time.time() - t > CHALLENGE_TTL_S]:
        challenges.pop(cid, None)
    return ch.to_dict()


def _json_safe(x):
    """NaN and infinities aren't valid JSON; a dead signal (covered lens, test pattern) can
    produce them. Report those values as missing instead of failing the request."""
    if isinstance(x, dict):
        return {k: _json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_safe(v) for v in x]
    if isinstance(x, (float, np.floating)):
        return float(x) if np.isfinite(x) else None
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def run_pipeline(video: Path, meta: dict, ch: challenge_mod.Challenge,
                 selfie: bytes | None, user: str | None, transit_blob: bytes | None = None) -> dict:
    b = bundle_mod.load(video, meta)
    lag_r = lag.analyze(b, ch)
    stash: dict = {}
    cornea_r = (cornea.analyze(b, ch, lag_r["lag_ms"], stash=stash) if lag_r.get("ok")
                else {"ok": False, "reason": "skipped: no light response"})

    ident = {"similarity": None, "reason": "no selfie uploaded"}
    selfie_emb = enrolled_emb = None
    if selfie:
        ref = USERS / f"{user}.npy" if user else None
        selfie_emb = identity.embed(selfie)
        if selfie_emb is None:
            ident = {"similarity": None, "reason": "no face found in the selfie"}
        elif ref is None or not ref.exists():
            ident = {"similarity": None, "reason": "user is not enrolled"}
        else:
            enrolled_emb = np.load(ref)
            ident = {"similarity": identity.similarity(selfie_emb, enrolled_emb)}

    cont_r = continuity.analyze(stash, selfie_emb, enrolled_emb) if selfie else None
    transit_r = None
    if transit_blob:
        cap = bundle_mod.open_frames(video)
        ok, first = cap.read()
        cap.release()
        transit_r = transit.analyze(transit.unpack(transit_blob), meta.get("transit_ts", []), selfie_emb,
                                    first if ok else None, float(b.ts[0]))
    stash.clear()                                   # frames are large
    vib_r = vibration.analyze(b) if meta.get("haptics") else None

    out = verdict_mod.decide(lag_r, cornea_r, ident, meta, SHAPE_MODE,
                             continuity=cont_r, vibration=vib_r, transit=transit_r)
    out["signals"] = {"lag": lag_r, "cornea": cornea_r, "identity": ident, "continuity": cont_r,
                      "transit": transit_r, "vibration": vib_r}
    return out


@app.post("/verify")
def verify(challenge_id: str = Form(...), meta: str = Form(...), video: UploadFile | None = File(None),
           frames: UploadFile | None = File(None),
           selfie: UploadFile | None = File(None), transit: UploadFile | None = File(None),
           user: str | None = Form(None),
           request_id: str | None = Form(None), label: str | None = Form(None)):
    entry = challenges.pop(challenge_id, None)   # one-time use
    if entry is None or time.time() - entry[0] > CHALLENGE_TTL_S:
        raise HTTPException(410, "challenge unknown, already used, or expired")
    ch = entry[1]
    user = _safe(user) if user else None

    # Keep every capture: thresholds are set by replaying these (tools/replay.py).
    cap_dir = CAPTURES / f"{time.strftime('%m%d-%H%M%S')}_{_safe(label) if label else 'run'}_{ch.id}"
    cap_dir.mkdir(parents=True)
    if video is None and frames is None:
        raise HTTPException(422, "send either a video file or a frames container")
    if video is not None:
        suffix = Path(video.filename or "video.mov").suffix or ".mov"
        vpath = cap_dir / f"video{suffix}"
        vpath.write_bytes(video.file.read())
    else:                       # the web client: timestamped JPEG frames (see bundle.JpegSequence)
        vpath = cap_dir / "video.bin"
        vpath.write_bytes(frames.file.read())
    meta_d = json.loads(meta)
    (cap_dir / "meta.json").write_text(json.dumps(meta_d))
    (cap_dir / "challenge.json").write_text(json.dumps(ch.to_dict()))
    selfie_bytes = selfie.file.read() if selfie else None
    if selfie_bytes:
        (cap_dir / "selfie.jpg").write_bytes(selfie_bytes)
    transit_bytes = transit.file.read() if transit else None
    if transit_bytes:
        (cap_dir / "transit.bin").write_bytes(transit_bytes)

    t0 = time.time()
    result = _json_safe(run_pipeline(vpath, meta_d, ch, selfie_bytes, user, transit_bytes))
    result["processing_s"] = round(time.time() - t0, 2)
    result["capture"] = cap_dir.name
    (cap_dir / "result.json").write_text(json.dumps(result))

    if request_id and request_id in requests_:
        slim = {k: result[k] for k in ("verdict", "reason", "tiles", "capture", "processing_s")}
        # What face recognition alone would have concluded: the relying party shows it next to the verdict.
        slim["face_similarity"] = ((result.get("signals") or {}).get("identity") or {}).get("similarity")
        slim["face_pass_mark"] = verdict_mod.THRESHOLDS["face_similarity_min"]
        requests_[request_id].update(status="done", result=slim)
    return result


@app.get("/captures/{name}/selfie.jpg")
def capture_selfie(name: str):
    p = CAPTURES / _safe(name)   # _safe strips separators, so no path traversal
    if not (p / "selfie.jpg").exists():
        raise HTTPException(404)
    return FileResponse(p / "selfie.jpg")


@app.get("/captures")
def capture_list():
    """Saved checks, newest first: what the results replay and the attack log read."""
    out = []
    for d in sorted(CAPTURES.iterdir(), reverse=True):
        rj, mj = d / "result.json", d / "meta.json"
        if not (d.is_dir() and rj.exists() and mj.exists()) or d.name.startswith("_"):
            continue
        try:
            r, m = json.loads(rj.read_text()), json.loads(mj.read_text())
        except ValueError:
            continue
        parts = d.name.split("_")
        out.append({"name": d.name, "label": parts[1] if len(parts) > 2 else "", "device": m.get("device_model"),
                    "verdict": r.get("verdict"), "reason": r.get("reason"),
                    "face_similarity": ((r.get("signals") or {}).get("identity") or {}).get("similarity"),
                    "has_selfie": (d / "selfie.jpg").exists()})
    return out


@app.get("/captures/{name}/result.json")
def capture_result(name: str):
    p = CAPTURES / _safe(name) / "result.json"
    if not p.exists():
        raise HTTPException(404)
    return json.loads(p.read_text())


@app.get("/health")
def health():
    return {"ok": True, "shape_mode": SHAPE_MODE}


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
