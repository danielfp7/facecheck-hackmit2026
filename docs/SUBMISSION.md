# Plume submission

Submission closes **11:00am**. The library disclosure below is not optional: HackMIT disqualifies
undisclosed libraries. Paste the whole "Libraries, models and tools" section into the free-text
field, and if Plume has a dedicated dependencies field, paste it there too. Better duplicated than
missing.

**Before you submit, open <http://localhost:8000/app/attacks.html> and read the three counters.**
They count live and they are moving: 13 / 13 / 11 at 02:12, 14 / 14 / 11 at 02:40. This document
says 13 throughout. Whatever the page says at 10:45 is the number that goes in the submission, in
this file, in PITCH.md and in DECK.md. The ratio does not move and that is the claim: every attack
has been rejected. The 0.88 to 0.98 range and the 0.35 pass mark are stable.

---

## Name

**FaceCheck**

## Tagline (one line)

A second factor that proves a live human is at the camera, not a real-time deepfake.

## Short description (about 280 characters)

Face recognition cannot tell you from a live face swap. FaceCheck flashes coloured shapes at your eye
and reads their reflection off your cornea, a 7.8 mm convex mirror. 13 live deepfake attacks, 13
rejected. Face recognition scored those same fakes 0.88 to 0.98 against a 0.35 pass mark.

## What it does

FaceCheck is a step-up authentication factor, in the same slot as a push notification from an
authenticator app. An application asks for verification. The user takes an arm's-length selfie,
then leans in until one eye fills a ring on the screen. The screen goes to full brightness and
flashes randomly chosen coloured shapes for about five seconds. The server returns **verified**,
**unverified** with the failing check named, or **unverifiable**.

It runs two ways: an iPhone app, and a web app on any laptop webcam. Both talk to the same server
and share one account, so you can enrol on either and verify on either.

The threat it is built for is the one that hit the engineering firm Arup in 2024, when a finance
worker joined a video call with a deepfaked CFO and colleagues and transferred about US$25 million
to accounts in Hong Kong. The face was the credential and the face was fake.

## How it works

Three checks, plus one informational signal. None of them is a classifier trained to spot
"deepfake artefacts". They are physics and bookkeeping, which is why they generalise to a face-swap
model they have never seen.

**1. Light response and lag.** The screen is a light source. Skin lit by a flash changes colour
with no physical delay, so the only genuine lag is the display plus the camera pipeline, which we
calibrate per device. Measured baselines: **22.4 ms** on an iPhone 14 Pro, **105.5 ms** in the
browser on a Mac webcam. A pipeline that has to see the flash, re-render a face and inject it
arrives late. Across our attacks, injected frames landed at **120 to 598 ms**. The pass limit is
the device baseline plus 100 ms. Where a browser cannot lock exposure, the fit switches to
chromaticity with a full colour-mixing model.

**2. Corneal reflection.** A cornea is a convex mirror of roughly 7.8 mm radius, so it shows a
minified, flipped copy of the screen. The server finds the reflection of the displayed shape, fits
the iris around it, and because irises are about **11.7 mm** across in every adult, that fit
doubles as a ruler and gives the true distance to the eye. Then four tests: the reflection must sit
where the shape was displayed, carry the right colour, sit inside the iris, and be cornea sized.
On a genuine capture the reflection measures **1.9 mm across at 205 mm** from the camera, against
an expected 2.7 mm. A phone held up to a laptop playing a deepfake produces a reflection about
**five times too large**, because a flat screen is not a 7.8 mm mirror. A generated face produces
none at all. When the reflection spans at least 18 pixels the shape's outline is scored too.

**3. Continuity.** Otherwise an attacker shows a deepfake for the selfie and their own real eye for
the liveness checks. The selfie and the eye check must be one person in one unbroken sitting. The
server runs face recognition on the eye-check frames themselves, aligning the partial face by hand
from the iris position and scale, because face detectors fail on a face cropped that hard.
Measured: same person **0.36 to 0.67**, different people **at or below 0.12**, threshold 0.25. On
top of that the client keeps about ten thumbnails per second during the move inward, and the server
checks frame to frame that it is one continuous view with no cut, no hole in the timestamps, and no
other face appearing.

