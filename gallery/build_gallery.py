"""Deterministic gallery generator for ``mintchip``.

Generates:
- ``gallery/output/hero_banner.svg`` — Editorial README hero card with live SVG chips + Unicode strip.
- ``gallery/output/themes_overview.svg`` — All 6 themes & 6 CVD-safe palettes side-by-side.
- ``gallery/output/chips/<name>.svg`` & ``<name>_dark.svg`` — Individual pill-card SVGs for all 17 chips.
- ``gallery/output/index.html`` — Zero-dependency interactive HTML visual gallery & Keep/Refine/Drop workbench.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import mintchip as mc

OUT_DIR = Path(__file__).parent / "output"
CHIPS_DIR = OUT_DIR / "chips"


def _strip_svg_wrapper(svg: str) -> tuple[float, float, str]:
    """Return ``(width, height, inner_markup)`` from a chip SVG string."""
    w_m = re.search(r'\bwidth="([\d.]+)"', svg)
    h_m = re.search(r'\bheight="([\d.]+)"', svg)
    w = float(w_m.group(1)) if w_m else 70.0
    h = float(h_m.group(1)) if h_m else 16.0
    inner = re.sub(r"^<svg\b[^>]*>", "", svg.strip(), count=1)
    inner = re.sub(r"</svg>\s*$", "", inner, count=1)
    inner = re.sub(r"<title>.*?</title>", "", inner, count=1, flags=re.DOTALL)
    return w, h, inner


def _chip_pill_svg(chip: mc.Chip, *, compact: bool = True) -> str:
    """Wrap a chip's value + micro-SVG into a crisp standalone pill SVG for Markdown tables."""
    t = chip.theme
    is_dark = mc.relative_luminance(t.background) < 0.35
    val = (chip.compact_value or chip.value_text) if compact else chip.value_text
    svg_w, svg_h, inner = _strip_svg_wrapper(chip.svg)

    pad_x = 8.0
    gap = 6.0
    # Approximate tabular character width for 11.5px sans-serif bold
    text_w = max(len(val) * 6.5, 18.0) if val else 0.0
    total_w = round(pad_x + (text_w + gap if val else 0.0) + svg_w + pad_x)
    total_h = 26
    pill_bg = "#1E242E" if is_dark else "#F6F8FA"
    pill_border = t.grid

    svg_x = pad_x + (text_w + gap if val else 0.0)
    svg_y = (total_h - svg_h) / 2.0

    val_el = (
        f'<text x="{pad_x:.1f}" y="16.8" fill="{t.ink}" '
        f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="11.5" font-weight="600">{html.escape(val)}</text>'
        if val
        else ""
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{total_h}" '
        f'viewBox="0 0 {total_w} {total_h}" role="img" aria-label="{html.escape(chip.alt_text, quote=True)}">'
        f"<title>{html.escape(chip.alt_text)}</title>"
        f'<rect x="0.5" y="0.5" width="{total_w - 1}" height="{total_h - 1}" rx="6" '
        f'fill="{pill_bg}" stroke="{pill_border}" stroke-width="1"/>'
        f"{val_el}"
        f'<g transform="translate({svg_x:.1f},{svg_y:.1f})">{inner}</g>'
        f"</svg>"
    )


