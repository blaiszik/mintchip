"""spark: a series as a word-sized line. The exemplar for a run-of-marks chip.

Text: ``0.42 (range 0.42 to 1.84) ▇▅▃▂▁▁▁▁▁`` (one cell per point, at most CELLS cells): the
value is the latest point, and the full form adds the series' range so a spike is in the
numbers too; compact is the bare ``0.42``. With ``vs``: ``0.42 vs 0.61 ▇▅▃▂▁▁▁ ▇▆▅▄▃▃▃``.
SVG: one ink line with an accent end point; ``vs`` in context ink; ``band`` as a context wash,
at least BAND_H tall about its true centre so a narrow band stays visible; ``reference`` as a
dashed context line.

Distortions are announced (design rule 7): a range under 2% of the level adds ``±x%`` to the
text and an axis-break mark to the SVG; a series longer than CELLS adds ``n=…`` to the text;
values outside an explicit domain become ``^``/``v`` cells and edge chevrons.
"""

from __future__ import annotations

import math

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import TRACK, TextOptions, TextOut, level
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

CELLS = 12  # most text cells per series; longer series are downsampled, keeping spikes
END_R = 2.25  # radius of the accent end point
LOW_VARIATION = 0.02  # a domain narrower than this fraction of its level is "zoomed"
BAND_H = 3.0  # least drawn height of a band, about its true centre (facts give the true bounds)


@chip(
    "spark",
    question="How did a value evolve over steps or time?",
    have="A series over time or steps",
    params=(
        Param(
            "values",
            "numbers",
            "Give the series, oldest first; None marks a gap.",
            required=True,
            positional=True,
        ),
        Param("vs", "numbers", "Give a second series over the same steps, to compare."),
        Param("band", "range", "Give a target or normal range (lo, hi), drawn as a wash."),
        Param("reference", "number", "Give a reference level, drawn as a dashed line."),
        Param("domain", "range", "Fix the y-range (lo, hi); share it so sparks compare."),
        Param("label", "string", "Say what the series measures."),
        Param("unit", "string", "Name the unit of the values."),
        Param("higher_is_better", "bool", "Declare a direction: the end point turns good/bad."),
    ),
    example={
        "values": [1.84, 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43, 0.42],
        "band": (0.38, 0.48),
    },
    size="m",
)
def spark(
    values,
    *,
    vs=None,
    band=None,
    reference=None,
    domain=None,
    label=None,
    unit=None,
    higher_is_better=None,
) -> Built:
    pts = [v for v in values if v is not None]
    if len(pts) < 2:
        raise ChipError(
            f"needs at least 2 numbers in values; got {len(pts)}.",
            fix_hint="Pass a series, e.g. mintchip.spark([0.9, 0.6, 0.4]).",
        )
    others = [v for v in (vs or []) if v is not None]
    if vs is not None and (len(vs) != len(values) or len(others) < 2):
        raise ChipError(
            f"vs must have the same length as values ({len(values)}) and 2+ numbers.",
            fix_hint="Align vs to the same steps, with None where a step is missing.",
        )
    if band is not None and band[0] == band[1]:
        raise ChipError("band must have lo < hi.", fix_hint="Use reference= for a single level.")

    drawn = pts + others + list(band or ()) + ([reference] if reference is not None else [])
    lo, hi = min(drawn), max(drawn)
    natural = (lo, hi) if hi > lo else padded(lo, hi)
    first, last = pts[0], pts[-1]
    better = None
    if higher_is_better is not None and last != first:
        better = "good" if (last > first) == higher_is_better else "bad"
    sig = _sig(pts + others)

    warnings = _cut_lines(values, vs, unit, domain or natural)
    if len(values) > CELLS:
        warnings.append(
            f"text shows {len(values)} points in {CELLS} cells, keeping each cell's most "
            f"extreme value (marked n={len(values)})."
        )

    name = f"{label}: " if label else ""
    change = fmt.num(last - first, sig=sig, signed=True, unit=unit)
    facts = [
        (
            f"{len(pts)} points, {fmt.num(first, sig=sig, unit=unit)} → "
            f"{fmt.num(last, sig=sig, unit=unit)} ({change})"
        ),
        f"range {_range((min(pts), max(pts)), unit, sig)}",
    ]
    if vs is not None:
        facts.append(f"vs series ends at {fmt.num(others[-1], sig=sig, unit=unit)}")
    if band is not None:
        where = "inside" if band[0] <= last <= band[1] else "outside"
        facts.append(f"latest value is {where} the band {_range(band, unit)}")
    if reference is not None:
        facts.append(f"reference {fmt.num(reference, unit=unit)}")
    return Built(
        stats={
            "values": values,
            "vs": vs,
            "band": band,
            "reference": reference,
            "first": first,
            "value": last,
            "last": last,
            "vs_last": others[-1] if others else None,
            "sig": sig,
            "better": better,
        },
        facts=facts,
        warnings=warnings,
        alt=f"{name}sparkline of {len(pts)} points from {fmt.num(first, sig=sig)} "
        f"to {fmt.num(last, sig=sig)}.",
        domain=natural,
    )


def _cut_lines(values, vs, unit: str | None, dom: tuple[float, float]) -> list[str]:
    """The warnings that depend on the y-scale: values it cuts, and a zoomed-in scale."""
    out = []
    cut = [v for v in [*values, *(vs or ())] if v is not None and not dom[0] <= v <= dom[1]]
    if cut:
        out.append(
            f"domain {_range(dom, unit)} cuts {len(cut)} value(s); they are pinned to the edge "
            "and marked (^ or v in text, a chevron in SVG)."
        )
    zoom = _zoom(dom)
    if zoom:
        out.append(
            f"the series spans only ±{zoom} of its level, stretched to full height "
            f"(marked ±{zoom} in text, an axis break in SVG)."
        )
    return out


