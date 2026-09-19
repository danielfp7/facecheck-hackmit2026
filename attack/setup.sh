#!/bin/zsh
# Sets up Deep-Live-Cam as the test attacker. Own venv: its pins (insightface 0.7.3,
# opencv 4.14, onnxruntime 1.28) conflict with the server's.
# For defensive testing on consenting teammates only.
set -euo pipefail
cd "$(dirname "$0")"

[ -d Deep-Live-Cam ] || git clone --depth 1 https://github.com/hacksider/Deep-Live-Cam.git
cd Deep-Live-Cam

[ -d .venv ] || uv venv --python 3.12
# insightface 0.7.3 is an sdist with a Cython extension; give it its build deps up front.
uv pip install --python .venv/bin/python "numpy>=2.0,<3" cython setuptools wheel
uv pip install --python .venv/bin/python --no-build-isolation insightface==0.7.3
uv pip install --python .venv/bin/python -r requirements.txt

HF=https://huggingface.co/hacksider/deep-live-cam/resolve/main
for m in inswapper_128_fp16.onnx gfpgan-1024.onnx; do
  [ -s "models/$m" ] || curl -L --fail --retry 3 -o "models/$m" "$HF/$m"
done

echo
echo "Ready. Launch the live swapper with:"
echo "  cd attack/Deep-Live-Cam && .venv/bin/python run.py --execution-provider coreml --live-mirror --live-resizable"
