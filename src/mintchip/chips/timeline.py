"""timeline: where the time went, as phases along one wall clock.

Text: ``7.5 s (solve 64%) ██▏██████▏██``: the wall-clock total and the longest phase's share
of it, then CELLS cells split among the phases in time order, separated by thin gaps; the
longest phase is in accent. Idle time between phases is empty track (``·``), not closed up.
A phase too short to earn a cell gets one half-height cell (``▄``) and a warning.
SVG: bars with gaps on the same clock, the longest in accent, idle time as a context line.

Overlapping phases (given as ``name → (start, end)``): the SVG packs them into up to
MAX_LANES lanes, so every phase keeps its true length. The text has one line, so it draws one
lane where the later-starting phase covers the overlap, and announces it as ``overlap 0.4 s``.
"""

from __future__ import annotations

import itertools

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import GAP, TRACK, TextOptions, TextOut, largest_remainder
from ..spec import Built, Chip, ChipError, Param, chip, svg_renderer, text_renderer
from .share import SMALL

CELLS = 12  # total text-bar width (block/track cells + separator gaps)
MAX_PHASES = 10  # maximum phases shown in one timeline
MAX_LANES = 3  # parallel phases the SVG can stack and still read at 1x
LANES = {  # SVG bar (top, height) per lane, by lane count
    1: ((4.0, 8.0),),
    2: ((3.0, 4.5), (8.5, 4.5)),
    3: ((2.5, 3.0), (6.5, 3.0), (10.5, 3.0)),
}
INSET = 0.75  # SVG bars are inset this much at each end, leaving a gap between neighbours
MIN_W = 1.5
HINT = 'Pass durations in order, {"fetch": 1.2, "solve": 4.8}, or spans, {"fetch": (0, 1.2)}.'


@chip(
    "timeline",
    question="Where did the time go?",
    have="Durations of phases",
    params=(
        Param(
            "stages",
            "mapping",
            "Give each phase's duration in order, or its (start, end), by name.",
            required=True,
            positional=True,
        ),
        Param("label", "string", "Say what was timed."),
        Param("unit", "string", "Name the unit of the times.", default="s"),
    ),
    example={"stages": {"fetch": 1.2, "solve": 4.8, "write": 1.5}, "label": "Agent step"},
    size="m",
)
def timeline(stages, *, label=None, unit="s") -> Built:
    if not stages:
        raise ChipError("needs at least 1 phase; got none.", fix_hint=HINT)
    if len(stages) > MAX_PHASES:
        raise ChipError(
            f"shows at most {MAX_PHASES} phases; got {len(stages)}.",
            fix_hint="Group short phases together, e.g. 'setup' for the first few.",
        )
    kinds = {isinstance(v, tuple) for v in stages.values()}
    if len(kinds) > 1:
        raise ChipError("phases must be all durations or all (start, end) spans.", fix_hint=HINT)
    names = list(stages)
    if kinds == {True}:
        spans = [stages[n] for n in names]
    else:
        ends = list(itertools.accumulate(stages.values(), initial=0.0))
        spans = list(itertools.pairwise(ends))  # back to back, with no float sliver between
    for name, (a, b) in zip(names, spans, strict=True):
        if not b > a:
            raise ChipError(
                f"phase {name!r} must take positive time; got {fmt.num(b - a)}.",
                fix_hint="Leave out phases that took no time; give spans as (start, end).",
            )
    order = sorted(range(len(spans)), key=lambda i: spans[i][0])  # stable
    names = [names[i] for i in order]
    spans = [spans[i] for i in order]
    t0, t1 = spans[0][0], max(b for _, b in spans)
    wall = t1 - t0
    durs = [b - a for a, b in spans]
    longest = max(range(len(durs)), key=lambda i: (durs[i], -i))

    pieces, idle, overlap, peak = _sweep(spans)
    lanes = _lanes(spans)
    if max(lanes) + 1 > MAX_LANES:
        raise ChipError(
            f"{peak} phases run at once; a timeline stacks at most {MAX_LANES}.",
            fix_hint="Group parallel phases into one, or show each group as its own timeline.",
        )
    text, small, use_gaps, block_budget = _text_pieces(pieces, len(spans))

    warnings = []
    if overlap > 0:
        warnings.append(
            f"phases overlap for {fmt.num(overlap, unit=unit)} (up to {peak} at once); the SVG "
            f"stacks them in {max(lanes) + 1} lanes, the one-line text lets the later phase "
            f"cover the overlap (marked overlap {fmt.num(overlap, unit=unit)})."
        )
    for i in small:
        warnings.append(
            f"phase {names[i]!r} ({fmt.num(durs[i], unit=unit)}, {fmt.pct(durs[i] / wall)}) is "
            f"under one text cell of {block_budget}; it is drawn as one half-height cell ({SMALL}), "
            "and as a half-height bar in SVG if it is narrower than the minimum."
        )

    facts = [
        f"{n} {fmt.num(d, unit=unit)} ({fmt.pct(d / wall)})"
        for n, d in zip(names, durs, strict=True)
    ]
    idle_time = sum(b - a for a, b in idle)
    if idle_time > 0:
        facts.append(f"idle {fmt.num(idle_time, unit=unit)} ({fmt.pct(idle_time / wall)})")
    if overlap > 0:
        facts.append(f"overlap {fmt.num(overlap, unit=unit)}, up to {peak} phases at once")
    name = f"{label}: " if label else ""
    return Built(
        stats={
            "value": wall,
            "total": wall,
            "start": t0,
            "names": names,
            "spans": spans,
            "longest": longest,
            "share": durs[longest] / wall,
            "lanes": lanes,
            "idle": idle,
            "overlap": overlap,
            "text": text,
            "use_gaps": use_gaps,
        },
        facts=facts,
        warnings=warnings,
        alt=f"{name}{fmt.num(wall, unit=unit)} over {len(spans)} phases; {names[longest]} is "
        f"longest at {fmt.num(durs[longest], unit=unit)} ({fmt.pct(durs[longest] / wall)}).",
    )


