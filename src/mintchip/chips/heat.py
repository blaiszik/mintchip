"""heat: a single-row word-sized heatmap strip across ordered slots.

Text: ``12 to 95 ms ░░▓█▓░``: min-to-max summary plus one density shade cell (``░▒▓█``) per slot,
with ``·`` for missing gaps. Longer strips than CELLS downsample while preserving extremes and add
``n=…``.
SVG: a crisp row of equal-width rectangles at 1em height with graduated opacity on the accent role
(zero external dependencies), with faint baseline ticks for gaps. Supports ``shared_domain``.
"""

from __future__ import annotations

import math

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import (
    SHADES,
    TRACK,
    Segment,
    TextOptions,
    TextOut,
    braille_cell,
    braille_level_mask,
)
from ..scales import downsample_minmax, padded
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

CELLS = 24  # enough for a full 24-hour strip or 12-month strip with no downsampling
MIN_CELL_W = 1.75  # minimum SVG rectangle width before downsampling
BAR_TOP = 2.5
BAR_H = 11.0


@chip(
    "heat",
    question="How does intensity vary across ordered slots?",
    have="Intensity across slots",
    params=(
        Param(
            "values",
            "numbers",
            "Give the slot values in order; None or NaN marks a gap.",
            required=True,
            positional=True,
        ),
        Param("labels", "strings", "Name each slot, in the same order as values."),
        Param("label", "string", "Say what the heatmap measures."),
        Param("unit", "string", "Name the unit of the values."),
    ),
    example={"values": [12, 24, 68, 95, 78, 30, 15], "unit": "ms", "label": "Hourly p95"},
    size="m",
)
def heat(values, *, labels=None, label=None, unit=None) -> Built:
    pts = [v for v in values if v is not None]
    missing = len(values) - len(pts)
    if len(pts) < 2:
        raise ChipError(
            f"needs at least 2 numbers in values; got {len(pts)}.",
            fix_hint="Pass a series of slot values, e.g. mintchip.heat([12, 40, 95, 30]).",
        )
    if labels is not None and len(labels) != len(values):
        raise ChipError(
            f"labels has {len(labels)} entries but values has {len(values)}.",
            fix_hint="Pass exactly one label per value, in the same order.",
        )

    lo, hi = min(pts), max(pts)
    mean = math.fsum(pts) / len(pts)
    natural = (lo, hi) if hi > lo else padded(lo, hi)
    sig = _sig(pts)

    peak_i = max((i for i, v in enumerate(values) if v is not None), key=lambda i: values[i])
    low_i = min((i for i, v in enumerate(values) if v is not None), key=lambda i: values[i])

    def slot(i: int) -> str:
        return labels[i] if labels is not None else f"slot {i + 1}"

    warnings: list[str] = []
    if missing:
        warnings.append(f"{missing} missing slot(s) shown as gaps.")
    if len(values) > CELLS:
        warnings.append(
            f"text shows {len(values)} slots in {CELLS} cells, keeping each cell's most "
            f"extreme value (marked n={len(values)})."
        )

    def f(v: float, u: str | None = None) -> str:
        return fmt.num(v, sig=sig, unit=u)

    facts = [
        f"{len(pts)} slots, range {f(lo)} to {f(hi, unit)}, mean {f(mean, unit)}",
        f"peak at {slot(peak_i)} ({f(hi, unit)}), lowest at {slot(low_i)} ({f(lo, unit)})",
    ]
    name = f"{label}: " if label else ""
    alt = f"{name}heatmap of {len(values)} slots from {f(lo)} to {f(hi, unit)}."
    return Built(
        stats={
            "values": values,
            "labels": labels,
            "min": lo,
            "max": hi,
            "mean": mean,
            "value": hi,
            "peak_index": peak_i,
            "min_index": low_i,
            "missing": missing,
            "sig": sig,
        },
        facts=facts,
        warnings=warnings,
        alt=alt,
        domain=natural,
    )


def _sig(values: list[float]) -> int:
    spread, size = max(values) - min(values), max(abs(v) for v in values)
    if spread == 0 or size == 0:
        return 3
    return min(6, max(3, math.ceil(math.log10(size / spread)) + 1))


def _cut_lines(values: list[float | None], unit: str | None, dom: tuple[float, float]) -> list[str]:
    cut = [v for v in values if v is not None and not dom[0] <= v <= dom[1]]
    if not cut:
        return []
    return [
        (
            f"domain {fmt.num(dom[0])} to {fmt.num(dom[1], unit=unit)} cuts {len(cut)} value(s); "
            "out-of-range cells are clamped to the extreme shade."
        )
    ]


