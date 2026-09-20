#!/bin/zsh
# Launch Deep-Live-Cam's live window. In the window: "Select a face" -> the victim's photo, then "Live".
cd "$(dirname "$0")/Deep-Live-Cam"
PATH="$PWD/.venv/bin:$PATH" exec .venv/bin/python run.py --execution-provider coreml --live-mirror --live-resizable "$@"
