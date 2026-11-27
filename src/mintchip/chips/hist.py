"""hist: a miniature inline histogram showing skew and modality of raw numeric samples.

Text: ``med 20.5 ms (n=8, 18 to 31) ▅█▃·▃··▃`` (compact drops the parenthesis): one spark-bar
height cell (``▁▂▃▄▅▆▇█``) per bin, ``·`` for empty bins, optional ``│`` for an empty reference
bin.
SVG: crisp zero-baseline miniature vertical bars (modal bin highlighted in accent, others in ink)
standing on a context baseline, plus an optional dashed vertical reference tick.
"""

from __future__ import annotations

import itertools
import math

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import (
    REF,
    TRACK,
    Segment,
    TextOptions,
    TextOut,
    braille_cell,
    braille_level_mask,
    level,
)
from ..scales import padded, quantile
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

MIN_BINS = 2
MAX_BINS = 24
MIN_BAR_H = 1.5
BASE_Y = 13.5


@chip(
    "hist",
    question="What is the shape, skew or modality of a sample?",
    have="Sample shape (histogram)",
    params=(
        Param(
            "samples",
            "numbers",
            "Give the raw numeric samples; None or NaN is skipped.",
            required=True,
            positional=True,
        ),
        Param(
            "bins",
            "int",
            "Number of equal-width bins (2 to 24).",
            default=8,
        ),
        Param("reference", "number", "Give a reference value, drawn as a vertical tick."),
        Param("label", "string", "Say what was sampled."),
        Param("unit", "string", "Name the unit of the samples."),
    ),
    example={"samples": [18, 19, 20, 20, 21, 22, 26, 31], "unit": "ms", "label": "Latency"},
    size="m",
)
def hist(samples, *, bins=8, reference=None, label=None, unit=None) -> Built:
    xs = sorted(v for v in samples if v is not None)
    missing = len(samples) - len(xs)
    if len(xs) < 2:
        raise ChipError(
            f"needs at least 2 numbers in samples; got {len(xs)}.",
            fix_hint="Pass raw numeric samples, e.g. mintchip.hist([18, 19, 20, 21, 26]).",
        )
    if not MIN_BINS <= bins <= MAX_BINS:
        raise ChipError(
            f"bins must be between {MIN_BINS} and {MAX_BINS}; got {bins}.",
            fix_hint=f"Pass bins=8 (between {MIN_BINS} and {MAX_BINS}).",
        )

    n = len(xs)
    q1, med, q3 = (quantile(xs, q) for q in (0.25, 0.5, 0.75))
    mean = math.fsum(xs) / n
    var = math.fsum((v - mean) ** 2 for v in xs) / n
    sd = math.sqrt(var)
    skew = (math.fsum(((v - mean) / sd) ** 3 for v in xs) / n) if sd > 0 else 0.0

    drawn = [xs[0], xs[-1]] + ([reference] if reference is not None else [])
    d_lo, d_hi = min(drawn), max(drawn)
    natural = (d_lo, d_hi) if d_hi > d_lo else padded(d_lo, d_hi)

    counts, edges = _bin(xs, natural, bins)
    peak = max(counts)
    modal_i = counts.index(peak)
    bimodal = _is_bimodal(counts)
    sig = _sig(xs[0], xs[-1])

    def f(v: float, u: str | None = None) -> str:
        return fmt.num(v, sig=sig, unit=u)

    skew_desc = (
        "bimodal"
        if bimodal
        else "roughly symmetric"
        if abs(skew) < 0.3
        else "right-skewed"
        if skew > 0
        else "left-skewed"
    )

    warnings: list[str] = []
    if missing:
        warnings.append(f"{missing} missing sample(s) skipped; n={n} counts the rest.")

    facts = [
        f"n={n}, median {f(med, unit)}, range {f(xs[0])} to {f(xs[-1], unit)}",
        (
            f"modal bin {f(edges[modal_i])} to {f(edges[modal_i + 1], unit)} "
            f"({counts[modal_i]} of {n}, {fmt.pct(counts[modal_i] / n)})"
        ),
        f"spread: IQR {f(q1)} to {f(q3, unit)}, {skew_desc} (skew {fmt.num(skew, sig=2, signed=True)})",
    ]
    if reference is not None:
        facts.append(f"reference {f(reference, unit)}")

    name = f"{label}: " if label else ""
    alt = f"{name}histogram of {n} samples ({bins} bins), median {f(med, unit)}, {skew_desc}."
    return Built(
        stats={
            "samples": xs,
            "bins": bins,
            "counts": counts,
            "edges": edges,
            "n": n,
            "value": med,
            "median": med,
            "mean": mean,
            "sd": sd,
            "skew": skew,
            "skew_desc": skew_desc,
            "bimodal": bimodal,
            "modal_bin": (edges[modal_i], edges[modal_i + 1]),
            "modal_count": counts[modal_i],
            "q1": q1,
            "q3": q3,
            "min": xs[0],
            "max": xs[-1],
            "reference": reference,
            "missing": missing,
            "sig": sig,
        },
        facts=facts,
        warnings=warnings,
        alt=alt,
        domain=natural,
    )


