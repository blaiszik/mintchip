"""bullet: Stephen Few inline bullet graph — value vs target on qualitative range bands.

Text: ``82% (target 90%) ██████▌│`` (compact drops the parenthesis): CELLS cells in eighths for
the actual value, shaded qualitative range bands (``▒``, ``░``, ``·``) on the unfilled track, and
``│`` for an unmet target. A value past the scale maximum appends ``+``, never a silent clip.
SVG: layered context washes from dark to light for qualitative bands, a bold accent actual bar
centred vertically inside the bands, and a crisp ink target tick across the track; overflows add
ROOM past the track for a chevron without shifting the scale.
"""

from __future__ import annotations

import itertools

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import REF, TRACK, Segment, TextOptions, TextOut, hbar
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

CELLS = 8
OVER = "+"
ROOM = 5.0
EDGE = 0.01
DEFAULT_BANDS = (0.6, 0.85, 1.0)
BAND_NAMES_3 = ("low", "mid", "high")
BAND_GLYPHS = ("▒", "░", TRACK)


@chip(
    "bullet",
    question="How does a value compare against its target and qualitative bands?",
    have="A value against target & bands",
    params=(
        Param("value", "number", "Give the actual value, 0 or more.", required=True, positional=True),
        Param(
            "target",
            "number",
            "Give the positive target value, drawn as a tick across the track.",
            required=True,
            positional=True,
        ),
        Param(
            "ranges",
            "numbers",
            "Give qualitative band upper bounds in ascending order (default: 60%, 85%, 100%).",
        ),
        Param(
            "total",
            "number",
            "Give the scale maximum; defaults to the highest band, target or value.",
        ),
        Param("label", "string", "Say what is measured."),
        Param("unit", "string", "Name the unit of value, target and ranges."),
    ),
    example={"value": 0.82, "target": 0.9, "label": "SLA attainment"},
    size="m",
)
def bullet(value, target, *, ranges=None, total=None, label=None, unit=None) -> Built:
    if value < 0:
        raise ChipError(
            f"value must be 0 or more; got {fmt.num(value)}.",
            fix_hint="A bullet graph starts at zero; for a signed change use mintchip.delta.",
        )
    if target <= 0:
        raise ChipError(
            f"target must be positive; got {fmt.num(target)}.",
            fix_hint="Pass a positive target on the same scale as value, e.g. mintchip.bullet(0.82, 0.9).",
        )
    if total is not None and total <= 0:
        raise ChipError(
            f"total must be positive; got {fmt.num(total)}.",
            fix_hint="Pass the scale maximum as total, e.g. mintchip.bullet(82, 90, total=100).",
        )

    if ranges is not None:
        if any(r is None for r in ranges):
            raise ChipError(
                "ranges cannot contain missing values.",
                fix_hint="Pass ascending positive upper bounds, e.g. ranges=[0.6, 0.85, 1.0].",
            )
        if not 1 <= len(ranges) <= 5:
            raise ChipError(
                f"ranges must have between 1 and 5 thresholds; got {len(ranges)}.",
                fix_hint="Pass 2 to 4 ascending thresholds, e.g. ranges=[0.6, 0.85, 1.0].",
            )
        if ranges[0] <= 0 or any(b <= a for a, b in itertools.pairwise(ranges)):
            raise ChipError(
                "ranges must be positive and strictly ascending.",
                fix_hint="Order thresholds from lowest to highest, e.g. ranges=[0.6, 0.85, 1.0].",
            )
        if total is not None and ranges[-1] > total:
            raise ChipError(
                f"highest range {fmt.num(ranges[-1])} exceeds total {fmt.num(total)}.",
                fix_hint="Pass total at least as large as the highest range, or omit total.",
            )
        scale_max = float(total) if total is not None else float(max(ranges[-1], target))
        bands = [float(r) for r in ranges]
        if bands[-1] < scale_max:
            bands.append(scale_max)
    else:
        if total is not None:
            scale_max = float(total)
        elif unit is None and target <= 1.0:
            scale_max = 1.0
        elif unit == "%" and target <= 100.0:
            scale_max = 100.0
        else:
            scale_max = max(value, target) * 1.25
        bands = [scale_max * frac for frac in DEFAULT_BANDS]

    if total is not None and target > total:
        raise ChipError(
            f"target {fmt.num(target)} exceeds total {fmt.num(total)}.",
            fix_hint="Pass target at most total, or raise total.",
        )

    pct_mode = (unit is None and scale_max == 1.0) or (unit == "%" and scale_max == 100.0)
    over = value > scale_max
    band_idx, band_name, band_lo, band_hi = _classify_band(value, bands)

    s = {
        "value": value,
        "target": target,
        "ranges": bands,
        "total": scale_max,
        "frac": value / scale_max,
        "target_pct": value / target,
        "band_index": band_idx,
        "band": band_name,
        "pct_mode": pct_mode,
        "over": over,
    }
    f = _formatter(s, unit)

    warnings = []
    if over:
        of = "the scale" if pct_mode else f"the scale maximum {f(scale_max)}"
        warnings.append(
            f"value {f(value)} exceeds {of}; the bar fills the track and is marked {OVER} "
            "in text and by a chevron in SVG."
        )

    def diff(d: float) -> str:
        if pct_mode:
            return fmt.pct(d / scale_max).removesuffix("%") + " points"
        return fmt.num(d, unit=unit)

    met = value >= target
    target_fact = (
        f"{fmt.pct(value / target)} of target {f(target)} (meets target)"
        if met
        else f"{fmt.pct(value / target)} of target {f(target)} ({diff(target - value)} short)"
    )
    if band_hi is None:
        band_fact = f"above top band ({f(band_lo)})"
    else:
        band_fact = f"in {band_name} band ({f(band_lo)} to {f(band_hi)})"
    facts = [target_fact, band_fact]
    if not pct_mode:
        facts.append(f"{_pct(s['frac'])} of scale {f(scale_max)}")

    name = f"{label}: " if label else ""
    alt = f"{name}{f(value)} against target {f(target)} ({fmt.pct(value / target)} of target, {band_name} band)."
    return Built(
        stats=s,
        facts=facts,
        warnings=warnings,
        alt=alt,
        domain=(0.0, scale_max),
    )


