# Demo runbook

Literal. Follow it top to bottom. Every step has a fallback; if a fallback fails, drop to the next
one and keep talking. A judge will forgive a fallback. A judge will not forgive silence.

Repo root is `/Users/danielpacheco/HackMIT`. All commands are absolute so they can be pasted into
any shell.

---

## 0. The one trap that will ruin the demo

**`attack/live.py` holds the Mac's camera. The browser cannot open the same camera for a genuine
run while it is running.**

In `?inject` mode the page never touches the real camera, so the attack demo is fine. The genuine
run is not. Therefore:

- Best order: **genuine run on the iPhone**, then **attack run on the laptop** with the rig already
  warm. No conflict, and you show both form factors.
- If the phone is out: do the **genuine run on the laptop first**, then start the rig, then the
  attack run. Budget 30 seconds for model load.
- Test this at 10:00. If the browser gets a black viewfinder while `live.py` is running, that
  confirms the conflict and you use the ordering above for the whole expo.

---

## 1. Setup, by 10:00

Do this once, in this order. Leave everything running for the whole expo.

### 1.1 Room and machine

```sh
# Mac: full brightness, no adaptive anything.
# System Settings > Displays: Auto-brightness OFF, True Tone OFF, Night Shift OFF.
# System Settings > Focus: Do Not Disturb ON.
# Plug in power. Close Zoom, FaceTime, Photo Booth, and any other browser tab holding a camera.
```

Dim the table if you can. The check reads the screen's light on your face; a spotlight overhead
fights it. If the room is bright, sit closer and expect more "lean in closer" results.

Phone, if you are demoing it: Auto-Brightness off, True Tone off, Night Shift off, Low Power Mode
off.

### 1.2 Terminal window 1: the server

```sh
cd /Users/danielpacheco/HackMIT/server
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Confirm:

```sh
curl -s http://localhost:8000/health
# {"ok":true,"shape_mode":"auto"}
```

**Fallback:** port already in use (`Address already in use`) means a server from earlier is still
up. Check `/health` first. If it answers, you are done, do not start a second one. If it does not:

```sh
lsof -ti:8000 | xargs kill
```

then start again.

**Fallback:** if `uv` itself fails, the demo is dead. Go straight to the recorded video (section 6).

### 1.3 Terminal window 2: the attack rig

Must be the **Terminal app**, not a terminal inside an editor. macOS grants camera access per app
and refuses anything launched from VS Code.

```sh
cd /Users/danielpacheco/HackMIT
uv run --project server attack/live.py --source server/data/users/daniel.jpg --serve
```

`--serve` starts a frame server on `127.0.0.1:8765` with no window. `server/data/users/daniel.jpg`
is the enrolled face, which is the strongest possible swap source.

Confirm it is producing frames:

```sh
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8765/frame?after=0"
# 200
```

**Fallback:** black frames or a camera error. Turn Terminal on under System Settings > Privacy &
Security > Camera. If Terminal is not listed:

```sh
tccutil reset Camera com.apple.Terminal
```

then relaunch it so macOS asks.

**Fallback:** if the rig will not run at all, the attack demo becomes a replay. See section 5.

### 1.4 Warm the models

The first face-recognition call loads buffalo_l and takes several seconds. Do not let a judge watch
that. Warm it with one throwaway run:

```sh
uv run --project server /Users/danielpacheco/HackMIT/tools/mac_capture.py --synthetic --lag-ms 60
```

That writes a `run`-labelled capture, which does not show up in the attack log (it only counts
`*attack*` and `real`). Harmless.

### 1.5 Browser tabs, in this order, left to right

1. <http://localhost:8000> - the bank page. This is the demo.
2. <http://localhost:8000/?inject> - the bank page in attack mode. Opens the FaceCheck tab already
   pointed at the face swap.
3. <http://localhost:8000/app/attacks.html> - the attack log. This is the closing slide.
4. <http://localhost:8000/?replay=0920-004853_inject-attack_b1c2d3b7784326d3> - the attack fallback,
   pre-loaded so it renders instantly.

Use Chrome. Everything works over `http://localhost`; a hostname other than localhost needs HTTPS
for camera access and you do not have time for that.

