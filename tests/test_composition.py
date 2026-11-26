"""Tests for Composition & Flow inline components (share, funnel, ratio)."""

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
from mintchip.composition import funnel, ratio, share
from mintchip.core import Chip, format_prose

SVG_NS = "{http://www.w3.org/2000/svg}"


def _parse_svg(svg: str) -> ET.Element:
    assert svg.startswith("<svg ") and svg.endswith("</svg>")
    root = ET.fromstring(svg)
    assert root.tag == f"{SVG_NS}svg"
    return root


def _titles(root: ET.Element) -> list[str]:
    return [el.text or "" for el in root.iter(f"{SVG_NS}title")]


# --------------------------------------------------------------------------- #
# 1. share()
# --------------------------------------------------------------------------- #


def test_share_mapping_svg_unicode_ascii_and_facts() -> None:
    g = share({"Code": 62, "Docs": 28, "Tests": 10}, label="Tokens", unit="k")
    assert isinstance(g, Chip)
    assert g.kind == "share"
    assert g.value_text == "62/28/10%"
    assert g.compact_value == "Code 62%"
    assert g.text == "[██████▓▓▓░]"
    assert g.ascii_text == "[######===.]"
    assert g.ascii_text.isascii()
    assert g.to_text() == "62/28/10% [██████▓▓▓░]"
    assert g.to_text(compact=True) == "Code 62% [██████▓▓▓░]"
    assert g.to_text(ascii_only=True) == "62/28/10% [######===.]"

    root = _parse_svg(g.svg)
    rects = list(root.iter(f"{SVG_NS}rect"))
    # 1 subtle background track + 3 segment rects
    assert len(rects) == 4
    lines = list(root.iter(f"{SVG_NS}line"))
    # 2 thin background separators between 3 segments
    assert len(lines) == 2
    assert all(ln.attrib["stroke"] == g.theme.background for ln in lines)

    titles = _titles(root)
    assert any("Code: 62.0%" in t for t in titles)
    assert any("Docs: 28.0%" in t for t in titles)
    assert any("Tests: 10.0%" in t for t in titles)

    # Theme series colors used in descending rank order
    seg_fills = [r.attrib["fill"] for r in rects[1:]]
    assert seg_fills == list(g.theme.series_colors[:3])

    assert any("100 k" in f for f in g.facts)
    assert any("Largest: Code 62.0%" in f for f in g.facts)
    assert g.data["folded_count"] == 0
    assert g.data["top_name"] == "Code"


def test_share_sequence_unsorted_and_single_part() -> None:
    seq_g = share([10, 62, 28])
    assert seq_g.value_text == "62/28/10%"
    assert seq_g.compact_value == "62% top"
    assert seq_g.text == "[██████▓▓▓░]"
    assert seq_g.ascii_text == "[######===.]"

    pairs_g = share([("Alpha", 30), ("Beta", 70)])
    assert pairs_g.value_text == "70/30%"
    assert pairs_g.compact_value == "Beta 70%"
    assert pairs_g.text == "[███████░░░]"
    assert pairs_g.ascii_text == "[#######...]"

    single = share({"Only": 100}, expand=_HAS_MINTFIG)
    root = _parse_svg(single.svg)
    assert len(list(root.iter(f"{SVG_NS}line"))) == 0
    assert single.value_text == "100%"
    assert single.text == "[██████████]"
    assert single.ascii_text == "[##########]"
    if _HAS_MINTFIG:
        assert single.expand_explanation is not None


