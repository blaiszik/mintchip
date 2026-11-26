"""bar: a value against a total, as a bullet bar on a context track.

Text: ``82% (target 90%) ██████▌│`` (compact drops the parenthesis): CELLS cells in eighths, the
rest of the track as ``·``, an unmet target as ``│`` on the track. A value above the total
fills the track and gains a ``+``: ``140% ████████+``, never a silent clip.
SVG: a context wash for the track (0 to total), an ink bar, and ink strokes: the target as a
tick across the track, the baseline as a short notch hanging under it (one kind of mark, told
apart by where it sits), and a chevron after the bar when the value overflows the total; only
then does the chip grow past the track, by ROOM, so the scale itself never moves.
"""

from __future__ import annotations

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
    own_scale,
    svg_renderer,
    text_renderer,
)

CELLS = 8
OVER = "+"  # appended to the text cells when the value exceeds the total or the domain
ROOM = 5.0  # width added after the track for an overflow chevron; the scale never moves
EDGE = 0.01  # a share this close to 0 or to the whole (but not on it) prints one decimal


@chip(
    "bar",
    question="How much of a total, budget or capacity is used?",
    have="A value against a total",
    params=(
        Param("value", "number", "Give the amount, 0 or more.", required=True, positional=True),
        Param(
            "total",
            "number",
            "Give the whole the value is measured against.",
            positional=True,
            default=1.0,
        ),
        Param(
            "baseline",
            "number",
            "Give an earlier or comparison value, drawn as a notch under the track.",
        ),
        Param("target", "number", "Give a goal, drawn as a tick across the track."),
        Param("label", "string", "Say what is measured."),
        Param("unit", "string", "Name the unit of value and total."),
    ),
    example={"value": 0.82, "target": 0.9, "label": "Test coverage"},
    size="m",
)
def bar(value, total=1.0, *, baseline=None, target=None, label=None, unit=None) -> Built:
    if total <= 0:
        raise ChipError(
            f"total must be positive; got {fmt.num(total)}.",
            fix_hint="Pass the whole as total, e.g. mintchip.bar(412, 500).",
        )
    if value < 0:
        raise ChipError(
            f"value must be 0 or more; got {fmt.num(value)}.",
            fix_hint="A bar starts at zero; for a signed change use mintchip.delta.",
        )
    for name, v in (("baseline", baseline), ("target", target)):
        if v is not None and not 0 <= v <= total:
            raise ChipError(
                f"{name} {fmt.num(v)} must lie between 0 and the total {fmt.num(total)}.",
                fix_hint=f"Pass {name}= on the same scale as value, at most total.",
            )
    pct_mode = (unit is None and total == 1) or (unit == "%" and total == 100)
    s = {
        "value": value,
        "total": total,
        "frac": value / total,
        "baseline": baseline,
        "target": target,
        "pct_mode": pct_mode,
        "over": value > total,
    }
    f = _formatter(s, unit)
    share = _pct(s["frac"])

    warnings = []
    if s["over"]:
        of = "the total" if pct_mode else f"the total {f(total)} ({share})"
        warnings.append(
            f"value {f(value)} exceeds {of}; the bar fills the track and is marked {OVER} "
            "in text and by a chevron in SVG."
        )

    def diff(d: float, signed: bool = False) -> str:
        if pct_mode:
            return fmt.pct(d / total, signed=signed).removesuffix("%") + " points"
        return fmt.num(d, signed=signed, unit=unit)

    facts = [f"{share} of the whole" if pct_mode else f"{share} of the total"]
    if baseline is not None:
        facts.append(f"{diff(value - baseline, True)} vs baseline {f(baseline)}")
    if target is not None:
        met = value >= target
        facts.append(
            f"meets the target {f(target)}"
            if met
            else f"{diff(target - value)} short of the target {f(target)}"
        )
    name = f"{label}: " if label else ""
    return Built(
        stats=s,
        facts=facts,
        warnings=warnings,
        alt=f"{name}{fmt.num(value, unit=unit)} of {fmt.num(total, unit=unit)} ({share}).",
        domain=(0.0, total),
    )


