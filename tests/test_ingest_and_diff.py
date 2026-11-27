"""Tests for zero-dep SWE ingestors (``mintchip from``) and benchmark diffing (``mintchip diff``)."""

from __future__ import annotations

import json
from pathlib import Path

from mintchip.cli import run
from mintchip.ingest import detect_format, ingest

GIT_NUMSTAT = """\
42\t8\tsrc/mintchip/cli.py
15\t5\tsrc/mintchip/skill.py
30\t10\ttests/test_skill.py
12\t3\tdocs/guide.md
5\t0\tpyproject.toml
-\t-\tgallery/output/opener.gif
"""

HYPERFINE_BASE = {
    "results": [
        {
            "command": "parse_fast",
            "mean": 0.010,
            "stddev": 0.0004,
            "times": [0.0096, 0.0099, 0.0100, 0.0102, 0.0103],
        },
        {
            "command": "parse_full",
            "mean": 0.025,
            "stddev": 0.0008,
            "times": [0.0241, 0.0248, 0.0250, 0.0254, 0.0257],
        },
    ]
}

HYPERFINE_HEAD = {
    "results": [
        {
            "command": "parse_fast",
            "mean": 0.008,
            "stddev": 0.0003,
            "times": [0.0077, 0.0079, 0.0080, 0.0081, 0.0083],
        },
        {
            "command": "parse_full",
            "mean": 0.030,
            "stddev": 0.0009,
            "times": [0.0290, 0.0297, 0.0300, 0.0304, 0.0309],
        },
    ]
}

PYTEST_BENCH_BASE = {
    "benchmarks": [
        {
            "name": "test_encode",
            "stats": {"mean": 0.0020, "stddev": 0.0001, "rounds": 50},
        },
        {
            "name": "test_decode",
            "stats": {"mean": 0.0040, "stddev": 0.0002, "rounds": 50},
        },
    ]
}

PYTEST_BENCH_HEAD = {
    "benchmarks": [
        {
            "name": "test_encode",
            "stats": {"mean": 0.0018, "stddev": 0.0001, "rounds": 50},
        },
        {
            "name": "test_decode",
            "stats": {"mean": 0.0048, "stddev": 0.0002, "rounds": 50},
        },
    ]
}

GO_BENCH_BASE = """\
goos: darwin
goarch: arm64
BenchmarkParse-8        100000      11420 ns/op       4096 B/op       42 allocs/op
BenchmarkRender-8       500000       2310 ns/op        512 B/op        8 allocs/op
PASS
"""

GO_BENCH_HEAD = """\
BenchmarkParse-16       100000      13000 ns/op       4096 B/op       42 allocs/op
BenchmarkRender-16      500000       2000 ns/op        512 B/op        8 allocs/op
"""

CARGO_BENCH_BASE = """\
running 2 tests
test bench_parse  ... bench:      12,000 ns/iter (+/- 400)
test bench_render ... bench:       2,500 ns/iter (+/- 100)
"""

CARGO_BENCH_HEAD = """\
running 2 tests
test bench_parse  ... bench:      10,800 ns/iter (+/- 350)
test bench_render ... bench:       2,900 ns/iter (+/- 120)
"""

JUNIT_SINGLE = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuite name="unit" tests="4" failures="1" skipped="1">
  <testcase name="test_ok_1"/>
  <testcase name="test_ok_2"/>
  <testcase name="test_bad"><failure message="boom"/></testcase>
  <testcase name="test_skip"><skipped/></testcase>
</testsuite>
"""

JUNIT_MULTI = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="core" tests="3">
    <testcase name="a"/>
    <testcase name="b"/>
    <testcase name="c"/>
  </testsuite>
  <testsuite name="cli" tests="3">
    <testcase name="d"/>
    <testcase name="e"><failure message="fail"/></testcase>
    <testcase name="f"><skipped/></testcase>
  </testsuite>
</testsuites>
"""


