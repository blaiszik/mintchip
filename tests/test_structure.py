"""Tests for Structure, Timelines & Comparison inline micro-graphics."""

from __future__ import annotations

import html as html_lib
import importlib.util
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_HAS_MINTFIG = importlib.util.find_spec("mintfig") is not None

import mintchip as mc
from mintchip.structure import dual_spark, rank, timeline


def _parse_svg(svg: str) -> ET.Element:
    assert svg.startswith("<svg ") and svg.endswith("</svg>")
    return ET.fromstring(svg)


def _assert_pure_ascii(text: str) -> None:
    assert all(ord(ch) < 128 for ch in text), f"Non-ASCII character in {text!r}"


# --------------------------------------------------------------------------- #
# 1. timeline()
# --------------------------------------------------------------------------- #


def test_timeline_sequential_mapping_svg_unicode_ascii_and_expand(tmp_path: Path) -> None:
    g = timeline(
        {"fetch": 1.2, "code": 4.8, "test": 1.5},
        label="Agent turn",
        unit="s",
        expand=_HAS_MINTFIG,
    )
    assert isinstance(g, mc.Chip)
    assert g.kind == "timeline"
    assert g.value_text == "7.5 s (code 64%)"
    assert g.compact_value == "7.5 s"
    assert g.to_text(compact=True).startswith("7.5 s [")
    assert g.to_text().startswith("7.5 s (code 64%) [")

    # 10-cell proportional phase strip wrapped in [...]
    assert g.text.startswith("[") and g.text.endswith("]") and len(g.text) == 12
    assert g.ascii_text.startswith("[") and g.ascii_text.endswith("]") and len(g.ascii_text) == 12
    _assert_pure_ascii(g.ascii_text)
    assert "█" in g.text and "#" in g.ascii_text
    assert g.text.count("█") >= 5  # bottleneck occupies ~64% of 10 cells

    # Valid SVG with per-stage <title> and warm accent on bottleneck
    root = _parse_svg(g.svg)
    titles = [el.text or "" for el in root.iter("{http://www.w3.org/2000/svg}title")]
    assert any("fetch:" in t for t in titles)
    assert any("code:" in t and "[bottleneck]" in t for t in titles)
    assert any("test:" in t for t in titles)
    assert g.theme.accent_colors[0] in g.svg

    # Facts & structured data
    assert g.data["bottleneck"] == "code"
    assert g.data["total_span"] == pytest.approx(7.5)
    assert g.data["bottleneck_share"] == pytest.approx(4.8 / 7.5)
    assert g.data["overlap_count"] == 0
    assert g.data["lanes"] == 1
    assert any("7.5 s" in f for f in g.facts)
    assert any("code" in f and "64.0%" in f for f in g.facts)

    # Expandable HTML chip + save
    if _HAS_MINTFIG:
        assert g.expand_explanation is not None
    chip_html = g.html(show_label=True)
    if _HAS_MINTFIG:
        assert "data-mf-chip=" in chip_html and "↗" in chip_html
    m = re.search(r'data-mf-chip="([^"]+)"', chip_html)
    assert m is not None
    payload = json.loads(html_lib.unescape(m.group(1)))
    if _HAS_MINTFIG:
        assert payload["has_figure"] is True
    if _HAS_MINTFIG:
        assert "<svg" in payload["figure_svg"]

    svg_file = tmp_path / "timeline.svg"
    res = g.save(svg_file)
    assert svg_file.exists() and res["expandable"] is _HAS_MINTFIG


def test_timeline_parallel_intervals_lanes_overlaps_and_idle_gap() -> None:
    g = timeline(
        {
            "fetch": (0.0, 1.5),
            "compile": (1.0, 6.0),
            "lint": (1.0, 3.0),
            "package": (7.0, 10.0),
        },
        label="CI build",
        unit="s",
        expand=_HAS_MINTFIG,
    )
    root = _parse_svg(g.svg)
    assert g.data["is_parallel"] is True
    assert g.data["overlap_count"] >= 2  # fetch/compile, fetch/lint, compile/lint -> 3
    assert g.data["overlap_count"] == 3
    assert g.data["peak_concurrency"] == 3
    assert g.data["lanes"] == 3
    assert g.data["idle_time"] == pytest.approx(1.0)
    assert g.data["bottleneck"] == "compile"
    assert g.value_text == "10 s (compile 50%)"

    # Idle gap [6.0, 7.0] shows up as · / . in the 10-cell strip
    assert "·" in g.text
    assert "." in g.ascii_text
    assert any("overlap" in f for f in g.facts)
    assert any("Idle gap" in f for f in g.facts)

    # Multiple distinct y-coordinates for stacked horizontal lanes
    rects = [
        el
        for el in root.iter("{http://www.w3.org/2000/svg}rect")
        if el.find("{http://www.w3.org/2000/svg}title") is not None
    ]
    assert len(rects) == 4
    distinct_ys = {round(float(r.attrib["y"]), 2) for r in rects}
    assert len(distinct_ys) == 3
    if _HAS_MINTFIG:
        assert g.expand_explanation is not None


