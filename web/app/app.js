// FaceCheck web client: the same verification flow as the iPhone app, on a computer's webcam.
//
// Differences a browser forces on us, and how the server copes:
//  - No video file with exact per-frame timestamps: each camera frame is grabbed with its
//    capture time and packed as [uint32 LE length][JPEG] (server: bundle.JpegSequence).
//  - Exposure usually can't be locked: meta.camera.exposure_locked = false switches the
//    lag check to chromaticity.
//  - A wide screen has no vertical room for three positions: shapes go left/middle/right
//    (meta.screen.position_axis = "x") and are sized from the screen height.
//  - No haptics or motion sensors, so no vibration check.
"use strict";

const $ = (id) => document.getElementById(id);
const SCREENS = ["home", "approve", "warning", "camera", "uploading", "results"];
const MAX_SELFIE_TO_CHECK_S = 20;
const SHAPE_SPAN_OF_HEIGHT = 0.75;
const POSITION_X = { top: 0.25, middle: 0.5, bottom: 0.75 };   // server names, used as left/middle/right here
const TARGET_DISTANCE_MM = 165;      // ~6.5 in. People end up ~30% further than asked (322 mm on a 250 mm ask)
const ASSUMED_FOV_DEG = 65;
const now = () => performance.now() / 1000;
const sleep = (s) => new Promise((r) => setTimeout(r, s * 1000));

const S = {
  step: "home", enrolling: false, request: null, challenge: null,
  stream: null, track: null, selfie: null, selfieTs: null, exposureLocked: false, tsSource: "now",
  tracker: { ready: false, on: false, raf: null, last: null, lostAt: null, goodSince: null, startedAt: 0, phase: null },
  transit: { on: false, blobs: [], ts: [], timer: null },
  frames: { on: false, blobs: [], ts: [], pending: [] },
  aborted: null,
};

// Attack test mode (?inject): the "camera" is the live face swap served by `attack/live.py --serve`,
// which is what a virtual camera does for a real attacker. Everything after openCamera() is unchanged.
const INJECT = new URLSearchParams(location.search).has("inject")
  ? `http://127.0.0.1:${new URLSearchParams(location.search).get("inject") || 8765}` : null;

const video = $("video");
const full = document.createElement("canvas");
const small = document.createElement("canvas");

// ---------- plumbing ----------

function show(name) {
  S.step = name;
  for (const s of SCREENS) $(s).hidden = s !== name;
}

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 7000);
}

/**
 * Where the server is. Empty means "same origin", which is the normal case when the server
 * serves these files itself. A static copy hosted elsewhere (Vercel) needs an absolute URL,
 * because the check uploads 8-80 MB of frames and no static host will proxy that. Set it
 * once with ?api=https://... and it is remembered, or bake it into config.js.
 */
const API = (() => {
  const q = new URLSearchParams(location.search).get("api");
  if (q !== null) {
    try { q ? localStorage.setItem("facecheck.api", q) : localStorage.removeItem("facecheck.api"); } catch {}
    return q.replace(/\/$/, "");
  }
  let saved = null;
  try { saved = localStorage.getItem("facecheck.api"); } catch {}
  return (saved || window.FACECHECK_API || "").replace(/\/$/, "");
})();
const apiURL = (path) => API + path;
window.apiURL = apiURL;   // results.js and attacks.html build capture URLs too

async function api(path, opts) {
  const r = await fetch(apiURL(path), opts);
  if (!r.ok) throw new Error(`${r.status}: ${(await r.text()).slice(0, 200)}`);
  return r.json();
}

const user = () => $("user").value.trim() || "daniel";

function deviceModel() {
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const os = /Mac/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "OS";
  return `web-${os}-${browser}`;
}

/** Blobs -> one container: repeated [uint32 little-endian length][bytes]. */
function pack(blobs) {
  const parts = [];
  for (const b of blobs) {
    if (!b) continue;
    const head = new DataView(new ArrayBuffer(4));
    head.setUint32(0, b.size, true);
    parts.push(head.buffer, b);
  }
  return new Blob(parts, { type: "application/octet-stream" });
}

// ---------- home: poll for sign-in requests (stands in for a push) ----------

