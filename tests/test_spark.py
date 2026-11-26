from __future__ import annotations

import re

import pytest

import mintchip as mc
from mintchip.chips.spark import BAND_H, CELLS
from mintchip.render.svg_base import BAND_OPACITY, WASH_OPACITY


def test_single_spike_survives_downsampling() -> None:
    c = mc.spark([1.0] * 20 + [50.0] + [1.0] * 20)
    glyph = c.text(value=False)
    assert "█" in glyph and glyph.count("▁") == CELLS - 1
    assert glyph.endswith(" n=41") and any("41 points" in w for w in c.warnings)
    assert "#" in c.text(ascii=True)


def test_shared_domain_shows_level_differences() -> None:
    a, b = mc.spark([1, 2, 3, 4]), mc.spark([100, 200, 300, 400])
    assert a.text(value=False) == b.text(value=False), "each on its own scale"
    d = mc.shared_domain(a, b)
    assert a.text(domain=d, value=False) != b.text(domain=d, value=False)
    assert a.text(domain=d, value=False) == "▁▁▁▁"
    assert mc.spark([1, 2, 3, 4], domain=d).text() == a.text(domain=d)


def test_full_value_states_the_range_compact_does_not() -> None:
    p95 = mc.spark([212, 208, 215, 240, 310, 290, 225, 214], unit="ms")
    assert p95.text() == "214 ms (range 208 to 310) ▁▁▁▃█▇▂▁"
    assert p95.text(compact=True) == "214 ms ▁▁▁▃█▇▂▁"
    assert mc.spark([0.9, 0.6], vs=[0.8, 0.7]).text().startswith("0.6 vs 0.7 "), "vs adds nothing"
    assert mc.spark([5, 5, 5]).text() == "5 ▅▅▅", "a flat series has no range to state"


def test_a_narrow_band_is_drawn_tall_enough_to_see() -> None:
    svg = mc.REGISTRY["spark"].example_chip().svg()
    band = re.search(r'<rect x="[\d.]+" y="([\d.]+)" width="[\d.]+" height="([\d.]+)"', svg)
    assert band and float(band[2]) == BAND_H, "0.38-0.48 is 0.75 units true; drawn at BAND_H"
    true_mid = 13.5 - (0.43 - 0.38) / (1.84 - 0.38) * 11
    assert abs(float(band[1]) + BAND_H / 2 - true_mid) < 0.01, "about the band's true centre"
    assert f"fill-opacity:{BAND_OPACITY}" in svg
    wide = mc.spark([1, 2, 3], band=(1.5, 2.5)).svg()
    assert f"fill-opacity:{WASH_OPACITY}" in wide, "a band tall enough keeps the light wash"


def test_low_variation_is_announced() -> None:
    c = mc.spark([0.4200, 0.4201, 0.4203, 0.4204, 0.4206])
    assert c.text() == "0.4206 (range 0.4200 to 0.4206) ▁▂▅▆█ ±0.071%"
    assert c.text(ascii=True).endswith("+/-0.071%")
    assert any("±0.071%" in w for w in c.warnings)
    assert c.svg().count("<path") == 3, "two axis-break slashes and the line"
    assert "±" not in c.text(domain=(0, 1)), "an imposed wide domain is not zoomed"


def test_vs_runs_in_context_on_one_scale() -> None:
    c = mc.spark([1.4, 1.05, 0.8, 0.62], vs=[1.42, 1.1, 0.88, 0.74])
    assert c.text() == "0.62 vs 0.74 █▅▃▁ █▅▃▂"
    assert c.text(compact=True) == "0.62 █▅▃▁ █▅▃▂"
    assert "\x1b[2m" in c.text(color=True)
    with pytest.raises(mc.ChipError, match="same length"):
        mc.spark([1, 2, 3], vs=[1, 2])


def test_gaps_band_reference_and_direction() -> None:
    c = mc.spark([3, 2, None, 1], band=(0, 4), reference=2, higher_is_better=False)
    assert "·" in c.text()
    svg = c.svg()
    assert "fill-opacity:0.16" in svg and "stroke-dasharray" in svg
    assert "var(--mc-good" in svg and "var(--mc-accent" not in svg
    assert "var(--mc-bad" in mc.spark([1, 2], higher_is_better=False).svg()
    assert "var(--mc-accent" in mc.spark([1, 2]).svg()


def test_domain_that_cuts_data_is_marked() -> None:
    c = mc.spark([0.6, 0.7, 0.9], domain=(0.6, 0.8))
    assert c.text().endswith("^") and any("cuts 1 value" in w for w in c.warnings)
    assert c.svg().count("<path") == 2, "the line and a chevron"
    assert mc.spark([0.6, 0.7, 0.9]).text(domain=(0.7, 0.8), value=False).startswith("v")


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match="at least 2"):
        mc.spark([1.0, None, float("nan")])
    with pytest.raises(mc.ChipError, match="band"):
        mc.spark([1, 2], band=(1, 1))
    with pytest.raises(mc.ChipError, match="domain"):
        mc.spark([1, 2], domain=(1, 1))
    assert mc.spark([5, 5, 5]).text() == "5 ▅▅▅"
