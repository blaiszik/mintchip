"""Registry-wide invariants: every registered chip kind is checked, including kinds added later."""

from __future__ import annotations

import inspect
import json
import re
import xml.etree.ElementTree as ET

import pytest

import mintchip as mc
from mintchip.render.svg_base import SIZES
from mintchip.render.text_base import ALLOWED
from mintchip.scales import downsample_minmax, quantile, robust_extent
from mintchip.spec import CATALOG_ORDER, PARAM_TYPES
from mintchip.themes import AUTO_FALLBACKS

KINDS = sorted(mc.REGISTRY)
SEQUENCE_TYPES = {"numbers", "strings", "values", "range", "mapping"}
CONTENT_FIT = {"ratio", "strip"}  # kinds whose canvas ends after their last mark (Canvas.fit)
ANSI = re.compile(r"\x1b\[[0-9;]*m")
BAD = {
    "number": ["1.5", True, [1.0], float("inf")],
    "int": [1.5, "3", True],
    "string": [5, ["a"]],
    "bool": ["yes", 1],
    "numbers": ["abc", 5, [1.0, "x"], [1.0, float("inf")], {"a": 1}],
    "range": [(1.0,), (2.0, 1.0), "ab", 3.0],
    "strings": ["abc", [1, 2]],
    "values": [5, [object()]],
    "mapping": [5, [1, 2], [("a", "x")]],
}


def kind_of(name: str) -> mc.Kind:
    return mc.REGISTRY[name]


def example(name: str) -> mc.Chip:
    return kind_of(name).example_chip()


def svg_kinds() -> list[str]:
    return [k for k in KINDS if kind_of(k).svg is not None]


@pytest.mark.parametrize("name", KINDS)
def test_registration_is_complete(name: str) -> None:
    k = kind_of(name)
    assert k.text is not None, "every kind needs a text renderer"
    assert k.question.endswith("?") and k.have
    assert set(k.example) <= {p.name for p in k.params}
    assert all(p.name in k.example for p in k.params if p.required)
    # Tables sort and align on the chip's primary number.
    value = k.example_chip().stats["value"]
    assert value is None or isinstance(value, float | int)


@pytest.mark.parametrize("name", KINDS)
def test_every_constructor_parameter_has_a_param_and_vice_versa(name: str) -> None:
    k = kind_of(name)
    sig = inspect.signature(k.fn)
    assert list(sig.parameters) == [p.name for p in k.params]
    for p, sp in zip(k.params, sig.parameters.values(), strict=True):
        assert p.type in PARAM_TYPES and p.help
        assert p.positional == (sp.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD)
        assert p.required == (sp.default is inspect.Parameter.empty)
        if not p.required:
            assert sp.default == p.default


@pytest.mark.parametrize("name", KINDS)
def test_round_trip_through_json(name: str) -> None:
    c = example(name)
    d = json.loads(json.dumps(c.to_dict()))
    assert d == c.to_dict() and d["chip"] == name
    again = mc.from_dict(d)
    assert again.text() == c.text()
    assert again == c


@pytest.mark.parametrize("name", KINDS)
def test_text_tiers(name: str) -> None:
    c = example(name)
    for compact in (False, True):
        assert c.text(ascii=True, compact=compact).isascii()
        assert all(ch.isascii() or ch in ALLOWED for ch in c.text(compact=compact))
    assert ANSI.sub("", c.text(color=True)) == c.text()
    assert c.text().startswith(c.value_text)
    assert c.text(value=False) in c.text()
    assert c.markdown() == f"`{c.text()}`"


@pytest.mark.parametrize("name", KINDS)
def test_repr_is_one_short_line(name: str) -> None:
    r = repr(example(name))
    assert "\n" not in r and len(r) <= 100 and r.startswith(f"<Chip {name}: ")


@pytest.mark.parametrize("name", svg_kinds())
@pytest.mark.parametrize("size", [None, "s", "m", "l"])
def test_svg_root_per_contract(name: str, size: str | None) -> None:
    c = example(name)
    root = ET.fromstring(c.svg(size=size))
    x0, y0, w, h = root.get("viewBox").split()
    assert (x0, y0, h) == ("0", "0", "16")
    if name not in CONTENT_FIT:
        assert float(w) == SIZES[size or kind_of(name).size]
    assert root.get("width") == f"{round(float(w) / 16, 2):g}em" and root.get("height") == "1em"
    assert root.get("role") == "img" and root.get("aria-label") == c.alt
    assert json.loads(root.get("data-mc")) == c.to_dict()
    assert root.get("style") == "vertical-align:-0.15em;overflow:visible"
    title, desc = list(root)[:2]
    assert title.tag.endswith("title") and title.text == c.alt
    assert desc.tag.endswith("desc") and (desc.text or "") == "; ".join(c.facts)
    assert len(list(root)) > 2, "the chip draws something"