def _demo_specs(style: str = "default", palette: str | None = None) -> list[dict[str, Any]]:
    ci_dom = mc.shared_domain((0.05, 0.11), (-0.024, 0.048), (-0.08, -0.02), reference=0.0)
    delta_dom = mc.shared_domain(0.65, 0.88)
    samples_q = [
        14.2, 16.0, 17.5, 18.1, 18.9, 19.3, 19.8, 20.1, 20.6, 21.0,
        21.4, 21.9, 22.3, 22.8, 23.4, 24.1, 24.8, 26.2, 28.5, 31.4,
    ]
    xs = [1.0, 1.8, 2.5, 3.3, 4.1, 4.9, 5.8, 6.6, 7.5, 8.4, 9.2, 10.0]
    ys = [1.8, 2.9, 2.3, 4.6, 3.8, 5.9, 5.2, 7.6, 6.7, 8.9, 8.2, 9.8]
    kw: dict[str, Any] = {"style": style, "palette": palette}

    catalog_q = {c["name"]: c["question"] for c in mc.CATALOG}
    rows = [
        ("spark", "core",
         mc.spark([1.84, 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43, 0.42],
                  label="Val loss", band=(0.38, 0.48), reference=0.45, **kw),
         "Training settled inside the target band at {c}.",
         'mc.spark([1.84, 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43, 0.42], band=(0.38, 0.48), reference=0.45)'),
        ("ci", "core",
         mc.ci(0.08, (0.05, 0.11), inner_error=(0.07, 0.09),
               error_label="95% CI, 5 seeds", reference=0.0, domain=ci_dom,
               label="Retrieval lift", **kw),
         "Retrieval delivers a reliable {c} gain over baseline.",
         'mc.ci(0.08, (0.05, 0.11), inner_error=(0.07, 0.09), error_label="95% CI, 5 seeds", reference=0.0)'),
        ("dist", "core",
         mc.dist([18.2, 19.1, 19.4, 19.8, 20.0, 20.3, 20.6, 21.1, 21.4, 22.0, 47.8],
                 label="Shard p95", unit="ms", reference=25.0, **kw),
         "Shard latency clusters tightly at {c} except one cold-cache outlier.",
         'mc.dist([18.2, 19.1, 19.4, 19.8, 20.0, 20.3, 20.6, 21.1, 21.4, 22.0, 47.8], unit="ms", reference=25.0)'),
        ("bar", "core",
         mc.bar(0.82, total=1.0, baseline=0.74, target=0.80, bands=(0.60, 0.80),
                label="Accuracy", **kw),
         "Pass@1 climbed to {c}, clearing both baseline and target.",
         "mc.bar(0.82, total=1.0, baseline=0.74, target=0.80, bands=(0.60, 0.80))"),
        ("strip", "core",
         mc.strip([True, True, True, "warn", True, False, True, "skip"],
                  labels=[f"seed_{i}" for i in range(8)], label="Repro seeds", **kw),
         "Reproducibility checks show {c} across 8 evaluation seeds.",
         'mc.strip([True, True, True, "warn", True, False, True, "skip"])'),

        ("delta", "change",
         mc.delta(0.74, 0.82, label="Accuracy", domain=delta_dom, **kw),
         "Adding retrieval shifted accuracy {c} across held-out tasks.",
         "mc.delta(0.74, 0.82, domain=(0.65, 0.88))"),
        ("waterfall", "change",
         mc.waterfall({"Fine-tuning": 0.13, "Retrieval": 0.08, "Int4 quant": -0.02},
                      start=0.63, label="Ablation bridge", **kw),
         "Net lift breaks down cleanly as {c} from base checkpoint.",
         'mc.waterfall({"Fine-tuning": 0.13, "Retrieval": 0.08, "Int4 quant": -0.02}, start=0.63)'),
        ("scatter", "change",
         mc.scatter(xs, ys, highlight=9, names=[f"m{i}" for i in range(12)],
                    fit=True, label="Scaling law", x_label="Compute", y_label="Score", **kw),
         "Log-compute and benchmark score track closely at {c}.",
         "mc.scatter(compute, score, highlight=9, fit=True)"),

        ("share", "composition",
         mc.share({"Weights": 62, "KV cache": 28, "Activations": 10},
                  label="GPU memory", unit="GB", **kw),
         "VRAM footprint splits {c} across weights, KV cache, and activations.",
         'mc.share({"Weights": 62, "KV cache": 28, "Activations": 10}, unit="GB")'),
        ("funnel", "composition",
         mc.funnel({"Screened": 1200, "Eligible": 520, "Enrolled": 350, "Completed": 290},
                   label="Cohort", **kw),
         "Clinical cohort attrition shows {c}, with the steepest drop at eligibility.",
         'mc.funnel({"Screened": 1200, "Eligible": 520, "Enrolled": 350, "Completed": 290})'),
        ("ratio", "composition",
         mc.ratio(3, 10, label="Responder rate", **kw),
         "Treatment response occurred in {c} patients in the phase-II arm.",
         "mc.ratio(3, 10)"),

        ("gauge", "evidence",
         mc.gauge(7.38, (7.35, 7.45), warn=(7.30, 7.50), label="Blood pH", **kw),
         "Arterial pH remained centered inside the physiological window at {c}.",
         "mc.gauge(7.38, normal=(7.35, 7.45), warn=(7.30, 7.50))"),
        ("quantiles", "evidence",
         mc.quantiles(samples_q, threshold=25.0, n_dots=10, unit="ms",
                      label="Tail forecast", **kw),
         "Posterior predictive latency puts SLA breach risk at {c}.",
         'mc.quantiles(samples, threshold=25.0, n_dots=10, unit="ms")'),
        ("evidence", "evidence",
         mc.evidence(p=0.002, n=48, label="Drug vs placebo", **kw),
         "Primary endpoint support rates {c} across all 48 paired subjects.",
         "mc.evidence(p=0.002, n=48)"),

        ("timeline", "structure",
         mc.timeline({"fetch": 1.2, "solve": 4.8, "verify": 1.5}, unit="s",
                     label="Agent turn", **kw),
         "Turn wall-clock spent {c}, dominated by the solver phase.",
         'mc.timeline({"fetch": 1.2, "solve": 4.8, "verify": 1.5}, unit="s")'),
        ("rank", "structure",
         mc.rank(2, 18, label="MMLU-Pro", **kw),
         "Our candidate places {c} among 18 frontier models.",
         "mc.rank(2, 18)"),
        ("dual_spark", "structure",
         mc.dual_spark([1.40, 1.05, 0.80, 0.62, 0.51, 0.45, 0.42],
                       [1.42, 1.10, 0.88, 0.74, 0.66, 0.62, 0.61],
                       labels=("train", "val"), label="Loss gap", **kw),
         "Train vs. validation trajectories diverge late to {c}, signaling mild overfitting.",
         'mc.dual_spark(train_loss, val_loss, labels=("train", "val"))'),
    ]
    return [
        {
            "name": name,
            "family": family,
            "question": catalog_q[name],
            "chip": chip,
            "sentence": sentence,
            "code": code,
        }
        for name, family, chip, sentence, code in rows
    ]


