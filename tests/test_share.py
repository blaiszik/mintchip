from __future__ import annotations

import re

import pytest

import mintchip as mc
from mintchip.chips.share import CELLS, MAX_SEGMENTS


def test_example_reads_as_target() -> None:
    c = mc.share({"code": 62, "docs": 28, "tests": 10})
    assert c.text() == "62·28·10% ██████▏███▏█"
    assert c.text(ascii=True) == "62/28/10% ######|###|#", "no '62.28.10' decimal look-alike"
    assert c.stats["value"] == 0.62 and not c.warnings
    assert "docs 28 (28%)" in c.facts


def test_one_hue_in_opacity_steps_largest_first() -> None:
    c = mc.share([("small", 1), ("big", 3)])
    assert c.text(value=False) == "████████▏██" and c.stats["names"] == ["big", "small"]
    svg = c.svg()
    assert "var(--mc-" not in svg, "parts are ink, never categorical colours"
    assert svg.count("<rect") == 2 and "fill-opacity:0.66" in svg
    assert len(set(re.findall(r"fill:(#\w+)", c.svg(theme="dark")))) == 1, "one hue"


def test_fold_into_other_is_announced() -> None:
    c = mc.share({"a": 40, "b": 25, "c": 15, "d": 8, "e": 7, "f": 5})
    assert c.text() == "40·25·15·20% ████▏███▏█▏██ other=3"
    assert len(c.stats["fracs"]) == MAX_SEGMENTS
    assert any("3 parts" in w and "other" in w for w in c.warnings)
    assert "other (3 parts) 20 (20%)" in c.facts
    assert "\x1b[2m██" in c.text(color=True), "the folded segment is context"
    assert not mc.share({"a": 4, "b": 3, "c": 2, "d": 1}).warnings, "four parts fit"


def test_part_under_one_cell_stays_visible() -> None:
    c = mc.share({"a": 95, "b": 4.5, "c": 0.5})
    assert c.text() == "95·4.5·0.5% ████████▏▄▏▄"
    assert sum(c.stats["cells"]) == CELLS
    assert sum("half-height" in w for w in c.warnings) == 2
    widths = [float(w) for w in re.findall(r'<rect x="[\d.]+" y="4" width="([\d.]+)"', c.svg())]
    assert min(widths) >= 1.5 and abs(sum(widths) + 3 - 67) < 0.01


def test_comparable_cell_counts() -> None:
    for parts in ({"a": 1}, {"a": 1, "b": 1}, {"a": 5, "b": 3, "c": 1, "d": 1}):
        assert sum(mc.share(parts).stats["cells"]) == CELLS
    assert mc.share({"all": 3}).text() == "100% ██████████"


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match="at least 1 part") as e:
        mc.share({})
    assert e.value.fix_hint
    with pytest.raises(mc.ChipError, match="positive"):
        mc.share({"a": 3, "b": 0})
    with pytest.raises(mc.ChipError, match="one size"):
        mc.share({"a": (0, 1)})


def test_sort_false_keeps_the_given_order_and_shades_by_position() -> None:
    c = mc.share({"tests": 10, "docs": 28, "code": 62}, sort=False)
    assert c.text() == "10·28·62% █▏███▏██████"
    assert c.stats["names"] == ["tests", "docs", "code"]
    opacities = re.findall(r"fill-opacity:([\d.]+)", c.svg())
    assert opacities == ["0.66", "0.44"], "first part full ink, then the steps, by position"
    assert mc.from_dict(c.to_dict()).text() == c.text() and c.to_dict()["sort"] is False
    assert "sort" not in mc.share({"a": 1, "b": 2}).to_dict(), "the default is left out"
    folded = mc.share({"a": 1, "b": 2, "c": 3, "d": 4, "e": 50}, sort=False)
    assert folded.stats["names"][:3] == ["a", "b", "c"], "the first three, not the largest"