### 1.6 Check the numbers before you claim them

Open the attack log. Read the three counters out loud to each other:

- attacks
- caught by FaceCheck
- fooled face recognition

At 02:12 today: **13 / 13 / 11**. At 02:40: **14 / 14 / 11**, because another attack was recorded at
02:36. The counters move every time anyone runs a check, so say the number on the screen, not the
number in this document. Fix the same number in PITCH.md, DECK.md and SUBMISSION.md before the
11:00 submission deadline.

Two things never move, so lean on them: **every attack has been rejected**, and face recognition
scored the fakes **0.88 to 0.98** against a **0.35** pass mark.

**Know what the counter counts.** At 02:40 the 14 attacks were 13 live face swaps plus 1 synthetic
capture with a known 260 ms delay, which we used to exercise the timing check on its own. Its card
is labelled "Synthetic attack" and a judge can see it. Point at it before they do. See PITCH.md,
"Exactly what the counter counts".

Also note the "Genuine checks" section is counted the same way and reads **9 of 18 passed**. Know
why before a judge scrolls down: DEMO_SCRIPT section 6, and FAQ.md question 5.

### 1.7 Record the backup video (do not skip)

Before the room fills up, screen-record one genuine pass and one attack rejection end to end.
QuickTime > File > New Screen Recording. Save both to `~/Movies/facecheck-backup.mov`. Open it once
so it is in QuickTime's recent files. This is the last fallback and it takes four minutes to make.

---

## 2. Reset between judges (30 seconds)

1. Bank page: reload it. The status panel clears and both buttons re-enable.
2. FaceCheck tab: press **Done**, or reload `/app/`.
3. Check the rig is still alive: `curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8765/frame?after=0"`.
4. Wipe the laptop camera and the phone's front camera with a cloth. A smudge costs you the corneal
   reflection.
5. Brightness back to maximum. Some apps knock it down.

---

## 3. The run of show

Times are cumulative. Speaker letters match PITCH.md.

| Time | Who | What you do | What you say |
| --- | --- | --- | --- |
| 0:00 | [A] | Stand. Bank page on screen, nothing running. | Arup hook. See PITCH.md section 1. |
| 0:25 | [A] | Point at the amount and the memo. | "Twenty five point six million out, new beneficiary, urgent. The memo says the CFO approved it on a video call." |
| 0:35 | [A] | Press **Verify on my phone** (or **Verify on this computer** if the phone is out). | "This wire needs a live-person check." |
| 0:45 | [A] | Approve on the device. Selfie at arm's length. | "Selfie at arm's length." |
| 0:55 | [A] | Lean in until the eye fills the ring. Flashes run about 5 s. | "Now I lean in until my eye fills the ring, and the screen flashes at it." |
| 1:10 | [A] | Result lands on the bank page in about 6 s. Point at the tiles. | "Verified. Lag 101 milliseconds. The reflection in my cornea is 1.9 millimetres across, at 205 millimetres. Wire released." |
| 1:25 | [B] | Take over the laptop. Switch to the `?inject` tab. | "Same page, same account. This time my camera is a live face swap." |
| 1:35 | [B] | Show the swap for two seconds, real face then swapped. | "Deep-Live-Cam, inswapper_128, free on GitHub, thirty frames a second on this laptop." |
| 1:45 | [B] | Press **Verify on this computer**. Run the check: selfie, lean in, flashes. | "A real attacker pushes this in with a virtual camera. Ours feeds the page directly. Same frames, same delay." |
| 2:15 | [B] | Result lands. Point at the left cell of the comparison panel. | "Blocked. And face recognition scored this fake 0.98 against a 0.35 pass mark. It would have released the wire." |
| 2:35 | [C] | Stay on the result. Point at the Light response tile, then the Eye reflection tile. | How it works. PITCH.md section 4. |
| 3:40 | [D] | Open the attack log tab. | Continuity, 13 of 13, and the honest limits. PITCH.md section 5. |
| 4:30 | [A] | Turn the laptop to face the judge. | "Want to try it?" |
| 4:40 | any | The judge's hands, section 4 below. | Coach, do not narrate. |
| 6:00 | all | Stop. Take questions. | FAQ.md. |

