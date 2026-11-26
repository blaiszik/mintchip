"""rank: a position in a field, as ``rank(position, total)`` or from ``values=`` and ``value=``.

Text: ``#2/18 [········●·]``; from values, ``#2/5 (0.85) [·······●··]`` (compact drops the
parenthesis). SVG: one context ruler with end ticks and one ink dot. The best end is always
the right, and the facts say so.

Two rulers, one per way of calling it:
- ``rank(position, total)``: the ruler is the order of the field, last place at the left and #1
  at the right. It is a fixed scale, so every rank chip already compares; ``domain`` is None and
  a render-time ``domain=`` is ignored.
- ``rank(values=..., value=...)``: the ruler is the value axis over the field's extent
  (``chip.domain``), so the gap to the leader shows. With ``higher_is_better=False`` the axis
  runs high to low, so the best (lowest) value is still at the right. A render-time
  ``domain=`` puts several fields on one value scale.
"""

from __future__ import annotations

import math

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import DOT, TextOptions, TextOut, Track
from ..scales import padded
from ..spec import Built, Chip, ChipError, Param, chip, domain_warnings, svg_renderer, text_renderer

CELLS = 10
_HINT = "Call mintchip.rank(2, 18) or mintchip.rank(values=scores, value=0.88)."


@chip(
    "rank",
    question="Where does one item stand in its field?",
    have="A position in a ranked field",
    params=(
        Param("position", "int", "Give the 1-based rank, 1 being best.", positional=True),
        Param("total", "int", "Give the size of the field.", positional=True),
        Param("values", "numbers", "Give the field's values, to rank value among them."),
        Param("value", "number", "Give the value to rank within values."),
        Param(
            "higher_is_better",
            "bool",
            "Say whether a higher value ranks first (values= only).",
            default=True,
        ),
        Param("label", "string", "Say what is ranked."),
    ),
    example={"position": 2, "total": 18, "label": "Leaderboard"},
    size="m",
)
def rank(
    position=None,
    total=None,
    *,
    values=None,
    value=None,
    higher_is_better=True,
    label=None,
) -> Built:
    by_position = position is not None or total is not None
    by_value = values is not None or value is not None
    if by_position == by_value:
        raise ChipError(
            "needs either (position, total) or (values=, value=), "
            + ("not both." if by_position else "and got neither."),
            fix_hint=_HINT,
        )
    warnings: list[str] = []
    facts: list[str] = []
    if by_position:
        if position is None or total is None:
            raise ChipError("needs both position and total.", fix_hint=_HINT)
        if total < 1 or not 1 <= position <= total:
            raise ChipError(
                f"position must be between 1 and total; got {position} of {total}.",
                fix_hint="Pass a 1-based rank, e.g. mintchip.rank(2, 18).",
            )
        if not higher_is_better:
            raise ChipError(
                "higher_is_better applies only to values=; position 1 is always best.",
                fix_hint="Drop higher_is_better, or rank from values= and value=.",
            )
        score, domain, ties = None, None, 0
        facts.append("right end is best (#1); left end is last")
    else:
        if values is None or value is None:
            raise ChipError("needs both values= and value=.", fix_hint=_HINT)
        field = [v for v in values if v is not None]
        if not any(math.isclose(v, value, rel_tol=1e-9, abs_tol=1e-12) for v in field):
            field.append(value)
            warnings.append(
                f"value {fmt.num(value)} is not in values; ranked as an extra entry "
                f"(field of {len(field)})."
            )
        if len(field) < 2:
            raise ChipError(
                f"needs a field of at least 2 values; got {len(field)}.",
                fix_hint="Pass the whole field, e.g. values=[0.72, 0.81, 0.88].",
            )
        ahead = [v for v in field if (v > value if higher_is_better else v < value)]
        same = [v for v in field if math.isclose(v, value, rel_tol=1e-9, abs_tol=1e-12)]
        position, total, score, ties = len(ahead) + 1, len(field), value, len(same) - 1
        lo, hi = min(field), max(field)
        domain = (lo, hi) if hi > lo else padded(lo, hi)
        ends = (lo, hi) if higher_is_better else (hi, lo)
        facts.append(
            f"right end is best ({'highest' if higher_is_better else 'lowest'} value); "
            f"ruler runs {fmt.num(ends[0])} to {fmt.num(ends[1])}"
        )
        if ties:
            facts.append(f"tied with {ties} other(s) at #{position}")
    s = {
        "value": float(position),
        "position": position,
        "total": total,
        "frac": 1.0 if total == 1 else (total - position) / (total - 1),
        "score": score,
        "higher_is_better": higher_is_better,
    }
    behind = total - position - ties
    facts.insert(0, f"{position - 1} ahead, {behind} behind" if total > 1 else "alone in the field")
    alt = f"rank {position} of {total}"
    return Built(
        stats=s,
        facts=facts,
        warnings=warnings,
        alt=f"{label}: {alt}." if label else f"{alt[0].upper()}{alt[1:]}.",
        domain=domain,
    )


@domain_warnings("rank")
def _cuts(chip: Chip, domain: tuple[float, float], own: bool) -> list[str]:
    """A ruler that ends before the score (ranked by value) cuts it."""
    score = chip.stats["score"]
    if score is None or domain[0] <= score <= domain[1]:
        return []
    return [
        (
            f"domain {fmt.num(domain[0])} to {fmt.num(domain[1])} cuts the value {fmt.num(score)}; "
            "it is pinned to the end of the ruler and marked (< or > in text, a chevron in SVG)."
        )
    ]


# --- text -----------------------------------------------------------------------------------
@text_renderer("rank")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    value = f"#{s['position']}/{s['total']}"
    if s["score"] is None:
        t = Track(CELLS, (0.0, 1.0))
        t.put(s["frac"], DOT)
    else:
        if not o.compact:
            value += f" ({fmt.num(s['score'])})"
        t = Track(CELLS, o.domain)
        t.put(_onto(s, o.domain), DOT)
    return TextOut(value, t.glyph())


def _onto(s: dict, domain: tuple[float, float]) -> float:
    """The score's place on the ruler: mirrored within the domain when lower is better, so
    the best end is always the right."""
    lo, hi = domain
    return s["score"] if s["higher_is_better"] else lo + hi - s["score"]


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("rank")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    y = c.mid
    c.line(c.left, y, c.right, y, role="context")
    for x in (c.left, c.right):  # the ruler's two ends: the field's extent
        c.line(x, y - 2.5, x, y + 2.5, role="context", width=1.25)
    if s["score"] is None:
        x, tip = c.fx(s["frac"]), f"#{s['position']} of {s['total']}"
    else:
        x = c.x(_onto(s, c.domain))
        tip = f"#{s['position']} of {s['total']}: {fmt.num(s['score'])}"
    c.dot(x, y, r=2.75, title=tip)
