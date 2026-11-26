"""Structure, timeline, ranking, and dual-trajectory inline micro-graphics.

Word-sized Tufte micro-visuals returning :class:`Chip`:

- :func:`timeline` — micro-Gantt / phase breakdown for sequential durations or
  overlapping parallel intervals, highlighting the bottleneck stage.
- :func:`rank` — cohort percentile / leaderboard position ruler from either an
  explicit ``(position, total)`` pair or raw ``values`` + ``value``.
- :func:`dual_spark` — dual-series trajectory sparkline with crossover-aware
  divergence shading and Unicode/ASCII gap magnitude strip.
"""

from __future__ import annotations

import html
import itertools
import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .core import (
    _ASCII_SPARK,
    _SPARK_BLOCKS,
    Chip,
    ChipError,
    _fmt_val,
    _is_finite,
    _mintfig_style_name,
    _require_mintfig,
    _resolve_expand_explanation,
    _resolve_theme,
)
from .themes import Theme, relative_luminance

__all__ = [
    "dual_spark",
    "rank",
    "timeline",
]

_TIMELINE_UNI_SHADES = ("▓", "▒", "░")
_TIMELINE_ASCII_SHADES = ("=", "-", ":")


@dataclass(frozen=True)
class _StageSpan:
    name: str
    start: float
    end: float
    lane: int = 0

    @property
    def duration(self) -> float:
        return self.end - self.start


def _parse_timeline_stages(
    stages: (
        Mapping[str, float | tuple[float, float]]
        | Sequence[float | tuple[float, float] | tuple[str, float, float]]
    ),
) -> tuple[list[_StageSpan], bool]:
    """Normalize sequential durations or parallel intervals into ``_StageSpan`` records."""
    if isinstance(stages, Mapping):
        if not stages:
            raise ChipError(
                "inline.timeline requires at least 1 stage.",
                fix_hint='Pass e.g. {"fetch": 1.2, "code": 4.8, "test": 1.5} or {"a": (0, 2), "b": (1, 5)}.',
            )
        items = list(stages.items())
        first_val = items[0][1]
        is_interval = isinstance(first_val, Sequence) and not isinstance(first_val, (str, bytes))
        raw_spans: list[_StageSpan] = []

        if is_interval:
            for raw_name, bounds in items:
                nm = str(raw_name)
                if (
                    isinstance(bounds, (str, bytes))
                    or not isinstance(bounds, Sequence)
                    or len(bounds) != 2
                    or not (_is_finite(bounds[0]) and _is_finite(bounds[1]))
                ):
                    raise ChipError(
                        f"inline.timeline stage {nm!r} must be a finite (start, end) pair.",
                        fix_hint='Use uniform durations {stage: duration} or intervals {stage: (start, end)}.',
                    )
                s_val, e_val = float(bounds[0]), float(bounds[1])
                if e_val < s_val:
                    raise ChipError(
                        f"inline.timeline stage {nm!r} ends ({e_val}) before it starts ({s_val}).",
                        fix_hint="Ensure end >= start for every stage interval.",
                    )
                raw_spans.append(_StageSpan(name=nm, start=s_val, end=e_val))
            return raw_spans, True

        cursor = 0.0
        for raw_name, dur in items:
            nm = str(raw_name)
            if not _is_finite(dur):
                raise ChipError(
                    f"inline.timeline stage {nm!r} duration must be a finite non-negative number.",
                    fix_hint='Use uniform durations {stage: duration} or intervals {stage: (start, end)}.',
                )
            d_val = float(dur)  # type: ignore[arg-type]
            if d_val < 0.0:
                raise ChipError(
                    f"inline.timeline stage {nm!r} duration ({d_val}) cannot be negative.",
                    fix_hint="Pass non-negative stage durations or explicit (start, end) intervals.",
                )
            raw_spans.append(_StageSpan(name=nm, start=cursor, end=cursor + d_val))
            cursor += d_val
        return raw_spans, False

    if isinstance(stages, Sequence) and not isinstance(stages, (str, bytes)):
        if not stages:
            raise ChipError(
                "inline.timeline requires at least 1 stage.",
                fix_hint="Pass a sequence of durations, e.g. [1.2, 4.8, 1.5], or a mapping of stages.",
            )
        first = stages[0]
        if _is_finite(first):
            cursor = 0.0
            raw_spans = []
            for idx, dur in enumerate(stages):
                if not _is_finite(dur):
                    raise ChipError(
                        f"inline.timeline duration at index {idx} must be a finite non-negative number.",
                        fix_hint="Pass finite non-negative durations, e.g. [1.2, 4.8, 1.5].",
                    )
                d_val = float(dur)  # type: ignore[arg-type]
                if d_val < 0.0:
                    raise ChipError(
                        f"inline.timeline duration at index {idx} ({d_val}) cannot be negative.",
                        fix_hint="Pass non-negative stage durations.",
                    )
                raw_spans.append(_StageSpan(name=f"Stage {idx + 1}", start=cursor, end=cursor + d_val))
                cursor += d_val
            return raw_spans, False

        if isinstance(first, Sequence) and not isinstance(first, (str, bytes)):
            raw_spans = []
            for idx, item in enumerate(stages):
                if isinstance(item, (str, bytes)) or not isinstance(item, Sequence):
                    raise ChipError(
                        f"inline.timeline item at index {idx} must be a (start, end) or (name, start, end) tuple.",
                        fix_hint='Pass [("fetch", 0, 1.2), ("code", 1.2, 6.0)] or {stage: (start, end)}.',
                    )
                if len(item) == 3 and _is_finite(item[1]) and _is_finite(item[2]):
                    nm, s_val, e_val = str(item[0]), float(item[1]), float(item[2])
                elif len(item) == 2 and _is_finite(item[0]) and _is_finite(item[1]):
                    nm, s_val, e_val = f"Stage {idx + 1}", float(item[0]), float(item[1])
                else:
                    raise ChipError(
                        f"inline.timeline item at index {idx} must be finite (start, end) or (name, start, end).",
                        fix_hint='Pass [("fetch", 0, 1.2), ("code", 1.2, 6.0)] or {stage: (start, end)}.',
                    )
                if e_val < s_val:
                    raise ChipError(
                        f"inline.timeline stage {nm!r} ends ({e_val}) before it starts ({s_val}).",
                        fix_hint="Ensure end >= start for every stage interval.",
                    )
                raw_spans.append(_StageSpan(name=nm, start=s_val, end=e_val))
            return raw_spans, True

    raise ChipError(
        f"inline.timeline expected a mapping or sequence of stages; got {type(stages).__name__}.",
        fix_hint='Pass {stage: duration}, {stage: (start, end)}, or a sequence of durations.',
    )


