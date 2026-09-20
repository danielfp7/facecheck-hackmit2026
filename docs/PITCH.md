# FaceCheck: the pitch

Three versions: 10 seconds, 60 seconds, and the full 4 minutes with the demo inside it.
Then who says what.

**Before you speak, check the number.** Open <http://localhost:8000/app/attacks.html>. It counts
live off the saved captures, and it is moving: **13 / 13 / 11** at 02:12, **14 / 14 / 11** at 02:40,
because someone recorded another attack in between. Read the counter, then say the number on the
screen. The claim that never changes: **every attack we have run has been rejected.** The 0.88 to
0.98 range and the 0.35 pass mark are stable.

**Exactly what the counter counts.** At 02:40 the 14 were: **13 live face swaps** (Deep-Live-Cam
with inswapper_128), plus **1 synthetic capture** where we injected a known 260 ms delay to test the
timing check on its own. Of the 14, **11** put a swapped face in front of face recognition and every
one of those scored 0.88 to 0.98. In the other three no face reached the recogniser. So both of
these are true, say whichever fits:

- "Thirteen live face-swap attacks. Thirteen rejected."
- "Fourteen attacks in the log, fourteen rejected. Thirteen of them were live face swaps."

Do not say "thirteen" while the page shows fourteen without explaining the difference. A judge can
see the synthetic card, it is labelled "Synthetic attack", and being the one to point at it first is
worth more than the extra digit.

This document says "thirteen" throughout. Reconcile it with the page before you present, and before
the 11:00 submission.

**The one sentence we want a judge repeating at the next table:**
"Their thing flashes shapes at your eye and reads the reflection off your cornea, and it caught
thirteen out of thirteen live deepfakes that face recognition scored at 0.98."

Names below are placeholders. Replace `[A]` `[B]` `[C]` `[D]` with real names. `[A]` is Daniel
unless you decide otherwise.

---

## 10 seconds

> Face recognition cannot tell a live person from a real-time face swap. We can. We flash coloured
> shapes at your eye and read their reflection out of your cornea. Thirteen live deepfake attacks,
> thirteen rejected. Face recognition scored those same fakes up to 0.98 against a 0.35 pass mark.

Use this when a judge walks up mid-run, or when someone asks "what is it?" in a corridor.

---

## 60 seconds

> In 2024 a finance worker at the engineering firm Arup joined a video call with his CFO and
> several colleagues. Every person on that call was a deepfake. He sent about twenty five million
> dollars to accounts in Hong Kong. Nobody stole a password. The face was the credential, and the
> face was fake.
>
> FaceCheck is a second factor that proves a live human is at the camera. It runs as an iPhone app
> and as a web app on a laptop webcam.
>
> It works on physics, not on artefacts. The screen is a light source. Skin lit by a red flash goes
> red immediately, with no delay beyond the display and the camera. We measured that delay: 22
> milliseconds on the phone, 105 on the laptop. A pipeline that has to see the flash, re-render a
> face and inject it arrives late. Then the harder check: your cornea is a convex mirror, about 7.8
> millimetres of radius. It shows a tiny copy of whatever is in front of it. We find our shapes in
> that reflection, fit the iris around it, and check the reflection is in the right place, the right
> colour, inside the iris, and cornea sized. A flat screen reflects our flashes five times too
> large. A generated face reflects nothing.
>
> We ran thirteen live face-swap attacks at it with a free tool off GitHub. It rejected all
> thirteen. In eleven of them face recognition scored the fake between 0.88 and 0.98, against a
> 0.35 pass mark. Face recognition alone would have approved every one.

---

## Full pitch, about 4 minutes 30

Budget: 6 minutes presenting. This script is 4:30. The remaining 90 seconds are for the judge's
own hands. If you are running late, cut section 4 to its first and last sentence.

Everything in `[ ]` is an action, not a line.

### 1. Hook (25 s) - [A]

