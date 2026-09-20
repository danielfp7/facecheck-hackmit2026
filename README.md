# FaceCheck

A Duo-style second factor that proves a **live human** is holding the phone, not a real-time face swap.

1. An outside app asks for verification; the phone shows the request.
2. Arm's-length selfie: matched against the enrolled face and sent back to the outside app.
3. Phone held ~3 inches from one eye; the screen goes to full brightness and flashes random colored shapes for about 5 seconds.
4. **Check 1, light response and lag.** Skin follows the screen's colors instantly; the only genuine delay is display + camera. A pipeline that must see the flash, re-render a face and inject it arrives 150–300 ms late. No response at all, or a response later than this phone's calibrated baseline + 100 ms, fails.
5. **Check 2, corneal reflection.** The eye is a tiny convex mirror, so it shows a minified copy of the screen. The server finds the reflection, fits the iris around it (irises are ~11.7 mm in everyone, so this also measures the true distance), and checks that the reflection's position and color match what was sent, that it sits inside the iris, and that it is cornea-sized (a laptop screen or print reflects at the wrong size). The shape outline is scored too once the reflection spans ~18 px, which needs the phone at about 4 inches.
6. **Continuity.** The selfie and the eye check must be one sitting and one person. Otherwise an attacker could show a deepfake for the selfie and their own real eye for the liveness checks. The app cancels the check if you leave it, if the camera is interrupted, or if more than 20 s pass after the selfie. The server runs face recognition on the eye-check frames themselves, aligned by hand from the iris position and size, and compares them to the selfie (measured: same person 0.36-0.67, different people <= 0.12). The phone also keeps ~10 small frames per second from the selfie until the flashes start, and the server watches the whole move: every detectable face must still be the selfie person, consecutive frames must be one continuous view (matched on fine detail; measured >= 0.70 for continuous footage and 0.11-0.18 across a cut between two people), and no frames may be missing.
7. **Vibration** (informational until tuned): three haptic bursts at server-chosen random times, with gyro and accelerometer logged on the camera's clock. The server checks the sensor felt each burst, whether the video jittered at those instants, and whether image motion follows the gyro overall. Injected video does neither.
8. Verdict: **verified**, **unverified** (with the failing signal named) or **unverifiable**.

## Live URL

```
https://disclaimer-protecting-talked-newcastle.trycloudflare.com
```

That is a Cloudflare quick tunnel to the server running on this Mac, started with:

```sh
cloudflared tunnel --url http://localhost:8000
```

HTTPS is the point: browsers refuse the camera on plain HTTP from anything but localhost, so
a phone or a judge's laptop needs this rather than the LAN address. **The URL changes every
time the tunnel restarts, and it dies when the Mac sleeps or the server stops.** Re-run the
command and paste the new URL. The Mac has to stay awake and on the network for the whole
demo.

**Why not Vercel.** It only suits the static pages, and the static pages are not the product:

- The server carries about 425 MB of dependencies (InsightFace, onnxruntime, OpenCV) against
  Vercel's 250 MB limit for a serverless function.
- A check takes 5 to 9 seconds to analyse. Vercel's Hobby plan stops a function at 10.
- Every check writes a capture folder, and serverless storage does not persist.

A container host (Fly.io, Render, Railway) would run it as-is. That is a job for after the
hackathon; the tunnel is what gets a URL in front of a judge today.

## Steps, in order

Where things stand: the app builds with Xcode 27 and runs on an iPhone 14 Pro, and genuine users verify end to end on real captures. Vibration is built but untuned, and no deepfake attack has been run against the phone yet, so section D is the work that remains. Sections A to C are for setting up another Mac or phone. Details for each step are in the sections below.

**A. Get the phone app running** (Xcode is a multi-GB download; start it first)

1. Install Xcode 27 (this Mac is on macOS 27) from developer.apple.com as a `.xip`, plus the iOS platform it offers. Then `sudo xcode-select -s /Applications/Xcode.app` and open Xcode once.
2. Generate and open the project: `ios/bin/xcodegen/bin/xcodegen generate --spec ios/project.yml`, then open `ios/FaceCheck.xcodeproj`.
3. Pick your signing team, plug in the iPhone, enable Developer Mode (needs a reboot), build.
4. Trust the developer profile on the phone: Settings → General → VPN & Device Management.
5. Phone settings: turn off Auto-Brightness, True Tone, Night Shift and Low Power Mode.

