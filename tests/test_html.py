from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

import mintchip as mc
from mintchip.render.html import restates
from mintchip.themes import contrast_ratio

KINDS = sorted(mc.REGISTRY)
BLOCK = {"div", "p", "details", "table", "ul", "ol", "section", "figure", "h1", "h2", "h3"}


class Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attrs: list[dict] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append(dict(attrs))


def parse(h: str) -> Tags:
    t = Tags()
    t.feed(h)
    return t


def popover(h: str) -> str:
    m = re.search(r'class="mc-pop" popover[^>]*>(.*)</span></span>$', h)
    return m.group(1) if m else ""


@pytest.mark.parametrize("name", KINDS)
def test_chip_is_phrasing_content_with_a_compact_value(name: str) -> None:
    c = mc.REGISTRY[name].example_chip()
    h = c.html()
    t = parse(h)
    assert not BLOCK & set(t.tags), "a block element would end the enclosing <p>"
    assert "<script" not in h and "border-radius" not in h.split("<svg")[0], "no pill"
    shown = c.text(compact=True).split(" ")[0]
    assert f'<span class="mc-v">{shown}' in h.replace("&amp;", "&")
    targets = [a["popovertarget"] for a in t.attrs if "popovertarget" in a]
    ids = [a["id"] for a in t.attrs if "popover" in a]
    assert targets == ids and len(ids) == 1


def test_popover_ids_are_unique_for_the_same_chip() -> None:
    c = mc.ci(0.08, (0.05, 0.11), level=0.95)
    page = c.html() + c.html()
    ids = re.findall(r' id="([^"]+)"', page)
    assert len(ids) == 2 and len(set(ids)) == 2
    for pid in ids:
        assert f"anchor-name:--{pid}" in page and f"position-anchor:--{pid}" in page


def test_popover_holds_what_the_sentence_does_not_say() -> None:
    c = mc.ci(0.08, (0.05, 0.11), level=0.95, label="Retrieval lift")
    body = popover(c.html())
    assert '<span class="mc-v">+0.08</span>' in c.html(), "compact value in the sentence"
    assert "Retrieval lift" in body and "+0.08 (95% CI +0.05 to +0.11)" in body
    assert "interval width 0.06" in body
    full = c.html(compact=False, label=True)
    assert "95% CI" not in popover(full) and "Retrieval lift" not in popover(full)


@pytest.mark.parametrize(
    ("kind", "gone", "kept"),
    [
        ("num", "exact value", "Accuracy"),
        ("dist", "median 20.3 ms", "range 18.9 to 47.8 ms"),
        ("bar", "of the whole", "8 points short"),
        ("share", "never", "code 62 (62%)"),
    ],
)
def test_restating_facts_are_filtered(kind: str, gone: str, kept: str) -> None:
    body = popover(mc.REGISTRY[kind].example_chip().html())
    assert gone not in body and kept in body


def test_restates() -> None:
    assert restates("exact value 0.82", "0.82")
    assert restates("82% of the whole", "82%")
    assert not restates("higher is better", "0.82"), "no number: says something in words"
    assert not restates("code 62 (62%)", "62·28·10%"), "a name the sentence lacks"
    assert not restates("3 out of 10 (30%)", "3/10")


def test_warnings_detail_and_no_details() -> None:
    c = mc.dist([18.9, 19.4, 19.8, 20.1, 20.3, 20.3, 20.9, 21.6, 22.8, 47.8], unit="ms")
    body = popover(c.html(detail='<a href="#fig">figure 2</a>'))
    assert 'class="mc-pop-w">Note: 1 sample(s)' in body
    assert body.endswith('<a href="#fig">figure 2</a>'), "detail is appended, unescaped"
    bare = c.html(details=False)
    assert "popover" not in bare and "<button" not in bare and "nowrap" in bare
    assert "popover" not in mc.num(0.82).html(), "nothing to add, so no popover"


def test_css_tokens_and_dark_values_read_on_both_surfaces() -> None:
    s = mc.css()
    assert "color-scheme:light dark" in s and "prefers-color-scheme:dark" in s
    for role in ("accent", "good", "bad", "warn"):
        values = re.findall(rf"--mc-{role}:(#[0-9A-Fa-f]{{6}})", s)
        assert len(set(values)) == 2, role
        for v in values:
            assert contrast_ratio(v, "#FFFFFF") >= 3 and contrast_ratio(v, "#14181F") >= 3
    assert ".mc-pop" in s and ".mc-table" in s and "34em" in s
    assert "box-shadow" not in s and "<" not in s


def test_table_gutters_are_one_width_before_every_column() -> None:
    s = mc.css()
    assert ".mc-table th,.mc-table td{padding:.3em 0 .3em 1.25em;" in s
    assert ".mc-table :is(th,td):first-child{padding-left:0}" in s
    assert ".mc-table .mc-graph{padding-left:.45em}" in s, "a value sits close to its graphic"
    assert "padding-right" not in s.split(".mc-table", 1)[1].split(".mc-page", 1)[0], (
        "a gutter after a value cell would be lost when no graphic follows it"
    )


def test_repr_html_and_save_carry_the_stylesheet(tmp_path) -> None:
    c = mc.REGISTRY["spark"].example_chip()
    assert c._repr_html_().startswith(f"<style>{mc.css()}</style><span")
    c.save(tmp_path / "c.html")
    page = (tmp_path / "c.html").read_text(encoding="utf-8")
    assert mc.css() in page and "<script" not in page


class FakeTable:
    def html(self, *, theme="auto", accent=None) -> str:
        return f'<table class="mc-table" data-theme="{theme}"><tr><td>1</td></tr></table>'


def test_document_is_a_reading_page() -> None:
    chip = mc.REGISTRY["ci"].example_chip()
    page = mc.document(
        "Run <14>",
        [f"Lift was {chip.html()}.", "<h2>More</h2>", FakeTable(), chip, "<table></table>"],
        subtitle="five seeds",
        source="runs/14",
    )
    assert page.startswith("<!doctype html>") and "<script" not in page
    assert "<title>Run &lt;14&gt;</title>" in page and "<h1>Run &lt;14&gt;</h1>" in page
    assert '<p class="mc-sub">five seeds</p>' in page and "Source: runs/14" in page
    assert "<p>Lift was <span" in page and "\n<h2>More</h2>\n" in page
    assert '<div class="mc-wide"><table class="mc-table" data-theme="auto">' in page
    assert '<div class="mc-wide"><table></table></div>' in page
    assert '<p><span class="mc mc-ci">' in page
    assert 'content="light dark"' in page and "data-mc-scheme" not in page.split("<head>")[0]


def test_document_theme_and_errors() -> None:
    page = mc.document("t", ["x"], theme="dark")
    assert '<html lang="en" class="mc-page" data-mc-scheme="dark">' in page
    assert mc.document("t", "one block").count("<p>one block</p>") == 1
    with pytest.raises(mc.ChipError, match="theme"):
        mc.document("t", ["x"], theme="neon")
    with pytest.raises(mc.ChipError, match="block 1 is a int"):
        mc.document("t", ["x", 3])
