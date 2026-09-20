# FaceCheck
 
FaceCheck is a fast, reliable, and convenient solution for human verification utilizing computer vision and corneal reflection analysis.

<p align="center">
  <img src="facecheck-demo.png" alt="FaceCheck verifying a user by reading colored shapes flashed on screen back from the reflection in their eye" width="600">
</p>
 
## Inspiration
 
Deepfakes, catfishing, and digital impersonation indicate that a new system stronger than ReCAPTCHA is needed to verify one's identity in multi-factor authentication (MFA). Thus, we introduce our Human-factor Authentication (HFA) model: FaceCheck.
 
## What It Does
 
FaceCheck uses computer vision to verify identities against deepfake-generated impersonations by analysing the corneal reflections of faces, as well as changes in the continuity of facial outlines, exploiting current deepfake models' inability to accurately render reflections of images reflected in the eye. Images of squares, triangles, etc. are randomly generated and displayed, and then read back in the reflection of the user's eye. In this way, we are able to verify a user's identity using basic physical principles of light reflection.
 
FaceCheck can perform its analysis in under five seconds, from both mobile and laptop devices, requiring only a camera to run.
 
## How We Built It
 
The app was made in two parts.
 
**Server (Python)** does the computations:
- Generates a random sequence of colored shapes (triangles, squares, and circles in red, green, blue)
- Checks the recorded video against the sequence by measuring how fast the skin follows the screen's light
- Finds the screen's reflection in the cornea and fits a circle to the iris (the average diameter of the human iris is 12mm, so it doubles as a ruler for distance)
- Runs face recognition to confirm one person throughout
**Clients (web app + native iPhone app)** do the capturing:
- Flash the screen at specific intervals synchronized with the camera
- Record timestamps for each frame
- Track eye positions to automatically find the user and start FaceChecking
### Stack
 
| Component | Technology |
|-----------|------------|
| Server | Python (OpenCV, [face-recognition library or model name]) |
| Web app | [React/plain JS] |
| iOS app | Swift |
 
## Team
 
| Member | Contributions |
|--------|---------------|
| Manu | Server, corneal reflection detection, iris fitting |
| Josh | Camera sync, frame timestamps, pitch and design |
| Daniel | Web app, eye tracking, testing on different faces |
| Allison | Face recognition check, testing on different lighting, pitch and design |
 
## Challenges We Ran Into
 
- Accounting for the wide variation in facial features, eye shapes, glasses, and skin tones, all of which change how reflections and brightness respond.
- Lighting: bright rooms and windows compete with the screen's reflection, so we had to tune for signal-to-noise rather than assume a dark room.
- Synchronizing screen flashes with camera frames precisely enough to trust the timing, especially across two different platforms.
- Ethical and cybersecurity considerations when generating deepfakes to test against, so we limited ourselves to our own consenting faces and never stored generated media.
- Testing across a full breadth of people and situations within a weekend.
## Accomplishments We're Proud Of
 
This was our first hackathon and first time working together. We are proud to have landed on a great idea and accomplished more than expected, and the experience of creating something functioning from scratch together was something that everyone found rewarding.
 
## What We Learned
 
- The strongest anti-deepfake signals aren't in the face. They're in how the face interacts with the world: light, reflection, and timing.
- Real-world variance (lighting, hardware, glasses) is a bigger obstacle than the algorithm itself. Robustness is the product.
- Precise hardware timing is hard, and camera frame rates are not as reliable as documentation implies.
- How to scope: we cut features aggressively to ship one thing that works rather than three that almost do.
- Biometric products live under real legal constraints (BIPA, GDPR, EU AI Act), and privacy-by-design, such as storing embeddings rather than images, has to start at the architecture stage.
## What's Next
 
Our next steps for FaceCheck are to test it against a larger set of conditions and devices, and obtain precise statistics regarding false rejections and acceptances against deepfake models.
 
- **Accuracy:** Train on a larger and more diverse set of faces, lighting conditions, and devices, and benchmark false-accept and false-reject rates against a held-out set of modern deepfake generators.
- **Integration:** Expand FaceCheck into an API with better documentation and functionality to facilitate using FaceCheck in apps and logins.
- **Privacy and compliance:** Publish a retention and deletion policy, store only embeddings, and work toward BIPA and GDPR readiness before any real deployment.
