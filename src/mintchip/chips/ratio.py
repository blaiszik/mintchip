"""ratio: k out of n as an icon array (natural frequencies).

Text: ``3/10 ●●●○○○○○○○``: one icon per item when the total is at most ``units``; a larger
total, or a probability (``ratio(0.24)``), is drawn as ``units`` icons with the exact fraction
kept in the value. When whole icons would change the fraction materially (off by a quarter
icon or more, or showing none or all when the truth is neither), the boundary icon is drawn
as a partial icon (``·`` in text, a small dot in SVG) and a warning says so.
SVG: filled dots, then thin open rings in context ink (the rest of the whole, like a bar's
track), in one row cut to fit; ``units`` stops at 10, the most icons that still read as
separate marks at 1x in a word-sized chip.
"""

from __future__ import annotations

import math

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import DOT, HOLLOW, TRACK, TextOptions, TextOut
from ..spec import Built, Chip, ChipError, Param, chip, svg_renderer, text_renderer

MAX_UNITS = 10  # icons in a word-sized array that still read one by one at 1x
MATERIAL = 0.25  # rounding by at least this many icons is announced
PITCH = 6.75
R_FULL, R_RING, R_PART = 2.5, 2.25, 1.75
RING = 1.25  # ring stroke: the thinnest allowed, so the hole stays open at 1x
HINT = "Pass a count with its total, ratio(3, 10), or a probability alone, ratio(0.24)."


@chip(
    "ratio",
    question="How many out of how many?",
    have="A count out of a total, or a probability",
    params=(
        Param(
            "count",
            "number",
            "Give the count k (with total), or a probability in [0, 1] (without).",
            required=True,
            positional=True,
        ),
        Param("total", "int", "Give the total n that count is out of.", positional=True),
        Param(
            "units",
            "int",
            "Set how many icons stand for the whole when there is no total or it is larger.",
            default=10,
        ),
        Param("label", "string", "Say what is counted."),
    ),
    example={"count": 3, "total": 10, "label": "Runs that diverged"},
    size="m",
)
def ratio(count, total=None, *, units=10, label=None) -> Built:
    if not 2 <= units <= MAX_UNITS:
        raise ChipError(
            f"units must be between 2 and {MAX_UNITS}; got {units}.",
            fix_hint="Pass units=10 or fewer; the exact fraction stays in the value.",
        )
    if total is not None:
        if total < 1:
            raise ChipError(f"total must be at least 1; got {total}.", fix_hint=HINT)
        if not count.is_integer() or not 0 <= count <= total:
            raise ChipError(
                f"count must be a whole number from 0 to total ({total}); got {fmt.num(count)}.",
                fix_hint=HINT,
            )
        frac = count / total
    elif not 0 <= count <= 1:
        raise ChipError(
            f"without a total, count is a probability and must lie in [0, 1]; "
            f"got {fmt.num(count)}.",
            fix_hint=HINT,
        )
    else:
        frac = count

    icons = total if total is not None and total <= units else units
    exact = frac * icons
    whole = math.floor(exact + 0.5)  # half up
    partial = exact != whole and (abs(exact - whole) >= MATERIAL or whole == 0 or whole == icons)
    full = math.floor(exact) if partial else whole

    if total is not None:
        said = f"{fmt.count(count)} out of {fmt.count(total)} ({fmt.pct(frac)})"
    else:
        about = "" if exact == whole else "about "
        said = f"{fmt.pct(frac)}, {about}{whole} in {icons}"
    facts = [said]
    if icons != total:
        each = "" if total is None else f"; each icon stands for {fmt.num(total / icons)}"
        facts.append(f"drawn as {fmt.num(exact)} of {icons} icons{each}")
    warnings = []
    if partial:
        warnings.append(
            f"{fmt.pct(frac)} is {fmt.num(exact)} of {icons} icons; rounding to {whole} would "
            f"misstate it, so the boundary icon is drawn as a partial icon ({TRACK} in text, "
            "a small dot in SVG)."
        )
    name = f"{label}: " if label else ""
    return Built(
        stats={
            "value": frac,
            "count": count,
            "total": total,
            "icons": icons,
            "full": full,
            "partial": partial,
        },
        facts=facts,
        warnings=warnings,
        alt=f"{name}{said}.",
    )


# --- text -----------------------------------------------------------------------------------
@text_renderer("ratio")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    if s["total"] is None:
        value = fmt.pct(s["value"])
    else:
        value = f"{fmt.count(s['count'])}/{fmt.count(s['total'])}"
    rest = s["icons"] - s["full"] - s["partial"]
    return TextOut(value, DOT * s["full"] + TRACK * s["partial"] + HOLLOW * rest)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("ratio")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    y = c.mid
    for i in range(s["icons"]):
        x = c.left + R_RING + RING / 2 + i * PITCH
        if i < s["full"]:
            c.dot(x, y, r=R_FULL)
        elif i == s["full"] and s["partial"]:
            c.dot(x, y, r=R_PART)
        else:
            c.dot(x, y, r=R_RING, hollow=True, stroke=RING, role="context")  # the track
    c.fit()
