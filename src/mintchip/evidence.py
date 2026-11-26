"""Uncertainty, thresholds, and calibrated evidence micro-graphics (``mint.inline``).

Word-sized inline components for operating windows, countable predictive
quantiles, and calibrated epistemic strength:

- ``gauge`` — operating-window / biomarker / tolerance indicator with shaded
  ``normal`` band, optional wider ``warn`` caution band, and status-colored
  diamond reading marker.
- ``quantiles`` — Kay & Hullman countable micro quantile dotplot with optional
  threshold exceedance slice and empirical ``P(X > threshold)``.
- ``evidence`` — calibrated 5-tier epistemic strength & sample-size signal
  meter (Bayes factor, *p*-value, or explicit tier) with low-power warning
  for small *n*.
"""

from __future__ import annotations

import html
import math
import numbers
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .core import (
    _SPARK_BLOCKS,
    Chip,
    ChipError,
    _fmt_val,
    _is_finite,
    _mintfig_style_name,
    _quantiles,
    _require_mintfig,
    _resolve_expand_explanation,
    _resolve_theme,
)
from .themes import Theme

__all__ = [
    "evidence",
    "gauge",
    "quantiles",
]

_ASCII_DENSITY = "-=+*#"

_EVIDENCE_TIERS: dict[str, tuple[int, str]] = {
    "none": (0, "No material evidence against null"),
    "weak": (1, "Anecdotal / weak; gather more data"),
    "moderate": (3, "Moderate; consistent but not conclusive"),
    "strong": (4, "Strong evidence across repeated checks"),
    "decisive": (5, "Decisive evidence; robust to priors"),
}

_EVIDENCE_ALIASES: dict[str, str] = {
    "anecdotal": "weak",
}

_BAR_TIER_LABELS = ("Weak", "Suggestive", "Moderate", "Strong", "Decisive")


def _parse_bounds(raw: Any, name: str, hint: str) -> tuple[float, float]:
    """Validate a strictly increasing finite ``(low, high)`` pair."""
    if isinstance(raw, (str, bytes, Mapping)) or not isinstance(raw, Iterable):
        raise ChipError(
            f"{name} must be a (low, high) pair of finite numbers.",
            fix_hint=hint,
        )
    items = list(raw)
    if len(items) != 2:
        raise ChipError(
            f"{name} must be a (low, high) pair of finite numbers.",
            fix_hint=hint,
        )
    if not (_is_finite(items[0]) and _is_finite(items[1])):
        raise ChipError(
            f"{name} bounds must be finite numbers.",
            fix_hint=hint,
        )
    lo, hi = float(items[0]), float(items[1])
    if lo >= hi:
        raise ChipError(
            f"{name} lower bound ({lo}) must be strictly less than upper bound ({hi}).",
            fix_hint=hint,
        )
    return lo, hi


def _validate_size(width: int, height: int, fn: str) -> tuple[int, int]:
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, numbers.Integral)
        or not isinstance(height, numbers.Integral)
        or int(width) <= 0
        or int(height) <= 0
    ):
        raise ChipError(
            f"{fn} width and height must be positive integers.",
            fix_hint=f"Pass positive pixel sizes, e.g. width=74, height=16 for {fn}.",
        )
    return int(width), int(height)