def _sig(lo: float, hi: float) -> int:
    spread, size = hi - lo, max(abs(lo), abs(hi))
    if spread <= 0 or size == 0:
        return 3
    return min(6, max(3, math.ceil(math.log10(size / spread)) + 1))


def _bin(xs: list[float], domain: tuple[float, float], bins: int) -> tuple[list[int], list[float]]:
    lo, hi = domain
    span = hi - lo
    step = span / bins
    edges = [lo + i * step for i in range(bins + 1)]
    counts = [0] * bins
    for v in xs:
        if lo <= v <= hi:
            idx = min(bins - 1, int((v - lo) / span * bins))
            counts[idx] += 1
    return counts, edges


def _is_bimodal(counts: list[int]) -> bool:
    """Detect two distinct peaks separated by a clear valley."""
    if len(counts) < 3:
        return False
    peak = max(counts)
    if peak < 2:
        return False
    maxima = []
    for i, c in enumerate(counts):
        left = counts[i - 1] if i > 0 else -1
        right = counts[i + 1] if i < len(counts) - 1 else -1
        if c >= 0.4 * peak and c >= left and c >= right and (c > left or c > right):
            maxima.append(i)
    if len(maxima) < 2:
        return False
    for a, b in itertools.pairwise(maxima):
        if b - a >= 2:
            valley = min(counts[a + 1 : b])
            if valley <= 0.6 * min(counts[a], counts[b]):
                return True
    return False


def _cut_lines(s: dict, unit: str | None, dom: tuple[float, float]) -> list[str]:
    cut = [v for v in s["samples"] if not dom[0] <= v <= dom[1]]
    if not cut:
        return []
    return [
        (
            f"domain {fmt.num(dom[0])} to {fmt.num(dom[1], unit=unit)} cuts {len(cut)} sample(s); "
            "cut sides are marked (< or > in text, a chevron in SVG)."
        )
    ]


@domain_warnings("hist")
def _cuts(chip: Chip, domain: tuple[float, float], own: bool) -> list[str]:
    return _cut_lines(chip.stats, chip.unit, domain)


