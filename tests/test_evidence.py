"""Tests for Uncertainty, Thresholds & Evidence inline components (mintfig._inline.evidence)."""

from __future__ import annotations

import html as html_lib
import importlib.util
import json
import random
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_HAS_MINTFIG = importlib.util.find_spec("mintfig") is not None

import mintchip as mc
from mintchip.evidence import evidence, gauge, quantiles


def _parse_svg(svg: str) -> ET.Element:
    assert svg.startswith("<svg ") and svg.endswith("</svg>")
    return ET.fromstring(svg)


def _extract_chip_payload(chip_html: str) -> dict:
    match = re.search(r'data-mf-chip="([^"]+)"', chip_html)
    assert match is not None
    return json.loads(html_lib.unescape(match.group(1)))


# --------------------------------------------------------------------------- #
# 1. gauge
# --------------------------------------------------------------------------- #


def test_gauge_within_warn_above_below_and_facts() -> None:
    # Within normal window
    ok = gauge(7.38, (7.35, 7.45), warn=(7.25, 7.55), label="Blood pH", unit="pH")
    assert isinstance(ok, mc.Chip)
    assert ok.kind == "gauge"
    root = _parse_svg(ok.svg)
    assert "<polygon" in ok.svg
    assert len(root.findall(".//{http://www.w3.org/2000/svg}rect")) == 2  # warn + normal bands
    assert ok.theme.series_colors[2] in ok.svg  # teal/primary diamond
    assert ok.data["status"] == "within"
    assert ok.data["distance_to_boundary"] == pytest.approx(0.03)
    assert "7.38 pH [7.35–7.45]" == ok.value_text
    assert ok.compact_value == "7.38 pH"
    assert "◆" in ok.text and "|" in ok.text
    assert "*" in ok.ascii_text and ok.ascii_text.isascii()
    assert len(ok.text) == 13  # '[' + 11 slots + ']'
    assert len(ok.ascii_text) == 13
    assert any("within" in f for f in ok.facts)
    assert any("0.03 pH" in f for f in ok.facts)

    # Inside warn band above normal
    warn_hi = gauge(7.50, (7.35, 7.45), warn=(7.25, 7.55), label="Blood pH")
    _parse_svg(warn_hi.svg)
    assert warn_hi.data["status"] == "warn"
    assert warn_hi.data["side"] == "above"
    assert warn_hi.data["distance_to_boundary"] == pytest.approx(0.05)
    assert warn_hi.theme.series_colors[3] in warn_hi.svg  # amber diamond
    assert "▲" in warn_hi.text and "^" in warn_hi.ascii_text
    assert any("warn" in f for f in warn_hi.facts)

    # Inside warn band below normal
    warn_lo = gauge(7.30, (7.35, 7.45), warn=(7.25, 7.55))
    _parse_svg(warn_lo.svg)
    assert warn_lo.data["status"] == "warn"
    assert warn_lo.data["side"] == "below"
    assert warn_lo.data["distance_to_boundary"] == pytest.approx(0.05)
    assert "▼" in warn_lo.text and "v" in warn_lo.ascii_text

    # Above both normal and warn
    high = gauge(7.62, (7.35, 7.45), warn=(7.25, 7.55), label="Blood pH")
    _parse_svg(high.svg)
    assert high.data["status"] == "above"
    assert high.data["distance_to_boundary"] == pytest.approx(0.17)
    assert high.theme.accent_colors[0] in high.svg  # warm accent diamond
    assert "▲" in high.text and "^" in high.ascii_text
    assert any("above" in f for f in high.facts)
    assert any("beyond warn limit" in f for f in high.facts)

    # Below normal (no warn band)
    low = gauge(7.22, (7.35, 7.45))
    _parse_svg(low.svg)
    assert low.data["status"] == "below"
    assert low.data["distance_to_boundary"] == pytest.approx(0.13)
    assert low.theme.accent_colors[0] in low.svg
    assert "▼" in low.text and "v" in low.ascii_text
    assert any("below" in f for f in low.facts)


