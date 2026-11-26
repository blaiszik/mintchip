"""Tests for Change & Attribution inline micro-graphics (delta, waterfall, scatter)."""

from __future__ import annotations

import html as html_lib
import importlib.util
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_HAS_MINTFIG = importlib.util.find_spec("mintfig") is not None

import mintchip as mc
from mintchip.change import delta, scatter, waterfall
from mintchip.core import Chip, shared_domain


def _parse_svg(svg: str) -> ET.Element:
    assert svg.startswith("<svg ") and svg.endswith("</svg>")
    return ET.fromstring(svg)


def _assert_pure_ascii(text: str) -> None:
    assert all(ord(ch) < 128 for ch in text), f"Non-ASCII character in {text!r}"


# --------------------------------------------------------------------------- #
# 1. delta
# --------------------------------------------------------------------------- #


def test_delta_favorable_and_regression_dual_surface() -> None:
    up = delta(0.74, 0.82, label="Accuracy", expand=_HAS_MINTFIG)
    assert isinstance(up, Chip)
    assert up.kind == "delta"
    root = _parse_svg(up.svg)
    assert root.tag.endswith("svg")
    assert "<polygon" in up.svg  # arrowhead
    assert up.theme.series_colors[2] in up.svg  # favorable teal/primary
    assert "Before: 0.74" in up.svg
    assert "After: 0.82 (+0.08)" in up.svg

    assert up.value_text == "0.74→0.82 (+0.08)"
    assert up.compact_value == "+0.08"
    assert up.text.startswith("[") and up.text.endswith("]")
    assert len(up.text) == 13  # [ + 11 slots + ]
    assert "○" in up.text and "▶" in up.text and "●" in up.text
    _assert_pure_ascii(up.ascii_text)
    assert len(up.ascii_text) == 13
    assert "o" in up.ascii_text and ">" in up.ascii_text and "*" in up.ascii_text
    assert up.data["favorable"] is True
    assert math.isclose(up.data["delta"], 0.08)
    assert any("favorable" in f for f in up.facts)
    if _HAS_MINTFIG:
        assert up.expand_explanation is not None
    if _HAS_MINTFIG:
        assert next(iter(up.expand_explanation.panels.values())).kind == "change"

    # Regression when higher_is_better=True
    down = delta(0.82, 0.74, label="Accuracy")
    assert down.theme.accent_colors[0] in down.svg  # warm accent
    assert down.data["favorable"] is False
    assert "●" in down.text and "◀" in down.text and "○" in down.text
    assert down.text.index("●") < down.text.index("◀") < down.text.index("○")
    _assert_pure_ascii(down.ascii_text)
    assert down.ascii_text.index("*") < down.ascii_text.index("<") < down.ascii_text.index("o")
    assert any("regression" in f for f in down.facts)


def test_delta_higher_is_better_false_and_units() -> None:
    faster = delta(120, 95, label="Latency", unit="ms", higher_is_better=False)
    _parse_svg(faster.svg)
    assert faster.data["favorable"] is True
    assert faster.theme.series_colors[2] in faster.svg
    assert "◀" in faster.text
    assert faster.value_text == "120 ms→95 ms (\N{MINUS SIGN}25 ms)"
    assert faster.compact_value == "\N{MINUS SIGN}25 ms"
    assert any("favorable; lower is better" in f for f in faster.facts)

    slower = delta(95, 120, label="Latency", unit="ms", higher_is_better=False)
    assert slower.data["favorable"] is False
    assert slower.theme.accent_colors[0] in slower.svg
    assert "▶" in slower.text
    assert any("regression; lower is better" in f for f in slower.facts)


def test_delta_shared_domain_and_dark_theme(tmp_path: Path) -> None:
    dom = shared_domain((0.40, 0.55), (0.72, 0.90))
    low = delta(0.42, 0.52, domain=dom, style="dark")
    high = delta(0.74, 0.88, domain=dom, style="dark")
    _parse_svg(low.svg)
    _parse_svg(high.svg)

    assert low.theme.name == "dark"
    assert low.theme.background in low.svg
    # Low delta sits left of high delta on the shared 11-slot ruler
    assert low.text.index("○") < high.text.index("○")
    assert low.text.index("●") < high.text.index("●")

    # Shared domain crossing zero adds a subtle zero reference tick
    cross = delta(-0.10, 0.15, domain=(-0.30, 0.30), palette="okabe_ito")
    _parse_svg(cross.svg)
    assert "stroke-dasharray=" in cross.svg

    out = tmp_path / "delta_dark.html"
    res = low.save(out)
    assert out.exists()
    assert res["kind"] == "delta"


