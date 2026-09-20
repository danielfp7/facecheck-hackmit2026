// InHuman web client: the same verification flow as the iPhone app, on a computer's webcam.
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
  transit: { on: false, blobs: [], ts: [], timer: null },
  frames: { on: false, blobs: [], ts: [], pending: [] },
  eye: { on: false, raf: null, last: null, closeSince: null, lostSince: null },
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

async function api(path, opts) {
  const r = await fetch(path, opts);
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
    $("btnEnroll").textContent = enrolled ? "Re-enroll my face" : "Enroll my face";
    $("btnEnroll").disabled = false;
    $("status").textContent = enrolled ? `Waiting for a sign-in request for “${user()}”…` : "Enroll your face once to get started.";
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
  stopEyeTracking();
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
  F.blobs = []; F.ts = []; F.pending = []; F.on = true;
  const ctx = full.getContext("2d");
  const hasRVFC = "requestVideoFrameCallback" in HTMLVideoElement.prototype;
  const take = (ts) => {
    const i = F.ts.length;
    F.ts.push(ts);
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

// ---------- live eye tracking ----------
//
// The ring follows the eye instead of the eye having to find the ring. We track the
// corneal glint (the screen's own reflection), measure the iris around it, and start the
// check by itself once the eye is close enough and holding still. Every genuine failure
// so far has been a positioning failure ("lean in closer"), not a detection failure.

const IRIS_MM = 11.7;
const READY_HOLD_S = 0.7;        // eye must stay close and found for this long
const LOST_GRACE_S = 1.2;        // keep the last ring this long before giving up on tracking

/** Video pixels -> CSS px in the mirrored, object-fit:cover viewfinder. */
function videoToCss(x, y) {
  const vw = video.videoWidth, vh = video.videoHeight;
  const scale = Math.max(innerWidth / vw, innerHeight / vh);
  return { x: innerWidth - ((x - vw / 2) * scale + innerWidth / 2),
           y: (y - vh / 2) * scale + innerHeight / 2, scale };
}

/** Iris radius in video px at the target distance. */
function targetIrisPx() {
  const pxPerMM = video.videoWidth / (2 * TARGET_DISTANCE_MM * Math.tan((ASSUMED_FOV_DEG * Math.PI) / 360));
  return (IRIS_MM / 2) * pxPerMM;
}

// The tracker measures the whole dark eye region, not the iris alone, so it reads high.
// Calibrated on captures with a known distance: 147 mm (the furthest that still produced a
// clean check) came out at 4.5x the target iris radius, 118 mm at 7.6x.
const CLOSE_ENOUGH = 4.0;
function isClose(r) { return r >= CLOSE_ENOUGH * targetIrisPx(); }

function stopEyeTracking() {
  S.eye.on = false;
  if (S.eye.raf) cancelAnimationFrame(S.eye.raf);
  S.eye.raf = null;
  S.eye.last = S.eye.closeSince = S.eye.lostSince = null;
  $("ring").classList.remove("tracked", "near");
}

function startEyeTracking() {
  const E = S.eye;
  E.on = true; E.last = null; E.closeSince = null; E.lostSince = null;
  const ring = $("ring"), want = targetIrisPx();
  const tick = () => {
    if (!E.on || S.step !== "camera") return;
    let eye = null;
    try { eye = window.findEye(video); } catch { /* tracking is optional; the button still works */ }
    const t = now();
    if (eye) {
      E.lostSince = null;
      // Smooth so the ring doesn't jitter, but follow a real move quickly.
      E.last = E.last ? { x: 0.6 * E.last.x + 0.4 * eye.x, y: 0.6 * E.last.y + 0.4 * eye.y,
                          r: 0.7 * E.last.r + 0.3 * eye.r } : eye;
    } else if (E.last && E.lostSince == null) {
      E.lostSince = t;
    }
    const show = E.last && (!E.lostSince || t - E.lostSince < LOST_GRACE_S);
    if (show) {
      const { x, y, scale } = videoToCss(E.last.x, E.last.y);
      const d = 2 * (E.last.r / 3.0) * scale;   // draw at about iris size
      ring.style.transform = `translate(-50%, -50%)`;
      ring.style.left = `${x}px`;
      ring.style.top = `${y}px`;
      ring.style.width = ring.style.height = `${d}px`;
      ring.classList.add("tracked");
      const close = isClose(E.last.r);
      ring.classList.toggle("near", close);
      if (close && !E.lostSince) {
        if (E.closeSince == null) E.closeSince = t;
        const held = t - E.closeSince;
        setBanner(held >= READY_HOLD_S ? "hold" : "steady");
        if (held >= READY_HOLD_S) { stopEyeTracking(); ready(); return; }
      } else {
        E.closeSince = null;
        setBanner("closer");
      }
    } else {
      E.closeSince = null;
      ring.classList.remove("tracked", "near");
      ring.style.left = ring.style.top = "50%";
      ring.style.width = ring.style.height = `${2 * want * Math.max(innerWidth / video.videoWidth, innerHeight / video.videoHeight)}px`;
      setBanner("find");
    }
    E.raf = requestAnimationFrame(tick);
  };
  E.raf = requestAnimationFrame(tick);
}

const BANNERS = {
  find: ["Bring one eye toward the camera", "Looking for your eye. Keep the camera on your face."],
  closer: ["Closer", "Keep coming until the ring locks on."],
  steady: ["Hold still", "Almost there."],
  hold: ["Got it", "Starting the check. Keep your eye right there."],
};
function setBanner(key) {
  if (S.eye.banner === key) return;
  S.eye.banner = key;
  const [a, b] = BANNERS[key];
  $("camBanner").innerHTML = `<b>${a}</b>${b}<small>The move is being watched. Looking away, covering the camera or switching tabs cancels the check.</small>`;
}

// ---------- the flow ----------

function cameraMode(mode) {
  show("camera");
  const selfie = mode === "selfie";
  $("guide").className = "guide " + (selfie ? "selfie" : "close");
  $("btnShutter").hidden = !selfie;
  $("btnReady").hidden = selfie;
  $("countdown").hidden = true;
  // Ring the size an iris (11.7 mm) appears at the target distance. The video is shown
  // object-fit: cover, so CSS px per video px is the larger of the two axis ratios.
  const ring = $("ring");
  ring.hidden = selfie;
  if (!selfie) {
    const pxPerMM = video.videoWidth / (2 * TARGET_DISTANCE_MM * Math.tan((ASSUMED_FOV_DEG * Math.PI) / 360));
    const cssPerPx = Math.max(innerWidth / video.videoWidth, innerHeight / video.videoHeight);
    ring.style.width = ring.style.height = `${11.7 * pxPerMM * cssPerPx}px`;
  }
  if (selfie) {
    stopEyeTracking();
    $("camBanner").innerHTML = `<b>${S.enrolling ? "Enroll: take a selfie" : "Take a selfie"}</b>Lean in until your face fills the outline.`;
  } else {
    S.eye.banner = null;
    setBanner("find");
    startEyeTracking();
  }
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
    const cd = $("countdown");
    cd.hidden = false;
    for (let n = 3; n >= 1; n--) {
      cd.textContent = n;
      await sleep(0.8);
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
  show("home");
}

// ---------- wiring ----------

const params = new URLSearchParams(location.search);
$("user").value = params.get("user") || localStorage.getItem("inhuman.user") || "daniel";
$("user").addEventListener("change", () => { localStorage.setItem("inhuman.user", user()); poll(); });
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

show("home");
openReplay().then((replayed) => { if (!replayed) openLinkedRequest().then(poll); });
setInterval(poll, 2000);
