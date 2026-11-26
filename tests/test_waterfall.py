from __future__ import annotations

import re

import pytest

import mintchip as mc
from mintchip.chips.waterfall import SVG_BARS, TEXT_TERMS

STEPS = {"retrieval": 0.13, "reranker": 0.08, "latency cap": -0.02}


def test_example_prints_the_arithmetic() -> None:
    c = mc.waterfall(STEPS, start=0.63)
    assert c.text() == "0.63 +0.13 +0.08 −0.02 = 0.82"
    assert c.text(ascii=True) == "0.63 +0.13 +0.08 -0.02 = 0.82"
    assert c.text(compact=True) == "0.63→0.82 (+0.19)"
    assert c.text(value=False) == "" and c.stats["value"] == pytest.approx(0.82)
    assert "largest step: retrieval +0.13" in c.facts and not c.warnings


def test_zero_start_units_and_zero_steps() -> None:
    c = mc.waterfall({"q1": 5, "q2": -8, "q3": 2}, unit="k")
    assert c.text() == "+5 −8 +2 = −1 k" and c.text(compact=True) == "−1 k (3 steps)"
    assert mc.waterfall({"a": 0, "b": 0}, start=2).text() == "2 ±0 ±0 = 2"


def test_many_steps_fold_into_one_summed_term() -> None:
    steps = {"a": 0.13, "b": 0.08, "c": -0.02, "d": 0.01, "e": -0.005, "f": 0.002, "g": 0.03}
    c = mc.waterfall(steps, start=0.63)
    assert c.text() == "0.630 +0.130 +0.080 +0.030 −0.013 (4 others) = 0.857"
    assert len(c.stats["text_terms"]) == TEXT_TERMS
    assert any("3 largest of 7 steps" in w for w in c.warnings)
    many = mc.waterfall({f"s{i}": (-1) ** i * (i + 1) for i in range(20)})
    assert many.svg().count("<rect") == SVG_BARS
    assert any("SVG draws" in w for w in many.warnings)


def test_bridge_is_ink_unless_direction_declared() -> None:
    svg = mc.waterfall(STEPS, start=0.63).svg()
    assert svg.count("<rect") == 3 and "var(--mc-" not in svg
    tops = [float(y) for y in re.findall(r'<rect x="[\d.]+" y="([\d.]+)"', svg)]
    assert tops[0] > tops[1], "a rising step sits higher than the one before"
    good = mc.waterfall(STEPS, start=0.63, higher_is_better=True).svg()
    assert good.count("var(--mc-good") == 2 and good.count("var(--mc-bad") == 1
    assert "2 step(s) help, 1 hurt" in mc.waterfall(STEPS, higher_is_better=True).facts[-1]


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match="at least 1 step.*Fix:"):
        mc.waterfall({})
    with pytest.raises(mc.ChipError, match="one signed number.*Fix:"):
        mc.waterfall({"a": (0.1, 0.2)})
    with pytest.raises(mc.ChipError, match=r"mintchip\.waterfall: start"):
        mc.waterfall(STEPS, start=float("nan"))
