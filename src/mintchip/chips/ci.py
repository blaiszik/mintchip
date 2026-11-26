"""ci: an estimate with its interval, against a reference. The exemplar for an axis-position
chip (``[...]`` text track, x-domain, reference line).

Text: ``+0.08 (95% CI +0.05 to +0.11) [·│···├─●─┤·]``; compact drops the parenthesis. The dot is
hollow (``○``) when the interval crosses the reference: shape says it, not colour. The estimate
and both bounds share one decimal place: the fewest at which rounding moves none of them by more
than 3% of the interval width (``fmt.resolving``), so ``+0.031 (… +0.012 to +0.050)``.
SVG: a whisker with end ticks, a solid or hollow dot, a context reference line. Drawn alone, it
spans just its marks; the text track keeps a margin cell, which is axis, not blank.
"""

from __future__ import annotations

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import CROSS, DOT, HOLLOW, REF, TextOptions, TextOut, Track
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
PAD = 0.16  # natural domain margin, as a fraction of the drawn extent (text track cells)
FIT = 0.02  # the SVG's margin when drawn on its own scale: room for a dot at an end


@chip(
    "ci",
    question="What is the estimate, and how sure are we?",
    have="An estimate with an interval",
    params=(
        Param("estimate", "number", "Give the point estimate.", required=True, positional=True),
        Param(
            "interval",
            "range",
            "Give the interval (lo, hi) around the estimate.",
            required=True,
            positional=True,
        ),
        Param("level", "number", "State the interval's coverage, e.g. 0.95 for a 95% CI."),
        Param("inner", "range", "Give a narrower inner interval (lo, hi), drawn thicker."),
        Param(
            "reference", "number", "Give the null value; None for no reference line.", default=0.0
        ),
        Param("domain", "range", "Fix the x-range (lo, hi); share it so ci chips compare."),
        Param("label", "string", "Say what is estimated."),
        Param("unit", "string", "Name the unit of the estimate."),
    ),
    example={"estimate": 0.08, "interval": (0.05, 0.11), "level": 0.95, "label": "Retrieval lift"},
    size="m",
)
def ci(
    estimate,
    interval,
    *,
    level=None,
    inner=None,
    reference=0.0,
    domain=None,
    label=None,
    unit=None,
) -> Built:
    lo, hi = interval
    if level is not None and not 0 < level < 1:
        raise ChipError(
            f"level must be between 0 and 1; got {level}.",
            fix_hint="State the coverage as a fraction (level=0.95).",
        )
    if inner is not None and not lo <= inner[0] <= inner[1] <= hi:
        raise ChipError(
            f"inner {inner} must lie within interval {interval}.",
            fix_hint="Pass the narrower interval as inner=, e.g. the 50% CI inside the 95% CI.",
        )
    s = {
        "value": estimate,
        "estimate": estimate,
        "lo": lo,
        "hi": hi,
        "inner": inner,
        "reference": reference,
        "level": level,
        "crosses": None if reference is None else lo <= reference <= hi,
        "dec": fmt.resolving([estimate, lo, hi], hi - lo),
        "signed": reference == 0,
    }
    ends = _ends(s)
    natural = padded(min(ends), max(ends), PAD)

    warnings = []
    if level is None:
        warnings.append(
            "interval level not stated; state the interval's level (level=0.95) or its true "
            "coverage."
        )
    if not lo <= estimate <= hi:
        warnings.append(f"estimate {_f(s, estimate)} lies outside its interval.")
    warnings += _cut_lines(s, unit, domain or natural)

    what = f"{fmt.pct(level)} interval" if level is not None else "interval"
    facts = [f"{what} width {fmt.fixed(hi - lo, s['dec'], unit=unit)}"]
    if inner is not None:
        facts.append(f"inner interval {_f(s, inner[0])} to {_f(s, inner[1], unit)}")
    alt = f"estimate {_f(s, estimate, unit)}, {what} {_f(s, lo)} to {_f(s, hi, unit)}"
    if reference is not None:
        relation = "crosses" if s["crosses"] else "excludes"
        facts.append(f"{relation} the reference {fmt.num(reference, unit=unit)}")
        alt += f", {relation} {fmt.num(reference)}"
    return Built(
        stats=s,
        facts=facts,
        warnings=warnings,
        alt=f"{label}: {alt}." if label else f"{alt[0].upper()}{alt[1:]}.",
        domain=natural,
    )


def _ends(s: dict) -> list[float]:
    ref = s["reference"]
    return [s["lo"], s["hi"], s["estimate"]] + ([ref] if ref is not None else [])


def _cut_lines(s: dict, unit: str | None, domain: tuple[float, float]) -> list[str]:
    ends = _ends(s)
    if min(ends) >= domain[0] and max(ends) <= domain[1]:
        return []
    lo, hi = fmt.num(domain[0]), fmt.num(domain[1], unit=unit)
    return [
        (
            f"domain {lo} to {hi} cuts the interval; the cut end is marked at the edge (< or > in "
            "text, a chevron in SVG)."
        )
    ]


@domain_warnings("ci")
def _cuts(chip: Chip, domain: tuple[float, float], own: bool) -> list[str]:
    return _cut_lines(chip.stats, chip.unit, domain)


def _f(s: dict, v: float, unit: str | None = None, dec: int | None = None) -> str:
    """Every number in one ci shares a decimal place, set by the interval width."""
    return fmt.fixed(v, s["dec"] if dec is None else dec, signed=s["signed"], unit=unit)


# --- text -----------------------------------------------------------------------------------
@text_renderer("ci")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    dec = s["dec"] if o.decimals is None else o.decimals
    value = _f(s, s["estimate"], chip.unit, dec)
    if not o.compact:
        what = f"{fmt.pct(s['level'])} CI " if s["level"] is not None else ""
        value += f" ({what}{_f(s, s['lo'], dec=dec)} to {_f(s, s['hi'], dec=dec)})"

    t = Track(CELLS, o.domain)
    ref = s["reference"]
    if ref is not None and t.contains(ref):
        t.put(ref, REF, "context")
    t.span(s["lo"], s["hi"])
    if s["crosses"] and t.contains(ref):
        t.put(ref, CROSS)
    t.put(s["estimate"], HOLLOW if s["crosses"] else DOT)
    return TextOut(value, t.glyph(), dec)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("ci")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    if c.natural:  # alone: the scale spans the marks, so no blank margin sits in the sentence
        ends = _ends(s)
        c.domain = padded(min(ends), max(ends), FIT)
    y = c.mid
    ref = s["reference"]
    if ref is not None and c.contains(ref):
        x = c.x(ref)
        c.line(x, 1.5, x, 14.5, role="context")
    x1, x2 = c.x(s["lo"]), c.x(s["hi"])
    c.line(x1, y, x2, y)
    for end, x in ((s["lo"], x1), (s["hi"], x2)):
        if c.contains(end):  # a cut end gets the edge chevron instead of a tick
            c.line(x, y - 3, x, y + 3)
    if s["inner"] is not None:
        c.line(c.x(s["inner"][0]), y, c.x(s["inner"][1]), y, width=3.5)
    hollow = bool(s["crosses"])
    title = _f(s, s["estimate"], chip.unit)
    c.dot(c.x(s["estimate"]), y, r=2.5 if hollow else 2.75, hollow=hollow, title=title)
