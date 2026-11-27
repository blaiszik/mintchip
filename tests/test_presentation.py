"""SVG lint for the design rules, over every registered kind (so new chips are covered).

Specimens: each kind's registered example at every size, plus every edge case in the gallery
(clipped outliers, cut domains, overflow, folded parts), which is where marks tend to stray.

Checked from the SVG string: marks stay inside the 16-unit-high viewBox (strokes and caps
included), strokes are at least 1.25 and dots at least 1.75 units, the auto theme paints only by
role, good/bad/warn appear only with a declared direction or literal pass/warn/fail data, and a
chip has at most three kinds of mark. Not checkable here, and left to ``gallery/output/
baseline.html``: whether a mark is visible at 1× against a real background, and whether the
chip sits inside the line box of a real font.
"""

from __future__ import annotations

import importlib.util
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import mintchip as mc
from mintchip.render.svg_base import (
    BAND_OPACITY,
    CONTEXT_OPACITY,
    HEIGHT,
    MARK_OPACITY,
    MIN_RADIUS,
    MIN_STROKE,
    SIZES,
    WASH_OPACITY,
)
from mintchip.themes import AUTO_FALLBACKS

ROOT = Path(__file__).resolve().parents[1]
NS = "{http://www.w3.org/2000/svg}"
EPS = 0.01
MARKS = ("path", "circle", "rect", "line", "polyline", "polygon", "ellipse")
CONTEXT = {CONTEXT_OPACITY, MARK_OPACITY, WASH_OPACITY, BAND_OPACITY}
# Kinds whose data is itself a state (pass/warn/fail) or a declared normal range.
STATUS_KINDS = {"strip", "gauge", "status"}
MAX_MARK_KINDS = 3

# Real violations found by this lint, as (check, specimen id) -> reason. Each is a strict
# expected failure until the chip is fixed; delete the entry when it passes.
KNOWN: dict[tuple[str, str], str] = {}


