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

The app was made in two parts. A Python server does the computations: it generates a random sequence of colored shapes (triangles, squares, and circles in red, green, blue), then checks the recorded video against the sequence by measuring how fast the skin colors mirrors the screen's light, finding the screen's reflection in the cornea and fitting a circle to the iris (the average diameter of the human iris is 12mm), and running face recognition to confirm one person throughout. A web app and a native iPhone app do the capturing: both flash the screen at specific intervals with the camera, record timestamps for each frame and track eye positions to automatically find and start FaceChecking.

We utilized Python and OpenCV for the video analysis mechanism, and React/Swift to implement the web and iOS apps respectively, with the assistance of Claude Code.
 
## Team
 
| Member | Contributions |
|--------|---------------|
| Manu | Server, corneal reflection detection, iris fitting |
| Josh | Camera sync, frame timestamps, pitch and design |
| Daniel | Web app, eye tracking, testing on different faces |
| Allison | Face recognition check, testing on different lighting, pitch and design |
 
## Challenges We Ran Into
 
Some challenges we encountered while working on FaceCheck were making sure that FaceCheck worked well in different lighting condition or different face types, as well as trying to take account of additional factors like continuity of facial curve and face-matching with the screenshot provided to further increase the reliability of FaceCheck.
## Accomplishments We're Proud Of
 
This was our first hackathon and first time working together. We are proud to have landed on a great idea and accomplished more than expected, and the experience of creating something functioning from scratch together was something that everyone found rewarding.
 
## What We Learned
Some important lessons we learned, in addition to learning how to rapidly prototype an idea into code, was that variations in real-world scenarios were the most frequent causes of error, requiring constant attention into how we could compensate for such variations in our solution. Another important lesson was that given time and resource constraints, we needed to identify the key functionalities of our idea and focus on developing them rapidly.
## What's Next
 
Next steps for FaceCheck in the near future would involve testing our mechanism across different devices and lighting conditions, as well as working to establish a retention and deletion policy for the face scans used to verify identities in the process.
