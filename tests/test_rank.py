from __future__ import annotations

import pytest

import mintchip as mc

FIELD = [0.71, 0.80, 0.85, 0.91, 0.60]


def test_example_reads_as_target() -> None:
    c = mc.rank(2, 18)
    assert c.text() == "#2/18 [········●·]" and c.text(ascii=True) == "#2/18 [........*.]"
    assert c.stats["value"] == 2.0 and c.domain is None
    assert "right end is best (#1); left end is last" in c.facts
    assert "1 ahead, 16 behind" in c.facts
    assert c.text(domain=(0, 5)) == c.text(), "the order ruler is a fixed scale"


def test_ends_of_the_field() -> None:
    assert mc.rank(1, 18).text(value=False) == "[·········●]"
    assert mc.rank(18, 18).text(value=False) == "[●·········]"
    assert mc.rank(1, 1).text() == "#1/1 [·········●]"
    assert "alone in the field" in mc.rank(1, 1).facts


def test_from_values_on_a_value_ruler() -> None:
    c = mc.rank(values=FIELD, value=0.85)
    assert c.text() == "#2/5 (0.85) [·······●··]" and c.text(compact=True) == "#2/5 [·······●··]"
    assert c.domain == (0.60, 0.91)
    low = mc.rank(values=FIELD, value=0.85, higher_is_better=False)
    assert low.text() == "#4/5 (0.85) [··●·······]", "mirrored: the best end stays right"
    assert "right end is best (lowest value); ruler runs 0.91 to 0.6" in low.facts
    tie = mc.rank(values=[1, 2, 2, 3], value=2)
    assert tie.stats["position"] == 2 and "tied with 1 other(s) at #2" in tie.facts


def test_shared_domain_compares_fields() -> None:
    a = mc.rank(values=FIELD, value=0.85)
    b = mc.rank(values=[0.2, 0.5, 0.6], value=0.6)
    d = mc.shared_domain(a, b)
    assert a.text(domain=d, value=False) == "[········●·]"
    assert b.text(domain=d, value=False) == "[·····●····]"
    assert b.text(value=False) == "[·········●]", "alone, each field fills its ruler"
    assert a.text(domain=(0.0, 0.8), value=False).endswith("●>"), "a cut is marked"


def test_value_missing_from_values_is_announced() -> None:
    c = mc.rank(values=[0.71, 0.80, 0.91], value=0.86)
    assert c.text().startswith("#2/4") and any("not in values" in w for w in c.warnings)


def test_validation() -> None:
    with pytest.raises(mc.ChipError, match="not both.*Fix:"):
        mc.rank(2, 18, values=FIELD, value=0.8)
    with pytest.raises(mc.ChipError, match="got neither"):
        mc.rank()
    with pytest.raises(mc.ChipError, match="both position and total"):
        mc.rank(2)
    with pytest.raises(mc.ChipError, match="between 1 and total.*Fix:"):
        mc.rank(19, 18)
    with pytest.raises(mc.ChipError, match="both values= and value="):
        mc.rank(values=FIELD)
    with pytest.raises(mc.ChipError, match="at least 2"):
        mc.rank(values=[None], value=1.0)
    with pytest.raises(mc.ChipError, match="only to values="):
        mc.rank(2, 18, higher_is_better=False)
