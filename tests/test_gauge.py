from __future__ import annotations

import re

import pytest

import mintchip as mc


def test_example_reads_as_target() -> None:
    c = mc.gauge(7.38, (7.35, 7.45))
    assert c.text() == "7.38 (normal 7.35 to 7.45) [···├●───┤··]"
    assert c.text(compact=True) == "7.38 [···├●───┤··]"
    assert c.text(ascii=True) == "7.38 (normal 7.35 to 7.45) [...(*---)..]"
    assert c.stats["status"] == "normal" and not c.warnings
    assert "\x1b[32m●" in c.text(color=True)
    assert "var(--mc-good" in c.svg() and "var(--mc-bad" not in c.svg()


def test_colour_follows_position() -> None:
    warn = (7.3, 7.5)
    high = mc.gauge(7.52, (7.35, 7.45))
    assert high.text() == "7.52 (high; normal 7.35 to 7.45) [··├───┤·●··]"
    assert high.stats["status"] == "high" and "var(--mc-bad" in high.svg()
    caution = mc.gauge(7.48, (7.35, 7.45), warn=warn)
    assert caution.text(value=False) == "[··│├───┤●··]"
    assert "var(--mc-warn" in caution.svg() and "inside the warn range" in caution.alt
    low = mc.gauge(7.1, (7.35, 7.45), warn=warn)
    assert low.text(compact=True) == "7.10 [·●···│├─┤│·]" and low.stats["status"] == "low"
    assert "0.25 below the normal range" in low.facts


def test_shared_domain_and_cut() -> None:
    a, b = mc.gauge(72, (60, 100), unit="bpm"), mc.gauge(118, (60, 100), unit="bpm")
    d = mc.shared_domain(a, b)
    ga, gb = a.text(domain=d, value=False), b.text(domain=d, value=False)
    assert len(ga) == len(gb) == 13
    assert ga.index("├") == gb.index("├"), "one scale: the normal band lines up"
    cut = mc.gauge(7.38, (7.35, 7.45), domain=(7.4, 7.6))
    assert cut.text(value=False).startswith("<●") and any("cuts" in w for w in cut.warnings)
    assert cut.svg().count("<path") == 2, "the band and an edge chevron"


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match="lo < hi") as e:
        mc.gauge(1, (2, 2))
    assert e.value.fix_hint
    with pytest.raises(mc.ChipError, match="must contain normal"):
        mc.gauge(7.4, (7.35, 7.45), warn=(7.4, 7.5))
    with pytest.raises(mc.ChipError, match="lo 2.0 > hi 1.0"):
        mc.gauge(1, (2, 1))


def test_precision_and_fit() -> None:
    assert mc.gauge(7.384, (7.35, 7.45)).value() == "7.384 (normal 7.350 to 7.450)"
    assert mc.gauge(7.38, (7.35, 7.45)).value() == "7.38 (normal 7.35 to 7.45)"
    band = re.search(r'<path d="M([\d.]+) 8L([\d.]+) 8"', mc.gauge(7.38, (7.35, 7.45)).svg())
    assert band and float(band[1]) < 6 and float(band[2]) > 66, "the band spans a lone gauge"
