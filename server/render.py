"""Render a challenge state exactly as the phone draws it.

Geometry contract shared with ios/Sources/ChallengeViewController.swift:
  - shape is centered horizontally and spans SHAPE_SPAN of the screen width
  - vertical center at 0.25 / 0.50 / 0.75 of the height for top / middle / bottom
  - triangle is equilateral, pointing up
"""
from __future__ import annotations

import cv2
import numpy as np

from challenge import COLORS, SHAPE_SPAN, State

POSITION_Y = {"top": 0.25, "middle": 0.5, "bottom": 0.75}


def shape_mask(shape: str, position: str, w: int, h: int) -> np.ndarray:
    """Boolean (h, w) mask of the shape on a w x h screen."""
    img = np.zeros((h, w), np.uint8)
    span = SHAPE_SPAN * w
    cx, cy = w / 2, POSITION_Y[position] * h
    if shape == "circle":
        cv2.circle(img, (round(cx), round(cy)), round(span / 2), 255, -1, cv2.LINE_AA)
    elif shape == "square":
        p0 = (round(cx - span / 2), round(cy - span / 2))
        p1 = (round(cx + span / 2), round(cy + span / 2))
        cv2.rectangle(img, p0, p1, 255, -1)
    elif shape == "triangle":
        th = span * np.sqrt(3) / 2
        pts = np.array([[cx, cy - th / 2], [cx - span / 2, cy + th / 2], [cx + span / 2, cy + th / 2]])
        cv2.fillPoly(img, [np.round(pts).astype(np.int32)], 255, cv2.LINE_AA)
    else:
        raise ValueError(shape)
    return img > 127


def render_state(state: State, w: int, h: int) -> np.ndarray:
    """(h, w, 3) uint8 RGB image of the screen in this state."""
    img = np.empty((h, w, 3), np.uint8)
    img[:] = COLORS[state.background]
    if state.shape is not None:
        img[shape_mask(state.shape, state.position, w, h)] = COLORS[state.shape_color]
    return img


def render_color(name: str, w: int, h: int) -> np.ndarray:
    img = np.empty((h, w, 3), np.uint8)
    img[:] = COLORS[name]
    return img
