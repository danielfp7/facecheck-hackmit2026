# Hard questions, honest answers

Read this once before the expo. In the two-minute question window you will get three or four of
these. The rule: answer the question that was asked, give the number, and say the word "untested"
when it is true. Do not fill silence with speculation.

Numbers here match the attack log at 02:12 today: 13 attacks, 13 caught, 11 fooled face
recognition. By 02:40 it read 14 / 14 / 11, being 13 live face swaps plus 1 synthetic capture with
an injected 260 ms delay. Re-check the page before you present and use its number. The ratio is the
claim: every attack has been rejected.

---

## Is this new? Liveness detection already exists.

Existing liveness falls into three families. Passive detectors classify artefacts in the image,
which means they are trained against yesterday's generator and degrade against tomorrow's. Active
challenges ask you to blink, turn your head or smile, which a real-time face swap performs
perfectly because it is driven by a real person doing exactly that. Specialised hardware, like
Face ID's dot projector, works, and does not exist on a laptop webcam.

What we do is different in kind: we introduce a light source we control, and we measure a physical
property of the eye in front of it. There is no trained liveness or deepfake classifier anywhere in
this project. A face swap is not failing our checks because it looks synthetic. It is failing
because it is not a 7.8 millimetre convex mirror sitting 20 centimetres from our screen.

The corneal-reflection idea is not ours: reading a screen out of an eye is known in the literature.
What we built is a working version of it that runs on an ordinary phone and an ordinary webcam,
with the distance solved by using the iris as a ruler, wired end to end into an authentication
flow, and measured against live attacks.

## Why not just train a deepfake detector?

Because we would be shipping a model that is one generator behind, forever. We would also have to
explain a verdict by saying "the model said so". Every one of our rejections names a physical fact:
the reflection was five times too large for a cornea, or the face reacted 197 milliseconds late, or
the face in the eye check is not the person who took the selfie. That is auditable. A bank can put
it in a log.

## Could an attacker just render the corneal reflection too?

That is the right question and the honest answer is: we have not tested it, because we did not
build that attacker.

Here is what such an attacker has to do. Render a reflection of the correct shape, in the correct
position, in the correct colour, inside a correctly sized iris, at the correct sub-millimetre scale
for the distance we independently measure from the iris, for a sequence of shapes and positions the
server chooses at random and the attacker only learns at run time, and get all of it back to the
camera inside a 100 millisecond budget on top of a swap that already costs 120 to 200 milliseconds.
Our belief is that this is expensive. We have not proved it, and we will not claim we have.

What we can say is that the free, widely used attack tool that fooled face recognition at 0.98 does
none of it.

## Your lag check did not catch most of these attacks. Why keep it?

Correct, and we would rather say it than have you find it. Across our injected attacks the swap
added 120 to 200 milliseconds, which sits under the browser's limit of 206. Timing alone fired in
one attack. The corneal check caught eight of them, and the rest split between the light-response
check, which caught the attacks shown on a screen, and continuity, which caught two.

That is the argument for having three independent checks rather than one. We measured the attacker
before we tuned the defence, we found out that timing alone was not enough, and the corneal
geometry check exists because of that measurement. On the phone the picture is different: the
genuine baseline is 22.4 milliseconds, so the limit is 122, and every injected attack we measured
would have been caught on timing there.

## Why are half the genuine checks in your log red?

Eighteen genuine captures, nine verified. Scroll it with me.

Two of the red ones are negative controls that were supposed to be red: a selfie and an eye check
from two different people, which continuity caught at 0.02, and a selfie of someone who is not the
enrolled user, which face match caught at 0.00. Those failing is the system working.

Two more are early runs where the phone was pointed at a screen while we were calibrating.

The remaining five are honest misses, and all five say the same thing: "lean in closer" or "the
reflection did not line up". The corneal reflection is about two millimetres wide and you have to
be within about 20 centimetres for a webcam to resolve it. People stop roughly 30 percent further
away than you ask them to. So the system says it cannot tell, rather than guessing. It fails
closed. Every one of those is a retry away from passing, and once the web client was finished we
had three genuine web runs pass in a row.

## What is your false accept rate? Your false reject rate?