def test_ingest_git_diff_and_auto() -> None:
    assert detect_format(GIT_NUMSTAT) == "git-diff"
    chip = ingest(GIT_NUMSTAT, fmt="git-diff")
    assert chip.label == "Changed lines"
    code, out, err = run(["from", "git-diff"], GIT_NUMSTAT)
    assert (code, err) == (0, "")
    assert "54·31·12" in out
    assert "%" in out

    code2, out2, _ = run(["from", "auto", "--ascii"], GIT_NUMSTAT)
    assert code2 == 0 and out2.isascii()

    code3, out3, _ = run(["from", "git-diff", "--format", "md"], GIT_NUMSTAT)
    assert code3 == 0 and out3.startswith("`")


def test_ingest_hyperfine_all_output_formats(tmp_path: Path) -> None:
    f = tmp_path / "hf.json"
    f.write_text(json.dumps(HYPERFINE_BASE), encoding="utf-8")
    assert detect_format(f.read_text(encoding="utf-8")) == "hyperfine"

    for fmt in ("text", "ansi", "md", "html", "json"):
        code, out, err = run(["from", "hyperfine", str(f), "--format", fmt])
        assert (code, err) == (0, ""), (fmt, err)
        assert "parse_fast" in out
        if fmt == "json":
            parsed = json.loads(out)
            assert "columns" in parsed and "rows" in parsed
        elif fmt == "md":
            assert out.startswith("| Command")
        elif fmt == "html":
            assert "<table" in out

    code_auto, out_auto, _ = run(["from", "auto", str(f), "--ascii"])
    assert code_auto == 0 and out_auto.isascii()


def test_ingest_pytest_go_cargo_bench() -> None:
    pb = json.dumps(PYTEST_BENCH_BASE)
    assert detect_format(pb) == "pytest-bench"
    code, out, err = run(["from", "pytest-bench"], pb)
    assert (code, err) == (0, "")
    assert "test_encode" in out and "ms" in out

    assert detect_format(GO_BENCH_BASE) == "go-bench"
    code, out, err = run(["from", "go-bench"], GO_BENCH_BASE)
    assert (code, err) == (0, "")
    assert "BenchmarkParse" in out and "B/op" in out

    # Multi-run go-bench produces dist column
    multi_go = GO_BENCH_BASE + "\n" + GO_BENCH_BASE.replace("11420", "11600").replace("2310", "2400")
    tbl = ingest(multi_go, fmt="go-bench")
    assert any(c.kind == "dist" for c in tbl.columns)

    assert detect_format(CARGO_BENCH_BASE) == "cargo-bench"
    code, out, err = run(["from", "cargo-bench", "--strict"], CARGO_BENCH_BASE)
    assert (code, err) == (0, "")
    assert "bench_parse" in out and "bench_render" in out


def test_ingest_junit_single_and_multi() -> None:
    assert detect_format(JUNIT_SINGLE) == "junit"
    code, out, err = run(["from", "junit"], JUNIT_SINGLE)
    assert (code, err) == (0, "")
    assert "2/4 pass" in out and "1 fail" in out

    code, out, err = run(["from", "auto"], JUNIT_MULTI)
    assert (code, err) == (0, "")
    assert "core" in out and "cli" in out and "Suite" in out


def test_ingest_errors() -> None:
    code, out, err = run(["from", "unknown-tool"], "hello")
    assert (code, out) == (2, "") and "unknown format" in err

    code, out, err = run(["from", "auto"], "totally unrecognized text")
    assert (code, out) == (2, "") and "could not detect" in err