@domain_warnings("heat")
def _cuts(chip: Chip, domain: tuple[float, float], own: bool) -> list[str]:
    return _cut_lines(chip.stats["values"], chip.unit, domain)


def _shade(v: float, lo: float, hi: float) -> tuple[str, str]:
    t = 0.5 if hi <= lo else min(1.0, max(0.0, (v - lo) / (hi - lo)))
    idx = min(3, max(0, round(t * 3)))
    return SHADES[idx], f"ramp:{t:.3f}"


# --- text -----------------------------------------------------------------------------------
@text_renderer("heat")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    sig = s["sig"]
    lo_val, hi_val = s["min"], s["max"]
    dec = fmt.places(fmt.num(hi_val, sig=sig))
    fixed = o.decimals is not None and dec is not None
    dec = o.decimals if fixed else dec

    def f(v: float, u: str | None = None) -> str:
        if fixed:
            return fmt.fixed(v, dec, unit=u)
        return fmt.num(v, sig=sig, unit=u)

    if lo_val < hi_val:
        value = f"{f(lo_val)} to {f(hi_val, chip.unit)}"
    else:
        value = f(lo_val, chip.unit)

    d_lo, d_hi = o.domain
    glyph: list[Segment] = []
    if o.braille and not o.ascii:
        braille_slots = CELLS * 2
        sampled = downsample_minmax(s["values"], braille_slots)
        for i in range(0, len(sampled), 2):
            v0 = sampled[i]
            v1 = sampled[i + 1] if i + 1 < len(sampled) else None
            if v0 is None and v1 is None:
                ch, role = TRACK, "context"
            else:
                mask = 0
                ts: list[float] = []
                for col, v in ((0, v0), (1, v1)):
                    if v is None:
                        continue
                    t = 0.5 if d_hi <= d_lo else min(1.0, max(0.0, (v - d_lo) / (d_hi - d_lo)))
                    ts.append(t)
                    h = min(4, max(1, round(t * 3) + 1))
                    mask |= braille_level_mask(col, h)
                ch = braille_cell(mask)
                role = f"ramp24:{max(ts):.3f}"
            if glyph and glyph[-1][1] == role:
                glyph[-1] = (glyph[-1][0] + ch, role)
            else:
                glyph.append((ch, role))
        if len(s["values"]) > braille_slots:
            glyph.append((f" n={len(s['values'])}", None))
        return TextOut(value, glyph, dec)

    sampled = downsample_minmax(s["values"], CELLS)
    for v in sampled:
        ch, role = (TRACK, "context") if v is None else _shade(v, d_lo, d_hi)
        if glyph and glyph[-1][1] == role:
            glyph[-1] = (glyph[-1][0] + ch, role)
        else:
            glyph.append((ch, role))
    if len(s["values"]) > CELLS:
        glyph.append((f" n={len(s['values'])}", None))
    return TextOut(value, glyph, dec)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("heat")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    lo, hi = c.domain
    vals = s["values"]
    labels = s["labels"]
    plot_w = c.right - c.left
    max_cells = max(2, int(plot_w / MIN_CELL_W))
    if len(vals) > max_cells:
        drawn = downsample_minmax(vals, max_cells)
        slot_names = [f"bucket {i + 1}" for i in range(len(drawn))]
    else:
        drawn = list(vals)
        slot_names = (
            list(labels) if labels is not None else [f"slot {i + 1}" for i in range(len(drawn))]
        )

    n = len(drawn)
    step = plot_w / n
    gap = 0.75 if step >= 4.0 else (0.5 if step >= 2.5 else 0.0)
    cell_w = (plot_w - gap * (n - 1)) / n

    for i, (v, name) in enumerate(zip(drawn, slot_names, strict=True)):
        x = c.left + i * (cell_w + gap)
        if v is None:
            c.rect(x, 7.25, cell_w, 1.5, role="context", narrow=True, title=f"{name}: missing")
            continue
        t = 0.5 if hi <= lo else min(1.0, max(0.0, (v - lo) / (hi - lo)))
        opacity = round(0.2 + 0.8 * t, 2)
        tip = f"{name}: {fmt.num(v, sig=s['sig'], unit=chip.unit)}"
        c.rect(x, BAR_TOP, cell_w, BAR_H, role="accent", opacity=opacity, title=tip)
