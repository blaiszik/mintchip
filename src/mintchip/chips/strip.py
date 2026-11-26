"""strip: pass / warn / fail / skip per item, readable without colour.

Text: ``5/8 pass (1 fail, 1 warn, 1 skip) ███▄█×█·``; compact drops the parenthesis. The
denominator is every item given, skipped ones included. The glyph carries the state (pass full
``█``, warn half ``▄``, fail ``×``, skip a dot ``·``) and colour repeats it (good / warn / bad,
skip in context ink). More than CELLS items are bucketed, each cell showing
its bucket's worst state, and the text gains ``n=…``.
SVG: one cell per item at the same four heights, the canvas cut to fit them; skip is a hollow
context ring.

There is no numeric heat-strip mode: heights here mean states, so numbers drawn as heights would
read as states (a ▄ would be a warning). A series of numbers is a spark.
"""

from __future__ import annotations

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import TRACK, Segment, TextOptions, TextOut
from ..spec import Built, Chip, ChipError, Param, chip, svg_renderer, text_renderer

CELLS = 20  # most cells; longer strips are bucketed by worst state
TOKENS = {
    "pass": ("pass", "passed", "ok", "true", "yes", "good", "success"),
    "warn": ("warn", "warning", "flaky", "partial"),
    "fail": ("fail", "failed", "failure", "error", "false", "no", "bad"),
    "skip": ("skip", "skipped", "na", "n/a", "none", "missing", "pending"),
}
STATE = {tok: state for state, toks in TOKENS.items() for tok in toks}
GLYPH = {"pass": "█", "warn": "▄", "fail": "×", "skip": TRACK}  # × is x in ASCII
ROLE = {"pass": "good", "warn": "warn", "fail": "bad", "skip": "context"}
WORST = {"skip": 0, "pass": 1, "warn": 2, "fail": 3}
HEIGHT = {"pass": 11.0, "warn": 5.5, "fail": 2.0}  # viewBox units, standing on the floor
PITCH = 8.0  # widest cell pitch (8 items fill size m); more items compress it


@chip(
    "strip",
    question="Which items passed, warned, failed or were skipped?",
    have="A pass/warn/fail/skip result per item",
    params=(
        Param(
            "values",
            "values",
            "Give one result per item: True/False, 'pass', 'warn', 'fail', 'skip' or None.",
            required=True,
            positional=True,
        ),
        Param("names", "strings", "Name each item, in the same order as values."),
        Param("label", "string", "Say what was checked."),
    ),
    example={"values": [True, True, True, "warn", True, False, True, None], "label": "Suites"},
    size="m",
)
def strip(values, *, names=None, label=None) -> Built:
    if not values:
        raise ChipError(
            "needs at least 1 item in values.",
            fix_hint="Pass one result per item, e.g. mintchip.strip([True, 'warn', False]).",
        )
    states = [_state(v, i) for i, v in enumerate(values)]
    if names is not None and len(names) != len(values):
        raise ChipError(
            f"names has {len(names)} entries but values has {len(values)}.",
            fix_hint="Pass exactly one name per value, in the same order.",
        )
    counts = {k: states.count(k) for k in TOKENS}
    active = len(states) - counts["skip"]
    s = {
        "value": counts["pass"] / len(states) if active else None,
        "states": states,
        "names": names,
        "counts": counts,
        "active": active,
    }
    warnings = []
    if len(states) > CELLS:
        warnings.append(
            f"{len(states)} items shown in {CELLS} cells, each the worst state of its bucket "
            f"(marked n={len(states)})."
        )
    who = names or [f"item {i + 1}" for i in range(len(states))]
    facts = [_tally(counts) or f"{active} pass"]
    for state in ("fail", "warn"):
        hit = [w for w, st in zip(who, states, strict=True) if st == state]
        if hit:
            shown = ", ".join(hit[:5]) + (f" and {len(hit) - 5} more" if len(hit) > 5 else "")
            facts.append(f"{state}: {shown}")
    name = f"{label}: " if label else ""
    return Built(
        stats=s,
        facts=facts,
        warnings=warnings,
        alt=f"{name}{_value(s)} across {len(states)} items.",
    )


def _state(v, i: int) -> str:
    if v is None:
        return "skip"
    if isinstance(v, bool):
        return "pass" if v else "fail"
    if isinstance(v, str) and v.strip().lower() in STATE:
        return STATE[v.strip().lower()]
    hint = "Pass True/False, 'pass', 'warn', 'fail', 'skip' or None"
    if isinstance(v, str):
        raise ChipError(f"values[{i}] is {v!r}, not a known state.", fix_hint=hint + ".")
    raise ChipError(
        f"values[{i}] is the number {fmt.num(v)}; strip shows states, not numbers.",
        fix_hint=hint + "; for a series of numbers use mintchip.spark.",
    )


def _tally(counts: dict[str, int]) -> str:
    return ", ".join(f"{counts[k]} {k}" for k in ("fail", "warn", "skip") if counts[k])


def _value(s: dict) -> str:
    if not s["active"]:
        return f"all {s['counts']['skip']} skipped"
    return f"{s['counts']['pass']}/{len(s['states'])} pass"


def _cells(s: dict) -> list[tuple[str, list[int]]]:
    """(state, item indices) per cell: one item each, or the worst of each bucket."""
    states, n = s["states"], len(s["states"])
    if n <= CELLS:
        return [(st, [i]) for i, st in enumerate(states)]
    out = []
    for b in range(CELLS):
        idx = list(range(b * n // CELLS, (b + 1) * n // CELLS))
        out.append((max((states[i] for i in idx), key=WORST.__getitem__), idx))
    return out


# --- text -----------------------------------------------------------------------------------
@text_renderer("strip")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    value = _value(s)
    tally = _tally(s["counts"]) if s["active"] else ""
    if tally and not o.compact:
        value += f" ({tally})"
    glyph: list[Segment] = []
    for state, _ in _cells(s):
        ch, role = GLYPH[state], ROLE[state]
        if glyph and glyph[-1][1] == role:
            glyph[-1] = (glyph[-1][0] + ch, role)
        else:
            glyph.append((ch, role))
    if len(s["states"]) > CELLS:
        glyph.append((f" n={len(s['states'])}", None))
    return TextOut(value, glyph)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("strip")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    cells = _cells(s)
    pitch = min(PITCH, (c.right - c.left) / len(cells))
    w = pitch - max(1.25, 0.3 * pitch)
    names = s["names"] or [f"item {i + 1}" for i in range(len(s["states"]))]
    for k, (state, idx) in enumerate(cells):
        x = c.left + k * pitch
        who = names[idx[0]] if len(idx) == 1 else f"{names[idx[0]]} to {names[idx[-1]]}"
        title = f"{who}: {state}"
        if state == "skip":
            c.dot(x + w / 2, c.bottom - 1.75, r=1.75, role="context", hollow=True, title=title)
        else:
            h = HEIGHT[state]
            c.rect(x, c.bottom - h, w, h, role=ROLE[state], title=title)
    c.fit()
