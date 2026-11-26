"""Change, attribution, and 2D relationship micro-graphics for ``mint.inline``.

Provides three Tufte word-sized inline components returning
:class:`~mintfig._inline.core.Chip`:

- :func:`delta` — paired before→after dumbbell arrow with favorable/regression
  encoding and optional shared domain.
- :func:`waterfall` — micro-attribution bridge of floating stepped bars from a
  starting value through signed contributions to a final total.
- :func:`scatter` — micro 2D scatter / correlation / Pareto frontier glyph with
  true 2D Unicode Braille (10×4 pixel grid across 5 Braille cells).
"""

from __future__ import annotations

import html
import math
from collections.abc import Mapping, Sequence
from typing import Any

from .core import (
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

__all__ = ["delta", "scatter", "waterfall"]

# Unicode Braille Patterns (U+2800..U+28FF): 2 columns × 4 rows per cell.
# Row 0 is the top (max y); row 3 is the bottom (min y).
_BRAILLE_BITS: tuple[tuple[int, int], ...] = (
    (0x01, 0x08),  # row 0: dots 1, 4
    (0x02, 0x10),  # row 1: dots 2, 5
    (0x04, 0x20),  # row 2: dots 3, 6
    (0x40, 0x80),  # row 3: dots 7, 8
)

_ASCII_SCATTER_LEVELS = (".", ",", "-", "^", "'")


def _positive_color(theme: Theme) -> str:
    """Return the theme's favorable/positive color (teal/emerald, falling back to primary)."""
    return theme.series_colors[2] if len(theme.series_colors) > 2 else theme.series_colors[0]


def _parse_domain(domain: tuple[float, float], caller: str) -> tuple[float, float]:
    if (
        isinstance(domain, (str, bytes))
        or not isinstance(domain, Sequence)
        or len(domain) != 2
        or not (_is_finite(domain[0]) and _is_finite(domain[1]))
    ):
        raise ChipError(
            f"{caller} domain must be a 2-tuple of finite numbers (low, high).",
            fix_hint="Pass e.g. domain=(0.0, 1.0) or use mintchip.shared_domain(...).",
        )
    lo, hi = sorted((float(domain[0]), float(domain[1])))
    return lo, hi


def _clip_segment(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
) -> tuple[float, float, float, float] | None:
    """Clip a 2D line segment to an axis-aligned box using Liang–Barsky."""
    dx = x1 - x0
    dy = y1 - y0
    t0, t1 = 0.0, 1.0
    for p, q in (
        (-dx, x0 - xmin),
        (dx, xmax - x0),
        (-dy, y0 - ymin),
        (dy, ymax - y0),
    ):
        if abs(p) <= 1e-15:
            if q < 0.0:
                return None
        else:
            r = q / p
            if p < 0.0:
                if r > t1:
                    return None
                t0 = max(t0, r)
            else:
                if r < t0:
                    return None
                t1 = min(t1, r)
    return (x0 + t0 * dx, y0 + t0 * dy, x0 + t1 * dx, y0 + t1 * dy)


def _pareto_upper_right(xs: Sequence[float], ys: Sequence[float]) -> list[int]:
    """Return indices of non-dominated upper-right Pareto frontier points ordered by ascending x."""
    n = len(xs)
    keep: list[int] = []
    for i in range(n):
        xi, yi = xs[i], ys[i]
        dominated = False
        for j in range(n):
            if i == j:
                continue
            xj, yj = xs[j], ys[j]
            if (
                xj >= xi - 1e-12
                and yj >= yi - 1e-12
                and (xj > xi + 1e-12 or yj > yi + 1e-12)
            ):
                dominated = True
                break
        if not dominated:
            keep.append(i)
    keep.sort(key=lambda idx: (xs[idx], -ys[idx]))
    return keep


# --------------------------------------------------------------------------- #
# 1. mintchip.delta — Paired before→after dumbbell arrow
# --------------------------------------------------------------------------- #


def delta(
    before: float,
    after: float,
    *,
    label: str | None = None,
    unit: str | None = None,
    domain: tuple[float, float] | None = None,
    higher_is_better: bool = True,
    width: int = 68,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized paired before→after dumbbell arrow (``○───▶●``).

    Encodes direction redundantly via hollow-start → arrowhead → solid-end
    geometry as well as color (primary/teal for favorable moves per
    ``higher_is_better``, warm accent for regressions, muted when unchanged).
    Pass a shared ``domain=(low, high)`` from :func:`shared_domain` to align
    multiple delta chips onto one honest scale.
    """
    if not (_is_finite(before) and _is_finite(after)):
        raise ChipError(
            "inline.delta requires finite numeric before and after values.",
            fix_hint="Pass two numbers, e.g. mintchip.delta(0.74, 0.82).",
        )

    b_val = float(before)
    a_val = float(after)
    diff = a_val - b_val
    unchanged = abs(diff) <= 1e-12
    favorable: bool | None = (
        None if unchanged else ((diff > 0.0) if higher_is_better else (diff < 0.0))
    )

    theme = _resolve_theme(style, palette=palette, accent=accent)
    pos_color = _positive_color(theme)
    neg_color = theme.accent_colors[0]
    mark_color = theme.muted if unchanged else (pos_color if favorable else neg_color)

    if domain is not None:
        d_lo, d_hi = _parse_domain(domain, "inline.delta")
    else:
        raw_lo, raw_hi = min(b_val, a_val), max(b_val, a_val)
        if unchanged:
            half = max(abs(b_val) * 0.1, 1.0)
            d_lo, d_hi = b_val - half, b_val + half
        else:
            margin = (raw_hi - raw_lo) * 0.25
            d_lo, d_hi = raw_lo - margin, raw_hi + margin

    span = d_hi - d_lo
    pad_x = 4.5
    inner_w = max(width - 2.0 * pad_x, 8.0)
    cy = height / 2.0

    def _norm(v: float) -> float:
        if span <= 1e-12:
            return 0.5
        return max(0.0, min(1.0, (v - d_lo) / span))

    def _x(v: float) -> float:
        return pad_x + _norm(v) * inner_w

    xb = _x(b_val)
    xa = _x(a_val)

    before_str = _fmt_val(b_val, unit=unit)
    after_str = _fmt_val(a_val, unit=unit)
    compact_val = _fmt_val(diff, unit=unit, signed=True)
    val_str = f"{before_str}→{after_str} ({compact_val})"

    svg_parts: list[str] = [
        # Subtle baseline ruler
        (
            f'<line x1="{pad_x:.1f}" y1="{cy:.2f}" x2="{width - pad_x:.1f}" y2="{cy:.2f}" '
            f'stroke="{theme.grid}" stroke-width="1.0"/>'
        ),
    ]
    if domain is not None and d_lo < 0.0 < d_hi:
        zx = _x(0.0)
        svg_parts.append(
            f'<line x1="{zx:.2f}" y1="{cy - 3.5:.2f}" x2="{zx:.2f}" y2="{cy + 3.5:.2f}" '
            f'stroke="{theme.zero_line}" stroke-width="0.85" stroke-opacity="0.45" '
            f'stroke-dasharray="1.5,1.2"/>'
        )

    r_start = 2.15
    r_end = 2.55
    if unchanged:
        same_tip = html.escape(f"Unchanged: {before_str}")
        svg_parts.append(
            f'<g><title>{same_tip}</title>'
            f'<circle cx="{xb:.2f}" cy="{cy:.2f}" r="2.75" fill="{theme.background}" '
            f'stroke="{theme.muted}" stroke-width="1.2"/>'
            f'<circle cx="{xb:.2f}" cy="{cy:.2f}" r="1.15" fill="{theme.muted}"/></g>'
        )
    else:
        px_dist = abs(xa - xb)
        sign = 1.0 if xa >= xb else -1.0
        if px_dist >= 8.0:
            tip_x = xa - sign * (r_end + 0.55)
            ah_len = min(4.2, max(2.6, (px_dist - r_start - r_end) * 0.45))
            ah_half = 2.2
            base_x = tip_x - sign * ah_len
            shaft_x0 = xb + sign * (r_start + 0.2)
            shaft_x1 = base_x + sign * 0.45
            if (shaft_x1 - shaft_x0) * sign > 0.2:
                svg_parts.append(
                    f'<line x1="{shaft_x0:.2f}" y1="{cy:.2f}" x2="{shaft_x1:.2f}" y2="{cy:.2f}" '
                    f'stroke="{mark_color}" stroke-width="1.55" stroke-linecap="round"/>'
                )
            svg_parts.append(
                f'<polygon points="{tip_x:.2f},{cy:.2f} '
                f'{base_x:.2f},{cy - ah_half:.2f} {base_x:.2f},{cy + ah_half:.2f}" '
                f'fill="{mark_color}"/>'
            )
        elif px_dist > 0.4:
            svg_parts.append(
                f'<line x1="{xb:.2f}" y1="{cy:.2f}" x2="{xa:.2f}" y2="{cy:.2f}" '
                f'stroke="{mark_color}" stroke-width="1.5" stroke-linecap="round"/>'
            )
            if px_dist >= 4.0:
                tip_x = xa - sign * (r_end * 0.5)
                base_x = tip_x - sign * 2.2
                svg_parts.append(
                    f'<polygon points="{tip_x:.2f},{cy:.2f} '
                    f'{base_x:.2f},{cy - 1.7:.2f} {base_x:.2f},{cy + 1.7:.2f}" '
                    f'fill="{mark_color}"/>'
                )
        # Hollow start dot + solid end dot with hover tooltips
        start_tip = html.escape(f"Before: {before_str}")
        end_tip = html.escape(f"After: {after_str} ({compact_val})")
        svg_parts.append(
            f'<circle cx="{xb:.2f}" cy="{cy:.2f}" r="{r_start:.2f}" fill="{theme.background}" '
            f'stroke="{mark_color}" stroke-width="1.35" stroke-opacity="0.85">'
            f"<title>{start_tip}</title></circle>"
        )
        svg_parts.append(
            f'<circle cx="{xa:.2f}" cy="{cy:.2f}" r="{r_end:.2f}" fill="{mark_color}" '
            f'stroke="{theme.background}" stroke-width="0.75">'
            f"<title>{end_tip}</title></circle>"
        )

    # 11-slot Unicode / ASCII ruler
    slots = 11
    u_buf = ["·"] * slots
    a_buf = ["."] * slots
    s_before = round(_norm(b_val) * (slots - 1))
    s_after = round(_norm(a_val) * (slots - 1))

    if unchanged:
        u_buf[s_before] = "◎"
        a_buf[s_before] = "="
    elif s_before == s_after:
        u_buf[s_after] = "▸" if diff > 0.0 else "◂"
        a_buf[s_after] = ">" if diff > 0.0 else "<"
    elif s_after > s_before:
        u_buf[s_before] = "○"
        a_buf[s_before] = "o"
        u_buf[s_after] = "●"
        a_buf[s_after] = "*"
        if s_after - s_before >= 2:
            for k in range(s_before + 1, s_after - 1):
                u_buf[k] = "─"
                a_buf[k] = "-"
            u_buf[s_after - 1] = "▶"
            a_buf[s_after - 1] = ">"
    else:
        u_buf[s_before] = "○"
        a_buf[s_before] = "o"
        u_buf[s_after] = "●"
        a_buf[s_after] = "*"
        if s_before - s_after >= 2:
            u_buf[s_after + 1] = "◀"
            a_buf[s_after + 1] = "<"
            for k in range(s_after + 2, s_before):
                u_buf[k] = "─"
                a_buf[k] = "-"

    u_glyph = f"[{''.join(u_buf)}]"
    a_glyph = f"[{''.join(a_buf)}]"

    rel_pct: float | None = None
    rel_str: str | None = None
    if not unchanged and abs(b_val) > 1e-12 and (unit or "").strip() != "%":
        rel_pct = (diff / abs(b_val)) * 100.0
        rel_str = _fmt_val(rel_pct, unit="%", signed=True)

    prefix = f"{label}: " if label else ""
    facts = [
        (
            f"{prefix}{before_str} → {after_str} ({compact_val}, {rel_str})"
            if rel_str is not None
            else f"{prefix}{before_str} → {after_str} ({compact_val})"
        ),
    ]
    if unchanged:
        facts.append("Unchanged between before and after")
    else:
        move = "Increase" if diff > 0.0 else "Decrease"
        verdict = "favorable" if favorable else "regression"
        pref = "higher" if higher_is_better else "lower"
        facts.append(f"{move} ({verdict}; {pref} is better)")

    alt = f"{prefix}delta {before_str} to {after_str} ({compact_val})"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        explain_change = mint.change

        name = label or "Metric"
        panel = explain_change(
            {name: b_val},
            {name: a_val},
            title=f"{name} shifted {compact_val}",
            label=label or "Value",
            unit=unit,
            highlight=name,
        )
        return mint.explain(
            f"{name}: {before_str} → {after_str} ({compact_val})",
            panel,
            style=_mintfig_style_name(theme),
        )

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="delta",
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
            "before": b_val,
            "after": a_val,
            "delta": diff,
            "pct_change": rel_pct,
            "higher_is_better": higher_is_better,
            "favorable": favorable,
        },
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 2. mintchip.waterfall — Micro-attribution bridge
# --------------------------------------------------------------------------- #


def _parse_waterfall_steps(
    steps: Mapping[str, float] | Sequence[float] | Sequence[tuple[str, float]],
) -> list[tuple[str, float]]:
    raw_items: list[tuple[str, object]]
    if isinstance(steps, Mapping):
        raw_items = [(str(k), v) for k, v in steps.items()]
    elif isinstance(steps, (str, bytes)) or not isinstance(steps, Sequence):
        raise ChipError(
            "inline.waterfall steps must be a mapping {name: delta} or sequence of numbers.",
            fix_hint='Pass e.g. mintchip.waterfall({"Retrieval": 0.12, "Overhead": -0.03}).',
        )
    else:
        seq = list(steps)
        if seq and all(
            isinstance(el, tuple) and len(el) == 2 and isinstance(el[0], str) for el in seq
        ):
            raw_items = [(el[0], el[1]) for el in seq]  # type: ignore[index]
        else:
            raw_items = [(f"Step {i + 1}", el) for i, el in enumerate(seq)]

    if not raw_items:
        raise ChipError(
            "inline.waterfall requires at least 1 step.",
            fix_hint='Pass non-empty steps, e.g. mintchip.waterfall({"Gain": 0.12, "Drag": -0.02}).',
        )

    parsed: list[tuple[str, float]] = []
    for nm, val in raw_items:
        if not _is_finite(val):
            raise ChipError(
                f"inline.waterfall step {nm!r} must have a finite numeric delta.",
                fix_hint="Replace NaN/None/non-numeric step values with finite numbers.",
            )
        parsed.append((nm.strip() or "Step", float(val)))  # type: ignore[arg-type]
    return parsed


def waterfall(
    steps: Mapping[str, float] | Sequence[float],
    *,
    start: float = 0.0,
    label: str | None = None,
    unit: str | None = None,
    width: int = 74,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized attribution waterfall bridge from ``start`` through ``steps``.

    Accepts either a ``{name: delta}`` mapping or a sequence of signed floats.
    Renders floating stepped bars connected by faint hairlines, an optional
    dashed zero reference when cumulative levels cross zero, per-bar
    ``<title>`` tooltips, and a final total marker dot.
    """
    if not _is_finite(start):
        raise ChipError(
            "inline.waterfall start must be a finite number.",
            fix_hint="Pass a finite numeric start=, e.g. start=0.0.",
        )

    step_items = _parse_waterfall_steps(steps)
    start_val = float(start)
    theme = _resolve_theme(style, palette=palette, accent=accent)

    # Cumulative path
    segments: list[tuple[str, float, float, float]] = []
    running = start_val
    for nm, d in step_items:
        nxt = running + d
        segments.append((nm, running, nxt, d))
        running = nxt
    end_val = running
    net = end_val - start_val

    levels = [start_val, *(y1 for _, _, y1, _ in segments)]
    lo = min(levels)
    hi = max(levels)
    crosses_zero = lo < 0.0 < hi
    if hi - lo <= 1e-12:
        lo -= 0.5
        hi += 0.5
    span = hi - lo

    pad_x = 2.5
    right_margin = 3.2
    gap_to_dot = 2.8
    pad_y = 2.2
    inner_h = max(height - 2.0 * pad_y, 4.0)
    n = len(segments)

    bars_w = max(width - pad_x - right_margin - gap_to_dot, 8.0)
    gap = 1.4 if n <= 10 else 0.7
    if n == 1:
        bar_w = min(bars_w, 24.0)
    else:
        bar_w = max((bars_w - gap * (n - 1)) / n, 1.2)

    def _y(v: float) -> float:
        return pad_y + (1.0 - (v - lo) / span) * inner_h

    def _bar_x(idx: int) -> float:
        return pad_x + idx * (bar_w + gap)

    last_bar_right = _bar_x(n - 1) + bar_w
    dot_x = min(width - right_margin, last_bar_right + gap_to_dot)

    pos_color = _positive_color(theme)
    neg_color = theme.accent_colors[0]
    svg_parts: list[str] = []

    # Dashed zero reference when cumulative path crosses zero; otherwise faint start baseline
    if crosses_zero:
        zy = _y(0.0)
        svg_parts.append(
            f'<line x1="{pad_x:.1f}" y1="{zy:.2f}" x2="{width - 1.5:.1f}" y2="{zy:.2f}" '
            f'stroke="{theme.zero_line}" stroke-width="0.85" stroke-opacity="0.6" '
            f'stroke-dasharray="2,1.6"/>'
        )
    else:
        sy = _y(start_val)
        svg_parts.append(
            f'<line x1="{pad_x:.1f}" y1="{sy:.2f}" x2="{dot_x:.2f}" y2="{sy:.2f}" '
            f'stroke="{theme.grid}" stroke-width="0.8"/>'
        )

    # Faint connector hairlines between consecutive bars and into the final total dot
    for i, (_nm, _y0, y1, _d) in enumerate(segments):
        cx1 = _bar_x(i) + bar_w
        cx2 = _bar_x(i + 1) if i + 1 < n else dot_x
        cy_c = _y(y1)
        svg_parts.append(
            f'<line x1="{cx1:.2f}" y1="{cy_c:.2f}" x2="{cx2:.2f}" y2="{cy_c:.2f}" '
            f'stroke="{theme.axis}" stroke-width="0.65" stroke-opacity="0.65"/>'
        )

    # Floating stepped bars with per-bar <title>
    for i, (nm, y0, y1, d) in enumerate(segments):
        bx = _bar_x(i)
        py0, py1 = _y(y0), _y(y1)
        top_y = min(py0, py1)
        bh = max(abs(py1 - py0), 1.3)
        tip = f"{nm}: {_fmt_val(d, unit=unit, signed=True)} (cum {_fmt_val(y1, unit=unit)})"
        if abs(d) <= 1e-12:
            svg_parts.append(
                f'<rect x="{bx:.2f}" y="{py0 - 0.6:.2f}" width="{bar_w:.2f}" height="1.2" '
                f'fill="{theme.muted}" rx="0.4"><title>{html.escape(tip)}</title></rect>'
            )
        else:
            fill = pos_color if d > 0.0 else neg_color
            svg_parts.append(
                f'<rect x="{bx:.2f}" y="{top_y:.2f}" width="{bar_w:.2f}" height="{bh:.2f}" '
                f'fill="{fill}" rx="0.8"><title>{html.escape(tip)}</title></rect>'
            )

    # Subtle start anchor tick when starting from a non-zero baseline
    if abs(start_val) > 1e-12:
        sy0 = _y(start_val)
        start_tip = html.escape(f"Start: {_fmt_val(start_val, unit=unit)}")
        svg_parts.append(
            f'<circle cx="{pad_x:.2f}" cy="{sy0:.2f}" r="1.45" fill="{theme.background}" '
            f'stroke="{theme.muted}" stroke-width="1.0"><title>{start_tip}</title></circle>'
        )

    # Final total dot
    total_tip = f"Total: {_fmt_val(end_val, unit=unit)} (net {_fmt_val(net, unit=unit, signed=True)})"
    svg_parts.append(
        f'<circle cx="{dot_x:.2f}" cy="{_y(end_val):.2f}" r="2.15" '
        f'fill="{theme.ink}" stroke="{theme.background}" stroke-width="0.7">'
        f"<title>{html.escape(total_tip)}</title></circle>"
    )

    # Proportional directional Unicode & ASCII step glyphs
    max_abs = max((abs(d) for _, d in step_items), default=0.0)
    u_parts: list[str] = []
    a_parts: list[str] = []
    for _nm, d in step_items:
        if abs(d) <= 1e-12 or max_abs <= 0.0:
            u_parts.append("·")
            a_parts.append("0")
        else:
            ratio = abs(d) / max_abs
            b_idx = max(0, min(len(_SPARK_BLOCKS) - 1, round(ratio * (len(_SPARK_BLOCKS) - 1))))
            a_mag = max(1, min(9, round(ratio * 9)))
            if d > 0.0:
                u_parts.append(f"▲{_SPARK_BLOCKS[b_idx]}")
                a_parts.append(f"+{a_mag}")
            else:
                u_parts.append(f"▼{_SPARK_BLOCKS[b_idx]}")
                a_parts.append(f"-{a_mag}")
    u_glyph = f"[{''.join(u_parts)}]"
    a_glyph = f"[{''.join(a_parts)}]"

    net_str = _fmt_val(net, unit=unit, signed=True)
    compact_val = net_str
    if abs(start_val) <= 1e-12:
        val_str = f"net {net_str}"
    else:
        val_str = f"{_fmt_val(start_val, unit=unit)}→{_fmt_val(end_val, unit=unit)} ({net_str})"

    prefix = f"{label}: " if label else ""
    facts: list[str] = []
    if abs(start_val) <= 1e-12:
        facts.append(
            f"{prefix}net {net_str} across {n} step{'s' if n != 1 else ''} "
            f"(total {_fmt_val(end_val, unit=unit)})"
        )
    else:
        facts.append(
            f"{prefix}{_fmt_val(start_val, unit=unit)} → {_fmt_val(end_val, unit=unit)} "
            f"(net {net_str} across {n} step{'s' if n != 1 else ''})"
        )

    pos_steps = [(nm, d) for nm, d in step_items if d > 0.0]
    neg_steps = [(nm, d) for nm, d in step_items if d < 0.0]
    if pos_steps:
        best_nm, best_d = max(pos_steps, key=lambda kv: kv[1])
        facts.append(f"Largest positive driver: {best_nm} ({_fmt_val(best_d, unit=unit, signed=True)})")
    if neg_steps:
        worst_nm, worst_d = min(neg_steps, key=lambda kv: kv[1])
        facts.append(f"Largest negative drag: {worst_nm} ({_fmt_val(worst_d, unit=unit, signed=True)})")
    if crosses_zero:
        facts.append(
            f"Cumulative path crosses zero (range {_fmt_val(lo, unit=unit)} to {_fmt_val(hi, unit=unit)})"
        )

    alt = f"{prefix}waterfall bridge {val_str} across {n} step{'s' if n != 1 else ''}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        explain_waterfall = mint.waterfall

        # Ensure unique step keys if caller supplied duplicate tuple labels
        step_dict: dict[str, float] = {}
        seen: dict[str, int] = {}
        for nm, d in step_items:
            if nm in seen:
                seen[nm] += 1
                key = f"{nm} ({seen[nm]})"
            else:
                seen[nm] = 1
                key = nm
            step_dict[key] = d

        name = label or "Attribution"
        panel = explain_waterfall(
            step_dict,
            start=("Start", start_val) if abs(start_val) > 1e-12 else None,
            title=f"{name}: {val_str}",
            label=label or "Value",
            unit=unit,
        )
        return mint.explain(
            f"{name} bridges {val_str} across {n} step{'s' if n != 1 else ''}",
            panel,
            style=_mintfig_style_name(theme),
        )

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="waterfall",
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
            "steps": [(nm, d) for nm, d in step_items],
            "start": start_val,
            "end": end_val,
            "net": net,
            "crosses_zero": crosses_zero,
        },
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 3. mintchip.scatter — Micro 2D scatter / correlation / Pareto glyph
# --------------------------------------------------------------------------- #


def scatter(
    x: Sequence[float],
    y: Sequence[float],
    *,
    highlight: int | str | None = None,
    names: Sequence[str] | None = None,
    fit: bool = False,
    frontier: bool = False,
    label: str | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    width: int = 36,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized 2D scatter / correlation / Pareto position glyph.

    Renders a crisp micro 2D frame with L-axes, context points, optional
    least-squares fit line (``fit=True``) or upper-right Pareto frontier
    polyline (``frontier=True``), and an accented halo marker for ``highlight``.
    Its Unicode text rendering uses true 2D Unicode Braille patterns
    (``U+2800``..``U+28FF``) across 5 Braille cells (a 10×4 pixel grid).
    """
    if (
        isinstance(x, (str, bytes))
        or isinstance(y, (str, bytes))
        or not isinstance(x, Sequence)
        or not isinstance(y, Sequence)
    ):
        raise ChipError(
            "inline.scatter requires numeric sequences x and y.",
            fix_hint="Pass two equal-length lists of numbers, e.g. mintchip.scatter(xs, ys).",
        )

    raw_x = list(x)
    raw_y = list(y)
    if len(raw_x) != len(raw_y):
        raise ChipError(
            f"inline.scatter got {len(raw_x)} x values and {len(raw_y)} y values.",
            fix_hint="Pass equal-length sequences for x and y.",
        )

    raw_names: list[str] | None = None
    if names is not None:
        if isinstance(names, (str, bytes)) or not isinstance(names, Sequence):
            raise ChipError(
                "inline.scatter names must be a sequence of strings.",
                fix_hint='Pass e.g. names=["A", "B", "C"] aligned with x and y.',
            )
        raw_names = [str(nm) for nm in names]
        if len(raw_names) != len(raw_x):
            raise ChipError(
                f"inline.scatter names length ({len(raw_names)}) must match x/y length ({len(raw_x)}).",
                fix_hint="Pass one name per (x, y) point, or omit names.",
            )

    # Filter to complete finite pairs while remembering original indices
    pts: list[tuple[int, float, float, str | None]] = []
    for idx, (xv, yv) in enumerate(zip(raw_x, raw_y, strict=True)):
        if _is_finite(xv) and _is_finite(yv):
            nm = raw_names[idx] if raw_names is not None else None
            pts.append((idx, float(xv), float(yv), nm))  # type: ignore[arg-type]

    if len(pts) < 2:
        raise ChipError(
            f"inline.scatter requires at least 2 complete finite (x, y) pairs; got {len(pts)}.",
            fix_hint="Pass equal-length numeric sequences x and y with 2+ finite points.",
        )

    # Resolve highlight (int index into original sequence, or matching name)
    hl_idx: int | None = None
    hl_orig_idx: int | None = None
    hl_name: str | None = None
    if highlight is not None:
        if isinstance(highlight, bool):
            raise ChipError(
                "inline.scatter highlight must be an int index or a name from names=.",
                fix_hint='Pass highlight=0 or highlight="Model A" (with names=).',
            )
        if isinstance(highlight, int):
            target = highlight if highlight >= 0 else len(raw_x) + highlight
            if not (0 <= target < len(raw_x)):
                raise ChipError(
                    f"inline.scatter highlight index {highlight} is out of range for {len(raw_x)} points.",
                    fix_hint=f"Pass an index between 0 and {len(raw_x) - 1}.",
                )
            for k, (orig_i, _xv, _yv, nm) in enumerate(pts):
                if orig_i == target:
                    hl_idx = k
                    hl_orig_idx = orig_i
                    hl_name = nm
                    break
            if hl_idx is None:
                raise ChipError(
                    f"inline.scatter highlight index {highlight} refers to a non-finite point.",
                    fix_hint="Highlight a point with finite x and y coordinates.",
                )
        elif isinstance(highlight, str):
            if raw_names is None:
                raise ChipError(
                    f"inline.scatter highlight={highlight!r} requires names= to resolve point names.",
                    fix_hint="Pass names=[...] aligned with x and y, or pass an integer index.",
                )
            for k, (orig_i, _xv, _yv, nm) in enumerate(pts):
                if nm == highlight:
                    hl_idx = k
                    hl_orig_idx = orig_i
                    hl_name = nm
                    break
            if hl_idx is None:
                raise ChipError(
                    f"inline.scatter highlight={highlight!r} not found among finite named points.",
                    fix_hint=f"Choose a name from {raw_names[:6]!r}.",
                )
        else:
            raise ChipError(
                f"inline.scatter highlight must be int, str, or None; got {type(highlight).__name__}.",
                fix_hint='Pass an integer index or point name from names=.',
            )

    theme = _resolve_theme(style, palette=palette, accent=accent)
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts]
    pt_names = [p[3] for p in pts] if raw_names is not None else None
    n = len(pts)

    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((xv - mx) ** 2 for xv in xs)
    syy = sum((yv - my) ** 2 for yv in ys)
    sxy = sum((xv - mx) * (yv - my) for xv, yv in zip(xs, ys, strict=True))

    r_val: float | None = None
    if n >= 3 and sxx > 0.0 and syy > 0.0:
        r_val = max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))

    slope: float | None = None
    intercept: float | None = None
    if sxx > 0.0:
        slope = sxy / sxx
        intercept = my - slope * mx

    frontier_idx = _pareto_upper_right(xs, ys) if frontier else []
    frontier_set = set(frontier_idx)

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_span = x_max - x_min
    y_span = y_max - y_min

    # SVG 2D micro-frame
    pad_l = 3.2
    pad_r = 3.0
    pad_t = 2.2
    pad_b = 2.8
    inner_w = max(width - pad_l - pad_r, 6.0)
    inner_h = max(height - pad_t - pad_b, 6.0)

    def _sx(v: float) -> float:
        if x_span <= 0.0:
            return pad_l + inner_w / 2.0
        return pad_l + ((v - x_min) / x_span) * inner_w

    def _sy(v: float) -> float:
        if y_span <= 0.0:
            return pad_t + inner_h / 2.0
        return pad_t + (1.0 - (v - y_min) / y_span) * inner_h

    ax_x = pad_l - 1.5
    ax_y = height - pad_b + 1.3
    svg_parts: list[str] = [
        # Subtle L-axes framing the 2D scatter
        (
            f'<path d="M{ax_x:.1f},{pad_t - 0.8:.1f} L{ax_x:.1f},{ax_y:.1f} '
            f'L{width - pad_r + 1.3:.1f},{ax_y:.1f}" fill="none" '
            f'stroke="{theme.axis}" stroke-width="0.8" stroke-opacity="0.7" '
            f'stroke-linecap="square"/>'
        ),
    ]

    # Optional least-squares regression line
    if fit and slope is not None and intercept is not None:
        if y_span <= 0.0:
            fx0, fy0, fx1, fy1 = x_min, intercept, x_max, intercept
            clipped: tuple[float, float, float, float] | None = (fx0, fy0, fx1, fy1)
        else:
            clipped = _clip_segment(
                x_min,
                slope * x_min + intercept,
                x_max,
                slope * x_max + intercept,
                x_min,
                x_max,
                y_min,
                y_max,
            )
        if clipped is not None:
            cx0, cy0, cx1, cy1 = clipped
            fit_tip = f"OLS fit: slope {_fmt_val(slope)}, intercept {_fmt_val(intercept)}"
            svg_parts.append(
                f'<line x1="{_sx(cx0):.2f}" y1="{_sy(cy0):.2f}" '
                f'x2="{_sx(cx1):.2f}" y2="{_sy(cy1):.2f}" '
                f'stroke="{theme.ink}" stroke-width="0.95" stroke-opacity="0.72" '
                f'stroke-linecap="round"><title>{html.escape(fit_tip)}</title></line>'
            )

    # Optional upper-right Pareto frontier polyline
    if frontier and len(frontier_idx) >= 2:
        f_pts = " ".join(f"{_sx(xs[i]):.2f},{_sy(ys[i]):.2f}" for i in frontier_idx)
        f_tip = f"Upper-right Pareto frontier ({len(frontier_idx)} of {n} points)"
        svg_parts.append(
            f'<polyline points="{f_pts}" fill="none" '
            f'stroke="{theme.series_colors[0]}" stroke-width="1.0" '
            f'stroke-dasharray="2,1.2" stroke-linecap="round" stroke-linejoin="round">'
            f"<title>{html.escape(f_tip)}</title></polyline>"
        )
    elif frontier and len(frontier_idx) == 1:
        fi = frontier_idx[0]
        f_tip = f"Dominant upper-right point ({_fmt_val(xs[fi])}, {_fmt_val(ys[fi])})"
        svg_parts.append(
            f'<circle cx="{_sx(xs[fi]):.2f}" cy="{_sy(ys[fi]):.2f}" r="2.3" '
            f'fill="none" stroke="{theme.series_colors[0]}" stroke-width="0.85">'
            f"<title>{html.escape(f_tip)}</title></circle>"
        )

    # Context dots (with per-point hover tooltips when n <= 60)
    dot_r = 1.15 if n <= 30 else 0.9
    base_color = theme.axis if hl_idx is not None else theme.series_colors[0]
    base_opacity = "0.62" if hl_idx is not None else "0.78"
    include_pt_tips = n <= 60
    for i, (xv, yv) in enumerate(zip(xs, ys, strict=True)):
        if i == hl_idx:
            continue
        is_front = i in frontier_set
        fill = theme.series_colors[0] if is_front else base_color
        op = "0.90" if is_front else base_opacity
        r_pt = dot_r + 0.2 if is_front else dot_r
        if include_pt_tips:
            pt_lbl = pt_names[i] if (pt_names is not None and pt_names[i] is not None) else f"#{pts[i][0]}"
            pt_tip = html.escape(f"{pt_lbl}: ({_fmt_val(xv)}, {_fmt_val(yv)})")
            svg_parts.append(
                f'<circle cx="{_sx(xv):.2f}" cy="{_sy(yv):.2f}" r="{r_pt:.2f}" '
                f'fill="{fill}" fill-opacity="{op}"><title>{pt_tip}</title></circle>'
            )
        else:
            svg_parts.append(
                f'<circle cx="{_sx(xv):.2f}" cy="{_sy(yv):.2f}" r="{r_pt:.2f}" '
                f'fill="{fill}" fill-opacity="{op}"/>'
            )

    # Bold accented highlight dot with translucent halo
    if hl_idx is not None:
        hx = _sx(xs[hl_idx])
        hy = _sy(ys[hl_idx])
        hl_color = theme.accent_colors[0]
        hl_lbl = hl_name if hl_name is not None else f"#{hl_orig_idx}"
        hl_tip = f"{hl_lbl}: ({_fmt_val(xs[hl_idx])}, {_fmt_val(ys[hl_idx])})"
        svg_parts.append(
            f'<circle cx="{hx:.2f}" cy="{hy:.2f}" r="3.3" '
            f'fill="{hl_color}" fill-opacity="0.22"/>'
        )
        svg_parts.append(
            f'<circle cx="{hx:.2f}" cy="{hy:.2f}" r="1.95" '
            f'fill="{hl_color}" stroke="{theme.background}" stroke-width="0.75">'
            f"<title>{html.escape(hl_tip)}</title></circle>"
        )

    # True 2D Unicode Braille scatter (5 Braille cells = 10×4 pixel grid)
    n_cells = 5
    masks = [0] * n_cells
    bin_tys: list[list[float]] = [[] for _ in range(n_cells)]
    bin_rows: list[set[int]] = [set() for _ in range(n_cells)]
    hl_cell: int | None = None

    for i, (xv, yv) in enumerate(zip(xs, ys, strict=True)):
        tx = 0.5 if x_span <= 0.0 else (xv - x_min) / x_span
        ty = 0.5 if y_span <= 0.0 else (yv - y_min) / y_span
        gx = max(0, min(9, round(tx * 9.0)))
        gy = max(0, min(3, round((1.0 - ty) * 3.0)))
        cell = gx // 2
        col = gx % 2
        masks[cell] |= _BRAILLE_BITS[gy][col]
        bin_tys[cell].append(ty)
        bin_rows[cell].add(gy)
        if i == hl_idx:
            hl_cell = cell

    u_glyph = "[" + "".join(chr(0x2800 + m) for m in masks) + "]"

    # 5-char pure ASCII slope/cloud fallback
    a_chars: list[str] = []
    for cell in range(n_cells):
        if cell == hl_cell:
            a_chars.append("*")
        elif not bin_tys[cell]:
            a_chars.append(" ")
        elif max(bin_rows[cell]) - min(bin_rows[cell]) >= 2:
            a_chars.append(":")
        else:
            mean_ty = sum(bin_tys[cell]) / len(bin_tys[cell])
            lvl = max(
                0,
                min(len(_ASCII_SCATTER_LEVELS) - 1, round(mean_ty * (len(_ASCII_SCATTER_LEVELS) - 1))),
            )
            a_chars.append(_ASCII_SCATTER_LEVELS[lvl])
    a_glyph = f"[{''.join(a_chars)}]"

    # Value & facts formatting
    r_str = f"{r_val:.2f}".replace("-", "\N{MINUS SIGN}") if r_val is not None else None
    if hl_idx is not None and not fit:
        hx_s = _fmt_val(xs[hl_idx])
        hy_s = _fmt_val(ys[hl_idx])
        if hl_name is not None:
            val_str = f"{hl_name} ({hx_s}, {hy_s})"
            compact_val = hl_name
        else:
            val_str = f"({hx_s}, {hy_s})"
            compact_val = val_str
    elif r_str is not None:
        val_str = f"r={r_str}"
        compact_val = val_str
    else:
        val_str = f"n={n}"
        compact_val = val_str

    x_nm = x_label or "x"
    y_nm = y_label or "y"
    prefix = f"{label}: " if label else ""
    facts: list[str] = []
    if r_val is not None and r_str is not None:
        strength = (
            "no"
            if abs(r_val) < 0.2
            else ("weak" if abs(r_val) < 0.5 else ("moderate" if abs(r_val) < 0.8 else "strong"))
        )
        direction = "" if strength == "no" else (" positive" if r_val > 0.0 else " negative")
        facts.append(f"{prefix}Pearson r = {r_str} (n={n}; {strength}{direction} linear association)")
    else:
        reason = "n < 3" if n < 3 else "zero variance"
        facts.append(f"{prefix}n={n} points (Pearson r undefined: {reason})")

    facts.append(
        f"{x_nm} range {_fmt_val(x_min)} to {_fmt_val(x_max)}; "
        f"{y_nm} range {_fmt_val(y_min)} to {_fmt_val(y_max)}"
    )
    if hl_idx is not None:
        hl_desc = hl_name if hl_name is not None else f"point #{hl_orig_idx}"
        facts.append(
            f"Highlight {hl_desc}: {x_nm}={_fmt_val(xs[hl_idx])}, {y_nm}={_fmt_val(ys[hl_idx])}"
        )
    if fit and slope is not None and intercept is not None:
        facts.append(f"OLS fit: slope {_fmt_val(slope)}, intercept {_fmt_val(intercept)}")
    if frontier and frontier_idx:
        if pt_names is not None:
            f_names = ", ".join(pt_names[i] for i in frontier_idx if pt_names[i] is not None)
            facts.append(f"Upper-right Pareto frontier ({len(frontier_idx)} of {n}): {f_names}")
        else:
            facts.append(f"Upper-right Pareto frontier: {len(frontier_idx)} of {n} points")

    alt = f"{prefix}scatter of {n} points ({val_str})"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        explain_relate = mint.relate

        expand_names: list[str] | None = None
        expand_hl: str | None = None
        if pt_names is not None:
            expand_names = [nm if nm is not None else f"#{i}" for i, nm in enumerate(pt_names)]
            if hl_idx is not None:
                expand_hl = expand_names[hl_idx]
        elif hl_idx is not None:
            expand_names = [f"#{i}" for i in range(n)]
            expand_hl = expand_names[hl_idx]

        panel = explain_relate(
            xs,
            ys,
            x_label=x_nm,
            y_label=y_nm,
            title=f"{label or f'{y_nm} vs {x_nm}'} ({val_str})",
            names=expand_names,
            highlight=expand_hl,
            fit=fit,
            frontier="upper-right" if frontier else False,
        )
        return mint.explain(
            f"{label or f'{y_nm} vs {x_nm}'}: {val_str} across n={n} points",
            panel,
            style=_mintfig_style_name(theme),
        )

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="scatter",
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
            "n": n,
            "r": r_val,
            "slope": slope,
            "intercept": intercept,
            "highlight": hl_name if hl_name is not None else hl_orig_idx,
            "highlight_coords": (xs[hl_idx], ys[hl_idx]) if hl_idx is not None else None,
            "frontier_indices": frontier_idx if frontier else None,
        },
        expand_explanation=exp_obj,
    )
