from __future__ import annotations

import re

import pytest

import mintchip as mc
from mintchip.chips.dist import CELLS, DOTS

TEN = [18.9, 19.4, 19.8, 20.1, 20.3, 20.3, 20.9, 21.6, 22.8, 47.8]


def test_outlier_is_clipped_not_flattening_the_scale() -> None:
    c = mc.dist(TEN, unit="ms")
    assert c.text() == "med 20.3 ms (n=10, IQR 19.9 to 21.4) [▃▃▃█·▃▃··▃]→47.8"
    assert c.text(compact=True) == "med 20.3 ms [▃▃▃█·▃▃··▃]→47.8"
    assert c.text(ascii=True).endswith("[---#.--..-]->47.8")
    assert c.domain[1] < 25, "47.8 stays off the natural scale"
    assert any("3×IQR" in w and "47.8" in w for w in c.warnings)
    svg = c.svg()
    assert svg.count("<path") == 8 + 1, "eight ticks for nine samples, the outlier clipped"
    assert "above the scale, to 47.8 ms" in svg, "an edge chevron names the clipped value"


def test_low_and_high_outliers_and_reference() -> None:
    c = mc.dist([1.2, 1.3, 1.1, 1.4, 1.25, -6.0, 1.35, 1.2, 9.5, 1.3], reference=1.0)
    glyph = c.text(value=False)
    assert glyph.startswith("−6→[│") and glyph.endswith("]→9.5")
    assert c.text(ascii=True, value=False).startswith("-6->[|")
    assert c.svg().count("stroke-width:1.25") == 2, "two chevrons"
    assert "stroke-dasharray" in c.svg()
    two = mc.dist([1, 2, 3, 4, 5, 6, 7, 8, 90, 100]).text(value=False)
    assert two.endswith("]→90..100")


def test_threshold_gives_exceedance_probability() -> None:
    c = mc.dist(TEN, threshold=21, unit="ms")
    assert c.text(compact=True).startswith("P>21 ms 30% [")
    assert c.text().startswith("P>21 ms 30% (3 of 10) [")
    assert c.stats["value"] == pytest.approx(0.3)
    assert len(c.text(value=False).split("]")[0]) == CELLS + 2, "│ inserted at the threshold"
    assert "\x1b[34m" in c.text(color=True), "cells past the threshold in accent"
    svg = c.svg()
    assert svg.count("var(--mc-accent") == 2, "21.6 and 22.8; 47.8 is clipped"
    assert "3 of 10 samples above 21 ms (30%)" in c.facts


def test_quantile_dotplot_above_twenty_samples() -> None:
    xs = [10 + (i % 17) * 0.5 + (i % 5) * 0.1 for i in range(200)]
    c = mc.dist(xs)
    assert c.stats["n"] == 200 and len(c.stats["quantiles"]) == DOTS
    assert c.svg().count("<circle") == DOTS
    assert not re.search(r'cy="-', c.svg()), "stacks stay inside the line"


def test_few_samples_draw_a_rug_with_the_median_marked() -> None:
    svg = mc.dist(TEN, unit="ms").svg()
    ticks = [float(w) for w in re.findall(r"stroke-width:([\d.]+)", svg) if w != "1.25"]
    assert len(ticks) == 8, "9 samples on the scale, the two 20.3s sharing one tick"
    assert max(ticks) == 3, "a tie is a tick twice as wide"
    assert svg.count("<circle") == 1 and "median 20.3 ms" in svg, "one accent dot: the median"
    assert re.search(r"<circle[^>]*mc-accent", svg)
    same = mc.dist([5.0] * 10).svg()
    assert same.count("<path") == 1 and "stroke-width:4.5" in same, "all equal: one heavy tick"
    assert mc.dist([1, 2, 3]).svg().count("<path") == 3
    assert mc.dist(TEN, threshold=21).svg().count("<circle") == 0, "the value is P, not the median"


def test_shared_domain_and_explicit_domain() -> None:
    a, b = mc.dist([1, 2, 3, 4]), mc.dist([11, 12, 13, 14])
    assert a.text(value=False) == b.text(value=False), "each on its own scale"
    d = mc.shared_domain(a, b)
    ga, gb = a.text(domain=d, value=False), b.text(domain=d, value=False)
    assert len(ga) == len(gb) == CELLS + 2 and ga != gb
    assert ga.endswith("····]") and gb.startswith("[····")
    cut = mc.dist(TEN, domain=(19, 22))
    assert any("domain" in w and "cuts 3" in w for w in cut.warnings)
    assert cut.text(value=False).startswith("18.9→[")


def test_validation_and_missing() -> None:
    with pytest.raises(mc.ChipError, match="at least 2") as e:
        mc.dist([1.0, None])
    assert e.value.fix_hint
    with pytest.raises(mc.ChipError, match="domain"):
        mc.dist([1, 2], domain=(1, 1))
    c = mc.dist([1, 2, float("nan"), None, 3])
    assert c.stats["n"] == 3 and any("2 missing" in w for w in c.warnings)
    assert mc.dist([5, 5, 5, 5]).text() == "med 5 (n=4, IQR 5 to 5) [·····█····]"


def test_precision_and_warnings_for_a_shared_domain() -> None:
    assert mc.dist([0.1234, 0.124, 0.1255, 0.127, 0.1299, 0.13]).value(compact=True) == (
        "med 0.1263"
    )
    a = mc.dist([18.9, 19.4, 19.8, 20.1, 20.3, 20.3, 20.9, 21.6, 22.8, 47.8], unit="ms")
    assert a.warnings and a.warnings_for(None) == a.warnings
    assert a.warnings_for((15, 50)) == (), "a shared scale brings the outlier back"
    cut = mc.dist([30, 40, 45, 50, 55]).warnings_for((40, 50))
    assert len(cut) == 1 and cut[0].startswith("domain 40 to 50 cuts 2 sample(s) (30, 55)")