**4. Vibration (informational only).** The phone fires haptic bursts at server-chosen random times
and logs gyro and accelerometer on the camera's clock. Injected video does not shake when the phone
shakes. This is built and passes its unit tests on simulated signals, but it is not tuned on real
captures, so it never contributes to a verdict. We left it visible and labelled rather than quietly
switching it off.

## Results

We built the attacker before the defence: Deep-Live-Cam driving the inswapper_128 face-swap model,
running at about 30 frames per second on the demo Mac, wearing a teammate's face from a single
photo. Attacks were delivered three ways: injected into the browser the way a virtual camera would,
shown to the phone on a laptop screen, and swapped into the Mac's own capture path.

- **13 attacks run. 13 rejected.** (Set this from the live counter before submitting. As of 02:40
  the log holds 14 attacks, all rejected: 13 live face swaps plus 1 synthetic capture with a known
  260 ms delay injected to exercise the timing check on its own.)
- In **11** of them, ordinary face recognition (ArcFace from InsightFace buffalo_l) scored the fake
  between **0.88 and 0.98** against a **0.35** pass mark. Face recognition alone would have approved
  every one of those. In the others, no face reached the recogniser at all.
- Which check caught it, across the 14 attacks recorded by 02:40: corneal reflection 8, light
  response 3, continuity 2, timing 1.
- Genuine captures: 18 recorded, 9 verified. Two of the nine failures are deliberate negative
  controls that were supposed to fail (a selfie and eye check from two different people; a selfie of
  someone who is not the enrolled user, which scored 0.00). Two more are early runs pointed at a
  screen. The remaining five failed with "lean in closer" or "the reflection did not line up",
  which is a usability failure, not a security failure. It fails closed.
- A verdict takes about **6 seconds** on a laptop CPU, no GPU.

Every number above is recomputed from saved captures on disk. The attack log page at
`/app/attacks.html` reads them live, and every card links to the full result.

## Honest limits

We would rather say these than be caught on them.

- Thresholds are tuned on a small number of genuine captures from a handful of people. This is not
  a statistically meaningful sample and we do not claim a false-accept or false-reject rate.
- No independent evaluation. Everyone who has attacked this system also built it.
- Most browsers cannot lock camera exposure. We handle that by fitting chromaticity instead of
  absolute brightness, and it is tested against simulated auto-exposure, but a real webcam's
  auto-exposure is a source of noise we have not fully characterised.
- We have not faced an attacker who specifically tries to synthesise a correct corneal reflection:
  right size, right position, right colour, inside a correctly sized iris, tracking a sequence the
  attacker learns only at run time. That is the interesting attack and it is untested. We think it
  is expensive, because the attacker has to render physically correct optics inside a 2 mm patch at
  the right scale, within the lag budget, without knowing the sequence in advance. We have not
  proved it.
- The vibration signal is untuned and informational.
- The iPhone app needs a front camera with autofocus. On iPhone 13 and earlier the shape outline
  blurs at close range, and the server falls back to scoring position and colour only.

## What we built and what we used

We wrote: the challenge protocol and its seizure-safety constraints, the light-response and lag
estimator, the entire corneal reflection pipeline (blob localisation, iris fit, per-state
registration, geometry gate, shape scoring), the hand-aligned partial-face continuity check, the
frame-by-frame transit check, the verdict fusion, the FastAPI server, the iPhone app, the web
client including its timestamped frame container, the relying-party demo, and the attack harness.

We used off-the-shelf: a face-recognition model, a face detector, an ONNX runtime, a browser face
landmarker, a web framework, and the face-swap model we attacked ourselves with. None of the three
checks is a pretrained liveness or deepfake detector. There is no such model in this project.

## Libraries, models and tools (full disclosure)

### Product, server (Python 3.12, managed with uv)

| Library | Version | What it does here |
| --- | --- | --- |
| FastAPI | 0.141.1 | HTTP API: enrolment, challenge issue, verification, capture serving |
| uvicorn | 0.53.0 | ASGI server |
| python-multipart | 0.0.32 | multipart upload parsing for video, frames, selfie |
| numpy | 2.5.3 | all signal maths |
| scipy | 1.18.1 | median filtering and signal processing in the vibration check |
| opencv-python (cv2) | 5.0.0.93 | image decode, resize, warp, Gaussian blur, phase correlation |
| InsightFace | 2.0 | `buffalo_l` model pack: SCRFD face detection and **ArcFace** face recognition embeddings |
| onnxruntime | 1.30.0 | runs the InsightFace ONNX models, CPU execution provider |
| onnx | 1.23.0 | transitive, via InsightFace |
| Pillow | 12.3.0 | transitive, via InsightFace |
| scikit-image | 0.26.0 | transitive, via InsightFace |
| httpx | 0.28.1 | HTTP client in `tools/mac_capture.py` |
| pytest | 9.1.1 | development only, synthetic ground-truth tests |

