"""waterfall: signed contributions from a start to a total.

Text prints the arithmetic and no glyph (design rule 6): ``0.63 +0.13 +0.08 −0.02 = 0.82``
(the start is left out when it is 0; the unit goes on the total). With more than TEXT_TERMS
steps the text keeps the TEXT_TERMS − 1 largest steps, in their order, and folds the rest into
one summed term, ``+0.03 (4 others)``, so the line still adds up; a warning says so.
Compact: ``0.63→0.82 (+0.19)``, or ``0.19 (3 steps)`` from a zero start. Numbers share one
decimal place, enough to show the smallest step shown to one significant figure.

SVG: a stepped bridge on its own y-scale (the levels' extent, not zero-based): a level mark for
the start, one floating bar per step, a heavier level mark for the total. Bars are ink, and
direction is read from position; they turn good/bad only when the caller passes
``higher_is_better``. More than SVG_BARS steps fold the same way.
"""

from __future__ import annotations

import math

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import TextOptions, TextOut
from ..spec import Built, Chip, ChipError, Param, chip, svg_renderer, text_renderer

TEXT_TERMS = 4  # most step terms in the text line, a folded remainder included
SVG_BARS = 12  # most step bars in the SVG, a folded remainder included


@chip(
    "waterfall",
    question="Which contributions took a value from its start to its total?",
    have="Signed contributions from a start to a total",
    params=(
        Param(
            "steps",
            "mapping",
            "Give the signed contributions in order, name → change.",
            required=True,
            positional=True,
        ),
        Param("start", "number", "Give the starting level the steps add to.", default=0.0),
        Param("higher_is_better", "bool", "Declare a direction: steps turn good or bad."),
        Param("label", "string", "Say what the steps add up to."),
        Param("unit", "string", "Name the unit of the values."),
    ),
    example={
        "steps": {"retrieval": 0.13, "reranker": 0.08, "latency cap": -0.02},
        "start": 0.63,
        "label": "Accuracy",
    },
    size="m",
)
def waterfall(steps, *, start=0.0, higher_is_better=None, label=None, unit=None) -> Built:
    if not steps:
        raise ChipError(
            "needs at least 1 step.",
            fix_hint='Pass named changes, e.g. mintchip.waterfall({"gain": 0.12, "drag": -0.02}).',
        )
    for name, d in steps.items():
        if isinstance(d, tuple):
            raise ChipError(
                f"step {name!r} must be one signed number; got the pair {d!r}.",
                fix_hint="Give each step's change, not its (start, end).",
            )
    items = [[name, d] for name, d in steps.items()]
    levels = [start]
    for _, d in items:
        levels.append(levels[-1] + d)
    total = levels[-1]
    text_terms = _fold(items, TEXT_TERMS)
    svg_terms = _fold(items, SVG_BARS)
    s = {
        "value": total,
        "start": start,
        "total": total,
        "steps": items,
        "text_terms": text_terms,
        "svg_terms": svg_terms,
        "dec": _decimals([d for _, d in text_terms]),
        "higher_is_better": higher_is_better,
    }

    warnings = []
    if len(text_terms) < len(items):
        rest = text_terms[-1]
        warnings.append(
            f"text shows the {TEXT_TERMS - 1} largest of {len(items)} steps and sums the other "
            f"{len(items) - TEXT_TERMS + 1} into one term ({_term(s, rest[1])} ({rest[0]}))."
        )
    if len(svg_terms) < len(items):
        warnings.append(
            f"SVG draws the {SVG_BARS - 1} largest of {len(items)} steps and the other "
            f"{len(items) - SVG_BARS + 1} as one bar, last."
        )

    net = total - start
    big = max(items, key=lambda kv: abs(kv[1]))
    facts = [
        f"{_n(s, start)} to {_n(s, total, unit)} ({_term(s, net)}) over {len(items)} step"
        + ("s" if len(items) > 1 else ""),
        f"largest step: {big[0]} {_term(s, big[1], unit)}",
    ]
    if higher_is_better is not None:
        helps = sum(1 for _, d in items if d and (d > 0) == higher_is_better)
        hurts = sum(1 for _, d in items if d and (d > 0) != higher_is_better)
        way = "higher" if higher_is_better else "lower"
        facts.append(f"{helps} step(s) help, {hurts} hurt; {way} is better")
    alt = f"from {_n(s, start)} through {len(items)} steps to {_n(s, total, unit)}"
    return Built(
        stats=s,
        facts=facts,
        warnings=warnings,
        alt=f"{label}: {alt}." if label else f"{alt[0].upper()}{alt[1:]}.",
    )


