from __future__ import annotations

import json
import re

import pytest

import mintchip as mc

LOSS = [1.84, 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43, 0.42]
ROWS = [
    {"model": "retrieval", "acc": 0.82, "lift": (0.08, 0.05, 0.11), "loss": LOSS},
    {"model": "warmup", "acc": 0.75, "lift": (0.01, -0.02, 0.04), "loss": [1.9, 1.1, 0.61]},
    {"model": "baseline", "acc": 0.7, "lift": (-0.05, -0.09, -0.01)},
]
COLS = {"model": "text", "acc": "bar", "lift": {"chip": "ci", "level": 0.95}, "loss": "spark"}


def _body(text: str) -> list[str]:
    lines = text.splitlines()
    rule = next(i for i, line in enumerate(lines) if set(line) <= {"─", "-"})
    return lines[rule + 1 :]


def test_columns_share_one_scale_in_text() -> None:
    t = mc.table(ROWS, COLS)
    lines = t.text().splitlines()
    assert lines[0].split() == ["model", "acc", "lift", "loss"]
    assert "−0.1" in lines[1] and "+0.13" in lines[1], "the ci scale's ends, once, in the header"
    body = _body(t.text())
    assert len(body) == 3 and all(len(line) <= 80 for line in lines)
    opens = {line.index("[") for line in body}
    assert len(opens) == 1, "the axes line up"
    refs = {line.index("│") if "│" in line else line.index("┼") for line in body[:2]}
    assert len(refs) == 1, "one reference line runs down the column"
    assert "82% ██████▌·" in body[0] and "70% █████▋··" in body[2], "bars share a zero"
    assert "[·├●─┤······]  —" in body[2] and "—" not in body[0]


def test_values_align_on_the_decimal_point() -> None:
    t = mc.table([{"x": 12.5}, {"x": 1.25}, {"x": 13}, {"x": None}], {"x": "num"})
    assert _body(t.text()) == ["12.50", " 1.25", "13.00", " —"]
    wide = mc.table([{"x": 12.5}, {"x": 0.25}, {"x": 130}, {"x": None}], {"x": "num"})
    assert _body(wide.text()) == [" 12.5", "  0.25", "130", "  —"], (
        "columns spanning >= 100x keep integers crisp while aligning on the decimal point"
    )
    bench = mc.table(
        [{"n": "small", "ms": 1.92}, {"n": "medium", "ms": 18.4}, {"n": "large", "ms": 212}],
        {"n": "text", "ms": {"chip": "num", "unit": "ms"}},
    )
    assert "212 ms" in bench.text() and "212.00" not in bench.text() and "1.92 ms" in bench.text()
    t = mc.table([{"x": 12.5}, {"x": 130}], {"x": {"chip": "num", "unit": "s"}})
    assert _body(t.text()) == [" 12.5 s", "130.0 s"], "with a unit, right-aligned"


def test_twelve_rows_four_columns_fit_80_and_long_text_is_shortened() -> None:
    rows = [
        {"name": f"run-{i}", "acc": 0.5 + i / 40, "lift": (i / 100, i / 100 - 0.03, i / 100 + 0.03),
         "loss": [2, 1.5, 1.2, 1 - i / 50]}
        for i in range(12)
    ]  # fmt: skip
    cols = {"name": "text", "acc": "bar", "lift": "ci", "loss": "spark"}
    t = mc.table(rows, cols)
    assert len(_body(t.text())) == 12
    assert max(len(line) for line in t.text().splitlines()) <= 80
    rows[0]["name"] = "a-very-long-experiment-name-" * 3
    t = mc.table(rows, cols)
    assert max(len(line) for line in t.text().splitlines()) <= 80
    assert "…" in _body(t.text())[0] and "~" in _body(t.text(ascii=True))[0]
    assert any("'name' shortened" in w for w in t.warnings)