# --- text -----------------------------------------------------------------------------------
@text_renderer("hist")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    sig = s["sig"]
    dec = fmt.places(fmt.num(s["median"], sig=sig))
    fixed = o.decimals is not None and dec is not None
    dec = o.decimals if fixed else dec

    def f(v: float, u: str | None = None) -> str:
        if fixed:
            return fmt.fixed(v, dec, unit=u)
        return fmt.num(v, sig=sig, unit=u)

    value = f"med {f(s['median'], chip.unit)}"
    if not o.compact:
        value += f" (n={s['n']}, {f(s['min'])} to {f(s['max'])})"

    lo, hi = o.domain
    counts, _ = _bin(s["samples"], (lo, hi), s["bins"])
    peak = max(counts) if any(counts) else 1

    cells: list[Segment] = []
    ref = s["reference"]
    if o.braille and not o.ascii:
        r_idx = (
            min(s["bins"] - 1, int((ref - lo) / (hi - lo) * s["bins"]))
            if ref is not None and lo <= ref <= hi
            else -1
        )
        for i in range(0, len(counts), 2):
            k0 = counts[i]
            k1 = counts[i + 1] if i + 1 < len(counts) else 0
            ref_here = r_idx in (i, i + 1)
            if k0 == 0 and k1 == 0:
                cells.append((REF if ref_here else braille_cell(0), "context"))
                continue
            h0 = max(1, min(4, round(k0 / peak * 4))) if k0 > 0 else 0
            h1 = max(1, min(4, round(k1 / peak * 4))) if k1 > 0 else 0
            mask = braille_level_mask(0, h0) | braille_level_mask(1, h1)
            role = "accent" if (k0 == peak or k1 == peak) else None
            if ref_here and r_idx == i:
                cells.append((REF, "context"))
                cells.append((braille_cell(mask), role))
            elif ref_here and r_idx == i + 1:
                cells.append((braille_cell(mask), role))
                cells.append((REF, "context"))
            else:
                cells.append((braille_cell(mask), role))
    else:
        for k in counts:
            if k == 0:
                cells.append((TRACK, "context"))
            else:
                role = "accent" if k == peak else None
                cells.append((level(k, 0, peak), role))

        if ref is not None and lo <= ref <= hi:
            r_idx = min(s["bins"] - 1, int((ref - lo) / (hi - lo) * s["bins"]))
            if counts[r_idx] == 0:
                cells[r_idx] = (REF, "context")

    below = any(v < lo for v in s["samples"])
    above = any(v > hi for v in s["samples"])
    glyph: list[Segment] = []
    if below:
        glyph.append(("<", None))
    for ch, role in cells:
        if glyph and glyph[-1][1] == role:
            glyph[-1] = (glyph[-1][0] + ch, role)
        else:
            glyph.append((ch, role))
    if above:
        glyph.append((">", None))
    return TextOut(value, glyph, dec)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("hist")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    lo, hi = c.domain
    below = any(v < lo for v in s["samples"])
    above = any(v > hi for v in s["samples"])
    if below:
        c.left += 5.0
    if above:
        c.right -= 5.0

    counts, edges = _bin(s["samples"], (lo, hi), s["bins"])
    peak = max(counts) if any(counts) else 0
    n = s["n"]
    bins = s["bins"]

    # Crisp zero-baseline across the full plot width.
    c.line(c.left, BASE_Y, c.right, BASE_Y, role="context", width=1.25)

    ref = s["reference"]
    if ref is not None and c.contains(ref):
        rx = c.x(ref)
        c.line(
            rx,
            1.5,
            rx,
            BASE_Y,
            role="context",
            dash=(2, 1.5),
            width=1.25,
            title=f"reference {fmt.num(ref, sig=s['sig'], unit=chip.unit)}",
        )

    plot_w = c.right - c.left
    gap = 1.0 if plot_w / bins >= 4.0 else 0.5
    bar_w = (plot_w - gap * (bins - 1)) / bins
    y_floor = BASE_Y - 0.75
    max_h = y_floor - c.top

    if peak > 0:
        for i, k in enumerate(counts):
            if k == 0:
                continue
            h = max(MIN_BAR_H, (k / peak) * max_h)
            x = c.left + i * (bar_w + gap)
            role = "accent" if k == peak else "ink"
            tip = (
                f"{fmt.num(edges[i], sig=s['sig'])} to "
                f"{fmt.num(edges[i + 1], sig=s['sig'], unit=chip.unit)}: "
                f"{k} ({fmt.pct(k / n)})"
            )
            c.rect(x, y_floor - h, bar_w, h, role=role, title=tip)

    if below:
        c.chevron("left")
    if above:
        c.chevron("right")
