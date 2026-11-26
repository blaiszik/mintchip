"""SVG tier: the Canvas every SVG renderer draws on, and the root wrapper.

An SVG renderer has the signature ``render(chip, c: Canvas) -> None`` and draws only through
the Canvas methods below. They enforce the design rules: paint by role only (there is no way to
name a colour, let alone a background), stroke ≥ 1.25 and dot radius ≥ 1.75 viewBox units,
lines stop at the edge of hollow dots, and data mapped outside the domain is pinned to the edge
with a chevron marking the cut.

Coordinates are viewBox units: the canvas is ``width`` × 16, and 16 units render as 1em.
"""

from __future__ import annotations

import html
import itertools
import json
import math
from collections.abc import Iterable, Mapping
from typing import Any

from ..themes import DARK_INK, LIGHT_INK, Theme

__all__ = ["HEIGHT", "MIN_RADIUS", "MIN_STROKE", "SIZES", "Canvas", "svg_root"]

SIZES = {"s": 40, "m": 72, "l": 104}
HEIGHT = 16
MIN_STROKE = 1.25
MIN_RADIUS = 1.75
PAD = 2.5
CONTEXT_OPACITY = 0.45  # context strokes: axes, references, a comparison series
MARK_OPACITY = 0.6  # context dots and strokes under 1.5 wide: fainter would vanish at 1x
WASH_OPACITY = 0.16  # context fills: bands, normal ranges
BAND_OPACITY = 0.3  # a context fill only a few units tall (a narrow target band): 0.16 vanishes

Point = tuple[float, float]