def _fold(items: list[list], most: int) -> list[list]:
    """At most ``most`` terms: the ``most − 1`` largest steps in their order, then the rest
    summed as ``["N others", sum]``."""
    if len(items) <= most:
        return [list(kv) for kv in items]
    keep = sorted(range(len(items)), key=lambda i: -abs(items[i][1]))[: most - 1]
    rest = [items[i][1] for i in range(len(items)) if i not in keep]
    return [list(items[i]) for i in sorted(keep)] + [[f"{len(rest)} others", sum(rest)]]


def _decimals(changes: list[float]) -> int | None:
    """Decimal places that show the smallest step to one significant figure, one more when
    that leaves any step more than 5% off, and at most two more than the largest step needs;
    None when every step is zero."""
    sizes = [abs(d) for d in changes if d]
    if not sizes:
        return None
    dec = -math.floor(math.log10(min(sizes)))
    if any(abs(round(d, dec) - d) > 0.05 * d for d in sizes):
        dec += 1
    return max(0, min(dec, 2 - math.floor(math.log10(max(sizes)))))


def _n(s: dict, v: float, unit: str | None = None) -> str:
    if s["dec"] is None:
        return fmt.num(v, unit=unit)
    return fmt.fixed(v, s["dec"], unit=unit)


def _term(s: dict, d: float, unit: str | None = None) -> str:
    if d == 0:
        return fmt.with_unit("±0", unit)
    if s["dec"] is None:
        return fmt.num(d, signed=True, unit=unit)
    return fmt.fixed(d, s["dec"], signed=True, unit=unit)


def _role(s: dict, d: float) -> str:
    if s["higher_is_better"] is None or d == 0:
        return "ink"
    return "good" if (d > 0) == s["higher_is_better"] else "bad"


# --- text -----------------------------------------------------------------------------------
@text_renderer("waterfall")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    if o.decimals is not None:  # one place for every number, as the chip's own dec is
        s = {**s, "dec": o.decimals}
    total = _n(s, s["total"], chip.unit)
    dec = s["dec"] if s["dec"] is not None else fmt.places(total)
    if o.compact:
        net = _term(s, s["total"] - s["start"])
        if s["start"]:
            return TextOut(f"{_n(s, s['start'])}→{total} ({net})", "", dec)
        n = len(s["steps"])
        return TextOut(f"{total} ({n} step{'s' if n > 1 else ''})", "", dec)
    terms = [_n(s, s["start"])] if s["start"] else []
    folded = len(s["text_terms"]) < len(s["steps"])
    for i, (name, d) in enumerate(s["text_terms"]):
        last = folded and i == len(s["text_terms"]) - 1
        terms.append(_term(s, d) + (f" ({name})" if last else ""))
    return TextOut(f"{' '.join(terms)} = {total}", "", dec)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("waterfall")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    terms = s["svg_terms"]
    levels = [s["start"]]
    for _, d in terms:
        levels.append(levels[-1] + d)
    lo, hi = min(levels), max(levels)

    def y(v: float) -> float:
        return c.fy(0.5 if hi == lo else (v - lo) / (hi - lo))

    slots = len(terms) + 2  # start mark, one bar per step, total mark
    slot = (c.right - c.left) / slots
    gap = min(1.5, slot * 0.3)
    w = slot - gap

    def x(i: int) -> float:
        return c.left + i * slot + gap / 2

    ys = y(s["start"])
    c.line(x(0), ys, x(0) + w, ys, title=f"start {_n(s, s['start'], chip.unit)}")
    for i, (name, d) in enumerate(terms, start=1):
        y0, y1 = y(levels[i - 1]), y(levels[i])
        h = abs(y1 - y0)
        top = min(y0, y1) - max(0.0, 1.5 - h) / 2  # a tiny step keeps a visible sliver
        tip = f"{name}: {_term(s, d, chip.unit)} → {_n(s, levels[i], chip.unit)}"
        c.rect(x(i), top, w, max(h, 1.5), role=_role(s, d), title=tip)
    yt, xt = y(s["total"]), x(slots - 1)
    c.line(xt, yt, xt + w, yt, width=2.5, title=f"total {_n(s, s['total'], chip.unit)}")