def test_gauge_themes_domain_boundaries_and_expand(tmp_path: Path) -> None:
    # Exact boundary reading counts as within with 0 distance
    edge = gauge(7.35, (7.35, 7.45), domain=(7.20, 7.60))
    assert edge.data["status"] == "within"
    assert edge.data["distance_to_boundary"] == pytest.approx(0.0)
    assert "◆" in edge.text

    # Dark theme + custom palette + expand=_HAS_MINTFIG
    g = gauge(
        7.48,
        (7.35, 7.45),
        warn=(7.25, 7.55),
        label="Arterial pH",
        style="dark",
        palette="okabe_ito",
        expand=_HAS_MINTFIG,
    )
    _parse_svg(g.svg)
    assert g.theme.name == "dark"
    assert g.theme.background in g.svg
    if _HAS_MINTFIG:
        assert g.expand_explanation is not None
        panel = next(iter(g.expand_explanation.panels.values()))
        assert panel.kind == "compare"

    chip_html = g.html(show_label=True)
    if _HAS_MINTFIG:
        assert "↗" in chip_html
    payload = _extract_chip_payload(chip_html)
    if _HAS_MINTFIG:
        assert payload["has_figure"] is True
    if _HAS_MINTFIG:
        assert "<svg" in payload["figure_svg"]

    svg_path = tmp_path / "gauge.svg"
    res = g.save(svg_path)
    assert svg_path.exists() and res["expandable"] is _HAS_MINTFIG


@pytest.mark.parametrize(
    "kwargs",
    [
        {"value": float("nan"), "normal": (7.35, 7.45)},
        {"value": float("inf"), "normal": (7.35, 7.45)},
        {"value": True, "normal": (7.35, 7.45)},
        {"value": 7.38, "normal": (7.45, 7.35)},
        {"value": 7.38, "normal": (7.35, 7.35)},
        {"value": 7.38, "normal": (7.35,)},
        {"value": 7.38, "normal": (7.35, float("nan"))},
        {"value": 7.38, "normal": (7.35, 7.45), "warn": (7.55, 7.25)},
        {"value": 7.38, "normal": (7.35, 7.45), "domain": (8.0, 7.0)},
        {"value": 7.38, "normal": (7.35, 7.45), "width": 0},
        {"value": 7.38, "normal": (7.35, 7.45), "height": -4},
    ],
)
def test_gauge_invalid_inputs_raise_explain_error(kwargs: dict) -> None:
    with pytest.raises(mc.ChipError):
        gauge(**kwargs)


# --------------------------------------------------------------------------- #
# 2. quantiles
# --------------------------------------------------------------------------- #


def test_quantiles_dot_count_and_threshold_exceedance() -> None:
    samples = [
        12.0, 14.2, 15.5, 16.8, 17.4, 18.1, 18.9, 19.3, 19.8, 20.1,
        20.6, 21.0, 21.5, 22.3, 23.1, 24.4, 25.8, 26.5, 27.9, 29.4,
    ]
    q = quantiles(samples, threshold=25.0, n_dots=10, label="Latency", unit="ms")
    assert isinstance(q, mc.Chip)
    assert q.kind == "quantiles"
    root = _parse_svg(q.svg)
    circles = root.findall(".//{http://www.w3.org/2000/svg}circle")
    assert len(circles) == 10
    assert q.data["n_dots"] == 10
    assert q.data["p_exceed"] == pytest.approx(4 / 20)  # 4 of 20 samples > 25.0 -> 20%
    assert q.data["dots_above"] == 2
    assert q.value_text == "P>25 ms 20%"
    assert q.compact_value == "20%"
    assert "│" in q.text
    assert "|" in q.ascii_text and q.ascii_text.isascii()
    assert q.theme.accent_colors[0] in q.svg
    assert q.theme.series_colors[0] in q.svg
    assert 'stroke-dasharray="2,1.5"' in q.svg
    assert any("Empirical P(X > 25 ms) = 20.0%" in f for f in q.facts)
    assert any("2/10 quantile dots above threshold" in f for f in q.facts)

    # Verify custom dot counts (5 and 20) and numpy array input
    for nd in (5, 20):
        qn = quantiles(tuple(samples), n_dots=nd)
        r = _parse_svg(qn.svg)
        assert len(r.findall(".//{http://www.w3.org/2000/svg}circle")) == nd
        assert qn.data["n_dots"] == nd
        assert qn.value_text.startswith("med ")
        assert "│" not in qn.text
        assert qn.ascii_text.isascii()