> In 2024 a finance worker at Arup joined a video call with his chief financial officer and several
> colleagues. Every face on that call was a deepfake. He made fifteen transfers, about twenty five
> million dollars, to accounts in Hong Kong. Nobody hacked a password. The face was the credential,
> and the face was fake.
>
> This is FaceCheck. It proves a live human is at the camera. Let me show you, then I will tell you
> how it works.

Do not explain the architecture yet. Do not say the word "pipeline".

### 2. The genuine run, live (60 s) - [A] drives

[Laptop showing the Northwind banking page. Twenty five point six million dollars, new beneficiary,
"approved by the CFO on this morning's video call".]

> Corporate banking. Twenty five point six million out, new beneficiary, urgent and confidential.
> The memo says the CFO approved it on a video call. This wire needs a live-person check before it
> releases.

[Press **Verify on this computer**. A tab opens.]

> Selfie at arm's length. Now I lean in until my eye fills the ring.

[Lean in to about 20 cm. Screen goes full brightness and flashes coloured shapes for about
5 seconds. Result comes back in roughly 6 seconds. **Read the numbers off the tiles, do not recite
the ones below.** On the capture these were taken from they were lag 101 ms, reflection 1.9 mm,
distance 205 mm.]

> Verified, and the wire released. Lag 101 milliseconds. The reflection of those shapes in my
> cornea was 1.9 millimetres across, and my eye was 205 millimetres from the camera. The check took
> about ten seconds of my time and six seconds of the server's.

### 3. The attack, live (70 s) - [B] drives

> Same page. Same account. Same check. This time the camera is a live face swap.

[Show the attack window for two seconds: real face, then swapped face.]

> Deep-Live-Cam with the inswapper_128 model. It is free, it is on GitHub, it runs at about thirty
> frames a second on this laptop. That is [B]'s head wearing [A]'s face, live, right now. A real
> attacker would push this into the browser through a virtual camera. Ours feeds the page
> directly, same frames, same delay.

[Run the check in `?inject` mode: selfie, lean in, flashes.]

> Blocked.

[Point at the comparison panel on the bank page. **Read the similarity off the panel.** In our
attacks it lands between 0.88 and 0.98. Anything above 0.35 makes the point.]

> This is the part that matters. On the left is what ordinary face recognition concluded: 0.98
> similarity against a 0.35 pass mark. Face recognition would have released the wire. On the right
> is FaceCheck: no cornea-sized reflection of our shapes inside an iris. The deepfake has an eye
> painted on it. That eye is not a mirror.

### 4. How it works (65 s) - [C]

> Two physics checks and one continuity check.
>
> First, light and lag. The screen is a light source. Skin lit by a red flash goes red instantly,
> and the only real delay is the display and the camera. We measured that per device: 22.4
> milliseconds on the iPhone, 105.5 on this laptop's webcam. Anything that has to see the flash,
> re-render a face and inject it arrives late. Across our attacks the injected frames landed
> between 120 and 598 milliseconds.
>
> Second, the cornea. Your cornea is a convex mirror, radius about 7.8 millimetres, so it shows a
> minified copy of the screen. We find our shape in that reflection and fit the iris around it.
> Irises are 11.7 millimetres across in everyone, so the iris doubles as a ruler and gives us the
> true distance to the eye. Then four tests: right position, right colour, inside the iris, and
> cornea sized. Sizing is what kills a screen attack. Hold a phone up to a laptop playing a
> deepfake and the reflection comes back about five times too large, because a flat screen is not a
> 7.8 millimetre mirror.

### 5. Continuity, results, and what is not done (50 s) - [D]

> The obvious way around this is to deepfake the selfie and then show your own real eye. So the two
> halves have to be one person in one unbroken sitting. We run face recognition on the eye-check
> frames themselves, aligned by hand off the iris, and we match the camera view frame by frame all
> the way in. Same person scores 0.36 to 0.67. Two different people score under 0.12. Two of our
> attacks died exactly there.