def _pct(frac: float, dec: int | None = None) -> str:
    """A share of the total as a percentage. Within EDGE of 0 or of the total, but not on it,
    one decimal at least (``99.5%``, not ``99%`` beside a true ``100%``), and more where needed:
    a share that is not exactly 0 or 1 never prints as ``0%`` or ``100%``."""
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
    """Percent of the total in percent mode, else the number with its unit; ``dec`` fixes the
    decimal places (of the percentage in percent mode)."""
    if s["pct_mode"]:
        return lambda v: _pct(v / s["total"], dec)
    if dec is not None:
        return lambda v: fmt.fixed(v, dec, unit=unit)
    return lambda v: fmt.num(v, unit=unit)


@domain_warnings("bar")
def _cuts(chip: Chip, domain: tuple[float, float], own: bool) -> list[str]:
    """A scale that ends before the value cuts the bar (a value over the total already warns)."""
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
@text_renderer("bar")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    f = _formatter(s, chip.unit)
    own = f(s["value"]) if s["pct_mode"] else fmt.num(s["value"])
    dec = fmt.places(own) if o.decimals is None or fmt.places(own) is None else o.decimals
    if s["pct_mode"]:
        value = own if o.decimals is None else _formatter(s, None, dec)(s["value"])
        notes = []
    else:
        num = _formatter(s, None, None if o.decimals is None else dec)
        value = f"{num(s['value'])}/{fmt.with_unit(num(s['total']), chip.unit)}"
        notes = [_pct(s["frac"])]
    if not o.compact:
        notes += [f"{k} {f(s[k])}" for k in ("baseline", "target") if s[k] is not None]
        if notes:
            value += f" ({', '.join(notes)})"

    lo, hi = o.domain
    scale = CELLS / (hi - lo)
    cells = max(0.0, min(s["value"], hi) - lo) * scale
    # ASCII has no eighths (▌ would become a "|" that reads as a tick): round to whole cells.
    fill = "█" * round(cells) if o.ascii else hbar(cells)
    end = round(max(0.0, min(s["total"], hi) - lo) * scale)
    track = [TRACK] * max(0, end - len(fill))
    t = s["target"]
    if t is not None and lo <= t <= hi:
        i = min(CELLS - 1, int((t - lo) * scale)) - len(fill)
        if 0 <= i < len(track):  # an unmet target shows on the track; a met one is covered
            track[i] = REF
    glyph: list[Segment] = [(fill, None), ("".join(track), "context")]
    if s["value"] > min(s["total"], hi):
        glyph.append((OVER, None))
    return TextOut(value, [g for g in glyph if g[0]], dec)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("bar")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    lo, hi = c.domain
    if s["value"] > min(s["total"], hi):  # room for the overflow chevron, after the track
        c.width += ROOM
    v = min(s["value"], hi)
    x0 = c.left
    c.rect(x0, 4, c.x(min(s["total"], hi)) - x0, 8, role="context")
    title = _formatter(s, chip.unit)(s["value"])
    if v > lo:
        c.rect(x0, 5.5, c.x(v) - x0, 5, role="ink", title=title)
    b, t = s["baseline"], s["target"]
    if b is not None and c.contains(b):  # a notch hanging under the track, like an axis tick
        x = c.x(b)
        c.line(x, 12, x, 15, title=f"baseline {_formatter(s, chip.unit)(b)}")
    if t is not None and c.contains(t):
        x = c.x(t)
        c.line(x, 2, x, 14, title=f"target {_formatter(s, chip.unit)(t)}")
    if s["value"] > min(s["total"], hi):  # overflow: a chevron just past the bar's end
        x = max(c.x(v), x0) + 1.5
        y = c.mid
        c.path([(x, y - 3), (x + 2.5, y), (x, y + 3)], width=1.25, title=f"over: {title}")


# A bar is a share of its own total: siblings keep their own scales unless the totals agree.
own_scale("bar")