def test_cells_from_chips_dicts_and_bare_values() -> None:
    rows = [
        {"k": "a", "c": mc.ci(0.1, (0.0, 0.2), level=0.9)},
        {"k": "b", "c": {"estimate": 0.05, "interval": [0.01, 0.09]}},
        {"k": "c", "c": [0.02, [-0.01, 0.05]]},
        {"k": "d", "c": (0.03, 0.0, 0.06)},
        {"k": "e"},
    ]
    t = mc.table(rows, {"k": "text", "c": "ci"})
    assert [r[1].kind for r in t.rows[:4]] == ["ci"] * 4 and t.rows[4][1] is None
    assert _body(t.text())[4].endswith("—") and _body(t.text(ascii=True))[4].endswith("-")
    t = mc.table([{"s": {"a": 3, "b": 1}}, {"b": [412, 500]}], {"s": "share", "b": "bar"})
    assert t.rows[0][0].kind == "share" and t.rows[1][0] is None
    assert mc.table([{"b": [412, 500]}], {"b": "bar"}).rows[0][0].stats["total"] == 500


def test_cell_errors_name_row_and_column() -> None:
    with pytest.raises(mc.ChipError, match=r"row 1, column 'lift': mintchip\.ci") as e:
        mc.table([{"lift": (0.1, 0, 0.2)}, {"lift": "high"}], {"lift": "ci"})
    assert e.value.fix_hint
    with pytest.raises(mc.ChipError, match="more than mintchip.ci takes") as e:
        mc.table([{"lift": (1, 2, 3, 4)}], {"lift": "ci"})
    assert e.value.fix_hint
    for bad, match in (
        (lambda: mc.table([{"a": 1}], {"a": "bra"}), "Did you mean 'bar'"),
        (lambda: mc.table([{"a": 1}], {"a": {"chip": "bar", "totl": 2}}), "total="),
        (lambda: mc.table([{"a": 1}], sort="b"), "not a column"),
        (lambda: mc.table([{"a": 1}, 2]), "row 1"),
        (lambda: mc.table([{"a": 1}], limit=0), "limit"),
    ):
        with pytest.raises(mc.ChipError, match=match) as e:
            bad()
        assert e.value.fix_hint


def test_sort_limit_and_empty_cells_last() -> None:
    rows = [{"m": "b", "v": 0.5}, {"m": "a", "v": None}, {"m": "c", "v": 0.9}, {"m": "d"}]
    t = mc.table(rows, {"m": "text", "v": "num"}, sort="v")
    assert [r[0] for r in t.rows] == ["c", "b", "a", "d"]
    t = mc.table(rows, {"m": "text", "v": "num"}, sort="v", descending=False, limit=2)
    assert [r[0] for r in t.rows] == ["b", "c"]
    t = mc.table(rows, {"m": "text"}, sort="m", descending=False)
    assert [r[0] for r in t.rows] == ["a", "b", "c", "d"]


def test_inferred_columns_and_files(tmp_path) -> None:
    rows = [{"model": "a", "acc": 0.8, "loss": [3, 2, 1]}, {"model": "b", "acc": 0.7}]
    t = mc.table(rows)
    assert [(c.key, c.kind) for c in t.columns] == [
        ("model", "text"), ("acc", "num"), ("loss", "spark")
    ]  # fmt: skip
    (tmp_path / "r.json").write_text(json.dumps(rows))
    assert mc.table(tmp_path / "r.json").text() == t.text()
    (tmp_path / "r.csv").write_text('model,acc,loss\na,0.8,"3 2 1"\nb,0.7,\n')
    assert mc.table(str(tmp_path / "r.csv")).text() == t.text()
    with pytest.raises(mc.ChipError, match="cannot read"):
        mc.table(tmp_path / "missing.csv")


def test_warnings_are_prefixed_by_row_and_column() -> None:
    t = mc.table([{"m": "x", "c": (0.1, 0.0, 0.2)}], {"m": "text", "c": "ci"})
    assert t.warnings == ("row 0 (x), column 'c': " + mc.ci(0.1, (0, 0.2)).warnings[0],)


def test_markdown_is_gfm_with_code_spans() -> None:
    md = mc.table(ROWS, COLS, title="Runs").markdown().splitlines()
    assert md[0] == "**Runs**" and md[2].startswith("| model | acc | lift (")
    assert md[3] == "|:--|:--|:--|:--|"
    assert md[4].startswith("| retrieval | `82% ██████▌·` | `+0.08 [")
    starts = {line.split("|")[3].index("[") for line in md[4:]}
    assert len(starts) == 1, "glyphs line up inside the code spans"
    num = mc.table([{"n": 1200}, {"n": 35}], {"n": "num"}).markdown().splitlines()
    assert num[1] == "|--:|" and num[3] == "| `   35` |"


