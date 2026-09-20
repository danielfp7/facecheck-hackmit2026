#!/usr/bin/env python3
"""Minimal ffprobe stand-in for Deep-Live-Cam's file mode.

imageio-ffmpeg bundles ffmpeg but not ffprobe, and there is no Homebrew on the dev Mac.
Deep-Live-Cam asks ffprobe exactly three things; this answers them with OpenCV.
"""
import sys

import cv2

args = sys.argv[1:]
entries = args[args.index("-show_entries") + 1] if "-show_entries" in args else ""
cap = cv2.VideoCapture(args[-1])
if not cap.isOpened():
    sys.exit(f"ffprobe shim: cannot open {args[-1]}")
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
if "r_frame_rate" in entries:
    print(f"{round(fps * 1000)}/1000")
elif "width,height" in entries:
    print(f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
elif "duration" in entries:
    print(cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps)
else:
    sys.exit(f"ffprobe shim: unsupported query {entries!r}")
