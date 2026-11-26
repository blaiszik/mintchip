"""gauge: a reading against its normal range, with an optional wider warn range.

Text: ``7.38 (normal 7.35 to 7.45) [··├─●───┤··]``; compact drops the parenthesis, which also
says ``high`` or ``low`` when the reading is outside the normal range. Warn edges are ``│``.
SVG: the normal range as a thick context band, the warn range as a thin context line either
side of it, and the reading as a dot coloured good / warn / bad by which band it falls in,
so the colour always repeats what the position shows. Drawn alone, the scale spans just the
marks, so no blank margin sits in the sentence; the text track keeps its margin cells.
"""

from __future__ import annotations

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import DOT, REF, TextOptions, TextOut, Track
from ..scales import padded
from ..spec import (
    Built,
    Chip,
    ChipError,
    Param,
    chip,
    domain_warnings,
    svg_renderer,
    text_renderer,
)

CELLS = 11
BAND = 4.0  # stroke width of the normal band
DOT_R = 3.0
FIT = 0.015  # the SVG's margin when drawn on its own scale: room for the dot at an end
ROLE = {"normal": "good", "warn": "warn", "low": "bad", "high": "bad"}


@chip(
    "gauge",
    question="Is a reading inside its normal range?",
    have="A reading with a normal range",
    params=(
        Param("value", "number", "Give the reading.", required=True, positional=True),
        Param(
            "normal",
            "range",
            "Give the normal range (lo, hi).",
            required=True,
            positional=True,
        ),
        Param("warn", "range", "Give a wider caution range (lo, hi) that contains normal."),
        Param("domain", "range", "Fix the x-range (lo, hi); share it so gauges compare."),
        Param("label", "string", "Say what is read."),
        Param("unit", "string", "Name the unit of the reading."),
    ),
    example={"value": 7.38, "normal": (7.35, 7.45), "label": "Blood pH"},
    size="m",
)
def gauge(value, normal, *, warn=None, domain=None, label=None, unit=None) -> Built:
    n_lo, n_hi = normal
    if not n_lo < n_hi:
        raise ChipError(
            f"normal must have lo < hi; got ({n_lo:g}, {n_hi:g}).",
            fix_hint="Pass the normal range as normal=(lo, hi), e.g. (7.35, 7.45).",
        )
    if warn is not None and not warn[0] <= n_lo < n_hi <= warn[1]:
        raise ChipError(
            f"warn ({warn[0]:g}, {warn[1]:g}) must contain normal ({n_lo:g}, {n_hi:g}).",
            fix_hint="Pass warn= as the wider caution range around normal, e.g. (7.3, 7.5).",
        )
    if n_lo <= value <= n_hi:
        status = "normal"
    elif warn is not None and warn[0] <= value <= warn[1]:
        status = "warn"
    else:
        status = "high" if value > n_hi else "low"
    side = "high" if value > n_hi else "low" if value < n_lo else None
    s = {
        "value": value,
        "normal": normal,
        "warn": warn,
        "status": status,
        "side": side,
    }
    ends = _ends(s)
    # The range's own precision, or more when rounding would move the reading or a limit by
    # over 3% of the normal width (7.384 in 7.35 to 7.45 needs the third place).
    s["dec"] = max(0, fmt.decimals(n_hi - n_lo), fmt.resolving(ends, n_hi - n_lo))
    lo, hi = min(ends), max(ends)
    pad = max(0.2 * (hi - lo), 0.5 * (n_hi - n_lo))
    natural = (lo - pad, hi + pad)

    def f(v: float, u: str | None = None) -> str:
        return fmt.fixed(v, s["dec"], unit=u)

    warnings = _cut_lines(s, unit, domain or natural)

    rel = {None: "within", "high": "above", "low": "below"}[side]
    alt = f"{f(value, unit)}, {rel} the normal range {f(n_lo)} to {f(n_hi, unit)}"
    if side is None:
        facts = [f"{f(min(value - n_lo, n_hi - value), unit)} inside the nearest normal limit"]
    else:
        gap = value - n_hi if side == "high" else n_lo - value
        facts = [f"{f(gap, unit)} {rel} the normal range"]
    if warn is not None:
        inside = "inside" if warn[0] <= value <= warn[1] else "outside"
        facts.append(f"{inside} the warn range {f(warn[0])} to {f(warn[1], unit)}")
        if side is not None:
            alt += f", {inside} the warn range"
    return Built(
        stats=s,
        facts=facts,
        warnings=warnings,
        alt=f"{label}: {alt}." if label else f"{alt}.",
        domain=natural,
    )


