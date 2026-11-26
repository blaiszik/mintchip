"""Tufte word-sized micro-graphics and expandable evidence chips (``mintchip``).

Embeds high-legibility scientific micro-visuals directly inside conversational
prose, markdown tables, terminals, notebooks, and interactive HTML briefings:

- ``mintchip.spark`` — compact trend / convergence sparklines with optional
  reference band (normal range), subtle area wash, extrema marks, and endpoint.
- ``mintchip.ci`` — confidence/credible interval whiskers with reference
  tick (e.g. null = 0), nested inner CI, shared-domain support, and redundant
  encoding (solid dot when excluding reference, hollow dot when crossing it).
- ``mintchip.dist`` — raw observation mini-beeswarm dot-strips (or
  micro-histograms for large *n*) with IQR pill, median tick, and accented
  1.5×IQR outlier rings.
- ``mintchip.bar`` — zero-based Tufte bullet bars with crisp zero anchor,
  optional qualitative bands, and baseline/target ticks.
- ``mintchip.strip`` — CVD-safe redundant-encoded pass/fail/warn/skip strips
  or sequential/diverging numeric heat strips.

Any :class:`InlineGraphic` renders cleanly across four surfaces:

1. ``.svg`` — pure baseline-aligned inline SVG themed to ``mintfig`` tokens.
2. ``.text`` / ``str(g)`` — compact Unicode (or ASCII) micro-glyphs for chat,
   terminals, and plain Markdown.
3. ``.html()`` / ``_repr_html_()`` — clickable inline "evidence chip" that
   expands into computed ``facts`` and an embedded full ``mint.explain`` figure.
4. ``.markdown()`` — Markdown-ready Unicode or base64 SVG data-URI embed.
"""

from __future__ import annotations

import base64
import html
import json
import math
import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .themes import Theme, apply_accent, apply_palette, get_theme, relative_luminance

__all__ = [
    "Chip",
    "ChipError",
    "InlineGraphic",
    "bar",
    "ci",
    "dist",
    "document",
    "format_prose",
    "shared_domain",
    "spark",
    "strip",
]


class ChipError(ValueError):
    """Validation error with an actionable ``fix_hint`` for agents and humans."""

    def __init__(self, message: str, *, fix_hint: str | None = None) -> None:
        self.fix_hint = fix_hint
        full = f"{message} Fix: {fix_hint}" if fix_hint else message
        super().__init__(full)


ExplainError = ChipError


def _require_mintfig() -> Any:
    """Lazily import optional ``mintfig`` only when ``expand=True`` is requested."""
    try:
        import mintfig as mint
    except ImportError as exc:
        raise ChipError(
            "expand=True requires the optional 'mintfig' package to synthesize full multi-panel figures.",
            fix_hint='Install with: pip install "mintchip[mintfig]" (or omit expand=True).',
        ) from exc
    return mint


def _mintfig_style_name(theme: Theme) -> str:
    return "mintfig" if theme.name == "default" else theme.name

