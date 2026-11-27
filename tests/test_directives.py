from __future__ import annotations

import pytest

import mintchip as mc
from mintchip.directives import (
    DirectiveError,
    call_text,
    example_call,
    parse_tokens,
    render,
    spec_tokens,
)


@pytest.mark.parametrize("kind", sorted(mc.REGISTRY))
@pytest.mark.parametrize("style", ["cli", "directive"])
def test_every_example_round_trips_through_tokens(kind: str, style: str) -> None:
    k = mc.REGISTRY[kind]
    toks = spec_tokens(kind, k.example, style=style)
    rebuilt = k.fn(**parse_tokens(kind, toks, style=style))
    assert rebuilt.to_dict() == k.example_chip().to_dict()
    if style == "directive":
        assert render(call_text(kind, toks, style))[0] == k.example_chip().text()


def test_token_grammar() -> None:
    assert parse_tokens("delta", ["-0.2", "0.1"]) == {"before": -0.2, "after": 0.1}
    kw = parse_tokens("spark", ["1", "2,", "nan", "null", "−3", "--reference", "-1"])
    assert kw == {"values": [1.0, 2.0, None, None, -3.0], "reference": -1.0}
    assert parse_tokens("spark", ["1", "band=-0.5:-0.1"])["band"] == (-0.5, -0.1)
    assert parse_tokens("ci", ["0.1", "0:1", "reference=none"])["reference"] is None
    assert parse_tokens("delta", ["1", "2", "--no-higher-is-better"])["higher_is_better"] is False
    assert parse_tokens("delta", ["1", "2", "higher_is_better=true"])["higher_is_better"] is True
    assert parse_tokens("strip", ["pass", "fail", "true", "null"])["values"] == [
        "pass", "fail", True, None,
    ]  # fmt: skip
    kw = parse_tokens("timeline", ["a=0:1", "b=0.5:2", "unit=ms"])
    assert kw == {"stages": {"a": (0.0, 1.0), "b": (0.5, 2.0)}, "unit": "ms"}
    kw = parse_tokens("spark", ["1", "2", "--vs", "3", "4", "--label", "x"])
    assert kw == {"values": [1.0, 2.0], "vs": [3.0, 4.0], "label": "x"}


@pytest.mark.parametrize(
    ("kind", "tokens", "message", "fix"),
    [
        ("spark", ["1", "2", "--bnd", "0.3:0.4"], "unknown option --bnd", "--band 0.3:0.4"),
        ("ci", ["0.08", "0.11:0.05"], "lo <= hi", "mintchip ci 0.08 0.05:0.11"),
        ("ci", ["0.08", "0.05-0.11"], "with a colon", "mintchip ci 0.08 0.05:0.11"),
        ("gauge", ["7.4", "--normal", "7.35", "7.45"], "one lo:hi", "--normal 7.35:7.45"),
        ("bar", ["82%"], "plain number", "0.82"),
        ("spark", ["1", "--label", "Val", "loss"], "got 'loss'", "--label 'Val loss'"),
        ("delta", ["1", "2", "3"], "left over", "BEFORE AFTER"),
        ("spark", [], "missing values", "mintchip spark 1.84"),
    ],
)
def test_errors_name_the_fix(kind: str, tokens: list[str], message: str, fix: str) -> None:
    with pytest.raises(mc.ChipError) as e:
        parse_tokens(kind, tokens)
    assert e.value.message.startswith(f"mintchip.{kind}: ")
    assert message in e.value.message and fix in (e.value.fix_hint or "")


def test_text_outside_directives_is_untouched() -> None:
    src = 'a {x} }} \\{{lit}}\r\n{{num 3 unit=ms}}, {{ {"chip": "num", "value": 4} }}.\r\n'
    out, found = render(src)
    assert out == "a {x} }} {{lit}}\r\n3 ms, 4.\r\n"
    assert [(d.line, d.col) for d in found] == [(2, 1), (2, 20)]
    assert render("x {{num 3}} y", format="md")[0] == "x `3` y"
    assert "\x1b[" in render("{{spark 1 3 2}}", format="ansi")[0]
    assert render("{{spark 1 3 2}}", format="text", ascii=True)[0].isascii()


