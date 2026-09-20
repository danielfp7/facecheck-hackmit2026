#!/bin/zsh
# Pre-render a high-quality deepfake clip: swap VICTIM's face onto every frame of a video
# of the attacker, then play the result fullscreen for a presentation attack.
#
#   attack/render.sh victim.jpg attacker.mov [out.mp4] [--fast]
#
# Live swapping is already smooth on this Mac (~36 fps); what offline adds is the face
# enhancer, which is too slow to run live. Cost: ~0.75 s per frame (~0.3 s with --fast,
# which skips the enhancer), so a 20 s clip takes 7-8 minutes.
# Only use faces of people who have agreed to it.
set -euo pipefail
[ $# -ge 2 ] || { echo "usage: $0 victim.jpg attacker_video [out.mp4] [--fast]"; exit 1; }
victim=${1:A}; target=${2:A}; out=${3:-deepfake.mp4}; [[ "$out" == --* ]] && out=deepfake.mp4; out=${out:A}
procs=(face_swapper face_enhancer); [[ " $* " == *" --fast "* ]] && procs=(face_swapper)
cd "$(dirname "$0")/Deep-Live-Cam"
export PATH="$PWD/.venv/bin:$PATH"
.venv/bin/python run.py -s "$victim" -t "$target" -o "$out" --execution-provider coreml --keep-fps --frame-processor $procs
echo "\nWrote $out. Play it fullscreen (QuickTime: View > Enter Full Screen, and loop it with View > Loop)."
