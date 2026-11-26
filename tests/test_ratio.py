from __future__ import annotations

import pytest

import mintchip as mc


def test_example_reads_as_target() -> None:
    c = mc.ratio(3, 10)
    assert c.text() == "3/10 ●●●○○○○○○○"
    assert c.text(ascii=True) == "3/10 ***ooooooo"
    assert c.stats["value"] == 0.3 and not c.warnings
    assert c.alt == "3 out of 10 (30%)."


def test_small_total_is_one_icon_per_item() -> None:
    assert mc.ratio(1, 3).text() == "1/3 ●○○"
    assert mc.ratio(0, 4).text() == "0/4 ○○○○"
    svg = mc.ratio(2, 3).svg()
    assert svg.count("<circle") == 3 and svg.count("fill:none") == 1


def test_large_total_keeps_the_exact_fraction() -> None:
    c = mc.ratio(412, 1000)
    assert c.text() == "412/1,000 ●●●●○○○○○○"
    assert not c.warnings, "4.12 icons rounds to 4 without changing the fraction materially"
    assert any("each icon stands for 100" in f for f in c.facts)
    assert mc.ratio(7, 18).text() == "7/18 ●●●●○○○○○○"


def test_probability_becomes_k_in_units() -> None:
    c = mc.ratio(0.3)
    assert c.text() == "30% ●●●○○○○○○○" and c.facts[0] == "30%, 3 in 10"
    assert mc.ratio(0.31).text() == "31% ●●●○○○○○○○"
    assert mc.ratio(0.5, units=4).text() == "50% ●●○○"


def test_material_rounding_draws_a_partial_icon() -> None:
    for p, glyph in ((0.24, "●●·○○○○○○○"), (0.01, "·○○○○○○○○○"), (0.995, "●●●●●●●●●·")):
        c = mc.ratio(p)
        assert c.text(value=False) == glyph, p
        assert any("partial icon" in w for w in c.warnings)
    svg = mc.ratio(0.24).svg()
    assert svg.count('r="1.75"') == 1, "the partial icon is a small dot"
    assert any("partial" in w for w in mc.ratio(5, 40).warnings), "1.25 icons is material"


def test_validation() -> None:
    cases = (
        ((3,), "probability"),
        ((2.5, 10), "whole number"),
        ((11, 10), "whole number"),
        ((1, 0), "at least 1"),
        ((-0.1,), "probability"),
    )
    for args, msg in cases:
        with pytest.raises(mc.ChipError, match=msg) as e:
            mc.ratio(*args)
        assert e.value.fix_hint
    with pytest.raises(mc.ChipError, match="units"):
        mc.ratio(0.2, units=20)


def test_svg_fits_its_icons_and_rings_read_at_1x() -> None:
    svg = mc.ratio(1, 3).svg()
    assert 'viewBox="0 0 24.25 16" width="1.52em"' in svg, "no blank run after three icons"
    assert svg.count("stroke-width:1.25") == 2 and svg.count("stroke-opacity:0.6") == 2
    assert 'viewBox="0 0 71.5 16"' in mc.ratio(3, 10).svg(size="s"), "ten icons never overflow"
