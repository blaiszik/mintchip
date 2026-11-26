"""Composition & Flow word-sized inline components (``share``, ``funnel``, ``ratio``).

Provides Tufte word-sized micro-graphics for part-to-whole composition,
sequential pipeline attrition, and Gigerenzer/Hullman natural-frequency icon
arrays. Every component renders as both crisp Unicode/ASCII text and rich,
themed inline SVG with tooltips, light/dark support, and ``expand=True`` full
``mint.explain`` figures.
"""

from __future__ import annotations

import html
import math
from collections.abc import Mapping, Sequence
from fractions import Fraction
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
from .themes import Theme

__all__ = [
    "funnel",
    "ratio",
    "share",
]

_SHARE_UNICODE_PALETTES: dict[int, tuple[str, ...]] = {
    1: ("█",),
    2: ("█", "░"),
    3: ("█", "▓", "░"),
    4: ("█", "▓", "▒", "░"),
    5: ("█", "▓", "▒", "░", "·"),
}

_SHARE_ASCII_PALETTES: dict[int, tuple[str, ...]] = {
    1: ("#",),
    2: ("#", "."),
    3: ("#", "=", "."),
    4: ("#", "=", "-", "."),
    5: ("#", "=", "-", ":", "."),
}


def _fmt_pct(pct: float) -> str:
    """Format a percentage cleanly (integer when >=10% or near whole, else 1 decimal)."""
    ap = abs(pct)
    if ap >= 10.0 or abs(pct - round(pct)) < 0.05:
        return f"{round(pct)}%"
    return f"{pct:.1f}%"


def _fmt_share_part_pct(pct: float) -> str:
    """Format a single share component without trailing ``%`` for ``62/28/10%``."""
    if pct <= 0.0:
        return "0"
    if pct < 0.1:
        return "<0.1"
    if pct < 1.0:
        return f"{pct:.1f}"
    return f"{round(pct)}"


def _validate_dimensions(width: int | None, height: int, *, name: str) -> None:
    if width is not None and (isinstance(width, bool) or width <= 0):
        raise ChipError(
            f"inline.{name} width must be a positive integer; got {width!r}.",
            fix_hint="Pass a positive pixel width, e.g. width=72.",
        )
    if isinstance(height, bool) or height <= 0:
        raise ChipError(
            f"inline.{name} height must be a positive integer; got {height!r}.",
            fix_hint="Pass a positive pixel height, e.g. height=14.",
        )


def _allocate_cells(fracs: Sequence[float], total_cells: int) -> list[int]:
    """Largest-remainder (Hamilton) allocation of integer cells summing to ``total_cells``."""
    exact = [max(0.0, f) * total_cells for f in fracs]
    floors = [math.floor(x) for x in exact]
    remainder = total_cells - sum(floors)
    if remainder > 0:
        order = sorted(
            range(len(fracs)),
            key=lambda i: (exact[i] - floors[i], exact[i]),
            reverse=True,
        )
        for idx in order[:remainder]:
            floors[idx] += 1
    return floors