def test_html_is_a_table_with_shared_domains() -> None:
    page = mc.table(ROWS, COLS, title="Runs").html()
    assert page.startswith('<table class="mc-table"') and "<caption>Runs</caption>" in page
    assert page.count('colspan="2"') == 3 and page.count('class="mc-graph"><span class="mc') == 8
    assert 'class="mc-lo">−0.1<' in page and 'class="mc-hi">+0.13<' in page
    refs = re.findall(r'<path d="M([\d.]+) 1\.5', page)
    assert len(refs) == 3 and len(set(refs)) == 1, "the ci reference sits at one x in every row"
    bars = re.findall(r'<rect x="([\d.]+)"', page)
    assert len(set(bars)) == 1, "bars share a zero"
    assert "popover" not in page and 'class="mc-num mc-empty" align="right">—' in page
    num = mc.table([{"n": 1.5}, {"n": 0.125}], {"n": "num"}).html()
    assert "mc-graph" not in num and ">1.500<" in num, "one precision per column"


def test_to_dict_round_trips_through_json() -> None:
    t = mc.table(ROWS, COLS, sort="acc", limit=2, title="Runs")
    d = json.loads(json.dumps(t.to_dict()))
    assert d["columns"]["lift"] == {"chip": "ci", "header": "lift", "level": 0.95}
    again = mc.Table.from_dict(d)
    assert again.text() == t.text() and again.to_dict() == d


def test_ascii_and_color() -> None:
    t = mc.table(ROWS, COLS)
    assert t.text(ascii=True).isascii()
    colored = t.text(color=True)
    assert "\x1b[" in colored
    assert re.sub(r"\x1b\[\d+m", "", colored) == t.text(), "colour never moves a column"


def test_a_column_shares_one_precision() -> None:
    rows = [{"s": [1.8, 0.42]}, {"s": [1.5, 0.9]}, {"s": [1.2, 0.4]}, {"s": None}]
    t = mc.table(rows, {"s": "spark"})
    assert [line.split()[0] for line in _body(t.text())] == ["0.42", "0.90", "0.40", "—"]
    assert ">0.90<" in t.html() and "`0.90 " in t.markdown()
    assert mc.spark([1.5, 0.9]).text().startswith("0.9 "), "a chip alone keeps its own"
    n = mc.table([{"n": 0.8}, {"n": 0.42}], {"n": "num"})
    assert _body(n.text()) == ["0.80", "0.42"]


def test_table_warnings_hold_on_the_shared_scale() -> None:
    a = mc.dist([18.9, 19.4, 19.8, 20.1, 20.3, 20.3, 20.9, 21.6, 22.8, 47.8])
    b = mc.dist([30, 40, 45, 50, 55])
    assert a.warnings and mc.table([{"x": a}, {"x": b}], {"x": "dist"}).warnings == ()
    cut = mc.delta(1, 2, domain=(0, 1.5))
    t = mc.table([{"x": cut}, {"x": mc.delta(0, 3)}], {"x": "delta"})
    assert cut.warnings and t.warnings == ()


def test_text_columns_sort_a_to_z_by_default() -> None:
    rows = [{"m": "b", "v": 0.5}, {"m": "a", "v": 0.1}, {"m": "c", "v": 0.9}]
    assert [r[0] for r in mc.table(rows, {"m": "text", "v": "num"}, sort="m").rows] == list("abc")
    assert [r[0] for r in mc.table(rows, {"m": "text", "v": "num"}, sort="v").rows] == list("cba")
    flipped = mc.table(rows, {"m": "text"}, sort="m", descending=True)
    assert [r[0] for r in flipped.rows] == list("cba") and flipped.to_dict()["descending"]
    with pytest.raises(mc.ChipError, match="descending"):
        mc.table(rows, sort="m", descending="yes")


