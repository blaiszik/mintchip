"""dist: raw samples as a word-sized distribution, with outliers kept off the scale.

Text: ``med 20.3 ms (n=10, IQR 19.9 to 21.4) [▃▃▃█·▃▃··▃]→47.8``; compact drops the
parenthesis. One histogram cell per tenth of the domain, ``·`` where a cell is empty.
With ``threshold=`` the value is the exceedance probability, ``P>25 ms 15% (3 of 20)``, and a
``│`` is inserted at the threshold.

SVG: for n ≤ DOTS a rug, one ink tick per sample (samples too close to tell apart share one
tick, as much wider as they are many), with the median as an accent dot under it; above DOTS a
quantile dotplot of DOTS dots (each dot is 1/DOTS of the samples), stacked from the floor, which
shows where samples pile up better than a rug of that many ticks would at 1×. Threshold as a
context line, with the marks above it in accent (and no median dot: the value is then the
share above); reference as a dashed context line.

Outliers beyond FENCE × IQR do not stretch the scale (v0.1 let one 47.8 squeeze ten points
into a blob). They lie outside the natural domain, so both renderers clip them to an edge
marker: ``→47.8`` in text, a chevron in SVG, and a line in ``warnings``.
"""

from __future__ import annotations

import math

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import REF, TRACK, Segment, TextOptions, TextOut, level
from ..scales import padded, quantile, robust_extent
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

CELLS = 10  # text histogram cells across the domain
DOTS = 20  # raw dots up to this many samples; above, this many quantile dots
FENCE = 3.0  # samples beyond FENCE × IQR from the quartiles are outliers
PAD = 0.06  # natural domain margin, as a fraction of the drawn extent
R = 1.75  # dot radius
PITCH = 2 * R + 0.5  # dots closer than this share a stack
WEIGHT = 1.5  # rug tick width per sample it stands for
TICK_MAX = 4.5  # widest rug tick (three or more samples in one place)
TICK_PITCH = 2.5  # rug ticks whose centres are closer than this merge into one, wider
RUG = (2.0, 10.5)  # rug tick top and bottom, leaving room under it for the median
MEDIAN_Y = 13.75  # the median: an accent dot under the rug, on the text baseline
EDGE = 6.0  # plot inset on a clipped side, room for the chevron