Pretrained model weights used in the product: **InsightFace buffalo_l** (SCRFD detector + ArcFace
recogniser). No other pretrained weights run in the product.

### Product, web client

| Library | What it does here |
| --- | --- |
| **MediaPipe Tasks Vision, FaceLandmarker** (`vision_bundle.mjs`, `face_landmarker.task`, WASM runtime) | live face and iris tracking in the browser: iris centres and radii, distance from the iris as a ruler, face box for the self-timed selfie. **Vendored** under `web/app/vendor/mediapipe/` so nothing is fetched from the internet during a check. |

No JavaScript framework, no build step, no other front-end dependency. Plain HTML, CSS and JS.

### Product, iPhone app

| Library | What it does here |
| --- | --- |
| Swift, SwiftUI | app and UI |
| AVFoundation | camera capture, exposure lock, per-frame timestamps |
| CoreMotion | gyro and accelerometer for the vibration signal |
| CoreHaptics | the haptic bursts |
| XcodeGen | generates the Xcode project from `ios/project.yml` |

### Attack rig only, never part of the product

These exist so we could attack our own system. They are in a separate virtual environment, they are
not imported by the server or either client, and nothing they produce ships.

| Library / model | What it does here |
| --- | --- |
| **Deep-Live-Cam** (github.com/hacksider/Deep-Live-Cam) | real-time face-swap application used as the attacker |
| **inswapper_128** (`inswapper_128_fp16.onnx`) | the face-swap model itself |
| **GPEN-BFR-256 / GPEN-BFR-512** | face enhancers, used to make the fake look better to a human |
| GFPGAN (`gfpgan-1024.onnx`) | downloaded by `attack/setup.sh` as an alternative enhancer |
| InsightFace 0.7.3, opencv 4.14, onnxruntime 1.28 | pinned by Deep-Live-Cam, kept in its own venv |
| imageio-ffmpeg | supplies a static ffmpeg binary so Deep-Live-Cam will start |

Face swaps were run only on faces of team members who agreed to it. Source photographs of people
are excluded from the repository by `.gitignore` and were never committed.

### Tooling

| Tool | What it did |
| --- | --- |
| **Claude Code (Anthropic)** | used to write code throughout this project, across the server, both clients and the attack harness, under our direction and review |
| uv | Python environment and dependency management |
| Xcode 27 | iOS build |

## What we learned

- The first design for the continuity check was wrong, and measuring it is what told us. Comparing
  the eye region directly fails: a person's own eye scored 0.47 to 0.70 against their selfie while
  strangers' eyes scored as high as 0.82. What works is running face recognition on the liveness
  frames, aligning the partial face by hand from the iris, because the iris gives both position and
  scale.
- One eye gives you a mirror and a ruler at the same time. The iris fit that locates the reflection
  also measures true distance, which is what makes the "is it cornea sized" test possible at all.
- Building the attacker first changed the defence. The lag check on its own did not stop most of
  our injection attacks, because a well-tuned swap adds only 120 to 200 ms, which sits under the
  browser's limit. We knew that only because we measured it, and it is why the corneal geometry
  check exists.
- Most of the engineering was not machine learning. It was honest timestamps on camera frames,
  exposure locking, keeping the flash sequence under two transitions per second for photosensitivity
  safety, and making a browser behave enough like a phone camera to compare the two.

## Safety

The flash sequence holds every state for at least 0.34 s, which is under two flashes per second and
below the WCAG 2.3.1 limit of three. It uses an orange-red rather than a saturated red, shows a
photosensitivity warning before it starts, and stops on any tap or Esc.

## Links

- Repository: this repo
- Demo relying-party page: `/` (served by the server)
- Web client: `/app/`
- Attack log with every saved attack and its result: `/app/attacks.html`