def test_quantiles_edge_cases_themes_and_expand() -> None:
    # Constant samples and dropped non-finite values
    const_q = quantiles([10.0, None, 10.0, float("nan"), 10.0, 10.0], threshold=12.0)  # type: ignore[list-item]
    root = _parse_svg(const_q.svg)
    assert len(root.findall(".//{http://www.w3.org/2000/svg}circle")) == 10
    assert const_q.data["p_exceed"] == 0.0
    assert any("non-finite" in f for f in const_q.facts)

    # Dark theme + custom accent + expand=_HAS_MINTFIG builds distribution(mode="quantile")
    rng = random.Random(7)
    draws = [20.0 + rng.gauss(0.0, 3.5) for _ in range(60)]
    q_exp = quantiles(
        draws,
        threshold=24.0,
        n_dots=12,
        label="ETA",
        unit="min",
        style="dark",
        accent="#E05A47",
        expand=_HAS_MINTFIG,
    )
    _parse_svg(q_exp.svg)
    assert q_exp.theme.name == "dark"
    if _HAS_MINTFIG:
        assert q_exp.expand_explanation is not None
        panel = next(iter(q_exp.expand_explanation.panels.values()))
        assert panel.kind == "distribution"
        assert panel.spec.get("mode") == "quantile"
        assert panel.spec.get("quantiles") == 12

    chip_html = q_exp.html(show_label=True)
    payload = _extract_chip_payload(chip_html)
    if _HAS_MINTFIG:
        assert payload["has_figure"] is True
    if _HAS_MINTFIG:
        assert "<svg" in payload["figure_svg"]


@pytest.mark.parametrize(
    "args,kwargs",
    [
        (([1.0, 2.0],), {}),
        (([1.0, None, float("nan"), 2.0],), {}),
        (("not-a-sequence",), {}),
        (([1.0, 2.0, 3.0, 4.0],), {"n_dots": 4}),
        (([1.0, 2.0, 3.0, 4.0],), {"n_dots": 21}),
        (([1.0, 2.0, 3.0, 4.0],), {"n_dots": True}),
        (([1.0, 2.0, 3.0, 4.0],), {"threshold": float("nan")}),
        (([1.0, 2.0, 3.0, 4.0],), {"domain": (5.0, 5.0)}),
    ],
)
def test_quantiles_invalid_inputs_raise_explain_error(args: tuple, kwargs: dict) -> None:
    with pytest.raises(mc.ChipError):
        quantiles(*args, **kwargs)


# --------------------------------------------------------------------------- #
# 3. evidence
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kwargs,expected_level,expected_bars",
    [
        # Bayes factor (Kass & Raftery)
        ({"bf": 0.4}, "none", 0),
        ({"bf": 1.0}, "weak", 1),
        ({"bf": 2.4}, "weak", 1),
        ({"bf": 3.0}, "moderate", 3),
        ({"bf": 8.5}, "moderate", 3),
        ({"bf": 10.0}, "strong", 4),
        ({"bf": 24.0}, "strong", 4),
        ({"bf": 30.0}, "decisive", 5),
        ({"bf": 42.0}, "decisive", 5),
        # p-value tiers
        ({"p": 0.35}, "none", 0),
        ({"p": 0.10}, "weak", 1),
        ({"p": 0.06}, "weak", 1),
        ({"p": 0.05}, "moderate", 3),
        ({"p": 0.02}, "moderate", 3),
        ({"p": 0.01}, "strong", 4),
        ({"p": 0.002}, "strong", 4),
        ({"p": 0.001}, "decisive", 5),
        ({"p": 0.0002}, "decisive", 5),
        # Explicit levels (including alias & uppercase)
        ({"level": "none"}, "none", 0),
        ({"level": "weak"}, "weak", 1),
        ({"level": "anecdotal"}, "weak", 1),
        ({"level": "moderate"}, "moderate", 3),
        ({"level": "STRONG"}, "strong", 4),
        ({"level": "decisive"}, "decisive", 5),
    ],
)
def test_evidence_tiers_svg_and_text(
    kwargs: dict,
    expected_level: str,
    expected_bars: int,
) -> None:
    ev = evidence(**kwargs)
    assert isinstance(ev, mc.Chip)
    assert ev.kind == "evidence"
    assert ev.data["level"] == expected_level
    assert ev.data["tier"] == expected_bars
    assert ev.compact_value == expected_level
    assert ev.text == "[" + ("▰" * expected_bars) + ("▱" * (5 - expected_bars)) + "]"
    assert ev.ascii_text == "[" + ("#" * expected_bars) + ("." * (5 - expected_bars)) + "]"
    assert ev.ascii_text.isascii()

    root = _parse_svg(ev.svg)
    rects = root.findall(".//{http://www.w3.org/2000/svg}rect")
    assert len(rects) == 5
    # Verify heights strictly ascend left-to-right
    heights = [float(r.attrib["height"]) for r in rects]
    assert all(heights[i] < heights[i + 1] for i in range(4))
    filled_rects = [r for r in rects if r.attrib.get("fill") != "none"]
    assert len(filled_rects) == expected_bars