---

## 4. The judge's hands

Two options. Pick by how much time is left and how confident the judge looks.

### Option A, 40 seconds, low risk: the judge drives the relying party

Hand them the trackpad on the bank page.

1. "Press **Verify on this computer**."
2. You take the camera seat and do the check while they watch the bank page update.
3. "Watch the step bar at the top. Approval turns blue while it runs, then green."

They touch the product, nothing can go wrong with their face, and they see the approval flow as a
customer would.

### Option B, 90 seconds, higher impact: the judge enrols and verifies

Only if you have the time and the room is not too bright.

1. Open <http://localhost:8000/app/>.
2. "Type any username in the box." Let them type their own.
3. "Press **Enroll my face**." Selfie at arm's length. The photo takes itself once their face fills
   the outline.
4. **Run a test check** appears within two seconds of enrolling. "Press **Run a test check**."
   Then **Continue** past the photosensitivity warning.
5. Coach them, out loud, while they lean in: **"Closer. Keep going. Until one eye fills the ring."**
   People stop about 30 percent too far away. That single sentence is the difference between a
   green result and "lean in closer".
6. If it says **lean in closer**: this is the honest failure mode, not a crash. Say so.
   "That is it refusing to guess. It needs about 20 centimetres to resolve a reflection that is
   two millimetres wide. Try once more and get uncomfortably close." Second attempts usually pass.
7. Two attempts maximum, then move on. Do not let a judge fail three times at your table.

Before the next judge, their enrolment stays on disk under `server/data/users/`. That is fine. Do
not delete anything mid-expo.

**Know this before you choose Option B.** The label dropdown defaults to `real`, so every judge run
is saved as a genuine capture and lands in the "Genuine checks" section of the attack log. A judge
who passes moves the counter from 9 of 18 to 10 of 19. A judge who fails moves it to 9 of 19. Over
an afternoon of judges who do not lean in far enough, that counter degrades in public.

Our recommendation: default to Option A, and use Option B when the room is dim, you have the time,
and you are willing to coach properly. Do not quietly relabel a judge's genuine run as something
else to protect the number. If it drops, explain it: "that is every attempt anyone has made at this
table today, including people who have never seen it before, and every failure says lean in closer."
Watching the counter move honestly in front of a judge is worth more than a tidy one.

### Never

- Never point the camera at a judge's face without asking.
- Never swap a judge's face, or anyone's face who has not agreed. The rig runs on team faces only.
- Never mention the photosensitivity warning as a joke. Read it as written and let them press
  Continue themselves.

---

## 5. Fallbacks, in order

Every saved check can be re-rendered from disk. No camera, no rig, no live run required. Both the
bank page and the FaceCheck app take `?replay=<capture folder>`.

### The replay URLs that matter

| Use it when | URL |
| --- | --- |
| The attack demo fails, and you want the money shot (face recognition 0.98 next to "Transfer blocked") | <http://localhost:8000/?replay=0920-004853_inject-attack_b1c2d3b7784326d3> |
| The genuine run fails, and you want a green bank page | <http://localhost:8000/?replay=0919-203905_real_383daac7abd8d978> |
| You want the full tile detail of a genuine web pass | <http://localhost:8000/app/?replay=0919-203905_real_383daac7abd8d978> |
| You want a genuine pass on the phone instead (lag 22.5 ms) | <http://localhost:8000/app/?replay=0919-200442_real_0e9a5617e83a05b9> |
| Someone asks to see the continuity check catch an attack (face rec 0.96, continuity 0.09) | <http://localhost:8000/app/?replay=0920-003257_inject-attack_ad81dc7a748d10ca> |
| Someone asks about a screen or replay attack (no light response, face rec 0.93) | <http://localhost:8000/app/?replay=0920-002201_screen-attack_d6dbd3036e048b07> |
| Someone asks to see the lag check fire on its own (delayed by 197 ms) | <http://localhost:8000/app/?replay=0919-163315_synth-attack_199af1053ae4978c> |