[Open <http://localhost:8000/app/attacks.html>.]

> Thirteen live attacks. Thirteen rejected. Eleven of them fooled face recognition outright, 0.88
> to 0.98. The corneal check caught eight of them, the rest split between light response,
> continuity and timing. Every card is a real saved capture, click one and you get the full result.
>
> What is not done, honestly: our thresholds are tuned on a small number of genuine captures from a
> handful of people, nobody outside this team has evaluated it, on most browsers we cannot lock the
> camera's exposure, and we have not yet faced an attacker who tries to synthesise the corneal
> reflection geometry itself. That last one is the real frontier and it is what we would build
> next.

### 6. Hand it over (10 s) - [A]

> Want to try it? You can enrol your face and run a check in about forty seconds.

[Hand over the laptop. See DEMO_SCRIPT.md, "The judge's hands".]

---

## Who says what

Learning and collaboration is 10 percent of the score, and judges notice when one person talks for
six minutes. Four speakers, four clean handoffs. Each person owns something they actually built and
can be questioned on.

Practise the handoffs twice. The handoff is the only part that goes wrong.

### [A] (Daniel): host, product, genuine demo

- Speaks: hook, genuine run, handover to the judge, close.
- Owns: the iPhone app, the challenge protocol, the relying-party flow.
- If asked what you learned: "How much of this problem is not machine learning. Locking exposure,
  getting an honest timestamp on a frame, keeping the whole thing under two flashes per second so
  it is safe for photosensitive people. The signal was the easy part."
- Backup role: can run any other section.

### [B]: the attack

- Speaks: the attack demo.
- Owns: the attack rig. Deep-Live-Cam, inswapper_128, the frame server that feeds the browser, the
  lag measurements.
- If asked what you learned: "How cheap the attack is. One photo, one free repo, thirty frames a
  second on a laptop, and face recognition scores it 0.98. We built the attacker first, and that is
  why the defence is aimed at a real thing."
- Must be able to answer: what does a virtual camera do, why is injection harder to defend than a
  screen, what is the swap's real latency.

### [C]: the signals

- Speaks: how it works, section 4.
- Owns: `server/signals/lag.py` and `server/signals/cornea.py`. The light-response fit, finding the
  reflection, fitting the iris, the geometry gate.
- If asked what you learned: "Optics. A cornea is a 7.8 millimetre convex mirror and an iris is
  11.7 millimetres in everyone, which means one eye gives you both a mirror and a ruler. We get
  distance for free out of the same fit."
- Must be able to answer: why chromaticity when exposure is unlocked, what the lag fit actually
  optimises, why 18 pixels is the cutoff for reading the shape outline.

### [D]: continuity, results, limits

- Speaks: section 5.
- Owns: `server/signals/continuity.py` and `server/signals/transit.py`, the verdict fusion, the
  results and attack-log pages.
- If asked what you learned: "That our first idea was wrong. Comparing the eye region directly
  does not work, strangers' eyes scored higher than your own. Running face recognition on the
  liveness frames does work, if you align the partial face by hand off the iris. We only found
  that by measuring both."
- Must be able to answer: the false-reject question, the sample-size question, why half the genuine
  rows in the attack log are red. See FAQ.md, those three come up most.

### If someone is missing

Collapse to two speakers: [A] does 1, 2, 6 and [C] does 3, 4, 5. Do not try to cover four people's
lines alone. Say "two of us are at the table, the other two are asleep" and carry on.

---

## Lines to never say

- "AI-powered". The whole point is that this is optics and timing, not a classifier.
- "100 percent accurate". Say "thirteen out of thirteen" and let the judge do the arithmetic.
- "It can't be beaten". Say "here is what we have not tested yet" and name it.
- Anything about the Arup case beyond: 2024, a finance worker, a video call with a deepfaked CFO
  and colleagues, about twenty five million dollars, Hong Kong. Those are verified. Do not add
  detail you cannot source.