def test_share_four_parts_vs_folding_more_than_four() -> None:
    four = share({"A": 40, "B": 30, "C": 20, "D": 10})
    assert four.data["folded_count"] == 0
    assert len(four.data["parts"]) == 4
    assert all(not p["is_other"] for p in four.data["parts"])
    assert four.text == "[████▓▓▓▒▒░]"
    assert four.ascii_text == "[####===--.]"
    assert four.theme.context_fill not in four.svg

    six = share({"A": 40, "B": 25, "C": 15, "D": 10, "E": 6, "F": 4}, label="Traffic")
    assert six.data["folded_count"] == 2
    assert len(six.data["parts"]) == 5
    assert six.data["parts"][-1]["name"] == "Other"
    assert six.data["parts"][-1]["is_other"] is True
    assert math.isclose(six.data["parts"][-1]["pct"], 10.0)
    assert six.value_text == "40/25/15/10/10%"
    assert len(six.text) == 12  # "[" + 10 cells + "]"
    assert len(six.ascii_text) == 12
    assert six.ascii_text.isascii()

    root = _parse_svg(six.svg)
    rects = list(root.iter(f"{SVG_NS}rect"))
    # 1 track + 4 top parts + 1 Other
    assert len(rects) == 6
    assert rects[-1].attrib["fill"] == six.theme.context_fill
    assert any("Other: 10.0%" in t for t in _titles(root))
    assert any("2 smaller parts folded into Other" in f for f in six.facts)

    # Edge case: "Other" already in top 4
    collision = share({"Other": 50, "A": 20, "B": 15, "C": 10, "D": 3, "E": 2})
    assert collision.data["folded_count"] == 2
    assert collision.data["parts"][-1]["name"] == "Other (2)"


def test_share_themes_and_expand() -> None:
    light = share({"Code": 60, "Docs": 40}, style="mintfig", expand=_HAS_MINTFIG)
    dark = share(
        {"Code": 60, "Docs": 40},
        style="dark",
        palette="okabe_ito",
        label="Mix",
        expand=_HAS_MINTFIG,
    )
    assert light.theme.background != dark.theme.background
    assert dark.theme.background in dark.svg
    assert dark.theme.series_colors[0] in dark.svg
    if _HAS_MINTFIG:
        assert light.expand_explanation is not None
    if _HAS_MINTFIG:
        assert dark.expand_explanation is not None
    if _HAS_MINTFIG:
        assert "Code" in light.expand_explanation.takeaway

    chip_html = dark.html(show_label=True)
    m = re.search(r'data-mf-chip="([^"]+)"', chip_html)
    assert m is not None
    payload = json.loads(html_lib.unescape(m.group(1)))
    assert payload["kind"] == "share"
    if _HAS_MINTFIG:
        assert payload["has_figure"] is True
    if _HAS_MINTFIG:
        assert "<svg" in payload["figure_svg"]


@pytest.mark.parametrize(
    "bad_parts",
    [
        {},
        [],
        "abc",
        123,
        {"A": -5, "B": 10},
        {"A": 0, "B": 10},
        {"A": 0, "B": 0},
        [0, 0],
        [-1, 2],
        [math.nan, 1.0],
        [math.inf, 1.0],
        [True, False],
        [("A", 10), ("A", 20)],
    ],
)
def test_share_invalid_inputs_raise_explain_error(bad_parts: object) -> None:
    with pytest.raises(mc.ChipError):
        share(bad_parts)  # type: ignore[arg-type]


def test_share_invalid_dimensions() -> None:
    with pytest.raises(mc.ChipError):
        share([10, 20], width=0)
    with pytest.raises(mc.ChipError):
        share([10, 20], height=-4)


# --------------------------------------------------------------------------- #
# 2. funnel()
# --------------------------------------------------------------------------- #