async function poll() {
  if (S.step !== "home") return;
  try {
    const enrolled = (await api(`/users/${encodeURIComponent(user())}`)).enrolled;
    $("btnTest").hidden = !enrolled;
    $("btnEnroll").textContent = enrolled ? "Update my profile picture" : "Create my profile picture";
    $("btnEnroll").disabled = false;
    $("status").textContent = enrolled ? `Waiting for a sign-in request for “${user()}”…` : "Create a profile picture once to get started.";
    if (!enrolled) return;
    const { request } = await api(`/auth/pending?user=${encodeURIComponent(user())}&device=web`);
    if (request && S.step === "home") {
      S.request = request;
      $("approveText").textContent = `${request.app_name} wants to confirm a live person is signing in as “${request.user}”.`;
      show("approve");
    }
  } catch {
    $("status").textContent = "Can't reach the server.";
    $("btnEnroll").disabled = true;
  }
}

// ---------- camera ----------

/** A MediaStream fed by the swapped frames, painted onto a canvas as they arrive. */
async function injectedStream() {
  const next = async (after) => {
    const r = await fetch(`${INJECT}/frame?after=${after}`, { cache: "no-store" });
    if (!r.ok) throw new Error("no frame yet");
    return { seq: Number(r.headers.get("X-Seq")), bmp: await createImageBitmap(await r.blob()) };
  };
  let first;
  try { first = await next(0); } catch { throw new Error("The fake isn't running. Start it first: attack/live.py --serve"); }
  const c = document.createElement("canvas");
  c.width = first.bmp.width;
  c.height = first.bmp.height;
  const ctx = c.getContext("2d");
  ctx.drawImage(first.bmp, 0, 0);
  const stream = c.captureStream();
  (async () => {
    let seq = first.seq;
    while (stream.active) {
      try { const f = await next(seq); seq = f.seq; ctx.drawImage(f.bmp, 0, 0); f.bmp.close(); } catch { await sleep(0.2); }
    }
  })();
  return stream;
}

async function openCamera() {
  S.stream = INJECT ? await injectedStream() : await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: "user", width: { ideal: 1920 }, height: { ideal: 1080 }, frameRate: { ideal: 30 } },
  });
  S.track = S.stream.getVideoTracks()[0];
  video.srcObject = S.stream;
  await video.play();
  full.width = video.videoWidth;
  full.height = video.videoHeight;
  small.width = 480;
  small.height = Math.round((480 * video.videoHeight) / video.videoWidth);
}

function closeCamera() {
  stopTracking();
  stopTransit();
  S.frames.on = false;
  if (S.stream) S.stream.getTracks().forEach((t) => t.stop());
  S.stream = S.track = null;
  video.srcObject = null;
}

function grab(canvas, quality) {
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  return new Promise((res) => canvas.toBlob(res, "image/jpeg", quality));   // the bitmap is copied synchronously
}

/** Freeze exposure and white balance if this camera/browser allows it. Most don't. */
async function lockExposure() {
  S.exposureLocked = false;
  try {
    const caps = S.track.getCapabilities ? S.track.getCapabilities() : {};
    const adv = [];
    if ((caps.exposureMode || []).includes("manual")) adv.push({ exposureMode: "manual" });
    if ((caps.whiteBalanceMode || []).includes("manual")) adv.push({ whiteBalanceMode: "manual" });
    if (adv.length) {
      await S.track.applyConstraints({ advanced: adv });
      S.exposureLocked = adv.some((a) => a.exposureMode);
    }
  } catch { /* stays unlocked; the server handles that */ }
}

async function unlockExposure() {
  try {
    if (S.exposureLocked) await S.track.applyConstraints({ advanced: [{ exposureMode: "continuous" }, { whiteBalanceMode: "continuous" }] });
  } catch { /* ignore */ }
}

// Transit: small frames from the selfie until the flashes start, so the server can watch the move-in.
function startTransit() {
  const T = S.transit;
  T.blobs = []; T.ts = []; T.on = true;
  T.timer = setInterval(() => {
    if (!T.on || T.ts.length >= 260) return;
    const i = T.ts.length;
    T.ts.push(now());
    grab(small, 0.65).then((b) => (T.blobs[i] = b));
  }, 100);
}

function stopTransit() {
  S.transit.on = false;
  clearInterval(S.transit.timer);
}

