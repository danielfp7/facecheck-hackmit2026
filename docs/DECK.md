# Deck

Nine slides. At a table you will mostly not use them: the demo is the pitch. The deck exists for
three jobs.

1. The fallback when the demo cannot run. Slides 1, 3 and 7 carry the whole argument on their own.
2. The source of the screenshots and the wording for the Plume submission.
3. Something to point at while a teammate resets the laptop between judges.

Rules for building it: one idea per slide, numbers big enough to read from a metre away over
someone's shoulder, no bullet lists longer than four lines, no logos, no stock photography, no
gradients behind text. Screenshots come from the real product, not mockups. Dark background so it
does not blind anyone at a table, and so a phone screen can show it if the laptop dies.

Every number below must match <http://localhost:8000/app/attacks.html>. That page counts live and
it is moving: 13 / 13 / 11 at 02:12, 14 / 14 / 11 at 02:40 (13 live face swaps plus 1 synthetic
capture with an injected delay). Set the numbers on slides 1, 3 and 7 from the page just before you
submit, and check them again before the expo. The ratio is the claim: every attack has been
rejected. See PITCH.md, "Exactly what the counter counts".

---

## Slide 1. Title

**On screen**
- InHuman
- Proves a live human is at the camera, not a real-time deepfake
- One line underneath, small: 13 live face-swap attacks. 13 rejected. Face recognition scored the
  same fakes 0.88 to 0.98.

**Said:** nothing. This is the slide that sits on screen while judges walk up, and it is the slide
you hold up if everything else is dead. It has to work as a poster with no narration.

---

## Slide 2. The problem

**On screen**
- 2024. A finance worker at Arup joins a video call with his CFO and colleagues.
- Every face on the call is a deepfake.
- About US$25 million leaves the company, to accounts in Hong Kong.
- One line, larger: **the face was the credential, and the face was fake.**

**Said:** PITCH.md section 1.

**Do not add:** any detail of the Arup case beyond the four facts above. They are verified. Nothing
else is.

---

## Slide 3. Face recognition is not the defence

**On screen**
- A horizontal bar: 0 to 1, with a marker at 0.35 labelled "pass mark".
- Eleven dots between 0.88 and 0.98, all of them deepfakes.
- One line: **every one of these is a live face swap. Face recognition approved all of them.**

**Said:**
> This is the check that is already deployed everywhere. Eleven of our thirteen attacks scored
> between 0.88 and 0.98 against a 0.35 pass mark. Face recognition is answering a different
> question: is this the right face. It cannot answer whether the face is here.

This is the single most important slide. If a judge only looks at one, make it this one. The
attack log page already renders this bar per attack, so screenshot it rather than redrawing it.

---

## Slide 4. Check 1: light and lag

**On screen**
- A diagram: screen flashes, skin follows, camera records.
- Three numbers, large:
  - genuine iPhone **22.4 ms**
  - genuine laptop webcam **105.5 ms**
  - injected attack **120 to 598 ms**
- Small line: limit is the device baseline plus 100 ms.

**Said:**
> The screen is a light source. Skin lit by a red flash goes red instantly. The only genuine delay
> is the display and the camera, and we calibrate it per device. A pipeline that has to see the
> flash, re-render a face and inject it arrives late.

**Have ready, because it is the honest follow-up:** this check alone did not catch most of our
injection attacks, because a well-tuned swap only adds 120 to 200 ms. That is why check 2 exists.
See FAQ.md question 4.

---

## Slide 5. Check 2: the cornea

**On screen**
- The real eye crop from a genuine capture, with the reflected shape visible. Pull it from
  <http://localhost:8000/app/?replay=0919-203905_real_383daac7abd8d978>.
- Labelled: cornea, convex mirror, radius about 7.8 mm. Iris, 11.7 mm in everyone, so it is a ruler.
- Measured on that capture: **reflection 1.9 mm wide, eye at 205 mm, expected 2.7 mm.**
- Underneath: **a flat screen reflects about 5x too large. A generated face reflects nothing.**

**Said:** PITCH.md section 4, second half.

This is the slide people remember. Make the eye crop as large as the slide allows.

---

## Slide 6. Check 3: continuity

**On screen**
- Two panels: "deepfake for the selfie" then "my own real eye for the liveness check", with an
  arrow between them and a red cross over the arrow.
- Same person **0.36 to 0.67**. Different people **at or below 0.12**. Threshold **0.25**.
- Small line: plus frame-by-frame view matching during the move, so there is no unobserved gap.

**Said:**
> Two checks that both pass are still beatable if you can run them on two different people. So the
> selfie and the eye check have to be one person in one unbroken sitting. Two of our thirteen
> attacks died here and nowhere else.

---

## Slide 7. The result

**On screen**
- **13 attacks. 13 rejected. 11 fooled face recognition.** (Read the live counter first.)
- Which check caught it: corneal reflection 8, light response 3, continuity 2, timing 1. That
  breakdown is for the 14 attacks on the page at 02:40; recount if it moves.
- A screenshot of `/app/attacks.html`.

**Said:**
> We built the attacker first. Deep-Live-Cam with inswapper_128, free on GitHub, thirty frames a
> second on this laptop, wearing a teammate's face from one photo. Thirteen attacks, three delivery
> methods: injected into the browser like a virtual camera would, shown to the phone on a laptop
> screen, and swapped into the Mac's own capture path. Thirteen rejected.

The "which check caught it" line is doing real work. It shows the three checks are independent, not
one check with three names.

---

## Slide 8. What is not done

**On screen**, in plain language, no hedging:
- Thresholds tuned on a small number of captures from a handful of people.
- No independent evaluation. Everyone who attacked it also built it.
- The web client cannot lock camera exposure on most browsers.
- Untested: an attacker who synthesises a correct corneal reflection. That is the real next attack.
- Vibration is built but untuned, so it never affects a verdict.

**Said:**
> This is where we are, not where we are pretending to be.

Judges reward this. Leave it on screen while you answer questions.

---

## Slide 9. Who built what

**On screen**, four names, one line each, naming the actual files or components.
- [A]: iPhone app, challenge protocol, relying-party flow
- [B]: attack rig, injection path, lag measurement
- [C]: light response and lag estimator, corneal pipeline, iris fit
- [D]: continuity and transit checks, verdict fusion, results and attack-log pages

Plus one line at the bottom: written with Claude Code, under our direction. Libraries disclosed in
the submission.

**Said:** nothing, unless asked. It is there so the collaboration score has something to look at,
and so that when a judge asks a specific technical question, the right person answers it.

---

## If you only have one slide

Slide 3. The bar with eleven deepfakes above the pass mark. Add the sentence "we caught all of
them" underneath it and nothing else.