def _classify_band(value: float, bands: list[float]) -> tuple[int, str, float, float | None]:
    lo = 0.0
    for i, hi in enumerate(bands):
        if value <= hi:
            name = BAND_NAMES_3[i] if len(bands) == 3 else f"band {i + 1}/{len(bands)}"
            return i, name, lo, hi
        lo = hi
    return len(bands), "above top", bands[-1], None


def _pct(frac: float, dec: int | None = None) -> str:
    near = 0 < frac <= EDGE or 1 - EDGE <= frac < 1
    if dec is None and not near:
        return fmt.pct(frac)
    places = max(dec or 0, 1 if near else 0)
    out = fmt.pct(frac, decimals=places)
    while frac != 0 and not float(out.rstrip("%").replace(",", "")) and places < 6:
        places += 1
        out = fmt.pct(frac, decimals=places)
    return out


def _formatter(s: dict, unit: str | None, dec: int | None = None):
    if s["pct_mode"]:
        return lambda v: _pct(v / s["total"], dec)
    if dec is not None:
        return lambda v: fmt.fixed(v, dec, unit=unit)
    return lambda v: fmt.num(v, unit=unit)


def _band_char(mid_val: float, bands: list[float]) -> str:
    for i, hi in enumerate(bands):
        if mid_val <= hi:
            return BAND_GLYPHS[min(i, len(BAND_GLYPHS) - 1)]
    return TRACK


