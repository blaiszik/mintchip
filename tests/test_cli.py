from __future__ import annotations

import io
import json
import shlex

import pytest

import mintchip as mc
from mintchip.cli import main, run, schema
from mintchip.directives import example_call


def test_kind_commands_take_negative_numbers_and_gaps() -> None:
    assert run(["delta", "-0.2", "0.1"]) == (0, mc.delta(-0.2, 0.1).text() + "\n", "")
    code, out, _ = run(["spark", "1", "nan", "null", "3", "--reference", "-1", "--band", "-1:2"])
    assert code == 0
    assert out == mc.spark([1, None, None, 3], reference=-1, band=(-1, 2)).text() + "\n"


@pytest.mark.parametrize("kind", sorted(mc.REGISTRY))
def test_help_is_generated_with_a_runnable_example(kind: str) -> None:
    k = mc.REGISTRY[kind]
    code, out, _ = run([kind, "--help"])
    assert code == 0 and k.question in out
    flat = " ".join(out.split())
    assert all(" ".join(p.help.split()) in flat for p in k.params)
    assert example_call(kind) in out and k.example_chip().text() in out
    warnings = "".join(f"mintchip: warning: {w}\n" for w in k.example_chip().warnings)
    argv = shlex.split(example_call(kind))[1:]
    assert run(argv) == (0, k.example_chip().text() + "\n", warnings)


def test_output_formats() -> None:
    base = ["ci", "0.08", "0.05:0.11", "--level", "0.95"]
    c = mc.ci(0.08, (0.05, 0.11), level=0.95)
    assert run([*base, "--format", "md"])[1] == f"`{c.text()}`\n"
    assert run([*base, "--format", "ansi"])[1] == c.text(color=True) + "\n"
    assert run([*base, "--format", "svg"])[1].startswith("<svg")
    assert 'class="mc mc-ci"' in run([*base, "--format", "html"])[1]
    assert run([*base, "--ascii"])[1].isascii()
    assert run([*base, "--compact"])[1] == c.text(compact=True) + "\n"
    data = json.loads(run([*base, "--format", "json"])[1])
    assert mc.from_dict(data["spec"]).text() == data["text"] == c.text()
    code, out, err = run([*base, "--format", "markdown"])
    assert (code, out) == (2, "") and "Use --format md" in err


def test_errors_go_to_stderr_with_a_fix_and_exit_2() -> None:
    code, out, err = run(["spark", "1", "2", "--bnd", "0.3:0.4"])
    assert (code, out) == (2, "")
    assert err.startswith("mintchip: error: spark: unknown option --bnd.")
    assert "  fix: Use --band: mintchip spark 1 2 --band 0.3:0.4" in err
    code, out, err = run(["ci", "abc", "0.05:0.11"])
    assert (code, out) == (2, "") and "estimate must be a number" in err
    code, _, err = run(["sprak", "1"])
    assert code == 2 and "Did you mean 'spark'?" in err
    code, _, err = run(["render", "--formt", "md"])
    assert code == 2 and "Did you mean --format?" in err
    code, _, err = run(["num", "3", "--format", "svg"])
    assert code == 2 and "no graphic" in err


def test_warnings_go_to_stderr_and_strict_fails() -> None:
    argv = ["dist", "18.9", "19.4", "19.8", "20.1", "20.3", "20.9", "21.6", "47.8"]
    code, out, err = run(argv)
    assert code == 0 and out and err.startswith("mintchip: warning: ")
    assert run([*argv, "--strict"])[0] == 1


def test_render_reads_stdin_and_files(tmp_path, monkeypatch, capsys) -> None:
    src = "Loss {{spark 3 2 1}} {braces}\r\nkept.\n"
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(src.encode())))
    assert main(["render"]) == 0
    assert capsys.readouterr().out == f"Loss {mc.spark([3, 2, 1]).text()} {{braces}}\r\nkept.\n"
    f = tmp_path / "msg.md"
    f.write_text("{{num 3 unit=ms}}", encoding="utf-8")
    assert run(["render", str(f), "--format", "md"]) == (0, "`3 ms`", "")
    page = run(["render", str(f), "--format", "html"])[1]
    assert page.startswith("<!doctype html>") and "<title>msg</title>" in page
    code, out, err = run(["render", "-"], "x\n{{spark 1 2 bnd=0}}\n")
    assert (code, out) == (2, "")
    assert "line 2, column 1: {{spark 1 2 bnd=0}}: spark: unknown option bnd=." in err
    assert run(["render", str(tmp_path / "nope.md")])[0] == 2


