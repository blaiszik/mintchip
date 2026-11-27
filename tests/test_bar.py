from __future__ import annotations

import re

import pytest

import mintchip as mc


def test_example_reads_as_target() -> None:
    c = mc.bar(0.82, target=0.9)
    assert c.text() == "82% (target 90%) ██████▌│"
    assert c.text(compact=True) == "82% ██████▌│"
    assert c.text(ascii=True) == "82% (target 90%) #######|", "no eighths in ASCII"
    assert mc.bar(0.82).text() == "82% ██████▌·"
    assert "8 points short of the target 90%" in c.facts and not c.warnings
    assert c.stats["value"] == 0.82 and c.domain == (0.0, 1.0)


def test_overflow_is_marked_never_clipped_silently() -> None:
    c = mc.bar(1.4)
    assert c.text() == "140% ████████+"
    assert any("exceeds the total" in w for w in c.warnings)
    svg = c.svg()
    assert svg.count("<path") == 1 and "over: 140%" in svg, "a chevron after the bar"
    assert mc.bar(1.0).text() == "100% ████████" and not mc.bar(1.0).warnings
    assert "<path" not in mc.bar(1.0).svg()


def test_counts_baseline_and_met_target() -> None:
    c = mc.bar(412, 500, unit="tests", target=450, baseline=400)
    assert c.text() == "412/500 tests (82%, baseline 400 tests, target 450 tests) ██████▋│"
    assert c.text(compact=True) == "412/500 tests ██████▋│"
    assert "+12 tests vs baseline 400 tests" in c.facts
    met = mc.bar(0.97, target=0.9)
    assert met.text(value=False) == "███████▊", "a met target is covered by the bar"
    assert "meets the target 90%" in met.facts
    svg = mc.bar(0.5, baseline=0.4, target=0.75).svg()
    assert "stroke-opacity" not in svg and svg.count("<path") == 2, "two ink strokes"
    assert '<path d="M29.3 12L29.3 15"' in svg, "the baseline hangs under the track (4..12)"
    assert '<path d="M52.75 2L52.75 14"' in svg, "the target crosses it"
    assert mc.bar(82, 100, unit="%").text() == "82% ██████▌·"
    assert mc.bar(0).text() == "0% ········"


def test_shared_domain_compares_lengths() -> None:
    a, b = mc.bar(90, 100), mc.bar(150, 200)
    d = mc.union_domain(a.domain, b.domain)
    assert a.text(domain=d, value=False) == "███▋"
    assert b.text(domain=d, value=False) == "██████··"
    assert mc.bar(120, 100).text(domain=d, value=False) == "████▊+"


def test_validation() -> None:
    for bad, match in (
        ({"value": 0.5, "total": 0}, "total must be positive"),
        ({"value": -0.1}, "0 or more"),
        ({"value": 0.5, "target": 1.2}, "target 1.2 must lie between"),
        ({"value": 0.5, "baseline": -1}, "baseline"),
    ):
        with pytest.raises(mc.ChipError, match=match) as e:
            mc.bar(**bad)
        assert e.value.fix_hint


def test_room_for_the_chevron_only_on_overflow() -> None:
    assert 'viewBox="0 0 72 16"' in mc.bar(0.82).svg()
    track = re.search(r'<rect x="2.5" y="4" width="([\d.]+)"', mc.bar(0.82).svg())
    assert track and float(track[1]) == 67, "the track runs to the pad, no blank after it"
    over = mc.bar(1.3).svg()
    assert 'viewBox="0 0 77 16"' in over and 'y="4" width="67"' in over, "the scale is kept"
    assert mc.bar(0.8).warnings_for((0, 0.5))[0].startswith("domain 0% to 50% cuts the bar")


def test_percent_near_the_ends_is_never_rounded_onto_them() -> None:
    assert mc.bar(1840, 1850).text() == "1,840/1,850 (99.5%) ████████"
    assert mc.bar(0.995).text(compact=True) == "99.5% ████████"
    assert mc.bar(0.99999).text(compact=True).startswith("99.9%")
    assert mc.bar(0.0004).text(compact=True).startswith("0.04%")
    assert mc.bar(0.004).facts[0] == "0.4% of the whole"
    assert mc.bar(1).text(compact=True).startswith("100% ")
    assert mc.bar(0).text(compact=True).startswith("0% ")
    t = mc.table([{"a": 0.995}, {"a": 0.5}], {"a": "bar"}).text()
    assert "99.5%" in t and "50.0%" in t, "the column takes the one decimal"


def test_percent_option_overrides_default_mode() -> None:
    c = mc.bar(1, 1, percent=False)
    assert c.text() == "1/1 (100%) ████████"
    assert c.text(compact=True) == "1/1 ████████"
    assert c.to_dict()["percent"] is False
    assert mc.from_dict(c.to_dict()).text() == c.text()

    p = mc.bar(38, 40, percent=True)
    assert p.text() == "95% ███████▋"
    assert p.to_dict()["percent"] is True
    assert "percent" not in mc.bar(0.82).to_dict(), "default omits percent from spec"