def _sweep(spans: list[tuple[float, float]]):
    """Walk the clock once. Returns the one-lane pieces ``[owner, seconds]`` (owner is the
    latest-started running phase, or None when idle), the idle spans, the time with two or
    more phases running, and the most phases running at once."""
    bounds = sorted({t for span in spans for t in span})
    pieces: list[list] = []
    idle, overlap, peak = [], 0.0, 0
    for a, b in itertools.pairwise(bounds):
        running = [i for i, (s, e) in enumerate(spans) if s <= a and e >= b]
        owner = max(running) if running else None  # spans are sorted by start
        peak = max(peak, len(running))
        if len(running) > 1:
            overlap += b - a
        if owner is None:
            idle.append((a, b))
        if pieces and pieces[-1][0] == owner:
            pieces[-1][1] += b - a
        else:
            pieces.append([owner, b - a])
    return pieces, idle, overlap, peak


def _lanes(spans: list[tuple[float, float]]) -> list[int]:
    """Greedy lane per phase (spans sorted by start): the first lane free by its start."""
    ends: list[float] = []
    lanes = []
    for a, b in spans:
        k = next((k for k, e in enumerate(ends) if e <= a), len(ends))
        ends[k : k + 1] = [b]
        lanes.append(k)
    return lanes


def _allocate_pieces(pieces: list[list], phases: int, budget: int) -> tuple[list[list], list[int]]:
    owners = [o for o, _ in pieces]
    cells = largest_remainder([d for _, d in pieces], budget)
    flag = [False] * len(pieces)

    def spare(j: int) -> bool:  # can piece j give up a cell without hiding its phase?
        if flag[j] or not cells[j]:
            return False
        o = owners[j]
        return (
            cells[j] > 1
            or o is None
            or any(cells[k] for k in range(len(pieces)) if k != j and owners[k] == o)
        )

    has = {o for o, n in zip(owners, cells, strict=True) if n and o is not None}
    small = [i for i in range(phases) if i not in has]
    for i in small:
        k = max((j for j, o in enumerate(owners) if o == i), key=lambda j: pieces[j][1])
        donor = max((j for j in range(len(cells)) if spare(j)), key=lambda j: (cells[j], -j))
        cells[donor] -= 1
        cells[k], flag[k] = 1, True
    out: list[list] = []
    for (owner, _), n, f in zip(pieces, cells, flag, strict=True):
        if not n:
            continue
        if out and out[-1][0] == owner and not f and not out[-1][2]:
            out[-1][1] += n
        else:
            out.append([owner, n, f])
    return out, small