def test_share_columns_keep_one_part_order_when_the_rows_agree() -> None:
    rows = [{"pr": "a", "s": {"code": 62, "docs": 28, "tests": 10}},
            {"pr": "b", "s": {"code": 20, "docs": 50, "tests": 30}}]  # fmt: skip
    t = mc.table(rows, {"pr": "text", "s": "share"})
    assert [r[1].stats["names"] for r in t.rows] == [["code", "docs", "tests"]] * 2
    assert "20·50·30%" in t.text(), "row b keeps code first though docs is larger"
    assert mc.Table.from_dict(json.loads(json.dumps(t.to_dict()))).text() == t.text()
    rows[1]["s"] = {"docs": 50, "code": 20, "tests": 30}
    assert "50·30·20%" in mc.table(rows, {"s": "share"}).text(), "names disagree: sorted"
    rows[1]["s"] = {"code": 20, "docs": 50, "tests": 30}
    forced = mc.table(rows, {"s": {"chip": "share", "sort": True}})
    assert "50·30·20%" in forced.text(), "an explicit column option wins"


def test_bars_with_different_totals_keep_their_own_scale() -> None:
    """38/40 beside 1,840/1,850 are two shares: one absolute scale would empty the first bar."""
    rows = [{"s": "e2e", "p": [38, 40]}, {"s": "unit", "p": [1840, 1850]}]
    t = mc.table(rows, {"s": "text", "p": "bar"})
    e2e, unit = t.text().splitlines()[-2:]
    assert "███████▋" in e2e and "████████" in unit
    same = mc.table([{"p": [90, 200]}, {"p": [150, 200]}], {"p": "bar"}).text().splitlines()[-2:]
    assert "███▋" in same[0] and "██████" in same[1], "equal totals still compare by length"


def test_mixed_bar_column_keeps_count_wording_for_one_of_one() -> None:
    rows = [
        {"s": "e2e", "p": [38, 40]},
        {"s": "smoke", "p": [1, 1]},
        {"s": "unit", "p": [1840, 1850]},
    ]
    t = mc.table(rows, {"s": "text", "p": "bar"})
    txt = t.text()
    assert "38/40" in txt and "1/1" in txt and "1,840/1,850" in txt and "100%" not in txt
    assert "1/1" in t.markdown() and "1/1" in t.html()
    assert mc.Table.from_dict(json.loads(json.dumps(t.to_dict()))).text() == txt

    pcts = mc.table([{"p": 0.82}, {"p": 1.0}], {"p": "bar"}).text()
    assert "82%" in pcts and "100%" in pcts
    forced = mc.table(rows, {"s": "text", "p": {"chip": "bar", "percent": True}}).text()
    assert "95%" in forced and "100%" in forced


def test_text_width_parameter() -> None:
    long_name = "experiment-configuration-alpha-beta-gamma-delta"
    rows = [{"name": long_name, "acc": 0.82, "lift": (0.08, 0.05, 0.11)}]
    cols = {"name": "text", "acc": "bar", "lift": "ci"}
    t = mc.table(rows, cols)
    assert "…" in t.text(width=60) and max(len(ln) for ln in t.text(width=60).splitlines()) <= 60
    wide = t.text(width=120)
    assert long_name in wide and "…" not in wide
    for bad in (0, -10, True, "80"):
        with pytest.raises(mc.ChipError, match="width"):
            t.text(width=bad)  # type: ignore[arg-type]


