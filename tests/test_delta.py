from __future__ import annotations

import re

import pytest

import mintchip as mc


def test_example_reads_as_target() -> None:
    c = mc.delta(0.74, 0.82)
    assert c.text() == "0.74→0.82 (+0.08) [··○────●··]"
    assert c.text(compact=True) == "0.74→0.82 [··○────●··]"
    assert c.text(ascii=True) == "0.74->0.82 (+0.08) [..o----*..]"
    assert c.stats["value"] == pytest.approx(0.08) and not c.warnings
    assert "▶" not in c.text(), "no arrowhead glyph: hollow-then-solid carries direction"


def test_ink_only_unless_a_direction_is_declared() -> None:
    plain = mc.delta(0.74, 0.82)
    assert "var(--mc-" not in plain.svg() and "\x1b[3" not in plain.text(color=True)
    up = mc.delta(0.74, 0.82, higher_is_better=True)
    assert "var(--mc-good" in up.svg() and "\x1b[32m" in up.text(color=True)
    worse = mc.delta(20.3, 24.1, unit="ms", higher_is_better=False)
    assert worse.text() == "20.3→24.1 ms (+3.8 ms) [··○────●··]"
    assert "var(--mc-bad" in worse.svg() and "lower is better" in worse.facts


def test_decrease_and_unchanged() -> None:
    down = mc.delta(0.82, 0.74)
    assert down.text() == "0.82→0.74 (−0.08) [··●────○··]"
    assert down.text(ascii=True).startswith("0.82->0.74 (-0.08)")
    same = mc.delta(0.82, 0.82, higher_is_better=True)
    assert same.text() == "0.82→0.82 (±0) [····●·····]" and same.facts[0] == "unchanged"
    assert "var(--mc-" not in same.svg(), "no change, no verdict"
    svg = mc.delta(0.82, 0.74).svg()
    ring = re.search(r'<circle cx="[\d.]+" cy="8" r="2.5" style="fill:none', svg)
    assert ring, "the start is a hollow ring"
    assert re.findall(r'<path d="([^"]+)"', svg)[1].count("M") == 1, "line stops at the ring"


def test_shared_domain_and_cut() -> None:
    a, b = mc.delta(0.74, 0.82), mc.delta(0.50, 0.60)
    d = mc.shared_domain(a, b)
    assert a.text(domain=d, value=False) == "[······○─●·]"
    assert b.text(domain=d, value=False) == "[·○─●······]"
    cut = mc.delta(0.74, 0.82, domain=(0.76, 0.9))
    assert cut.text(value=False).startswith("<○") and any("cuts" in w for w in cut.warnings)
    assert cut.svg().count("<path") == 3, "axis, line and a chevron"
    assert mc.from_dict(cut.to_dict()).text() == cut.text()


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match=r"mintchip\.delta: after .*Fix: Pass after="):
        mc.delta(0.74, None)
    with pytest.raises(mc.ChipError, match="empty domain"):
        mc.delta(0.74, 0.82, domain=(1, 1))
    with pytest.raises(mc.ChipError, match="higher_is_better"):
        mc.delta(0.74, 0.82, higher_is_better="yes")


def test_precision_resolves_the_change() -> None:
    assert mc.delta(0.744, 0.821).value() == "0.744→0.821 (+0.077)"
    assert mc.delta(0.74, 0.82).value() == "0.74→0.82 (+0.08)"
    assert mc.delta(1, 2).warnings_for((0, 1.5))[0].startswith("domain 0 to 1.5 cuts")
