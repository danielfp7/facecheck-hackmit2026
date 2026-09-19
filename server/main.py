"""InHuman verification server.

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
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import bundle as bundle_mod
import challenge as challenge_mod
import verdict as verdict_mod
from signals import cornea, identity, lag

ROOT = Path(__file__).parent
DATA = ROOT / "data"
USERS = DATA / "users"
CAPTURES = DATA / "captures"
WEB = ROOT.parent / "web"
for d in (USERS, CAPTURES):
    d.mkdir(parents=True, exist_ok=True)

# 'auto' scores the outline when the reflection is big enough to read; 'shape' always; 'layout' never.
SHAPE_MODE = os.environ.get("INHUMAN_SHAPE_MODE", "auto")
CHALLENGE_TTL_S = 90

app = FastAPI(title="InHuman")

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


@app.post("/auth/requests")
def create_request(req: AuthRequest):
    rid = secrets.token_hex(6)
    requests_[rid] = {"id": rid, "user": _safe(req.user), "app_name": req.app_name,
                      "status": "pending", "created": time.time(), "result": None}
    return requests_[rid]


@app.get("/auth/requests/{rid}")
def get_request(rid: str):
    if rid not in requests_:
        raise HTTPException(404, "unknown request")
    return requests_[rid]


@app.get("/auth/pending")
def pending(user: str):
    """Polled by the phone every 2 s; stands in for a push notification."""
    user = _safe(user)
    now = time.time()
    for r in sorted(requests_.values(), key=lambda r: r["created"]):
        if r["user"] == user and r["status"] == "pending" and now - r["created"] < 120:
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


def run_pipeline(video: Path, meta: dict, ch: challenge_mod.Challenge,
                 selfie: bytes | None, user: str | None) -> dict:
    b = bundle_mod.load(video, meta)
    lag_r = lag.analyze(b, ch)
    cornea_r = cornea.analyze(b, ch, lag_r["lag_ms"]) if lag_r.get("ok") else {"ok": False, "reason": "skipped: no light response"}

    ident = {"similarity": None, "reason": "no selfie uploaded"}
    if selfie:
        ref = USERS / f"{user}.npy" if user else None
        emb = identity.embed(selfie)
        if emb is None:
            ident = {"similarity": None, "reason": "no face found in the selfie"}
        elif ref is None or not ref.exists():
            ident = {"similarity": None, "reason": "user is not enrolled"}
        else:
            ident = {"similarity": identity.similarity(emb, np.load(ref))}

    out = verdict_mod.decide(lag_r, cornea_r, ident, meta, SHAPE_MODE)
    out["signals"] = {"lag": lag_r, "cornea": cornea_r, "identity": ident}
    return out


@app.post("/verify")
def verify(challenge_id: str = Form(...), meta: str = Form(...), video: UploadFile = File(...),
           selfie: UploadFile | None = File(None), user: str | None = Form(None),
           request_id: str | None = Form(None), label: str | None = Form(None)):
    entry = challenges.pop(challenge_id, None)   # one-time use
    if entry is None or time.time() - entry[0] > CHALLENGE_TTL_S:
        raise HTTPException(410, "challenge unknown, already used, or expired")
    ch = entry[1]
    user = _safe(user) if user else None

    # Keep every capture: thresholds are set by replaying these (tools/replay.py).
    cap_dir = CAPTURES / f"{time.strftime('%m%d-%H%M%S')}_{_safe(label) if label else 'run'}_{ch.id}"
    cap_dir.mkdir(parents=True)
    suffix = Path(video.filename or "video.mov").suffix or ".mov"
    vpath = cap_dir / f"video{suffix}"
    vpath.write_bytes(video.file.read())
    meta_d = json.loads(meta)
    (cap_dir / "meta.json").write_text(json.dumps(meta_d))
    (cap_dir / "challenge.json").write_text(json.dumps(ch.to_dict()))
    selfie_bytes = selfie.file.read() if selfie else None
    if selfie_bytes:
        (cap_dir / "selfie.jpg").write_bytes(selfie_bytes)

    t0 = time.time()
    result = run_pipeline(vpath, meta_d, ch, selfie_bytes, user)
    result["processing_s"] = round(time.time() - t0, 2)
    result["capture"] = cap_dir.name
    (cap_dir / "result.json").write_text(json.dumps(result))

    if request_id and request_id in requests_:
        slim = {k: result[k] for k in ("verdict", "reason", "tiles", "capture")}
        requests_[request_id].update(status="done", result=slim)
    return result


@app.get("/captures/{name}/selfie.jpg")
def capture_selfie(name: str):
    p = CAPTURES / _safe(name)   # _safe strips separators, so no path traversal
    if not (p / "selfie.jpg").exists():
        raise HTTPException(404)
    return FileResponse(p / "selfie.jpg")


@app.get("/health")
def health():
    return {"ok": True, "shape_mode": SHAPE_MODE}


if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