We do not have one and we are not going to invent one. Our thresholds come from a small number of
captures from a handful of people, all of us, on two device types. That is enough to build and tune
against. It is not enough to quote a rate. Anyone who quotes you a FAR on a weekend project's
sample size is telling you a number they made up.

What we have is: 13 attacks, 13 rejected, with the failing check named in each case, and every
capture kept on disk so any of it can be re-scored.

## How many people have you tested on?

A handful, all of us, on an iPhone 14 Pro and Mac webcams. That is the single biggest gap. The
things we most want more data on are darker irises, where finding a bright blob on a dark
background is easier but the iris edge is harder to fit, and glasses, which worked in our captures
but add a second reflective surface.

## Does it work with glasses? Contact lenses? Dark eyes?

Glasses: yes in our captures, and the geometry gate is what saves us. A lens reflects the screen
too, but at the wrong size and outside the iris, so it does not pass as a cornea. Contact lenses:
untested, and a soft lens sits on the cornea and follows its curvature, so we expect little change.
Dark irises: the reflection is actually easier to find against a dark iris; fitting the iris
boundary is the harder half. Tested on a small number of people, which is not enough.

## What about someone who is blind, or has one eye, or cannot hold a phone steady?

One eye is fine, the check uses one eye. Someone who cannot see the ring cannot aim the camera,
which is a real accessibility failure and we have not solved it. The honest answer is that a
liveness factor that depends on aiming your eye needs an alternative path, and we have not built
one. It fails closed, so nobody is wrongly approved; they are just blocked, which is its own
problem.

## The screen flashes. Is that safe?

We took it seriously and constrained the protocol rather than testing it afterwards. Every state
holds for at least 0.34 seconds, which keeps the sequence under two flashes per second, below the
WCAG 2.3.1 limit of three. The red is an orange-red, not a saturated red, which keeps it under the
red-flash rule. A photosensitivity warning is shown before it starts, the user has to press
Continue themselves, and any tap or Esc stops it immediately.

## Where do the video frames go? What about privacy?

Everything runs on our own server. Nothing leaves it and nothing goes to a third party. For the
demo we keep every capture on disk, which is exactly how we tuned the thresholds and how the attack
log works. In a real deployment you would keep the verdict and the evidence summary, not the video,
and you would set a retention window. We are not going to pretend we did that this weekend: right
now the frames are on the laptop.

The enrolled representation is an ArcFace embedding plus the enrolment photo, per user, in
`server/data/users/`.

## Could I just replay a recording of a genuine check?

No. The server generates the flash sequence, the shapes, the colours, the positions and the haptic
timings randomly per request, and a challenge is single use with a 90 second lifetime. A recording
made before the challenge existed cannot contain the right sequence in the eye, and the corneal
check scores position and colour against the exact sequence that was sent. That is why the
challenge is server-owned rather than client-generated.

## Would this have stopped the Arup attack? That was a video call, not a login.

Not by itself, and this is worth being precise about. InHuman is an authentication factor, not a
Zoom plugin. Where it belongs in that story is one step later: on the payment approval. That is
exactly what the demo shows, a wire above a policy limit that will not release until a live person
proves they are at the camera. The deepfaked CFO can be as convincing as it likes on the call; the
money does not move until someone passes a check that a deepfake cannot pass.

Putting the same check inside a video call is possible and we have not built it.

## Can an attacker feed fake frames to the iPhone?

Not without a jailbreak, which is why our injection attacks run against the browser, where a
virtual camera is a normal piece of software anyone can install. The phone attacks in our log are
presentation attacks: the phone is pointed at a laptop screen playing the swap. That is the real
threat model on each platform, and it is why the two platforms have different baselines and
different dominant failure modes.

## Does it work on Android? Over the internet? At scale?

Android: not built, and nothing in the approach is iOS-specific except the code. The web client
already runs on any browser with a 1080p webcam, which covers most Android phones through Chrome.

Over the internet: the server binds on the network and the web client works anywhere, but browsers
require HTTPS for camera access from a non-localhost origin, so a real deployment needs a
certificate. We tunnel it for testing.