def _parse_named_or_seq(
    raw: Any,
    *,
    what: str,
    default_prefix: str,
    fix_hint: str,
) -> tuple[list[tuple[str, float]], bool]:
    """Normalize a mapping, sequence of ``(name, val)`` pairs, or sequence of floats."""
    items: list[tuple[str, float]] = []
    is_named = False

    if isinstance(raw, Mapping) or (hasattr(raw, "items") and callable(raw.items)):
        is_named = True
        for raw_k, raw_v in raw.items():
            if not _is_finite(raw_v):
                raise ChipError(
                    f"{what}[{str(raw_k)!r}] must be a finite number; got {raw_v!r}.",
                    fix_hint=fix_hint,
                )
            items.append((str(raw_k), float(raw_v)))
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        seq = list(raw)
        if not seq:
            raise ChipError(f"{what} cannot be empty.", fix_hint=fix_hint)
        first = seq[0]
        if (
            isinstance(first, Sequence)
            and not isinstance(first, (str, bytes))
            and len(first) == 2
        ):
            is_named = True
            seen: set[str] = set()
            for idx, entry in enumerate(seq):
                if (
                    isinstance(entry, (str, bytes))
                    or not isinstance(entry, Sequence)
                    or len(entry) != 2
                ):
                    raise ChipError(
                        f"{what}[{idx}] must be a (name, value) pair.",
                        fix_hint=fix_hint,
                    )
                nm = str(entry[0])
                if nm in seen:
                    raise ChipError(
                        f"{what} repeats the name {nm!r}.",
                        fix_hint="Give each entry a unique name.",
                    )
                seen.add(nm)
                if not _is_finite(entry[1]):
                    raise ChipError(
                        f"{what}[{nm!r}] must be a finite number; got {entry[1]!r}.",
                        fix_hint=fix_hint,
                    )
                items.append((nm, float(entry[1])))
        else:
            for idx, val in enumerate(seq):
                if not _is_finite(val):
                    raise ChipError(
                        f"{what}[{idx}] must be a finite number; got {val!r}.",
                        fix_hint=fix_hint,
                    )
                items.append((f"{default_prefix} {idx + 1}", float(val)))
    else:
        raise ChipError(
            f"{what} must be a mapping or numeric sequence; got {type(raw).__name__}.",
            fix_hint=fix_hint,
        )

    if not items:
        raise ChipError(f"{what} cannot be empty.", fix_hint=fix_hint)
    return items, is_named


# --------------------------------------------------------------------------- #
# 1. mintchip.share — 100% stacked proportion bar (never a pie)
# --------------------------------------------------------------------------- #