def test_table_save_every_format(tmp_path) -> None:
    t = mc.table(ROWS, COLS, title="Runs")
    out_html = t.save(tmp_path / "t.html")
    html_text = (tmp_path / "t.html").read_text(encoding="utf-8")
    assert out_html["rows"] == 3 and out_html["columns"] == ["model", "acc", "lift", "loss"]
    assert html_text.startswith("<!doctype html>") and mc.css() in html_text
    assert '<table class="mc-table"' in html_text and "<h1>" not in html_text

    t.save(tmp_path / "frag.html", fragment=True)
    frag_text = (tmp_path / "frag.html").read_text(encoding="utf-8")
    assert frag_text.startswith('<table class="mc-table"') and "<!doctype" not in frag_text.lower()

    t.save(tmp_path / "compact.html", compact=True, accent="#2563EB")
    compact_text = (tmp_path / "compact.html").read_text(encoding="utf-8")
    assert "mc-compact" in compact_text and "--mc-accent:#2563EB" in compact_text

    t.save(tmp_path / "t.md")
    assert (tmp_path / "t.md").read_text(encoding="utf-8") == t.markdown() + "\n"

    t.save(tmp_path / "t.txt", ascii=True, width=100)
    assert (tmp_path / "t.txt").read_text(encoding="utf-8") == t.text(ascii=True, width=100) + "\n"

    t.save(tmp_path / "t.json", indent=2)
    loaded = mc.Table.from_dict(json.loads((tmp_path / "t.json").read_text(encoding="utf-8")))
    assert loaded.text() == t.text()

    assert t._repr_html_().startswith(f"<style>{mc.css()}</style><table")

    with pytest.raises(mc.ChipError, match="unsupported extension"):
        t.save(tmp_path / "t.png")
    with pytest.raises(mc.ChipError, match="Table.save"):
        t.save(tmp_path / "t.txt", bogus=1)


def test_highlight_and_baseline_row_emphasis() -> None:
    t = mc.table(ROWS, COLS, highlight="retrieval", baseline="baseline")
    txt = t.text()
    body = _body(txt)
    assert body[0].startswith("▸ retrieval")
    assert body[1].startswith("  warmup")
    assert body[2].startswith("· baseline")
    opens = {line.index("[") for line in body}
    assert len(opens) == 1, "gutter keeps every column aligned"

    asc = t.text(ascii=True)
    assert asc.isascii() and _body(asc)[0].startswith("> retrieval")
    assert _body(asc)[2].startswith(". baseline")

    colored = t.text(color=True)
    assert "\x1b[1m" in _body(colored)[0] and "\x1b[2m" in _body(colored)[2]
    assert re.sub(r"\x1b\[\d+m", "", colored) == txt, "ANSI emphasis never shifts a column"

    md = t.markdown().splitlines()
    assert "| **retrieval** | **`82% ██████▌·`** |" in md[2]
    assert "| warmup |" in md[3]
    assert "| *baseline* |" in md[4]

    html = t.html()
    assert '<tr class="mc-highlight"><td class="mc-text">retrieval</td>' in html
    assert '<tr><td class="mc-text">warmup</td>' in html
    assert '<tr class="mc-baseline"><td class="mc-text">baseline</td>' in html

    d = json.loads(json.dumps(t.to_dict()))
    assert d["highlight"] == ["retrieval"] and d["baseline"] == "baseline"
    rebuilt = mc.Table.from_dict(d)
    assert rebuilt.text() == txt and rebuilt.html() == html and rebuilt.to_dict() == d

    multi = mc.table(ROWS, COLS, highlight=["retrieval", "baseline"], baseline="baseline")
    assert '<tr class="mc-highlight mc-baseline">' in multi.html()

    plain = mc.table(ROWS, COLS)
    assert "highlight" not in plain.to_dict() and "baseline" not in plain.to_dict()

    with pytest.raises(mc.ChipError, match="highlight"):
        mc.table(ROWS, COLS, highlight=123)  # type: ignore[arg-type]
    with pytest.raises(mc.ChipError, match="baseline"):
        mc.table(ROWS, COLS, baseline=123)  # type: ignore[arg-type]


def test_tsv_and_jsonl_files(tmp_path) -> None:
    rows = [{"model": "a", "acc": 0.8, "loss": [3, 2, 1]}, {"model": "b", "acc": 0.7}]
    expect = mc.table(rows).text()

    tsv = tmp_path / "r.tsv"
    tsv.write_text("model\tacc\tloss\na\t0.8\t3 2 1\nb\t0.7\t\n", encoding="utf-8")
    assert mc.table(tsv).text() == expect

    jsonl = tmp_path / "r.jsonl"
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n\n", encoding="utf-8")
    assert mc.table(jsonl).text() == expect

    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"model": "a"}\n{not json}\n', encoding="utf-8")
    with pytest.raises(mc.ChipError, match="line 2 is not valid JSON"):
        mc.table(bad)

    with pytest.raises(mc.ChipError, match=r"\.jsonl.*\.tsv"):
        mc.table(tmp_path / "r.yaml")