def test_timeline_sequence_durations_and_milestone_and_themes() -> None:
    # Bare sequence of durations
    seq_g = timeline([1.0, 3.0, 1.0], unit="ms", style="dark", palette="okabe_ito")
    _parse_svg(seq_g.svg)
    assert seq_g.data["bottleneck"] == "Stage 2"
    assert seq_g.value_text == "5 ms (Stage 2 60%)"
    assert seq_g.theme.name == "dark"
    assert seq_g.theme.accent_colors[0] in seq_g.svg

    # Zero-duration milestone inside an interval timeline renders a diamond polygon
    ms_g = timeline({"start": (0.0, 0.0), "run": (0.0, 4.0)}, unit="s")
    root = _parse_svg(ms_g.svg)
    polys = list(root.iter("{http://www.w3.org/2000/svg}polygon"))
    assert len(polys) == 1
    assert ms_g.data["bottleneck"] == "run"


@pytest.mark.parametrize(
    "bad_stages",
    [
        {},
        [],
        "not-stages",
        {"a": -1.0},
        {"a": 0.0, "b": 0.0},
        {"a": float("nan")},
        {"a": True},
        {"a": (5.0, 2.0)},
        {"a": (0.0, 2.0), "b": 3.0},  # mixed interval & scalar
        [1.0, -0.5],
        [("x", 4.0, 1.0)],
    ],
)
def test_timeline_invalid_inputs_raise(bad_stages: object) -> None:
    with pytest.raises(mc.ChipError):
        timeline(bad_stages)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 2. rank()
# --------------------------------------------------------------------------- #


def test_rank_explicit_position_total_and_quartiles() -> None:
    top = rank(2, 18, label="Model A", expand=_HAS_MINTFIG)
    assert isinstance(top, mc.Chip)
    assert top.kind == "rank"
    assert top.value_text == "#2/18 (p94)"
    assert top.compact_value == "#2/18"
    assert top.text == "[········●·]"
    assert top.ascii_text == "[........*.]"
    _assert_pure_ascii(top.ascii_text)
    assert top.data["tier"] == "top 25%"
    assert top.theme.series_colors[0] in top.svg
    _parse_svg(top.svg)
    if _HAS_MINTFIG:
        assert top.expand_explanation is not None
    assert any("#2 of 18" in f and "p94" in f for f in top.facts)

    # #1 best sits at the rightmost slot
    best = rank(1, 18)
    assert best.text == "[·········●]"
    assert best.ascii_text == "[.........*]"
    assert best.value_text == "#1/18 (p100)"

    # Middle 50% colored in theme.ink
    mid = rank(9, 18)
    assert mid.data["tier"] == "middle 50%"
    assert f'fill="{mid.theme.ink}"' in mid.svg
    _parse_svg(mid.svg)

    # Bottom 25% colored in warm accent
    low = rank(17, 18, expand=_HAS_MINTFIG)
    assert low.data["tier"] == "bottom 25%"
    assert f'fill="{low.theme.accent_colors[0]}"' in low.svg
    if _HAS_MINTFIG:
        assert low.expand_explanation is not None

    # Worst sits at the leftmost slot
    worst = rank(18, 18)
    assert worst.text == "[●·········]"
    assert worst.ascii_text == "[*.........]"
    assert worst.value_text == "#18/18 (p0)"


