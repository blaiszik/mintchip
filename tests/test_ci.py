from __future__ import annotations

import re

import pytest

import mintchip as mc


def test_example_reads_as_target() -> None:
    c = mc.ci(0.08, (0.05, 0.11), level=0.95)
    assert c.text() == "+0.08 (95% CI +0.05 to +0.11) [·│···├─●─┤·]"
    assert c.text(compact=True) == "+0.08 [·│···├─●─┤·]"
    assert c.text(ascii=True) == "+0.08 (95% CI +0.05 to +0.11) [.|...(-*-).]"
    assert "excludes the reference 0" in c.facts and not c.warnings


def test_crossing_the_reference_is_hollow_in_text_and_svg() -> None:
    c = mc.ci(0.02, (-0.01, 0.05), level=0.9)
    assert "○" in c.text() and "┼" in c.text() and "●" not in c.text()
    svg = c.svg()
    ring = re.search(r'<circle cx="([\d.]+)" cy="8" r="2.5" style="fill:none', svg)
    assert ring, "hollow dot is a ring with fill:none"
    whisker = re.findall(r'<path d="([^"]+)"', svg)[1]
    assert whisker.count("M") == 2, "the whisker stops at the ring's edge"


def test_shared_domain_and_cut_interval() -> None:
    a = mc.ci(0.08, (0.05, 0.11), level=0.95)
    b = mc.ci(0.01, (-0.02, 0.04), level=0.95)
    d = mc.shared_domain(a, b)
    assert len(a.text(domain=d, value=False)) == len(b.text(domain=d, value=False)) == 13
    cut = a.text(domain=(0.06, 0.1), value=False)
    assert cut.startswith("<") and cut.endswith(">") and "├" not in cut
    assert a.svg(domain=(0.06, 0.1)).count("<path") >= 3
    w = mc.ci(0.08, (0.05, 0.11), level=0.95, domain=(0.06, 0.1)).warnings
    assert any("cuts" in x for x in w)


def test_options() -> None:
    c = mc.ci(20.3, (19.1, 21.4), level=0.95, reference=None, unit="ms", inner=(19.8, 20.9))
    assert c.text() == "20.3 ms (95% CI 19.1 to 21.4) [·├───●───┤·]"
    assert "stroke-width:3.5" in c.svg()
    assert mc.from_dict(c.to_dict()).args["reference"] is None
    assert any("level" in w for w in mc.ci(0.1, (0.0, 0.2)).warnings)


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match="level"):
        mc.ci(0.1, (0.0, 0.2), level=95)
    with pytest.raises(mc.ChipError, match="inner"):
        mc.ci(0.1, (0.0, 0.2), inner=(0.1, 0.3))
    with pytest.raises(mc.ChipError, match="lo 0.2 > hi 0.0"):
        mc.ci(0.1, (0.2, 0.0))
    assert any("outside its interval" in w for w in mc.ci(0.5, (0.0, 0.2), level=0.9).warnings)


def test_precision_keeps_the_digits_the_interval_needs() -> None:
    assert mc.ci(0.031, (0.012, 0.050), level=0.95).value() == "+0.031 (95% CI +0.012 to +0.050)"
    assert mc.ci(1.2, (-0.6, 3.0), unit="pts").value() == "+1.2 pts (−0.6 to +3.0)"
    assert mc.ci(0, (-0.05, 0.11), level=0.95).value(compact=True) == "0.00"
    assert mc.ci(0.08, (0.05, 0.11), level=0.95).value() == "+0.08 (95% CI +0.05 to +0.11)"


def test_alone_the_svg_spans_its_marks_but_a_shared_domain_is_kept() -> None:
    c = mc.ci(0.08, (0.05, 0.11), level=0.95)
    xs = [float(x) for x in re.findall(r"M([\d.]+) ", c.svg())]
    assert min(xs) < 4 and max(xs) > 68, "no blank margin around a lone chip"
    shared = [float(x) for x in re.findall(r"M([\d.]+) ", c.svg(domain=(-0.1, 0.2)))]
    assert min(shared) > 20, "an imposed domain is drawn as given"
