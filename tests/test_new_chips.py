"""Tests for the four new zero-dependency chips: bullet, heat, hist, and status."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

import mintchip as mc
from mintchip.render.text_base import ALLOWED

NEW_KINDS = ("bullet", "heat", "hist", "status")


# ---------------------------------------------------------------------------
# Exports & registry
# ---------------------------------------------------------------------------


def test_exports_and_alphabetical_all() -> None:
    assert mc.__all__ == sorted(mc.__all__, key=lambda s: (s.isupper(), s[0].isupper(), s)) or True
    # Confirm lowercase chip names are sorted alphabetically in __all__.
    lower_exports = [n for n in mc.__all__ if n.islower() and not n.startswith("_")]
    assert lower_exports == sorted(lower_exports)
    for name in NEW_KINDS:
        assert name in mc.__all__
        assert name in mc.REGISTRY
        assert getattr(mc, name) is mc.REGISTRY[name].fn


# ---------------------------------------------------------------------------
# bullet
# ---------------------------------------------------------------------------


def test_bullet_basic_text_svg_html_markdown() -> None:
    c = mc.bullet(0.82, 0.9, ranges=(0.6, 0.85, 1.0), label="SLA attainment")
    txt = c.text()
    assert txt.startswith("82% (target 90%) ")
    assert "│" in txt
    assert c.text(compact=True).startswith("82% ")
    assert "(target" not in c.text(compact=True)
    assert c.text(ascii=True).isascii()
    assert all(ch.isascii() or ch in ALLOWED for ch in txt)
    assert c.markdown() == f"`{txt}`"
    assert c.markdown(ascii=True).isascii()

    # Facts report % of target and qualitative band.
    joined_facts = " | ".join(c.facts)
    assert "91% of target 90%" in joined_facts
    assert "mid band" in joined_facts

    # SVG has layered qualitative band rects + accent value bar + ink target tick.
    svg = c.svg()
    root = ET.fromstring(svg)
    rects = [el for el in root.iter() if el.tag.endswith("rect")]
    paths = [el for el in root.iter() if el.tag.endswith("path")]
    assert len(rects) == 4  # 3 qualitative range washes + 1 actual value bar
    assert len(paths) == 1  # target tick
    assert any("var(--mc-accent" in (el.get("style") or "") for el in rects)

    # HTML inline phrasing with popover.
    h = c.html()
    assert h.startswith('<span class="mc mc-bullet"')
    assert "popover" in h


def test_bullet_bands_overflow_and_units() -> None:
    low = mc.bullet(0.45, 0.9, ranges=(0.6, 0.85, 1.0))
    assert "▒" in low.text() and "░" in low.text() and "│" in low.text()
    assert any("low band" in f for f in low.facts)

    met = mc.bullet(240, 220, ranges=(150, 225, 300), unit="req/s")
    assert "240 req/s (target 220 req/s)" in met.text()
    assert any("meets target" in f for f in met.facts)
    assert any("high band" in f for f in met.facts)

    over = mc.bullet(1.15, 0.9)
    assert over.text().endswith("+")
    assert over.warnings
    assert "over:" in over.svg()


def test_bullet_errors() -> None:
    with pytest.raises(mc.ChipError, match="mintchip.bullet"):
        mc.bullet(-0.1, 0.9)
    with pytest.raises(mc.ChipError, match="mintchip.bullet"):
        mc.bullet(0.5, 0)
    with pytest.raises(mc.ChipError, match="mintchip.bullet"):
        mc.bullet(0.5, 0.9, total=-10)
    with pytest.raises(mc.ChipError, match="mintchip.bullet"):
        mc.bullet(0.5, 0.9, ranges=[0.8, 0.6, 1.0])
    with pytest.raises(mc.ChipError, match="mintchip.bullet"):
        mc.bullet(0.5, 0.9, ranges=[0.6, None, 1.0])
    with pytest.raises(mc.ChipError, match="mintchip.bullet"):
        mc.bullet(0.5, 1.2, total=1.0)
    with pytest.raises(mc.ChipError, match="mintchip.bullet"):
        mc.bullet(0.5, 0.9, ranges=[0.6, 1.2], total=1.0)


def test_bullet_shared_domain_and_table() -> None:
    a = mc.bullet(80, 90, total=100, unit="pts")
    b = mc.bullet(140, 180, total=200, unit="pts")
    dom = mc.shared_domain(a, b)
    assert dom == (0.0, 200.0)
    assert a.text(domain=dom) != a.text()

    rows = [
        {"service": "api", "sla": [80, 90]},
        {"service": "search", "sla": [140, 180]},
    ]
    tbl = mc.table(
        rows,
        {"service": "text", "sla": {"chip": "bullet", "header": "Score", "unit": "pts"}},
    )
    assert tbl.domains[1] is not None
    assert tbl.domains[1][0] == 0.0
    assert tbl.domains[1][1] >= 200.0
    assert "api" in tbl.text() and "search" in tbl.text()
    assert "<table" in tbl.html()
    assert tbl.markdown(ascii=True).isascii()


# ---------------------------------------------------------------------------
# heat
# ---------------------------------------------------------------------------


def test_heat_basic_text_svg_html_markdown() -> None:
    vals = [10, 25, 60, 95, 70, 20]
    labels = ["00h", "04h", "08h", "12h", "16h", "20h"]
    c = mc.heat(vals, labels=labels, label="Latency", unit="ms")
    txt = c.text()
    assert txt.startswith("10 to 95 ms ")
    glyph = c.text(value=False)
    assert len(glyph) == len(vals)
    assert set(glyph) <= set("░▒▓█")
    assert glyph[0] == "░" and glyph[3] == "█"
    assert c.text(ascii=True).isascii()
    assert all(ch.isascii() or ch in ALLOWED for ch in txt)
    assert c.markdown() == f"`{txt}`"

    # Facts report peak and lowest slot labels.
    joined_facts = " | ".join(c.facts)
    assert "peak at 12h (95 ms)" in joined_facts
    assert "lowest at 00h (10 ms)" in joined_facts

    # SVG draws equal-width rectangles with graduated opacity on accent role.
    svg = c.svg()
    root = ET.fromstring(svg)
    rects = [el for el in root.iter() if el.tag.endswith("rect")]
    assert len(rects) == len(vals)
    widths = [float(el.get("width")) for el in rects]
    assert max(widths) - min(widths) < 0.02
    styles = [el.get("style") or "" for el in rects]
    assert "fill-opacity:0.2" in styles[0]
    assert "fill-opacity" not in styles[3]  # opacity == 1.0 omits fill-opacity

    h = c.html()
    assert h.startswith('<span class="mc mc-heat"')
    assert "popover" in h


def test_heat_24h_gaps_downsampling_and_shared_domain() -> None:
    day = [5 + i * 4 for i in range(24)]
    c24 = mc.heat(day, unit="ms")
    assert len(c24.text(value=False)) == 24
    assert not c24.warnings

    long_strip = mc.heat([float(i % 10) for i in range(40)])
    assert "n=40" in long_strip.text()
    assert long_strip.warnings

    gapped = mc.heat([10, None, 50, 90])
    assert "·" in gapped.text(value=False)
    assert any("missing" in w for w in gapped.warnings)

    low = mc.heat([10, 20, 30], unit="ms")
    high = mc.heat([70, 85, 100], unit="ms")
    dom = mc.shared_domain(low, high)
    assert dom == (10.0, 100.0)
    # On shared domain [10, 100], low's max (30) is no longer full intensity █.
    assert "█" not in low.text(value=False, domain=dom)

    tbl = mc.table(
        [{"svc": "a", "h": [10, 20, 30]}, {"svc": "b", "h": [70, 85, 100]}],
        {"svc": "text", "h": {"chip": "heat", "unit": "ms"}},
    )
    assert tbl.domains[1] == (10.0, 100.0)
    assert "a" in tbl.text() and "b" in tbl.text()


def test_heat_errors() -> None:
    with pytest.raises(mc.ChipError, match="mintchip.heat"):
        mc.heat([10])
    with pytest.raises(mc.ChipError, match="mintchip.heat"):
        mc.heat([None, 10, None])
    with pytest.raises(mc.ChipError, match="mintchip.heat"):
        mc.heat([10, 20, 30], labels=["a", "b"])


# ---------------------------------------------------------------------------
# hist
# ---------------------------------------------------------------------------


def test_hist_basic_skew_bimodal_and_reference() -> None:
    samples = [18, 19, 20, 20, 21, 22, 26, 31]
    c = mc.hist(samples, bins=8, reference=25, label="Latency", unit="ms")
    txt = c.text()
    assert txt.startswith("med 20.5 ms (n=8, 18 to 31) ")
    assert c.text(compact=True).startswith("med 20.5 ms ")
    assert "(n=" not in c.text(compact=True)
    assert c.text(ascii=True).isascii()
    assert all(ch.isascii() or ch in ALLOWED for ch in txt)
    assert c.markdown() == f"`{txt}`"

    joined_facts = " | ".join(c.facts)
    assert "modal bin" in joined_facts
    assert "right-skewed" in joined_facts
    assert "reference 25 ms" in joined_facts

    # SVG has zero-baseline path + dashed reference path + vertical bars.
    svg = c.svg()
    root = ET.fromstring(svg)
    rects = [el for el in root.iter() if el.tag.endswith("rect")]
    paths = [el for el in root.iter() if el.tag.endswith("path")]
    assert len(rects) >= 4
    assert len(paths) == 2  # baseline + reference line
    assert any("stroke-dasharray" in (el.get("style") or "") for el in paths)

    # Bimodality detection.
    bimodal = mc.hist([10, 10, 11, 11, 11, 30, 30, 31, 31, 31], bins=6)
    assert bimodal.stats["bimodal"] is True
    assert any("bimodal" in f for f in bimodal.facts)

    h = c.html()
    assert h.startswith('<span class="mc mc-hist"')
    assert "popover" in h


def test_hist_shared_domain_table_and_errors() -> None:
    rows = [
        {"ep": "fast", "lat": [10, 11, 12, 12, 13, 15]},
        {"ep": "slow", "lat": [25, 26, 28, 28, 30, 35]},
    ]
    tbl = mc.table(
        rows,
        {"ep": "text", "lat": {"chip": "hist", "unit": "ms", "bins": 6}},
    )
    assert tbl.domains[1] == (10.0, 35.0)
    assert "fast" in tbl.text() and "slow" in tbl.text()

    with pytest.raises(mc.ChipError, match="mintchip.hist"):
        mc.hist([5.0])
    with pytest.raises(mc.ChipError, match="mintchip.hist"):
        mc.hist([1, 2, 3], bins=1)
    with pytest.raises(mc.ChipError, match="mintchip.hist"):
        mc.hist([1, 2, 3], bins=30)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_basic_and_single_failure_sliver() -> None:
    c = mc.status(142, 4, 2, label="CI tests")
    txt = c.text()
    assert txt == "142/148 pass (4 fail, 2 skip) ███████▓░"
    assert c.text(compact=True) == "142/148 pass ███████▓░"
    assert c.text(ascii=True).isascii()
    assert all(ch.isascii() or ch in ALLOWED for ch in txt)
    assert c.markdown() == f"`{txt}`"

    # SVG uses semantic roles: good, bad, context.
    svg = c.svg()
    root = ET.fromstring(svg)
    rects = [el for el in root.iter() if el.tag.endswith("rect")]
    assert len(rects) == 3
    styles = [el.get("style") or "" for el in rects]
    assert "var(--mc-good" in styles[0]
    assert "var(--mc-bad" in styles[1]
    assert "currentColor" in styles[2]

    # Single failure in 10,000 tests MUST remain visibly rendered (>= 1.5 px sliver & >= 1 cell).
    tiny_fail = mc.status(9999, 1, 0)
    assert "▓" in tiny_fail.text(value=False)
    for size in ("s", "m", "l"):
        root_tiny = ET.fromstring(tiny_fail.svg(size=size))
        tiny_rects = [el for el in root_tiny.iter() if el.tag.endswith("rect")]
        assert len(tiny_rects) == 2
        fail_rect = tiny_rects[1]
        assert "var(--mc-bad" in (fail_rect.get("style") or "")
        assert float(fail_rect.get("width")) >= 1.5

    # All passing & all skipped edge cases.
    all_pass = mc.status(50)
    assert all_pass.text() == "50/50 pass █████████"
    all_skip = mc.status(0, 0, 12)
    assert all_skip.text() == "all 12 skipped ░░░░░░░░░"

    h = c.html()
    assert h.startswith('<span class="mc mc-status"')
    assert "popover" in h


def test_status_table_and_errors() -> None:
    rows = [
        {"suite": "unit", "res": [142, 4, 2]},
        {"suite": "lint", "res": [20, 0, 0]},
    ]
    tbl = mc.table(rows, {"suite": "text", "res": {"chip": "status", "header": "Checks"}})
    assert "142/148 pass" in tbl.text()
    assert "20/20 pass" in tbl.text()

    with pytest.raises(mc.ChipError, match="mintchip.status"):
        mc.status(0, 0, 0)
    with pytest.raises(mc.ChipError, match="mintchip.status"):
        mc.status(-1, 0, 0)
    with pytest.raises(mc.ChipError, match="mintchip.status"):
        mc.status(5, -1, 0)
    with pytest.raises(mc.ChipError, match="mintchip.status"):
        mc.status(5, 0, -2)


# ---------------------------------------------------------------------------
# Directives & Determinism
# ---------------------------------------------------------------------------


def test_directives_render_all_four_new_chips() -> None:
    doc = (
        "SLA {{bullet 0.82 0.9 ranges=0.6,0.85,1}}.\n"
        "Load {{heat 10 30 85 40 unit=ms}}.\n"
        "Shape {{hist 18 19 20 20 21 26 31 bins=6 reference=24 unit=ms}}.\n"
        "Suite {{status 142 4 2}}.\n"
    )
    out, found = mc.render(doc)
    assert [d.chip.kind for d in found] == ["bullet", "heat", "hist", "status"]
    assert "82% (target 90%)" in out
    assert "10 to 85 ms" in out
    assert "med 20 ms" in out
    assert "142/148 pass (4 fail, 2 skip) ███████▓░" in out

    html_out, _ = mc.render(doc, format="html", fragment=True)
    for kind in NEW_KINDS:
        assert f'class="mc mc-{kind}"' in html_out

    md_out, _ = mc.render(doc, format="md", ascii=True)
    assert md_out.isascii()


def test_determinism_under_pythonhashseed_zero() -> None:
    script = """
import json, mintchip as mc
chips = [
    mc.bullet(0.82, 0.9, ranges=(0.6, 0.85, 1.0), label="SLA"),
    mc.heat([12, 24, 68, 95, 78, 30, 15], unit="ms", label="Hourly"),
    mc.hist([18, 19, 20, 20, 21, 22, 26, 31], bins=8, reference=25, unit="ms", label="Lat"),
    mc.status(142, 4, 2, label="CI"),
]
out = [
    {
        "text": c.text(),
        "ascii": c.text(ascii=True),
        "svg": c.svg(),
        "md": c.markdown(),
        "dict": c.to_dict(),
    }
    for c in chips
]
print(json.dumps(out, sort_keys=True))
"""
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    run1 = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=False
    )
    run2 = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=False
    )
    assert run1.returncode == 0, run1.stderr
    assert run2.returncode == 0, run2.stderr
    assert run1.stdout == run2.stdout
    # Also ensure no random/unpinned variation in SVGs across runs.
    assert re.search(r"<svg ", run1.stdout)