def test_delta_zero_delta_tiny_move_and_errors() -> None:
    flat = delta(0.80, 0.80, label="F1", expand=_HAS_MINTFIG)
    _parse_svg(flat.svg)
    assert flat.data["delta"] == 0.0
    assert flat.data["favorable"] is None
    assert flat.theme.muted in flat.svg
    assert "◎" in flat.text
    assert "=" in flat.ascii_text
    _assert_pure_ascii(flat.ascii_text)
    assert flat.compact_value == "0"
    assert any("Unchanged" in f for f in flat.facts)
    if _HAS_MINTFIG:
        assert flat.expand_explanation is not None

    # Tiny move collapsing to same slot on a huge shared domain
    tiny = delta(0.50, 0.501, domain=(0.0, 100.0))
    _parse_svg(tiny.svg)
    assert "▸" in tiny.text
    assert ">" in tiny.ascii_text

    # HTML escaping
    xss = delta(1.0, 2.0, label='<script>alert("x")</script>')
    _parse_svg(xss.svg)
    assert "<script>" not in xss.svg
    assert "<script>" not in xss.html(show_label=True)

    # Error cases
    with pytest.raises(mc.ChipError):
        delta(float("nan"), 1.0)
    with pytest.raises(mc.ChipError):
        delta(1.0, float("inf"))
    with pytest.raises(mc.ChipError):
        delta(True, 1.0)  # type: ignore[arg-type]
    with pytest.raises(mc.ChipError):
        delta(0.1, 0.2, domain=(0.0, float("nan")))
    with pytest.raises(mc.ChipError):
        delta(0.1, 0.2, domain=(0.0,))  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 2. waterfall
# --------------------------------------------------------------------------- #


def test_waterfall_mapping_svg_unicode_ascii_and_expand() -> None:
    steps = {"Retrieval": 0.12, "Reranker": 0.08, "Latency cap": -0.01}
    g = waterfall(steps, label="Pass@1 lift", expand=_HAS_MINTFIG)
    assert isinstance(g, Chip)
    assert g.kind == "waterfall"
    root = _parse_svg(g.svg)
    assert root.tag.endswith("svg")

    # Floating bars + per-bar tooltips + positive/negative colors + final total dot
    assert g.svg.count("<rect ") == 3
    assert "Retrieval: +0.12" in g.svg
    assert "Reranker: +0.08" in g.svg
    assert "Latency cap: \N{MINUS SIGN}0.01" in g.svg
    assert g.theme.series_colors[2] in g.svg
    assert g.theme.accent_colors[0] in g.svg
    assert "<circle " in g.svg

    # Unicode & ASCII proportional directional glyphs
    assert g.text.startswith("[") and g.text.endswith("]")
    assert g.text.count("▲") == 2 and g.text.count("▼") == 1
    _assert_pure_ascii(g.ascii_text)
    assert g.ascii_text.startswith("[+") and "-1]" in g.ascii_text

    assert g.value_text == "net +0.19"
    assert g.compact_value == "+0.19"
    assert g.data["crosses_zero"] is False
    assert math.isclose(g.data["net"], 0.19)
    assert any("Retrieval" in f for f in g.facts)
    assert any("Latency cap" in f for f in g.facts)

    if _HAS_MINTFIG:
        assert g.expand_explanation is not None
    if _HAS_MINTFIG:
        assert next(iter(g.expand_explanation.panels.values())).kind == "waterfall"
    chip_html = g.html(show_label=True)
    m = re.search(r'data-mf-chip="([^"]+)"', chip_html)
    assert m is not None
    payload = json.loads(html_lib.unescape(m.group(1)))
    if _HAS_MINTFIG:
        assert payload["has_figure"] is True
    if _HAS_MINTFIG:
        assert "<svg" in payload["figure_svg"]


def test_waterfall_sequence_nonzero_start_zero_crossing_and_dark() -> None:
    # Sequence of floats with non-zero start
    seq = waterfall([0.12, 0.08, -0.01], start=0.65, label="Score", style="dark", expand=_HAS_MINTFIG)
    _parse_svg(seq.svg)
    assert seq.theme.name == "dark"
    assert seq.value_text == "0.65→0.84 (+0.19)"
    assert seq.compact_value == "+0.19"
    assert "Start: 0.65" in seq.svg
    if _HAS_MINTFIG:
        assert seq.expand_explanation is not None

    # Crossing zero triggers dashed zero reference line
    cross = waterfall({"Init": 0.30, "Regression": -0.75, "Patch": 0.25}, unit="%")
    _parse_svg(cross.svg)
    assert cross.data["crosses_zero"] is True
    assert "stroke-dasharray=" in cross.svg
    assert any("crosses zero" in f for f in cross.facts)

    # Non-zero start crossing zero
    cross_start = waterfall([-15.0, 5.0], start=10.0)
    _parse_svg(cross_start.svg)
    assert cross_start.data["crosses_zero"] is True
    assert "stroke-dasharray=" in cross_start.svg