def _render_hero_banner_svg() -> str:
    """Build a retina-crisp README hero SVG showing live chips in prose + Unicode parity."""
    specs = {r["name"]: r["chip"] for r in _demo_specs("default")}
    ci_dom = mc.shared_domain((0.05, 0.11), (-0.024, 0.048), (-0.08, -0.02), reference=0.0)
    null_ci = mc.ci(0.012, (-0.024, 0.048), error_label="95% CI, 5 seeds", reference=0.0, domain=ci_dom)
    specs["null_ci"] = null_ci

    w, h = 860, 326
    sans = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
    mono = "ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace"

    def _embed_pill(x: float, y: float, chip: mc.Chip, compact_label: str | None = None) -> tuple[float, str]:
        val = compact_label if compact_label is not None else (chip.compact_value or chip.value_text)
        sw, sh, inner = _strip_svg_wrapper(chip.svg)
        pad_x = 6.5
        gap = 5.5
        tw = max(len(val) * 6.5, 16.0)
        pw = pad_x + tw + gap + sw + pad_x
        ph = 23.0
        sx = x + pad_x + tw + gap
        sy = y + (ph - sh) / 2.0
        markup = (
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{pw:.1f}" height="{ph:.1f}" rx="5.5" '
            f'fill="#F6F8FA" stroke="#DCE2E8" stroke-width="1"/>'
            f'<text x="{x + pad_x:.1f}" y="{y + 15.4:.1f}" fill="#1A1D21" '
            f'font-family="{sans}" font-size="11.5" font-weight="600">{html.escape(val)}</text>'
            f'<g transform="translate({sx:.1f},{sy:.1f})">{inner}</g>'
        )
        return pw, markup

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect x="0.5" y="0.5" width="859" height="325" rx="12" fill="#FFFFFF" stroke="#E3E7EC" stroke-width="1"/>',
        # Top editorial rule & header
        '<rect x="0" y="0" width="860" height="4" rx="2" fill="#1F5A9D"/>',
        f'<text x="28" y="34" fill="#1A1D21" font-family="{sans}" font-size="15.5" font-weight="700">mintchip</text>',
        f'<text x="104" y="34" fill="#5B6570" font-family="{sans}" font-size="13">Word-sized visual chips for AI agents, scientists, and prose</text>',
        '<rect x="708" y="18" width="124" height="22" rx="11" fill="#EEF4FB" stroke="#C9DBEF" stroke-width="1"/>',
        f'<text x="770" y="32.5" text-anchor="middle" fill="#1F5A9D" font-family="{sans}" font-size="11" font-weight="600">0 dependencies · SVG + Text</text>',
        '<line x1="28" y1="49" x2="832" y2="49" stroke="#E3E7EC" stroke-width="1"/>',
    ]

    # Row 1: ML ablation prose with live SVG chips
    y1 = 76.0
    parts.append(f'<text x="28" y="{y1}" fill="#1A1D21" font-family="{sans}" font-size="13.5">Training settled into the target band at</text>')
    pw, m = _embed_pill(278, y1 - 16, specs["spark"], "0.42")
    parts.append(m)
    x_next = 278 + pw + 7
    parts.append(f'<text x="{x_next:.1f}" y="{y1}" fill="#1A1D21" font-family="{sans}" font-size="13.5">, lifting accuracy to</text>')
    pw2, m2 = _embed_pill(x_next + 123, y1 - 16, specs["bar"], "82%")
    parts.append(m2)
    x_next2 = x_next + 123 + pw2 + 7
    parts.append(f'<text x="{x_next2:.1f}" y="{y1}" fill="#1A1D21" font-family="{sans}" font-size="13.5">via</text>')
    _, m3 = _embed_pill(x_next2 + 25, y1 - 16, specs["waterfall"], "+0.19")
    parts.append(m3)

    # Row 2: CIs & scatter
    y2 = 110.0
    parts.append(f'<text x="28" y="{y2}" fill="#1A1D21" font-family="{sans}" font-size="13.5">Retrieval delivers a clear</text>')
    pw, m = _embed_pill(184, y2 - 16, specs["ci"], "+0.08")
    parts.append(m)
    x2 = 184 + pw + 7
    parts.append(f'<text x="{x2:.1f}" y="{y2}" fill="#1A1D21" font-family="{sans}" font-size="13.5">lift, warmup</text>')
    pw2, m2 = _embed_pill(x2 + 80, y2 - 16, specs["null_ci"], "+0.012")
    parts.append(m2)
    x3 = x2 + 80 + pw2 + 7
    parts.append(f'<text x="{x3:.1f}" y="{y2}" fill="#1A1D21" font-family="{sans}" font-size="13.5">crosses null, and scaling tracks</text>')
    _, m3 = _embed_pill(x3 + 195, y2 - 16, specs["scatter"], "r=0.96")
    parts.append(m3)

    # Row 3: Latency, seeds, clinical & quantile
    y3 = 144.0
    parts.append(f'<text x="28" y="{y3}" fill="#1A1D21" font-family="{sans}" font-size="13.5">Shard latency sits at</text>')
    pw, m = _embed_pill(157, y3 - 16, specs["dist"], "20.3 ms")
    parts.append(m)
    x2 = 157 + pw + 7
    parts.append(f'<text x="{x2:.1f}" y="{y3}" fill="#1A1D21" font-family="{sans}" font-size="13.5">, repro seeds</text>')
    pw2, m2 = _embed_pill(x2 + 85, y3 - 16, specs["strip"], "5/7 pass")
    parts.append(m2)
    x3 = x2 + 85 + pw2 + 7
    parts.append(f'<text x="{x3:.1f}" y="{y3}" fill="#1A1D21" font-family="{sans}" font-size="13.5">, and SLA risk</text>')
    _, m3 = _embed_pill(x3 + 91, y3 - 16, specs["quantiles"], "P>25 15%")
    parts.append(m3)

    # Row 4: Clinical / Systems chips
    y4 = 178.0
    parts.append(f'<text x="28" y="{y4}" fill="#1A1D21" font-family="{sans}" font-size="13.5">Cohort retained</text>')
    pw, m = _embed_pill(130, y4 - 16, specs["funnel"], "24%")
    parts.append(m)
    x2 = 130 + pw + 7
    parts.append(f'<text x="{x2:.1f}" y="{y4}" fill="#1A1D21" font-family="{sans}" font-size="13.5">with</text>')
    pw2, m2 = _embed_pill(x2 + 32, y4 - 16, specs["ratio"], "3/10")
    parts.append(m2)
    x3 = x2 + 32 + pw2 + 7
    parts.append(f'<text x="{x3:.1f}" y="{y4}" fill="#1A1D21" font-family="{sans}" font-size="13.5">responders, pH</text>')
    pw3, m3 = _embed_pill(x3 + 98, y4 - 16, specs["gauge"], "7.38")
    parts.append(m3)
    x4 = x3 + 98 + pw3 + 7
    parts.append(f'<text x="{x4:.1f}" y="{y4}" fill="#1A1D21" font-family="{sans}" font-size="13.5">, evidence</text>')
    _, m4 = _embed_pill(x4 + 66, y4 - 16, specs["evidence"], "strong")
    parts.append(m4)

    # Bottom dark terminal card showing exact mode="text" Unicode parity
    parts.append('<rect x="24" y="204" width="812" height="102" rx="8" fill="#14181F" stroke="#272E3B" stroke-width="1"/>')
    parts.append(
        f'<text x="40" y="225" fill="#9AA5B4" font-family="{sans}" font-size="10.5" font-weight="600" letter-spacing="0.06em">'
        f'SAME CHIPS IN TERMINAL / MARKDOWN (mode="text")</text>'
    )
    line_a = (
        f'loss {specs["spark"].to_text(compact=True)}   ·   '
        f'acc {specs["bar"].to_text(compact=True)}   ·   '
        f'lift {specs["ci"].to_text(compact=True)}   ·   '
        f'null {specs["null_ci"].to_text(compact=True)}'
    )
    line_b = (
        f'scale {specs["scatter"].to_text(compact=True)}   ·   '
        f'p95 {specs["dist"].to_text(compact=True)}   ·   '
        f'seeds {specs["strip"].to_text(compact=True)}   ·   '
        f'pH {specs["gauge"].to_text(compact=True)}'
    )
    line_c = (
        f'cohort {specs["funnel"].to_text(compact=True)}   ·   '
        f'resp {specs["ratio"].to_text(compact=True)}   ·   '
        f'risk {specs["quantiles"].to_text(compact=True)}   ·   '
        f'evid {specs["evidence"].to_text(compact=True)}'
    )
    parts.append(f'<text x="40" y="249" fill="#ECEFF4" font-family="{mono}" font-size="11.5">{html.escape(line_a)}</text>')
    parts.append(f'<text x="40" y="271" fill="#4BD9BA" font-family="{mono}" font-size="11.5">{html.escape(line_b)}</text>')
    parts.append(f'<text x="40" y="293" fill="#8CC4F8" font-family="{mono}" font-size="11.5">{html.escape(line_c)}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def _render_themes_overview_svg() -> str:
    """Render all 6 surface themes and 6 palettes side-by-side with live chips."""
    sans = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
    w, h = 860, 316
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        '<rect x="0.5" y="0.5" width="859" height="315" rx="10" fill="#FFFFFF" stroke="#E3E7EC" stroke-width="1"/>',
        f'<text x="24" y="28" fill="#1A1D21" font-family="{sans}" font-size="13.5" font-weight="700">Surface Themes (style=)</text>',
        f'<text x="448" y="28" fill="#1A1D21" font-family="{sans}" font-size="13.5" font-weight="700">CVD-Safe Palettes (palette=)</text>',
    ]

    theme_names = list(mc.THEMES)
    for idx, tname in enumerate(theme_names):
        y = 42 + idx * 43
        t = mc.get_theme(tname)
        sp = mc.spark([1.8, 1.2, 0.9, 0.7, 0.5, 0.42], band=(0.38, 0.52), style=tname)
        ci_c = mc.ci(0.08, (0.04, 0.12), error_label="95% CI", domain=(-0.05, 0.16), style=tname)
        sh = mc.share({"a": 55, "b": 30, "c": 15}, style=tname)
        st = mc.strip([True, True, "warn", False, True], style=tname)

        parts.append(
            f'<rect x="24" y="{y}" width="398" height="35" rx="6" fill="{t.background}" stroke="{t.grid}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="36" y="{y + 21.5}" fill="{t.ink}" font-family="{sans}" font-size="11.5" font-weight="600">{tname}</text>'
        )
        cx = 108.0
        for chip in (sp, ci_c, sh, st):
            sw, sh_h, inner = _strip_svg_wrapper(chip.svg)
            parts.append(f'<g transform="translate({cx:.1f},{y + (35 - sh_h) / 2:.1f})">{inner}</g>')
            cx += sw + 10.0

    pal_names = list(mc.PALETTES)
    for idx, pname in enumerate(pal_names):
        y = 42 + idx * 43
        t = mc.apply_palette(mc.get_theme("default"), pname)
        sh = mc.share({"a": 40, "b": 30, "c": 20, "d": 10}, palette=pname)
        ht = mc.strip([-0.9, -0.4, 0.0, 0.5, 0.95], diverging=True, palette=pname)
        sp = mc.dual_spark([1.2, 0.9, 0.7, 0.5, 0.4], [1.25, 1.0, 0.85, 0.72, 0.65], palette=pname)

        parts.append(
            f'<rect x="448" y="{y}" width="388" height="35" rx="6" fill="#FAFBFD" stroke="#E3E7EC" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="460" y="{y + 21.5}" fill="#1A1D21" font-family="{sans}" font-size="11.5" font-weight="600">{pname}</text>'
        )
        # 4 palette swatches
        for s_i, col in enumerate(t.series_colors[:4]):
            parts.append(
                f'<rect x="{536 + s_i * 15}" y="{y + 11}" width="11" height="13" rx="2.5" fill="{col}"/>'
            )
        cx = 610.0
        for chip in (sh, ht, sp):
            sw, sh_h, inner = _strip_svg_wrapper(chip.svg)
            parts.append(f'<g transform="translate({cx:.1f},{y + (35 - sh_h) / 2:.1f})">{inner}</g>')
            cx += sw + 10.0

    parts.append("</svg>")
    return "\n".join(parts)