def _count_gaps(runs: list[list]) -> int:
    return sum(1 for a, b in itertools.pairwise(runs) if a[0] is not None and b[0] is not None)


def _text_pieces(pieces: list[list], phases: int) -> tuple[list[list], list[int], bool, int]:
    """``[owner, cells, small]`` runs for the text line, small phases, whether gaps are drawn,
    and the block-cell budget. Separator gaps are budgeted inside ``CELLS`` so every timeline
    row has identical total bar width regardless of phase count."""
    n_gaps = _count_gaps(pieces)
    for _ in range(3):
        if phases + n_gaps > CELLS:
            out, small = _allocate_pieces(pieces, phases, CELLS)
            return out, small, False, CELLS
        budget = CELLS - n_gaps
        out, small = _allocate_pieces(pieces, phases, budget)
        actual_gaps = _count_gaps(out)
        if actual_gaps == n_gaps:
            return out, small, True, budget
        n_gaps = actual_gaps
    out, small = _allocate_pieces(pieces, phases, CELLS)
    return out, small, False, CELLS


# --- text -----------------------------------------------------------------------------------
@text_renderer("timeline")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    dec = fmt.places(fmt.num(s["total"]))
    if o.decimals is not None and dec is not None:  # scientific notation keeps its form
        dec = o.decimals
        total = fmt.fixed(s["total"], dec, unit=chip.unit)
    else:
        total = fmt.num(s["total"], unit=chip.unit)
    value = total if o.compact else f"{total} ({s['names'][s['longest']]} {fmt.pct(s['share'])})"
    glyph: list[tuple[str, str | None]] = []
    use_gaps = s.get("use_gaps", True)
    prev = None
    for owner, n, small in s["text"]:
        if owner is None:
            glyph.append((TRACK * n, "context"))
        else:
            if use_gaps and prev is not None:
                glyph.append((GAP, None))
            role = "accent" if owner == s["longest"] else None
            glyph.append((SMALL if small else "█" * n, role))
        prev = owner
    if s["overlap"] > 0:
        glyph.append((f" overlap {fmt.num(s['overlap'], unit=chip.unit)}", None))
    return TextOut(value, glyph, dec)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("timeline")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    t0, wall = s["start"], s["total"]

    def x(t: float) -> float:
        return c.fx((t - t0) / wall)

    for a, b in s["idle"]:  # idle time keeps its length, as empty track
        c.line(x(a), c.mid, x(b), c.mid, role="context", width=1.25)
    rows = LANES[max(s["lanes"]) + 1]
    for i, ((a, b), lane) in enumerate(zip(s["spans"], s["lanes"], strict=True)):
        x1, x2 = x(a) + INSET, x(b) - INSET
        top, h = rows[lane]
        if x2 - x1 < MIN_W:  # too short to draw: minimum width, half height, like ▄ in text
            x1, x2 = (x1 + x2 - MIN_W) / 2, (x1 + x2 + MIN_W) / 2
            top, h = top + h / 2, h / 2
        tip = f"{s['names'][i]}: {fmt.num(b - a, unit=chip.unit)}"
        role = "accent" if i == s["longest"] else "ink"
        c.rect(x1, top, x2 - x1, h, role=role, title=tip)