// Full-resolution frames with capture timestamps, for the flash sequence.
function startFrames() {
  const F = S.frames;
  F.blobs = []; F.ts = []; F.pending = []; F.eyes = []; F.on = true;
  const ctx = full.getContext("2d");
  const hasRVFC = "requestVideoFrameCallback" in HTMLVideoElement.prototype;
  const take = (ts) => {
    const i = F.ts.length;
    F.ts.push(ts);
    F.eyes[i] = trackFrame();          // where the eye was on this frame
    ctx.drawImage(video, 0, 0);
    F.pending.push(new Promise((res) => full.toBlob((b) => { F.blobs[i] = b; res(); }, "image/jpeg", 0.9)));
  };
  if (hasRVFC) {
    const onFrame = (t, md) => {
      if (!F.on) return;
      const ms = md.captureTime ?? md.presentationTime ?? t;
      S.tsSource = md.captureTime != null ? "captureTime" : md.presentationTime != null ? "presentationTime" : "callback";
      take(ms / 1000);
      video.requestVideoFrameCallback(onFrame);
    };
    video.requestVideoFrameCallback(onFrame);
  } else {
    let last = -1;
    const loop = () => {
      if (!F.on) return;
      if (video.currentTime !== last) { last = video.currentTime; take(now()); }
      requestAnimationFrame(loop);
    };
    S.tsSource = "poll";
    requestAnimationFrame(loop);
  }
}

// ---------- live face + eye tracking ----------
//
// The ring follows the eye instead of the person chasing a fixed outline, and the check
// runs itself: the selfie fires when the face is framed and still, the flashes start when
// the eye is close enough and steady. Every genuine rejection so far was a positioning
// failure ("lean in closer", wrong reflection position), never a detection failure.
//
// Tracking is an upgrade, never a requirement: if track.js fails to load, or the tracker
// finds no face, the shutter and "I'm in position" buttons still drive the same flow.

const IRIS_MM = 11.7;
const HOLD_S = 0.6;                 // how long a good pose must hold before it fires
const SELFIE_MIN_S = 2.0;           // and the selfie waits at least this long either way, so
                                    // the step is legible instead of firing the moment it opens
const LOST_GRACE_S = 0.9;           // keep the last reading this long after losing the face
// The selfie oval is a target too: the face has to be lined up inside it, not merely big
// enough somewhere in frame. Checking only size let people sit with their chin under the
// camera, which passed the selfie and then failed continuity on the way in to the eye.
const SELFIE_FILL = [0.52, 1.12];   // face height as a fraction of the oval's
const SELFIE_OFF = 0.30;            // centre offset allowed, as a fraction of the oval's half-size

/** The selfie oval in video pixels. Measured from the element, so CSS owns its size and
 *  the phone breakpoint can change it without the alignment maths drifting out of step. */
function ovalInVideoPx() {
  const vw = video.videoWidth, vh = video.videoHeight;
  const cssPerPx = Math.max(innerWidth / vw, innerHeight / vh);
  const r = $("guide").getBoundingClientRect();
  return { w: r.width / cssPerPx, h: r.height / cssPerPx, cssPerPx };
}
const IN_OUTLINE_FRAC = 0.30;       // eye must sit within this fraction of the ring's radius
const SIZE_TOL = 0.28;              // and its iris within this fraction of the ring's size
const RING_DRAW_SCALE = 0.8;        // how big the ring is drawn, relative to that iris

function trackerReady() { return !!(window.FaceCheckTracker && S.tracker.ready); }

function stopTracking() {
  const T = S.tracker;
  T.on = false;
  if (T.raf) cancelAnimationFrame(T.raf);
  T.raf = null;
  T.last = T.lostAt = T.goodSince = null;
  T.phase = null;
  $("ring").classList.remove("locked");
  $("hud").hidden = true;
}

/** Video pixels -> CSS px in the mirrored, object-fit:cover viewfinder. */
function videoToCss(x, y) {
  const vw = video.videoWidth, vh = video.videoHeight;
  const scale = Math.max(innerWidth / vw, innerHeight / vh);
  return { x: innerWidth - ((x - vw / 2) * scale + innerWidth / 2),
           y: (y - vh / 2) * scale + innerHeight / 2, scale };
}

/** Iris radius in video px at the distance the outline is drawn for. */
function targetIrisPx() {
  const pxPerMM = video.videoWidth / (2 * TARGET_DISTANCE_MM * Math.tan((ASSUMED_FOV_DEG * Math.PI) / 360));
  return (IRIS_MM / 2) * pxPerMM;
}

function setHud(state, main, sub) {
  const h = $("hud");
  h.hidden = false;
  h.className = "hud " + state;
  $("hudMain").textContent = main;
  $("hudSub").textContent = sub || "";
}