def _interp_quantile(sorted_vals: Sequence[float], p: float) -> float:
    """Linear-interpolation quantile matching ``numpy.quantile(..., method='linear')``."""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    idx = p * (n - 1)
    lo = math.floor(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def _fmt_p(p_val: float) -> str:
    """Format a p-value concisely without sacrificing small-value precision."""
    if p_val == 0.0:
        return "0"
    if p_val < 1e-4:
        return _fmt_val(p_val)
    if p_val < 1e-3:
        return f"{p_val:.4f}".rstrip("0").rstrip(".")
    return f"{p_val:.3g}"


def _fmt_pct(pct: float) -> str:
    """Format a percentage cleanly while avoiding false 0%/100% rounding on tails."""
    if 0.0 < pct < 0.5:
        return f"{pct:.1f}%"
    if 99.5 < pct < 100.0:
        return f"{pct:.1f}%"
    return f"{pct:.0f}%"


def _tier_from_bf(bf_val: float) -> str:
    """Kass & Raftery (1995) Bayes factor tiers."""
    if bf_val < 1.0:
        return "none"
    if bf_val < 3.0:
        return "weak"
    if bf_val < 10.0:
        return "moderate"
    if bf_val < 30.0:
        return "strong"
    return "decisive"


def _tier_from_p(p_val: float) -> str:
    """Calibrated p-value evidence tiers (avoids a single 0.05 cliff)."""
    if p_val > 0.1:
        return "none"
    if p_val > 0.05:
        return "weak"
    if p_val > 0.01:
        return "moderate"
    if p_val > 0.001:
        return "strong"
    return "decisive"


# --------------------------------------------------------------------------- #
# 1. mintchip.gauge — Operating-window / biomarker / tolerance indicator
# --------------------------------------------------------------------------- #


def gauge(
    value: float,
    normal: tuple[float, float],
    *,
    warn: tuple[float, float] | None = None,
    domain: tuple[float, float] | None = None,
    label: str | None = None,
    unit: str | None = None,
    width: int = 74,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build an inline operating-window / biomarker / tolerance range gauge.

    Draws a horizontal scale with a shaded ``normal=(lo, hi)`` target window,
    optional wider ``warn=(w_lo, w_hi)`` caution band, and a bold diamond
    reading marker colored primary/teal inside ``normal``, amber when only
    inside ``warn``, and warm accent when outside both.
    """
    if not _is_finite(value):
        raise ChipError(
            "inline.gauge value must be a finite number.",
            fix_hint="Pass a finite numeric reading, e.g. mintchip.gauge(7.38, (7.35, 7.45)).",
        )
    val = float(value)
    n_lo, n_hi = _parse_bounds(
        normal,
        "inline.gauge(normal)",
        "Pass normal=(low, high) with low < high, e.g. normal=(7.35, 7.45).",
    )
    warn_bounds: tuple[float, float] | None = None
    if warn is not None:
        warn_bounds = _parse_bounds(
            warn,
            "inline.gauge(warn)",
            "Pass warn=(low, high) with low < high, e.g. warn=(7.25, 7.55).",
        )
    dom_bounds: tuple[float, float] | None = None
    if domain is not None:
        dom_bounds = _parse_bounds(
            domain,
            "inline.gauge(domain)",
            "Pass domain=(low, high) with low < high.",
        )
    width, height = _validate_size(width, height, "inline.gauge")

    theme = _resolve_theme(style, palette=palette, accent=accent)

    # Determine status & distance to nearest normal boundary
    if n_lo <= val <= n_hi:
        status = "within"
        side = "within"
        d_lo_n = val - n_lo
        d_hi_n = n_hi - val
        if d_lo_n <= d_hi_n:
            dist_boundary = d_lo_n
            nearest_bound = n_lo
            bound_name = "lower"
        else:
            dist_boundary = d_hi_n
            nearest_bound = n_hi
            bound_name = "upper"
    elif warn_bounds is not None and warn_bounds[0] <= val <= warn_bounds[1]:
        status = "warn"
        if val > n_hi:
            side = "above"
            dist_boundary = val - n_hi
            nearest_bound = n_hi
            bound_name = "upper"
        else:
            side = "below"
            dist_boundary = n_lo - val
            nearest_bound = n_lo
            bound_name = "lower"
    elif val > n_hi:
        status = "above"
        side = "above"
        dist_boundary = val - n_hi
        nearest_bound = n_hi
        bound_name = "upper"
    else:
        status = "below"
        side = "below"
        dist_boundary = n_lo - val
        nearest_bound = n_lo
        bound_name = "lower"

    # Compute display domain with generous breathing room around normal window
    n_span = n_hi - n_lo
    if dom_bounds is not None:
        d_lo, d_hi = dom_bounds
    else:
        pts_d = [n_lo, n_hi, val]
        if warn_bounds is not None:
            pts_d.extend(warn_bounds)
        raw_lo, raw_hi = min(pts_d), max(pts_d)
        raw_span = raw_hi - raw_lo
        if warn_bounds is None and n_lo <= val <= n_hi:
            pad_lo = 0.45 * n_span
            pad_hi = 0.45 * n_span
        else:
            pad_lo = max(0.16 * raw_span, 0.25 * n_span) if raw_lo == n_lo else 0.12 * raw_span
            pad_hi = max(0.16 * raw_span, 0.25 * n_span) if raw_hi == n_hi else 0.12 * raw_span
        d_lo = raw_lo - pad_lo
        d_hi = raw_hi + pad_hi

    span = max(d_hi - d_lo, 1e-12)
    pad_x = 4.2
    inner_w = max(width - 2 * pad_x, 8.0)
    cy = height / 2.0

    def _x(v: float) -> float:
        t = max(0.0, min(1.0, (v - d_lo) / span))
        return pad_x + t * inner_w

    ok_color = theme.series_colors[2] if len(theme.series_colors) > 2 else theme.series_colors[0]
    warn_color = theme.series_colors[3] if len(theme.series_colors) > 3 else theme.series_colors[1]
    out_color = theme.accent_colors[0]

    if status == "within":
        marker_color = ok_color
    elif status == "warn":
        marker_color = warn_color
    else:
        marker_color = out_color

    svg_parts: list[str] = [
        # Horizontal baseline track
        (
            f'<line x1="{pad_x:.1f}" y1="{cy:.2f}" x2="{width - pad_x:.1f}" y2="{cy:.2f}" '
            f'stroke="{theme.grid}" stroke-width="2.0" stroke-linecap="round"/>'
        ),
    ]

    # Optional faint warn band
    if warn_bounds is not None:
        w_lo, w_hi = warn_bounds
        xw1, xw2 = _x(w_lo), _x(w_hi)
        warn_tip = html.escape(
            f"Warn band: {_fmt_val(w_lo, unit=unit)} to {_fmt_val(w_hi, unit=unit)}"
        )
        svg_parts.append(
            f'<rect x="{xw1:.2f}" y="{cy - 3.8:.2f}" width="{max(xw2 - xw1, 1.4):.2f}" '
            f'height="7.6" fill="{warn_color}" fill-opacity="0.16" rx="1.2">'
            f"<title>{warn_tip}</title></rect>"
        )
        for wb in (w_lo, w_hi):
            if d_lo <= wb <= d_hi:
                xwb = _x(wb)
                svg_parts.append(
                    f'<line x1="{xwb:.2f}" y1="{cy - 4.2:.2f}" x2="{xwb:.2f}" y2="{cy + 4.2:.2f}" '
                    f'stroke="{warn_color}" stroke-width="0.65" stroke-opacity="0.55" '
                    f'stroke-dasharray="1.5,1.2"/>'
                )

    # Shaded normal target band + crisp boundary hairlines
    xn1, xn2 = _x(n_lo), _x(n_hi)
    norm_tip = html.escape(
        f"Normal window: {_fmt_val(n_lo, unit=unit)} to {_fmt_val(n_hi, unit=unit)}"
    )
    svg_parts.append(
        f'<rect x="{xn1:.2f}" y="{cy - 4.4:.2f}" width="{max(xn2 - xn1, 1.6):.2f}" '
        f'height="8.8" fill="{ok_color}" fill-opacity="0.22" rx="1.2">'
        f"<title>{norm_tip}</title></rect>"
    )
    for nb in (n_lo, n_hi):
        if d_lo <= nb <= d_hi:
            xnb = _x(nb)
            svg_parts.append(
                f'<line x1="{xnb:.2f}" y1="{cy - 5.1:.2f}" x2="{xnb:.2f}" y2="{cy + 5.1:.2f}" '
                f'stroke="{ok_color}" stroke-width="0.95" stroke-opacity="0.82"/>'
            )

    # Bold diamond reading marker at value
    xv = _x(val)
    rx, ry = 3.4, 4.1
    diamond_pts = (
        f"{xv:.2f},{cy - ry:.2f} {xv + rx:.2f},{cy:.2f} "
        f"{xv:.2f},{cy + ry:.2f} {xv - rx:.2f},{cy:.2f}"
    )
    compact_val = _fmt_val(val, unit=unit)
    val_tip = html.escape(f"{label or 'Reading'}: {compact_val} ({status})")
    svg_parts.append(
        f'<polygon points="{diamond_pts}" fill="{marker_color}" '
        f'stroke="{theme.background}" stroke-width="0.9">'
        f"<title>{val_tip}</title></polygon>"
    )

    # 11-slot Unicode & ASCII ruler
    slots = 11
    u_buf = ["·"] * slots
    a_buf = ["."] * slots

    def _slot(v: float) -> int:
        t = max(0.0, min(1.0, (v - d_lo) / span))
        return round(t * (slots - 1))

    s_lo = _slot(n_lo)
    s_hi = _slot(n_hi)
    if s_hi <= s_lo:
        if s_lo < slots - 1:
            s_hi = s_lo + 1
        else:
            s_lo = max(0, s_hi - 1)

    for k in range(s_lo + 1, s_hi):
        u_buf[k] = "═"
        a_buf[k] = "="
    if d_lo <= n_lo <= d_hi:
        u_buf[s_lo] = "|"
        a_buf[s_lo] = "|"
    if d_lo <= n_hi <= d_hi:
        u_buf[s_hi] = "|"
        a_buf[s_hi] = "|"

    s_val = _slot(val)
    if status == "within":
        if n_lo < val < n_hi and s_hi - s_lo >= 2:
            s_val = max(s_lo + 1, min(s_hi - 1, s_val))
        u_buf[s_val] = "◆"
        a_buf[s_val] = "*"
    elif side == "above":
        if s_val <= s_hi < slots - 1:
            s_val = s_hi + 1
        u_buf[s_val] = "▲"
        a_buf[s_val] = "^"
    else:
        if s_val >= s_lo > 0:
            s_val = s_lo - 1
        u_buf[s_val] = "▼"
        a_buf[s_val] = "v"

    u_glyph = f"[{''.join(u_buf)}]"
    a_glyph = f"[{''.join(a_buf)}]"

    val_str = f"{compact_val} [{_fmt_val(n_lo)}\N{EN DASH}{_fmt_val(n_hi)}]"
    prefix = f"{label}: " if label else ""
    norm_range_str = f"[{_fmt_val(n_lo, unit=unit)}, {_fmt_val(n_hi, unit=unit)}]"
    if status == "within":
        status_phrase = f"within normal window {norm_range_str}"
        dist_fact = (
            f"Distance to nearest boundary ({bound_name} {_fmt_val(nearest_bound, unit=unit)}): "
            f"{_fmt_val(dist_boundary, unit=unit)}"
        )
    elif status == "warn":
        assert warn_bounds is not None
        warn_edge = warn_bounds[1] if side == "above" else warn_bounds[0]
        warn_margin = abs(warn_edge - val)
        status_phrase = (
            f"in warn band ({side} normal window {norm_range_str}; "
            f"warn [{_fmt_val(warn_bounds[0], unit=unit)}, {_fmt_val(warn_bounds[1], unit=unit)}])"
        )
        dist_fact = (
            f"Distance {side} normal {bound_name} boundary ({_fmt_val(nearest_bound, unit=unit)}): "
            f"{_fmt_val(dist_boundary, unit=unit)} "
            f"({_fmt_val(warn_margin, unit=unit)} inside warn limit {_fmt_val(warn_edge, unit=unit)})"
        )
    else:
        status_phrase = f"{status} normal window {norm_range_str}"
        dist_fact = (
            f"Distance {status} normal {bound_name} boundary ({_fmt_val(nearest_bound, unit=unit)}): "
            f"{_fmt_val(dist_boundary, unit=unit)}"
        )
        if warn_bounds is not None:
            warn_edge = warn_bounds[1] if side == "above" else warn_bounds[0]
            if (side == "above" and val > warn_edge) or (side == "below" and val < warn_edge):
                dist_fact += (
                    f"; {_fmt_val(abs(val - warn_edge), unit=unit)} beyond warn limit "
                    f"({_fmt_val(warn_edge, unit=unit)})"
                )

    facts = [
        f"{prefix}{compact_val} is {status_phrase} (status={status})",
        dist_fact,
    ]
    alt = f"{prefix}{val_str} ({status})"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        compare = mint.compare

        name = label or "Reading"
        reading_key = name if name not in {"Normal window", "Warn window"} else f"{name} (value)"
        n_mid = 0.5 * (n_lo + n_hi)
        items: dict[str, float] = {
            reading_key: val,
            "Normal window": n_mid,
        }
        errs: dict[str, tuple[float, float]] = {
            reading_key: (val, val),
            "Normal window": (n_lo, n_hi),
        }
        if warn_bounds is not None:
            w_mid = 0.5 * (warn_bounds[0] + warn_bounds[1])
            items["Warn window"] = w_mid
            errs["Warn window"] = warn_bounds
        panel = compare(
            items,
            error=errs,
            error_label="Operating window bounds",
            highlight=reading_key,
            zero=False,
            sort=False,
            reference=(n_mid, "Target mid"),
            title=f"{name} ({compact_val}) is {status} normal range",
            label=label or "Value",
            unit=unit,
        )
        return mint.explain(f"{prefix}{val_str} ({status})", panel, style=_mintfig_style_name(theme))

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="gauge",
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
            "value": val,
            "normal": [n_lo, n_hi],
            "warn": list(warn_bounds) if warn_bounds is not None else None,
            "status": status,
            "side": side,
            "distance_to_boundary": dist_boundary,
        },
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 2. mintchip.quantiles — Kay & Hullman countable micro quantile dotplot
# --------------------------------------------------------------------------- #


def quantiles(
    samples: Sequence[float],
    *,
    threshold: float | None = None,
    n_dots: int = 10,
    domain: tuple[float, float] | None = None,
    label: str | None = None,
    unit: str | None = None,
    width: int = 76,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a countable Kay & Hullman micro quantile dotplot.

    Computes ``n_dots`` (5–20, default 10) equal-probability quantiles from
    ``samples`` and stacks them vertically into Wilkinson dot columns so
    readers can count probability directly. Pass ``threshold=`` to slice the
    dotplot with a dashed cutoff, accent exceedance dots, and report empirical
    ``P(X > threshold)``.
    """
    if isinstance(samples, (str, bytes, Mapping)) or not isinstance(samples, Iterable):
        raise ChipError(
            "inline.quantiles samples must be a sequence of numeric observations.",
            fix_hint="Pass a list or array of at least 3 numbers, e.g. mintchip.quantiles([14, 18, 20, 22, 27]).",
        )
    raw = list(samples)
    nums = sorted(float(v) for v in raw if _is_finite(v))
    dropped = len(raw) - len(nums)
    if len(nums) < 3:
        raise ChipError(
            f"inline.quantiles requires at least 3 finite samples; got {len(nums)}.",
            fix_hint="Pass 3 or more finite numeric observations.",
        )

    if (
        isinstance(n_dots, bool)
        or not isinstance(n_dots, numbers.Integral)
        or not (5 <= int(n_dots) <= 20)
    ):
        raise ChipError(
            f"inline.quantiles n_dots must be an integer between 5 and 20; got {n_dots!r}.",
            fix_hint="Pass n_dots=10 (each dot = 10%) or another integer from 5 to 20.",
        )
    k_dots = int(n_dots)

    thresh: float | None = None
    if threshold is not None:
        if not _is_finite(threshold):
            raise ChipError(
                "inline.quantiles threshold must be a finite number.",
                fix_hint="Pass a finite numeric threshold, e.g. threshold=25.0.",
            )
        thresh = float(threshold)

    dom_bounds: tuple[float, float] | None = None
    if domain is not None:
        dom_bounds = _parse_bounds(
            domain,
            "inline.quantiles(domain)",
            "Pass domain=(low, high) with low < high.",
        )
    width, height = _validate_size(width, height, "inline.quantiles")

    theme = _resolve_theme(style, palette=palette, accent=accent)

    q_vals = [_interp_quantile(nums, (k + 0.5) / k_dots) for k in range(k_dots)]
    q25, med, q75 = _quantiles(nums)

    if dom_bounds is not None:
        d_lo, d_hi = dom_bounds
    else:
        pts_d = [nums[0], nums[-1]]
        if thresh is not None:
            pts_d.append(thresh)
        raw_lo, raw_hi = min(pts_d), max(pts_d)
        margin = (raw_hi - raw_lo) * 0.08 if raw_hi > raw_lo else max(abs(raw_lo) * 0.1, 0.5)
        d_lo, d_hi = raw_lo - margin, raw_hi + margin

    span = max(d_hi - d_lo, 1e-12)
    pad_x = 3.5
    inner_w = max(width - 2 * pad_x, 10.0)
    base_y = height - 2.0

    def _x(v: float) -> float:
        t = max(0.0, min(1.0, (v - d_lo) / span))
        return pad_x + t * inner_w

    primary = theme.series_colors[0]
    exceed_color = theme.accent_colors[0]

    # Wilkinson pixel-space column binning, respecting threshold boundary
    r_base = 1.6 if k_dots <= 12 else 1.3
    bw = max(2.0 * r_base + 0.8, inner_w / 13.0)

    def _bin_group(items: list[tuple[int, float, bool]]) -> list[tuple[float, list[tuple[int, float, bool]]]]:
        if not items:
            return []
        cols: list[list[tuple[float, tuple[int, float, bool]]]] = [[(_x(items[0][1]), items[0])]]
        anchor_px = _x(items[0][1])
        for item in items[1:]:
            px = _x(item[1])
            if px - anchor_px <= bw:
                cols[-1].append((px, item))
            else:
                cols.append([(px, item)])
                anchor_px = px
        merged: list[list[tuple[float, tuple[int, float, bool]]]] = [cols[0]]
        for col in cols[1:]:
            prev = merged[-1]
            c_prev = 0.5 * (prev[0][0] + prev[-1][0])
            c_curr = 0.5 * (col[0][0] + col[-1][0])
            if c_curr - c_prev < 2.0 * r_base + 0.35:
                merged[-1] = prev + col
            else:
                merged.append(col)
        return [
            (0.5 * (col[0][0] + col[-1][0]), [entry[1] for entry in col])
            for col in merged
        ]

    if thresh is not None:
        left_items = [(i, v, False) for i, v in enumerate(q_vals) if v <= thresh]
        right_items = [(i, v, True) for i, v in enumerate(q_vals) if v > thresh]
        left_cols = _bin_group(left_items)
        right_cols = _bin_group(right_items)
        xt = _x(thresh)
        # Keep dots cleanly separated from the threshold dashed line
        sep = r_base + 0.8
        if xt - pad_x > sep + 1.0:
            left_cols = [(min(cx, xt - sep), grp) for cx, grp in left_cols]
        if (width - pad_x) - xt > sep + 1.0:
            right_cols = [(max(cx, xt + sep), grp) for cx, grp in right_cols]
        columns = left_cols + right_cols
    else:
        columns = _bin_group([(i, v, False) for i, v in enumerate(q_vals)])

    max_stack = max((len(grp) for _, grp in columns), default=1)
    avail_h = max(base_y - 1.4, 4.0)
    if max_stack * (2.0 * r_base + 0.45) > avail_h:
        r_eff = min(r_base, max(0.8, (avail_h / max_stack) * 0.44))
    else:
        r_eff = r_base
    step_y = (
        min(2.0 * r_eff + 0.45, (avail_h - 2.0 * r_eff) / max(max_stack - 1, 1))
        if max_stack > 1
        else 0.0
    )
    cy_0 = base_y - r_eff - 0.6
    pct_per_dot = 100.0 / k_dots
    dot_pct_str = f"{pct_per_dot:.0f}%" if abs(pct_per_dot - round(pct_per_dot)) < 1e-6 else f"{pct_per_dot:.1f}%"

    svg_parts: list[str] = [
        (
            f'<line x1="{pad_x:.1f}" y1="{base_y:.1f}" x2="{width - pad_x:.1f}" y2="{base_y:.1f}" '
            f'stroke="{theme.grid}" stroke-width="0.9"/>'
        ),
    ]

    if thresh is not None:
        xt = _x(thresh)
        t_tip = html.escape(f"Threshold: {_fmt_val(thresh, unit=unit)}")
        svg_parts.append(
            f'<line x1="{xt:.2f}" y1="1.0" x2="{xt:.2f}" y2="{height - 1.0:.2f}" '
            f'stroke="{exceed_color}" stroke-width="1.15" stroke-dasharray="2,1.5">'
            f"<title>{t_tip}</title></line>"
        )
    else:
        # Subtle median baseline tick
        xm = _x(med)
        svg_parts.append(
            f'<line x1="{xm:.2f}" y1="{base_y - 1.2:.2f}" x2="{xm:.2f}" y2="{height - 0.4:.2f}" '
            f'stroke="{theme.ink}" stroke-width="1.3" stroke-linecap="round"/>'
        )

    for cx, grp in columns:
        for stack_idx, (q_idx, qv, is_exceed) in enumerate(grp):
            cy = cy_0 - stack_idx * step_y
            dot_col = exceed_color if is_exceed else primary
            q_tip = html.escape(
                f"Quantile {q_idx + 1}/{k_dots}: {_fmt_val(qv, unit=unit)} ({dot_pct_str})"
                + (" — above threshold" if is_exceed else "")
            )
            if is_exceed:
                svg_parts.append(
                    f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r_eff:.2f}" '
                    f'fill="{dot_col}" stroke="{theme.background}" stroke-width="0.35">'
                    f"<title>{q_tip}</title></circle>"
                )
            else:
                svg_parts.append(
                    f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r_eff:.2f}" '
                    f'fill="{dot_col}" fill-opacity="0.88">'
                    f"<title>{q_tip}</title></circle>"
                )

    # 9-slot Unicode & ASCII density blocks with optional threshold bar
    # Use raw samples when dense enough to avoid small-k pigeonhole gaps across 9 bins.
    density_src = nums if len(nums) >= k_dots else q_vals
    n_bins = 9
    bin_counts = [0] * n_bins
    for dv in density_src:
        b = min(n_bins - 1, max(0, int(((dv - d_lo) / span) * n_bins)))
        bin_counts[b] += 1
    max_c = max(bin_counts) or 1
    u_chars: list[str] = []
    a_chars: list[str] = []
    for cnt in bin_counts:
        if cnt == 0:
            u_chars.append("·")
            a_chars.append(".")
        else:
            u_idx = max(0, min(len(_SPARK_BLOCKS) - 1, round((cnt / max_c) * (len(_SPARK_BLOCKS) - 1))))
            a_idx = max(0, min(len(_ASCII_DENSITY) - 1, round((cnt / max_c) * (len(_ASCII_DENSITY) - 1))))
            u_chars.append(_SPARK_BLOCKS[u_idx])
            a_chars.append(_ASCII_DENSITY[a_idx])

    if thresh is not None:
        t_pos = max(0.0, min(1.0, (thresh - d_lo) / span))
        ins = max(0, min(n_bins, round(t_pos * n_bins)))
        u_chars.insert(ins, "│")
        a_chars.insert(ins, "|")

    u_glyph = f"[{''.join(u_chars)}]"
    a_glyph = f"[{''.join(a_chars)}]"

    med_str = _fmt_val(med, unit=unit)
    prefix = f"{label}: " if label else ""
    p_exceed: float | None = None
    dots_above: int | None = None
    n_above: int | None = None

    if thresh is not None:
        n_above = sum(1 for v in nums if v > thresh)
        p_exceed = n_above / len(nums)
        dots_above = sum(1 for qv in q_vals if qv > thresh)
        thresh_str = _fmt_val(thresh, unit=unit)
        pct_str = _fmt_pct(100.0 * p_exceed)
        val_str = f"P>{thresh_str} {pct_str}"
        compact_val = pct_str
        alt = (
            f"{prefix}quantile dotplot ({k_dots} dots, {dot_pct_str} each): "
            f"{val_str} ({dots_above}/{k_dots} dots above {thresh_str})"
        )
    else:
        val_str = f"med {med_str}"
        compact_val = med_str
        alt = (
            f"{prefix}quantile dotplot ({k_dots} dots, {dot_pct_str} each): "
            f"median {med_str}, IQR [{_fmt_val(q25)}, {_fmt_val(q75)}]"
        )

    facts = [
        f"{prefix}{k_dots} equal-probability quantiles ({dot_pct_str} each) from n={len(nums)} samples",
        (
            f"Median {med_str}, IQR [{_fmt_val(q25, unit=unit)}, {_fmt_val(q75, unit=unit)}], "
            f"range {_fmt_val(nums[0], unit=unit)} to {_fmt_val(nums[-1], unit=unit)}"
        ),
    ]
    if thresh is not None and p_exceed is not None and n_above is not None and dots_above is not None:
        thresh_str = _fmt_val(thresh, unit=unit)
        facts.append(
            f"Empirical P(X > {thresh_str}) = {100.0 * p_exceed:.1f}% "
            f"({n_above}/{len(nums)} samples; {dots_above}/{k_dots} quantile dots above threshold)"
        )
    if dropped:
        facts.append(f"{dropped} non-finite sample{'s' if dropped != 1 else ''} dropped")

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        distribution = mint.distribution

        name = label or "Predictive distribution"
        ref_arg: tuple[float, str] | None = (
            (thresh, f"Threshold {_fmt_val(thresh, unit=unit)}") if thresh is not None else None
        )
        title_txt = (
            f"{name}: {val_str} ({dots_above}/{k_dots} quantiles above threshold)"
            if thresh is not None
            else f"{name} centers at median {med_str} ({k_dots} quantiles)"
        )
        panel = distribution(
            {name: nums},
            mode="quantile",
            quantiles=k_dots,
            reference=ref_arg,
            title=title_txt,
            label=label or "Value",
            unit=unit,
        )
        return mint.explain(f"{prefix}{val_str} across n={len(nums)} samples", panel, style=_mintfig_style_name(theme))

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="quantiles",
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
            "n": len(nums),
            "n_dots": k_dots,
            "quantiles": q_vals,
            "median": med,
            "q25": q25,
            "q75": q75,
            "threshold": thresh,
            "p_exceed": p_exceed,
            "dots_above": dots_above,
        },
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 3. mintchip.evidence — Calibrated epistemic strength & sample-size meter
# --------------------------------------------------------------------------- #


