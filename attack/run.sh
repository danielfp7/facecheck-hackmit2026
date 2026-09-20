#!/bin/zsh
# Launch Deep-Live-Cam's live window. In the window: "Select a face" -> the victim's photo, then "Live".
#
#   attack/run.sh        sharper face, ~12 fps  (swap + GPEN-256 enhancer)   <- default
#   attack/run.sh fast   smooth ~35 fps, softer face (swap only)
#
# Measured on this Mac. Either way the swapped face scores ~0.9 against the victim in face
# recognition (pass mark 0.35), so both are equally strong attacks; the enhancer is for looks.
# Run from the Terminal app so macOS asks Terminal for the camera.
cd "$(dirname "$0")/Deep-Live-Cam"
export PATH="$PWD/.venv/bin:$PATH"
procs=(face_swapper face_enhancer_gpen256)
if [[ "${1:-}" == "fast" ]]; then procs=(face_swapper); shift; fi
exec .venv/bin/python run.py --execution-provider coreml --live-mirror --live-resizable --frame-processor $procs "$@"