**B. Connect phone and server**

6. Start the server: `cd server && uv run uvicorn main:app --host 0.0.0.0 --port 8000`. It does not survive a reboot.
7. Turn on the iPhone's Personal Hotspot and connect the Mac over USB. Venue Wi-Fi usually blocks phone-to-laptop traffic.
8. In the app's Settings enter `http://<mac-name>.local:8000` (or `http://172.20.10.2:8000`) and accept the local-network prompt. The home screen stops saying "Can't reach the server" when it works.

**C. First real run**

9. Tap **Enroll my face** and take the selfie.
10. Tap **Run a test check** with the label `real`. Look at the Eye reflection tile: are the crops sharp, and is the shape visible in the eye?
11. If the crops are blurred (fixed-focus front camera, iPhone 13 and earlier), restart the server with `FACECHECK_SHAPE_MODE=layout`.

**D. Tune on real captures**

12. Record about 5 of each label: `real`, `screen-attack`, `replay`, `print`. Do the `real` ones with every teammate, including anyone with glasses and the darkest skin tone on the team.
13. `uv run --project server tools/replay.py --set-baseline` to store this phone's genuine lag.
14. `uv run --project server tools/replay.py`, read the gap between `real` and attack rows, and edit `THRESHOLDS` in `server/verdict.py`.
15. Measure the attacker's added lag for the pitch: `uv run --project server tools/mac_capture.py --swap-source <teammate>.jpg --label dlc-attack`.

**E. Demo**

16. Open <http://localhost:8000>, press **Sign in**, approve on the phone, and check the page turns green. Repeat pointing the phone at Deep-Live-Cam fullscreen and check it turns red with a reason.
17. Run the full loop 20 times in the demo room's lighting on the demo phone. Fix flakiness only.
18. Record a backup video of a genuine pass and an attack fail.

**F. Still to do:** tune vibration on real captures; run the Deep-Live-Cam attacks.

## Layout

| Path | What |
| --- | --- |
| `server/` | FastAPI + signal processing (`signals/`: `lag`, `cornea`, `continuity`, `identity`, `transit`, `vibration`; `verdict.py`) |
| `web/` | Demo relying-party page ("Demo Bank" sign-in) served at `/`; `web/app/` is the webcam client served at `/app/` |
| `ios/` | Swift app. `project.yml` → Xcode project via XcodeGen |
| `tools/mac_capture.py` | Mac webcam stand-in for the phone; also the injection/lag attack simulator |
| `tools/replay.py` | Re-scores saved captures; sets thresholds and the per-device lag baseline |
| `attack/` | Deep-Live-Cam test attacker (`setup.sh`), in its own venv |

## Run the server

```sh
cd server
uv run uvicorn main:app --host 0.0.0.0 --port 8000
uv run pytest tests -q          # synthetic ground-truth tests, ~1 min
```

Open <http://localhost:8000> for the demo sign-in page.

Try the loop without a phone:

```sh
uv run --project server tools/mac_capture.py --synthetic --lag-ms 60     # genuine
uv run --project server tools/mac_capture.py --synthetic --lag-ms 260    # delayed attacker
uv run --project server tools/mac_capture.py --synthetic --flat          # flat-screen reflection
```

## Web app (computer + webcam)

The same product in a browser, served by the same server: open <http://localhost:8000/app/> in Chrome. Enroll, then either **Run a test check**, or go to the demo page at <http://localhost:8000> and press **Sign in, verify on this computer**, which opens the web app straight onto that request. **Sign in, verify on my phone** sends it to the iPhone instead; a request aimed at one device is invisible to the other. Accounts are shared: enroll on either, verify on either.

Flow: selfie at your normal distance → lean in until the colored part of one eye fills the on-screen ring (about 8 inches / 20 cm) while the move is watched → full-screen flashes → results tiles. The phone uses the same ring, sized for 4 inches: "put your eye in the outline" left people at 5-6 inches.

What a browser changes, and how it is handled:

