"""funnel: counts through stages.

Text prints the counts and the overall retention and no glyph (design rule 6):
``1,200 → 520 → 350 → 290 (24%)``; compact keeps the first and last stage,
``1,200 → 290 (24%)``. A stage larger than the one before is announced, not hidden: it is
marked ``!`` in text (and compact falls back to the full line), drawn as an outlined bar in SVG,
and named in ``warnings``.

SVG: one bar per stage on a zero baseline, heights linear in the count. The stage after the
steepest drop, the largest fraction lost from one stage to the next, is in accent.
"""

from __future__ import annotations

import itertools

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import TextOptions, TextOut
from ..spec import Built, Chip, ChipError, Param, chip, svg_renderer, text_renderer

_HINT = (
    'Pass 2+ stages with counts, first > 0, e.g. mintchip.funnel({"visited": 1200, "paid": 290}).'
)


@chip(
    "funnel",
    question="How many make it through each stage?",
    have="Counts through ordered stages",
    params=(
        Param(
            "stages",
            "mapping",
            "Give the stages in order, name → count.",
            required=True,
            positional=True,
        ),
        Param("label", "string", "Say what flows through the stages."),
    ),
    example={"stages": {"visited": 1200, "signed up": 520, "activated": 350, "retained": 290}},
    size="m",
)
def funnel(stages, *, label=None) -> Built:
    if len(stages) < 2:
        raise ChipError(f"needs at least 2 stages; got {len(stages)}.", fix_hint=_HINT)
    for name, n in stages.items():
        if isinstance(n, tuple) or n < 0:
            raise ChipError(
                f"stage {name!r} must be a count of zero or more; got {n!r}.", fix_hint=_HINT
            )
    names, counts = list(stages), list(stages.values())
    if counts[0] <= 0:
        raise ChipError(f"the first stage {names[0]!r} must be positive.", fix_hint=_HINT)

    kept = [b / a if a else None for a, b in itertools.pairwise(counts)]  # stage conversion
    losses = [(1 - k, i + 1) for i, k in enumerate(kept) if k is not None and k < 1]
    steepest = max(losses)[1] if losses else None
    rises = [i for i in range(1, len(counts)) if counts[i] > counts[i - 1]]
    s = {
        "value": counts[-1] / counts[0],
        "names": names,
        "counts": counts,
        "retention": counts[-1] / counts[0],
        "steepest": steepest,
        "rises": rises,
        "whole": all(float(n).is_integer() for n in counts),
    }

    warnings = [
        f"stage {names[i]!r} ({_c(s, counts[i])}) is larger than {names[i - 1]!r} "
        f"({_c(s, counts[i - 1])}); marked ! in text and outlined in SVG."
        for i in rises
    ]
    facts = [f"{len(counts)} stages, {fmt.pct(s['retention'])} of {names[0]} reach {names[-1]}"]
    if steepest is not None:
        a, b = steepest - 1, steepest
        facts.append(
            f"steepest drop: {names[a]} → {names[b]}, {fmt.pct(1 - kept[a])} lost "
            f"({_c(s, counts[a] - counts[b])})"
        )
    facts.append("stage conversion " + ", ".join("—" if k is None else fmt.pct(k) for k in kept))
    alt = f"funnel of {len(counts)} stages from {_c(s, counts[0])} to {_c(s, counts[-1])}, "
    alt += f"{fmt.pct(s['retention'])} retained"
    return Built(
        stats=s,
        facts=facts,
        warnings=warnings,
        alt=f"{label}: {alt}." if label else f"{alt[0].upper()}{alt[1:]}.",
    )


def _c(s: dict, n: float) -> str:
    return fmt.count(n) if s["whole"] else fmt.num(n)


# --- text -----------------------------------------------------------------------------------
@text_renderer("funnel")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    shown = [_c(s, n) + ("!" if i in s["rises"] else "") for i, n in enumerate(s["counts"])]
    if o.compact and not s["rises"]:
        shown = [shown[0], shown[-1]]
    return TextOut(f"{' → '.join(shown)} ({fmt.pct(s['retention'])})")


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("funnel")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    counts = s["counts"]
    top = max(counts)
    slot = (c.right - c.left) / len(counts)
    gap = min(2.0, slot * 0.3)
    w = slot - gap
    for i, (name, n) in enumerate(zip(s["names"], counts, strict=True)):
        x = c.left + i * slot + gap / 2
        tip = f"{name}: {_c(s, n)} ({fmt.pct(n / counts[0])})"
        if n == 0:  # nothing left: a context floor, so the stage is still seen
            c.line(x, c.bottom, x + w, c.bottom, role="context", title=tip)
            continue
        h = max(c.bottom - c.fy(n / top), 1.5)
        y = c.bottom - h
        if i in s["rises"]:  # announced distortion: an outlined bar
            pts = [(x + 0.75, c.bottom), (x + 0.75, y + 0.75), (x + w - 0.75, y + 0.75),
                   (x + w - 0.75, c.bottom)]  # fmt: skip
            c.path(pts, width=1.5, title=tip)
            continue
        c.rect(x, y, w, h, role="accent" if i == s["steepest"] else "ink", title=tip)