@domain_warnings("spark")
def _cuts(chip: Chip, domain: tuple[float, float], own: bool) -> list[str]:
    return _cut_lines(chip.stats["values"], chip.stats["vs"], chip.unit, domain)


def _sig(values: list[float]) -> int:
    """Significant figures for the value: 3, or more when the series varies in a later digit
    (0.4200 → 0.4206 prints as 0.4206, not 0.421)."""
    spread, size = max(values) - min(values), max(abs(v) for v in values)
    if spread == 0:
        return 3
    return min(6, max(3, math.ceil(math.log10(size / spread)) + 1))


def _range(r: tuple[float, float], unit: str | None, sig: int = 3) -> str:
    return f"{fmt.num(r[0], sig=sig)} to {fmt.num(r[1], sig=sig, unit=unit)}"


def _zoom(domain: tuple[float, float]) -> str | None:
    """``"0.071%"`` when the domain is under LOW_VARIATION of its level, else None."""
    lo, hi = domain
    mid = (lo + hi) / 2
    if hi <= lo or mid == 0 or hi - lo >= LOW_VARIATION * max(abs(lo), abs(hi)):
        return None
    return fmt.pct((hi - lo) / 2 / abs(mid))


def _end_role(chip: Chip) -> str:
    return chip.stats["better"] or "accent"


# --- text -----------------------------------------------------------------------------------
@text_renderer("spark")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    lo, hi = o.domain
    dec = fmt.places(fmt.num(s["last"], sig=s["sig"]))
    fixed = o.decimals is not None and dec is not None  # scientific notation keeps its form
    dec = o.decimals if fixed else dec

    def f(v: float) -> str:
        if fixed:
            return fmt.fixed(v, dec, unit=chip.unit)
        return fmt.num(v, sig=s["sig"], unit=chip.unit)

    def _end(v: float, dec: int | None) -> str:
        """A range end: at least the value's decimals (0.4200 beside 0.4206), more if needed."""
        t = fmt.num(v, sig=s["sig"])
        shown = fmt.places(t)
        return fmt.fixed(v, dec) if dec is not None and shown is not None and shown < dec else t

    value = f(s["last"])
    if s["vs"] is not None and not o.compact:
        value += f" vs {f(s['vs_last'])}"
    elif not o.compact:  # the latest value alone would hide a spike the glyph shows
        pts = [v for v in s["values"] if v is not None]
        if min(pts) < max(pts):
            value += f" (range {_end(min(pts), dec)} to {_end(max(pts), dec)})"

    def cells(series: list[float | None]) -> str:
        out = []
        for v in downsample_minmax(series, CELLS):
            out.append(
                TRACK if v is None else "^" if v > hi else "v" if v < lo else level(v, lo, hi)
            )
        return "".join(out)

    run = cells(s["values"])
    glyph = [(run[:-1], None), (run[-1], _end_role(chip))]
    if s["vs"] is not None:
        glyph.append((" " + cells(s["vs"]), "context"))
    zoom = _zoom((lo, hi))
    if zoom:
        glyph.append((f" ±{zoom}", None))
    if len(s["values"]) > CELLS:
        glyph.append((f" n={len(s['values'])}", None))
    return TextOut(value, glyph, dec)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("spark")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    c.right -= END_R  # the end point's radius, so the chip ends a pad after it, as others do
    zoomed = _zoom(c.domain) is not None
    if zoomed:  # axis break at the left: two short slashes in the space the plot gives up
        c.left += 4
        for x in (1.0, 3.0):  # the first slash's stroke and cap stay inside x = 0
            c.line(x, c.bottom, x + 2, c.bottom - 5, role="context", width=1.25)

    def points(series: list[float | None]) -> list[tuple[float, float] | None]:
        series = downsample_minmax(series, int(2 * c.width))
        last = len(series) - 1
        xs = [c.fx(i / last) for i in range(len(series))]
        return [None if v is None else (x, c.y(v, at=x)) for x, v in zip(xs, series, strict=True)]

    if s["band"] is not None:  # a band is context, not data: trim it to the domain, no chevron
        lo, hi = max(s["band"][0], c.domain[0]), min(s["band"][1], c.domain[1])
        if lo < hi:
            top, bottom = c.y(hi), c.y(lo)
            narrow = bottom - top < BAND_H
            if narrow:  # a given band is always visible: widen it about its true centre
                mid = (top + bottom) / 2
                top, bottom = max(mid - BAND_H / 2, 0.5), min(mid + BAND_H / 2, c.height - 0.5)
            c.rect(c.left, top, c.right - c.left, bottom - top, role="context", narrow=narrow)
    if s["reference"] is not None and c.contains(s["reference"]):
        y = c.y(s["reference"])
        c.line(c.left, y, c.right, y, role="context", dash=(2, 1.5))
    if s["vs"] is not None:
        c.path(points(s["vs"]), role="context")
    line = points(s["values"])
    c.path(line)
    end = next(p for p in reversed(line) if p is not None)
    c.dot(
        *end, r=END_R, role=_end_role(chip), title=fmt.num(s["last"], sig=s["sig"], unit=chip.unit)
    )