@chip(
    "dist",
    question="How are the samples spread, and are there outliers?",
    have="Raw samples of one measurement",
    params=(
        Param(
            "samples",
            "numbers",
            "Give the raw samples; None or NaN is skipped and counted.",
            required=True,
            positional=True,
        ),
        Param("threshold", "number", "Give a cutoff; the value becomes P(sample > cutoff)."),
        Param("reference", "number", "Give a reference value, drawn as a dashed line."),
        Param("domain", "range", "Fix the x-range (lo, hi); share it so dist chips compare."),
        Param("label", "string", "Say what was sampled."),
        Param("unit", "string", "Name the unit of the samples."),
    ),
    example={
        "samples": [18.9, 19.4, 19.8, 20.1, 20.3, 20.3, 20.9, 21.6, 22.8, 47.8],
        "unit": "ms",
        "label": "Request latency",
    },
    size="m",
)
def dist(
    samples,
    *,
    threshold=None,
    reference=None,
    domain=None,
    label=None,
    unit=None,
) -> Built:
    xs = sorted(v for v in samples if v is not None)
    missing = len(samples) - len(xs)
    if len(xs) < 2:
        raise ChipError(
            f"needs at least 2 numbers in samples; got {len(xs)}.",
            fix_hint="Pass the raw observations, e.g. mintchip.dist([19.8, 20.3, 21.1, 47.8]).",
        )
    n = len(xs)
    q1, med, q3 = (quantile(xs, q) for q in (0.25, 0.5, 0.75))
    core = robust_extent(xs, FENCE)
    outliers = [v for v in xs if not core[0] <= v <= core[1]]
    drawn = [*core] + [v for v in (threshold, reference) if v is not None]
    natural = padded(min(drawn), max(drawn), PAD)
    sig = _sig(q1, q3) if q3 > q1 else _sig(xs[0], xs[-1])
    dec = _decimals([q1, med, q3], sig, q3 - q1 if q3 > q1 else xs[-1] - xs[0])
    s = {
        "n": n,
        "samples": xs,
        "quantiles": [quantile(xs, (k + 0.5) / DOTS) for k in range(DOTS)] if n > DOTS else None,
        "median": med,
        "q1": q1,
        "q3": q3,
        "min": xs[0],
        "max": xs[-1],
        "mean": math.fsum(xs) / n,
        "outliers": outliers,
        "threshold": threshold,
        "reference": reference,
        "above": None,
        "p": None,
        "sig": sig,
        "dec": dec,
        "missing": missing,
    }
    if threshold is not None:
        s["above"] = sum(v > threshold for v in xs)
        s["p"] = s["above"] / n
    s["value"] = s["p"] if threshold is not None else med

    def f(v: float, u: str | None = None) -> str:
        return _f(s, v, u)

    def far(v: float) -> str:
        return fmt.num(v, sig=sig)

    warnings = []
    if missing:
        warnings.append(f"{missing} missing sample(s) skipped; n={n} counts the rest.")
    warnings += _cut_lines(s, unit, domain or natural, domain is None)

    name = f"{label}: " if label else ""
    facts = [
        f"n={n}, median {f(med, unit)}, IQR {f(q1)} to {f(q3, unit)}",
        f"range {f(xs[0])} to {f(xs[-1], unit)}",
    ]
    if outliers:
        facts.append(f"{len(outliers)} outlier(s) beyond {FENCE:g}×IQR: {_list(outliers, far)}")
    alt = f"{name}distribution of {n} samples, median {f(med, unit)}"
    if threshold is not None:
        share, cut_at = fmt.pct(s["p"]), fmt.num(threshold, sig=sig, unit=unit)
        facts.append(f"{s['above']} of {n} samples above {cut_at} ({share})")
        alt += f", {share} above {cut_at}"
    if reference is not None:
        facts.append(f"reference {fmt.num(reference, sig=sig, unit=unit)}")
    return Built(stats=s, facts=facts, warnings=warnings, alt=alt + ".", domain=natural)


def _cut_lines(s: dict, unit: str | None, dom: tuple[float, float], own: bool) -> list[str]:
    cut = [v for v in s["samples"] if not dom[0] <= v <= dom[1]]
    if not cut:
        return []
    what = f"{len(cut)} sample(s) ({_list(cut, lambda v: fmt.num(v, sig=s['sig']))})"
    why = (
        f"{what} beyond {FENCE:g}×IQR clipped so they do not flatten the scale"
        if own
        else f"domain {fmt.num(dom[0])} to {fmt.num(dom[1], unit=unit)} cuts {what}"
    )
    return [
        (
            f"{why}; their values are printed past the brackets in text and a chevron marks "
            "the edge in SVG."
        )
    ]


@domain_warnings("dist")
def _cuts(chip: Chip, domain: tuple[float, float], own: bool) -> list[str]:
    return _cut_lines(chip.stats, chip.unit, domain, own)


def _sig(lo: float, hi: float) -> int:
    """Significant figures that resolve the spread: 3, or more for a narrow spread at a high
    level (1000.2 to 1000.6 prints as 1000.4, not 1,000)."""
    spread, size = hi - lo, max(abs(lo), abs(hi))
    if spread <= 0 or size == 0:
        return 3
    return min(6, max(3, math.ceil(math.log10(size / spread)) + 1))


def _decimals(values: list[float], sig: int, width: float) -> int | None:
    """One decimal place for every number in a dist, so 17.0 and 23.9 line up: what ``sig``
    figures give, or more when rounding would move a quartile by over 3% of ``width`` (the
    IQR); None when a value needs scientific notation."""
    places = []
    for v in values:
        t = fmt.num(v, sig=sig)
        if "e" in t:
            return None
        places.append(len(t.split(".")[1]) if "." in t else 0)
    return max(*places, fmt.resolving(values, width))