def _n(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Canvas:
    """A ``width`` × 16 drawing surface with a plot area inset by ``pad`` on every side.

    ``domain`` is the resolved scale for the chip (render argument, then ``args["domain"]``,
    then ``chip.domain``): the x-extent for position chips, the y-extent for ``spark``.
    ``natural`` is True when that is the chip's own scale, not one imposed for comparison: a
    renderer may then tighten it to its marks, so a lone chip carries no blank margin into the
    sentence (an imposed scale must be kept as given, or a table column stops lining up).
    """

    def __init__(
        self,
        width: float,
        theme: Theme,
        domain: tuple[float, float] | None = None,
        *,
        pad: float = PAD,
        natural: bool = False,
    ) -> None:
        self.width, self.height = float(width), float(HEIGHT)
        self.theme = theme
        self.domain = domain
        self.natural = natural
        self.pad = pad
        self.left, self.right = pad, width - pad
        self.top, self.bottom = pad, HEIGHT - pad
        self.mid = HEIGHT / 2
        self.clipped: set[str] = set()  # sides where x()/y() pinned data: left/right/top/bottom
        self._cuts: list[tuple[str, float | None]] = []
        self._marks: list[tuple[str, Any]] = []
        self._holes: list[tuple[float, float, float]] = []

    # --- scales -----------------------------------------------------------------------------
    def fx(self, t: float) -> float:
        """Fraction 0..1 of the plot width → x."""
        return self.left + t * (self.right - self.left)

    def fy(self, t: float) -> float:
        """Fraction 0..1 of the plot height → y (0 is the bottom)."""
        return self.bottom - t * (self.bottom - self.top)

    def _t(self, v: float, sides: tuple[str, str], at: float | None) -> float:
        if self.domain is None:
            raise ValueError("this chip has no domain; use fx()/fy() for fractions")
        lo, hi = self.domain
        t = (v - lo) / (hi - lo)
        if -1e-9 <= t <= 1 + 1e-9:
            return t
        side = sides[0] if t < 0 else sides[1]
        self.clipped.add(side)
        if (side, at) not in self._cuts:
            self._cuts.append((side, at))
        return 0.0 if t < 0 else 1.0

    def x(self, v: float, *, at: float | None = None) -> float:
        """Domain value → x. Outside the domain it is pinned to the edge and a chevron is drawn
        there, at height ``at`` (default: middle)."""
        return self.fx(self._t(v, ("left", "right"), at))

    def y(self, v: float, *, at: float | None = None) -> float:
        """Domain value → y. Outside the domain it is pinned to the edge and a chevron is drawn
        there, at x position ``at`` (default: centre); pass the point's x."""
        return self.fy(self._t(v, ("bottom", "top"), at))

    def contains(self, v: float) -> bool:
        """Whether ``v`` is inside the domain. Draw a reference only when it is: a reference
        pinned to the edge would mislead."""
        return self.domain is not None and self.domain[0] <= v <= self.domain[1]

    # --- marks ------------------------------------------------------------------------------
    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        role: str = "ink",
        width: float = 1.5,
        dash: tuple[float, float] | None = None,
        title: str | None = None,
    ) -> None:
        """A straight stroke."""
        self.path([(x1, y1), (x2, y2)], role=role, width=width, dash=dash, title=title)

    def path(
        self,
        points: Iterable[Point | None],
        *,
        role: str = "ink",
        width: float = 1.5,
        dash: tuple[float, float] | None = None,
        title: str | None = None,
    ) -> None:
        """A polyline through ``points``; a None entry breaks it (a gap in the data)."""
        _check_stroke(width)
        runs: list[list[Point]] = [[]]
        for p in points:
            if p is None:
                runs.append([])
            else:
                runs[-1].append((float(p[0]), float(p[1])))
        segs = [(a, b) for run in runs for a, b in itertools.pairwise(run)]
        self._marks.append(("path", (segs, role, width, dash, title)))

    def dot(
        self,
        x: float,
        y: float,
        *,
        role: str = "ink",
        r: float = 2.25,
        hollow: bool = False,
        stroke: float = 1.5,
        title: str | None = None,
    ) -> None:
        """A point. ``hollow=True`` draws a ring (fill:none, ``stroke`` wide) and every line
        stops at its edge."""
        if r < MIN_RADIUS:
            raise ValueError(f"dot radius {r} is below the {MIN_RADIUS} minimum")
        _check_stroke(stroke)
        if hollow:
            self._holes.append((x, y, r + stroke / 2))
        self._marks.append(("dot", (x, y, r, role, hollow, title, stroke)))

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        role: str = "context",
        opacity: float = 1.0,
        narrow: bool = False,
        title: str | None = None,
    ) -> None:
        """A filled area. ``role="context"`` is a light wash (bands, ranges), or with
        ``narrow=True`` a firmer one for a band only a few units tall; ``opacity`` steps ink for
        parts of a whole (keep it ≥ 0.2)."""
        if not 0.2 <= opacity <= 1:
            raise ValueError(f"rect opacity {opacity} is outside 0.2..1")
        if narrow:
            opacity *= BAND_OPACITY / WASH_OPACITY if role == "context" else 1
        self._marks.append(("rect", (x, y, max(w, 0.0), max(h, 0.0), role, opacity, title)))

    def chevron(self, side: str, *, at: float | None = None, role: str = "ink") -> None:
        """A small arrowhead on the plot edge ``side`` (left/right/top/bottom) saying the data
        continue past it; ``at`` is its position along that edge. ``x()``/``y()`` draw these
        automatically for pinned data, so renderers rarely call this. Its arms are kept inside
        the canvas, so a cut at a corner does not reach into the neighbouring text."""
        reach = 3 + MIN_STROKE / 2  # half the chevron's spread, plus half its stroke
        if side in ("left", "right"):
            tip = self.left - 1 if side == "left" else self.right + 1
            back = tip + (2.5 if side == "left" else -2.5)
            y = self.mid if at is None else min(max(at, reach), self.height - reach)
            pts = [(back, y - 3), (tip, y), (back, y + 3)]
        elif side in ("top", "bottom"):
            tip = self.top - 1.5 if side == "top" else self.bottom + 1.5
            back = tip + (2.5 if side == "top" else -2.5)
            x = (self.left + self.right) / 2 if at is None else at
            x = min(max(x, reach), self.width - reach)
            pts = [(x - 3, back), (x, tip), (x + 3, back)]
        else:
            raise ValueError(f"unknown side {side!r}")
        self.path(pts, role=role, width=MIN_STROKE)

    def fit(self) -> None:
        """Make the canvas end ``pad`` after the rightmost mark drawn so far, so a chip with few
        marks leaves no blank run in the sentence (and one with many does not run into the
        next word). Call it after drawing; the width stays in em."""
        right = 0.0
        for kind, data in self._marks:
            if kind == "path":
                segs, _, width, _, _ = data
                right = max([right] + [p[0] + width / 2 for seg in segs for p in seg])
            elif kind == "dot":
                x, _, r, _, hollow, _, stroke = data
                right = max(right, x + r + (stroke / 2 if hollow else 0))
            else:
                right = max(right, data[0] + data[2])
        if right and "right" not in self.clipped:
            self.width, self.right = right + self.pad, right

    # --- output -----------------------------------------------------------------------------
    def body(self) -> str:
        """The SVG elements drawn so far, with edge chevrons for any clipped data."""
        for side, at in self._cuts:
            self.chevron(side, at=at)
        self._cuts.clear()
        return "".join(self._emit(kind, data) for kind, data in self._marks)

    def _stroke(
        self,
        role: str,
        width: float,
        dash: tuple[float, float] | None = None,
        *,
        mark: bool = False,
    ) -> str:
        cap = "butt" if dash else "round"
        s = f"fill:none;stroke:{self.theme.paint(role)};stroke-width:{_n(width)}"
        s += f";stroke-linecap:{cap};stroke-linejoin:round"
        if role == "context":  # a dot or a thin line is a mark, and needs more than an axis
            s += f";stroke-opacity:{MARK_OPACITY if mark or width < 1.5 else CONTEXT_OPACITY}"
        if dash:
            s += f";stroke-dasharray:{_n(dash[0])} {_n(dash[1])}"
        return s

    def _fill(self, role: str, opacity: float = 1.0, *, mark: bool = False) -> str:
        a = opacity * ((MARK_OPACITY if mark else WASH_OPACITY) if role == "context" else 1.0)
        return f"fill:{self.theme.paint(role)}" + ("" if a == 1 else f";fill-opacity:{_n(a)}")

    def _emit(self, kind: str, data: Any) -> str:
        if kind == "path":
            segs, role, width, dash, title = data
            d = _path_d(self._cut(segs))
            if not d:
                return ""
            return _el("path", f'd="{d}" style="{self._stroke(role, width, dash)}"', title)
        if kind == "dot":
            x, y, r, role, hollow, title, stroke = data
            style = self._stroke(role, stroke, mark=True) if hollow else self._fill(role, mark=True)
            return _el("circle", f'cx="{_n(x)}" cy="{_n(y)}" r="{_n(r)}" style="{style}"', title)
        x, y, w, h, role, opacity, title = data
        geo = f'x="{_n(x)}" y="{_n(y)}" width="{_n(w)}" height="{_n(h)}"'
        return _el("rect", f'{geo} style="{self._fill(role, opacity)}"', title)

    def _cut(self, segs: list[tuple[Point, Point]]) -> list[tuple[Point, Point]]:
        """Remove the parts of each segment that fall inside a hollow dot."""
        for cx, cy, rad in self._holes:
            out = []
            for (x1, y1), (x2, y2) in segs:
                dx, dy, fx, fy = x2 - x1, y2 - y1, x1 - cx, y1 - cy
                a, b, c = dx * dx + dy * dy, 2 * (fx * dx + fy * dy), fx * fx + fy * fy - rad * rad
                disc = b * b - 4 * a * c
                if a == 0 or disc <= 0:
                    out.append(((x1, y1), (x2, y2)))
                    continue
                t1, t2 = (-b - math.sqrt(disc)) / (2 * a), (-b + math.sqrt(disc)) / (2 * a)
                for lo, hi in ((0.0, min(t1, 1.0)), (max(t2, 0.0), 1.0)):
                    if hi - lo > 1e-3:
                        p = (x1 + dx * lo, y1 + dy * lo)
                        q = (x1 + dx * hi, y1 + dy * hi)
                        out.append((p, q))
            segs = out
        return segs