def test_waterfall_edge_cases_and_errors() -> None:
    # All-zero steps
    zeros = waterfall({"A": 0.0, "B": 0.0}, expand=_HAS_MINTFIG)
    _parse_svg(zeros.svg)
    assert zeros.text == "[··]"
    assert zeros.ascii_text == "[00]"
    _assert_pure_ascii(zeros.ascii_text)
    if _HAS_MINTFIG:
        assert zeros.expand_explanation is not None

    # Single step
    single = waterfall({"Only": 0.25}, expand=_HAS_MINTFIG)
    _parse_svg(single.svg)
    assert single.svg.count("<rect ") == 1
    if _HAS_MINTFIG:
        assert single.expand_explanation is not None

    # Sequence of (name, delta) tuples with duplicate names still expands cleanly
    dups = waterfall([("Cache", 0.05), ("Cache", 0.03)], expand=_HAS_MINTFIG)
    _parse_svg(dups.svg)
    if _HAS_MINTFIG:
        assert dups.expand_explanation is not None

    # Errors
    with pytest.raises(mc.ChipError):
        waterfall({})
    with pytest.raises(mc.ChipError):
        waterfall([])
    with pytest.raises(mc.ChipError):
        waterfall("abc")  # type: ignore[arg-type]
    with pytest.raises(mc.ChipError):
        waterfall({"A": float("nan")})
    with pytest.raises(mc.ChipError):
        waterfall([True, 0.2])  # type: ignore[list-item]
    with pytest.raises(mc.ChipError):
        waterfall([0.1, 0.2], start=float("inf"))


# --------------------------------------------------------------------------- #
# 3. scatter
# --------------------------------------------------------------------------- #


def test_scatter_braille_correlation_fit_and_expand() -> None:
    xs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    ys = [1.1, 1.9, 3.2, 3.8, 5.1, 6.2, 6.9, 8.1, 8.8, 10.2]
    g = scatter(
        xs,
        ys,
        fit=True,
        label="Scaling",
        x_label="Params",
        y_label="Score",
        expand=_HAS_MINTFIG,
    )
    assert isinstance(g, Chip)
    assert g.kind == "scatter"
    root = _parse_svg(g.svg)
    assert root.tag.endswith("svg")
    assert "<path " in g.svg  # L-axes
    assert "<line " in g.svg  # OLS regression line
    assert "OLS fit:" in g.svg

    # True 2D Unicode Braille check: [ + 5 chars in U+2800..U+28FF + ]
    assert g.text.startswith("[") and g.text.endswith("]")
    inner = g.text[1:-1]
    assert len(inner) == 5
    for ch in inner:
        assert 0x2800 <= ord(ch) <= 0x28FF, f"Not Braille: {ch!r} (U+{ord(ch):04X})"
    # Every cell in a 10-point diagonal should have lit dots (non-blank)
    assert all(ord(ch) > 0x2800 for ch in inner)

    # Pure 5-char ASCII fallback
    _assert_pure_ascii(g.ascii_text)
    assert g.ascii_text.startswith("[") and g.ascii_text.endswith("]")
    assert len(g.ascii_text) == 7

    assert g.data["n"] == 10
    assert g.data["r"] is not None and g.data["r"] > 0.99
    assert g.value_text.startswith("r=1.00") or g.value_text.startswith("r=0.99")
    assert any("Pearson r =" in f and "n=10" in f for f in g.facts)
    assert any("OLS fit:" in f for f in g.facts)
    if _HAS_MINTFIG:
        assert g.expand_explanation is not None
    if _HAS_MINTFIG:
        assert next(iter(g.expand_explanation.panels.values())).kind == "relate"

    # Negative correlation produces Unicode minus in r and distinct Braille pattern
    neg = scatter(xs, list(reversed(ys)), fit=True)
    _parse_svg(neg.svg)
    assert neg.data["r"] is not None and neg.data["r"] < -0.99
    assert "\N{MINUS SIGN}" in neg.value_text
    assert neg.text != g.text