_SPARK_BLOCKS = "▁▂▃▄▅▆▇█"
_ASCII_SPARK = "._-=+*#@"
_BAR_BLOCKS = (" ", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█")

_PASS_TOKENS = frozenset({"pass", "passed", "ok", "true", "yes", "1", "good", "hit"})
_FAIL_TOKENS = frozenset({"fail", "failed", "err", "error", "false", "no", "0", "bad", "miss"})
_WARN_TOKENS = frozenset({"warn", "warning", "flaky", "partial", "maybe", "mixed"})
_SKIP_TOKENS = frozenset({"skip", "skipped", "na", "n/a", "none", "null", "missing", "-"})


def _is_finite(val: Any) -> bool:
    if isinstance(val, bool) or val is None:
        return False
    try:
        return math.isfinite(float(val))
    except (TypeError, ValueError):
        return False


def _fmt_val(
    val: float,
    *,
    unit: str | None = None,
    signed: bool = False,
    ascii_only: bool = False,
) -> str:
    """Format a scalar cleanly to ~3 significant digits matching mintfig style."""
    if not math.isfinite(val):
        return "-" if ascii_only else "—"
    abs_v = abs(val)
    if abs_v == 0.0:
        core = "0"
    elif abs_v >= 1e6 or (0 < abs_v < 1e-3):
        core = f"{val:.2e}"
    elif abs(val - round(val)) < 1e-9 and abs_v < 1e6:
        core = f"{round(val):,}"
    else:
        core = f"{val:.3g}"
    if signed and val > 0:
        core = f"+{core}"
    if not ascii_only:
        core = core.replace("-", "\N{MINUS SIGN}")
    if unit:
        sep = "" if unit in {"%", "°", "°C", "°F", "×"} else " "
        return f"{core}{sep}{unit}"
    return core


def _resolve_theme(
    style: str | Theme = "default",
    *,
    palette: str | None = None,
    accent: str | None = None,
) -> Theme:
    theme = get_theme(style)
    theme = apply_palette(theme, palette)
    theme = apply_accent(theme, accent)
    return theme


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lerp_hex(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


def _sample_stops(stops: Sequence[str], t: float) -> str:
    if not stops:
        return "#1F5A9D"
    if len(stops) == 1:
        return stops[0]
    t = max(0.0, min(1.0, t))
    pos = t * (len(stops) - 1)
    idx = min(math.floor(pos), len(stops) - 2)
    frac = pos - idx
    return _lerp_hex(stops[idx], stops[idx + 1], frac)


def _quantiles(sorted_vals: Sequence[float]) -> tuple[float, float, float]:
    """Return (q25, median, q75) using linear interpolation."""
    n = len(sorted_vals)
    if n == 1:
        v = sorted_vals[0]
        return v, v, v

    def _pct(p: float) -> float:
        idx = p * (n - 1)
        lo = math.floor(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac

    return _pct(0.25), _pct(0.5), _pct(0.75)


def shared_domain(
    *items: float | Sequence[float | None],
    reference: float | None = None,
    pad: float = 0.08,
) -> tuple[float, float]:
    """Compute a common ``(low, high)`` domain across multiple intervals or samples.

    Pass the returned tuple to ``domain=`` on sibling ``mintchip.ci`` or
    ``mintchip.dist`` chips so comparisons inside a paragraph or table share
    one honest visual scale.
    """
    vals: list[float] = []
    for item in items:
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            vals.extend(float(v) for v in item if _is_finite(v))
        elif _is_finite(item):
            vals.append(float(item))
    if reference is not None and math.isfinite(reference):
        vals.append(float(reference))
    if not vals:
        raise ExplainError(
            "shared_domain requires at least one finite numeric value.",
            fix_hint="Pass sequences or (lo, hi) tuples, e.g. mintchip.shared_domain((0.05, 0.11), (-0.02, 0.04), reference=0).",
        )
    lo, hi = min(vals), max(vals)
    margin = max((hi - lo) * max(0.0, float(pad)), 1e-6)
    return (lo - margin, hi + margin)


def _extract_svg_markup(exp: Any) -> str:
    """Render an Explanation figure to a clean inline SVG string."""
    import io

    buf = io.StringIO()
    exp.fig.savefig(
        buf,
        format="svg",
        facecolor=exp.theme.background,
        edgecolor="none",
    )
    raw = buf.getvalue()
    raw = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", raw, count=1, flags=re.IGNORECASE)
    raw = re.sub(r"^\s*<!DOCTYPE[^>]*>\s*", "", raw, count=1, flags=re.IGNORECASE)
    raw = re.sub(
        r"<svg\b([^>]*)>",
        lambda m: (
            "<svg"
            + re.sub(r'\s(?:width|height)="[^"]*"', "", m.group(1))
            + ' style="width:100%;height:auto;display:block;"'
            + ">"
        ),
        raw,
        count=1,
    )
    return raw


def _resolve_expand_explanation(
    expand: bool | Any | None,
    auto_builder: Any,
) -> Any | None:
    if expand is None or expand is False:
        return None
    if expand is True and callable(auto_builder):
        return auto_builder()
    if hasattr(expand, "fig") and hasattr(expand, "takeaway"):
        return expand
    if hasattr(expand, "kind") and hasattr(expand, "spec"):
        mint = _require_mintfig()
        title = getattr(expand, "title", None) or getattr(expand, "label", None) or "Evidence detail"
        return mint.explain(title, expand)
    raise ChipError(
        f"expand must be bool, a mintfig Panel/Explanation, or None; got {type(expand).__name__}.",
        fix_hint="Pass expand=True (with mintfig installed) or an Explanation from mint.explain(...).",
    )


@dataclass
class Chip:
    """A Tufte word-sized micro-graphic rendered for prose, terminal, and HTML."""

    kind: str
    svg: str
    text: str
    ascii_text: str
    value_text: str
    alt_text: str
    facts: list[str]
    theme: Theme
    compact_value: str | None = None
    label: str | None = None
    unit: str | None = None
    error_label: str | None = None
    warnings: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    expand_explanation: Any | None = field(default=None, repr=False)
    _expand_svg_cache: str | None = field(default=None, init=False, repr=False)

    def __str__(self) -> str:
        """Compact Unicode representation for f-strings, terminals, and Markdown."""
        return self.to_text(ascii_only=False)

    def to_text(
        self,
        *,
        ascii_only: bool = False,
        include_value: bool = True,
        compact: bool = False,
    ) -> str:
        glyph = self.ascii_text if ascii_only else self.text
        val = (self.compact_value or self.value_text) if compact else self.value_text
        if ascii_only:
            val = val.replace("\N{MINUS SIGN}", "-").replace("—", "-")
        if include_value and val:
            return f"{val} {glyph}"
        return glyph

    def markdown(self, *, mode: str = "unicode", compact: bool = False) -> str:
        """Return Markdown embed: ``"unicode"`` (default) or ``"svg_uri"``."""
        if mode == "unicode":
            return f"`{self.to_text(compact=compact)}`"
        if mode == "svg_uri":
            b64 = base64.b64encode(self.svg.encode("utf-8")).decode("ascii")
            alt = self.alt_text.replace("]", r"\]")
            return f"![{alt}](data:image/svg+xml;base64,{b64})"
        raise ExplainError(
            f"Unknown markdown mode {mode!r}.",
            fix_hint='Use mode="unicode" or mode="svg_uri".',
        )

    def _get_expand_svg(self) -> str | None:
        if self.expand_explanation is None:
            return None
        if self._expand_svg_cache is None:
            self._expand_svg_cache = _extract_svg_markup(self.expand_explanation)
        return self._expand_svg_cache

    def html(
        self,
        *,
        show_value: bool = True,
        show_label: bool = False,
        compact: bool = False,
        expandable: bool = True,
        chip_id: str | None = None,
    ) -> str:
        """Return a self-contained inline HTML evidence chip.

        When ``expandable=True``, renders as an interactive pill that reveals
        computed facts (and the attached full ``mint.explain`` figure, if any)
        when clicked inside a document, inline widget, or notebook.
        """
        is_dark = relative_luminance(self.theme.background) < 0.35
        pill_bg = "rgba(255,255,255,0.06)" if is_dark else "rgba(26,29,33,0.035)"
        pill_border = self.theme.grid
        ink = self.theme.ink
        muted = self.theme.muted

        val_display = (self.compact_value or self.value_text) if compact else self.value_text
        parts: list[str] = []
        if show_label and self.label:
            parts.append(
                f'<span class="mf-chip-label" style="color:{muted};font-size:0.86em;'
                f'margin-right:4px;">{html.escape(self.label)}</span>'
            )
        if show_value and val_display:
            parts.append(
                f'<span class="mf-chip-val" style="font-variant-numeric:tabular-nums;'
                f'font-weight:600;color:{ink};margin-right:5px;">'
                f"{html.escape(val_display)}</span>"
            )
        parts.append(
            f'<span class="mf-chip-svg" style="display:inline-flex;align-items:center;">{self.svg}</span>'
        )

        has_fig = self.expand_explanation is not None
        if expandable and has_fig:
            parts.append(
                f'<span class="mf-chip-caret" aria-hidden="true" '
                f'style="color:{muted};font-size:0.72em;margin-left:4px;">↗</span>'
            )

        inner = "".join(parts)
        base_style = (
            f"display:inline-flex;align-items:center;vertical-align:-0.2em;"
            f"padding:1px 6px;border-radius:5px;background:{pill_bg};"
            f"border:1px solid {pill_border};line-height:1.25;white-space:nowrap;"
            f"font-size:0.92em;"
            f"font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        )

        if not expandable:
            return (
                f'<span class="mf-chip mf-chip-static" title="{html.escape(self.alt_text)}" '
                f'style="{base_style}">{inner}</span>'
            )

        payload: dict[str, Any] = {
            "kind": self.kind,
            "label": self.label or self.kind,
            "value": self.value_text,
            "alt": self.alt_text,
            "facts": self.facts,
            "warnings": self.warnings,
            "error_label": self.error_label,
            "has_figure": has_fig,
        }
        if has_fig and self.expand_explanation is not None:
            payload["figure_title"] = self.expand_explanation.takeaway
            payload["figure_svg"] = self._get_expand_svg()

        payload_attr = html.escape(json.dumps(payload, ensure_ascii=False), quote=True)
        id_attr = f' id="{html.escape(chip_id, quote=True)}"' if chip_id else ""
        interactive_style = (
            base_style + "cursor:pointer;transition:border-color 120ms ease,background 120ms ease;"
        )
        return (
            f'<button type="button"{id_attr} class="mf-chip mf-chip-interactive" '
            f'data-mf-chip="{payload_attr}" '
            f'aria-label="{html.escape(self.alt_text, quote=True)}" '
            f'title="{html.escape(self.alt_text, quote=True)}" '
            f'style="{interactive_style}">{inner}</button>'
        )

    def _repr_html_(self) -> str:
        """Render directly inside Jupyter notebooks with working inline expansion."""
        return _wrap_standalone_snippet(self.html(show_label=bool(self.label)), self.theme)

    def summary(self) -> dict[str, Any]:
        """Return a structured JSON-friendly summary matching mintfig's audit style."""
        return {
            "kind": self.kind,
            "label": self.label,
            "value": self.value_text,
            "text": self.to_text(),
            "alt_text": self.alt_text,
            "facts": list(self.facts),
            "warnings": list(self.warnings),
            "expandable": self.expand_explanation is not None,
        }

    def save(self, path: str | Path) -> dict[str, Any]:
        """Write standalone ``.svg`` or interactive ``.html`` file."""
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        suffix = dest.suffix.lower()
        if suffix == ".svg":
            dest.write_text(self.svg, encoding="utf-8")
        elif suffix in {".html", ".htm"}:
            title = self.label or f"mintchip {self.kind}"
            dest.write_text(
                document(title, [self.html(show_label=True)], style=self.theme),
                encoding="utf-8",
            )
        else:
            raise ExplainError(
                f"Unsupported inline save extension {suffix!r}.",
                fix_hint='Save inline graphics as ".svg" or ".html".',
            )
        out = self.summary()
        out["path"] = str(dest)
        return out


# --------------------------------------------------------------------------- #
# 1. mintchip.spark — Tufte word-sized sparkline
# --------------------------------------------------------------------------- #


def spark(
    values: Sequence[float | None],
    *,
    label: str | None = None,
    unit: str | None = None,
    band: tuple[float, float] | None = None,
    reference: float | None = None,
    show_extrema: bool = True,
    show_end: bool = True,
    area_fill: bool = True,
    width: int = 70,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized Tufte sparkline for trends, losses, or traces."""
    raw = list(values)
    pts: list[tuple[int, float]] = [(i, float(v)) for i, v in enumerate(raw) if _is_finite(v)]
    if len(pts) < 2:
        raise ExplainError(
            "inline.spark requires at least 2 finite numeric values.",
            fix_hint="Pass a sequence of 2+ numbers, e.g. mintchip.spark([0.9, 0.6, 0.4]).",
        )

    theme = _resolve_theme(style, palette=palette, accent=accent)
    ys = [v for _, v in pts]
    v_min, v_max = min(ys), max(ys)
    lo, hi = v_min, v_max
    if band is not None:
        lo = min(lo, float(band[0]), float(band[1]))
        hi = max(hi, float(band[0]), float(band[1]))
    if reference is not None and math.isfinite(reference):
        lo = min(lo, float(reference))
        hi = max(hi, float(reference))

    span = hi - lo
    pad_x = 3.2
    pad_y = 2.6
    inner_w = max(width - 2 * pad_x, 4.0)
    inner_h = max(height - 2 * pad_y, 4.0)
    n_slots = max(len(raw) - 1, 1)

    def _x(idx: int) -> float:
        return pad_x + (idx / n_slots) * inner_w

    def _y(val: float) -> float:
        if span <= 0:
            return height / 2.0
        return pad_y + (1.0 - (val - lo) / span) * inner_h

    svg_parts: list[str] = []
    if band is not None:
        b_lo, b_hi = sorted((float(band[0]), float(band[1])))
        y_top = _y(b_hi)
        y_bot = _y(b_lo)
        svg_parts.append(
            f'<rect x="{pad_x:.1f}" y="{y_top:.2f}" width="{inner_w:.1f}" '
            f'height="{max(y_bot - y_top, 1.2):.2f}" fill="{theme.context_fill}" '
            f'fill-opacity="0.42" rx="1"/>'
        )
        # Subtle hairlines delimiting the target/normal band
        svg_parts.append(
            f'<line x1="{pad_x:.1f}" y1="{y_top:.2f}" x2="{width - pad_x:.1f}" y2="{y_top:.2f}" '
            f'stroke="{theme.context_line}" stroke-width="0.5" stroke-opacity="0.7"/>'
        )
        svg_parts.append(
            f'<line x1="{pad_x:.1f}" y1="{y_bot:.2f}" x2="{width - pad_x:.1f}" y2="{y_bot:.2f}" '
            f'stroke="{theme.context_line}" stroke-width="0.5" stroke-opacity="0.7"/>'
        )
    if reference is not None and math.isfinite(reference):
        ry = _y(float(reference))
        svg_parts.append(
            f'<line x1="{pad_x:.1f}" y1="{ry:.2f}" x2="{width - pad_x:.1f}" y2="{ry:.2f}" '
            f'stroke="{theme.axis}" stroke-width="0.8" stroke-dasharray="2,1.8"/>'
        )

    # Split polyline across None/NaN gaps
    segments: list[list[tuple[int, float]]] = []
    cur: list[tuple[int, float]] = []
    for i, val in enumerate(raw):
        if _is_finite(val):
            cur.append((i, float(val)))  # type: ignore[arg-type]
        elif cur:
            segments.append(cur)
            cur = []
    if cur:
        segments.append(cur)

    line_color = theme.series_colors[0]
    base_y = height - pad_y + 0.5
    for seg in segments:
        coords = " ".join(f"{_x(i):.2f},{_y(v):.2f}" for i, v in seg)
        if area_fill and len(seg) >= 2 and band is None:
            poly = f"{_x(seg[0][0]):.2f},{base_y:.2f} {coords} {_x(seg[-1][0]):.2f},{base_y:.2f}"
            svg_parts.append(
                f'<polygon points="{poly}" fill="{line_color}" fill-opacity="0.10"/>'
            )
        svg_parts.append(
            f'<polyline points="{coords}" fill="none" stroke="{line_color}" '
            f'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
        )

    # Subtle hollow start anchor
    start_i, start_v = pts[0]
    svg_parts.append(
        f'<circle cx="{_x(start_i):.2f}" cy="{_y(start_v):.2f}" r="1.35" '
        f'fill="{theme.background}" stroke="{line_color}" stroke-width="0.9"/>'
    )

    if show_extrema and span > 0:
        min_pt = min(pts, key=lambda p: p[1])
        max_pt = max(pts, key=lambda p: p[1])
        for pt in (min_pt, max_pt):
            if pt not in {pts[0], pts[-1]}:
                svg_parts.append(
                    f'<circle cx="{_x(pt[0]):.2f}" cy="{_y(pt[1]):.2f}" r="1.3" '
                    f'fill="{theme.muted}"/>'
                )

    end_i, end_v = pts[-1]
    delta = end_v - start_v
    if show_end:
        end_color = theme.accent_colors[0]
        svg_parts.append(
            f'<circle cx="{_x(end_i):.2f}" cy="{_y(end_v):.2f}" r="2.2" '
            f'fill="{end_color}" stroke="{theme.background}" stroke-width="0.75"/>'
        )

    # Unicode & ASCII sparklines (downsample if > 14 points to stay word-sized)
    sample_ys = ys
    if len(sample_ys) > 14:
        step = (len(sample_ys) - 1) / 13.0
        sample_ys = [sample_ys[round(k * step)] for k in range(14)]
    uni_chars: list[str] = []
    asc_chars: list[str] = []
    for v in sample_ys:
        frac = 0.5 if span <= 0 else (v - lo) / span
        idx = max(0, min(len(_SPARK_BLOCKS) - 1, round(frac * (len(_SPARK_BLOCKS) - 1))))
        uni_chars.append(_SPARK_BLOCKS[idx])
        asc_chars.append(_ASCII_SPARK[idx])

    val_str = _fmt_val(end_v, unit=unit)
    delta_str = _fmt_val(delta, unit=unit, signed=True)
    direction = "flat" if abs(delta) <= 1e-12 else ("up" if delta > 0 else "down")
    prefix = f"{label}: " if label else ""
    facts = [
        f"{prefix}{_fmt_val(start_v, unit=unit)} → {val_str} ({delta_str}, {direction})",
        f"Range {_fmt_val(v_min, unit=unit)} to {_fmt_val(v_max, unit=unit)} across {len(pts)} points",
    ]
    if band is not None:
        b_lo, b_hi = sorted((float(band[0]), float(band[1])))
        status = "within" if b_lo <= end_v <= b_hi else "outside"
        facts.append(
            f"Latest value is {status} band [{_fmt_val(b_lo, unit=unit)}, {_fmt_val(b_hi, unit=unit)}]"
        )
    alt = f"{prefix}sparkline ending at {val_str} ({delta_str}; min {_fmt_val(v_min)}, max {_fmt_val(v_max)})"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        trend = mint.trend

        x_idx = list(range(len(raw)))
        name = label or "Series"
        ref_val = reference
        if ref_val is None and band is not None:
            ref_val = 0.5 * (float(band[0]) + float(band[1]))
        panel = trend(
            x_idx,
            {name: [float(v) if _is_finite(v) else None for v in raw]},
            title=f"{name} moves from {_fmt_val(start_v, unit=unit)} to {val_str}",
            label=label or "Value",
            x_label="Step",
            unit=unit,
            reference=ref_val,
        )
        return mint.explain(
            f"{name} shifted {delta_str} across {len(pts)} observations",
            panel,
            style=_mintfig_style_name(theme),
        )

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="spark",
        svg=svg,
        text="".join(uni_chars),
        ascii_text="".join(asc_chars),
        value_text=val_str,
        compact_value=val_str,
        alt_text=alt,
        facts=facts,
        theme=theme,
        label=label,
        unit=unit,
        data={"values": raw, "band": band, "reference": reference},
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 2. mintchip.ci — Inline uncertainty / confidence interval whisker
# --------------------------------------------------------------------------- #


def ci(
    estimate: float,
    error: float | tuple[float, float],
    *,
    error_label: str | None = None,
    inner_error: float | tuple[float, float] | None = None,
    reference: float | None = 0.0,
    domain: tuple[float, float] | None = None,
    label: str | None = None,
    unit: str | None = None,
    width: int = 78,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build an inline point-estimate + uncertainty whisker with reference tick.

    Uses redundant visual encoding for epistemic clarity (and grayscale/CVD
    safety): intervals that exclude ``reference`` render with a solid point mark
    in primary/accent ink; intervals that cross ``reference`` render with a
    hollow point mark in muted ink.
    """
    est = float(estimate)
    if not math.isfinite(est):
        raise ExplainError("inline.ci estimate must be finite.")

    if isinstance(error, (tuple, list)):
        if len(error) != 2:
            raise ExplainError("error tuple must have 2 elements (low, high).")
        lo_err, hi_err = sorted((float(error[0]), float(error[1])))
    else:
        half = abs(float(error))
        lo_err, hi_err = est - half, est + half

    inner_bounds: tuple[float, float] | None = None
    if inner_error is not None:
        if isinstance(inner_error, (tuple, list)):
            inner_bounds = tuple(sorted((float(inner_error[0]), float(inner_error[1]))))  # type: ignore[assignment]
        else:
            ih = abs(float(inner_error))
            inner_bounds = (est - ih, est + ih)

    theme = _resolve_theme(style, palette=palette, accent=accent)
    warnings: list[str] = []
    if not error_label:
        warnings.append(
            "Unnamed uncertainty interval: pass error_label= (e.g. '95% CI, n=12') so readers know what the whisker represents."
        )

    if domain is not None:
        d_lo, d_hi = sorted((float(domain[0]), float(domain[1])))
    else:
        pts_d = [lo_err, hi_err, est]
        if reference is not None and math.isfinite(reference):
            pts_d.append(float(reference))
        raw_lo, raw_hi = min(pts_d), max(pts_d)
        margin = max((raw_hi - raw_lo) * 0.16, 1e-6)
        d_lo, d_hi = raw_lo - margin, raw_hi + margin

    span = max(d_hi - d_lo, 1e-12)
    pad_x = 4.0
    inner_w = max(width - 2 * pad_x, 8.0)
    cy = height / 2.0

    def _x(v: float) -> float:
        t = max(0.0, min(1.0, (v - d_lo) / span))
        return pad_x + t * inner_w

    excludes_ref: bool | None = None
    if reference is not None and math.isfinite(reference):
        excludes_ref = hi_err < reference or lo_err > reference

    if excludes_ref is True:
        mark_color = (
            theme.accent_colors[0]
            if (reference is not None and est < reference)
            else theme.series_colors[0]
        )
    elif excludes_ref is False:
        mark_color = theme.muted
    else:
        mark_color = theme.series_colors[0]

    svg_parts: list[str] = [
        # Subtle scale axis
        (
            f'<line x1="{pad_x:.1f}" y1="{cy:.2f}" x2="{width - pad_x:.1f}" y2="{cy:.2f}" '
            f'stroke="{theme.grid}" stroke-width="1.0"/>'
        )
    ]
    if reference is not None and math.isfinite(reference) and d_lo <= reference <= d_hi:
        rx = _x(float(reference))
        svg_parts.append(
            f'<line x1="{rx:.2f}" y1="1.5" x2="{rx:.2f}" y2="{height - 1.5:.2f}" '
            f'stroke="{theme.zero_line}" stroke-width="1.05" stroke-opacity="0.65" stroke-dasharray="2,1.4"/>'
        )

    # Outer whisker + subtle end serifs
    x1, x2, xe = _x(lo_err), _x(hi_err), _x(est)
    svg_parts.append(
        f'<line x1="{x1:.2f}" y1="{cy:.2f}" x2="{x2:.2f}" y2="{cy:.2f}" '
        f'stroke="{mark_color}" stroke-width="1.5" stroke-linecap="round"/>'
    )
    svg_parts.append(
        f'<line x1="{x1:.2f}" y1="{cy - 2.0:.2f}" x2="{x1:.2f}" y2="{cy + 2.0:.2f}" '
        f'stroke="{mark_color}" stroke-width="1.0" stroke-opacity="0.75"/>'
    )
    svg_parts.append(
        f'<line x1="{x2:.2f}" y1="{cy - 2.0:.2f}" x2="{x2:.2f}" y2="{cy + 2.0:.2f}" '
        f'stroke="{mark_color}" stroke-width="1.0" stroke-opacity="0.75"/>'
    )

    # Optional nested inner CI (e.g. 50% CI inside 95% CI)
    if inner_bounds is not None:
        ix1, ix2 = _x(inner_bounds[0]), _x(inner_bounds[1])
        svg_parts.append(
            f'<line x1="{ix1:.2f}" y1="{cy:.2f}" x2="{ix2:.2f}" y2="{cy:.2f}" '
            f'stroke="{mark_color}" stroke-width="3.6" stroke-linecap="round" stroke-opacity="0.48"/>'
        )

    # Point estimate: solid dot when signal clears reference; hollow dot when crossing reference
    if excludes_ref is False:
        svg_parts.append(
            f'<circle cx="{xe:.2f}" cy="{cy:.2f}" r="2.55" fill="{theme.background}" '
            f'stroke="{mark_color}" stroke-width="1.45"/>'
        )
    else:
        svg_parts.append(
            f'<circle cx="{xe:.2f}" cy="{cy:.2f}" r="2.75" fill="{mark_color}" '
            f'stroke="{theme.background}" stroke-width="0.8"/>'
        )

    # Compact Unicode whisker diagram (11 slots) with redundant solid/hollow dot
    slots = 11
    u_buf = ["·"] * slots
    a_buf = ["."] * slots

    def _slot(v: float) -> int:
        t = max(0.0, min(1.0, (v - d_lo) / span))
        return round(t * (slots - 1))

    s_lo, s_hi, s_est = _slot(lo_err), _slot(hi_err), _slot(est)
    for k in range(s_lo, s_hi + 1):
        u_buf[k] = "─"
        a_buf[k] = "-"
    if reference is not None and math.isfinite(reference) and d_lo <= reference <= d_hi:
        s_ref = _slot(float(reference))
        u_buf[s_ref] = "│"
        a_buf[s_ref] = "|"
    u_buf[s_est] = "○" if excludes_ref is False else "●"
    a_buf[s_est] = "o" if excludes_ref is False else "*"
    u_glyph = f"[{''.join(u_buf)}]"
    a_glyph = f"[{''.join(a_buf)}]"

    signed = reference == 0.0
    compact_val = _fmt_val(est, unit=unit, signed=signed)
    val_str = f"{compact_val} [{_fmt_val(lo_err, signed=signed)}, {_fmt_val(hi_err, signed=signed)}]"
    prefix = f"{label}: " if label else ""
    err_desc = f" ({error_label})" if error_label else ""
    facts = [
        f"{prefix}estimate {compact_val}, interval [{_fmt_val(lo_err, unit=unit, signed=signed)}, {_fmt_val(hi_err, unit=unit, signed=signed)}]{err_desc}",
        f"Interval width {_fmt_val(hi_err - lo_err, unit=unit)}",
    ]
    if excludes_ref is not None and reference is not None:
        rel = "excludes" if excludes_ref else "crosses"
        facts.append(f"Interval {rel} reference {_fmt_val(reference, unit=unit)}")

    alt = f"{prefix}{val_str}{err_desc}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        compare = mint.compare

        name = label or "Estimate"
        verdict = (
            f"excludes reference {_fmt_val(reference, unit=unit)}"
            if excludes_ref is True and reference is not None
            else (
                f"crosses reference {_fmt_val(reference, unit=unit)}"
                if excludes_ref is False and reference is not None
                else f"centered at {_fmt_val(est, unit=unit)}"
            )
        )
        panel = compare(
            {name: est},
            error={name: (lo_err, hi_err)},
            error_label=error_label or "Interval",
            inner_error={name: inner_bounds} if inner_bounds is not None else None,
            reference=reference,
            zero=(reference == 0.0),
            title=f"{name} {verdict}",
            label=label or "Estimate",
            unit=unit,
        )
        return mint.explain(f"{name}: {val_str}{err_desc}", panel, style=_mintfig_style_name(theme))

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="ci",
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
        error_label=error_label,
        warnings=warnings,
        data={
            "estimate": est,
            "error": [lo_err, hi_err],
            "inner_error": list(inner_bounds) if inner_bounds else None,
            "reference": reference,
            "excludes_reference": excludes_ref,
        },
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 3. mintchip.dist — Mini-beeswarm dot-strip / micro-histogram + median/IQR
# --------------------------------------------------------------------------- #


def dist(
    values: Sequence[float],
    *,
    reference: float | None = None,
    domain: tuple[float, float] | None = None,
    label: str | None = None,
    unit: str | None = None,
    width: int = 78,
    height: int = 16,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized distribution strip showing raw points + median/IQR."""
    nums = sorted(float(v) for v in values if _is_finite(v))
    if len(nums) < 2:
        raise ExplainError(
            "inline.dist requires at least 2 finite observations.",
            fix_hint="Pass a sequence of 2+ numbers, e.g. mintchip.dist([1.1, 1.4, 1.3, 2.8]).",
        )

    theme = _resolve_theme(style, palette=palette, accent=accent)
    q25, med, q75 = _quantiles(nums)
    iqr = q75 - q25
    mean_v = statistics.fmean(nums)
    outliers = [v for v in nums if iqr > 0 and (v < q25 - 1.5 * iqr or v > q75 + 1.5 * iqr)]

    if domain is not None:
        d_lo, d_hi = sorted((float(domain[0]), float(domain[1])))
    else:
        pts_d = [nums[0], nums[-1]]
        if reference is not None and math.isfinite(reference):
            pts_d.append(float(reference))
        raw_lo, raw_hi = min(pts_d), max(pts_d)
        margin = max((raw_hi - raw_lo) * 0.08, 1e-6)
        d_lo, d_hi = raw_lo - margin, raw_hi + margin

    span = max(d_hi - d_lo, 1e-12)
    pad_x = 3.5
    inner_w = max(width - 2 * pad_x, 8.0)

    def _x(v: float) -> float:
        t = max(0.0, min(1.0, (v - d_lo) / span))
        return pad_x + t * inner_w

    svg_parts: list[str] = [
        # Baseline track
        (
            f'<line x1="{pad_x:.1f}" y1="{height - 2.0:.1f}" x2="{width - pad_x:.1f}" '
            f'y2="{height - 2.0:.1f}" stroke="{theme.grid}" stroke-width="0.9"/>'
        )
    ]
    cy = height / 2.0

    if reference is not None and math.isfinite(reference) and d_lo <= reference <= d_hi:
        rx = _x(float(reference))
        svg_parts.append(
            f'<line x1="{rx:.2f}" y1="1.5" x2="{rx:.2f}" y2="{height - 1.5:.2f}" '
            f'stroke="{theme.zero_line}" stroke-width="0.95" stroke-opacity="0.6" stroke-dasharray="2,1.5"/>'
        )

    primary = theme.series_colors[0]
    accent_c = theme.accent_colors[0]
    if len(nums) <= 40:
        # IQR shaded pill + mini-beeswarm stacking around centerline so clusters bulge visibly
        x_q25, x_q75 = _x(q25), _x(q75)
        svg_parts.append(
            f'<rect x="{x_q25:.2f}" y="{cy - 3.6:.2f}" width="{max(x_q75 - x_q25, 1.4):.2f}" '
            f'height="7.2" fill="{primary}" fill-opacity="0.16" rx="1.4"/>'
        )
        outlier_set = set(outliers)
        placed: list[tuple[float, float]] = []
        r_dot = 1.45
        y_candidates = (0.0, -2.3, 2.3, -4.3, 4.3, -1.2, 1.2)
        for v in nums:
            px = _x(v)
            chosen_dy = 0.0
            for dy in y_candidates:
                py = cy + dy
                if all(math.hypot(px - ox, py - oy) >= 2.25 for ox, oy in placed):
                    chosen_dy = dy
                    break
            py = cy + chosen_dy
            placed.append((px, py))
            if v in outlier_set:
                # Distinct hollow accent ring so outliers stand out in grayscale too
                svg_parts.append(
                    f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.0" fill="{theme.background}" '
                    f'stroke="{accent_c}" stroke-width="1.25"/>'
                )
            else:
                svg_parts.append(
                    f'<circle cx="{px:.2f}" cy="{py:.2f}" r="{r_dot:.2f}" '
                    f'fill="{primary}" fill-opacity="0.80"/>'
                )
    else:
        # Micro-histogram for larger samples (14 bins)
        n_bins = 14
        counts = [0] * n_bins
        for v in nums:
            b = min(n_bins - 1, max(0, int(((v - d_lo) / span) * n_bins)))
            counts[b] += 1
        max_c = max(counts) or 1
        bw = inner_w / n_bins
        for b, cnt in enumerate(counts):
            if cnt == 0:
                continue
            bh = max(1.5, (cnt / max_c) * (height - 4.0))
            bx = pad_x + b * bw
            by = height - 2.0 - bh
            svg_parts.append(
                f'<rect x="{bx:.2f}" y="{by:.2f}" width="{max(bw - 0.7, 1.0):.2f}" '
                f'height="{bh:.2f}" fill="{primary}" fill-opacity="0.68" rx="0.6"/>'
            )

    # Bold median vertical mark
    xm = _x(med)
    svg_parts.append(
        f'<line x1="{xm:.2f}" y1="1.8" x2="{xm:.2f}" y2="{height - 1.8:.2f}" '
        f'stroke="{theme.ink}" stroke-width="1.7" stroke-linecap="round"/>'
    )

    # Unicode micro-histogram (8 bins) with subtle empty-bin baseline dot
    u_bins = 8
    u_counts = [0] * u_bins
    for v in nums:
        b = min(u_bins - 1, max(0, int(((v - d_lo) / span) * u_bins)))
        u_counts[b] += 1
    u_max = max(u_counts) or 1
    u_chars = []
    a_chars = []
    for cnt in u_counts:
        if cnt == 0:
            u_chars.append("·")
            a_chars.append(".")
        else:
            idx = max(0, min(len(_SPARK_BLOCKS) - 1, round((cnt / u_max) * (len(_SPARK_BLOCKS) - 1))))
            u_chars.append(_SPARK_BLOCKS[idx])
            a_chars.append(_ASCII_SPARK[idx])
    u_glyph = f"│{''.join(u_chars)}│"
    a_glyph = f"|{''.join(a_chars)}|"

    compact_val = _fmt_val(med, unit=unit)
    val_str = f"med {compact_val} (IQR {_fmt_val(iqr)})"
    prefix = f"{label}: " if label else ""
    facts = [
        f"{prefix}n={len(nums)}, median {compact_val}, IQR [{_fmt_val(q25)}, {_fmt_val(q75)}]",
        f"Mean {_fmt_val(mean_v, unit=unit)}; range {_fmt_val(nums[0], unit=unit)} to {_fmt_val(nums[-1], unit=unit)}",
    ]
    if outliers:
        facts.append(f"{len(outliers)} outlier{'s' if len(outliers) != 1 else ''} beyond 1.5×IQR")
    alt = f"{prefix}distribution (n={len(nums)}, median {compact_val}, IQR {_fmt_val(iqr)})"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.18em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        distribution, histogram = mint.distribution, mint.histogram

        name = label or "Sample"
        if len(nums) > 60:
            panel = histogram(
                nums,
                title=f"{name} centers at median {compact_val} (n={len(nums)})",
                label=label or "Value",
                unit=unit,
                reference=reference,
            )
        else:
            panel = distribution(
                {name: nums},
                title=f"{name} centers at median {compact_val} (IQR {_fmt_val(iqr)})",
                label=label or "Value",
                unit=unit,
                reference=reference,
            )
        return mint.explain(f"{name} distribution across n={len(nums)} observations", panel, style=_mintfig_style_name(theme))

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="dist",
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
        data={"n": len(nums), "median": med, "q25": q25, "q75": q75, "mean": mean_v, "outliers": outliers},
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 4. mintchip.bar — Zero-based Tufte bullet bar
# --------------------------------------------------------------------------- #


def bar(
    value: float,
    total: float = 1.0,
    *,
    baseline: float | None = None,
    target: float | None = None,
    bands: tuple[float, float] | None = None,
    label: str | None = None,
    unit: str | None = None,
    width: int = 66,
    height: int = 14,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a zero-based Tufte bullet micro-bar for ratios, scores, or shares."""
    val = float(value)
    tot = float(total)
    if not (math.isfinite(val) and math.isfinite(tot)) or tot <= 0:
        raise ExplainError(
            "inline.bar requires finite value and positive total.",
            fix_hint="Pass e.g. mintchip.bar(0.84, total=1.0, baseline=0.75).",
        )

    theme = _resolve_theme(style, palette=palette, accent=accent)
    frac = max(0.0, min(1.0, val / tot))
    pad_x = 1.5
    inner_w = max(width - 2 * pad_x, 8.0)
    track_h = max(height - 4.0, 6.0)
    track_y = (height - track_h) / 2.0
    bar_h = max(track_h - 3.0, 4.0)
    bar_y = (height - bar_h) / 2.0

    fill_color = theme.series_colors[0]
    if target is not None and val < target:
        fill_color = theme.accent_colors[0]

    svg_parts: list[str] = [
        # Zero-based full track
        (
            f'<rect x="{pad_x:.1f}" y="{track_y:.2f}" width="{inner_w:.1f}" height="{track_h:.2f}" '
            f'fill="{theme.context_fill}" fill-opacity="0.34" rx="1.5"/>'
        ),
    ]

    # Optional qualitative bullet bands (e.g. poor / ok thresholds)
    if bands is not None:
        b1, b2 = sorted((float(bands[0]), float(bands[1])))
        w2 = max(0.0, min(1.0, b2 / tot)) * inner_w
        w1 = max(0.0, min(1.0, b1 / tot)) * inner_w
        svg_parts.append(
            f'<rect x="{pad_x:.1f}" y="{track_y:.2f}" width="{w2:.2f}" height="{track_h:.2f}" '
            f'fill="{theme.context_fill}" fill-opacity="0.32" rx="1.2"/>'
        )
        svg_parts.append(
            f'<rect x="{pad_x:.1f}" y="{track_y:.2f}" width="{w1:.2f}" height="{track_h:.2f}" '
            f'fill="{theme.context_line}" fill-opacity="0.28" rx="1.2"/>'
        )

    # Value bar + crisp zero-anchor hairline
    svg_parts.append(
        f'<rect x="{pad_x:.1f}" y="{bar_y:.2f}" width="{frac * inner_w:.2f}" height="{bar_h:.2f}" '
        f'fill="{fill_color}" rx="1.2"/>'
    )
    svg_parts.append(
        f'<line x1="{pad_x:.1f}" y1="{track_y - 0.5:.2f}" x2="{pad_x:.1f}" y2="{track_y + track_h + 0.5:.2f}" '
        f'stroke="{theme.axis}" stroke-width="0.9"/>'
    )

    if baseline is not None and math.isfinite(baseline):
        bf = max(0.0, min(1.0, baseline / tot))
        bx = pad_x + bf * inner_w
        svg_parts.append(
            f'<line x1="{bx:.2f}" y1="1.5" x2="{bx:.2f}" y2="{height - 1.5:.2f}" '
            f'stroke="{theme.muted}" stroke-width="1.2" stroke-dasharray="2,1"/>'
        )
    if target is not None and math.isfinite(target):
        tf = max(0.0, min(1.0, target / tot))
        tx = pad_x + tf * inner_w
        svg_parts.append(
            f'<line x1="{tx:.2f}" y1="1.0" x2="{tx:.2f}" y2="{height - 1.0:.2f}" '
            f'stroke="{theme.ink}" stroke-width="1.6"/>'
        )

    # Unicode 8-cell fractional block bar (strictly proportional to value/total)
    cells = 8
    filled = frac * cells
    full = math.floor(filled)
    rem = filled - full
    u_parts = ["█"] * full
    if full < cells:
        u_parts.append(_BAR_BLOCKS[min(8, round(rem * 8))])
        u_parts.extend(["░"] * (cells - full - 1))
    u_glyph = "".join(u_parts)
    a_full = round(frac * cells)
    a_glyph = "[" + ("#" * a_full) + ("." * (cells - a_full)) + "]"

    pct = frac * 100.0
    if unit == "%" or (unit is None and tot == 1.0 and 0.0 <= val <= 1.0):
        val_str = f"{pct:.1f}%" if abs(pct - round(pct)) >= 0.05 else f"{round(pct)}%"
    else:
        val_str = _fmt_val(val, unit=unit)

    prefix = f"{label}: " if label else ""
    facts = [f"{prefix}{_fmt_val(val, unit=unit)} / {_fmt_val(tot, unit=unit)} ({pct:.1f}%)"]
    if baseline is not None and math.isfinite(baseline):
        delta = val - baseline
        facts.append(f"{_fmt_val(delta, unit=unit, signed=True)} vs baseline {_fmt_val(baseline, unit=unit)}")
    if target is not None and math.isfinite(target):
        gap = val - target
        status = "meets" if val >= target else "below"
        facts.append(f"{status} target {_fmt_val(target, unit=unit)} ({_fmt_val(gap, unit=unit, signed=True)})")

    alt = f"{prefix}{val_str} ({pct:.1f}% of {_fmt_val(tot, unit=unit)})"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.16em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        compare = mint.compare

        items: dict[str, float] = {label or "Current": val}
        if baseline is not None and math.isfinite(baseline):
            items["Baseline"] = float(baseline)
        panel = compare(
            items,
            reference=target,
            title=f"{label or 'Metric'} stands at {val_str}",
            label=label or "Value",
            unit=unit,
        )
        return mint.explain(f"{prefix}{val_str} ({pct:.1f}% of capacity)", panel, style=_mintfig_style_name(theme))

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="bar",
        svg=svg,
        text=u_glyph,
        ascii_text=a_glyph,
        value_text=val_str,
        compact_value=val_str,
        alt_text=alt,
        facts=facts,
        theme=theme,
        label=label,
        unit=unit,
        data={"value": val, "total": tot, "pct": pct, "baseline": baseline, "target": target},
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# 5. mintchip.strip — Redundant-encoded status strip or micro-heatmap
# --------------------------------------------------------------------------- #


def strip(
    values: Sequence[bool | str | float | None],
    *,
    labels: Sequence[str] | None = None,
    diverging: bool = False,
    label: str | None = None,
    unit: str | None = None,
    cell_width: int = 6,
    height: int = 13,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
    expand: bool | Any = False,
) -> Chip:
    """Build a word-sized status strip (pass/fail/warn/skip) or numeric heat strip.

    Status strips encode state with both colour and shape (solid cell = pass,
    crossed accent cell = fail, half-height cell = warn, hollow outline = skip)
    so state remains unambiguous under monochrome or colour-vision deficiency.
    """
    raw = list(values)
    if not raw:
        raise ExplainError(
            "inline.strip requires at least 1 item.",
            fix_hint="Pass booleans, status strings ('pass'/'fail'/'warn'), or numeric values.",
        )

    theme = _resolve_theme(style, palette=palette, accent=accent)
    is_numeric = all(v is None or (not isinstance(v, bool) and _is_finite(v)) for v in raw) and any(
        _is_finite(v) for v in raw
    )

    gap = 1.6
    pad_x = 1.0
    cw = float(cell_width)
    ch = max(height - 3.0, 6.0)
    cy = (height - ch) / 2.0
    width = round(2 * pad_x + len(raw) * cw + max(len(raw) - 1, 0) * gap)

    svg_parts: list[str] = []
    u_chars: list[str] = []
    a_chars: list[str] = []
    facts: list[str] = []
    prefix = f"{label}: " if label else ""

    if is_numeric:
        nums = [float(v) for v in raw if _is_finite(v)]
        v_min, v_max = min(nums), max(nums)
        if diverging:
            bound = max(abs(v_min), abs(v_max), 1e-12)
            stops = (*theme.div_low, theme.div_mid, *theme.div_high)
        else:
            stops = theme.seq_stops

        for idx, v in enumerate(raw):
            x = pad_x + idx * (cw + gap)
            cell_lbl = labels[idx] if labels and idx < len(labels) else f"#{idx + 1}"
            if not _is_finite(v):
                u_chars.append("·")
                a_chars.append(".")
                tip = f"{cell_lbl}: missing"
                svg_parts.append(
                    f'<rect x="{x:.1f}" y="{cy:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
                    f'fill="none" stroke="{theme.grid}" stroke-width="0.9" rx="1.2">'
                    f"<title>{html.escape(tip)}</title></rect>"
                )
            else:
                fv = float(v)  # type: ignore[arg-type]
                if diverging:
                    t = (fv + bound) / (2.0 * bound)
                else:
                    t = 0.5 if v_max == v_min else (fv - v_min) / (v_max - v_min)
                fill = _sample_stops(stops, t)
                b_idx = max(0, min(len(_SPARK_BLOCKS) - 1, round(t * (len(_SPARK_BLOCKS) - 1))))
                u_chars.append(_SPARK_BLOCKS[b_idx])
                a_chars.append(_ASCII_SPARK[b_idx])
                tip = f"{cell_lbl}: {_fmt_val(fv, unit=unit)}"
                svg_parts.append(
                    f'<rect x="{x:.1f}" y="{cy:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
                    f'fill="{fill}" rx="1.2"><title>{html.escape(tip)}</title></rect>'
                )

        mean_v = statistics.fmean(nums)
        val_str = f"mean {_fmt_val(mean_v, unit=unit)}"
        compact_val = _fmt_val(mean_v, unit=unit)
        facts = [
            f"{prefix}{len(nums)} cells, mean {_fmt_val(mean_v, unit=unit)}, range {_fmt_val(v_min, unit=unit)} to {_fmt_val(v_max, unit=unit)}"
        ]
        alt = f"{prefix}heat strip of {len(raw)} cells ({val_str})"
    else:
        counts = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
        pass_color = theme.series_colors[2] if len(theme.series_colors) > 2 else theme.series_colors[0]
        fail_color = theme.accent_colors[0]
        warn_color = theme.series_colors[3] if len(theme.series_colors) > 3 else theme.series_colors[1]
        skip_color = theme.context_line

        for idx, v in enumerate(raw):
            x = pad_x + idx * (cw + gap)
            cell_lbl = labels[idx] if labels and idx < len(labels) else f"#{idx + 1}"
            if isinstance(v, bool):
                state = "pass" if v else "fail"
            elif v is None:
                state = "skip"
            else:
                tok = str(v).strip().lower()
                if tok in _PASS_TOKENS:
                    state = "pass"
                elif tok in _FAIL_TOKENS:
                    state = "fail"
                elif tok in _WARN_TOKENS:
                    state = "warn"
                elif tok in _SKIP_TOKENS:
                    state = "skip"
                else:
                    state = "warn"
            counts[state] += 1
            tip = html.escape(f"{cell_lbl}: {state}")
            if state == "pass":
                ug, ag = "■", "+"
                svg_parts.append(
                    f'<rect x="{x:.1f}" y="{cy:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
                    f'fill="{pass_color}" rx="1.2"><title>{tip}</title></rect>'
                )
            elif state == "fail":
                ug, ag = "×", "x"
                # Redundant shape encoding: filled accent cell + crisp white cross
                svg_parts.append(
                    f'<g><title>{tip}</title>'
                    f'<rect x="{x:.1f}" y="{cy:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
                    f'fill="{fail_color}" rx="1.2"/>'
                    f'<path d="M{x + 1.4:.1f},{cy + 2.0:.1f} L{x + cw - 1.4:.1f},{cy + ch - 2.0:.1f} '
                    f'M{x + cw - 1.4:.1f},{cy + 2.0:.1f} L{x + 1.4:.1f},{cy + ch - 2.0:.1f}" '
                    f'stroke="{theme.background}" stroke-width="1.05" stroke-linecap="round"/></g>'
                )
            elif state == "warn":
                ug, ag = "▄", "!"
                # Redundant shape encoding: lower half-height bar inside subtle outline
                wh = ch * 0.56
                svg_parts.append(
                    f'<g><title>{tip}</title>'
                    f'<rect x="{x:.1f}" y="{cy:.1f}" width="{cw:.1f}" height="{ch:.1f}" '
                    f'fill="{warn_color}" fill-opacity="0.22" rx="1.2"/>'
                    f'<rect x="{x:.1f}" y="{cy + ch - wh:.1f}" width="{cw:.1f}" height="{wh:.1f}" '
                    f'fill="{warn_color}" rx="1.0"/></g>'
                )
            else:
                ug, ag = "□", "."
                svg_parts.append(
                    f'<rect x="{x + 0.4:.1f}" y="{cy + 0.4:.1f}" width="{cw - 0.8:.1f}" '
                    f'height="{ch - 0.8:.1f}" fill="none" stroke="{skip_color}" '
                    f'stroke-width="0.9" rx="1.0"><title>{tip}</title></rect>'
                )
            u_chars.append(ug)
            a_chars.append(ag)

        total_active = len(raw) - counts["skip"]
        val_str = f"{counts['pass']}/{total_active} pass" if total_active > 0 else f"0/{len(raw)}"
        compact_val = val_str
        summary_bits = [f"{k}={v}" for k, v in counts.items() if v > 0]
        facts = [f"{prefix}{val_str} ({', '.join(summary_bits)})"]
        if counts["fail"] > 0 and labels:
            failed_names = [
                labels[i]
                for i, v in enumerate(raw)
                if i < len(labels)
                and (
                    (isinstance(v, bool) and not v)
                    or (isinstance(v, str) and v.strip().lower() in _FAIL_TOKENS)
                )
            ]
            if failed_names:
                facts.append(f"Failed: {', '.join(failed_names)}")
        alt = f"{prefix}status strip: {val_str}"

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(alt, quote=True)}" '
        f'style="display:inline-block;vertical-align:-0.16em;overflow:visible;">'
        f"<title>{html.escape(alt)}</title>{''.join(svg_parts)}</svg>"
    )

    def _auto_expand() -> Any:
        mint = _require_mintfig()
        compare = mint.compare

        if is_numeric:
            items = {
                (labels[i] if labels and i < len(labels) else f"Item {i + 1}"): float(v)
                for i, v in enumerate(raw)
                if _is_finite(v)
            }
            panel = compare(
                items,
                title=f"{label or 'Cells'} ({val_str})",
                label=label or "Value",
                unit=unit,
            )
        else:
            panel = compare(
                {k: v for k, v in counts.items() if v > 0},
                title=f"{label or 'Status'}: {val_str}",
                label="Count",
            )
        return mint.explain(f"{prefix}{val_str}", panel, style=_mintfig_style_name(theme))

    exp_obj = _resolve_expand_explanation(expand, _auto_expand)
    return Chip(
        kind="strip",
        svg=svg,
        text="".join(u_chars),
        ascii_text="".join(a_chars),
        value_text=val_str,
        compact_value=compact_val,
        alt_text=alt,
        facts=facts,
        theme=theme,
        label=label,
        unit=unit,
        data={"values": raw, "numeric": is_numeric},
        expand_explanation=exp_obj,
    )


# --------------------------------------------------------------------------- #
# Prose interpolation & interactive HTML evidence-chip document
# --------------------------------------------------------------------------- #


def format_prose(
    template: str,
    *,
    mode: str = "html",
    show_value: bool = True,
    show_label: bool = False,
    compact: bool = False,
    ascii_only: bool = False,
    **chips: Chip,
) -> str:
    """Interpolate ``{name}`` placeholders in prose with HTML chips or Unicode glyphs.

    In ``mode="html"``, literal prose text is HTML-escaped while embedded
    :class:`InlineGraphic` placeholders render as live interactive chips.
    Pass ``compact=True`` for sleeker mid-sentence numerical readouts (e.g.
    ``+0.08 [··│··─●──··]`` instead of repeating the full bracketed interval).
    """
    if mode not in {"html", "text", "markdown"}:
        raise ExplainError(
            f"Unknown mode {mode!r}.",
            fix_hint='Use mode="html", mode="text", or mode="markdown".',
        )

    tokens = re.split(r"(\{[a-zA-Z_][a-zA-Z0-9_]*\})", template)
    out: list[str] = []
    for tok in tokens:
        if len(tok) >= 3 and tok.startswith("{") and tok.endswith("}"):
            key = tok[1:-1]
            if key in chips:
                g = chips[key]
                if mode == "html":
                    out.append(g.html(show_value=show_value, show_label=show_label, compact=compact))
                elif mode == "markdown":
                    out.append(g.markdown(compact=compact))
                else:
                    out.append(g.to_text(ascii_only=ascii_only, include_value=show_value, compact=compact))
                continue
        out.append(html.escape(tok) if mode == "html" else tok)
    return "".join(out)


_POPOVER_JS = r"""
(function() {
  if (window.__mintfigInlineInit) return;
  window.__mintfigInlineInit = true;

  var backdrop = document.createElement('div');
  backdrop.className = 'mf-modal-backdrop';
  backdrop.hidden = true;
  backdrop.innerHTML =
    '<div class="mf-modal" role="dialog" aria-modal="true">' +
      '<div class="mf-modal-head">' +
        '<div class="mf-modal-title-wrap">' +
          '<span class="mf-modal-badge"></span>' +
          '<strong class="mf-modal-title"></strong>' +
        '</div>' +
        '<button type="button" class="mf-modal-close" aria-label="Close">×</button>' +
      '</div>' +
      '<div class="mf-modal-body">' +
        '<ul class="mf-modal-facts"></ul>' +
        '<div class="mf-modal-warn" hidden></div>' +
        '<div class="mf-modal-fig" hidden></div>' +
      '</div>' +
    '</div>';
  document.body.appendChild(backdrop);

  var badgeEl = backdrop.querySelector('.mf-modal-badge');
  var titleEl = backdrop.querySelector('.mf-modal-title');
  var factsEl = backdrop.querySelector('.mf-modal-facts');
  var warnEl = backdrop.querySelector('.mf-modal-warn');
  var figEl = backdrop.querySelector('.mf-modal-fig');
  var closeBtn = backdrop.querySelector('.mf-modal-close');

  function closeModal() { backdrop.hidden = true; }
  closeBtn.addEventListener('click', closeModal);
  backdrop.addEventListener('click', function(e) {
    if (e.target === backdrop) closeModal();
  });
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && !backdrop.hidden) closeModal();
  });

  document.addEventListener('click', function(e) {
    var btn = e.target.closest && e.target.closest('button.mf-chip-interactive');
    if (!btn) return;
    var raw = btn.getAttribute('data-mf-chip');
    if (!raw) return;
    var data;
    try { data = JSON.parse(raw); } catch (_) { return; }

    badgeEl.textContent = (data.kind || 'inline').toUpperCase();
    titleEl.textContent = data.figure_title || (data.label ? (data.label + ' — ' + data.value) : data.value);

    factsEl.innerHTML = '';
    (data.facts || []).forEach(function(f) {
      var li = document.createElement('li');
      li.textContent = f;
      factsEl.appendChild(li);
    });

    if (data.warnings && data.warnings.length) {
      warnEl.hidden = false;
      warnEl.textContent = data.warnings.join(' ');
    } else {
      warnEl.hidden = true;
      warnEl.textContent = '';
    }

    if (data.has_figure && data.figure_svg) {
      figEl.hidden = false;
      figEl.innerHTML = data.figure_svg;
    } else {
      figEl.hidden = true;
      figEl.innerHTML = '';
    }

    backdrop.hidden = false;
  });
})();
"""


def _popover_css(theme: Theme) -> str:
    is_dark = relative_luminance(theme.background) < 0.35
    card_bg = "#1E2228" if is_dark else "#FFFFFF"
    soft_bg = "rgba(255,255,255,0.06)" if is_dark else "#F6F8FA"
    return f"""
.mf-chip-interactive:hover {{
  border-color: {theme.series_colors[0]} !important;
  background: {soft_bg} !important;
}}
.mf-modal-backdrop {{
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(15, 18, 22, 0.52);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}}
.mf-modal-backdrop[hidden] {{ display: none; }}
.mf-modal {{
  width: min(760px, 95vw); max-height: 90vh; overflow: auto;
  background: {card_bg}; color: {theme.ink};
  border: 1px solid {theme.grid}; border-radius: 10px;
  box-shadow: 0 20px 50px rgba(0,0,0,0.28);
  font-family: ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
}}
.mf-modal-head {{
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid {theme.grid}; gap: 12px;
}}
.mf-modal-title-wrap {{ display: flex; align-items: center; gap: 8px; min-width: 0; }}
.mf-modal-badge {{
  font-size: 10px; font-weight: 700; letter-spacing: 0.06em;
  padding: 2px 6px; border-radius: 4px;
  background: {theme.series_colors[0]}; color: #FFFFFF; flex-shrink: 0;
}}
.mf-modal-title {{ font-size: 14px; line-height: 1.3; }}
.mf-modal-close {{
  background: transparent; border: none; color: {theme.muted};
  font-size: 22px; line-height: 1; cursor: pointer; padding: 2px 6px;
}}
.mf-modal-close:hover {{ color: {theme.ink}; }}
.mf-modal-body {{ padding: 14px 16px 18px; }}
.mf-modal-facts {{
  margin: 0 0 12px; padding-left: 18px; font-size: 13px;
  line-height: 1.5; color: {theme.ink};
}}
.mf-modal-warn {{
  margin: 0 0 12px; padding: 8px 10px; border-radius: 6px; font-size: 12px;
  background: rgba(205, 67, 36, 0.10); color: {theme.accent_colors[0]};
  border: 1px solid rgba(205, 67, 36, 0.28);
}}
.mf-modal-fig {{
  margin-top: 8px; padding: 8px; border-radius: 8px;
  border: 1px solid {theme.grid}; background: {theme.background};
}}
"""


def _wrap_standalone_snippet(snippet_html: str, theme: Theme) -> str:
    return f"<style>{_popover_css(theme)}</style>{snippet_html}<script>{_POPOVER_JS}</script>"


def document(
    title: str,
    blocks: Sequence[str],
    *,
    subtitle: str | None = None,
    source: str | None = None,
    style: str | Theme = "default",
    palette: str | None = None,
    accent: str | None = None,
) -> str:
    """Compose a self-contained HTML research note with clickable inline evidence chips."""
    theme = _resolve_theme(style, palette=palette, accent=accent)
    is_dark = relative_luminance(theme.background) < 0.35
    page_bg = "#12151A" if is_dark else "#F7F8FA"
    card_bg = theme.background
    body_html = "\n".join(
        b if b.lstrip().startswith("<") else f"<p>{b}</p>"
        for b in blocks
    )
    sub_html = f'<p class="mf-doc-sub">{html.escape(subtitle)}</p>' if subtitle else ""
    src_html = f'<footer class="mf-doc-src">Source: {html.escape(source)}</footer>' if source else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
  :root {{ color-scheme: {'dark' if is_dark else 'light'}; }}
  body {{
    margin: 0; padding: 32px 16px;
    background: {page_bg}; color: {theme.ink};
    font-family: ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
    line-height: 1.72; font-size: 15px;
  }}
  .mf-doc {{
    max-width: 780px; margin: 0 auto;
    background: {card_bg}; border: 1px solid {theme.grid};
    border-radius: 12px; padding: 28px 34px;
    box-shadow: 0 4px 20px rgba(0,0,0,{'0.32' if is_dark else '0.05'});
  }}
  .mf-doc h1 {{
    margin: 0 0 6px; font-size: 21px; line-height: 1.3; letter-spacing: -0.01em;
  }}
  .mf-doc-sub {{
    margin: 0 0 20px; color: {theme.muted}; font-size: 13.5px;
  }}
  .mf-doc p {{ margin: 0 0 14px; }}
  .mf-doc h2 {{
    margin: 22px 0 10px; font-size: 14px; text-transform: uppercase;
    letter-spacing: 0.06em; color: {theme.muted};
  }}
  .mf-doc table {{
    width: 100%; border-collapse: collapse; margin: 14px 0 18px; font-size: 13.5px;
  }}
  .mf-doc th {{
    text-align: left; font-weight: 600; color: {theme.muted};
    border-bottom: 1.5px solid {theme.ink}; padding: 7px 8px;
  }}
  .mf-doc td {{
    border-bottom: 1px solid {theme.grid}; padding: 8px 8px; vertical-align: middle;
  }}
  .mf-doc-src {{
    margin-top: 22px; padding-top: 12px; border-top: 1px solid {theme.grid};
    font-size: 12px; color: {theme.muted};
  }}
  {_popover_css(theme)}
</style>
</head>
<body>
<article class="mf-doc">
  <h1>{html.escape(title)}</h1>
  {sub_html}
  {body_html}
  {src_html}
</article>
<script>{_POPOVER_JS}</script>
</body>
</html>
"""


InlineGraphic = Chip