/**
 * The outline is a fixed target in the middle of the screen and does not move. The person
 * brings their eye to it, which is what pins the working distance, and the working distance
 * is what decides how many pixels across the screen's reflection lands in. Letting the ring
 * chase the eye meant people stopped wherever the tracker was happy, so the reflection
 * arrived at whatever size, and reading the outline out of it became unreliable.
 *
 * Tracking still runs, but only to answer one question: is the eye in the outline yet. It
 * never moves the target and it can always be replaced by the button.
 */
function startTracking(phase) {
  const T = S.tracker;
  stopTracking();
  if (!trackerReady()) { setHud("hunting", phase === "selfie" ? "Fill the outline" : "Put your eye in the outline", "Then press the button"); return; }
  T.on = true; T.phase = phase; T.startedAt = now();
  const ring = $("ring"), guide = $("guide");

  const tick = () => {
    if (!T.on || S.step !== "camera") return;
    let r = null;
    try { r = window.FaceCheckTracker.track(video, video.videoWidth, video.videoHeight); }
    catch { /* a bad frame is not a failure */ }
    const t = now();
    if (r) {
      T.lostAt = null;
      T.last = T.last
        ? { eye: { x: 0.55 * T.last.eye.x + 0.45 * r.eye.x, y: 0.55 * T.last.eye.y + 0.45 * r.eye.y,
                   r: 0.7 * T.last.eye.r + 0.3 * r.eye.r },
            box: r.box, mm: 0.7 * T.last.mm + 0.3 * r.distanceMM(ASSUMED_FOV_DEG) }
        : { eye: r.eye, box: r.box, mm: r.distanceMM(ASSUMED_FOV_DEG) };
    } else if (T.last && T.lostAt == null) {
      T.lostAt = t;
    }
    const have = T.last && (!T.lostAt || t - T.lostAt < LOST_GRACE_S);
    if (!have) {
      T.goodSince = null;
      ring.classList.remove("locked");
      setHud("hunting", phase === "selfie" ? "Fill the outline" : "Put your eye in the outline", "Looking for you");
      T.raf = requestAnimationFrame(tick);
      return;
    }

    const { eye, box, mm } = T.last;
    if (phase === "selfie") {
      const vw = video.videoWidth, vh = video.videoHeight;
      const { w: ovalW, h: ovalH } = ovalInVideoPx();
      const dx = Math.abs(box.x + box.w / 2 - vw / 2) / (ovalW / 2);
      const dy = Math.abs(box.y + box.h / 2 - vh / 2) / (ovalH / 2);
      const fill = box.h / ovalH;
      const centred = dx <= SELFIE_OFF && dy <= SELFIE_OFF;
      const sized = fill >= SELFIE_FILL[0] && fill <= SELFIE_FILL[1];
      guide.classList.toggle("locked", centred && sized);
      if (!sized) {
        T.goodSince = null;
        setHud("warn", fill < SELFIE_FILL[0] ? "Closer" : "Back off a little",
               `${Math.round(mm)} mm \u2014 fill the outline`);
      } else if (!centred) {
        T.goodSince = null;
        setHud("warn", "Centre your face", `${Math.round(mm)} mm \u2014 line up with the outline`);
      } else {
        if (T.goodSince == null) T.goodSince = t;
        const ready = t - T.goodSince >= HOLD_S && t - T.startedAt >= SELFIE_MIN_S;
        setHud("good", ready ? "Hold it" : "Hold still", `${Math.round(mm)} mm \u2014 in the outline`);
        if (ready) { stopTracking(); shutter(); return; }
      }
      T.raf = requestAnimationFrame(tick);
      return;
    }

    // Eye check: is the eye inside the fixed outline, at the size the outline is drawn for?
    const want = targetIrisPx();
    const centre = { x: video.videoWidth / 2, y: video.videoHeight / 2 };
    const off = Math.hypot(eye.x - centre.x, eye.y - centre.y) / want;   // in iris radii
    const sizeErr = Math.abs(eye.r - want) / want;
    const centred = off <= IN_OUTLINE_FRAC * 2;
    const rightSize = sizeErr <= SIZE_TOL;
    ring.classList.toggle("locked", centred && rightSize);
    if (!rightSize) {
      T.goodSince = null;
      setHud("warn", eye.r < want ? "Closer" : "Back off a little",
             `${Math.round(mm)} mm \u2014 fill the outline`);
    } else if (!centred) {
      T.goodSince = null;
      setHud("warn", "Centre your eye", `${Math.round(mm)} mm \u2014 move it into the outline`);
    } else {
      if (T.goodSince == null) T.goodSince = t;
      const held = t - T.goodSince;
      setHud("good", held >= HOLD_S ? "Starting" : "Hold still", `${Math.round(mm)} mm \u2014 in the outline`);
      if (held >= HOLD_S) { stopTracking(); ready(); return; }
    }
    T.raf = requestAnimationFrame(tick);
  };
  T.raf = requestAnimationFrame(tick);
}

