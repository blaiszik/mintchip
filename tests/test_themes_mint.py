"""Tests for the zero-yellow mint-inspired themes (`mint` and `mint_dark`)."""

from __future__ import annotations

import colorsys
import re
import xml.etree.ElementTree as ET

import pytest

import mintchip as mc
from mintchip.themes import DARK_INK, LIGHT_INK, ROLES, THEMES, contrast_ratio, resolve_theme

_HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}\b")
_YELLOW_HEXES = {"#B87A00", "#C08000"}


def _is_yellow_or_amber(hex_colour: str) -> bool:
    """Return True if a saturated hex colour falls in the yellow/amber hue band (30°–80°)."""
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    hue, sat, _ = colorsys.rgb_to_hsv(r, g, b)
    hue_deg = hue * 360.0
    return sat >= 0.25 and 30.0 <= hue_deg <= 80.0


def test_resolve_mint_and_mint_dark_themes() -> None:
    mint = resolve_theme("mint")
    mint_dark = resolve_theme("mint_dark")

    assert mint == THEMES["mint"]
    assert mint_dark == THEMES["mint_dark"]
    assert mint.name == "mint" and mint.ink == LIGHT_INK and not mint.auto
    assert mint_dark.name == "mint_dark" and mint_dark.ink == DARK_INK and not mint_dark.auto

    for th in (mint, mint_dark):
        for role in ROLES:
            painted = th.paint(role)
            assert _HEX_RE.fullmatch(painted), (th.name, role, painted)
            assert "currentColor" not in painted and "var(" not in painted

    overridden = resolve_theme("mint", accent="#0A6E56")
    assert overridden.accent == "#0A6E56"
    assert THEMES["mint"].accent != "#0A6E56"


@pytest.mark.parametrize(
    ("name", "ground", "min_ratio"),
    [
        ("mint", "#FFFFFF", 4.5),
        ("mint_dark", "#14181F", 4.5),
    ],
)
def test_mint_themes_wcag_contrast(name: str, ground: str, min_ratio: float) -> None:
    th = resolve_theme(name)
    for role in ("ink", "accent", "good", "bad", "warn"):
        colour = getattr(th, role)
        ratio = contrast_ratio(colour, ground)
        assert ratio >= 3.0, f"{name}.{role} ({colour}) on {ground}: {ratio:.2f}:1 < 3.0:1"
        assert ratio >= min_ratio, (
            f"{name}.{role} ({colour}) on {ground}: {ratio:.2f}:1 < {min_ratio}:1"
        )


@pytest.mark.parametrize("name", ["mint", "mint_dark"])
def test_mint_themes_have_zero_yellow_roles(name: str) -> None:
    th = resolve_theme(name)
    for role in ("ink", "accent", "good", "bad", "warn"):
        colour = getattr(th, role)
        assert colour.upper() not in _YELLOW_HEXES
        assert not _is_yellow_or_amber(colour), f"{name}.{role} ({colour}) is yellow/amber"


@pytest.mark.parametrize("name", ["mint", "mint_dark"])
def test_chips_and_table_render_cleanly_in_mint_themes(name: str) -> None:
    th = resolve_theme(name)
    chips = {
        "bar": mc.bar(0.82, label="Accuracy"),
        "delta_pos": mc.delta(0.78, 0.84, higher_is_better=True, label="Recall"),
        "delta_neg": mc.delta(0.78, 0.71, higher_is_better=True, label="Latency score"),
        "spark": mc.spark([1.84, 1.32, 0.96, 0.74, 0.61, 0.46, 0.42], label="Loss"),
        "ci": mc.ci(0.08, (0.05, 0.11), level=0.95, label="Lift"),
        "gauge_warn": mc.gauge(0.78, normal=(0.0, 0.6), warn=(0.0, 0.85), label="Load"),
    }

    for label, chip in chips.items():
        svg = chip.svg(theme=name)
        root = ET.fromstring(svg)
        assert root.tag.endswith("svg"), label
        assert "currentColor" not in svg and "var(" not in svg

        found_hexes = {h.upper() for h in _HEX_RE.findall(svg)}
        assert found_hexes, f"{label} in {name} emitted no hex colours"
        for h in found_hexes:
            assert h not in _YELLOW_HEXES
            assert not _is_yellow_or_amber(h), f"{label} in {name} emitted yellow {h}"

        standalone = chip.svg(theme=name, standalone=True)
        assert "prefers-color-scheme" not in standalone
        assert f"svg{{color:{th.ink}}}" in standalone

        html = chip.html(theme=name)
        assert f'<span class="mc mc-{chip.kind}"' in html
        assert "currentColor" not in html and "var(" not in html
        for h in _HEX_RE.findall(html):
            assert h.upper() not in _YELLOW_HEXES
            assert not _is_yellow_or_amber(h), f"{label} HTML in {name} emitted yellow {h}"

    # Verify every semantic theme colour renders on the expected chip kinds
    assert th.ink.lower() in chips["bar"].svg(theme=name).lower()
    assert th.good.lower() in chips["delta_pos"].svg(theme=name).lower()
    assert th.bad.lower() in chips["delta_neg"].svg(theme=name).lower()
    assert th.accent.lower() in chips["spark"].svg(theme=name).lower()
    assert th.ink.lower() in chips["ci"].svg(theme=name).lower()
    assert th.warn.lower() in chips["gauge_warn"].svg(theme=name).lower()

    # Render a full mintchip.Table in HTML and verify all roles & zero yellow
    rows = [
        {
            "model": "emerald-v2",
            "acc": 0.88,
            "change": (0.81, 0.88),
            "lift": (0.08, 0.05, 0.11),
            "loss": [1.84, 1.32, 0.96, 0.74, 0.52, 0.42],
            "load": 0.78,
        },
        {
            "model": "baseline",
            "acc": 0.74,
            "change": (0.79, 0.74),
            "lift": (-0.04, -0.08, 0.00),
            "loss": [1.90, 1.55, 1.24, 1.01, 0.88, 0.82],
            "load": 0.45,
        },
    ]
    cols = {
        "model": "text",
        "acc": "bar",
        "change": {"chip": "delta", "higher_is_better": True},
        "lift": {"chip": "ci", "level": 0.95},
        "loss": "spark",
        "load": {"chip": "gauge", "normal": (0.0, 0.6), "warn": (0.0, 0.85)},
    }
    tbl = mc.table(rows, cols, title="Mint Theme Benchmark")
    table_html = tbl.html(theme=name)
    assert '<table class="mc-table"' in table_html
    assert "currentColor" not in table_html and "var(" not in table_html
    for role in ("ink", "accent", "good", "bad", "warn"):
        assert getattr(th, role).lower() in table_html.lower(), (name, role)
    for h in _HEX_RE.findall(table_html):
        assert h.upper() not in _YELLOW_HEXES
        assert not _is_yellow_or_amber(h), f"Table HTML in {name} emitted yellow {h}"


@pytest.mark.parametrize("name", ["mint", "mint_dark"])
def test_every_registered_svg_kind_renders_zero_yellow_in_mint_themes(name: str) -> None:
    for kind_name, kind in sorted(mc.REGISTRY.items()):
        if kind.svg is None:
            continue
        svg = kind.example_chip().svg(theme=name)
        assert "currentColor" not in svg and "var(" not in svg, (kind_name, name)
        for h in _HEX_RE.findall(svg):
            assert h.upper() not in _YELLOW_HEXES, (kind_name, name, h)
            assert not _is_yellow_or_amber(h), (kind_name, name, h)