def evidence(
    *,
    p: float | None = None,
    bf: float | None = None,
    n: int | None = None,
    level: str | None = None,
    label: str | None = None,
    width: int = 44,
    height: int = 14,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a calibrated epistemic strength & sample-size signal meter.

    Maps a Bayes factor (``bf``, Kass & Raftery tiers), *p*-value (``p``), or
    explicit ``level`` (``"none"``, ``"weak"``, ``"moderate"``, ``"strong"``,
    ``"decisive"``) onto a 5-bar signal meter instead of a naive binary
    significance cliff. When ``n < 10``, emits an epistemic low-power warning
    and tints the bars amber.
    """
    if p is None and bf is None and level is None:
        raise ChipError(
            "inline.evidence requires at least one of p=, bf=, or level=.",
            fix_hint='Pass e.g. mintchip.evidence(p=0.002, n=48), bf=42, or level="strong".',
        )

    p_val: float | None = None
    if p is not None:
        if not _is_finite(p) or not (0.0 <= float(p) <= 1.0):
            raise ChipError(
                f"inline.evidence p must be a finite number in [0, 1]; got {p!r}.",
                fix_hint="Pass a valid p-value between 0 and 1, e.g. p=0.002.",
            )
        p_val = float(p)

    bf_val: float | None = None
    if bf is not None:
        if not _is_finite(bf) or float(bf) < 0.0:
            raise ChipError(
                f"inline.evidence bf must be a finite non-negative Bayes factor; got {bf!r}.",
                fix_hint="Pass a non-negative Bayes factor, e.g. bf=18.5.",
            )
        bf_val = float(bf)

    n_val: int | None = None
    if n is not None:
        if isinstance(n, bool) or not isinstance(n, numbers.Integral) or int(n) < 1:
            raise ChipError(
                f"inline.evidence n must be a positive integer; got {n!r}.",
                fix_hint="Pass sample size as a positive integer, e.g. n=48.",
            )
        n_val = int(n)

    resolved_level: str | None = None
    if level is not None:
        if not isinstance(level, str) or not level.strip():
            raise ChipError(
                f"inline.evidence level must be one of {sorted(_EVIDENCE_TIERS)}; got {level!r}.",
                fix_hint='Use level="none", "weak", "moderate", "strong", or "decisive".',
            )
        norm_lvl = level.strip().lower()
        norm_lvl = _EVIDENCE_ALIASES.get(norm_lvl, norm_lvl)
        if norm_lvl not in _EVIDENCE_TIERS:
            raise ChipError(
                f"Unknown inline.evidence level {level!r}.",
                fix_hint='Use level="none", "weak", "moderate", "strong", or "decisive".',
            )
        resolved_level = norm_lvl

    width, height = _validate_size(width, height, "inline.evidence")
    theme = _resolve_theme(style, palette=palette, accent=accent)

    # Resolve canonical evidence level & source basis
    if resolved_level is not None:
        tier_name = resolved_level
        basis = "explicit level"
    elif bf_val is not None:
        tier_name = _tier_from_bf(bf_val)
        basis = "Bayes factor (Kass & Raftery)"
    else:
        assert p_val is not None
        tier_name = _tier_from_p(p_val)
        basis = "p-value calibration"

    filled_bars, guidance = _EVIDENCE_TIERS[tier_name]
    underpowered = n_val is not None and n_val < 10

    warnings: list[str] = []
    if underpowered and n_val is not None:
        warnings.append(
            f"Small sample (n={n_val}): treat as preliminary — low statistical power increases false-positive risk."
        )

    ok_color = theme.series_colors[2] if len(theme.series_colors) > 2 else theme.series_colors[0]
    amber_color = theme.series_colors[3] if len(theme.series_colors) > 3 else theme.series_colors[1]
    muted_color = theme.muted

    if underpowered:
        bar_fill = amber_color
    elif filled_bars <= 1:
        bar_fill = muted_color
    else:
        bar_fill = ok_color
    unfilled_stroke = amber_color if (underpowered and filled_bars == 0) else theme.context_line

    # 5 ascending signal-grade SVG bars
    pad_x = 2.0
    pad_y = 1.5
    gap = 2.2
    inner_w = max(width - 2 * pad_x, 12.0)
    inner_h = max(height - 2 * pad_y, 6.0)
    bar_w = max((inner_w - 4.0 * gap) / 5.0, 2.0)
    fracs = (0.34, 0.50, 0.67, 0.84, 1.00)

    svg_parts: list[str] = []
    for i, frac in enumerate(fracs):
        bh = max(2.4, frac * inner_h)
        bx = pad_x + i * (bar_w + gap)
        by = height - pad_y - bh
        is_filled = i < filled_bars
        bar_tip = html.escape(
            f"Signal {i + 1}/5 ({_BAR_TIER_LABELS[i]}): "
            + ("active" if is_filled else "inactive")
            + (" [low power]" if underpowered else "")
        )
        if is_filled:
            svg_parts.append(
                f'<rect x="{bx:.2f}" y="{by:.2f}" width="{bar_w:.2f}" height="{bh:.2f}" '
                f'fill="{bar_fill}" rx="1.1"><title>{bar_tip}</title></rect>'
            )
        else:
            svg_parts.append(
                f'<rect x="{bx + 0.45:.2f}" y="{by + 0.45:.2f}" '
                f'width="{max(bar_w - 0.9, 1.0):.2f}" height="{max(bh - 0.9, 1.0):.2f}" '
                f'fill="none" stroke="{unfilled_stroke}" stroke-width="0.9" rx="1.0">'
                f"<title>{bar_tip}</title></rect>"
            )

    u_glyph = "[" + ("▰" * filled_bars) + ("▱" * (5 - filled_bars)) + "]"
    a_glyph = "[" + ("#" * filled_bars) + ("." * (5 - filled_bars)) + "]"

    detail_parts: list[str] = []
    if bf_val is not None:
        detail_parts.append(f"BF={_fmt_val(bf_val)}")
    if p_val is not None:
        detail_parts.append(f"p={_fmt_p(p_val)}")
    if n_val is not None:
        detail_parts.append(f"n={n_val}")

    val_str = f"{tier_name} ({', '.join(detail_parts)})" if detail_parts else tier_name
    compact_val = tier_name
    prefix = f"{label}: " if label else ""

    facts = [
        f"{prefix}evidence tier is {tier_name} ({filled_bars}/5 signal bars; basis: {basis})",
        f"Interpretation: {guidance}",
    ]
    if bf_val is not None:
        bf_tier = _tier_from_bf(bf_val)
        facts.append(f"Bayes factor BF={_fmt_val(bf_val)} maps to {bf_tier} (Kass & Raftery)")
    if p_val is not None:
        p_tier = _tier_from_p(p_val)
        facts.append(f"p={_fmt_p(p_val)} maps to {p_tier} evidence")
    if n_val is not None:
        power_note = "underpowered (n < 10; preliminary)" if underpowered else "sample size recorded"
        facts.append(f"Sample size n={n_val} ({power_note})")

    alt = f"{prefix}evidence strength {val_str} ({filled_bars}/5)"
    if underpowered:
        alt += " — small sample warning"

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.16em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        table = mint.table

        name = label or "Evidence"
        rows: list[dict[str, Any]] = [
            {
                "Metric": "Tier",
                "Value": f"{tier_name} ({filled_bars}/5)",
                "Note": guidance,
            }
        ]
        if bf_val is not None:
            rows.append(
                {
                    "Metric": "Bayes factor",
                    "Value": f"BF={_fmt_val(bf_val)}",
                    "Note": f"Kass & Raftery: {_tier_from_bf(bf_val)}",
                }
            )
        if p_val is not None:
            rows.append(
                {
                    "Metric": "p-value",
                    "Value": f"p={_fmt_p(p_val)}",
                    "Note": f"Calibrated: {_tier_from_p(p_val)}",
                }
            )
        if n_val is not None:
            rows.append(
                {
                    "Metric": "Sample size",
                    "Value": f"n={n_val}",
                    "Note": "Preliminary (n < 10)" if underpowered else "Adequate sample",
                }
            )
        panel = table(
            rows,
            highlight="Tier",
            title=f"{name}: {val_str}",
        )
        takeaway = (
            f"{name} shows {val_str} — treat as preliminary (n={n_val})"
            if underpowered
            else f"{name} shows {val_str}"
        )
        return mint.explain(takeaway, panel, style=_mintfig_style_name(theme))

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="evidence",
        svg=svg,
        text=u_glyph,
        ascii_text=a_glyph,
        value_text=val_str,
        compact_value=compact_val,
        alt_text=alt,
        facts=facts,
        theme=theme,
        label=label,
        warnings=warnings,
        data={
            "level": tier_name,
            "tier": filled_bars,
            "p": p_val,
            "bf": bf_val,
            "n": n_val,
            "underpowered": underpowered,
            "basis": basis,
        },
        expand_explanation=exp_obj,
    )