def test_funnel_mapping_steepest_drop_svg_unicode_ascii() -> None:
    stages = {
        "Screened": 1200,
        "Eligible": 520,
        "Enrolled": 350,
        "Completed": 290,
    }
    g = funnel(stages, label="Trial cohort")
    assert isinstance(g, Chip)
    assert g.kind == "funnel"
    assert g.value_text == "1,200→290 (24%)"
    assert g.compact_value == "24% retained"
    assert g.text == "[█▄▃▃]"
    assert g.ascii_text.isascii()
    assert g.ascii_text.startswith("[") and g.ascii_text.endswith("]")
    assert len(g.ascii_text) == 6
    assert g.to_text() == "1,200→290 (24%) [█▄▃▃]"
    assert g.to_text(compact=True) == "24% retained [█▄▃▃]"

    # Steepest drop: Screened (1200) -> Eligible (520), drop = 680
    assert g.data["steepest_drop_stage"] == "Eligible"
    assert g.data["steepest_drop_index"] == 1
    assert g.data["steepest_drop_count"] == 680.0
    assert math.isclose(g.data["retention_pct"], 290 / 1200 * 100.0)
    assert any("24.2% retained" in f for f in g.facts)
    assert any("Steepest drop at Eligible" in f and "680" in f for f in g.facts)

    root = _parse_svg(g.svg)
    rects = list(root.iter(f"{SVG_NS}rect"))
    polys = list(root.iter(f"{SVG_NS}polygon"))
    assert len(rects) == 4
    assert len(polys) == 3  # connecting trapezoids

    accent_c = g.theme.accent_colors[0]
    primary_c = g.theme.series_colors[0]
    assert rects[0].attrib["fill"] == primary_c
    assert rects[1].attrib["fill"] == accent_c  # steepest drop highlighted in warm accent
    assert rects[2].attrib["fill"] == primary_c
    assert rects[3].attrib["fill"] == primary_c

    titles = _titles(root)
    assert any("Screened: 1,200 (100.0% retained)" in t for t in titles)
    assert any("Eligible: 520" in t and "steepest drop" in t for t in titles)
    assert any("Completed: 290 (24.2% retained)" in t for t in titles)


def test_funnel_steepest_drop_later_stage_and_sequences() -> None:
    # Steepest drop at stage 2 (950 -> 200, drop 750)
    g = funnel([1000, 950, 200, 180])
    assert g.data["steepest_drop_index"] == 2
    assert g.data["steepest_drop_stage"] == "Stage 3"
    assert g.data["steepest_drop_count"] == 750.0
    root = _parse_svg(g.svg)
    rects = list(root.iter(f"{SVG_NS}rect"))
    assert rects[2].attrib["fill"] == g.theme.accent_colors[0]

    # Tuple pairs + zero final stage
    zero_end = funnel([("In", 100), ("Filter", 30), ("Shipped", 0)])
    assert zero_end.value_text == "100→0 (0%)"
    assert zero_end.compact_value == "0% retained"
    assert zero_end.data["steepest_drop_stage"] == "Filter"
    _parse_svg(zero_end.svg)

    # Flat funnel (no drops -> no warm accent highlight)
    flat = funnel({"A": 50, "B": 50, "C": 50})
    assert flat.data["steepest_drop_index"] is None
    assert flat.data["steepest_drop_count"] == 0.0
    assert any("No attrition drop" in f for f in flat.facts)
    flat_root = _parse_svg(flat.svg)
    assert all(r.attrib["fill"] == flat.theme.series_colors[0] for r in flat_root.iter(f"{SVG_NS}rect"))

    # Long pipeline (>12 stages) stays word-sized in Unicode
    long_f = funnel([1000 - i * 50 for i in range(16)])
    assert len(long_f.text) == 14  # "[" + 12 glyphs + "]"
    _parse_svg(long_f.svg)


def test_funnel_themes_and_expand() -> None:
    stages = {"Visited": 500, "Signed up": 210, "Activated": 95}
    light = funnel(stages, label="Onboarding", style="mintfig", expand=_HAS_MINTFIG)
    dark = funnel(stages, label="Onboarding", style="dark", accent="#FF9F1C", expand=_HAS_MINTFIG)

    if _HAS_MINTFIG:
        assert light.expand_explanation is not None
    if _HAS_MINTFIG:
        assert dark.expand_explanation is not None
    assert dark.theme.accent_colors[0] in dark.svg
    assert dark.theme.series_colors[0] in dark.svg
    assert light.theme.series_colors[0] != dark.theme.series_colors[0]

    chip_html = light.html(show_label=True)
    m = re.search(r'data-mf-chip="([^"]+)"', chip_html)
    assert m is not None
    payload = json.loads(html_lib.unescape(m.group(1)))
    assert payload["kind"] == "funnel"
    if _HAS_MINTFIG:
        assert payload["has_figure"] is True
    if _HAS_MINTFIG:
        assert "<svg" in payload["figure_svg"]