/** Eye position per frame during the flashes, so the server never has to hunt for it. */
function trackFrame() {
  if (!trackerReady()) return null;
  try {
    const r = window.FaceCheckTracker.track(video, video.videoWidth, video.videoHeight);
    return r ? [Math.round(r.eye.x), Math.round(r.eye.y), Math.round(r.eye.r * 10) / 10] : null;
  } catch { return null; }
}

// ---------- the flow ----------

function cameraMode(mode) {
  show("camera");
  const selfie = mode === "selfie";
  $("guide").className = "guide " + (selfie ? "selfie" : "close");
  $("btnShutter").hidden = !selfie;
  $("btnReady").hidden = selfie;
  $("countdown").hidden = true;
  const ring = $("ring");
  ring.hidden = selfie;
  if (!selfie) {
    // Fixed target in the middle: the coloured part of one eye, at the working distance.
    // It does not move, because lining the eye up with it is what pins that distance.
    // Drawn a little inside the iris it checks for, which reads better against a real eye.
    // RING_DRAW_SCALE is presentation only; targetIrisPx() still decides the size check.
    const cssPerPx = Math.max(innerWidth / video.videoWidth, innerHeight / video.videoHeight);
    ring.style.left = ring.style.top = "50%";
    ring.style.width = ring.style.height = `${2 * targetIrisPx() * RING_DRAW_SCALE * cssPerPx}px`;
  }
  $("camBanner").innerHTML = selfie
    ? `<b>${S.enrolling ? "Profile picture: look at the camera" : "Look at the camera"}</b>${trackerReady() ? "The photo takes itself once your face fills the outline." : "Lean in until your face fills the outline."}`
    : `<b>Put one eye in the outline</b>Line the coloured part of your eye up with the circle, so it fills it.${trackerReady() ? " The check starts on its own." : ""}<small>The move is being watched. Looking away, covering the camera or switching tabs cancels the check.</small>`;
  startTracking(selfie ? "selfie" : "close");
}

async function begin(enrolling) {
  S.enrolling = enrolling;
  try {
    await openCamera();
    cameraMode("selfie");
  } catch (e) {
    toast("Couldn't open the camera: " + e.message);
    reset();
  }
}

async function shutter() {
  $("btnShutter").disabled = true;
  try {
    const jpeg = await grab(full, 0.92);
    if (S.enrolling) {
      const fd = new FormData();
      fd.append("user", user());
      fd.append("selfie", jpeg, "selfie.jpg");
      await api("/enroll", { method: "POST", body: fd });
      reset();
    } else {
      S.selfie = jpeg;
      S.selfieTs = now();
      startTransit();                       // keep watching while they lean in
      cameraMode("close");
    }
  } catch (e) {
    toast(e.message);
    reset();
  } finally {
    $("btnShutter").disabled = false;
  }
}