| Limitation | Handling |
| --- | --- |
| No video file with exact per-frame timestamps | The page grabs every camera frame with its capture time (`requestVideoFrameCallback`) and uploads them as `[uint32 length][JPEG]`; the server reads that like a video (`bundle.JpegSequence`) |
| Exposure usually can't be locked | The lag check switches to chromaticity with a full color-mixing fit; tested against simulated auto-exposure |
| Wide screen, no vertical room | Shapes go left / middle / right and are sized from the screen height; the server scores the reflection along x |
| Can't force brightness | The page asks for maximum brightness; a dim room helps |
| No haptics or motion sensors | No vibration check |
| Slower, more variable camera pipeline | Default lag baseline 130 ms for `web-*` devices; calibrate with `tools/replay.py --set-baseline` after a few genuine runs |

The eye reflection is the hard part on a laptop: at normal sitting distance it is only ~4 px, which is why the app asks you to lean in. A 1080p webcam is needed; at 720p it is marginal. Works over `http://localhost`; from another machine browsers require HTTPS for camera access (use a `cloudflared` tunnel).

Verified so far with headless Chrome and a fake camera (flow, upload, server parsing, results page). Not yet run with a real face.

## Build the phone app

1. Install Xcode (`.xip` from developer.apple.com matching the phone's iOS) and its iOS platform, then `sudo xcode-select -s /Applications/Xcode.app`.
2. `ios/bin/xcodegen/bin/xcodegen generate --spec ios/project.yml`, open `ios/FaceCheck.xcodeproj`.
3. Signing & Capabilities → pick your team (or put the Team ID in `project.yml` so regenerating keeps it). Change the bundle id if Xcode says it's taken.
4. Plug in the iPhone, enable Developer Mode, run. Trust the developer profile in Settings → General → VPN & Device Management.
5. In the app's Settings set the server address. Most reliable at a venue: turn on the iPhone's Personal Hotspot, connect the Mac over USB, and use `http://<mac-name>.local:8000` (the Mac is usually `172.20.10.2`). Accept the local-network prompt.
6. On the phone turn off Auto-Brightness, True Tone, Night Shift and Low Power Mode.

## Demo

Enroll once in the app. On the web page press **Sign in** → the phone shows the request → selfie → close-up flashes → the page turns green or red with the reason and tiles.

## Tuning (do this on the real phone before the demo)

Use the label picker on the app's home screen, record ~5 of each: `real`, `screen-attack` (phone pointed at Deep-Live-Cam fullscreen), `replay` (tablet playing a recording), `print`.

```sh
uv run --project server tools/replay.py --set-baseline   # stores this phone's genuine lag
uv run --project server tools/replay.py                  # compare rows, then edit THRESHOLDS in server/verdict.py
```

If the phone's front camera is fixed-focus (iPhone 13 and earlier) the shape outline blurs at 3 inches. Run the server with `FACECHECK_SHAPE_MODE=layout` to score shape position + color instead of the outline.

## Testing with a deepfake

Only swap faces of teammates who have agreed to it. Call the enrolled person the *victim* and the person at the keyboard the *attacker*. You need one clear, front-facing photo of the victim; their selfie from a saved capture works (`server/data/captures/<run>/selfie.jpg`).

**Start the live face swap**

```sh
attack/setup.sh      # once; downloads ~600 MB of models and a bundled ffmpeg
uv run --project server attack/live.py --source victim.jpg
```

`attack/live.py` is the simplest way: the same swap model (inswapper_128) in a plain full-screen window, with nothing to click. Pass several photos of the same person to `--source` for a steadier likeness. Space turns the swap on and off, `+`/`-` zoom in so the phone can be shown a life-size eye, `h` shows the frame rate, `q` quits. Run it from the Terminal app: macOS gives camera permission per app and refuses anything started from an editor. If it still can't read the camera, turn Terminal on under System Settings > Privacy & Security > Camera.

**Attack the web app on the computer.** A real attacker feeds the fake to the browser through a virtual camera. The test setup does the same without installing one: the swap tool serves its frames, and the web app's test mode uses them as its camera, so the check sees only swapped frames with the swap's real delay.

```sh
uv run --project server attack/live.py --serve        # from the Terminal app; no window, Ctrl-C to stop
```

Then open <http://localhost:8000/app/?inject> in Chrome. The page says it is in attack-test mode and labels the capture `inject-attack`. Run a check as usual, sitting at the Mac's camera.

Deep-Live-Cam's own app is the alternative:

```sh
attack/run.sh
```

`attack/run.sh` runs the swap with a live face enhancer (GPEN-256): about 12 fps with a visibly sharper face. `attack/run.sh fast` drops the enhancer for about 35 fps and a softer face. Measured here, both score about 0.9 against the victim in face recognition (a stranger scores -0.03, the pass mark is 0.35), so the enhancer is for how it looks to people, not for how strong the attack is.

In its window: **Select a face** → the victim's photo, then **Live**. macOS will ask for camera access for the terminal the first time. Make the preview as large as it goes, turn the Mac's brightness to maximum, and sit so the swapped face is roughly life-size. Launch it from the Terminal app (not from an editor), so macOS asks Terminal for camera access; without it the preview stays black.

**Optional, for the best-looking fake: pre-render it.** Live swapping already runs smoothly here (about 36 fps), but the face enhancer is too slow to use live. For a screen attack the fake doesn't need to be live, so film 20 s of the attacker (QuickTime → New Movie Recording, face filling the frame, slow head turns, looking at the camera) and render it offline with the face enhancer:

```sh
attack/render.sh attack/Deep-Live-Cam/victim.jpg ~/Movies/attacker.mov ~/Movies/deepfake.mp4    # ~7-8 min for 20 s; add --fast to skip the enhancer
```

Play `deepfake.mp4` fullscreen and looped, then run the attacks below against it.

**Attack 1: deepfake on a screen** (label `screen-attack`). The attacker sits at the Mac wearing the victim's face. On the phone choose the label, **Run a test check**, take the selfie *of the Mac screen*, then move the phone in to the on-screen eye as the app asks. Expected: the face match may well pass, since that is the point of a deepfake. It should then fail on **Eye reflection** (a flat screen has no cornea-sized reflection inside an iris) and probably on **Light response** (a glowing screen doesn't take on the phone's colors the way skin does).

**Attack 2: deepfake for the selfie, real eye for the check** (label `screen-attack`). Take the selfie of the Mac screen, then turn the phone to the attacker's own real eye. Expected: **Continuity** fails, with "the camera view jumped", "a different face appeared", or "the face in the eye check is not the person in the selfie".

**Attack 3: leave and come back.** After the selfie, swipe out of the app. Expected: the check is cancelled on the phone.

**Attack 4: injected video, for the lag number.** An iPhone's camera can't be fed fake frames without a jailbreak, so this runs on the Mac's webcam, where every frame goes through the real swap model and is stamped when it would reach the app:

```sh
uv run --project server tools/mac_capture.py --user <victim> --label mac-real                     # baseline, no swap
uv run --project server tools/mac_capture.py --user <victim> --swap-source victim.jpg --label dlc-attack
```

Compare the **lag** the two runs print; that difference is the attacker's added delay. Measure it, don't assume it: a well-configured swap is fast (Deep-Live-Cam's own pipeline runs at about 28 ms per frame, 36 fps, on this Mac), so the extra delay comes mostly from the attacker's capture, copy and display hops, which the literature puts at 150-300 ms end to end. The limit is baseline + 100 ms. If a tuned attacker measures under that, lag alone doesn't stop them and the eye reflection and continuity checks have to. Neither Mac run can come back verified: a webcam at arm's length can't resolve the eye reflection. This one exists for the measured delay, which is the number for the pitch.

**Controls, so a red result means something:** a genuine run by the victim (should verify), a genuine run by a teammate with glasses, a tablet replaying a recording of the victim (`replay`), and a printed photo (`print`).

Afterwards, `uv run --project server tools/replay.py` prints one row per saved capture for the results table.

## Safety

The sequence holds every state for at least 0.34 s (under 2 flashes per second, below the WCAG 2.3.1 limit of 3), uses an orange-red rather than saturated red, shows a photosensitivity warning first, and stops on any tap.

## What is and isn't validated

On real iPhone 14 Pro captures: Check 1, Check 2 (position + color; works through glasses), face match and continuity, including rejecting every selfie/eye-check pairing of two different people. Vibration passes its unit test on simulated signals but has not been tuned on real captures, so it is informational. No deepfake attack has been run against the phone yet.
