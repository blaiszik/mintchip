"""Text tier: glyphs, cell helpers, ASCII transliteration and ANSI colour.

A text renderer has the signature ``render(chip, o: TextOptions) -> TextOut``. It writes the
Unicode tier only, from the glyphs below; ``Chip.text(ascii=True)`` transliterates the whole
output through ``ASCII``, so renderers branch on ``o.ascii`` only when the transliteration of a
specific glyph would read badly.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "ALLOWED",
    "ASCII",
    "CROSS",
    "DOT",
    "EIGHTHS",
    "GAP",
    "HI_END",
    "HOLLOW",
    "LEVELS",
    "LO_END",
    "REF",
    "RULE",
    "SHADES",
    "TRACK",
    "Glyph",
    "Segment",
    "TextOptions",
    "TextOut",
    "Track",
    "ansi",
    "cell_counts",
    "hbar",
    "largest_remainder",
    "level",
    "plain",
    "to_ascii",
]

# --- the Unicode tier's whole alphabet (CONTRACT section 5) ---------------------------------
LEVELS = "▁▂▃▄▅▆▇█"  # eight heights, for runs of values
EIGHTHS = "▏▎▍▌▋▊▉█"  # left-aligned partial cells, for lengths
SHADES = "░▒▓█"  # four density steps, for heatmaps and stacked status bars
TRACK = "·"  # an empty cell on an axis, or a missing value in a run
RULE = "─"  # a span along an axis
REF = "│"  # a reference position on an axis
CROSS = "┼"  # a reference position inside a span
LO_END, HI_END = "├", "┤"  # the two ends of a span
DOT, HOLLOW = "●", "○"  # a point; hollow when it is not distinguishable from the reference
GAP = "▏"  # thin separator between parts of a whole
ALLOWED = frozenset(LEVELS + EIGHTHS + SHADES + "─│├┤┼●○·−→±×")

# Transliteration applied to every character of ``text(ascii=True)``.
ASCII: dict[str, str] = {
    **dict(zip(LEVELS, "_.-~=+*#", strict=True)),
    "░": ".", "▒": ":", "▓": "=",
    "▏": "|", "▎": "|", "▍": "|", "▌": "|", "▋": "#", "▊": "#", "▉": "#",
    "·": ".", "─": "-", "│": "|", "┼": "+", "├": "(", "┤": ")", "●": "*", "○": "o",
    "−": "-", "→": "->", "±": "+/-", "×": "x",
    "–": "-", "—": "-", "…": "...", "µ": "u", "μ": "u", "°": "deg", "≤": "<=", "≥": ">=",
}  # fmt: skip

_SGR = {"accent": "34", "good": "32", "bad": "31", "warn": "33", "context": "2"}

Segment = tuple[str, str | None]  # (text, role)
Glyph = str | Sequence[Segment]


@dataclass(frozen=True)
class TextOptions:
    """What a text renderer is asked for. ``domain`` is already resolved (render argument,
    then ``args["domain"]``, then ``chip.domain``). ``decimals``, when given, is the decimal
    places for the primary value (a table column passes one count to all its cells); kinds
    whose value is not a decimal number ignore it."""

    ascii: bool = False
    compact: bool = False
    domain: tuple[float, float] | None = None
    decimals: int | None = None


@dataclass(frozen=True)
class TextOut:
    """``value`` is the number part; ``glyph`` is a string or ``(text, role)`` segments, with
    role one of None, "accent", "good", "bad", "warn", "context". Empty glyph means none.
    ``decimals`` is the decimal places the primary value was printed with, for kinds that
    honour ``TextOptions.decimals`` (None for the others)."""

    value: str
    glyph: Glyph = ""
    decimals: int | None = None


def to_ascii(s: str) -> str:
    """Transliterate to pure ASCII; anything unknown becomes ``?``."""
    return "".join(ch if ch.isascii() else ASCII.get(ch, "?") for ch in s)


def _segments(glyph: Glyph) -> list[Segment]:
    return [(glyph, None)] if isinstance(glyph, str) else list(glyph)


def plain(glyph: Glyph, *, ascii: bool = False) -> str:
    """Join segments without colour."""
    s = "".join(t for t, _ in _segments(glyph))
    return to_ascii(s) if ascii else s


def ansi(glyph: Glyph, *, ascii: bool = False) -> str:
    """Join segments, wrapping each coloured role in an ANSI SGR code."""
    out = []
    for text, role in _segments(glyph):
        text = to_ascii(text) if ascii else text
        out.append(f"\x1b[{_SGR[role]}m{text}\x1b[0m" if role and text else text)
    return "".join(out)


def level(v: float, lo: float, hi: float) -> str:
    """The LEVELS block for ``v`` on ``[lo, hi]`` (clamped; check clipping yourself)."""
    t = 0.5 if hi <= lo else (v - lo) / (hi - lo)
    return LEVELS[min(7, max(0, round(t * 7)))]


def hbar(cells: float) -> str:
    """A horizontal length of ``cells`` cells, in eighths: hbar(2.5) == "██▌"."""
    whole = math.floor(cells)
    part = round((cells - whole) * 8)
    if part == 8:
        whole, part = whole + 1, 0
    return "█" * whole + (EIGHTHS[part - 1] if part else "")


def largest_remainder(weights: list[float], cells: int) -> list[int]:
    """Split ``cells`` whole cells among ``weights`` in proportion (largest remainder)."""
    total = sum(weights)
    raw = [w / total * cells for w in weights]
    out = [math.floor(r) for r in raw]
    order = sorted(range(len(raw)), key=lambda i: (out[i] - raw[i], i))
    for i in order[: cells - sum(out)]:
        out[i] += 1
    return out


def cell_counts(weights: list[float], cells: int) -> tuple[list[int], list[bool]]:
    """``largest_remainder``, then a weight that got no cell is given one (flagged True in the
    second list), taken from the weight holding the most. Needs ``len(weights) <= cells / 2``."""
    out = largest_remainder(weights, cells)
    small = [n == 0 for n in out]
    for i in (i for i, s in enumerate(small) if s):
        donor = max(range(len(out)), key=lambda j: (out[j], -j))
        out[donor] -= 1
        out[i] = 1
    return out, small


class Track:
    """A bracketed axis of ``cells`` cells over ``domain``, for position chips.

    ``Track(11, (lo, hi))``, then ``span``/``put`` marks in drawing order (later wins), then
    ``glyph()``. A value outside the domain lands on the end cell and turns that end's bracket
    into ``<`` or ``>``, so a cut is always visible.
    """

    def __init__(self, cells: int, domain: tuple[float, float]) -> None:
        self.cells = cells
        self.lo, self.hi = domain
        self._chars = [TRACK] * cells
        self._roles: list[str | None] = [None] * cells
        self.clipped_lo = self.clipped_hi = False

    def contains(self, v: float) -> bool:
        """Whether ``v`` is inside the domain. Place a reference only when it is."""
        return self.lo <= v <= self.hi

    def cell(self, v: float) -> int:
        """Cell index of ``v``; records clipping when ``v`` is outside the domain."""
        if v < self.lo:
            self.clipped_lo = True
            return 0
        if v > self.hi:
            self.clipped_hi = True
            return self.cells - 1
        return round((v - self.lo) / (self.hi - self.lo) * (self.cells - 1))

    def span(self, a: float, b: float, *, ends: bool = True, role: str | None = None) -> None:
        """``├───┤`` from ``a`` to ``b`` (``─`` throughout when ``ends`` is False)."""
        a, b = sorted((a, b))
        i, j = self.cell(a), self.cell(b)
        for k in range(i, j + 1):
            self.set(k, RULE, role)
        if ends and j > i:  # no end cap where the span runs past the domain
            if a >= self.lo:
                self.set(i, LO_END, role)
            if b <= self.hi:
                self.set(j, HI_END, role)

    def put(self, v: float, ch: str, role: str | None = None) -> int:
        """Place one glyph at ``v``; returns the cell index."""
        k = self.cell(v)
        self.set(k, ch, role)
        return k

    def set(self, k: int, ch: str, role: str | None = None) -> None:
        self._chars[k], self._roles[k] = ch, role

    def glyph(self) -> list[Segment]:
        segs: list[Segment] = [("<" if self.clipped_lo else "[", None)]
        for ch, role in zip(self._chars, self._roles, strict=True):
            if segs and segs[-1][1] == role:
                segs[-1] = (segs[-1][0] + ch, role)
            else:
                segs.append((ch, role))
        segs.append((">" if self.clipped_hi else "]", None))
        return segs
