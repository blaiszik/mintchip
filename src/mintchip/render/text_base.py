"""Text tier: glyphs, cell helpers, ASCII transliteration and ANSI colour.

A text renderer has the signature ``render(chip, o: TextOptions) -> TextOut``. It writes the
Unicode tier only, from the glyphs below; ``Chip.text(ascii=True)`` transliterates the whole
output through ``ASCII``, so renderers branch on ``o.ascii`` only when the transliteration of a
specific glyph would read badly.
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..themes import Theme

__all__ = [
    "ALLOWED",
    "ASCII",
    "BRAILLE_BASE",
    "BRAILLE_COL",
    "BRAILLE_LEFT",
    "BRAILLE_RIGHT",
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
    "ansi_theme",
    "braille_cell",
    "braille_level_mask",
    "braille_mode",
    "braille_row",
    "cell_counts",
    "hbar",
    "is_braille_mode",
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
_ANSI_THEME: ContextVar[Theme | None] = ContextVar("_mintchip_ansi_theme", default=None)
_BRAILLE_MODE: ContextVar[bool] = ContextVar("_mintchip_braille_mode", default=False)

# --- optional 2×4 inline Braille grid (U+2800..U+28FF) --------------------------------------
BRAILLE_BASE = 0x2800
BRAILLE_LEFT = (0x01, 0x02, 0x04, 0x40)  # rows 0 (top) .. 3 (bottom), dots 1,2,3,7
BRAILLE_RIGHT = (0x08, 0x10, 0x20, 0x80)  # rows 0 (top) .. 3 (bottom), dots 4,5,6,8
BRAILLE_COL = (BRAILLE_LEFT, BRAILLE_RIGHT)

Segment = tuple[str, str | None]  # (text, role)
Glyph = str | Sequence[Segment]


@dataclass(frozen=True)
class TextOptions:
    """What a text renderer is asked for. ``domain`` is already resolved (render argument,
    then ``args["domain"]``, then ``chip.domain``). ``decimals``, when given, is the decimal
    places for the primary value (a table column passes one count to all its cells); kinds
    whose value is not a decimal number ignore it. ``braille`` requests high-res 2×4 inline
    Braille glyphs when supported and ``ascii`` is False."""

    ascii: bool = False
    compact: bool = False
    domain: tuple[float, float] | None = None
    decimals: int | None = None
    braille: bool = False


def braille_cell(mask: int) -> str:
    """Return the Unicode Braille Patterns character (U+2800..U+28FF) for bitmask ``mask``."""
    return chr(BRAILLE_BASE | (mask & 0xFF))


def braille_row(v: float, lo: float, hi: float) -> int:
    """Map ``v`` on ``[lo, hi]`` to a 4-level Braille row index: 0 (top) .. 3 (bottom)."""
    t = 0.5 if hi <= lo else min(1.0, max(0.0, (v - lo) / (hi - lo)))
    return 3 - min(3, max(0, round(t * 3)))


def braille_level_mask(col: int, height: int) -> int:
    """Return the Braille bitmask filling ``height`` dots (0..4) from the bottom in ``col``."""
    bits = BRAILLE_COL[col]
    mask = 0
    for r in range(4 - min(4, max(0, height)), 4):
        mask |= bits[r]
    return mask


def is_braille_mode() -> bool:
    """Return True when a :func:`braille_mode` context is active."""
    return _BRAILLE_MODE.get()


@contextmanager
def braille_mode(enabled: bool = True) -> Iterator[None]:
    """Temporarily enable or disable 2×4 inline Braille rendering for text renders."""
    token = _BRAILLE_MODE.set(bool(enabled))
    try:
        yield
    finally:
        _BRAILLE_MODE.reset(token)


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


def _hex_rgb(colour: str) -> tuple[int, int, int] | None:
    """Parse a ``#RGB`` or ``#RRGGBB`` hex colour into an ``(r, g, b)`` 0..255 triple."""
    if not colour.startswith("#"):
        return None
    h = colour[1:]
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return None
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None


def _hex_sgr(colour: str) -> str | None:
    """Convert a ``#RGB`` or ``#RRGGBB`` hex colour to a 24-bit ANSI foreground SGR parameter."""
    rgb = _hex_rgb(colour)
    return f"38;2;{rgb[0]};{rgb[1]};{rgb[2]}" if rgb is not None else None


