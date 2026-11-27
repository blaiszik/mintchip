"""share: parts of a whole, as one run of ink in opacity steps, largest first by default.

Text: ``62·28·10% ██████▏███▏█``: the parts' percentages, then CELLS cells split among them,
separated by thin gaps. SVG: one bar of segments in ink at falling opacity, with gaps.
Never categorical colours, never textures.

``sort=False`` keeps the caller's order instead, and the opacity steps follow position, so in
a table column of rows with the same parts each part has the same place and shade in every row
(``mintchip.table`` does this by itself when the rows' part names agree).

At most MAX_SEGMENTS segments: with more parts than that, the first MAX_SEGMENTS − 1 (the
largest, or the first given with ``sort=False``) are shown and the rest are folded into one
"other" segment, drawn last and announced as ``other=N`` after the glyph. A part too small to
earn a cell gets one half-height cell (``▄``) taken from the largest part, and a warning.
"""

from __future__ import annotations

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import GAP, TextOptions, TextOut, cell_counts
from ..spec import Built, Chip, ChipError, Param, chip, svg_renderer, text_renderer

CELLS = 12  # total text-bar width (block cells + separator gaps)
MAX_SEGMENTS = 4  # beyond this, opacity steps stop reading at 1x
OPACITY = (1.0, 0.66, 0.44, 0.28)  # segment i's ink opacity, by position
SMALL = "▄"  # a part under one cell, drawn as a half-height cell
BAR = (4.0, 8.0)  # SVG bar top and height
GAP_W = 1.5  # SVG gap between segments
MIN_W = 1.5  # SVG minimum segment width
HINT = 'Pass sizes by name, e.g. mintchip.share({"code": 62, "docs": 28, "tests": 10}).'


@chip(
    "share",
    question="How is a whole split into parts?",
    have="Parts of a whole",
    params=(
        Param(
            "parts",
            "mapping",
            "Give each part's size by name; they are shown as shares of their sum.",
            required=True,
            positional=True,
        ),
        Param(
            "sort",
            "bool",
            "Order parts largest first; False keeps your order, so rows of a table compare.",
            default=True,
        ),
        Param("label", "string", "Say what the whole is."),
        Param("unit", "string", "Name the unit of the part sizes."),
    ),
    example={"parts": {"code": 62, "docs": 28, "tests": 10}, "label": "Changed lines"},
    size="m",
)
def share(parts, *, sort=True, label=None, unit=None) -> Built:
    if not parts:
        raise ChipError("needs at least 1 part; got none.", fix_hint=HINT)
    for name, v in parts.items():
        if isinstance(v, tuple):
            raise ChipError(
                f"part {name!r} must be one size; got the pair {v}.",
                fix_hint="Pass one number per part; (start, end) spans belong to timeline.",
            )
        if v <= 0:
            raise ChipError(
                f"part {name!r} must be positive; got {fmt.num(v)}.",
                fix_hint="Leave out parts of size 0; a share is a positive size.",
            )
    total = sum(parts.values())
    ranked = list(parts.items())
    if sort:
        ranked.sort(key=lambda kv: -kv[1])  # stable: ties keep their order
    folded = 0
    if len(ranked) > MAX_SEGMENTS:
        rest = ranked[MAX_SEGMENTS - 1 :]
        folded = len(rest)
        ranked = [*ranked[: MAX_SEGMENTS - 1], ("other", sum(v for _, v in rest))]
    names = [n for n, _ in ranked]
    sizes = [v for _, v in ranked]
    fracs = [v / total for v in sizes]
    block_cells = CELLS - (len(fracs) - 1)
    cells, small = cell_counts(fracs, block_cells)

    warnings = []
    if folded:
        warnings.append(
            f"{folded} parts beyond the {'largest' if sort else 'first'} {MAX_SEGMENTS - 1} are "
            f"folded into one 'other' segment ({fmt.pct(fracs[-1])}), drawn last (marked other={folded})."
        )
    for i in (i for i, s in enumerate(small) if s):
        warnings.append(
            f"{_who(names, i, folded)} ({fmt.pct(fracs[i])}) is under one text cell of "
            f"{block_cells}; it is drawn as one half-height cell ({SMALL}) taken from the largest part."
        )

    facts = [
        f"{_who(names, i, folded)} {fmt.num(v, unit=unit)} ({fmt.pct(f)})"
        for i, (v, f) in enumerate(zip(sizes, fracs, strict=True))
    ]
    facts.append(f"total {fmt.num(total, unit=unit)}")
    name = f"{label}: " if label else ""
    split = ", ".join(f"{_who(names, i, folded)} {fmt.pct(f)}" for i, f in enumerate(fracs))
    return Built(
        stats={
            "value": fracs[0],
            "names": names,
            "sizes": sizes,
            "fracs": fracs,
            "cells": cells,
            "small": small,
            "folded": folded,
            "total": total,
        },
        facts=facts,
        warnings=warnings,
        alt=f"{name}{len(parts)} parts of a whole: {split}.",
    )


def _who(names: list[str], i: int, folded: int) -> str:
    if folded and i == len(names) - 1:
        return f"other ({folded} parts)"
    return names[i]


def _pct(f: float) -> str:
    return fmt.pct(f)[:-1]


# --- text -----------------------------------------------------------------------------------
@text_renderer("share")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    sep = "/" if o.ascii else "·"  # "62.28.10%" would read as one decimal number
    value = sep.join(_pct(f) for f in s["fracs"]) + "%"
    glyph: list[tuple[str, str | None]] = []
    last = len(s["cells"]) - 1
    for i, (n, small) in enumerate(zip(s["cells"], s["small"], strict=True)):
        if i:
            glyph.append((GAP, None))
        role = "context" if s["folded"] and i == last else None
        glyph.append((SMALL if small else "█" * n, role))
    if s["folded"]:
        glyph.append((f" other={s['folded']}", None))
    return TextOut(value, glyph)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("share")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    fracs = s["fracs"]
    room = c.right - c.left - GAP_W * (len(fracs) - 1)
    widths = [max(MIN_W, f * room) for f in fracs]
    big = widths.index(max(widths))
    widths[big] -= sum(widths) - room  # a part lifted to MIN_W is paid for by the largest
    x = c.left
    for i, (w, f) in enumerate(zip(widths, fracs, strict=True)):
        name = _who(s["names"], i, s["folded"])
        tip = f"{name}: {fmt.num(s['sizes'][i], unit=chip.unit)} ({fmt.pct(f)})"
        c.rect(x, BAR[0], w, BAR[1], role="ink", opacity=OPACITY[i], title=tip)
        x += w + GAP_W
