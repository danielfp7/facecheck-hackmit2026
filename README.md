# InHuman

A Duo-style second factor that proves a **live human** is holding the phone, not a real-time face swap.

1. An outside app asks for verification; the phone shows the request.
2. Arm's-length selfie: matched against the enrolled face and sent back to the outside app.
3. Phone held ~3 inches from one eye; the screen goes to full brightness and flashes random colored shapes for about 5 seconds.
4. **Check 1, light response and lag.** Skin follows the screen's colors instantly; the only genuine delay is display + camera. A pipeline that must see the flash, re-render a face and inject it arrives 150–300 ms late. No response at all, or a response later than this phone's calibrated baseline + 100 ms, fails.
5. **Check 2, corneal reflection.** The eye is a tiny convex mirror, so it shows a minified copy of the screen. The server reads the shape, position and color out of that reflection and checks they match what was sent, and that the reflection is cornea-sized (a laptop screen or print reflects at the wrong size).
6. Verdict: **verified**, **unverified** (with the failing signal named) or **unverifiable**.

## Steps, in order

Where things stand: the server, web page, Mac stand-in and attack rig are built and pass their tests on simulated captures. The iPhone app is written but has never been compiled, and nothing has been tuned on real footage. Details for each step are in the sections below.

**A. Get the phone app running** (blocked on Xcode; start the download first)

1. Install Xcode 27 (this Mac is on macOS 27) from developer.apple.com as a `.xip`, plus the iOS platform it offers. Then `sudo xcode-select -s /Applications/Xcode.app` and open Xcode once.
2. Generate and open the project: `ios/bin/xcodegen/bin/xcodegen generate --spec ios/project.yml`, then open `ios/InHuman.xcodeproj`.
3. Pick your signing team, plug in the iPhone, enable Developer Mode (needs a reboot), build. Fix compile errors as they come up; the Swift has only been syntax-checked.
4. Trust the developer profile on the phone: Settings → General → VPN & Device Management.
5. Phone settings: turn off Auto-Brightness, True Tone, Night Shift and Low Power Mode.

**B. Connect phone and server**

6. Start the server: `cd server && uv run uvicorn main:app --host 0.0.0.0 --port 8000`. It does not survive a reboot.
7. Turn on the iPhone's Personal Hotspot and connect the Mac over USB. Venue Wi-Fi usually blocks phone-to-laptop traffic.
8. In the app's Settings enter `http://<mac-name>.local:8000` (or `http://172.20.10.2:8000`) and accept the local-network prompt. The home screen stops saying "Can't reach the server" when it works.

**C. First real run**

9. Tap **Enroll my face** and take the selfie.
10. Tap **Run a test check** with the label `real`. Look at the Eye reflection tile: are the crops sharp, and is the shape visible in the eye?
11. If the crops are blurred (fixed-focus front camera, iPhone 13 and earlier), restart the server with `INHUMAN_SHAPE_MODE=layout`.

**D. Tune on real captures**

12. Record about 5 of each label: `real`, `screen-attack`, `replay`, `print`. Do the `real` ones with every teammate, including anyone with glasses and the darkest skin tone on the team.
13. `uv run --project server tools/replay.py --set-baseline` to store this phone's genuine lag.
14. `uv run --project server tools/replay.py`, read the gap between `real` and attack rows, and edit `THRESHOLDS` in `server/verdict.py`.
15. Measure the attacker's added lag for the pitch: `uv run --project server tools/mac_capture.py --swap-source <teammate>.jpg --label dlc-attack`.

**E. Demo**

16. Open <http://localhost:8000>, press **Sign in**, approve on the phone, and check the page turns green. Repeat pointing the phone at Deep-Live-Cam fullscreen and check it turns red with a reason.
17. Run the full loop 20 times in the demo room's lighting on the demo phone. Fix flakiness only.
18. Record a backup video of a genuine pass and an attack fail.

**F. If time remains:** vibration test, then rPPG heartbeat.

## Layout

| Path | What |
| --- | --- |
| `server/` | FastAPI + signal processing (`signals/lag.py`, `signals/cornea.py`, `signals/identity.py`, `verdict.py`) |
| `web/` | Demo relying-party page ("Demo Bank" sign-in) served at `/` |
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

## Build the phone app

1. Install Xcode (`.xip` from developer.apple.com matching the phone's iOS) and its iOS platform, then `sudo xcode-select -s /Applications/Xcode.app`.
2. `ios/bin/xcodegen/bin/xcodegen generate --spec ios/project.yml`, open `ios/InHuman.xcodeproj`.
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

If the phone's front camera is fixed-focus (iPhone 13 and earlier) the shape outline blurs at 3 inches. Run the server with `INHUMAN_SHAPE_MODE=layout` to score shape position + color instead of the outline.

## Attack rig

```sh
attack/setup.sh
cd attack/Deep-Live-Cam && .venv/bin/python run.py --execution-provider coreml --live-mirror --live-resizable
```

- **Presentation attack:** swap fullscreen on the Mac and point the phone at it. Expected to fail Check 2 (reflection not cornea-sized) and Check 1 (no diffuse response).
- **Injection / lag attack:** an iPhone's camera can't be fed fake frames, so the pipeline delay is measured on the Mac: `tools/mac_capture.py --swap-source victim.jpg` runs the real inswapper per frame and stamps frames on arrival. `--attack-delay-ms N` adds a fixed delay instead.

Only swap faces of teammates who have agreed to it.

## Safety

The sequence holds every state for at least 0.34 s (under 2 flashes per second, below the WCAG 2.3.1 limit of 3), uses an orange-red rather than saturated red, shows a photosensitivity warning first, and stops on any tap.

## Not built yet

Vibration test (random haptic bursts vs. frame motion and gyro; `meta.json` already reserves `imu` and `haptics`) and rPPG heartbeat. Literature says rPPG only catches photos and masks, so it is last.