def _ramp_sgr(t: float, active: Theme | None, *, force_truecolor: bool = False) -> str | None:
    """Return an SGR foreground code along the active theme's accent ramp for ``t`` in [0, 1].

    When ``active`` is None and ``force_truecolor`` is False, falls back to the classic 16-color
    density mapping (dim for lowest, default for mid, blue accent for highest) so default ANSI
    stays backwards compatible.
    """
    t = min(1.0, max(0.0, t))
    if active is None and not force_truecolor:
        idx = min(3, max(0, round(t * 3)))
        return "2" if idx == 0 else "34" if idx == 3 else None

    if active is not None:
        accent = _hex_rgb(active.accent) or (13, 131, 102)
        ink_rgb = _hex_rgb(active.ink)
        is_dark = (
            (0.2126 * ink_rgb[0] + 0.7152 * ink_rgb[1] + 0.0722 * ink_rgb[2]) > 128
            if ink_rgb is not None
            else False
        )
        if is_dark:
            base = (
                round(26 * 0.78 + accent[0] * 0.22),
                round(32 * 0.78 + accent[1] * 0.22),
                round(38 * 0.78 + accent[2] * 0.22),
            )
        else:
            base = (
                round(242 * 0.82 + accent[0] * 0.18),
                round(245 * 0.82 + accent[1] * 0.18),
                round(244 * 0.82 + accent[2] * 0.18),
            )
    else:
        # Auto theme in true-color mode: neutral mid-to-mint ramp legible on light & dark terminals.
        base = (136, 184, 170)
        accent = (13, 131, 102)

    r = round(base[0] + (accent[0] - base[0]) * t)
    g = round(base[1] + (accent[1] - base[1]) * t)
    b = round(base[2] + (accent[2] - base[2]) * t)
    return f"38;2;{r};{g};{b}"


def _resolve_ansi_theme(theme: str | Theme | None) -> Theme | None:
    if theme is None:
        return _ANSI_THEME.get()
    from ..themes import resolve_theme

    resolved = resolve_theme(theme)
    return None if resolved.auto else resolved


@contextmanager
def ansi_theme(theme: str | Theme | None) -> Iterator[None]:
    """Temporarily apply a 24-bit RGB ANSI palette from ``theme`` to :func:`ansi` calls.

    ``None`` or ``"auto"`` keeps the classic 16-color SGR codes for backwards compatibility.
    Explicit themes (such as ``"mint"`` or ``"mint_dark"``) emit 24-bit RGB foreground codes
    matching ``theme.accent``, ``theme.good``, ``theme.bad`` and ``theme.warn``.
    """
    resolved = None
    if theme is not None:
        from ..themes import resolve_theme

        th = resolve_theme(theme)
        resolved = None if th.auto else th
    token = _ANSI_THEME.set(resolved)
    try:
        yield
    finally:
        _ANSI_THEME.reset(token)


def _role_sgr(role: str, active: Theme | None) -> str | None:
    if role.startswith("ramp24:"):
        try:
            return _ramp_sgr(float(role[7:]), active, force_truecolor=True)
        except ValueError:
            return None
    if role.startswith("ramp:"):
        try:
            return _ramp_sgr(float(role[5:]), active, force_truecolor=False)
        except ValueError:
            return None
    if active is None:
        return _SGR.get(role)
    if role == "context":
        return "2"
    if role in ("accent", "good", "bad", "warn", "ink"):
        return _hex_sgr(getattr(active, role)) or _SGR.get(role)
    return _SGR.get(role)


def ansi(glyph: Glyph, *, ascii: bool = False, theme: str | Theme | None = None) -> str:
    """Join segments, wrapping each coloured role in an ANSI SGR code.

    When ``theme`` (or an active :func:`ansi_theme` context) names a non-auto theme such as
    ``"mint"`` or ``"mint_dark"``, emits 24-bit RGB foreground sequences matching the theme's
    semantic ink roles; otherwise emits standard 16-color SGR codes.
    """
    active = _resolve_ansi_theme(theme)
    out = []
    for text, role in _segments(glyph):
        text = to_ascii(text) if ascii else text
        code = _role_sgr(role, active) if role and text else None
        out.append(f"\x1b[{code}m{text}\x1b[0m" if code else text)
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