def _pack_lanes(spans: Sequence[_StageSpan]) -> tuple[list[_StageSpan], int]:
    """Assign each stage to the lowest non-overlapping horizontal lane."""
    order = sorted(range(len(spans)), key=lambda i: (spans[i].start, -spans[i].duration, i))
    lane_ends: list[float] = []
    lane_for: dict[int, int] = {}
    for idx in order:
        sp = spans[idx]
        assigned = -1
        for lane_idx, end_t in enumerate(lane_ends):
            if end_t <= sp.start + 1e-12:
                assigned = lane_idx
                lane_ends[lane_idx] = sp.end
                break
        if assigned < 0:
            assigned = len(lane_ends)
            lane_ends.append(sp.end)
        lane_for[idx] = assigned

    packed = [
        _StageSpan(name=sp.name, start=sp.start, end=sp.end, lane=lane_for[idx])
        for idx, sp in enumerate(spans)
    ]
    return packed, max(len(lane_ends), 1)


def _overlap_stats(spans: Sequence[_StageSpan]) -> tuple[int, int, float]:
    """Return ``(overlap_pair_count, peak_concurrency, idle_time)``."""
    overlap_pairs = 0
    n = len(spans)
    for i in range(n):
        si, ei = spans[i].start, spans[i].end
        if ei <= si:
            continue
        for j in range(i + 1, n):
            sj, ej = spans[j].start, spans[j].end
            if ej <= sj:
                continue
            if max(si, sj) < min(ei, ej) - 1e-12:
                overlap_pairs += 1

    events: list[tuple[float, int]] = []
    for sp in spans:
        if sp.end > sp.start:
            events.append((sp.start, 1))
            events.append((sp.end, -1))
    # End (-1) before start (+1) at equal timestamps: back-to-back stages are not concurrent.
    events.sort(key=lambda pair: (pair[0], pair[1]))

    cur = 0
    peak = 0
    active_time = 0.0
    prev_t: float | None = None
    for t, delta in events:
        if prev_t is not None and cur > 0 and t > prev_t:
            active_time += t - prev_t
        cur += delta
        peak = max(peak, cur)
        prev_t = t

    wall = max(sp.end for sp in spans) - min(sp.start for sp in spans)
    idle_time = max(0.0, wall - active_time)
    return overlap_pairs, peak, idle_time


# --------------------------------------------------------------------------- #
# 1. mintchip.timeline — Micro-Gantt / phase breakdown
# --------------------------------------------------------------------------- #


