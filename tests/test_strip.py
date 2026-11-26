from __future__ import annotations

import pytest

import mintchip as mc
from mintchip.chips.strip import CELLS


def test_example_reads_without_colour() -> None:
    c = mc.strip([True, True, True, "warn", True, False, True, None])
    assert c.text() == "5/8 pass (1 fail, 1 warn, 1 skip) ███▄█×█·"
    assert c.text(compact=True) == "5/8 pass ███▄█×█·"
    assert c.text(ascii=True) == "5/8 pass (1 fail, 1 warn, 1 skip) ###~#x#."
    assert c.stats["value"] == pytest.approx(5 / 8), "every item counts, skipped ones too"
    jobs = mc.strip(["pass"] * 4 + ["fail", "skip", "pass"])
    assert jobs.text() == "5/7 pass (1 fail, 1 skip) ████×·█"
    coloured = c.text(color=True)
    assert all(f"\x1b[{k}m" in coloured for k in ("32", "33", "31", "2"))


def test_svg_heights_and_colours() -> None:
    svg = mc.strip(["pass", "warn", "fail", "skip"]).svg()
    assert 'height="11"' in svg and 'height="5.5"' in svg and 'height="2"' in svg
    assert "var(--mc-good" in svg and "var(--mc-warn" in svg and "var(--mc-bad" in svg
    assert "<circle" in svg and "fill:none" in svg, "skip is a hollow ring"


def test_names_tokens_and_all_skipped() -> None:
    c = mc.strip(["PASS", "flaky", "error"], names=["unit", "e2e", "lint"])
    assert c.text(value=False) == "█▄×"
    assert "fail: lint" in c.facts and "warn: e2e" in c.facts
    assert "<title>lint: fail</title>" in c.svg()
    none = mc.strip([None, "skip"])
    assert none.text() == "all 2 skipped ··" and none.stats["value"] is None


def test_long_strip_keeps_the_worst_state() -> None:
    c = mc.strip([True] * 30 + [False] + [True] * 9)
    glyph = c.text(value=False)
    assert glyph.endswith(" n=40") and glyph.count("×") == 1
    assert len(glyph.split()[0]) == CELLS
    assert any("worst state" in w for w in c.warnings)
    assert c.svg().count("<rect") == CELLS


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match="at least 1"):
        mc.strip([])
    with pytest.raises(mc.ChipError, match="not a known state") as e:
        mc.strip(["pass", "maybe"])
    assert "'warn'" in e.value.fix_hint
    with pytest.raises(mc.ChipError, match="mintchip.spark"):
        mc.strip([0.5, 0.7])
    with pytest.raises(mc.ChipError, match="names has 1"):
        mc.strip([True, False], names=["a"])


def test_svg_fits_its_cells() -> None:
    svg = mc.strip([True, True, None]).svg()
    assert 'viewBox="0 0 26.3 16" width="1.64em"' in svg
    assert "stroke-opacity:0.6" in svg, "a skip ring is a mark, stronger than a wash"