def test_malformed_directives_report_line_column_and_correction() -> None:
    src = "ok {{num 1}}\n  {{sprak 1 2}} and {{ci 0.1 0.2:0.1}}\n{{spark 1 2.\n"
    with pytest.raises(DirectiveError) as e:
        render(src)
    errs = e.value.errors
    assert [w.split(":")[0] for w, _ in errs] == [
        "line 2, column 3", "line 2, column 21", "line 3, column 1",
    ]  # fmt: skip
    assert errs[0][1].fix_hint == "Write {{spark 1 2}}"
    assert errs[1][1].fix_hint.endswith("{{ci 0.1 0.1:0.2}}")
    assert "{{spark 1 2}}." in errs[2][1].fix_hint
    with pytest.raises(DirectiveError, match="bad JSON"):
        render('{{ {"chip": "num",} }}')
    with pytest.raises(DirectiveError, match="unknown option bnd="):
        render("{{spark 1 2 bnd=0.3:0.4}}")


def test_same_unit_chips_share_a_scale() -> None:
    _, found = render("{{ci 1 0:2 unit=ms}} vs {{ci 10 9:11 unit=ms}} vs {{ci 1 0:2}}")
    assert found[0].domain == found[1].domain is not None
    assert found[2].domain is None


def test_html_is_a_full_page() -> None:
    out, _ = render("<b> & {{num 3 unit=ms}}\n\nsecond", format="html", title="T")
    assert out.startswith("<!doctype html>") and "<title>T</title>" in out
    assert "&lt;b&gt; &amp; " in out and out.count("<p>") >= 2 and "mc-num" in out


def test_html_fragment_and_top_level_render_export() -> None:
    assert mc.render is render and "render" in mc.__all__
    frag, found = mc.render("<b> & {{num 3 unit=ms}}\n\nsecond {{spark 1 3 2}}", format="html", fragment=True)
    assert len(found) == 2
    assert "<!doctype" not in frag.lower() and "<html" not in frag and "<style>" not in frag
    assert frag.startswith("<p>&lt;b&gt; &amp; ") and frag.count("<p>") == 2
    assert "mc-num" in frag and "mc-spark" in frag and "popover" in frag
    dark_frag, _ = mc.render("{{spark 1 3 2}}", format="html", fragment=True, theme="dark")
    assert "currentColor" not in dark_frag and "mc-spark" in dark_frag


def test_example_calls() -> None:
    assert example_call("ci") == "mintchip ci 0.08 0.05:0.11 --level 0.95 --label 'Retrieval lift'"
    assert (
        example_call("ci", "directive") == '{{ci 0.08 0.05:0.11 level=0.95 label="Retrieval lift"}}'
    )


def test_code_blocks_and_inline_code_spans_are_skipped() -> None:
    doc = (
        "Run `${{ github.sha }}` and ``{{ jinja_var }}`` -> {{num 42 unit=ms}}.\n"
        "```yaml\n"
        "run: echo ${{ github.sha }}\n"
        "{{not a chip}}\n"
        "```\n"
        "~~~jsx\n"
        "<div style={{ color: 'red' }} />\n"
        "~~~\n"
        "Lone ` backtick then {{num 7}}.\n"
    )
    out, found = render(doc)
    assert len(found) == 2
    assert "`${{ github.sha }}`" in out
    assert "``{{ jinja_var }}``" in out
    assert "run: echo ${{ github.sha }}" in out
    assert "{{not a chip}}" in out
    assert "<div style={{ color: 'red' }} />" in out
    assert "-> 42 ms." in out
    assert "Lone ` backtick then 7." in out


def test_render_accepts_markdown_alias() -> None:
    assert render("x {{num 3}} y", format="markdown") == render("x {{num 3}} y", format="md")
