"""Server-side challenge generator.

The server owns the random sequence so a replayed recording can never match it.
A state is what the phone shows full-screen for `duration_s`:
  shape (triangle/square/circle) x color, drawn in the middle of the screen.
Default polarity is a bright shape on black; `inverse=True` gives a black shape
on a colored background (Tab 1's other reading of "black, red, green").
"""
from __future__ import annotations

import secrets
import random
from dataclasses import dataclass, asdict, field

SHAPES = ("triangle", "square", "circle")
POSITIONS = ("top", "middle", "bottom")

# Four well-separated colors carry the challenge. Orange-red, not pure red:
# R/(R+G+B) = 0.68 stays under the 0.8 "saturated red" threshold in the WCAG 2.3.1
# red-flash rule. Their chromaticities sit far apart, which is what the server scores:
#   red (.68,.21,.11)  green (0,1,0)  blue (.09,.28,.63)  white (.33,.33,.33)
COLORS = {
    "black": (0, 0, 0),
    "red": (255, 80, 40),
    "green": (0, 255, 0),
    "blue": (35, 110, 245),
    "white": (255, 255, 255),
}
# Colors a shape can be drawn in.
LIT = ("red", "green", "blue", "white")

# Seizure safety: with >= 0.34 s per state the screen makes at most ~1.5 flashes
# per second (a flash is a pair of opposing transitions), under the limit of 3.
MIN_STATE_S = 0.34

# Fraction of the screen's short side that the shape spans. Used by the phone to
# draw and by the server to estimate emitted light per state.
SHAPE_SPAN = 0.8
# Approx. fraction of screen *area* each shape covers on a ~19.5:9 portrait screen.
SHAPE_AREA = {"triangle": 0.13, "square": 0.30, "circle": 0.23}


@dataclass
class State:
    index: int
    shape: str | None  # None = plain full-screen color (used for black baseline)
    shape_color: str
    background: str
    position: str
    duration_s: float

    def emitted_rgb(self) -> tuple[float, float, float]:
        """Area-weighted mean screen color, 0..1. The expected skin response."""
        bg = COLORS[self.background]
        if self.shape is None:
            return tuple(c / 255 for c in bg)
        a = SHAPE_AREA[self.shape]
        fg = COLORS[self.shape_color]
        return tuple((a * f + (1 - a) * b) / 255 for f, b in zip(fg, bg))


@dataclass
class Challenge:
    id: str
    nonce: str
    states: list[State] = field(default_factory=list)
    settle_color: str = "green"  # brightest state; phone locks exposure on it
    settle_s: float = 0.6
    # Vibration test: haptic bursts at server-chosen offsets from the first state, so
    # the timing can't be predicted or pre-rendered.
    haptic_times_s: list[float] = field(default_factory=list)
    haptic_duration_s: float = 0.4

    def to_dict(self) -> dict:
        d = asdict(self)
        d["colors"] = COLORS
        d["shape_span"] = SHAPE_SPAN
        d["total_s"] = round(sum(s.duration_s for s in self.states), 3)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Challenge":
        keys = ("index", "shape", "shape_color", "background", "position", "duration_s")
        states = [State(**{k: s[k] for k in keys}) for s in d["states"]]
        return cls(id=d["id"], nonce=d["nonce"], states=states,
                   settle_color=d.get("settle_color", "green"), settle_s=d.get("settle_s", 0.6),
                   haptic_times_s=d.get("haptic_times_s", []),
                   haptic_duration_s=d.get("haptic_duration_s", 0.4))


def _haptic_times(rng: random.Random, total_s: float, n: int = 3, min_gap: float = 1.2) -> list[float]:
    """n random burst times inside the sequence, at least min_gap apart."""
    lo, hi = 0.4, total_s - 0.7
    for _ in range(200):
        ts = sorted(rng.uniform(lo, hi) for _ in range(n))
        if all(b - a >= min_gap for a, b in zip(ts, ts[1:])):
            return [round(t, 3) for t in ts]
    return [round(lo + (hi - lo) * (i + 0.5) / n, 3) for i in range(n)]


def generate(n_shapes: int = 7, state_s: float = 0.4, inverse: bool = False,
             seed: str | None = None, haptics: bool = True) -> Challenge:
    """Random sequence: black, shape, shape, black, shape, ... about 4-5 s total.

    Every shape is drawn in the middle of the screen. Off-centre shapes were tried and
    dropped: up close the cornea only mirrors a narrow cone, so a shape near the screen's
    edge reflects off the visible part of the eye and reads as a miss. The challenge is
    carried by colour and outline instead, which is why there are four colours rather
    than two. Consecutive shape states always differ in colour, so every transition is a
    chroma step the lag check can use, and black states are the corneal check's baseline.
    """
    state_s = max(state_s, MIN_STATE_S)
    nonce = seed or secrets.token_hex(16)
    rng = random.Random(nonce)

    states: list[State] = []

    def add(shape, color, bg, pos):
        states.append(State(len(states), shape, color, bg, pos, state_s))

    add(None, "black", "black", "middle")
    last_color = None
    last_shape = None
    # Every colour appears about equally often, in random order. Independent draws can come
    # out lopsided, which leaves the colour score hanging on a couple of transitions.
    colors = [LIT[i % len(LIT)] for i in range(n_shapes)]
    rng.shuffle(colors)
    for i in range(n_shapes):
        color = colors[i]
        if color == last_color:                       # never two of the same in a row
            swap = next((j for j in range(i + 1, n_shapes) if colors[j] != color), None)
            if swap is not None:
                colors[i], colors[swap] = colors[swap], colors[i]
                color = colors[i]
        shape = rng.choice([s for s in SHAPES if s != last_shape])
        pos = "middle"
        if inverse:
            add(shape, "black", color, pos)
        else:
            add(shape, color, "black", pos)
        last_color, last_shape = color, shape
        # Black baseline after every second shape.
        if i % 2 == 1 and i != n_shapes - 1:
            add(None, "black", "black", "middle")
            last_color = None
    add(None, "black", "black", "middle")

    total = sum(s.duration_s for s in states)
    return Challenge(id=secrets.token_hex(8), nonce=nonce, states=states,
                     haptic_times_s=_haptic_times(rng, total) if haptics else [])
