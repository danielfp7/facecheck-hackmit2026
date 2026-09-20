"""Server-side challenge generator.

The server owns the random sequence so a replayed recording can never match it.
A state is what the phone shows full-screen for `duration_s`:
  shape (triangle/square/circle) x color x position, on a background color.
Default polarity is a bright shape on black; `inverse=True` gives a black shape
on a colored background (Tab 1's other reading of "black, red, green").
"""
from __future__ import annotations

import secrets
import random
from dataclasses import dataclass, asdict, field

SHAPES = ("triangle", "square", "circle")
POSITIONS = ("top", "middle", "bottom")

# Orange-red, not pure red: R/(R+G+B) = 0.68 stays under the 0.8 "saturated red"
# threshold in the WCAG 2.3.1 red-flash rule.
COLORS = {
    "black": (0, 0, 0),
    "red": (255, 80, 40),
    "green": (0, 255, 0),
}

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

    Consecutive shape states always differ in color so every transition produces
    a chroma step for the lag check, and black states are interleaved as the
    ambient baseline for the corneal check.
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
    # Every position appears about equally often, in random order. Independent draws can
    # come out 6-of-7 the same (seen on a real run), which leaves the position score
    # hanging on a single flash.
    positions = [POSITIONS[i % len(POSITIONS)] for i in range(n_shapes)]
    rng.shuffle(positions)
    for i in range(n_shapes):
        color = rng.choice([c for c in ("red", "green") if c != last_color])
        shape = rng.choice([s for s in SHAPES if s != last_shape])
        pos = positions[i]
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
