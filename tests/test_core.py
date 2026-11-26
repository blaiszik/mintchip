"""Tests for mintchip core primitives, prose interpolation, document builder, and themes."""

from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path

import pytest

import mintchip as mc


def test_spark_svg_unicode_and_save(tmp_path: Path) -> None:
    g = mc.spark(
        [1.82, 1.31, 0.94, 0.72, 0.58, 0.49, 0.44],
        label="Val loss",
        band=(0.40, 0.55),
        reference=0.50,
    )
    assert isinstance(g, mc.Chip)
    assert g.kind == "spark"
    assert g.svg.startswith("<svg ") and g.svg.endswith("</svg>")
    assert "<polyline" in g.svg
    assert "<rect" in g.svg
    assert "0.44" in str(g)
    assert any("within band" in f for f in g.facts)
    assert g.markdown(mode="svg_uri").startswith("![")

    svg_path = tmp_path / "loss.svg"
    res = g.save(svg_path)
    assert svg_path.exists()
    assert res["kind"] == "spark"


def test_spark_gaps_and_flat_series() -> None:
    g = mc.spark([2.0, 2.0, None, 2.0, 2.0])
    assert g.svg.count("<polyline") == 2
    assert "flat" in g.facts[0]

    with pytest.raises(mc.ChipError):
        mc.spark([1.0])


def test_ci_solid_vs_hollow_null_encoding_and_warning() -> None:
    dom = mc.shared_domain((0.06, 0.22), (-0.03, 0.07), reference=0.0)
    assert dom[0] < -0.03 and dom[1] > 0.22

    sig = mc.ci(
        0.14,
        (0.06, 0.22),
        error_label="95% CI, 10 seeds",
        inner_error=(0.11, 0.17),
        reference=0.0,
        domain=dom,
        label="Δ accuracy",
    )
    assert sig.warnings == []
    assert sig.data["excludes_reference"] is True
    assert "│" in sig.text and "●" in sig.text
    assert "|" in sig.ascii_text and "*" in sig.ascii_text

    null_ci = mc.ci(0.02, 0.05, reference=0.0, domain=dom)
    assert null_ci.data["excludes_reference"] is False
    assert "○" in null_ci.text and "o" in null_ci.ascii_text
    assert any("Unnamed uncertainty" in w for w in null_ci.warnings)
    assert f'fill="{null_ci.theme.background}"' in null_ci.svg


def test_dist_small_and_large_n() -> None:
    small = mc.dist(
        [12.1, 12.4, 12.9, 13.0, 13.2, 13.5, 13.8, 28.4],
        label="Latency",
        unit="ms",
        reference=15.0,
    )
    assert "<circle" in small.svg
    assert any("outlier" in f for f in small.facts)

    large = mc.dist([float(i % 17) + 0.1 * (i // 17) for i in range(120)])
    assert "<rect" in large.svg
    assert large.data["n"] == 120


def test_bar_and_strip_modes() -> None:
    b = mc.bar(0.84, total=1.0, baseline=0.76, target=0.80, bands=(0.60, 0.80), label="Pass@1")
    assert b.value_text == "84%"
    assert any("meets target" in f for f in b.facts)

    status = mc.strip(
        [True, True, False, True, "warn", "skip", True],
        labels=[f"seed_{i}" for i in range(7)],
        label="Seeds",
    )
    assert "4/6 pass" in status.value_text
    assert any("seed_2" in f for f in status.facts)
    assert "<path" in status.svg
    assert "▄" in status.text and "□" in status.text

    heat = mc.strip([-0.8, -0.2, 0.0, 0.4, 0.9], diverging=True, label="Effect")
    assert heat.data["numeric"] is True
    assert heat.svg.count("<rect") == 5


def test_prose_escaping_compact_and_document(tmp_path: Path) -> None:
    chip = mc.bar(0.82, baseline=0.74, label="<script>alert(1)</script>")
    prose = mc.format_prose("Model reached {acc} with <unsafe> tags.", acc=chip)
    assert "&lt;unsafe&gt;" in prose
    assert "&lt;script&gt;" in prose
    assert "<script>alert(1)</script>" not in prose

    m = re.search(r'data-mf-chip="([^"]+)"', prose)
    assert m is not None
    payload = json.loads(html_lib.unescape(m.group(1)))
    assert payload["kind"] == "bar"

    doc_html = mc.document(
        "Ablation Note",
        [prose],
        subtitle="Word-sized inline chips",
        style="dark",
        palette="okabe_ito",
        source="pytest",
    )
    out = tmp_path / "note.html"
    out.write_text(doc_html, encoding="utf-8")
    assert "color-scheme: dark" in doc_html

    ci_chip = mc.ci(0.08, (0.05, 0.11), error_label="95% CI")
    compact_prose = mc.format_prose("Gain {g}.", mode="text", compact=True, g=ci_chip)
    assert "[+0.05" not in compact_prose
    assert "+0.08 [" in compact_prose


def test_themes_palettes_and_accent() -> None:
    for theme_name in mc.THEMES:
        for pal_name in mc.PALETTES:
            g = mc.spark([1, 3, 2, 5], style=theme_name, palette=pal_name, accent="#2563EB")
            assert g.svg.startswith("<svg ")
            assert mc.contrast_ratio(g.theme.ink, g.theme.background) >= 4.5


def test_catalog_exports_all_17_components() -> None:
    names = [entry["name"] for entry in mc.CATALOG]
    assert len(names) == 17
    assert len(set(names)) == 17
    for name in names:
        assert callable(getattr(mc, name))