def _check_stroke(width: float) -> None:
    if width < MIN_STROKE:
        raise ValueError(f"stroke width {width} is below the {MIN_STROKE} minimum")


def _path_d(segs: list[tuple[Point, Point]]) -> str:
    d: list[str] = []
    last: Point | None = None
    for p, q in segs:
        if last is None or abs(last[0] - p[0]) > 1e-6 or abs(last[1] - p[1]) > 1e-6:
            d.append(f"M{_n(p[0])} {_n(p[1])}")
        d.append(f"L{_n(q[0])} {_n(q[1])}")
        last = q
    return "".join(d)


def _el(tag: str, attrs: str, title: str | None) -> str:
    if title:
        return f"<{tag} {attrs}><title>{html.escape(title)}</title></{tag}>"
    return f"<{tag} {attrs}/>"


def svg_root(
    c: Canvas,
    *,
    alt: str,
    facts: Iterable[str],
    spec: Mapping[str, Any],
    standalone: bool = False,
) -> str:
    """Wrap a drawn Canvas in the contract's root element, title, desc and data-mc spec."""
    data = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    style = ""
    if standalone:
        style = (
            f"<style>svg{{color:{LIGHT_INK}}}"
            f"@media (prefers-color-scheme:dark){{svg{{color:{DARK_INK}}}}}</style>"
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(c.width)} 16" '
        f'width="{_n(c.width / 16)}em" height="1em" role="img" '
        f'aria-label="{html.escape(alt, quote=True)}" data-mc="{html.escape(data, quote=True)}" '
        f'style="vertical-align:-0.15em;overflow:visible">'
        f"<title>{html.escape(alt)}</title><desc>{html.escape('; '.join(facts))}</desc>"
        f"{style}{c.body()}</svg>"
    )