@pytest.mark.parametrize("name", svg_kinds())
def test_auto_svg_paints_by_role_only(name: str) -> None:
    svg = example(name).svg()
    assert not re.search(r'\s(fill|stroke|color)="', svg), "paint goes through style=, not attrs"
    fallback = re.compile(r"var\(--mc-(accent|good|bad|warn), #[0-9A-Fa-f]{6}\)")
    for style in re.findall(r'style="([^"]*)"', svg):
        assert "#" not in fallback.sub("", style), style
        assert "background" not in style.lower()
    markup = re.sub(r'(aria-label|data-mc)="[^"]*"|<title>.*?</title>|<desc>.*?</desc>', "", svg)
    assert "background" not in markup.lower()
    assert "<style>" not in svg and "prefers-color-scheme" in example(name).svg(standalone=True)


@pytest.mark.parametrize("name", svg_kinds())
def test_static_themes_emit_concrete_colours(name: str) -> None:
    for theme in ("light", "dark", "mono"):
        svg = example(name).svg(theme=theme)
        assert "currentColor" not in svg and "var(" not in svg


def test_auto_fallbacks_reach_3_to_1_on_light_and_dark() -> None:
    for role, colour in AUTO_FALLBACKS.items():
        for ground in ("#FFFFFF", "#14181F"):
            assert mc.contrast_ratio(colour, ground) >= 3.0, (role, ground)
    for name, ground in (("light", "#FFFFFF"), ("dark", "#14181F"), ("mono", "#FFFFFF")):
        t = mc.THEMES[name]
        for colour in (t.ink, t.accent, t.good, t.bad, t.warn):
            assert mc.contrast_ratio(colour, ground) >= 3.0, (name, colour)


@pytest.mark.parametrize(
    "name", [k for k in KINDS if any(p.type in SEQUENCE_TYPES for p in kind_of(k).params)]
)
def test_non_sequence_iterables_are_accepted(name: str) -> None:
    k = kind_of(name)
    spec = dict(k.example)
    for p in k.params:
        if p.type in SEQUENCE_TYPES and p.name in spec:
            v = spec[p.name]
            spec[p.name] = (x for x in (v.items() if isinstance(v, dict) else v))
    assert k.fn(**spec).text() == example(name).text()


@pytest.mark.parametrize("name", KINDS)
def test_wrong_types_raise_chip_error(name: str) -> None:
    k = kind_of(name)
    for p in k.params:
        for bad in [object(), *BAD[p.type]]:
            with pytest.raises(mc.ChipError, match=rf"mintchip\.{name}\b"):
                k.fn(**{**k.example, p.name: bad})
    with pytest.raises(mc.ChipError, match=rf"mintchip\.{name}: unknown argument"):
        k.fn(**k.example, colour="red")
    if any(p.required for p in k.params):
        with pytest.raises(mc.ChipError, match=rf"mintchip\.{name}"):
            k.fn()


@pytest.mark.parametrize("name", KINDS)
def test_html_is_bare_and_inline(name: str) -> None:
    c = example(name)
    h = c.html()
    assert h.startswith(f'<span class="mc mc-{name}"') and c.value_text.split()[0] in h
    assert "<details" not in h and "<div" not in h, "block elements would end the <p>"
    assert "popover" in h and "popover" not in c.html(details=False)
    r = c._repr_html_()
    assert r.startswith("<style>") and f'<span class="mc mc-{name}"' in r


@pytest.mark.parametrize("name", KINDS)
def test_save_every_format(name: str, tmp_path) -> None:
    c = example(name)
    exts = ("svg", "html", "txt", "json") if kind_of(name).svg else ("html", "txt", "json")
    for ext in exts:
        out = c.save(tmp_path / f"chip.{ext}")
        assert out["kind"] == name and (tmp_path / f"chip.{ext}").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "chip.json").read_text()) == c.to_dict()
    with pytest.raises(mc.ChipError):
        c.save(tmp_path / "chip.png")
    if not kind_of(name).svg:
        with pytest.raises(mc.ChipError, match="no graphic"):
            c.save(tmp_path / "chip.svg")
    json.dumps(c.summary())


def test_catalog_follows_contract_order() -> None:
    names = [e["name"] for e in mc.CATALOG]
    assert sorted(names) == KINDS
    known = [n for n in names if n in CATALOG_ORDER]
    assert known == [n for n in CATALOG_ORDER if n in mc.REGISTRY]
    assert all(getattr(mc, n) is mc.REGISTRY[n].fn for n in names)