async function ready() {
  if (now() - S.selfieTs > MAX_SELFIE_TO_CHECK_S) return broken("Too long passed since the selfie.");
  $("btnReady").hidden = true;
  try {
    // Fullscreen needs the click's user activation, so ask now, before the countdown.
    await document.documentElement.requestFullscreen({ navigationUI: "hide" }).catch(() => {});
    S.challenge = await api("/challenge", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const cd = $("countdown"), cdNum = $("countdownNum");
    cd.hidden = false;
    for (let n = 3; n >= 1; n--) {
      cdNum.textContent = n;
      await sleep(0.9);
      if (S.step !== "camera") return;
    }
    cd.hidden = true;
    await runChallenge();
  } catch (e) {
    if (!S.aborted) toast(e.message);
    reset();
  }
}

function paint(state) {
  const ch = S.challenge, stage = $("stage"), svg = $("shape");
  const css = (name) => `rgb(${ch.colors[name].join(",")})`;
  if (state === "settle") { stage.style.background = css(ch.settle_color); svg.innerHTML = ""; return; }
  stage.style.background = css(state.background);
  if (!state.shape) { svg.innerHTML = ""; return; }
  const W = innerWidth, H = innerHeight, span = SHAPE_SPAN_OF_HEIGHT * H;
  const cx = W * POSITION_X[state.position], cy = H / 2, r = span / 2, fill = css(state.shape_color);
  if (state.shape === "circle") svg.innerHTML = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}"/>`;
  else if (state.shape === "square") svg.innerHTML = `<rect x="${cx - r}" y="${cy - r}" width="${span}" height="${span}" fill="${fill}"/>`;
  else {
    const th = (span * Math.sqrt(3)) / 2;
    svg.innerHTML = `<polygon points="${cx},${cy - th / 2} ${cx - r},${cy + th / 2} ${cx + r},${cy + th / 2}" fill="${fill}"/>`;
  }
}