def _gallery():
    spec = importlib.util.spec_from_file_location(
        "build_gallery", ROOT / "gallery/build_gallery.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def specimens() -> list[tuple[str, mc.Chip, str | None]]:
    out = []
    for kind in sorted(mc.REGISTRY):
        if mc.REGISTRY[kind].svg is None:
            continue
        for size in SIZES:
            out.append((f"{kind}[{size}]", mc.REGISTRY[kind].example_chip(), size))
    out += [(name, chip, None) for name, chip in _gallery().edge_chips() if chip.svg()]
    return out


SPECIMENS = specimens()


def cases(check: str) -> list:
    out = []
    for name, chip, size in SPECIMENS:
        why = KNOWN.get((check, name))
        marks = [pytest.mark.xfail(reason=why, strict=True)] if why else []
        out.append(pytest.param(chip, size, id=name, marks=marks))
    return out


def style(el: ET.Element) -> dict[str, str]:
    pairs = (kv.split(":", 1) for kv in (el.get("style") or "").split(";") if ":" in kv)
    return {k.strip(): v.strip() for k, v in pairs}


def marks(svg: str) -> tuple[float, list[tuple[str, ET.Element, dict[str, str]]]]:
    root = ET.fromstring(svg)
    x0, y0, w, h = (float(v) for v in root.get("viewBox").split())
    assert (x0, y0, h) == (0, 0, HEIGHT) and root.get("height") == "1em"
    els = [(el.tag.replace(NS, ""), el) for el in root.iter()]
    unknown = {t for t, _ in els} - {"svg", "title", "desc", "path", "circle", "rect"}
    assert not unknown, f"lint does not know how to measure {unknown}; extend it"
    return w, [(t, el, style(el)) for t, el in els if t in MARKS]


def points(d: str) -> list[tuple[float, float]]:
    """Points of a path drawn by svg_base (M and L commands only)."""
    cmds = re.findall(r"([A-Za-z])\s*([-\d.e]+)[ ,]([-\d.e]+)", d)
    assert re.sub(r"[ML][-\d.e]+[ ,][-\d.e]+", "", d).strip() == "", f"unexpected path {d!r}"
    return [(float(x), float(y)) for _, x, y in cmds]


def stroke_width(st: dict[str, str]) -> float:
    if st.get("stroke", "none") == "none":
        return 0.0
    return float(st.get("stroke-width", "1"))


def bounds(tag: str, el: ET.Element, st: dict[str, str]) -> tuple[float, float, float, float]:
    half = stroke_width(st) / 2
    if tag == "path":
        pts = points(el.get("d"))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    elif tag == "circle":
        cx, cy, r = (float(el.get(a)) for a in ("cx", "cy", "r"))
        xs, ys = [cx - r, cx + r], [cy - r, cy + r]
    else:
        x, y, w, h = (float(el.get(a)) for a in ("x", "y", "width", "height"))
        xs, ys = [x, x + w], [y, y + h]
    return min(xs) - half, min(ys) - half, max(xs) + half, max(ys) + half


def is_chevron(tag: str, el: ET.Element, st: dict[str, str]) -> bool:
    """The edge marker svg_base draws for data cut by the domain (Canvas.chevron)."""
    if tag != "path" or stroke_width(st) != MIN_STROKE:
        return False
    pts = points(el.get("d"))
    if len(pts) != 3:
        return False
    (ax, ay), (tx, ty), (bx, by) = pts
    side = ax == bx and abs(ay - ty) == abs(by - ty) == 3 and abs(ax - tx) == 2.5
    end = ay == by and abs(ax - tx) == abs(bx - tx) == 3 and abs(ay - ty) == 2.5
    return side or end


def paint(st: dict[str, str]) -> list[str]:
    return [st[k] for k in ("fill", "stroke") if st.get(k, "none") != "none"]


def role(value: str) -> str:
    if value == "currentColor":
        return "ink"
    m = re.fullmatch(r"var\(--mc-(\w+), (#[0-9A-Fa-f]{6})\)", value)
    assert m, f"paint {value!r} is not a role"
    assert AUTO_FALLBACKS.get(m[1]) == m[2], f"{value} does not use the theme's fallback"
    return m[1]


def layer(st: dict[str, str]) -> str:
    """data (ink, accent or a status colour) or context (ink at a context opacity)."""
    roles = {role(v) for v in paint(st)}
    opacity = float(st.get("fill-opacity") or st.get("stroke-opacity") or 1)
    if roles == {"ink"} and opacity in CONTEXT:
        return "context"
    return "data"


@pytest.mark.parametrize(("chip", "size"), cases("viewbox"))
def test_marks_stay_inside_the_viewbox(chip: mc.Chip, size: str | None) -> None:
    width, els = marks(chip.svg(size=size))
    for tag, el, st in els:
        x0, y0, x1, y1 = bounds(tag, el, st)
        slack = EPS  # chevrons too: Canvas keeps their arms inside, even at a corner
        where = f"{tag} {ET.tostring(el, encoding='unicode')[:90]}"
        assert x0 >= -slack and x1 <= width + slack, (
            f"{where} spans x {x0:.2f}..{x1:.2f} of {width}"
        )
        assert y0 >= -slack and y1 <= HEIGHT + slack, f"{where} spans y {y0:.2f}..{y1:.2f} of 16"


@pytest.mark.parametrize(("chip", "size"), cases("strokes"))
def test_strokes_and_dots_meet_the_minimums(chip: mc.Chip, size: str | None) -> None:
    for tag, el, st in marks(chip.svg(size=size))[1]:
        w = stroke_width(st)
        assert w == 0 or w >= MIN_STROKE, f"{tag} stroke {w} < {MIN_STROKE}"
        if tag == "circle":
            r = float(el.get("r"))
            assert r >= MIN_RADIUS, f"dot radius {r} < {MIN_RADIUS}"


@pytest.mark.parametrize(("chip", "size"), cases("paint"))
def test_auto_theme_paints_only_by_role(chip: mc.Chip, size: str | None) -> None:
    svg = chip.svg(size=size)
    assert not re.search(r'\s(fill|stroke|color|opacity)="', svg), "paint must go through style="
    for tag, _, st in marks(svg)[1]:
        assert paint(st), f"{tag} paints nothing"
        assert not {"opacity", "color", "background"} & set(st), st
        roles = {role(v) for v in paint(st)}
        status = roles & {"good", "bad", "warn"}
        declared = chip.args.get("higher_is_better") is not None or chip.kind in STATUS_KINDS
        assert not status or declared, (
            f"{tag} is painted {status} but {chip.kind} declared no direction (rule 3)"
        )


@pytest.mark.parametrize(("chip", "size"), cases("kinds"))
def test_at_most_three_kinds_of_mark(chip: mc.Chip, size: str | None) -> None:
    kinds = {
        (tag, layer(st))
        for tag, el, st in marks(chip.svg(size=size))[1]
        if not is_chevron(tag, el, st)
    }
    assert len(kinds) <= MAX_MARK_KINDS, sorted(kinds)


@pytest.mark.parametrize(("chip", "size"), cases("height"))
def test_no_chip_is_taller_than_1em(chip: mc.Chip, size: str | None) -> None:
    root = ET.fromstring(chip.svg(size=size))
    assert root.get("height") == "1em" and root.get("viewBox").split()[3] == str(HEIGHT)
    assert "vertical-align:-0.15em" in root.get("style")  # 0.85em above the baseline


def test_known_violations_name_real_specimens() -> None:
    names = {name for name, _, _ in SPECIMENS}
    assert {name for _, name in KNOWN} <= names


def test_every_kind_with_a_graphic_is_linted() -> None:
    linted = {chip.kind for _, chip, _ in SPECIMENS}
    assert linted == {k for k, v in mc.REGISTRY.items() if v.svg is not None}
