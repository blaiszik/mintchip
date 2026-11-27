from __future__ import annotations

import re

import pytest

import mintchip as mc
from mintchip.chips.timeline import CELLS


def test_example_reads_as_target() -> None:
    c = mc.timeline({"fetch": 1.2, "solve": 4.8, "write": 1.5})
    assert c.text() == "7.5 s (solve 64%) ██▏██████▏██"
    assert c.text(compact=True) == "7.5 s ██▏██████▏██"
    assert c.text(ascii=True) == "7.5 s (solve 64%) ##|######|##"
    assert c.stats["value"] == 7.5 and not c.warnings
    assert "\x1b[34m██████" in c.text(color=True), "the longest phase is accent"
    svg = c.svg()
    assert svg.count("<rect") == 3 and svg.count("var(--mc-accent") == 1


def test_idle_time_is_empty_track() -> None:
    c = mc.timeline({"fetch": (0, 1), "solve": (3, 7), "write": (8, 10)})
    assert c.text() == "10 s (solve 40%) █···█████·██"
    assert len(c.text(value=False)) == CELLS
    assert "idle 3 s (30%)" in c.facts
    assert c.svg().count("stroke-opacity:0.6") == 2, "two idle stretches as context track"


def test_overlap_is_stacked_in_svg_and_announced_in_text() -> None:
    c = mc.timeline({"fetch": (0, 1.2), "compile": (0.8, 5.6), "test": (5.6, 7.5)})
    assert c.text() == "7.5 s (compile 64%) █▏██████▏███ overlap 0.4 s"
    assert c.stats["lanes"] == [0, 1, 0]
    assert any("overlap for 0.4 s" in w for w in c.warnings)
    heights = set(re.findall(r'height="([\d.]+)"', c.svg().split("</desc>")[1]))
    assert heights == {"4.5"}, "two lanes"
    with pytest.raises(mc.ChipError, match="at most 3") as e:
        mc.timeline({"a": (0, 4), "b": (1, 4), "c": (2, 4), "d": (3, 4)})
    assert e.value.fix_hint


def test_phase_under_one_cell_stays_visible() -> None:
    c = mc.timeline({"a": 10, "b": 0.05, "c": 3})
    assert c.text(value=False) == "███████▏▄▏██"
    assert len(c.text(value=False)) == CELLS
    assert any("'b'" in w and "half-height" in w for w in c.warnings)
    assert 'height="4"' in c.svg(), "a half-height bar in SVG too"


def test_unit_and_order() -> None:
    c = mc.timeline({"late": (5, 6), "early": (0, 5)}, unit="ms")
    assert c.text() == "6 ms (early 83%) █████████▏██"
    assert c.stats["names"] == ["early", "late"], "spans are drawn in time order"
    assert mc.timeline({"only": 2}).text() == "2 s (only 100%) ████████████"


def test_constant_bar_width_across_phase_counts() -> None:
    for n in (1, 2, 3, 4, 5, 6, 7, 10):
        stages = {f"p{i}": 1.0 for i in range(n)}
        assert len(mc.timeline(stages).text(value=False)) == CELLS
    tbl = mc.table(
        [
            {"run": "single", "t": {"all": 5.0}},
            {"run": "five", "t": {"a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0, "e": 1.0}},
        ],
        {"run": "text", "t": "timeline"},
    )
    bars = [r[1].text(value=False) for r in tbl.rows]
    assert len(bars[0]) == len(bars[1]) == CELLS


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match="all durations or all") as e:
        mc.timeline({"a": 1, "b": (1, 2)})
    assert e.value.fix_hint
    with pytest.raises(mc.ChipError, match="positive time"):
        mc.timeline({"a": 1, "b": 0})
    with pytest.raises(mc.ChipError, match="at least 1"):
        mc.timeline({})
    with pytest.raises(mc.ChipError, match="at most 10"):
        mc.timeline({f"p{i}": 1 for i in range(11)})
