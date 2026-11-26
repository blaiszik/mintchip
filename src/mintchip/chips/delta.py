"""delta: a before and an after on one axis.

Text: ``0.74→0.82 (+0.08) [··○────●··]``; compact drops the parenthesis. Direction is carried
by hollow-then-solid and by the numbers, never by an arrowhead glyph. SVG: a context axis, a
connecting line, a hollow start and a solid end. The line and end turn good/bad only when the
caller passes ``higher_is_better``; otherwise the chip is ink only.

The natural domain pads the pair by half its gap on each side, so a lone delta fills the middle
of its axis; pass one ``domain=`` (``mintchip.shared_domain(a, b)``) to compare several.
"""

from __future__ import annotations

import math

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import DOT, HOLLOW, TextOptions, TextOut, Track
from ..scales import padded
from ..spec import Built, Chip, Param, chip, domain_warnings, svg_renderer, text_renderer

CELLS = 10
PAD = 0.5  # natural domain margin on each side, as a fraction of |after − before|
INSET = 0.75  # SVG plot inset beyond the Canvas pad, room for a dot pinned at the edge


@chip(
    "delta",
    question="How much did a value change from before to after?",
    have="A before and an after value",
    params=(
        Param("before", "number", "Give the starting value.", required=True, positional=True),
        Param("after", "number", "Give the ending value.", required=True, positional=True),
        Param("domain", "range", "Fix the x-range (lo, hi); share it so deltas compare."),
        Param("higher_is_better", "bool", "Declare a direction: the change turns good or bad."),
        Param("label", "string", "Say what changed."),
        Param("unit", "string", "Name the unit of the values."),
    ),
    example={"before": 0.74, "after": 0.82, "higher_is_better": True, "label": "Accuracy"},
    size="m",
)
def delta(
    before,
    after,
    *,
    domain=None,
    higher_is_better=None,
    label=None,
    unit=None,
) -> Built:
    change = after - before
    better = None
    if higher_is_better is not None and change != 0:
        better = "good" if (change > 0) == higher_is_better else "bad"
    s = {
        "value": change,
        "before": before,
        "after": after,
        "change": change,
        "dec": _decimals(before, after),
        "better": better,
    }
    lo, hi = min(before, after), max(before, after)
    natural = padded(lo, hi, PAD)
    warnings = _cut_lines(s, unit, domain or natural)

    word = "up" if change > 0 else "down" if change < 0 else "unchanged"
    facts = [f"{word} {_f(s, abs(change), unit)}" if change else "unchanged"]
    if change and before != 0:
        facts[0] += f" ({fmt.pct(change / abs(before), signed=True)} of the start)"
    if higher_is_better is not None:
        facts.append("higher is better" if higher_is_better else "lower is better")
    alt = f"{_f(s, before)} to {_f(s, after, unit)}, {facts[0]}"
    return Built(
        stats=s,
        facts=facts,
        warnings=warnings,
        alt=f"{label}: {alt}." if label else f"{alt[0].upper()}{alt[1:]}.",
        domain=natural,
    )


def _cut_lines(s: dict, unit: str | None, domain: tuple[float, float]) -> list[str]:
    if domain[0] <= min(s["before"], s["after"]) and max(s["before"], s["after"]) <= domain[1]:
        return []
    lo, hi = fmt.num(domain[0]), fmt.num(domain[1], unit=unit)
    return [
        (
            f"domain {lo} to {hi} cuts the change; the cut end is pinned to the edge and marked "
            "(< or > in text, a chevron in SVG)."
        )
    ]


@domain_warnings("delta")
def _cuts(chip: Chip, domain: tuple[float, float], own: bool) -> list[str]:
    return _cut_lines(chip.stats, chip.unit, domain)


def _decimals(before: float, after: float) -> int | None:
    """One decimal place for before, after and change, set by the size of the change: one
    significant figure of it (0.08), or two when one would be more than 5% off (3.8, 0.013),
    or more when rounding would move any of the three by over 3% of the change (0.744→0.821
    needs 0.077, not 0.08); None when nothing changed."""
    change = after - before
    if not change:
        return None
    dec = -math.floor(math.log10(abs(change)))
    if abs(round(change, dec) - change) > 0.05 * abs(change):
        dec += 1
    return max(0, dec, fmt.resolving([before, after, change], abs(change)))


def _f(
    s: dict, v: float, unit: str | None = None, *, signed: bool = False, dec: int | None = None
) -> str:
    dec = s["dec"] if dec is None else dec
    if dec is None:
        return fmt.num(v, signed=signed, unit=unit)
    return fmt.fixed(v, dec, signed=signed, unit=unit)


def _change(s: dict, unit: str | None, dec: int | None = None) -> str:
    if not s["change"]:
        return f"±{_f(s, 0, unit, dec=dec)}"
    return _f(s, s["change"], unit, signed=True, dec=dec)


# --- text -----------------------------------------------------------------------------------
@text_renderer("delta")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    dec = o.decimals if o.decimals is not None else s["dec"]
    value = f"{_f(s, s['before'], dec=dec)}→{_f(s, s['after'], chip.unit, dec=dec)}"
    if not o.compact:
        value += f" ({_change(s, chip.unit, dec)})"
    t = Track(CELLS, o.domain)
    t.span(s["before"], s["after"], ends=False, role=s["better"])
    t.put(s["before"], HOLLOW)
    t.put(s["after"], DOT, s["better"])  # unchanged: the solid end covers the hollow start
    shown = dec if dec is not None else fmt.places(fmt.num(s["after"]))
    return TextOut(value, t.glyph(), shown)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("delta")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    y = c.mid
    # The plot ends INSET inside the pad, so a dot pinned at an edge (the hollow start reaches
    # 3.25 with its stroke) stays inside the chip.
    c.left, c.right = c.left + INSET, c.right - INSET
    c.line(c.left, y, c.right, y, role="context", width=1.25)
    xb, xa = c.x(s["before"]), c.x(s["after"])
    role = s["better"] or "ink"
    start, end = _f(s, s["before"], chip.unit), _f(s, s["after"], chip.unit)
    if abs(xa - xb) < 1:  # unchanged at this scale: a ring around a dot
        xb = xa = min(max(xb, c.left + 0.75), c.right - 0.75)  # the ring reaches 4.0
        c.dot(xb, y, r=3.25, hollow=True, title=start)
        c.dot(xa, y, r=1.75, title=end)
        return
    c.line(xb, y, xa, y, role=role, width=1.75)
    c.dot(xb, y, r=2.5, hollow=True, title=start)
    c.dot(xa, y, r=2.75, role=role, title=f"{end} ({_change(s, chip.unit)})")