def share(
    parts: Mapping[str, float] | Sequence[float] | Sequence[tuple[str, float]],
    *,
    label: str | None = None,
    unit: str | None = None,
    width: int = 72,
    height: int = 14,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized 100% stacked proportion bar (never a pie).

    Accepts a mapping ``{name: positive_value}``, a sequence of ``(name, value)``
    pairs, or a sequence of positive numbers. Parts are ordered largest-first;
    any parts beyond the top 4 are folded into a muted ``"Other"`` segment.
    """
    _validate_dimensions(width, height, name="share")
    fix_hint = 'Pass positive parts, e.g. mintchip.share({"Code": 62, "Docs": 28, "Tests": 10}).'
    raw_items, is_named = _parse_named_or_seq(
        parts,
        what="inline.share(parts)",
        default_prefix="Part",
        fix_hint=fix_hint,
    )

    for nm, val in raw_items:
        if val <= 0.0:
            raise ChipError(
                f"inline.share requires positive values; got {val:g} for {nm!r}.",
                fix_hint="Pass strictly positive values for every part.",
            )

    total = sum(v for _, v in raw_items)
    if not math.isfinite(total) or total <= 0.0:
        raise ChipError(
            "inline.share parts must sum to a finite positive total.",
            fix_hint=fix_hint,
        )

    theme = _resolve_theme(style, palette=palette, accent=accent)

    # Sort descending (Python's timsort is stable for ties) and fold past top 4
    ranked = sorted(raw_items, key=lambda kv: kv[1], reverse=True)
    kept = ranked[:4]
    rest = ranked[4:]

    segments: list[tuple[str, float, bool]] = [(nm, val, False) for nm, val in kept]
    other_name: str | None = None
    if rest:
        kept_names = {nm for nm, _ in kept}
        other_name = "Other" if "Other" not in kept_names else f"Other ({len(rest)})"
        segments.append((other_name, sum(v for _, v in rest), True))

    fracs = [val / total for _, val, _ in segments]
    pcts = [100.0 * f for f in fracs]

    # SVG: crisp 100% stacked bar with thin theme.background separators + per-segment <title>
    pad_x = 1.0
    inner_w = max(width - 2.0 * pad_x, 8.0)
    bar_h = max(height - 4.0, 6.0)
    bar_y = (height - bar_h) / 2.0

    svg_parts: list[str] = [
        (
            f'<rect x="{pad_x:.1f}" y="{bar_y:.2f}" width="{inner_w:.1f}" height="{bar_h:.2f}" '
            f'fill="{theme.grid}" fill-opacity="0.30" rx="1.2"/>'
        )
    ]

    xs: list[float] = [pad_x]
    acc = 0.0
    for idx, frac in enumerate(fracs):
        acc += frac
        if idx == len(fracs) - 1:
            xs.append(pad_x + inner_w)
        else:
            xs.append(pad_x + acc * inner_w)

    rx_attr = ' rx="1.2"' if len(segments) == 1 else ""
    for idx, ((nm, val, is_other), pct) in enumerate(zip(segments, pcts, strict=True)):
        sx = xs[idx]
        sw = max(xs[idx + 1] - sx, 0.0)
        fill = (
            theme.context_fill
            if is_other
            else theme.series_colors[idx % len(theme.series_colors)]
        )
        tip = f"{nm}: {pct:.1f}% ({_fmt_val(val, unit=unit)})"
        svg_parts.append(
            f'<rect x="{sx:.2f}" y="{bar_y:.2f}" width="{sw:.2f}" height="{bar_h:.2f}" '
            f'fill="{fill}"{rx_attr}><title>{html.escape(tip)}</title></rect>'
        )

    # Thin background separators between adjacent segments
    for boundary_x in xs[1:-1]:
        svg_parts.append(
            f'<line x1="{boundary_x:.2f}" y1="{bar_y - 0.25:.2f}" '
            f'x2="{boundary_x:.2f}" y2="{bar_y + bar_h + 0.25:.2f}" '
            f'stroke="{theme.background}" stroke-width="1.1"/>'
        )

    # 10-cell luminance-shaded Unicode & ASCII stacked bar
    cell_counts = _allocate_cells(fracs, 10)
    k = len(segments)
    u_palette = _SHARE_UNICODE_PALETTES[k]
    a_palette = _SHARE_ASCII_PALETTES[k]
    u_cells = "".join(u_palette[i] * cnt for i, cnt in enumerate(cell_counts))
    a_cells = "".join(a_palette[i] * cnt for i, cnt in enumerate(cell_counts))
    u_glyph = f"[{u_cells}]"
    a_glyph = f"[{a_cells}]"

    # Value & compact readouts
    val_str = "/".join(_fmt_share_part_pct(p) for p in pcts) + "%"
    top_name, top_val, _ = segments[0]
    top_pct = pcts[0]
    top_pct_str = _fmt_share_part_pct(top_pct) + "%"
    if is_named and len(top_name) <= 14:
        compact_val = f"{top_name} {top_pct_str}"
    else:
        compact_val = f"{top_pct_str} top"

    prefix = f"{label}: " if label else ""
    shares_desc = ", ".join(
        f"{nm} {p:.1f}%" for (nm, _, _), p in zip(segments, pcts, strict=True)
    )
    facts = [
        f"{prefix}total {_fmt_val(total, unit=unit)} across {len(raw_items)} part"
        + ("s" if len(raw_items) != 1 else ""),
        f"Largest: {top_name} {top_pct:.1f}% ({_fmt_val(top_val, unit=unit)})",
        f"Shares: {shares_desc}",
    ]
    if rest and other_name is not None:
        other_val = segments[-1][1]
        other_pct = pcts[-1]
        facts.append(
            f"{len(rest)} smaller part{'s' if len(rest) != 1 else ''} folded into "
            f"{other_name} ({other_pct:.1f}%, {_fmt_val(other_val, unit=unit)})"
        )

    alt = f"{prefix}composition bar: {shares_desc}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.16em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        explain_share = mint.share

        part_map = {nm: val for nm, val in ranked}
        panel = explain_share(
            part_map,
            title=f"{top_name} accounts for {_fmt_pct(top_pct)} of {label or 'total'}",
            label=label or "total",
            unit=unit,
            highlight=top_name,
        )
        return mint.explain(
            f"{prefix}{top_name} leads at {top_pct:.1f}% ({val_str})",
            panel,
            style=_mintfig_style_name(theme),
        )

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="share",
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
            "parts": [
                {"name": nm, "value": val, "pct": p, "is_other": is_other}
                for (nm, val, is_other), p in zip(segments, pcts, strict=True)
            ],
            "total": total,
            "folded_count": len(rest),
            "top_name": top_name,
            "top_pct": top_pct,
        },
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 2. mintchip.funnel — Micro-attrition / pipeline cascade
# --------------------------------------------------------------------------- #


def funnel(
    stages: Mapping[str, float] | Sequence[float] | Sequence[tuple[str, float]],
    *,
    label: str | None = None,
    width: int = 70,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized micro-attrition / pipeline cascade funnel.

    Accepts a mapping ``{stage_name: count}``, a sequence of ``(stage_name, count)``
    pairs, or a sequence of non-negative counts (with a strictly positive first stage).
    Highlights the stage with the steepest drop in the theme's warm accent color.
    """
    _validate_dimensions(width, height, name="funnel")
    fix_hint = (
        'Pass 2+ stages with non-negative counts (first > 0), e.g. '
        'mintchip.funnel({"Screened": 1200, "Eligible": 520, "Enrolled": 290}).'
    )
    items, _ = _parse_named_or_seq(
        stages,
        what="inline.funnel(stages)",
        default_prefix="Stage",
        fix_hint=fix_hint,
    )
    if len(items) < 2:
        raise ChipError(
            "inline.funnel requires at least 2 stages to show attrition or retention.",
            fix_hint=fix_hint,
        )
    for nm, val in items:
        if val < 0.0:
            raise ChipError(
                f"inline.funnel stage {nm!r} has negative count {val:g}.",
                fix_hint="Funnel counts must be non-negative.",
            )
    if items[0][1] <= 0.0:
        raise ChipError(
            f"inline.funnel first stage {items[0][0]!r} must be positive; got {items[0][1]:g}.",
            fix_hint="Start the funnel with a positive initial cohort or volume.",
        )

    theme = _resolve_theme(style, palette=palette, accent=accent)
    stage_names = [nm for nm, _ in items]
    counts = [val for _, val in items]
    n = len(counts)
    start_val = counts[0]
    end_val = counts[-1]
    scale_max = max(start_val, max(counts))

    pct_retained = [100.0 * v / start_val for v in counts]
    overall_retention = pct_retained[-1]

    # Identify steepest absolute drop across consecutive stages
    steepest_drop_idx: int | None = None
    steepest_drop_count = 0.0
    steepest_drop_pct = 0.0
    for i in range(1, n):
        drop = counts[i - 1] - counts[i]
        if drop > steepest_drop_count:
            steepest_drop_count = drop
            steepest_drop_idx = i
            steepest_drop_pct = (100.0 * drop / counts[i - 1]) if counts[i - 1] > 0 else 0.0

    # SVG: vertical step-bars scaled linearly to stage 0 (=100%) + connecting trapezoids
    pad_x = 1.5
    pad_top = 1.5
    pad_bot = 1.8
    inner_w = max(width - 2.0 * pad_x, 8.0)
    inner_h = max(height - pad_top - pad_bot, 6.0)
    base_y = height - pad_bot

    gap = min(3.2, inner_w / max(n * 3.5, 1.0)) if n > 1 else 0.0
    bar_w = max((inner_w - (n - 1) * gap) / n, 1.2)
    # Recompute gap if bar_w clamped for very large n so bars stay inside viewBox
    if n > 1 and n * bar_w + (n - 1) * gap > inner_w:
        gap = max((inner_w - n * bar_w) / (n - 1), 0.3)
        bar_w = max((inner_w - (n - 1) * gap) / n, 0.8)

    primary = theme.series_colors[0]
    accent_c = theme.accent_colors[0] if theme.accent_colors else theme.series_colors[1]

    rects_geom: list[tuple[float, float, float, float]] = []
    for i, val in enumerate(counts):
        x0 = pad_x + i * (bar_w + gap)
        x1 = x0 + bar_w
        if val > 0.0:
            bh = max((val / scale_max) * inner_h, 1.0)
        else:
            bh = 0.0
        by = base_y - bh
        rects_geom.append((x0, x1, by, bh))

    svg_parts: list[str] = [
        (
            f'<line x1="{pad_x:.1f}" y1="{base_y:.2f}" x2="{width - pad_x:.1f}" '
            f'y2="{base_y:.2f}" stroke="{theme.grid}" stroke-width="0.8"/>'
        )
    ]

    # Subtle connecting trapezoids & cascade slope hairlines between consecutive stages
    for i in range(1, n):
        _, prev_x1, prev_y, _ = rects_geom[i - 1]
        curr_x0, _, curr_y, _ = rects_geom[i]
        is_steep = i == steepest_drop_idx
        trap_col = accent_c if is_steep else primary
        trap_op = "0.26" if is_steep else "0.15"
        poly = (
            f"{prev_x1:.2f},{prev_y:.2f} {curr_x0:.2f},{curr_y:.2f} "
            f"{curr_x0:.2f},{base_y:.2f} {prev_x1:.2f},{base_y:.2f}"
        )
        svg_parts.append(
            f'<polygon points="{poly}" fill="{trap_col}" fill-opacity="{trap_op}"/>'
        )
        svg_parts.append(
            f'<line x1="{prev_x1:.2f}" y1="{prev_y:.2f}" x2="{curr_x0:.2f}" y2="{curr_y:.2f}" '
            f'stroke="{trap_col}" stroke-opacity="0.55" stroke-width="0.75"/>'
        )

    # Step-bars with per-stage <title> tooltips
    for i, ((nm, val), pct, (x0, _, by, bh)) in enumerate(
        zip(items, pct_retained, rects_geom, strict=True)
    ):
        is_steep = i == steepest_drop_idx
        tip = f"{nm}: {_fmt_val(val)} ({pct:.1f}% retained)"
        if is_steep:
            tip += (
                f"; steepest drop \N{MINUS SIGN}{_fmt_val(steepest_drop_count)} "
                f"(\N{MINUS SIGN}{steepest_drop_pct:.1f}%)"
            )
        if bh > 0.0:
            if is_steep:
                fill, opacity = accent_c, "0.95"
            elif i == 0:
                fill, opacity = primary, "0.92"
            elif i == n - 1:
                fill, opacity = primary, "0.86"
            else:
                fill, opacity = primary, "0.70"
            svg_parts.append(
                f'<rect x="{x0:.2f}" y="{by:.2f}" width="{bar_w:.2f}" height="{bh:.2f}" '
                f'fill="{fill}" fill-opacity="{opacity}" rx="0.8">'
                f"<title>{html.escape(tip)}</title></rect>"
            )
        else:
            # Zero-count stage: faint floor stub so tooltip remains accessible
            stub_fill = accent_c if is_steep else theme.context_fill
            svg_parts.append(
                f'<rect x="{x0:.2f}" y="{base_y - 1.2:.2f}" width="{bar_w:.2f}" height="1.20" '
                f'fill="{stub_fill}" fill-opacity="0.50" rx="0.4">'
                f"<title>{html.escape(tip)}</title></rect>"
            )

    # Unicode & ASCII 8-level vertical block per stage (downsample if > 12 to stay word-sized)
    sample_counts = counts
    if len(sample_counts) > 12:
        step = (len(sample_counts) - 1) / 11.0
        sample_counts = [sample_counts[round(k * step)] for k in range(12)]
    u_chars: list[str] = []
    a_chars: list[str] = []
    max_idx = len(_SPARK_BLOCKS) - 1
    for val in sample_counts:
        frac = val / scale_max if scale_max > 0 else 0.0
        b_idx = max(0, min(max_idx, round(frac * max_idx)))
        u_chars.append(_SPARK_BLOCKS[b_idx])
        a_chars.append(_ASCII_SPARK[b_idx])
    u_glyph = f"[{''.join(u_chars)}]"
    a_glyph = f"[{''.join(a_chars)}]"

    ret_str = _fmt_pct(overall_retention)
    val_str = f"{_fmt_val(start_val)}\N{RIGHTWARDS ARROW}{_fmt_val(end_val)} ({ret_str})"
    compact_val = f"{ret_str} retained"

    prefix = f"{label}: " if label else ""
    facts = [
        (
            f"{prefix}{stage_names[0]} {_fmt_val(start_val)} \N{RIGHTWARDS ARROW} "
            f"{stage_names[-1]} {_fmt_val(end_val)} "
            f"({overall_retention:.1f}% retained across {n} stages)"
        )
    ]
    if steepest_drop_idx is not None:
        drop_stage = stage_names[steepest_drop_idx]
        prev_stage = stage_names[steepest_drop_idx - 1]
        facts.append(
            f"Steepest drop at {drop_stage} ({prev_stage} \N{RIGHTWARDS ARROW} {drop_stage}): "
            f"\N{MINUS SIGN}{_fmt_val(steepest_drop_count)} "
            f"(\N{MINUS SIGN}{steepest_drop_pct:.1f}% of prior stage)"
        )
    else:
        facts.append("No attrition drop across stages")
    if n <= 6:
        stage_summary = " \N{RIGHTWARDS ARROW} ".join(
            f"{nm} {_fmt_val(v)} ({_fmt_pct(p)})"
            for (nm, v), p in zip(items, pct_retained, strict=True)
        )
        facts.append(f"Stages: {stage_summary}")

    alt = (
        f"{prefix}funnel {stage_names[0]} {_fmt_val(start_val)} to "
        f"{stage_names[-1]} {_fmt_val(end_val)} ({overall_retention:.1f}% retained)"
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        explain_flow = mint.flow

        hl_stage = stage_names[steepest_drop_idx] if steepest_drop_idx is not None else None
        panel = explain_flow(
            [(nm, val) for nm, val in items],
            title=(
                f"{label or 'Pipeline'} retains {ret_str} "
                f"({_fmt_val(start_val)} to {_fmt_val(end_val)})"
            ),
            label=label or "Count",
            highlight=hl_stage,
        )
        takeaway = (
            f"{prefix}{_fmt_val(start_val)} \N{RIGHTWARDS ARROW} {_fmt_val(end_val)} "
            f"({ret_str} retained"
            + (
                f"; steepest drop at {stage_names[steepest_drop_idx]}"
                if steepest_drop_idx is not None
                else ""
            )
            + ")"
        )
        return mint.explain(takeaway, panel, style=_mintfig_style_name(theme))

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="funnel",
        svg=svg,
        text=u_glyph,
        ascii_text=a_glyph,
        value_text=val_str,
        compact_value=compact_val,
        alt_text=alt,
        facts=facts,
        theme=theme,
        label=label,
        data={
            "stages": [
                {"name": nm, "count": val, "pct_retained": p}
                for (nm, val), p in zip(items, pct_retained, strict=True)
            ],
            "retention_pct": overall_retention,
            "steepest_drop_stage": (
                stage_names[steepest_drop_idx] if steepest_drop_idx is not None else None
            ),
            "steepest_drop_index": steepest_drop_idx,
            "steepest_drop_count": steepest_drop_count,
            "steepest_drop_pct": steepest_drop_pct,
        },
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 3. mintchip.ratio — Natural-frequency countable icon array
# --------------------------------------------------------------------------- #


def ratio(
    count: float,
    total: int | None = None,
    *,
    units: int = 10,
    label: str | None = None,
    width: int | None = None,
    height: int = 14,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized natural-frequency countable icon array (Gigerenzer / Hullman).

    Supports two modes:
    - Exact count/total: ``ratio(3, 10)`` renders exact hits out of total.
    - Proportion: ``ratio(0.24, units=20)`` scales a proportion in ``[0, 1]`` to
      ``units`` countable icons.
    """
    _validate_dimensions(width, height, name="ratio")
    if isinstance(units, bool) or not isinstance(units, int) or units < 1 or units > 100:
        raise ChipError(
            f"inline.ratio units must be an integer between 1 and 100; got {units!r}.",
            fix_hint="Pass e.g. units=10 or units=20.",
        )

    if not _is_finite(count):
        raise ChipError(
            f"inline.ratio count/proportion must be a finite number; got {count!r}.",
            fix_hint="Pass ratio(3, 10) for exact counts or ratio(0.24, units=20) for a proportion.",
        )

    is_exact_mode = total is not None
    cnt_int: int | None = None
    tot_int: int | None = None

    if is_exact_mode:
        if not _is_finite(total):
            raise ChipError(
                f"inline.ratio total must be a positive integer; got {total!r}.",
                fix_hint="Pass whole numbers, e.g. mintchip.ratio(3, 10).",
            )
        cnt_f = float(count)
        tot_f = float(total)  # type: ignore[arg-type]
        if not cnt_f.is_integer() or not tot_f.is_integer():
            raise ChipError(
                f"inline.ratio(count, total) requires integer values; got ({count!r}, {total!r}).",
                fix_hint="Pass integers like ratio(3, 10), or omit total for a proportion like ratio(0.24, units=20).",
            )
        cnt_int = round(cnt_f)
        tot_int = round(tot_f)
        if tot_int <= 0:
            raise ChipError(
                f"inline.ratio total must be positive; got {tot_int}.",
                fix_hint="Pass a positive integer total, e.g. mintchip.ratio(3, 10).",
            )
        if cnt_int < 0 or cnt_int > tot_int:
            raise ChipError(
                f"inline.ratio count must satisfy 0 <= count <= total; got {cnt_int}/{tot_int}.",
                fix_hint="Ensure 0 <= count <= total.",
            )
        prop = cnt_int / tot_int
        if tot_int <= 20:
            n_dots = tot_int
            filled_dots = cnt_int
            exact_hits = float(cnt_int)
            is_approx = False
        else:
            n_dots = units
            exact_hits = prop * n_dots
            filled_dots = max(0, min(n_dots, round(exact_hits)))
            is_approx = abs(exact_hits - filled_dots) > 1e-9
    else:
        prop = float(count)
        if prop < 0.0 or prop > 1.0:
            raise ChipError(
                f"inline.ratio proportion must be in [0, 1] when total is omitted; got {prop:g}.",
                fix_hint="Pass a proportion in [0, 1] like ratio(0.24, units=20), or pass total like ratio(3, 10).",
            )
        n_dots = units
        exact_hits = prop * n_dots
        filled_dots = max(0, min(n_dots, round(exact_hits)))
        is_approx = abs(exact_hits - filled_dots) > 1e-9

    pct = prop * 100.0
    theme = _resolve_theme(style, palette=palette, accent=accent)

    # SVG: crisp countable dot array (1 row if <= 8 dots, else 2 rows)
    rows = 1 if n_dots <= 8 else 2
    cols = math.ceil(n_dots / rows)

    pad_x = 2.0
    if rows == 1:
        r = min(3.2, max((height - 4.0) / 2.0, 1.4))
        gap_x = 2.2
        gap_y = 0.0
    else:
        pad_y = 1.6
        gap_y = 2.0
        r = min(2.3, max((height - 2.0 * pad_y - gap_y) / 4.0, 1.2))
        gap_x = 2.0

    natural_w = math.ceil(2.0 * pad_x + cols * (2.0 * r) + max(cols - 1, 0) * gap_x)
    svg_w = int(width) if width is not None else max(natural_w, 10)

    # Fit cleanly inside explicit narrow width if provided
    avail_w = max(svg_w - 2.0 * pad_x, 4.0)
    grid_w = cols * (2.0 * r) + max(cols - 1, 0) * gap_x
    if grid_w > avail_w:
        scale_f = avail_w / grid_w
        r = max(r * scale_f, 0.9)
        gap_x = max(gap_x * scale_f, 0.8)
        grid_w = cols * (2.0 * r) + max(cols - 1, 0) * gap_x

    offset_x = pad_x + max((avail_w - grid_w) / 2.0, 0.0)
    if rows == 1:
        row_ys = [height / 2.0]
    else:
        total_h = 4.0 * r + gap_y
        top_y = (height - total_h) / 2.0 + r
        row_ys = [top_y, top_y + 2.0 * r + gap_y]

    primary = theme.series_colors[0]
    stroke_w = min(0.95, max(r * 0.4, 0.65))
    hollow_r = max(r - stroke_w / 2.0, 0.65)
    hit_desc = label or "event"

    svg_parts: list[str] = []
    for idx in range(n_dots):
        row = idx // cols
        col = idx % cols
        cx = offset_x + r + col * (2.0 * r + gap_x)
        cy = row_ys[row]
        if idx < filled_dots:
            tip = f"{hit_desc}: {idx + 1} of {filled_dots} hit" + (
                "s" if filled_dots != 1 else ""
            ) + f" (out of {n_dots})"
            svg_parts.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{primary}">'
                f"<title>{html.escape(tip)}</title></circle>"
            )
        else:
            tip = f"non-hit {idx + 1} of {n_dots}"
            svg_parts.append(
                f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{hollow_r:.2f}" '
                f'fill="{theme.background}" stroke="{theme.context_line}" '
                f'stroke-width="{stroke_w:.2f}"><title>{html.escape(tip)}</title></circle>'
            )

    # Unicode & ASCII dot array (scale cleanly to 10 dots if displayed dots > 10)
    if n_dots <= 10:
        u_total = n_dots
        u_filled = filled_dots
    else:
        u_total = 10
        u_filled = max(0, min(10, round(prop * 10)))

    u_glyph = "[" + ("●" * u_filled) + ("○" * (u_total - u_filled)) + "]"
    a_glyph = "[" + ("*" * u_filled) + ("." * (u_total - u_filled)) + "]"

    pct_str = _fmt_pct(pct)
    if is_exact_mode and cnt_int is not None and tot_int is not None:
        val_str = f"{cnt_int}/{tot_int} ({pct_str})"
        compact_val = f"{cnt_int}/{tot_int}"
    else:
        approx_mark = "~" if is_approx else ""
        val_str = f"{pct_str} ({approx_mark}{filled_dots}/{n_dots})"
        compact_val = pct_str

    prefix = f"{label}: " if label else ""
    facts: list[str] = []
    if is_exact_mode and cnt_int is not None and tot_int is not None:
        g = math.gcd(cnt_int, tot_int)
        if g > 1 and 0 < cnt_int < tot_int:
            facts.append(
                f"{prefix}exact fraction {cnt_int}/{tot_int} ({cnt_int // g}/{tot_int // g}, {pct:.1f}%)"
            )
        else:
            facts.append(f"{prefix}exact fraction {cnt_int}/{tot_int} ({pct:.1f}%)")
        facts.append(
            f"Natural frequency: {cnt_int} out of {tot_int}"
            + (f" ({label})" if label else "")
            + f" ({pct:.1f}%)"
        )
        if tot_int > 20:
            approx_word = "about " if is_approx else ""
            facts.append(
                f"Icon array displays {approx_word}{filled_dots} of {n_dots} units"
            )
    else:
        frac_obj = Fraction(prop).limit_denominator(1000)
        facts.append(
            f"{prefix}{pct:.1f}% (exact fraction {frac_obj.numerator}/{frac_obj.denominator})"
        )
        if is_approx:
            facts.append(
                f"Natural frequency: about {filled_dots} out of every {n_dots}"
                + (f" ({label})" if label else "")
                + f" ({exact_hits:.1f} expected per {n_dots})"
            )
        else:
            facts.append(
                f"Natural frequency: {filled_dots} out of every {n_dots}"
                + (f" ({label})" if label else "")
            )

    alt = f"{prefix}icon array: {val_str}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_w}" height="{height}" '
        f'viewBox="0 0 {svg_w} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.16em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        explain_share = mint.share

        hit_name = label or "Hits"
        miss_name = "Other" if hit_name != "Other" else "Remaining"
        if is_exact_mode and cnt_int is not None and tot_int is not None:
            parts_map = {hit_name: float(cnt_int), miss_name: float(tot_int - cnt_int)}
            takeaway = f"{prefix}{cnt_int} of {tot_int} ({pct:.1f}%)"
        else:
            parts_map = {hit_name: float(exact_hits), miss_name: float(n_dots - exact_hits)}
            takeaway = f"{prefix}{pct:.1f}% ({'~' if is_approx else ''}{filled_dots} of {n_dots})"
        panel = explain_share(
            parts_map,
            title=f"{hit_name} makes up {pct_str} ({compact_val})",
            label=label or "total",
            highlight=hit_name,
        )
        return mint.explain(takeaway, panel, style=_mintfig_style_name(theme))

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="ratio",
        svg=svg,
        text=u_glyph,
        ascii_text=a_glyph,
        value_text=val_str,
        compact_value=compact_val,
        alt_text=alt,
        facts=facts,
        theme=theme,
        label=label,
        data={
            "mode": "exact" if is_exact_mode else "proportion",
            "count": cnt_int,
            "total": tot_int,
            "proportion": prop,
            "pct": pct,
            "displayed_hits": filled_dots,
            "displayed_units": n_dots,
            "rows": rows,
            "cols": cols,
            "approximate": is_approx,
        },
        expand_explanation=exp_obj,
    )
