"""Identity: ArcFace embedding of the arm's-length selfie vs the enrolled one."""
from __future__ import annotations

import functools

import cv2
import numpy as np


@functools.lru_cache(maxsize=1)
def _app():
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"],
                       allowed_modules=["detection", "recognition"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    return app


def embed(jpeg_bytes: bytes) -> np.ndarray | None:
    """Unit-length embedding of the largest face, or None if no face is found."""
    img = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    # Phone selfies are large; detection works on a 640 px canvas anyway.
    scale = 1280 / max(img.shape[:2])
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    faces = _app().get(img)
    if not faces:
        return None
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return np.asarray(face.normed_embedding, dtype=np.float32)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))