def test_from_dict_and_render_errors_are_chip_errors() -> None:
    with pytest.raises(mc.ChipError, match="'chip' key"):
        mc.from_dict({"values": [1, 2]})
    with pytest.raises(mc.ChipError, match="Did you mean 'spark'"):
        mc.from_dict({"chip": "sprak", "values": [1, 2]})
    c = example(svg_kinds()[0])
    for bad in ({"theme": "neon"}, {"size": "xl"}, {"accent": "blue"}, {"domain": (1, 1)}):
        with pytest.raises(mc.ChipError):
            c.svg(**bad)


def test_scales() -> None:
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.5) == 2.5
    assert downsample_minmax([1.0] * 20 + [50.0] + [1.0] * 20, 12).count(50.0) == 1
    assert downsample_minmax([1.0, None, 2.0], 12) == [1.0, None, 2.0]
    assert robust_extent([1, 2, 3, 4, 5, 100]) == (1.0, 5.0)
    lo, hi = mc.shared_domain(iter([1.0, 2.0]), (x for x in [3.0]), 0.5, pad=0)
    assert (lo, hi) == (0.5, 3.0)
    with pytest.raises(mc.ChipError):
        mc.shared_domain("abc")


def _right_edge(svg: str) -> float:
    """The rightmost ink in an SVG: rect ends, circle edges, path points plus half a stroke."""
    edge = 0.0
    for el in re.finditer(r"<(rect|circle|path) ([^>]*)>", svg):
        attrs = el[2]
        sw = float(m[1]) if (m := re.search(r"stroke-width:([\d.]+)", attrs)) else 0.0
        if el[1] == "rect":
            x, w = (float(re.search(rf'{a}="([\d.]+)"', attrs)[1]) for a in ("x", "width"))
            edge = max(edge, x + w)
        elif el[1] == "circle":
            cx, r = (float(re.search(rf'{a}="([\d.]+)"', attrs)[1]) for a in ("cx", "r"))
            edge = max(edge, cx + r + (sw / 2 if "fill:none" in attrs else 0))
        else:
            d = re.search(r'd="([^"]+)"', attrs)[1]
            edge = max([edge] + [float(x) + sw / 2 for x in re.findall(r"[ML](-?[\d.]+) ", d)])
    return edge


@pytest.mark.parametrize("name", svg_kinds())
def test_a_lone_chip_ends_a_word_space_from_the_next_word(name: str) -> None:
    svg = example(name).svg()
    width = float(re.search(r'viewBox="0 0 ([\d.]+) 16"', svg)[1])
    assert 1.5 <= width - _right_edge(svg) <= 4, "blank after the last mark is about the pad"


def test_value_alone_and_decimals() -> None:
    lift = mc.ci(0.08, (0.05, 0.11), level=0.95)
    assert lift.value() == lift.value_text == "+0.08 (95% CI +0.05 to +0.11)"
    assert lift.value(compact=True) == "+0.08" and lift.value(compact=True, decimals=3) == "+0.080"
    assert mc.dist([1, 2, 3], unit="µs").value(ascii=True).isascii()
    assert mc.spark([0.9, 0.6]).text(decimals=2) == "0.60 (range 0.60 to 0.90) █▁"
    assert mc.spark([0.9, 0.6]).text() == "0.6 (range 0.6 to 0.9) █▁", "alone, unchanged"
    assert mc.num(1.2e-5).value(decimals=2) == "1.2e−5", "scientific notation keeps its form"
    assert mc.ratio(3, 10).value(decimals=2) == mc.ratio(3, 10).value(), "counts ignore it"
    assert "0.90" in mc.spark([0.9, 0.6], vs=[0.8, 0.9]).html(decimals=2)


@pytest.mark.parametrize("name", KINDS)
def test_warnings_for_without_a_domain_is_warnings(name: str) -> None:
    c = example(name)
    assert c.warnings_for() == c.warnings
    if c.domain is not None:
        lo, hi = c.domain
        assert c.warnings_for((lo - 1e6, hi + 1e6)) == tuple(
            w for w in c.warnings if "clipped" not in w and "cuts" not in w
        )


def test_messages_read_for_a_shell_user_too() -> None:
    msgs = [
        *mc.ci(0.1, (0.0, 0.2)).warnings,
        *mc.ci(0.1, (0.0, 0.2), domain=(0.05, 0.3)).warnings,
        *mc.dist([1, None, 2, 3]).warnings,
        *mc.table([{"c": [0.1, 0.0, 0.2]}], {"c": "ci"}).warnings,
        *mc.lint("{a} {b} {c}.", {k: mc.spark([1, 2]) for k in "abc"}),
    ]
    assert msgs and any("state the interval's level (level=0.95)" in m for m in msgs)
    for m in msgs:
        assert not re.search(r"\bpass \w+=|mintchip\.|\bNone\b|\(\d[\d.]*, \d", m), m