def _f(s: dict, v: float, unit: str | None = None, dec: int | None = None) -> str:
    dec = s["dec"] if dec is None else dec
    if dec is None:
        return fmt.num(v, sig=s["sig"], unit=unit)
    return fmt.fixed(v, dec, unit=unit)


def _list(values: list[float], f) -> str:
    shown = ", ".join(f(v) for v in values[:3])
    return shown + (f" and {len(values) - 3} more" if len(values) > 3 else "")


def _clip_text(values: list[float], f) -> str:
    """The clipped samples on one side: the one value, or nearest..farthest."""
    if len(values) == 1:
        return f(values[0])
    return f"{f(values[0])}..{f(values[-1])}"


# --- text -----------------------------------------------------------------------------------
@text_renderer("dist")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    dec = s["dec"] if o.decimals is None or s["dec"] is None else o.decimals

    def f(v: float, u: str | None = None) -> str:
        return _f(s, v, u, dec)

    t = s["threshold"]
    if t is not None:
        value = f"P>{fmt.num(t, sig=s['sig'], unit=chip.unit)} {fmt.pct(s['p'])}"
        if not o.compact:
            value += f" ({s['above']} of {s['n']})"
    else:
        value = f"med {f(s['median'], chip.unit)}"
        if not o.compact:
            value += f" (n={s['n']}, IQR {f(s['q1'])} to {f(s['q3'])})"

    lo, hi = o.domain
    xs = s["samples"]
    counts = [0] * CELLS
    for v in xs:
        if lo <= v <= hi:
            counts[min(CELLS - 1, int((v - lo) / (hi - lo) * CELLS))] += 1
    peak = max(counts)
    cells: list[Segment] = [(level(k, 0, peak) if k else TRACK, None) for k in counts]
    ref = s["reference"]
    if ref is not None and lo <= ref <= hi:
        i = min(CELLS - 1, int((ref - lo) / (hi - lo) * CELLS))
        if not counts[i]:  # data wins over context, as in ci
            cells[i] = (REF, "context")
    if t is not None and lo <= t <= hi:
        b = round((t - lo) / (hi - lo) * CELLS)
        tail = [(ch, "accent" if role is None else role) for ch, role in cells[b:]]
        cells = [*cells[:b], (REF, "context"), *tail]

    below = [v for v in xs if v < lo]
    above = [v for v in xs if v > hi]

    def far(v: float) -> str:  # clipped values sit far from the core: no shared decimals
        return fmt.num(v, sig=s["sig"])

    glyph: list[Segment] = []
    if below:
        glyph.append((f"{_clip_text(below[::-1], far)}→", None))
    glyph += [("[", None), *cells, ("]", None)]
    if above:
        glyph.append((f"→{_clip_text(above, far)}", None))
    shown = None if t is not None else dec if dec is not None else fmt.places(value)
    return TextOut(value, _merge(glyph), shown)


def _merge(segs: list[Segment]) -> list[Segment]:
    out: list[Segment] = []
    for text, role in segs:
        if out and out[-1][1] == role:
            out[-1] = (out[-1][0] + text, role)
        else:
            out.append((text, role))
    return out


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("dist")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    lo, hi = c.domain
    xs = s["samples"]
    below = [v for v in xs if v < lo]
    above = [v for v in xs if v > hi]
    if below:
        c.left += EDGE
    if above:
        c.right -= EDGE

    t, ref = s["threshold"], s["reference"]
    if ref is not None and c.contains(ref):
        x = c.x(ref)
        c.line(x, 1.5, x, 14.5, role="context", dash=(2, 1.5))
    if t is not None and c.contains(t):
        x = c.x(t)
        c.line(x, 1.5, x, 14.5, role="context")

    if s["quantiles"] is None:
        _rug(chip, c, [v for v in xs if lo <= v <= hi])
    else:
        _dotplot(c, [v for v in s["quantiles"] if lo <= v <= hi], t)

    if below:
        far = fmt.num(below[0], sig=s["sig"], unit=chip.unit)
        _chevron(c, c.left - R - 1.25, -1, f"{len(below)} below the scale, to {far}")
    if above:
        far = fmt.num(above[-1], sig=s["sig"], unit=chip.unit)
        _chevron(c, c.right + R + 1.25, 1, f"{len(above)} above the scale, to {far}")