async function runChallenge() {
  const ch = S.challenge, stage = $("stage");
  S.step = "challenge";
  paint("settle");
  stage.hidden = false;

  // Brightest colour is up: let auto-exposure converge on it, then freeze it if we can.
  await sleep(Math.max(ch.settle_s, 1.0));
  await lockExposure();
  if (S.step !== "challenge") return;
  startFrames();
  setTimeout(stopTransit, 250);             // overlap the first frames so the two join without a hole

  // Flash sequence, driven from requestAnimationFrame so changes land on a display frame.
  const bounds = []; let acc = 0;
  for (const s of ch.states) bounds.push((acc += s.duration_s));
  const events = [];
  const SETTLE_HOLD = 0.4, TAIL = 0.5;
  await new Promise((done) => {
    let start = null, shown = null, lastT = null, frameDur = 1 / 60;
    const tick = (ms) => {
      if (S.step !== "challenge") return done();
      const t = ms / 1000;
      if (lastT != null) frameDur = Math.min(Math.max(t - lastT, 1 / 240), 1 / 24);
      lastT = t;
      // What is painted now reaches the panel about one frame later.
      if (start == null) { start = t + SETTLE_HOLD; events.push({ state_index: -1, ts: t + frameDur }); }
      const rel = t - start;
      if (rel >= acc + TAIL) return done();
      if (rel >= 0) {
        let idx = bounds.findIndex((b) => rel < b);
        if (idx < 0) idx = ch.states.length - 1;
        if (idx !== shown) { shown = idx; paint(ch.states[idx]); events.push({ state_index: ch.states[idx].index, ts: t + frameDur }); }
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  if (S.step !== "challenge") return;
  S.frames.on = false;

  await Promise.all(S.frames.pending);
  await unlockExposure();
  show("uploading");                        // before leaving fullscreen, or the exit reads as "stopped"
  stage.hidden = true;
  if (document.fullscreenElement) await document.exitFullscreen().catch(() => {});
  await upload(events);
}

async function upload(events) {
  show("uploading");
  const ch = S.challenge, F = S.frames, T = S.transit;
  const settings = S.track.getSettings();
  closeCamera();
  const heightMM = (screen.height / 127) * 25.4;      // CSS px at the ~127 ppi of a laptop's "looks like" mode
  const meta = {
    schema: 1, challenge_id: ch.id, device_model: deviceModel(),
    frames: F.ts, dropped: [], display_events: events,
    camera: { width: full.width, height: full.height, fps: settings.frameRate || 30, fov_deg: ASSUMED_FOV_DEG, mirrored: false,
              exposure_locked: S.exposureLocked, focus_locked: false, timestamp_source: S.tsSource },
    screen: { brightness: null, width_mm: (screen.width / 127) * 25.4, height_mm: heightMM,
              shape_span_mm: SHAPE_SPAN_OF_HEIGHT * heightMM * (innerHeight / screen.height), position_axis: "x" },
    distance_mm: TARGET_DISTANCE_MM, imu: [], haptics: [],
    session: { selfie_ts: S.selfieTs, challenge_start_ts: events[0]?.ts ?? 0, interruptions: 0 },
    transit_ts: T.ts.filter((_, i) => T.blobs[i]),
    // Client-side eye track, one entry per frame: [x, y, iris_radius] in video px, or null.
    eye_track: F.eyes,
  };

  const fd = new FormData();
  fd.append("challenge_id", ch.id);
  fd.append("meta", JSON.stringify(meta));
  fd.append("user", user());
  fd.append("label", $("label").value);
  if (S.request) fd.append("request_id", S.request.id);
  fd.append("frames", pack(F.blobs), "video.bin");
  fd.append("selfie", S.selfie, "selfie.jpg");
  if (T.blobs.length) fd.append("transit", pack(T.blobs), "transit.bin");
  try {
    renderResults(await api("/verify", { method: "POST", body: fd }));
  } catch (e) {
    toast(e.message);
    reset();
  }
}

/** The selfie and the eye check must be one uninterrupted sitting. */
function broken(why) {
  S.aborted = why;
  toast(`${why} The selfie and the eye check have to happen in one go, so this check was cancelled. Start again.`);
  reset();
}

const locked = () => (S.step === "camera" && !S.enrolling && S.selfie) || S.step === "challenge";

function reset() {
  closeCamera();
  $("stage").hidden = true;
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  S.request = S.challenge = S.selfie = S.selfieTs = null;
  setTimeout(() => (S.aborted = null), 0);
  // Load the face tracker in the background. Everything works without it.
(function initTracker() {
  const go = () => window.FaceCheckTracker.init()
    .then(() => { S.tracker.ready = true; })
    .catch(() => { S.tracker.ready = false; });
  if (window.FaceCheckTracker) go();
  else addEventListener("facecheck-tracker-loaded", go, { once: true });
})();

show("home");
}

// ---------- wiring ----------

const params = new URLSearchParams(location.search);
$("user").value = params.get("user") || localStorage.getItem("facecheck.user") || "daniel";
$("user").addEventListener("change", () => { localStorage.setItem("facecheck.user", user()); poll(); });
if (INJECT) { $("injectNote").hidden = false; $("label").value = "inject-attack"; }
$("btnEnroll").onclick = () => begin(true);
$("btnTest").onclick = () => { S.request = null; show("warning"); };
$("btnApprove").onclick = () => show("warning");
$("btnDeny").onclick = async () => { const id = S.request?.id; reset(); if (id) await api(`/auth/requests/${id}/deny`, { method: "POST" }).catch(() => {}); };
$("btnContinue").onclick = () => begin(false);
$("btnCancelWarn").onclick = $("btnDeny").onclick;
$("btnShutter").onclick = shutter;
$("btnReady").onclick = ready;
$("btnCancelCam").onclick = $("btnDeny").onclick;
$("btnDone").onclick = reset;

document.addEventListener("visibilitychange", () => { if (document.hidden && locked()) broken("You left the page."); });
document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement && S.step === "challenge") broken("The check was stopped."); });

/** Opened from a relying party's "verify on this computer": go straight to that request. */
async function openLinkedRequest() {
  const id = params.get("request");
  if (!id) return;
  history.replaceState(null, "", location.pathname);          // a reload shouldn't replay it
  try {
    const req = await api(`/auth/requests/${encodeURIComponent(id)}`);
    if (req.status !== "pending") return toast("That sign-in request is no longer waiting.");
    const enrolled = (await api(`/users/${encodeURIComponent(req.user)}`)).enrolled;
    if (!enrolled) return toast(`“${req.user}” isn't enrolled yet. Enroll first, then sign in again.`);
    S.request = req;
    $("approveText").textContent = `${req.app_name} wants to confirm a live person is signing in as “${req.user}”.`;
    show("approve");
  } catch (e) {
    toast(e.message);
  }
}

/** ?replay=<capture folder>: show a saved check's results without running one. */
async function openReplay() {
  const name = params.get("replay");
  if (!name) return false;
  try {
    const r = await api(`/captures/${encodeURIComponent(name)}/result.json`);
    r.capture = r.capture || name;
    renderResults(r);
    return true;
  } catch (e) { toast(e.message); return false; }
}

// Load the face tracker in the background. Everything works without it.
(function initTracker() {
  const go = () => window.FaceCheckTracker.init()
    .then(() => { S.tracker.ready = true; })
    .catch(() => { S.tracker.ready = false; });
  if (window.FaceCheckTracker) go();
  else addEventListener("facecheck-tracker-loaded", go, { once: true });
})();

show("home");
openReplay().then((replayed) => { if (!replayed) openLinkedRequest().then(poll); });
setInterval(poll, 2000);