def timeline(
    stages: (
        Mapping[str, float | tuple[float, float]]
        | Sequence[float | tuple[float, float] | tuple[str, float, float]]
    ),
    *,
    label: str | None = None,
    unit: str | None = "s",
    width: int = 76,
    height: int = 14,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized micro-Gantt / phase breakdown bar.

    Accepts either sequential stage durations (``{"fetch": 1.2, "code": 4.8}``
    or ``[1.2, 4.8, 1.5]``) or explicit parallel intervals
    (``{"fetch": (0.0, 1.2), "compile": (0.8, 5.6)}``). Highlights the
    longest-duration bottleneck stage in the warm theme accent and stacks
    compact horizontal lanes whenever intervals overlap.
    """
    raw_spans, is_interval = _parse_timeline_stages(stages)
    t_min = min(sp.start for sp in raw_spans)
    t_max = max(sp.end for sp in raw_spans)
    wall_span = t_max - t_min
    if wall_span <= 0.0:
        raise ChipError(
            "inline.timeline requires a positive total wall-clock span.",
            fix_hint="Provide at least one stage with duration > 0.",
        )

    spans, num_lanes = _pack_lanes(raw_spans)
    overlap_pairs, peak_concurrency, idle_time = _overlap_stats(spans)
    total_work = sum(sp.duration for sp in spans)
    is_parallel = overlap_pairs > 0 or num_lanes > 1

    bottleneck_idx = max(range(len(spans)), key=lambda i: spans[i].duration)
    bottleneck = spans[bottleneck_idx]
    bn_share = bottleneck.duration / wall_span
    bn_pct = 100.0 * bn_share

    theme = _resolve_theme(style, palette=palette, accent=accent)
    is_dark = relative_luminance(theme.background) < 0.35
    bn_color = theme.accent_colors[0]
    non_bn_palette: list[str] = []
    for cand in (*theme.series_colors, theme.muted, theme.context_line):
        if cand.lower() != bn_color.lower() and cand.lower() not in {
            c.lower() for c in non_bn_palette
        }:
            non_bn_palette.append(cand)
    if not non_bn_palette:
        non_bn_palette = [theme.muted]

    pad_x = 1.6
    inner_w = max(width - 2.0 * pad_x, 8.0)

    def _x(t: float) -> float:
        return pad_x + ((t - t_min) / wall_span) * inner_w

    if num_lanes == 1:
        track_h = max(height - 3.0, 6.0)
        track_y = (height - track_h) / 2.0
        lane_ys = [(height - max(track_h - 2.0, 4.5)) / 2.0]
        lane_h = max(track_h - 2.0, 4.5)
    else:
        track_h = max(height - 1.6, 8.0)
        track_y = (height - track_h) / 2.0
        lane_gap = 1.1 if num_lanes <= 3 else 0.75
        usable_h = max(track_h - 1.0, 6.0)
        lane_h = max(1.6, (usable_h - lane_gap * (num_lanes - 1)) / num_lanes)
        start_y = (height - (lane_h * num_lanes + lane_gap * (num_lanes - 1))) / 2.0
        lane_ys = [start_y + k * (lane_h + lane_gap) for k in range(num_lanes)]

    svg_parts: list[str] = [
        # Subtle wall-clock track background
        (
            f'<rect x="{pad_x:.1f}" y="{track_y:.2f}" width="{inner_w:.1f}" '
            f'height="{track_h:.2f}" fill="{theme.context_fill}" '
            f'fill-opacity="{0.18 if is_dark else 0.28:.2f}" rx="1.5"/>'
        )
    ]

    # Faint horizontal lane guide hairlines for multi-lane parallel views
    if num_lanes > 1:
        for ly in lane_ys:
            cy = ly + lane_h / 2.0
            svg_parts.append(
                f'<line x1="{pad_x:.1f}" y1="{cy:.2f}" x2="{width - pad_x:.1f}" y2="{cy:.2f}" '
                f'stroke="{theme.grid}" stroke-width="0.6" stroke-opacity="0.7"/>'
            )

    # Crisp start/end span anchor ticks
    svg_parts.append(
        f'<line x1="{pad_x:.1f}" y1="{track_y:.2f}" x2="{pad_x:.1f}" y2="{track_y + track_h:.2f}" '
        f'stroke="{theme.axis}" stroke-width="0.7" stroke-opacity="0.55"/>'
    )
    svg_parts.append(
        f'<line x1="{width - pad_x:.1f}" y1="{track_y:.2f}" x2="{width - pad_x:.1f}" '
        f'y2="{track_y + track_h:.2f}" stroke="{theme.axis}" stroke-width="0.7" stroke-opacity="0.55"/>'
    )

    non_bn_counter = 0
    stage_uni_char: dict[int, str] = {}
    stage_asc_char: dict[int, str] = {}
    for idx, sp in enumerate(spans):
        is_bn = idx == bottleneck_idx
        if is_bn:
            fill = bn_color
            opacity = 1.0
            stage_uni_char[idx] = "█"
            stage_asc_char[idx] = "#"
        else:
            fill = non_bn_palette[non_bn_counter % len(non_bn_palette)]
            opacity = 0.84 if is_dark else 0.80
            stage_uni_char[idx] = _TIMELINE_UNI_SHADES[non_bn_counter % len(_TIMELINE_UNI_SHADES)]
            stage_asc_char[idx] = _TIMELINE_ASCII_SHADES[
                non_bn_counter % len(_TIMELINE_ASCII_SHADES)
            ]
            non_bn_counter += 1

        pct_s = 100.0 * sp.duration / wall_span
        dur_s = _fmt_val(sp.duration, unit=unit)
        span_range = f"{_fmt_val(sp.start, unit=unit)}–{_fmt_val(sp.end, unit=unit)}"
        lane_note = f", lane {sp.lane + 1}" if num_lanes > 1 else ""
        bn_note = " [bottleneck]" if is_bn else ""
        tip = f"{sp.name}: {dur_s} ({pct_s:.0f}% of span; {span_range}{lane_note}){bn_note}"

        ly = lane_ys[sp.lane]
        x1 = _x(sp.start)
        x2 = _x(sp.end)
        if sp.duration <= 0.0:
            # Milestone diamond for zero-duration marker inside an interval timeline
            cy = ly + lane_h / 2.0
            r = min(lane_h * 0.45, 2.3)
            pts = (
                f"{x1:.2f},{cy - r:.2f} {x1 + r:.2f},{cy:.2f} "
                f"{x1:.2f},{cy + r:.2f} {x1 - r:.2f},{cy:.2f}"
            )
            svg_parts.append(
                f'<polygon points="{pts}" fill="{fill}" stroke="{theme.background}" '
                f'stroke-width="0.6"><title>{html.escape(tip)}</title></polygon>'
            )
        else:
            bw = max(x2 - x1, 1.4)
            svg_parts.append(
                f'<rect x="{x1:.2f}" y="{ly:.2f}" width="{bw:.2f}" height="{lane_h:.2f}" '
                f'fill="{fill}" fill-opacity="{opacity:.2f}" stroke="{theme.background}" '
                f'stroke-width="0.6" rx="1.2"><title>{html.escape(tip)}</title></rect>'
            )

    # 10-cell proportional phase strip with distinct shading & idle gaps
    cells = 10
    u_cells: list[str] = []
    a_cells: list[str] = []
    chosen_indices: list[int | None] = []
    for k in range(cells):
        c_lo = t_min + (k / cells) * wall_span
        c_hi = t_min + ((k + 1) / cells) * wall_span
        best_idx: int | None = None
        best_key: tuple[float, int, float] = (0.0, 0, 0.0)
        for idx, sp in enumerate(spans):
            ov = max(0.0, min(sp.end, c_hi) - max(sp.start, c_lo))
            if ov > 1e-12:
                key = (ov, 1 if idx == bottleneck_idx else 0, sp.duration)
                if key > best_key:
                    best_key = key
                    best_idx = idx
        chosen_indices.append(best_idx)

    # Ensure the bottleneck is visibly represented on at least its midpoint cell
    if bottleneck_idx not in chosen_indices:
        bn_mid = 0.5 * (bottleneck.start + bottleneck.end)
        mid_cell = max(0, min(cells - 1, int(((bn_mid - t_min) / wall_span) * cells)))
        chosen_indices[mid_cell] = bottleneck_idx

    for chosen in chosen_indices:
        if chosen is None:
            u_cells.append("·")
            a_cells.append(".")
        else:
            u_cells.append(stage_uni_char[chosen])
            a_cells.append(stage_asc_char[chosen])

    u_glyph = f"[{''.join(u_cells)}]"
    a_glyph = f"[{''.join(a_cells)}]"

    total_str = _fmt_val(wall_span, unit=unit)
    pct_int = round(bn_pct)
    val_str = f"{total_str} ({bottleneck.name} {pct_int}%)"
    compact_val = total_str
    prefix = f"{label}: " if label else ""

    stage_word = "stage" if len(spans) == 1 else "stages"
    facts: list[str] = [
        (
            f"{prefix}total span {total_str} across {len(spans)} {stage_word} "
            f"({_fmt_val(t_min, unit=unit)} to {_fmt_val(t_max, unit=unit)})"
        ),
        (
            f"Bottleneck: {bottleneck.name} "
            f"({_fmt_val(bottleneck.duration, unit=unit)}, {bn_pct:.1f}% of span)"
        ),
    ]
    if is_parallel:
        pair_word = "overlap" if overlap_pairs == 1 else "overlaps"
        facts.append(
            f"Parallel execution: {overlap_pairs} stage {pair_word}, "
            f"peak concurrency {peak_concurrency}, cumulative work {_fmt_val(total_work, unit=unit)}"
        )
    else:
        facts.append(f"Sequential execution across {len(spans)} {stage_word} (0 overlaps)")
    if idle_time > 1e-9:
        idle_pct = 100.0 * idle_time / wall_span
        facts.append(f"Idle gap: {_fmt_val(idle_time, unit=unit)} ({idle_pct:.1f}% of span)")

    alt = (
        f"{prefix}timeline spanning {total_str} across {len(spans)} {stage_word}; "
        f"bottleneck {bottleneck.name} ({pct_int}%)"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.16em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        explain_timeline = mint.timeline

        name = label or "Pipeline"
        # Ensure unique stage names for mint.timeline highlight lookup
        seen: dict[str, int] = {}
        span_tuples: list[tuple[str, float, float]] = []
        hl_name = bottleneck.name
        for idx, sp in enumerate(spans):
            count = seen.get(sp.name, 0) + 1
            seen[sp.name] = count
            uniq_name = sp.name if count == 1 else f"{sp.name} #{count}"
            if idx == bottleneck_idx:
                hl_name = uniq_name
            span_tuples.append((uniq_name, sp.start, sp.end))

        panel = explain_timeline(
            span_tuples,
            title=f"{bottleneck.name} accounts for {pct_int}% of {total_str} wall span",
            label=name,
            unit=unit,
            highlight=hl_name,
        )
        return mint.explain(
            f"{name} spans {total_str}; bottleneck is {bottleneck.name} ({pct_int}%)",
            panel,
            style=_mintfig_style_name(theme),
        )

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="timeline",
        svg=svg,
        text=u_glyph,
        ascii_text=a_glyph,
        value_text=val_str,
        compact_value=compact_val,
        alt_text=alt,
        facts=facts,
        theme=theme,
        label=label,
        unit=unit,
        data={
            "stages": [
                {
                    "name": sp.name,
                    "start": sp.start,
                    "end": sp.end,
                    "duration": sp.duration,
                    "lane": sp.lane,
                }
                for sp in spans
            ],
            "total_span": wall_span,
            "total_work": total_work,
            "bottleneck": bottleneck.name,
            "bottleneck_share": bn_share,
            "overlap_count": overlap_pairs,
            "peak_concurrency": peak_concurrency,
            "lanes": num_lanes,
            "idle_time": idle_time,
            "is_interval": is_interval,
            "is_parallel": is_parallel,
        },
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 2. mintchip.rank — Cohort percentile / leaderboard position micro-glyph
# --------------------------------------------------------------------------- #


def _is_strict_int(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def rank(
    position: int | None = None,
    total: int | None = None,
    *,
    values: Sequence[float] | None = None,
    value: float | None = None,
    label: str | None = None,
    unit: str | None = None,
    higher_is_better: bool = True,
    width: int = 68,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized cohort percentile / leaderboard position micro-glyph.

    Pass either explicit 1-indexed ``(position, total)`` (e.g. ``rank(2, 18)``)
    or a cohort sequence ``values=[...]`` together with ``value=...`` to compute
    rank and percentile automatically. Worst sits on the left and #1 best sits
    on the right.
    """
    has_pos_args = position is not None or total is not None
    has_val_args = values is not None or value is not None

    if has_pos_args and has_val_args:
        raise ChipError(
            "inline.rank accepts either (position, total) or (values, value), not both.",
            fix_hint="Call mintchip.rank(2, 18) or mintchip.rank(values=scores, value=0.88).",
        )
    if not has_pos_args and not has_val_args:
        raise ChipError(
            "inline.rank requires either (position, total) or (values, value).",
            fix_hint="Call mintchip.rank(2, 18) or mintchip.rank(values=scores, value=0.88).",
        )

    cohort: list[float] | None = None
    peers: list[float] = []
    entity_val: float | None = None

    if has_pos_args:
        if position is None or total is None:
            raise ChipError(
                "inline.rank requires both position and total when using explicit rank mode.",
                fix_hint="Pass both integers, e.g. mintchip.rank(2, 18).",
            )
        if not (_is_strict_int(position) and _is_strict_int(total)):
            raise ChipError(
                "inline.rank position and total must be integers.",
                fix_hint="Pass 1-indexed integers, e.g. mintchip.rank(2, 18).",
            )
        if total < 1:
            raise ChipError(
                f"inline.rank total must be >= 1; got {total}.",
                fix_hint="Pass a positive cohort size, e.g. mintchip.rank(2, 18).",
            )
        if not (1 <= position <= total):
            raise ChipError(
                f"inline.rank position ({position}) must be between 1 and total ({total}).",
                fix_hint=f"Pass a 1-indexed rank in 1..{total}.",
            )
        pos_i = int(position)
        tot_i = int(total)
    else:
        if values is None or value is None:
            raise ChipError(
                "inline.rank requires both values= and value= when ranking within a cohort.",
                fix_hint="Pass e.g. mintchip.rank(values=[0.71, 0.80, 0.85, 0.91], value=0.85).",
            )
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
            raise ChipError(
                f"inline.rank values= must be a numeric sequence; got {type(values).__name__}.",
                fix_hint="Pass a list or tuple of numbers for values=.",
            )
        if not _is_finite(value):
            raise ChipError(
                "inline.rank value= must be a finite number.",
                fix_hint="Pass a finite numeric score for value=.",
            )
        nums = [float(v) for v in values if _is_finite(v)]
        if len(nums) < 2:
            raise ChipError(
                "inline.rank values= requires at least 2 finite cohort observations.",
                fix_hint="Pass a cohort of 2+ numbers, e.g. values=[0.72, 0.81, 0.88].",
            )
        entity_val = float(value)
        match_idx = next(
            (i for i, v in enumerate(nums) if math.isclose(v, entity_val, rel_tol=1e-9, abs_tol=1e-12)),
            None,
        )
        if match_idx is not None:
            cohort = list(nums)
            peers = [v for i, v in enumerate(nums) if i != match_idx]
        else:
            cohort = [*nums, entity_val]
            peers = list(nums)

        tot_i = len(cohort)
        strictly_better = sum(
            1
            for v in cohort
            if (v > entity_val + 1e-12 if higher_is_better else v < entity_val - 1e-12)
        )
        pos_i = 1 + strictly_better

    rank_frac = 1.0 if tot_i == 1 else (tot_i - pos_i) / (tot_i - 1)
    percentile = 100.0 * rank_frac
    pct_int = round(percentile)

    theme = _resolve_theme(style, palette=palette, accent=accent)
    is_dark = relative_luminance(theme.background) < 0.35

    if percentile >= 75.0:
        dot_color = theme.series_colors[0]
        tier = "top 25%"
    elif percentile <= 25.0:
        dot_color = theme.accent_colors[0]
        tier = "bottom 25%"
    else:
        dot_color = theme.ink
        tier = "middle 50%"

    pad_x = 4.5
    inner_w = max(width - 2.0 * pad_x, 8.0)
    cy = height / 2.0

    def _x_frac(t: float) -> float:
        return pad_x + max(0.0, min(1.0, t)) * inner_w

    svg_parts: list[str] = [
        # Subtle top-quartile highlight zone on the rightmost 25% ("best" end)
        (
            f'<rect x="{_x_frac(0.75):.2f}" y="{cy - 3.6:.2f}" width="{inner_w * 0.25:.2f}" '
            f'height="7.2" fill="{theme.series_colors[0]}" '
            f'fill-opacity="{0.16 if is_dark else 0.11:.2f}" rx="1.2"/>'
        ),
        # Horizontal cohort ruler track (worst left -> best right)
        (
            f'<line x1="{pad_x:.1f}" y1="{cy:.2f}" x2="{width - pad_x:.1f}" y2="{cy:.2f}" '
            f'stroke="{theme.grid}" stroke-width="1.4" stroke-linecap="round"/>'
        ),
        # Crisp end-cap ticks delimiting worst (left) and best (right)
        (
            f'<line x1="{pad_x:.1f}" y1="{cy - 2.6:.2f}" x2="{pad_x:.1f}" y2="{cy + 2.6:.2f}" '
            f'stroke="{theme.axis}" stroke-width="0.85" stroke-opacity="0.7"/>'
        ),
        (
            f'<line x1="{width - pad_x:.1f}" y1="{cy - 2.6:.2f}" x2="{width - pad_x:.1f}" '
            f'y2="{cy + 2.6:.2f}" stroke="{theme.axis}" stroke-width="0.85" stroke-opacity="0.7"/>'
        ),
    ]

    entity_x = _x_frac(rank_frac)
    med_val: float | None = None
    v_min: float | None = None
    v_max: float | None = None

    if cohort is not None and entity_val is not None:
        v_min, v_max = min(cohort), max(cohort)
        med_val = statistics.median(cohort)
        v_span = v_max - v_min

        def _x_val(v: float) -> float:
            if v_span <= 0.0:
                return _x_frac(0.5)
            t = (v - v_min) / v_span if higher_is_better else (v_max - v) / v_span
            return _x_frac(t)

        entity_x = _x_val(entity_val)

        # Faint cohort median tick
        xm = _x_val(med_val)
        med_tip = f"Cohort median: {_fmt_val(med_val, unit=unit)}"
        svg_parts.append(
            f'<line x1="{xm:.2f}" y1="{cy - 3.6:.2f}" x2="{xm:.2f}" y2="{cy + 3.6:.2f}" '
            f'stroke="{theme.context_line}" stroke-width="1.0" stroke-opacity="0.85">'
            f"<title>{html.escape(med_tip)}</title></line>"
        )

        # Peer dots (or compact rug ticks for large cohorts)
        if len(peers) <= 40:
            placed_x: list[tuple[float, float]] = []
            dy_opts = (0.0, -2.2, 2.2, -3.8, 3.8)
            for pv in sorted(peers):
                px = _x_val(pv)
                chosen_dy = 0.0
                for dy in dy_opts:
                    if all(math.hypot(px - ox, dy - oy) >= 2.1 for ox, oy in placed_x):
                        chosen_dy = dy
                        break
                placed_x.append((px, chosen_dy))
                ptip = f"Peer: {_fmt_val(pv, unit=unit)}"
                svg_parts.append(
                    f'<circle cx="{px:.2f}" cy="{cy + chosen_dy:.2f}" r="1.3" '
                    f'fill="{theme.context_line}" fill-opacity="{0.70 if is_dark else 0.78:.2f}">'
                    f"<title>{html.escape(ptip)}</title></circle>"
                )
        else:
            for pv in peers:
                px = _x_val(pv)
                svg_parts.append(
                    f'<line x1="{px:.2f}" y1="{cy - 2.0:.2f}" x2="{px:.2f}" y2="{cy + 2.0:.2f}" '
                    f'stroke="{theme.context_line}" stroke-width="0.7" stroke-opacity="0.45"/>'
                )
    else:
        # Faint quartile ticks (p25, p50, p75)
        for q_frac, q_lbl, half_h in (
            (0.25, "p25 (lower quartile)", 2.2),
            (0.50, "p50 (median)", 3.2),
            (0.75, "p75 (top quartile)", 2.2),
        ):
            qx = _x_frac(q_frac)
            svg_parts.append(
                f'<line x1="{qx:.2f}" y1="{cy - half_h:.2f}" x2="{qx:.2f}" y2="{cy + half_h:.2f}" '
                f'stroke="{theme.context_line}" stroke-width="0.95" stroke-opacity="0.8">'
                f"<title>{q_lbl}</title></line>"
            )

    # Bold highlighted entity dot with subtle halo
    entity_name = label or "Target"
    if entity_val is not None:
        dot_tip = f"{entity_name}: {_fmt_val(entity_val, unit=unit)} (#{pos_i}/{tot_i}, p{pct_int}, {tier})"
    else:
        dot_tip = f"{entity_name}: #{pos_i}/{tot_i} (p{pct_int}, {tier})"
    svg_parts.append(
        f'<g><title>{html.escape(dot_tip)}</title>'
        f'<circle cx="{entity_x:.2f}" cy="{cy:.2f}" r="4.1" '
        f'fill="{dot_color}" fill-opacity="{0.24 if is_dark else 0.16:.2f}"/>'
        f'<circle cx="{entity_x:.2f}" cy="{cy:.2f}" r="2.8" '
        f'fill="{dot_color}" stroke="{theme.background}" stroke-width="0.9"/></g>'
    )

    # 10-slot position ruler (rightmost slot = #1 best)
    slots = 10
    slot_idx = max(0, min(slots - 1, round(rank_frac * (slots - 1))))
    u_buf = ["·"] * slots
    a_buf = ["."] * slots
    u_buf[slot_idx] = "●"
    a_buf[slot_idx] = "*"
    u_glyph = f"[{''.join(u_buf)}]"
    a_glyph = f"[{''.join(a_buf)}]"

    compact_val = f"#{pos_i}/{tot_i}"
    val_str = f"#{pos_i}/{tot_i} (p{pct_int})"
    prefix = f"{label}: " if label else ""

    facts: list[str] = [f"{prefix}rank #{pos_i} of {tot_i} (p{pct_int}, {tier})"]
    if cohort is not None and entity_val is not None and med_val is not None and v_min is not None and v_max is not None:
        facts.append(
            f"Value {_fmt_val(entity_val, unit=unit)} vs cohort median {_fmt_val(med_val, unit=unit)} "
            f"(range {_fmt_val(v_min, unit=unit)} to {_fmt_val(v_max, unit=unit)})"
        )
        if not higher_is_better:
            facts.append("Lower values rank higher (smaller is better)")
    elif tot_i > 1:
        beats = tot_i - pos_i
        peer_word = "peer" if tot_i - 1 == 1 else "peers"
        facts.append(f"Ranks ahead of {beats} of {tot_i - 1} {peer_word}")

    alt = f"{prefix}rank {val_str} ({tier})"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        name = label or "Target"
        if cohort is not None and entity_val is not None and len(cohort) >= 3:
            mint = _require_mintfig()
            distribution = mint.distribution

            panel = distribution(
                {"Cohort": cohort},
                reference=(entity_val, f"{name} ({compact_val})"),
                title=f"{name} ranks {val_str} in cohort of {tot_i}",
                label=label or "Value",
                unit=unit,
            )
            return mint.explain(f"{name} ranks {val_str} ({tier})", panel, style=_mintfig_style_name(theme))

        mint = _require_mintfig()
        compare = mint.compare

        if cohort is not None and entity_val is not None:
            items: dict[str, float] = {name: entity_val}
            for idx, pv in enumerate(peers):
                pkey = f"Peer {idx + 1}" if len(peers) > 1 else "Peer"
                if pkey == name:
                    pkey = f"Cohort {pkey}"
                items[pkey] = pv
            panel = compare(
                items,
                title=f"{name} ranks {val_str} in cohort of {tot_i}",
                label=label or "Value",
                unit=unit,
                highlight=name,
            )
            return mint.explain(f"{name} ranks {val_str} ({tier})", panel, style=_mintfig_style_name(theme))

        median_key = "Cohort median" if name != "Cohort median" else "Median benchmark"
        top_q_key = "Top quartile" if name != "Top quartile" else "Top quartile benchmark"
        panel = compare(
            {
                name: round(percentile, 1),
                median_key: 50.0,
                top_q_key: 75.0,
            },
            title=f"{name} stands at {val_str} ({tier})",
            label="Cohort percentile",
            unit="%",
            highlight=name,
            baseline=median_key,
        )
        return mint.explain(f"{name} ranks {val_str} ({tier})", panel, style=_mintfig_style_name(theme))

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="rank",
        svg=svg,
        text=u_glyph,
        ascii_text=a_glyph,
        value_text=val_str,
        compact_value=compact_val,
        alt_text=alt,
        facts=facts,
        theme=theme,
        label=label,
        unit=unit,
        data={
            "position": pos_i,
            "total": tot_i,
            "percentile": percentile,
            "tier": tier,
            "higher_is_better": higher_is_better,
            "value": entity_val,
            "cohort_size": tot_i,
        },
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 3. mintchip.dual_spark — Dual-series trajectory & divergence sparkline
# --------------------------------------------------------------------------- #


def _clean_zero(diff: float, a: float, b: float) -> float:
    if abs(diff) <= 1e-12 * max(1.0, abs(a), abs(b)):
        return 0.0
    return diff


def _count_crossovers(diffs: Sequence[float]) -> int:
    """Count sign reversals across a sequence of paired differences ``a - b``."""
    crossovers = 0
    last_sign = 0
    for d in diffs:
        sign = 1 if d > 0.0 else (-1 if d < 0.0 else 0)
        if sign != 0:
            if last_sign != 0 and sign != last_sign:
                crossovers += 1
            last_sign = sign
    return crossovers


def dual_spark(
    series_a: Sequence[float | None],
    series_b: Sequence[float | None],
    *,
    labels: tuple[str, str] = ("A", "B"),
    label: str | None = None,
    unit: str | None = None,
    width: int = 74,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a dual-series trajectory & divergence sparkline.

    Draws series A as a solid primary line and series B as a dashed warm-accent
    line with translucent crossover-aware gap shading between them (tinted
    primary where ``A >= B``, warm accent where ``B > A``) plus endpoint dots.
    """
    if (
        isinstance(series_a, (str, bytes))
        or isinstance(series_b, (str, bytes))
        or not isinstance(series_a, Sequence)
        or not isinstance(series_b, Sequence)
    ):
        raise ChipError(
            "inline.dual_spark requires two numeric sequences for series_a and series_b.",
            fix_hint="Pass e.g. mintchip.dual_spark([1.0, 0.6, 0.42], [1.1, 0.72, 0.61]).",
        )
    if (
        isinstance(labels, (str, bytes))
        or not isinstance(labels, Sequence)
        or len(labels) != 2
    ):
        raise ChipError(
            "inline.dual_spark labels= must be a 2-tuple of series names.",
            fix_hint='Pass e.g. labels=("train", "val").',
        )

    raw_a = list(series_a)
    raw_b = list(series_b)
    if len(raw_a) != len(raw_b):
        raise ChipError(
            f"inline.dual_spark requires equal-length series; got {len(raw_a)} and {len(raw_b)}.",
            fix_hint="Align series_a and series_b to the same step index (use None for missing steps).",
        )

    pairs: list[tuple[int, float, float]] = [
        (i, float(a), float(b))
        for i, (a, b) in enumerate(zip(raw_a, raw_b, strict=True))
        if _is_finite(a) and _is_finite(b)
    ]
    if len(pairs) < 2:
        raise ChipError(
            "inline.dual_spark requires at least 2 paired finite points.",
            fix_hint="Pass two sequences with 2+ aligned finite numbers.",
        )

    name_a, name_b = str(labels[0]), str(labels[1])
    theme = _resolve_theme(style, palette=palette, accent=accent)
    is_dark = relative_luminance(theme.background) < 0.35

    all_vals = [float(v) for v in raw_a if _is_finite(v)] + [
        float(v) for v in raw_b if _is_finite(v)
    ]
    lo, hi = min(all_vals), max(all_vals)
    span = hi - lo

    pad_x = 3.2
    pad_y = 2.4
    inner_w = max(width - 2.0 * pad_x, 4.0)
    inner_h = max(height - 2.0 * pad_y, 4.0)
    n_slots = max(len(raw_a) - 1, 1)

    def _x(idx: int) -> float:
        return pad_x + (idx / n_slots) * inner_w

    def _y(val: float) -> float:
        if span <= 0.0:
            return height / 2.0
        return pad_y + (1.0 - (val - lo) / span) * inner_h

    color_a = theme.series_colors[0]
    color_b = theme.accent_colors[0]
    if color_b.lower() == color_a.lower():
        color_b = theme.muted

    svg_parts: list[str] = []

    # 1. Crossover-aware shaded polygons between series A and series B
    # Split paired points into contiguous index runs (break across None/NaN gaps)
    paired_runs: list[list[tuple[int, float, float]]] = []
    cur_run: list[tuple[int, float, float]] = []
    for i, (a, b) in enumerate(zip(raw_a, raw_b, strict=True)):
        if _is_finite(a) and _is_finite(b):
            cur_run.append((i, float(a), float(b)))  # type: ignore[arg-type]
        elif cur_run:
            paired_runs.append(cur_run)
            cur_run = []
    if cur_run:
        paired_runs.append(cur_run)

    # Each region is (sign: +1 for A>=B else -1, list of (x, y_a, y_b))
    regions: list[tuple[int, list[tuple[float, float, float]]]] = []

    def _add_segment(sign: int, p0: tuple[float, float, float], p1: tuple[float, float, float]) -> None:
        if regions and regions[-1][0] == sign and regions[-1][1][-1] == p0:
            regions[-1][1].append(p1)
        else:
            regions.append((sign, [p0, p1]))

    for run in paired_runs:
        if len(run) < 2:
            continue
        for (i0, a0, b0), (i1, a1, b1) in itertools.pairwise(run):
            d0 = _clean_zero(a0 - b0, a0, b0)
            d1 = _clean_zero(a1 - b1, a1, b1)
            p0 = (_x(i0), _y(a0), _y(b0))
            p1 = (_x(i1), _y(a1), _y(b1))
            if d0 == 0.0 and d1 == 0.0:
                continue
            if d0 >= 0.0 and d1 >= 0.0:
                _add_segment(1, p0, p1)
            elif d0 <= 0.0 and d1 <= 0.0:
                _add_segment(-1, p0, p1)
            else:
                # Exact linear intersection between step i0 and step i1
                frac = d0 / (d0 - d1)
                xc = p0[0] + frac * (p1[0] - p0[0])
                yc = p0[1] + frac * (p1[1] - p0[1])
                pc = (xc, yc, yc)
                _add_segment(1 if d0 > 0.0 else -1, p0, pc)
                _add_segment(1 if d1 > 0.0 else -1, pc, p1)

    alpha_a = 0.22 if is_dark else 0.16
    alpha_b = 0.24 if is_dark else 0.18
    for sign, verts in regions:
        top_pts = [f"{x:.2f},{ya:.2f}" for x, ya, _ in verts]
        bot_pts = [f"{x:.2f},{yb:.2f}" for x, _, yb in reversed(verts)]
        poly_pts = " ".join([*top_pts, *bot_pts])
        fill_c = color_a if sign > 0 else color_b
        fill_op = alpha_a if sign > 0 else alpha_b
        reg_tip = f"{name_a} ≥ {name_b}" if sign > 0 else f"{name_b} > {name_a}"
        svg_parts.append(
            f'<polygon points="{poly_pts}" fill="{fill_c}" fill-opacity="{fill_op:.2f}">'
            f"<title>{html.escape(reg_tip)}</title></polygon>"
        )

    # 2. Split each individual series across None/NaN gaps and draw polylines
    def _segments(raw: Sequence[float | None]) -> list[list[tuple[int, float]]]:
        segs: list[list[tuple[int, float]]] = []
        cur: list[tuple[int, float]] = []
        for idx, val in enumerate(raw):
            if _is_finite(val):
                cur.append((idx, float(val)))  # type: ignore[arg-type]
            elif cur:
                segs.append(cur)
                cur = []
        if cur:
            segs.append(cur)
        return segs

    segs_b = _segments(raw_b)
    segs_a = _segments(raw_a)

    pts_b = [(i, float(v)) for i, v in enumerate(raw_b) if _is_finite(v)]
    pts_a = [(i, float(v)) for i, v in enumerate(raw_a) if _is_finite(v)]
    tip_b_line = (
        f"{name_b}: {_fmt_val(pts_b[0][1], unit=unit)} → {_fmt_val(pts_b[-1][1], unit=unit)}"
    )
    tip_a_line = (
        f"{name_a}: {_fmt_val(pts_a[0][1], unit=unit)} → {_fmt_val(pts_a[-1][1], unit=unit)}"
    )

    for seg in segs_b:
        if len(seg) >= 2:
            coords = " ".join(f"{_x(i):.2f},{_y(v):.2f}" for i, v in seg)
            svg_parts.append(
                f'<polyline points="{coords}" fill="none" stroke="{color_b}" '
                f'stroke-width="1.2" stroke-dasharray="2.6,1.5" stroke-opacity="0.90" '
                f'stroke-linecap="round" stroke-linejoin="round">'
                f"<title>{html.escape(tip_b_line)}</title></polyline>"
            )
        elif seg:
            si, sv = seg[0]
            svg_parts.append(
                f'<circle cx="{_x(si):.2f}" cy="{_y(sv):.2f}" r="1.35" '
                f'fill="{theme.background}" stroke="{color_b}" stroke-width="1.0">'
                f"<title>{html.escape(f'{name_b}: {_fmt_val(sv, unit=unit)}')}</title></circle>"
            )

    for seg in segs_a:
        if len(seg) >= 2:
            coords = " ".join(f"{_x(i):.2f},{_y(v):.2f}" for i, v in seg)
            svg_parts.append(
                f'<polyline points="{coords}" fill="none" stroke="{color_a}" '
                f'stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round">'
                f"<title>{html.escape(tip_a_line)}</title></polyline>"
            )
        elif seg:
            si, sv = seg[0]
            svg_parts.append(
                f'<circle cx="{_x(si):.2f}" cy="{_y(sv):.2f}" r="1.4" '
                f'fill="{color_a}">'
                f"<title>{html.escape(f'{name_a}: {_fmt_val(sv, unit=unit)}')}</title></circle>"
            )

    # 3. Endpoint dots (hollow warm ring for B, solid primary dot for A)
    end_bi, end_bv = pts_b[-1]
    end_ai, end_av = pts_a[-1]
    svg_parts.append(
        f'<circle cx="{_x(end_bi):.2f}" cy="{_y(end_bv):.2f}" r="1.95" '
        f'fill="{theme.background}" stroke="{color_b}" stroke-width="1.2">'
        f"<title>{html.escape(f'{name_b} latest: {_fmt_val(end_bv, unit=unit)}')}</title></circle>"
    )
    svg_parts.append(
        f'<circle cx="{_x(end_ai):.2f}" cy="{_y(end_av):.2f}" r="2.15" '
        f'fill="{color_a}" stroke="{theme.background}" stroke-width="0.75">'
        f"<title>{html.escape(f'{name_a} latest: {_fmt_val(end_av, unit=unit)}')}</title></circle>"
    )

    # 4. Divergence metrics & Unicode/ASCII |A - B| magnitude sparkline
    diffs = [_clean_zero(a - b, a, b) for _, a, b in pairs]
    abs_gaps = [abs(d) for d in diffs]
    crossovers = _count_crossovers(diffs)

    start_i = pairs[0][0]
    end_i, end_a, end_b = pairs[-1]
    start_gap = diffs[0]
    end_gap = diffs[-1]

    max_pos = max(range(len(pairs)), key=lambda k: abs_gaps[k])
    max_div_step = pairs[max_pos][0]
    max_div_abs = abs_gaps[max_pos]
    max_div_signed = diffs[max_pos]

    sample_gaps = abs_gaps
    if len(sample_gaps) > 12:
        step = (len(sample_gaps) - 1) / 11.0
        sample_gaps = [sample_gaps[round(k * step)] for k in range(12)]
    max_sample = max(sample_gaps)
    u_chars: list[str] = []
    a_chars: list[str] = []
    for g in sample_gaps:
        frac = 0.0 if max_sample <= 0.0 else g / max_sample
        idx = max(0, min(len(_SPARK_BLOCKS) - 1, round(frac * (len(_SPARK_BLOCKS) - 1))))
        u_chars.append(_SPARK_BLOCKS[idx])
        a_chars.append(_ASCII_SPARK[idx])
    u_glyph = f"[{''.join(u_chars)}]"
    a_glyph = f"[{''.join(a_chars)}]"

    a_end_str = _fmt_val(end_a, unit=unit)
    b_end_str = _fmt_val(end_b, unit=unit)
    delta_str = _fmt_val(end_gap, unit=unit, signed=True)
    compact_val = f"Δ{delta_str}"
    val_str = f"{a_end_str} vs {b_end_str} ({compact_val})"
    prefix = f"{label}: " if label else ""

    cross_word = "crossover" if crossovers == 1 else "crossovers"
    facts = [
        f"{prefix}{name_a} vs {name_b}: latest {a_end_str} vs {b_end_str} (end gap {delta_str})",
        (
            f"Start gap {_fmt_val(start_gap, unit=unit, signed=True)} (step {start_i}) → "
            f"end gap {delta_str} (step {end_i})"
        ),
        (
            f"Max divergence {_fmt_val(max_div_abs, unit=unit)} "
            f"({_fmt_val(max_div_signed, unit=unit, signed=True)}) at step {max_div_step}"
        ),
        f"{crossovers} {cross_word} across {len(pairs)} paired steps",
    ]
    alt = (
        f"{prefix}{name_a} vs {name_b} dual sparkline ending at {val_str} "
        f"({crossovers} {cross_word})"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        trend = mint.trend

        x_idx = list(range(len(raw_a)))
        k_a, k_b = (name_a, name_b) if name_a != name_b else (f"{name_a} (1)", f"{name_b} (2)")
        series_map = {
            k_a: [float(v) if _is_finite(v) else None for v in raw_a],
            k_b: [float(v) if _is_finite(v) else None for v in raw_b],
        }
        panel = trend(
            x_idx,
            series_map,
            title=f"{prefix}{k_a} vs {k_b} ends at {val_str}",
            label=label or "Value",
            x_label="Step",
            unit=unit,
            highlight=k_a,
            baseline=k_b,
        )
        return mint.explain(
            f"{prefix}{k_a} vs {k_b} gap {delta_str} ({crossovers} {cross_word})",
            panel,
            style=_mintfig_style_name(theme),
        )

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="dual_spark",
        svg=svg,
        text=u_glyph,
        ascii_text=a_glyph,
        value_text=val_str,
        compact_value=compact_val,
        alt_text=alt,
        facts=facts,
        theme=theme,
        label=label,
        unit=unit,
        data={
            "series_a": raw_a,
            "series_b": raw_b,
            "labels": [name_a, name_b],
            "start_gap": start_gap,
            "end_gap": end_gap,
            "max_divergence": max_div_abs,
            "max_divergence_signed": max_div_signed,
            "max_divergence_step": max_div_step,
            "crossovers": crossovers,
            "n_paired": len(pairs),
        },
        expand_explanation=exp_obj,
    )