def test_diff_hyperfine_with_ci_and_regression_gate(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    base.write_text(json.dumps(HYPERFINE_BASE), encoding="utf-8")
    head.write_text(json.dumps(HYPERFINE_HEAD), encoding="utf-8")

    # Without gate -> exits 0, shows table + 95% CI + takeaway
    code, out, err = run(["diff", str(base), str(head)])
    assert (code, err) == (0, "")
    assert "95% CI" in out
    assert "parse_fast" in out and "parse_full" in out
    assert "Compared 2 benchmarks" in out
    assert "worst regression parse_full (+20.0%" in out

    # Gate at 10% -> parse_full regressed +20% -> exits 1
    code, out, err = run(["diff", str(base), str(head), "--fail-on-regression", "10"])
    assert code == 1
    assert "FAILED >10% gate" in out
    assert "regression exceeded 10% threshold" in err

    # Gate at 25% -> passes (exits 0)
    code, out, err = run(["diff", str(base), str(head), "--fail-on-regression", "25"])
    assert (code, err) == (0, "")

    # JSON, Markdown, HTML, ASCII formats
    code_j, out_j, _ = run(["diff", str(base), str(head), "--format", "json", "--fail-on-regression", "10"])
    assert code_j == 1
    data = json.loads(out_j)
    assert data["failed"] is True
    assert [r["name"] for r in data["regressions"]] == ["parse_full"]
    assert len(data["rows"]) == 2 and data["rows"][0]["ci"] is not None

    code_m, out_m, _ = run(["diff", str(base), str(head), "--format", "md"])
    assert code_m == 0 and out_m.startswith("| Benchmark")

    code_h, out_h, _ = run(["diff", str(base), str(head), "--format", "html"])
    assert code_h == 0 and "<table" in out_h and "mc-takeaway" in out_h

    code_a, out_a, _ = run(["diff", str(base), str(head), "--ascii"])
    assert code_a == 0 and out_a.isascii()


def test_diff_pytest_go_cargo_csv_and_generic_json(tmp_path: Path) -> None:
    # pytest-bench
    p1, p2 = tmp_path / "pb1.json", tmp_path / "pb2.json"
    p1.write_text(json.dumps(PYTEST_BENCH_BASE), encoding="utf-8")
    p2.write_text(json.dumps(PYTEST_BENCH_HEAD), encoding="utf-8")
    code, out, _ = run(["diff", str(p1), str(p2), "--fail-on-regression", "10"])
    assert code == 1 and "test_decode" in out and "95% CI" in out

    # go-bench (matches across -8 and -16 GOMAXPROCS suffixes!)
    g1, g2 = tmp_path / "g1.txt", tmp_path / "g2.txt"
    g1.write_text(GO_BENCH_BASE, encoding="utf-8")
    g2.write_text(GO_BENCH_HEAD, encoding="utf-8")
    code, out, _ = run(["diff", str(g1), str(g2), "--fail-on-regression", "10"])
    assert code == 1 and "BenchmarkParse" in out

    # cargo-bench
    c1, c2 = tmp_path / "c1.txt", tmp_path / "c2.txt"
    c1.write_text(CARGO_BENCH_BASE, encoding="utf-8")
    c2.write_text(CARGO_BENCH_HEAD, encoding="utf-8")
    code, out, _ = run(["diff", str(c1), str(c2), "--fail-on-regression", "10"])
    assert code == 1 and "bench_render" in out and "95% CI" in out

    # CSV with higher-is-better throughput/accuracy
    csv1, csv2 = tmp_path / "acc1.csv", tmp_path / "acc2.csv"
    csv1.write_text("name,accuracy\nmodel_a,0.85\nmodel_b,0.80\n", encoding="utf-8")
    csv2.write_text("name,accuracy\nmodel_a,0.88\nmodel_b,0.70\n", encoding="utf-8")
    code, out, _ = run(["diff", str(csv1), str(csv2), "--fail-on-regression", "5"])
    assert code == 1 and "model_b" in out

    # Generic JSON mapping
    j1, j2 = tmp_path / "j1.json", tmp_path / "j2.json"
    j1.write_text(json.dumps({"step_a": 100.0, "step_b": 200.0}), encoding="utf-8")
    j2.write_text(json.dumps({"step_a": 90.0, "step_b": 180.0}), encoding="utf-8")
    code, out, err = run(["diff", str(j1), str(j2), "--fail-on-regression", "5"])
    assert (code, err) == (0, "") and "2 improved, 0 regressed" in out