@pytest.mark.parametrize(
    "bad_stages",
    [
        {},
        [],
        {"Only": 100},
        [100],
        {"Start": 0, "End": 0},
        [0, 50],
        {"Start": 100, "Bad": -10},
        [100, -5, 10],
        [100, math.nan],
        [math.inf, 10],
        [True, False],
        "abc",
        42,
    ],
)
def test_funnel_invalid_inputs_raise_explain_error(bad_stages: object) -> None:
    with pytest.raises(mc.ChipError):
        funnel(bad_stages)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 3. ratio()
# --------------------------------------------------------------------------- #


def test_ratio_exact_count_total_two_rows_and_single_row() -> None:
    # 10 units -> 2 rows x 5 cols
    g = ratio(3, 10, label="Adverse events")
    assert isinstance(g, Chip)
    assert g.kind == "ratio"
    assert g.value_text == "3/10 (30%)"
    assert g.compact_value == "3/10"
    assert g.text == "[●●●○○○○○○○]"
    assert g.ascii_text == "[***.......]"
    assert g.ascii_text.isascii()
    assert g.to_text() == "3/10 (30%) [●●●○○○○○○○]"
    assert g.to_text(compact=True) == "3/10 [●●●○○○○○○○]"
    assert g.to_text(ascii_only=True) == "3/10 (30%) [***.......]"
    assert g.data["rows"] == 2 and g.data["cols"] == 5
    assert g.data["displayed_hits"] == 3 and g.data["displayed_units"] == 10

    root = _parse_svg(g.svg)
    circles = list(root.iter(f"{SVG_NS}circle"))
    assert len(circles) == 10
    filled = [c for c in circles if c.attrib["fill"] == g.theme.series_colors[0]]
    hollow = [c for c in circles if c.attrib["fill"] == g.theme.background]
    assert len(filled) == 3
    assert len(hollow) == 7
    assert all(c.attrib["stroke"] == g.theme.context_line for c in hollow)
    unique_ys = {round(float(c.attrib["cy"]), 2) for c in circles}
    assert len(unique_ys) == 2  # 2-row dot grid

    assert any("exact fraction 3/10" in f and "30.0%" in f for f in g.facts)
    assert any("Natural frequency: 3 out of 10" in f for f in g.facts)

    # <= 8 units -> single row
    single_row = ratio(3, 8)
    assert single_row.data["rows"] == 1 and single_row.data["cols"] == 8
    assert single_row.text == "[●●●○○○○○]"
    assert single_row.ascii_text == "[***.....]"
    sr_root = _parse_svg(single_row.svg)
    sr_circles = list(sr_root.iter(f"{SVG_NS}circle"))
    assert len(sr_circles) == 8
    assert len({round(float(c.attrib["cy"]), 2) for c in sr_circles}) == 1

    # Reduced fraction reported when gcd > 1
    reducible = ratio(6, 10)
    assert any("3/5" in f for f in reducible.facts)


def test_ratio_proportion_mode_and_unicode_scaling() -> None:
    # 0.24 with units=20 -> 2x10 SVG (5 filled, 15 hollow), scaled to 10 dots in Unicode (2 filled)
    g = ratio(0.24, units=20, label="Conversion")
    assert g.value_text == "24% (~5/20)"
    assert g.compact_value == "24%"
    assert g.text == "[●●○○○○○○○○]"
    assert g.ascii_text == "[**........]"
    assert g.ascii_text.isascii()
    assert g.data["mode"] == "proportion"
    assert g.data["rows"] == 2 and g.data["cols"] == 10
    assert g.data["displayed_hits"] == 5 and g.data["displayed_units"] == 20
    assert g.data["approximate"] is True

    root = _parse_svg(g.svg)
    circles = list(root.iter(f"{SVG_NS}circle"))
    assert len(circles) == 20
    filled = [c for c in circles if c.attrib["fill"] == g.theme.series_colors[0]]
    assert len(filled) == 5
    assert len({round(float(c.attrib["cy"]), 2) for c in circles}) == 2

    assert any("24.0%" in f and "6/25" in f for f in g.facts)
    assert any("Natural frequency: about 5 out of every 20" in f for f in g.facts)

    # Exact proportion has no ~ marker
    exact_prop = ratio(0.3, units=10)
    assert exact_prop.value_text == "30% (3/10)"
    assert exact_prop.data["approximate"] is False
    assert any("Natural frequency: 3 out of every 10" in f for f in exact_prop.facts)

    # Large exact total scales icon array cleanly while preserving exact readout
    large_exact = ratio(45, 100, units=20)
    assert large_exact.value_text == "45/100 (45%)"
    assert large_exact.compact_value == "45/100"
    assert large_exact.data["displayed_units"] == 20
    assert large_exact.data["displayed_hits"] == 9
    assert len(list(_parse_svg(large_exact.svg).iter(f"{SVG_NS}circle"))) == 20
    assert len(large_exact.text) == 12  # "[" + 10 dots + "]"