def _rug(chip: Chip, c: Canvas, pts: list[float]) -> None:
    """One ink tick per sample; samples closer than TICK_PITCH share one tick at their mean,
    as wide as their count (WEIGHT per sample, at most TICK_MAX), so a tie reads as two.
    With a threshold the ticks past it are accent; without, an accent dot under the rug marks
    the median, the number the value prints."""
    s, t = chip.stats, chip.stats["threshold"]
    groups = [g for side in _sides(pts, t) for g in _groups(c, side, TICK_PITCH)]
    for x, members in groups:
        role = "accent" if t is not None and members[0] > t else "ink"
        k, a, b = len(members), members[0], members[-1]
        title = _f(s, a, chip.unit)
        if k > 1:
            title = f"{title} ×{k}" if a == b else f"{_f(s, a)} to {_f(s, b, chip.unit)} ({k})"
        w = min(WEIGHT * k, TICK_MAX)
        inset = (w - WEIGHT) / 2  # round caps: a heavier tick keeps the same visible length
        c.line(x, RUG[0] + inset, x, RUG[1] - inset, role=role, width=w, title=title)
    if t is None and c.contains(s["median"]):
        x = c.x(s["median"])
        tip = f"median {_f(s, s['median'], chip.unit)}"
        c.dot(x, MEDIAN_Y, r=R, role="accent", title=tip)


def _sides(pts: list[float], t: float | None) -> list[list[float]]:
    return [pts] if t is None else [[v for v in pts if v <= t], [v for v in pts if v > t]]


def _groups(c: Canvas, values: list[float], pitch: float) -> list[tuple[float, list[float]]]:
    """A value within ``pitch`` of its group's first value joins that group; the group sits at
    the mean x of its members."""
    groups: list[tuple[float, list[float], list[float]]] = []
    for v in sorted(values):
        x = c.x(v)
        if groups and x - groups[-1][0] < pitch:
            groups[-1][1].append(x)
            groups[-1][2].append(v)
        else:
            groups.append((x, [x], [v]))
    return [(sum(px) / len(px), vs) for _, px, vs in groups]


def _dotplot(c: Canvas, pts: list[float], t: float | None) -> None:
    """DOTS quantile dots (each 1/DOTS of the samples), stacked from the floor."""
    stacks = _spread([g for side in _sides(pts, t) for g in _groups(c, side, PITCH)],
                     c.left, c.right)  # fmt: skip
    tallest = max((len(m) for _, m in stacks), default=1)
    dy = 2 * R + 0.25 if tallest <= 3 else (c.bottom - c.top - 2 * R) / (tallest - 1)
    for x, members in stacks:
        for i, v in enumerate(members):
            role = "accent" if t is not None and v > t else "ink"
            c.dot(x, c.bottom - R - i * dy, r=R, role=role)


def _spread(stacks: list[tuple[float, list[float]]], left: float, right: float):
    """Push stacks apart to at least PITCH, then back inside [left, right]."""
    xs = [x for x, _ in stacks]
    for i in range(1, len(xs)):
        xs[i] = max(xs[i], xs[i - 1] + PITCH)
    if xs and xs[-1] > right:
        xs[-1] = right
        for i in range(len(xs) - 2, -1, -1):
            xs[i] = min(xs[i], xs[i + 1] - PITCH)
    xs = [max(x, left) for x in xs]
    return [(x, m) for x, (_, m) in zip(xs, stacks, strict=True)]


def _chevron(c: Canvas, x: float, d: int, title: str) -> None:
    """An edge marker for clipped samples: an arrowhead pointing off the plot, its back at
    ``x`` and its tip 2.5 units further in direction ``d`` (-1 left, 1 right)."""
    y = c.mid
    c.path([(x, y - 3), (x + 2.5 * d, y), (x, y + 3)], width=1.25, title=title)