def test_rank_cohort_values_higher_and_lower_is_better_and_dark_theme() -> None:
    scores = [0.68, 0.72, 0.75, 0.79, 0.84, 0.88, 0.91]
    g = rank(values=scores, value=0.88, label="Mint-7B", unit=None, expand=_HAS_MINTFIG)
    root = _parse_svg(g.svg)
    assert g.data["position"] == 2
    assert g.data["total"] == 7
    assert g.compact_value == "#2/7"
    assert "p83" in g.value_text
    if _HAS_MINTFIG:
        assert g.expand_explanation is not None
    assert any("cohort median" in f for f in g.facts)

    # Peer dots rendered in SVG (6 peers + 2 entity circles = 8 circles)
    circles = list(root.iter("{http://www.w3.org/2000/svg}circle"))
    assert len(circles) == 8

    # Lower-is-better (e.g. latency): smaller value ranks closer to #1 on the right!
    latencies = [12.0, 15.0, 21.0, 28.0, 40.0]
    fast = rank(
        values=latencies,
        value=12.0,
        higher_is_better=False,
        label="Latency",
        unit="ms",
        style="dark",
        expand=_HAS_MINTFIG,
    )
    _parse_svg(fast.svg)
    assert fast.data["position"] == 1
    assert fast.data["total"] == 5
    assert fast.text == "[·········●]"
    assert fast.theme.name == "dark"
    assert any("Lower values rank higher" in f for f in fast.facts)
    if _HAS_MINTFIG:
        assert fast.expand_explanation is not None

    # Value not already present in peer list is included automatically
    new_cand = rank(values=[10.0, 20.0, 40.0], value=30.0)
    assert new_cand.data["position"] == 2
    assert new_cand.data["total"] == 4

    # Small cohort (n=2) still expands cleanly via compare() fallback
    small = rank(values=[0.5, 0.9], value=0.9, expand=_HAS_MINTFIG)
    assert small.data["position"] == 1 and small.data["total"] == 2
    if _HAS_MINTFIG:
        assert small.expand_explanation is not None

    # Large cohort switches peer markers cleanly to rug ticks
    big = rank(values=[float(i) for i in range(60)], value=55.0)
    _parse_svg(big.svg)
    assert big.data["position"] == 5 and big.data["total"] == 60


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"position": 2},
        {"total": 10},
        {"position": 0, "total": 10},
        {"position": 11, "total": 10},
        {"position": 1, "total": 0},
        {"position": True, "total": 5},
        {"position": 2, "total": 10, "values": [1, 2, 3], "value": 2},
        {"values": [1.0, 2.0]},
        {"value": 1.0},
        {"values": [1.0], "value": 1.0},
        {"values": [], "value": 1.0},
        {"values": [1.0, 2.0, 3.0], "value": float("nan")},
        {"values": "abc", "value": 1.0},
    ],
)
def test_rank_invalid_inputs_raise(kwargs: dict[str, object]) -> None:
    with pytest.raises(mc.ChipError):
        rank(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# 3. dual_spark()
# --------------------------------------------------------------------------- #


def test_dual_spark_divergence_gap_shading_and_expand() -> None:
    train = [1.40, 1.05, 0.80, 0.62, 0.51, 0.45, 0.42]
    val = [1.42, 1.10, 0.88, 0.74, 0.66, 0.62, 0.61]
    g = dual_spark(
        train,
        val,
        labels=("train", "val"),
        label="Loss",
        expand=_HAS_MINTFIG,
    )
    assert isinstance(g, mc.Chip)
    assert g.kind == "dual_spark"
    assert g.value_text == "0.42 vs 0.61 (Δ−0.19)"
    assert g.compact_value == "Δ−0.19"
    assert g.text.startswith("[") and g.text.endswith("]") and len(g.text) == 9
    assert g.ascii_text.startswith("[") and g.ascii_text.endswith("]") and len(g.ascii_text) == 9
    _assert_pure_ascii(g.ascii_text)

    # SVG has shaded gap polygon in warm accent (B > A everywhere), 2 polylines (one dashed), 2 end dots
    root = _parse_svg(g.svg)
    polys = list(root.iter("{http://www.w3.org/2000/svg}polygon"))
    lines = list(root.iter("{http://www.w3.org/2000/svg}polyline"))
    circles = list(root.iter("{http://www.w3.org/2000/svg}circle"))
    assert len(polys) == 1
    assert polys[0].attrib["fill"] == g.theme.accent_colors[0]
    assert len(lines) == 2
    assert any("stroke-dasharray" in ln.attrib for ln in lines)
    assert len(circles) == 2

    # Facts & metrics
    assert g.data["crossovers"] == 0
    assert g.data["start_gap"] == pytest.approx(-0.02)
    assert g.data["end_gap"] == pytest.approx(-0.19)
    assert g.data["max_divergence_step"] == 6
    assert g.data["max_divergence"] == pytest.approx(0.19)
    assert any("0 crossovers" in f for f in g.facts)
    assert any("Max divergence" in f and "step 6" in f for f in g.facts)
    assert any("Start gap" in f and "end gap" in f for f in g.facts)
    if _HAS_MINTFIG:
        assert g.expand_explanation is not None


def test_dual_spark_crossovers_split_shading_and_dark_theme() -> None:
    # Crosses twice: A > B -> B > A -> A > B
    a = [1.0, 2.0, 1.0, 0.5, 2.5]
    b = [0.5, 1.0, 2.0, 1.5, 1.0]
    g = dual_spark(
        a,
        b,
        labels=("Actual", "Forecast"),
        label="Demand",
        unit="kW",
        style="dark",
        expand=_HAS_MINTFIG,
    )
    root = _parse_svg(g.svg)
    assert g.data["crossovers"] == 2
    assert g.theme.name == "dark"
    assert any("2 crossovers" in f for f in g.facts)
    assert g.compact_value == "Δ+1.5 kW"
    if _HAS_MINTFIG:
        assert g.expand_explanation is not None

    # Crossover splitting yields 3 polygons alternating primary (A>=B) and warm accent (B>A)
    polys = list(root.iter("{http://www.w3.org/2000/svg}polygon"))
    assert len(polys) == 3
    fills = [p.attrib["fill"] for p in polys]
    assert fills == [g.theme.series_colors[0], g.theme.accent_colors[0], g.theme.series_colors[0]]

    # Touching zero and bouncing back is NOT a crossover; touching zero and crossing IS 1 crossover
    bounce = dual_spark([2.0, 1.0, 2.0], [1.0, 1.0, 1.0])
    assert bounce.data["crossovers"] == 0

    zero_cross = dual_spark([2.0, 1.0, 0.0], [1.0, 1.0, 1.0])
    assert zero_cross.data["crossovers"] == 1
    assert any("1 crossover " in f for f in zero_cross.facts)


def test_dual_spark_gaps_flat_long_series_and_escaping() -> None:
    # Handles None gaps cleanly
    with_gaps = dual_spark([1.0, 1.2, None, 0.8, 0.6], [0.9, 1.0, None, 1.1, 1.2])
    root = _parse_svg(with_gaps.svg)
    assert len(list(root.iter("{http://www.w3.org/2000/svg}polyline"))) == 4
    assert with_gaps.data["crossovers"] == 1

    # Flat identical series -> zero divergence, valid SVG
    flat = dual_spark([3.0, 3.0, 3.0], [3.0, 3.0, 3.0])
    _parse_svg(flat.svg)
    assert flat.data["max_divergence"] == 0.0
    assert flat.compact_value == "Δ0"
    assert flat.text == "[▁▁▁]"

    # Long series (>12 points) downsamples Unicode glyph cleanly to 12 cells + brackets
    long_a = [float(i) for i in range(25)]
    long_b = [float(i) * 0.8 for i in range(25)]
    long_g = dual_spark(long_a, long_b, labels=("<A&1>", "<B&2>"), label="A < B & C")
    _parse_svg(long_g.svg)
    assert len(long_g.text) == 14  # '[' + 12 cells + ']'
    assert "&lt;A&amp;1&gt;" in long_g.svg


@pytest.mark.parametrize(
    "args,kwargs",
    [
        (([1.0, 2.0], [1.0]), {}),
        (([1.0], [2.0]), {}),
        (([], []), {}),
        (([1.0, None], [1.0, 2.0]), {}),
        (("abc", "def"), {}),
        (([1.0, 2.0], [2.0, 3.0]), {"labels": ("only_one",)}),
    ],
)
def test_dual_spark_invalid_inputs_raise(args: tuple[object, ...], kwargs: dict[str, object]) -> None:
    with pytest.raises(mc.ChipError):
        dual_spark(*args, **kwargs)  # type: ignore[arg-type]
