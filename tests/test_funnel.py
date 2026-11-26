from __future__ import annotations

import re

import pytest

import mintchip as mc

STAGES = {"visited": 1200, "signed up": 520, "activated": 350, "retained": 290}


def test_example_prints_counts_and_retention() -> None:
    c = mc.funnel(STAGES)
    assert c.text() == "1,200 → 520 → 350 → 290 (24%)"
    assert c.text(ascii=True) == "1,200 -> 520 -> 350 -> 290 (24%)"
    assert c.text(compact=True) == "1,200 → 290 (24%)"
    assert c.stats["value"] == pytest.approx(290 / 1200) and not c.warnings
    assert "steepest drop: visited → signed up, 57% lost (680)" in c.facts


def test_steepest_drop_is_the_one_accent_bar() -> None:
    svg = mc.funnel(STAGES).svg()
    assert svg.count("<rect") == 4 and svg.count("var(--mc-accent") == 1
    heights = [float(h) for h in re.findall(r'height="([\d.]+)"', svg)]
    assert heights == sorted(heights, reverse=True), "bars descend with the counts"
    rate = mc.funnel({"a": 1000, "b": 400, "c": 300, "d": 30})
    assert rate.stats["steepest"] == 3, "steepest by fraction lost, not by count"


def test_non_monotonic_is_announced() -> None:
    c = mc.funnel({"a": 1200, "b": 520, "c": 600, "d": 290})
    assert c.text() == "1,200 → 520 → 600! → 290 (24%)"
    assert c.text(compact=True) == c.text(), "compact keeps the mark"
    assert any("'c' (600) is larger than 'b' (520)" in w for w in c.warnings)
    assert c.svg().count("<rect") == 3 and c.svg().count("<path") == 1, "the rise is outlined"


def test_fractional_counts_and_an_empty_stage() -> None:
    c = mc.funnel({"a": 10.5, "b": 3.2, "c": 0})
    assert c.text() == "10.5 → 3.2 → 0 (0%)" and c.stats["value"] == 0.0
    assert "stroke-opacity:0.45" in c.svg(), "an empty stage is a context floor"
    assert "stage conversion 30%, 0%" in c.facts


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match="at least 2 stages.*Fix:"):
        mc.funnel({"a": 10})
    with pytest.raises(mc.ChipError, match="zero or more.*Fix:"):
        mc.funnel({"a": 10, "b": -1})
    with pytest.raises(mc.ChipError, match="first stage 'a' must be positive"):
        mc.funnel({"a": 0, "b": 0})
    with pytest.raises(mc.ChipError, match=r"mintchip\.funnel: stage 'b'"):
        mc.funnel({"a": 10, "b": (1, 2)})
