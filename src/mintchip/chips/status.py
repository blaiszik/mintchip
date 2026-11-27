"""status: compact CI / test pass-fail-skip stacked bar chip.

Text: ``142/148 pass (4 fail, 2 skip) ███████▓░`` (compact drops the parenthesis): CELLS cells
proportionally split across passed (``█``, good), failed (``▓``, bad), and skipped (``░``,
context). Any non-zero count receives at least 1 cell so a single failure is never hidden.
SVG: proportional stacked bar using semantic roles (``good``, ``bad``, ``context``) with a
minimum visible sliver of at least 1.5 viewBox units (2.0 px) for every non-zero segment.
"""

from __future__ import annotations

from .. import fmt
from ..render.svg_base import Canvas
from ..render.text_base import Segment, TextOptions, TextOut, cell_counts
from ..spec import Built, Chip, ChipError, Param, chip, svg_renderer, text_renderer

CELLS = 9
BAR_Y = 4.0
BAR_H = 8.0
GAP_W = 1.0
MIN_W = 2.0  # guaranteed >= 1.5 px visible sliver when failed > 0 (or any non-zero segment)

_GLYPH = {"passed": "█", "failed": "▓", "skipped": "░"}
_ROLE = {"passed": "good", "failed": "bad", "skipped": "context"}


@chip(
    "status",
    question="How many checks passed, failed or were skipped?",
    have="Pass, fail & skip counts",
    params=(
        Param(
            "passed",
            "int",
            "Number of passing checks (0 or more).",
            required=True,
            positional=True,
        ),
        Param(
            "failed",
            "int",
            "Number of failing checks (0 or more).",
            positional=True,
            default=0,
        ),
        Param(
            "skipped",
            "int",
            "Number of skipped checks (0 or more).",
            positional=True,
            default=0,
        ),
        Param("label", "string", "Say what suite or job was checked."),
    ),
    example={"passed": 142, "failed": 4, "skipped": 2, "label": "CI tests"},
    size="m",
)
def status(passed, failed=0, skipped=0, *, label=None) -> Built:
    for name, v in (("passed", passed), ("failed", failed), ("skipped", skipped)):
        if v < 0:
            raise ChipError(
                f"{name} must be 0 or more; got {v}.",
                fix_hint="Pass non-negative counts, e.g. mintchip.status(142, 4, 2).",
            )
    total = passed + failed + skipped
    if total == 0:
        raise ChipError(
            "total checks (passed + failed + skipped) must be at least 1; got 0.",
            fix_hint="Pass at least one check, e.g. mintchip.status(10, 0, 0).",
        )

    active = passed + failed
    pass_rate = passed / total
    segments = [
        (key, cnt)
        for key, cnt in (("passed", passed), ("failed", failed), ("skipped", skipped))
        if cnt > 0
    ]
    weights = [float(cnt) for _, cnt in segments]
    counts, _ = cell_counts(weights, CELLS)

    facts = [
        f"{fmt.count(cnt)} {key} ({fmt.pct(cnt / total)})" for key, cnt in segments
    ]
    facts.append(f"{fmt.count(total)} total")

    val_str = _value_text(passed, total, active, skipped)
    tally = _tally(failed, skipped)
    summary = f"{val_str} ({tally})" if active and tally else val_str
    name = f"{label}: " if label else ""

    return Built(
        stats={
            "value": pass_rate,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "total": total,
            "active": active,
            "segments": [(key, cnt, n) for (key, cnt), n in zip(segments, counts, strict=True)],
        },
        facts=facts,
        warnings=(),
        alt=f"{name}{summary}.",
    )


def _value_text(passed: int, total: int, active: int, skipped: int) -> str:
    if not active:
        return f"all {fmt.count(skipped)} skipped"
    return f"{fmt.count(passed)}/{fmt.count(total)} pass"


def _tally(failed: int, skipped: int) -> str:
    parts = []
    if failed:
        parts.append(f"{fmt.count(failed)} fail")
    if skipped:
        parts.append(f"{fmt.count(skipped)} skip")
    return ", ".join(parts)


# --- text -----------------------------------------------------------------------------------
@text_renderer("status")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    value = _value_text(s["passed"], s["total"], s["active"], s["skipped"])
    tally = _tally(s["failed"], s["skipped"])
    if s["active"] and tally and not o.compact:
        value += f" ({tally})"
    glyph: list[Segment] = [(_GLYPH[key] * n, _ROLE[key]) for key, _, n in s["segments"]]
    return TextOut(value, glyph)


# --- svg ------------------------------------------------------------------------------------
@svg_renderer("status")
def _svg(chip: Chip, c: Canvas) -> None:
    s = chip.stats
    segs = s["segments"]
    total = s["total"]
    room = (c.right - c.left) - GAP_W * (len(segs) - 1)
    widths = [max(MIN_W, (cnt / total) * room) for _, cnt, _ in segs]

    # Deduct any minimum-sliver lift from segments strictly wider than MIN_W so none vanishes.
    excess = sum(widths) - room
    while excess > 1e-6:
        donors = [i for i, w in enumerate(widths) if w > MIN_W + 1e-6]
        if not donors:
            break
        big = max(donors, key=widths.__getitem__)
        take = min(excess, widths[big] - MIN_W)
        widths[big] -= take
        excess -= take

    x = c.left
    for (key, cnt, _), w in zip(segs, widths, strict=True):
        tip = f"{key}: {fmt.count(cnt)} ({fmt.pct(cnt / total)})"
        c.rect(x, BAR_Y, w, BAR_H, role=_ROLE[key], narrow=(key == "skipped"), title=tip)
        x += w + GAP_W