def _render_interactive_gallery_html() -> str:
    """Build a self-contained zero-CDN interactive gallery & Keep/Refine/Drop workbench."""
    all_themes = list(mc.THEMES)
    all_palettes = list(mc.PALETTES)

    # Pre-render every component across all 6 themes so switching themes is instant & exact
    by_theme: dict[str, dict[str, str]] = {}
    for tname in all_themes:
        by_theme[tname] = {r["name"]: r["chip"].svg for r in _demo_specs(style=tname)}

    base_specs = _demo_specs("default")
    items_json = [
        {
            "name": r["name"],
            "family": r["family"],
            "question": r["question"],
            "label": r["chip"].label or r["name"],
            "value": r["chip"].value_text,
            "compact": r["chip"].compact_value or r["chip"].value_text,
            "text": r["chip"].to_text(compact=False),
            "text_compact": r["chip"].to_text(compact=True),
            "ascii": r["chip"].to_text(ascii_only=True),
            "facts": r["chip"].facts,
            "sentence": r["sentence"],
            "code": r["code"],
            "svgs": {tname: by_theme[tname][r["name"]] for tname in all_themes},
        }
        for r in base_specs
    ]
    theme_meta = {
        tname: {
            "bg": mc.get_theme(tname).background,
            "ink": mc.get_theme(tname).ink,
            "muted": mc.get_theme(tname).muted,
            "grid": mc.get_theme(tname).grid,
            "primary": mc.get_theme(tname).series_colors[0],
            "accent": mc.get_theme(tname).accent_colors[0],
            "is_dark": mc.relative_luminance(mc.get_theme(tname).background) < 0.35,
        }
        for tname in all_themes
    }
    payload_str = json.dumps({"items": items_json, "themes": theme_meta, "palettes": all_palettes}, ensure_ascii=False)
    payload_str = payload_str.replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>mintchip — Interactive Visual Gallery</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 28px 18px 48px;
    font-family: ui-sans-serif,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
    line-height: 1.55; transition: background 180ms ease, color 180ms ease;
  }}
  .wrap {{ max-width: 1040px; margin: 0 auto; }}
  header {{
    display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between;
    gap: 16px; padding-bottom: 18px; margin-bottom: 18px; border-bottom: 1px solid var(--grid);
  }}
  h1 {{ margin: 0 0 4px; font-size: 24px; letter-spacing: -0.02em; }}
  .sub {{ margin: 0; font-size: 13.5px; color: var(--muted); }}
  .controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
  .pill-group {{
    display: inline-flex; border: 1px solid var(--grid); border-radius: 7px; overflow: hidden;
  }}
  .pill-group button, .btn {{
    background: transparent; border: none; color: var(--muted);
    padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer;
    font-family: inherit;
  }}
  .pill-group button.active {{ background: var(--primary); color: #fff; }}
  .btn {{
    border: 1px solid var(--grid); border-radius: 7px; color: var(--ink);
  }}
  .btn-primary {{ background: var(--primary); border-color: var(--primary); color: #fff; }}
  .prose-card {{
    border: 1px solid var(--grid); border-radius: 10px; padding: 18px 22px;
    margin-bottom: 22px; background: var(--card);
  }}
  .prose-card h2 {{
    margin: 0 0 10px; font-size: 12px; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--muted);
  }}
  .prose-card p {{ margin: 0 0 10px; font-size: 14.5px; line-height: 1.8; }}
  .prose-card p:last-child {{ margin-bottom: 0; }}
  .chip {{
    display: inline-flex; align-items: center; gap: 5px; vertical-align: -0.22em;
    padding: 1px 7px; border-radius: 5px; border: 1px solid var(--grid);
    background: var(--pill); color: var(--ink); font-size: 0.91em; line-height: 1.25;
    white-space: nowrap; cursor: pointer;
  }}
  .chip:hover {{ border-color: var(--primary); }}
  .chip-val {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
  .chip-mono {{ font-family: ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size: 0.88em; }}
  .filters {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }}
  .filters button {{
    background: var(--card); border: 1px solid var(--grid); border-radius: 6px;
    padding: 5px 11px; font-size: 12px; font-weight: 600; color: var(--muted); cursor: pointer;
  }}
  .filters button.active {{ background: var(--primary); border-color: var(--primary); color: #fff; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 14px; }}
  .card {{
    border: 1px solid var(--grid); border-radius: 10px; padding: 16px;
    background: var(--card); display: flex; flex-direction: column; justify-content: space-between; gap: 10px;
  }}
  .card-head {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
  .card-name {{ font-family: ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size: 13.5px; font-weight: 700; }}
  .tag {{
    font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em;
    padding: 2px 6px; border-radius: 4px; border: 1px solid var(--grid); color: var(--muted);
  }}
  .question {{ margin: 0; font-size: 12px; color: var(--muted); }}
  .sentence {{ margin: 0; font-size: 13.5px; line-height: 1.65; }}
  .code-box {{
    border: 1px solid var(--grid); border-radius: 6px; padding: 7px 9px;
    font-family: ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size: 11.5px;
    background: var(--bg); overflow-x: auto;
  }}
  .code-row {{ display: flex; gap: 6px; }}
  .code-k {{ color: var(--muted); flex-shrink: 0; }}
  .facts {{ margin: 0; padding-left: 16px; font-size: 11.5px; color: var(--muted); }}
  .triage {{
    display: flex; justify-content: space-between; align-items: center;
    padding-top: 8px; border-top: 1px solid var(--grid); font-size: 11.5px;
  }}
  .triage-btns {{ display: flex; gap: 4px; }}
  .triage-btns button {{
    background: transparent; border: 1px solid var(--grid); border-radius: 5px;
    padding: 2px 8px; font-size: 11px; color: var(--muted); cursor: pointer;
  }}
  .triage-btns button.on-keep {{ background: #0F9478; border-color: #0F9478; color: #fff; font-weight: 600; }}
  .triage-btns button.on-refine {{ background: #CC8800; border-color: #CC8800; color: #fff; font-weight: 600; }}
  .triage-btns button.on-drop {{ background: #CD4324; border-color: #CD4324; color: #fff; font-weight: 600; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>mintchip — Visual Gallery</h1>
      <p class="sub">17 zero-dependency word-sized chips across SVG, Unicode, and ASCII. Switch themes or triage below.</p>
    </div>
    <div class="controls">
      <div class="pill-group" id="mode-group">
        <button data-mode="svg" class="active">SVG</button>
        <button data-mode="text">Unicode</button>
        <button data-mode="ascii">ASCII</button>
      </div>
      <div class="pill-group" id="theme-group">
        <button data-theme="default" class="active">default</button>
        <button data-theme="dark">dark</button>
        <button data-theme="paper">paper</button>
        <button data-theme="editorial">editorial</button>
        <button data-theme="mono">mono</button>
      </div>
      <button id="copy-btn" class="btn btn-primary" type="button">Copy Triage</button>
    </div>
  </header>

  <section class="prose-card" id="prose-demo"></section>
  <nav class="filters" id="filters"></nav>
  <main class="grid" id="grid"></main>
</div>

<script>
const DATA = {payload_str};
const BY_NAME = Object.fromEntries(DATA.items.map(x => [x.name, x]));
let mode = "svg";
let theme = "default";
let family = "all";
const verdicts = {{}};

function applyThemeVars() {{
  const t = DATA.themes[theme];
  const s = document.documentElement.style;
  s.setProperty("--bg", t.is_dark ? "#0F1319" : "#F6F8FA");
  s.setProperty("--card", t.bg);
  s.setProperty("--pill", t.is_dark ? "rgba(255,255,255,0.06)" : "rgba(26,29,33,0.035)");
  s.setProperty("--ink", t.ink);
  s.setProperty("--muted", t.muted);
  s.setProperty("--grid", t.grid);
  s.setProperty("--primary", t.primary);
  document.body.style.background = t.is_dark ? "#0F1319" : "#F6F8FA";
  document.body.style.color = t.ink;
}}

function chipMarkup(item, compact=true) {{
  if (mode === "svg") {{
    const val = compact ? item.compact : item.value;
    return `<span class="chip" title="${{item.facts.join(" | ")}}"><span class="chip-val">${{val}}</span><span style="display:inline-flex;align-items:center;">${{item.svgs[theme]}}</span></span>`;
  }}
  const txt = mode === "ascii" ? item.ascii : (compact ? item.text_compact : item.text);
  return `<span class="chip chip-mono" title="${{item.facts.join(" | ")}}">${{txt}}</span>`;
}}

function renderProse() {{
  const c = (name) => chipMarkup(BY_NAME[name], true);
  document.getElementById("prose-demo").innerHTML = `
    <h2>Live Prose Showcase (${{mode.toUpperCase()}} · style="${{theme}}")</h2>
    <p>Across 5 seeds, training settled into the target band at ${{c("spark")}}, lifting accuracy to ${{c("bar")}} (${{c("delta")}}) via ${{c("waterfall")}}, with retrieval adding ${{c("ci")}} and compute scaling tightly at ${{c("scatter")}}.</p>
    <p>VRAM splits ${{c("share")}}; cohort screening retained ${{c("funnel")}} with ${{c("ratio")}} responders, arterial pH stayed centered at ${{c("gauge")}}, SLA breach risk is ${{c("quantiles")}}, and primary support rates ${{c("evidence")}}. Shard latency clusters at ${{c("dist")}}, repro seeds show ${{c("strip")}}, turns took ${{c("timeline")}}, ranking ${{c("rank")}} while train/val curves end at ${{c("dual_spark")}}.</p>
  `;
}}

function renderFilters() {{
  const fams = [
    ["all", "All (17)"], ["core", "Core (5)"], ["change", "Change & Tradeoffs (3)"],
    ["composition", "Composition & Flow (3)"], ["evidence", "Windows & Evidence (3)"],
    ["structure", "Structure & Runs (3)"]
  ];
  document.getElementById("filters").innerHTML = fams.map(([id, lbl]) =>
    `<button data-fam="${{id}}" class="${{family === id ? "active" : ""}}">${{lbl}}</button>`
  ).join("");
}}

function renderGrid() {{
  const visible = family === "all" ? DATA.items : DATA.items.filter(x => x.family === family);
  document.getElementById("grid").innerHTML = visible.map(item => {{
    const v = verdicts[item.name] || "";
    const sent = item.sentence.replace("{{c}}", chipMarkup(item, true));
    return `
      <article class="card">
        <div style="display:flex;flex-direction:column;gap:8px;">
          <div class="card-head">
            <span class="card-name">mc.${{item.name}}</span>
            <span class="tag">${{item.family}}</span>
          </div>
          <p class="question">${{item.question}}</p>
          <p class="sentence">${{sent}}</p>
          <div class="code-box">
            <div class="code-row"><span class="code-k">text:</span><span>${{item.text}}</span></div>
            <div class="code-row"><span class="code-k">code:</span><span>${{item.code}}</span></div>
          </div>
          <ul class="facts">${{item.facts.slice(0, 2).map(f => `<li>${{f}}</li>`).join("")}}</ul>
        </div>
        <div class="triage">
          <span style="color:var(--muted);">Triage</span>
          <div class="triage-btns">
            <button data-v="keep" data-n="${{item.name}}" class="${{v === "keep" ? "on-keep" : ""}}">Keep</button>
            <button data-v="refine" data-n="${{item.name}}" class="${{v === "refine" ? "on-refine" : ""}}">Refine</button>
            <button data-v="drop" data-n="${{item.name}}" class="${{v === "drop" ? "on-drop" : ""}}">Drop</button>
          </div>
        </div>
      </article>
    `;
  }}).join("");
}}

function rerender() {{
  applyThemeVars();
  renderProse();
  renderFilters();
  renderGrid();
}}

document.getElementById("mode-group").addEventListener("click", (e) => {{
  const b = e.target.closest("button[data-mode]");
  if (!b) return;
  mode = b.dataset.mode;
  document.querySelectorAll("#mode-group button").forEach(x => x.classList.toggle("active", x === b));
  rerender();
}});
document.getElementById("theme-group").addEventListener("click", (e) => {{
  const b = e.target.closest("button[data-theme]");
  if (!b) return;
  theme = b.dataset.theme;
  document.querySelectorAll("#theme-group button").forEach(x => x.classList.toggle("active", x === b));
  rerender();
}});
document.getElementById("filters").addEventListener("click", (e) => {{
  const b = e.target.closest("button[data-fam]");
  if (!b) return;
  family = b.dataset.fam;
  rerender();
}});
document.getElementById("grid").addEventListener("click", (e) => {{
  const b = e.target.closest("button[data-v]");
  if (!b) return;
  verdicts[b.dataset.n] = verdicts[b.dataset.n] === b.dataset.v ? "" : b.dataset.v;
  renderGrid();
}});
document.getElementById("copy-btn").addEventListener("click", async () => {{
  const g = {{ keep: [], refine: [], drop: [], undecided: [] }};
  DATA.items.forEach(x => g[verdicts[x.name] || "undecided"].push(x.name));
  const txt = [
    "**mintchip Triage**",
    `- Keep (${{g.keep.length}}): ${{g.keep.join(", ") || "—"}}`,
    `- Refine (${{g.refine.length}}): ${{g.refine.join(", ") || "—"}}`,
    `- Drop (${{g.drop.length}}): ${{g.drop.join(", ") || "—"}}`,
  ].join("\\n");
  try {{
    await navigator.clipboard.writeText(txt);
    const btn = document.getElementById("copy-btn");
    btn.textContent = "Copied!";
    setTimeout(() => btn.textContent = "Copy Triage", 1600);
  }} catch (_) {{ console.log(txt); }}
}});

rerender();
</script>
</body>
</html>
"""


def main() -> None:
    CHIPS_DIR.mkdir(parents=True, exist_ok=True)
    light_specs = _demo_specs("default")
    dark_specs = _demo_specs("dark")

    for lr, dr in zip(light_specs, dark_specs):
        (CHIPS_DIR / f"{lr['name']}.svg").write_text(_chip_pill_svg(lr["chip"]), encoding="utf-8")
        (CHIPS_DIR / f"{dr['name']}_dark.svg").write_text(_chip_pill_svg(dr["chip"]), encoding="utf-8")

    (OUT_DIR / "hero_banner.svg").write_text(_render_hero_banner_svg(), encoding="utf-8")
    (OUT_DIR / "themes_overview.svg").write_text(_render_themes_overview_svg(), encoding="utf-8")
    (OUT_DIR / "index.html").write_text(_render_interactive_gallery_html(), encoding="utf-8")
    print(f"Built mintchip gallery: {len(light_specs) * 2} chip SVGs + hero_banner.svg + themes_overview.svg + index.html")


if __name__ == "__main__":
    main()