def test_scatter_highlight_and_pareto_frontier_and_dark() -> None:
    xs = [1.0, 2.0, 3.0, 4.0, 5.0, 2.5]
    ys = [5.0, 4.8, 3.5, 4.0, 2.0, 2.2]
    names = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta"]
    # Upper-right non-dominated points: Alpha(1,5), Beta(2,4.8), Delta(4,4.0), Epsilon(5,2.0)
    # Gamma(3,3.5) is dominated by Delta(4,4.0); Zeta(2.5,2.2) is dominated by Delta(4,4.0)
    g = scatter(
        xs,
        ys,
        names=names,
        highlight="Delta",
        frontier=True,
        x_label="Throughput",
        y_label="Quality",
        style="dark",
        expand=_HAS_MINTFIG,
    )
    _parse_svg(g.svg)
    assert g.theme.name == "dark"
    assert "<polyline " in g.svg  # Pareto frontier polyline
    assert 'fill-opacity="0.22"' in g.svg  # highlight halo
    assert g.theme.accent_colors[0] in g.svg  # bold accented dot
    assert g.data["frontier_indices"] == [0, 1, 3, 4]
    assert g.data["highlight"] == "Delta"
    assert g.data["highlight_coords"] == (4.0, 4.0)
    assert g.value_text == "Delta (4, 4)"
    assert g.compact_value == "Delta"
    assert "*" in g.ascii_text
    assert any("Highlight Delta" in f and "Throughput=4" in f for f in g.facts)
    assert any("Pareto frontier" in f and "Delta" in f for f in g.facts)
    if _HAS_MINTFIG:
        assert g.expand_explanation is not None
    if _HAS_MINTFIG:
        assert next(iter(g.expand_explanation.panels.values())).kind == "relate"

    # Highlight by negative integer index without names + fit=True switches value_text to r=...
    by_idx = scatter(xs, ys, highlight=-1, fit=True, expand=_HAS_MINTFIG)
    _parse_svg(by_idx.svg)
    assert by_idx.data["highlight"] == 5
    assert by_idx.value_text.startswith("r=")
    assert any("Highlight point #5" in f for f in by_idx.facts)
    if _HAS_MINTFIG:
        assert by_idx.expand_explanation is not None

    # Highlight by int index with fit=False shows coordinates
    coords_only = scatter(xs, ys, highlight=0)
    assert coords_only.value_text == "(1, 5)"
    assert coords_only.compact_value == "(1, 5)"


def test_scatter_edge_cases_and_errors() -> None:
    # n == 2: valid inline scatter, Pearson r undefined
    two = scatter([1.0, 4.0], [2.0, 6.0])
    _parse_svg(two.svg)
    assert two.data["r"] is None
    assert two.value_text == "n=2"
    assert len(two.text[1:-1]) == 5
    assert all(0x2800 <= ord(c) <= 0x28FF for c in two.text[1:-1])
    assert any("n < 3" in f for f in two.facts)

    # Zero variance (constant y) with fit=True does not divide by zero
    const_y = scatter([1.0, 2.0, 3.0, 4.0], [5.0, 5.0, 5.0, 5.0], fit=True)
    _parse_svg(const_y.svg)
    assert const_y.data["r"] is None
    assert "<line " in const_y.svg
    assert any("zero variance" in f for f in const_y.facts)

    # Constant x
    const_x = scatter([3.0, 3.0, 3.0], [1.0, 2.0, 4.0], fit=True)
    _parse_svg(const_x.svg)
    assert const_x.data["r"] is None

    # Single dominant upper-right point on frontier
    single_front = scatter([1.0, 2.0, 5.0], [1.0, 2.0, 5.0], frontier=True)
    _parse_svg(single_front.svg)
    assert single_front.data["frontier_indices"] == [2]

    # Missing NaN pair dropped cleanly while preserving highlight index
    with_nan = scatter([1.0, float("nan"), 3.0, 5.0], [2.0, 4.0, 6.0, 8.0], highlight=3)
    _parse_svg(with_nan.svg)
    assert with_nan.data["n"] == 3
    assert with_nan.data["highlight_coords"] == (5.0, 8.0)

    # Large n (> 60) renders cleanly
    big = scatter(list(range(80)), [i * 0.5 + (i % 7) for i in range(80)])
    _parse_svg(big.svg)
    assert big.data["n"] == 80

    # Markdown output modes
    assert big.markdown(mode="unicode").startswith("`")
    assert big.markdown(mode="svg_uri").startswith("![")

    # Error cases
    with pytest.raises(mc.ChipError):
        scatter([], [])
    with pytest.raises(mc.ChipError):
        scatter([1.0], [2.0])
    with pytest.raises(mc.ChipError):
        scatter([1.0, 2.0], [1.0, 2.0, 3.0])
    with pytest.raises(mc.ChipError):
        scatter([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], names=["a", "b"])
    with pytest.raises(mc.ChipError):
        scatter([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], highlight="missing")
    with pytest.raises(mc.ChipError):
        scatter([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], names=["a", "b", "c"], highlight="missing")
    with pytest.raises(mc.ChipError):
        scatter([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], highlight=10)
    with pytest.raises(mc.ChipError):
        scatter([1.0, float("nan"), 3.0], [1.0, 2.0, 3.0], highlight=1)
    with pytest.raises(mc.ChipError):
        scatter([1.0, 2.0, 3.0], [1.0, 2.0, 3.0], highlight=True)