def test_ratio_boundaries_custom_width_themes_and_expand() -> None:
    zero = ratio(0, 10, expand=_HAS_MINTFIG)
    full = ratio(10, 10, expand=_HAS_MINTFIG)
    one = ratio(1, 1, width=24)
    assert zero.text == "[○○○○○○○○○○]"
    assert full.text == "[●●●●●●●●●●]"
    assert one.text == "[●]"
    assert 'width="24"' in one.svg
    if _HAS_MINTFIG:
        assert zero.expand_explanation is not None
    if _HAS_MINTFIG:
        assert full.expand_explanation is not None

    dark = ratio(0.24, units=20, label="Responder", style="dark", expand=_HAS_MINTFIG)
    if _HAS_MINTFIG:
        assert dark.expand_explanation is not None
    assert dark.theme.background in dark.svg
    assert dark.theme.series_colors[0] in dark.svg
    assert dark.theme.context_line in dark.svg

    chip_html = dark.html(show_label=True)
    m = re.search(r'data-mf-chip="([^"]+)"', chip_html)
    assert m is not None
    payload = json.loads(html_lib.unescape(m.group(1)))
    assert payload["kind"] == "ratio"
    if _HAS_MINTFIG:
        assert payload["has_figure"] is True
    if _HAS_MINTFIG:
        assert "<svg" in payload["figure_svg"]


@pytest.mark.parametrize(
    "args,kwargs",
    [
        ((-0.1,), {}),
        ((1.2,), {}),
        ((math.nan,), {}),
        ((math.inf,), {}),
        ((True,), {}),
        ((-1, 10), {}),
        ((11, 10), {}),
        ((3, 0), {}),
        ((3, -5), {}),
        ((2.5, 10), {}),
        ((3, 10.5), {}),
        ((3, True), {}),
        ((0.5,), {"units": 0}),
        ((0.5,), {"units": -4}),
        ((0.5,), {"units": 101}),
        ((0.5,), {"units": True}),
        ((3, 10), {"width": 0}),
        ((3, 10), {"height": 0}),
    ],
)
def test_ratio_invalid_inputs_raise_explain_error(
    args: tuple[object, ...], kwargs: dict[str, object]
) -> None:
    with pytest.raises(mc.ChipError):
        ratio(*args, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Cross-component integration: prose, escaping, markdown, and save()
# --------------------------------------------------------------------------- #


def test_composition_family_escaping_prose_markdown_and_save(tmp_path: Path) -> None:
    s = share({"<script>": 70, "A&B": 30}, label="Mix <1>")
    f = funnel({"In <raw>": 200, "Out & ok": 80}, label="Pipe & flow")
    r = ratio(3, 10, label="Hits <tag>")

    for g in (s, f, r):
        _parse_svg(g.svg)
        assert "<script>" not in g.svg
        assert g.markdown(mode="unicode").startswith("`")
        assert g.markdown(mode="svg_uri").startswith("![")
        summary = g.summary()
        assert summary["kind"] == g.kind
        assert summary["facts"]

    prose = format_prose(
        "Split {s}, retention {f}, and frequency {r}.",
        s=s,
        f=f,
        r=r,
    )
    assert "&lt;script&gt;" in prose
    assert "<script>" not in prose

    svg_out = tmp_path / "share.svg"
    res = s.save(svg_out)
    assert svg_out.exists()
    assert res["kind"] == "share"