@domain_warnings("bullet")
def _cuts(chip: Chip, domain: tuple[float, float], own: bool) -> list[str]:
    s, (lo, hi) = chip.stats, domain
    if lo <= s["value"] <= hi or s["over"]:
        return []
    f = _formatter(s, chip.unit)
    how = (
        f"it fills the track and is marked {OVER} in text and by a chevron in SVG"
        if s["value"] > hi
        else "the bar is empty"
    )
    return [f"domain {f(lo)} to {f(hi)} cuts the bar at {f(s['value'])}; {how}."]


# --- text -----------------------------------------------------------------------------------
@text_renderer("bullet")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    f = _formatter(s, chip.unit)
    own = f(s["value"]) if s["pct_mode"] else fmt.num(s["value"])
    dec = fmt.places(own) if o.decimals is None or fmt.places(own) is None else o.decimals
    if s["pct_mode"]:
        value = own if o.decimals is None else _formatter(s, None, dec)(s["value"])
    else:
        num = _formatter(s, chip.unit, None if o.decimals is None else dec)
        value = num(s["value"])
    if not o.compact:
        value += f" (target {f(s['target'])})"

    lo, hi = o.domain
    span = hi - lo
    scale = CELLS / span
    cells = max(0.0, min(s["value"], hi) - lo) * scale
    fill = "█" * round(cells) if o.ascii else hbar(cells)
    end = round(max(0.0, min(s["total"], hi) - lo) * scale)
    track_len = max(0, end - len(fill))
    track_segs: list[Segment] = []
    t = s["target"]
    t_idx = min(CELLS - 1, int((t - lo) * scale)) if lo <= t <= hi else -1

    for offset in range(track_len):
        cell_i = len(fill) + offset
        if cell_i == t_idx:
            track_segs.append((REF, None))
        else:
            mid_val = lo + (cell_i + 0.5) / scale
            ch = _band_char(mid_val, s["ranges"])
            track_segs.append((ch, "context"))

    glyph: list[Segment] = []
    if fill:
        glyph.append((fill, "accent"))
    for ch, role in track_segs:
        if glyph and glyph[-1][1] == role:
            glyph[-1] = (glyph[-1][0] + ch, role)
        else:
            glyph.append((ch, role))
    if s["value"] > min(s["total"], hi):
        glyph.append((OVER, None))
    return TextOut(value, glyph, dec)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("bullet")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    lo, hi = c.domain
    f = _formatter(s, chip.unit)
    if s["value"] > min(s["total"], hi):
        c.width += ROOM

    x0 = c.left
    bands = s["ranges"]
    # Draw qualitative bands widest to narrowest: alpha stacking yields dark→medium→light washes.
    prev_lo = 0.0
    band_info: list[tuple[float, float, str]] = []
    for i, r in enumerate(bands):
        bname = BAND_NAMES_3[i] if len(bands) == 3 else f"band {i + 1}/{len(bands)}"
        band_info.append((prev_lo, r, bname))
        prev_lo = r
    for b_lo, b_hi, bname in reversed(band_info):
        clipped = min(b_hi, hi)
        if clipped > lo:
            tip = f"{bname} band: {f(b_lo)} to {f(b_hi)}"
            c.rect(x0, 3.0, c.x(clipped) - x0, 10.0, role="context", title=tip)

    v = min(s["value"], hi)
    title = f"value {f(s['value'])} ({fmt.pct(s['target_pct'])} of target)"
    if v > lo:
        c.rect(x0, 5.5, c.x(v) - x0, 5.0, role="accent", title=title)

    t = s["target"]
    if c.contains(t):
        x = c.x(t)
        c.line(x, 2.0, x, 14.0, role="ink", width=1.75, title=f"target {f(t)}")

    if s["value"] > min(s["total"], hi):
        x = max(c.x(v), x0) + 1.5
        y = c.mid
        c.path([(x, y - 3), (x + 2.5, y), (x, y + 3)], width=1.25, title=f"over: {f(s['value'])}")