def test_evidence_formatting_small_n_warning_dark_and_expand() -> None:
    # Well-powered strong evidence
    strong = evidence(p=0.002, n=48, label="Treatment effect", expand=_HAS_MINTFIG)
    assert strong.value_text == "strong (p=0.002, n=48)"
    assert strong.compact_value == "strong"
    assert strong.warnings == []
    assert strong.data["underpowered"] is False
    assert strong.theme.series_colors[2] in strong.svg  # teal/primary fill
    if _HAS_MINTFIG:
        assert strong.expand_explanation is not None
        panel = next(iter(strong.expand_explanation.panels.values()))
        assert panel.kind == "table"

    chip_html = strong.html(show_label=True)
    payload = _extract_chip_payload(chip_html)
    if _HAS_MINTFIG:
        assert payload["has_figure"] is True
    if _HAS_MINTFIG:
        assert "<svg" in payload["figure_svg"]

    # Bayes factor formatting
    bf_ev = evidence(bf=42)
    assert bf_ev.value_text == "decisive (BF=42)"
    assert bf_ev.compact_value == "decisive"
    assert bf_ev.to_text() == "decisive (BF=42) [▰▰▰▰▰]"
    assert bf_ev.to_text(ascii_only=True) == "decisive (BF=42) [#####]"

    # Small sample (n < 10) -> epistemic warning + amber tint (light and dark)
    low_n = evidence(p=0.004, n=6, label="Pilot", style="dark", expand=_HAS_MINTFIG)
    _parse_svg(low_n.svg)
    assert low_n.data["underpowered"] is True
    assert len(low_n.warnings) == 1
    assert "Small sample (n=6): treat as preliminary" in low_n.warnings[0]
    assert low_n.theme.series_colors[3] in low_n.svg  # amber tint in dark theme
    if _HAS_MINTFIG:
        assert low_n.expand_explanation is not None
    if _HAS_MINTFIG:
        assert "preliminary" in low_n.expand_explanation.takeaway.lower()

    # Even at tier 0 with n < 10, amber outline still signals low power
    low_n_none = evidence(bf=0.5, n=5)
    assert low_n_none.theme.series_colors[3] in low_n_none.svg
    assert any("Small sample (n=5): treat as preliminary" in w for w in low_n_none.warnings)

    # Boundary n=10 is NOT underpowered
    ok_n = evidence(p=0.02, n=10)
    assert ok_n.warnings == []
    assert ok_n.data["underpowered"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"p": -0.01},
        {"p": 1.05},
        {"p": float("nan")},
        {"p": True},
        {"bf": -1.0},
        {"bf": float("inf")},
        {"bf": False},
        {"n": 0, "p": 0.02},
        {"n": -5, "bf": 4.0},
        {"n": True, "level": "strong"},
        {"level": "overwhelming"},
        {"level": ""},
        {"level": "strong", "width": 0},
    ],
)
def test_evidence_invalid_inputs_raise_explain_error(kwargs: dict) -> None:
    with pytest.raises(mc.ChipError):
        evidence(**kwargs)