def _ends(s: dict) -> list[float]:
    return [s["value"], *s["normal"], *(s["warn"] or ())]


def _cut_lines(s: dict, unit: str | None, domain: tuple[float, float]) -> list[str]:
    ends = _ends(s)
    if min(ends) >= domain[0] and max(ends) <= domain[1]:
        return []
    lo, hi = fmt.num(domain[0]), fmt.num(domain[1])
    return [
        (
            f"domain {lo} to {fmt.with_unit(hi, unit)} cuts the reading or its ranges; a cut "
            "reading is pinned to the edge and marked (< or > in text, a chevron in SVG)."
        )
    ]


@domain_warnings("gauge")
def _cuts(chip: Chip, domain: tuple[float, float], own: bool) -> list[str]:
    return _cut_lines(chip.stats, chip.unit, domain)


# --- text -----------------------------------------------------------------------------------
@text_renderer("gauge")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    dec, unit = s["dec"] if o.decimals is None else o.decimals, chip.unit
    value = fmt.fixed(s["value"], dec, unit=unit)
    if not o.compact:
        n_lo, n_hi = s["normal"]
        side = f"{s['side']}; " if s["side"] else ""
        value += f" ({side}normal {fmt.fixed(n_lo, dec)} to {fmt.fixed(n_hi, dec)})"

    t = Track(CELLS, o.domain)
    if s["warn"] is not None:
        for edge in s["warn"]:
            if t.contains(edge):
                t.put(edge, REF, "context")
    t.span(*s["normal"], role="context")
    t.put(s["value"], DOT, ROLE[s["status"]])
    return TextOut(value, t.glyph(), dec)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("gauge")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    if c.natural:  # alone: the scale spans the marks, so no blank margin sits in the sentence
        ends = _ends(s)
        c.domain = padded(min(ends), max(ends), FIT)
    lo, hi = c.domain
    v = s["value"]
    cut = -1 if v < lo else 1 if v > hi else 0
    if cut < 0:
        c.left += DOT_R + 4
    if cut > 0:
        c.right -= DOT_R + 4

    def span(a: float, b: float, width: float) -> None:
        """A context stroke over [a, b] trimmed to the domain; the round caps end on a, b."""
        a, b = max(a, lo), min(b, hi)
        if b <= a:
            return
        x1, x2 = c.x(a) + width / 2, c.x(b) - width / 2
        if x2 < x1:  # narrower than the stroke: a round dab centred on the range
            x1 = x2 = (x1 + x2) / 2
        c.line(x1, c.mid, x2, c.mid, role="context", width=width)

    n_lo, n_hi = s["normal"]
    if s["warn"] is not None:
        span(s["warn"][0], n_lo, 1.5)
        span(n_hi, s["warn"][1], 1.5)
    span(n_lo, n_hi, BAND)
    x = c.x(min(max(v, lo), hi))
    role = ROLE[s["status"]]
    c.dot(x, c.mid, r=DOT_R, role=role, title=fmt.fixed(v, s["dec"], unit=chip.unit))
    if cut:  # a reading off the scale: the dot sits on the edge with a chevron beyond it
        back = x + cut * (DOT_R + 1.25)
        c.path(
            [(back, c.mid - 3), (back + cut * 2.5, c.mid), (back, c.mid + 3)],
            width=1.25,
        )