All seven were verified responding at 02:40 today. The last one is a synthetic capture with no
selfie image, so its card shows a placeholder face. Say "that one is synthetic, we injected a known
delay to test the lag check" if you use it.

### The ladder, step by step

**The genuine run comes back "lean in closer" or "the reflection did not line up".**
Say the honest line first: "It fails closed. It will not guess." Then retry once, closer and with
the table light off. If the second attempt fails, switch to the phone. If the phone is out, open
the genuine replay URL and say "here is one from earlier tonight". Do not attempt it a third time.

**The browser will not open the camera.**
Check no other tab or app holds it. Check `live.py` is not running (section 0). Check System
Settings > Privacy & Security > Camera for Chrome. If it is still dead, do the genuine run on the
phone, and the attack run stays on the laptop since `?inject` needs no camera.

**The attack rig will not start, or produces a face with no swap.**
Skip it. Go to the attack replay URL on the bank page. You lose the live face-swap moment, so
compensate by describing it in one sentence: "the rig runs at thirty frames a second off one photo,
and here is what it produced twenty minutes ago". Then point at the 0.98.

**The swap looks bad, blurry, or obviously not the victim.**
Do not apologise. It does not matter and it makes a better point: "it does not have to look good to
a human. Face recognition scored this 0.98."

**The phone cannot reach the server.**
Personal Hotspot on the phone, Mac connected over USB, server address
`http://172.20.10.2:8000` in the app's Settings, accept the local network prompt. Venue Wi-Fi
usually blocks phone to laptop traffic. If it still fails after 60 seconds, abandon the phone for
that judge and do everything on the laptop. Do not debug networking with a judge standing there.

**The server is dead and will not restart.**
Open `~/Movies/facecheck-backup.mov` in QuickTime and narrate over it. Then talk through DECK.md from
the laptop. You still have the whole technical story and the numbers.

**Everything is dead including the laptop.**
DECK.md slide 1 and slide 7 from a phone screen, spoken. The story is: the attack is free and
fast, the defence is optics, thirteen out of thirteen, face recognition 0.88 to 0.98.

---

## 6. Things a judge will notice on screen, and the one-line answer

Have these ready. They are all real and all fine, but they look odd if you are not expecting them.

**A "Heartbeat" tile on the genuine replays.**
Every genuine capture saved before 22:30 shows a Heartbeat tile at around 52 bpm. We pulled that
signal from the pipeline before the demo. Say: "that was an rPPG pulse estimate. Two decibels of
signal is too weak to put in front of a verdict, so we removed it. Live runs do not show it."

**A green "Vibration" tile on a rejected attack** (the `screen-attack` replay).
The phone really was moving, because someone was holding it at a laptop screen. Say: "vibration is
informational only. We built it, we have not tuned it on real captures, so it never contributes to
a verdict. That tile is honest, not broken."

**Red rows in the "Genuine checks" section of the attack log.**
Nine of eighteen are green. Two of the red ones are deliberate negative controls that were supposed
to fail, two are early runs pointed at a screen, and the remaining five are people who did not lean
in close enough. See FAQ.md, question 5. Do not get caught out by this; a sharp judge will scroll
down and ask.

**Processing time between 3 and 11 seconds.**
Say: "six seconds typical, on a laptop CPU, no GPU."

---

## 7. Teardown

Nothing to tear down. Leave the server and the rig running until you leave the room. Do not delete
`server/data/captures/`, it is the evidence behind every number you quoted.
