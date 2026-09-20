// Live face + iris tracking (ES module). Wraps MediaPipe's FaceLandmarker, vendored under
// ./vendor/mediapipe so nothing is fetched from the internet during a check.
//
// What it gives the flow:
//   - both iris centres and radii in video pixels, every frame
//   - the true distance to the camera, from the iris as a ruler (irises are ~11.7 mm in everyone)
//   - a face box, so the selfie can take itself when the face is framed and still
//
// app.js is a plain script, so the API hangs off window.InHumanTracker. Everything that uses
// it must cope with it being absent: tracking is an upgrade, never a requirement.

import { FaceLandmarker, FilesetResolver } from "./vendor/mediapipe/vision_bundle.mjs";

const IRIS_MM = 11.7;
const L_IRIS = [468, 469, 470, 471, 472];     // centre, then four points on the iris edge
const R_IRIS = [473, 474, 475, 476, 477];
const BASE = new URL("./vendor/mediapipe/", import.meta.url).href;

let landmarker = null;
let lastTs = 0;

async function create(delegate) {
  const fileset = await FilesetResolver.forVisionTasks(BASE + "wasm");
  return FaceLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: BASE + "face_landmarker.task", delegate },
    runningMode: "VIDEO",
    numFaces: 1,
    // Permissive on purpose: at the eye-check distance half the face is out of frame.
    minFaceDetectionConfidence: 0.3,
    minFacePresenceConfidence: 0.3,
    minTrackingConfidence: 0.3,
  });
}

async function init() {
  if (landmarker) return true;
  try { landmarker = await create("GPU"); } catch { landmarker = await create("CPU"); }
  return true;
}

function irisOf(lms, idx, w, h) {
  const cx = lms[idx[0]].x * w, cy = lms[idx[0]].y * h;
  let r = 0;
  for (let k = 1; k < idx.length; k++) r += Math.hypot(lms[idx[k]].x * w - cx, lms[idx[k]].y * h - cy);
  return { x: cx, y: cy, r: r / (idx.length - 1) };
}

/**
 * Track one frame. `source` is a <video>, <canvas> or <img>; w/h its pixel size.
 * Returns null when no face is found, else:
 *   { eyes: [{x, y, r}, {x, y, r}], eye: the larger (nearer) one, box: {x, y, w, h},
 *     distanceMM(fovDeg): distance from the nearer iris }
 */
function track(source, w, h, tsMs) {
  if (!landmarker) return null;
  // detectForVideo wants strictly increasing timestamps.
  const ts = Math.max(lastTs + 1, Math.round(tsMs ?? performance.now()));
  lastTs = ts;
  const res = landmarker.detectForVideo(source, ts);
  const lms = res.faceLandmarks && res.faceLandmarks[0];
  if (!lms || lms.length < 478) return null;
  const a = irisOf(lms, L_IRIS, w, h), b = irisOf(lms, R_IRIS, w, h);
  let x0 = 1, y0 = 1, x1 = 0, y1 = 0;
  for (const p of lms) { if (p.x < x0) x0 = p.x; if (p.x > x1) x1 = p.x; if (p.y < y0) y0 = p.y; if (p.y > y1) y1 = p.y; }
  const inFrame = (e) => e.x > 0 && e.y > 0 && e.x < w && e.y < h;
  const eyes = [a, b];
  const visible = eyes.filter(inFrame);
  const eye = (visible.length ? visible : eyes).reduce((p, q) => (q.r > p.r ? q : p));
  return {
    eyes, eye,
    box: { x: x0 * w, y: y0 * h, w: (x1 - x0) * w, h: (y1 - y0) * h },
    distanceMM: (fovDeg) => {
      const pxPerMM = (2 * eye.r) / IRIS_MM;
      return w / (2 * Math.tan((fovDeg * Math.PI) / 360)) / pxPerMM;
    },
  };
}

window.InHumanTracker = { init, track };
window.dispatchEvent(new Event("inhuman-tracker-loaded"));