def test_render_check_lints_density() -> None:
    text = "A {{spark 1 2}} B {{spark 2 1}} C {{spark 1 1}}.\n"
    code, out, err = run(["render", "-", "--check"], text)
    assert code == 0 and out == "A 2 (range 1 to 2) ▁█ B 1 (range 1 to 2) █▁ C 1 ▅▅.\n"
    assert "mintchip: check: " in err and "{{spark}} at 1:3" in err
    assert run(["render", "-", "--check", "--strict"], text)[0] == 1


ROWS = [
    {"model": "a", "acc": 0.82, "lift": [0.08, 0.05, 0.11]},
    {"model": "b", "acc": 0.75, "lift": [0.01, -0.02, 0.04]},
]


def test_table_from_file_and_stdin(tmp_path) -> None:
    f = tmp_path / "r.json"
    f.write_text(json.dumps(ROWS), encoding="utf-8")
    cols = ["--col", "model", "--col", "acc:bar:Accuracy", "--col", "lift:ci"]
    expect = mc.table(
        ROWS, {"model": {}, "acc": {"chip": "bar", "header": "Accuracy"},
               "lift": {"chip": "ci", "level": 0.95}}, sort="acc",
    ).text()  # fmt: skip
    argv = [*cols, "--set", "lift.level=0.95", "--sort", "acc"]
    assert run(["table", str(f), *argv]) == (0, expect + "\n", "")
    assert run(["table", "-", *argv], json.dumps(ROWS)) == (0, expect + "\n", "")
    csv_rows = "model,acc\na,0.5\nb,0.7\n"
    code, out, _ = run(["table", "-", "--col", "model", "--col", "acc:bar", "--asc"], csv_rows)
    assert code == 0 and out.index("a ") < out.index("b ")
    code, out, _ = run(["table", "-", "--col", "model", "--col", "acc:bar", "--sort", "model",
                        "--desc"], csv_rows)  # fmt: skip
    assert code == 0 and out.index("b ") < out.index("a ")
    assert run(["table", "-", "--col", "model", "--asc", "--desc"], csv_rows)[0] == 2
    assert run(["table", str(f), *cols, "--format", "md"])[1].startswith("| model")


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--col", "acc:bars"], "Did you mean --col acc:bar?"),
        (["--col", "acc:bar", "--set", "acc.trget=1"], "Did you mean --set acc.target"),
        (["--col", "acc:bar", "--set", "lift.level=1"], "Add --col lift:KIND first"),
        (["--col", "acc", "--set", "acc.target=1"], "Give it a kind"),
        (["--col", "acc:bar", "--sort", "accuracy"], "sort key 'accuracy'"),
    ],
)
def test_table_errors(tmp_path, argv: list[str], message: str) -> None:
    f = tmp_path / "r.json"
    f.write_text(json.dumps(ROWS), encoding="utf-8")
    code, out, err = run(["table", str(f), *argv])
    assert (code, out) == (2, "") and message in err


def test_schema() -> None:
    one = schema("ci")
    assert one["$schema"].endswith("2020-12/schema")
    assert one["required"] == ["chip", "estimate", "interval"]
    assert one["properties"]["reference"]["type"] == ["number", "null"]
    full = json.loads(run(["schema"])[1])
    assert [r["$ref"] for r in full["oneOf"]] == [f"#/$defs/{e['name']}" for e in mc.CATALOG]
    for name, s in full["$defs"].items():
        ex = s["examples"][0]
        assert ex["chip"] == s["properties"]["chip"]["const"] == name
        assert set(s["required"]) <= set(ex) and set(ex) <= set(s["properties"])
    assert run(["schema", "sprak"])[0] == 2


def test_render_check_quotes_the_sentence_as_written() -> None:
    text = "Tests: {{strip pass fail}} then {{strip pass}} and {{strip fail}} and {{strip pass}}.\n"
    err = run(["render", "-", "--check"], text)[2].splitlines()
    assert err[0] == (
        'mintchip: check: "Tests: {{strip pass fail}} then {{strip …" has 4 chips '
        "(at 1:8, 1:33, 1:52, 1:71); keep one or two per sentence, or use a table."
    )


def test_python_dash_m_and_sort_help() -> None:
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, "-m", "mintchip", "num", "0.5"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0 and done.stdout == "0.5\n"
    from mintchip.guide import guide_text

    assert "python -m mintchip`" in guide_text()
    out = " ".join(run(["table", "--help"])[1].split())
    assert "largest first; text A to Z" in out
    rows = '[{"m": "b"}, {"m": "a"}]'
    assert run(["table", "-", "--col", "m", "--sort", "m"], rows)[1].split()[-2:] == ["a", "b"]