At scale: a verdict costs about 6 seconds of CPU with no GPU, dominated by face recognition and the
corneal search. It is a batch of CPU work per authentication, not a persistent connection. Nothing
about it looks expensive to run.

## Why is there a green Vibration tile on an attack you rejected?

Because the phone genuinely was moving. Someone was holding it up to a laptop screen. Vibration is
built, it passes its unit tests on simulated signals, and it is not tuned on real captures, so it
is displayed and never counted toward a verdict. We left it visible and labelled rather than hiding
it. If we had counted it, that attack would still have been rejected, on light response.

## What is the Heartbeat tile in the saved results?

An rPPG pulse estimate we built and then removed. It read about 52 bpm with roughly 2 decibels of
signal, which is too weak to put in front of a verdict, so it is no longer in the pipeline. Saved
captures from before we removed it still show the tile because the tiles are stored with the
result. Live runs do not show it.

## Why is the face-recognition pass mark 0.35?

It is the threshold we set in `server/verdict.py`, in the usual range for ArcFace cosine
similarity. Our own calibration: strangers scored -0.03 and 0.00 against the enrolled face,
genuine users who passed scored 0.85 to 0.96, and the face swaps scored 0.88 to 0.98. The swaps
score like the real person because that is exactly what the swap model is optimised to do.

## Leaning in 20 centimetres from a screen is a bad experience.

It is not a great one, and we would not ask for it on every login. This is a step-up factor for the
moments that matter: a large wire, a new payee, a privileged account recovery. Ten seconds and an
awkward lean is cheap against twenty five million dollars. On the phone the same check needs about
10 centimetres, which is close to how people already hold a phone.

The measurement that drove the interface: we ask for a distance and people land about 30 percent
further away, so the ring is now sized for the distance we actually need rather than the one we
would like.

## Could an attacker use a real accomplice, or a 3D mask?

A live accomplice with their own face fails the face match, which is the check that already exists
everywhere and that we still run. A high-quality 3D mask of the enrolled person is a genuinely
different attack: it is a real object with real optics in front of our screen, so parts of our
approach would have to be argued rather than demonstrated. Untested. We attacked the threat that
costs an attacker one photograph and a free repository, because that is the one that took twenty
five million dollars off Arup.

Coercion, where the real enrolled person is standing there and is being forced, is out of scope for
any liveness check.

## What if the attacker reads your code? Everything here is open.

Nothing in the design depends on the attacker not knowing how it works. The secret is the
per-request random challenge, not the method. Knowing that we check for a cornea-sized reflection
of a random shape at a measured distance does not make the reflection easier to render.

## What did you actually write, and what came from a library?

We wrote all three checks. The light-response and lag estimator, the entire corneal pipeline from
blob localisation through the iris fit to the geometry gate, the hand-aligned partial-face
continuity check, the frame-by-frame transit check, the verdict fusion, the server, the iPhone app,
the web client including its timestamped frame container, and the attack harness.

From libraries: face recognition and detection (InsightFace buffalo_l), the ONNX runtime,
MediaPipe's FaceLandmarker for in-browser iris tracking, FastAPI and uvicorn, numpy, scipy and
OpenCV, and the face-swap model we attacked ourselves with. Full list in SUBMISSION.md. There is no
pretrained liveness or deepfake model in this project, because that is the thing we are arguing
against.

## What would you do next, with a week?

In order. First, build the attacker that renders a corneal reflection and find out what it costs,
because that is the only question that changes our confidence. Second, collect genuine captures
from thirty or forty people across skin tones, eye colours, glasses and devices, then re-tune the
thresholds on real distributions instead of a handful. Third, get someone outside the team to try
to break it. Fourth, tune vibration on real captures so it earns a place in the verdict.

## Who buys this?

Whoever currently loses money to a convincing face: banks on payment approval and account recovery,
and the identity-verification vendors who sit between them and the customer. It is a factor in an
existing flow, not a product someone has to adopt wholesale, which is why the demo is a bank
approval page and not an app of ours.

## What is the one thing you would change about the project?

We tuned the thresholds before we had run a real attack. It worked out, but the order was wrong.
The attack rig should have existed on day one, because the day it did exist it immediately told us
the timing check was not enough on the browser, which is the most useful thing we learned all
weekend.
