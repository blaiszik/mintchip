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
    assert code == 0
    assert "54·31·12" in out
    assert "%" in out
    assert err == "" or "half-height" in err

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


def test_diff_direction_ci_noise_mixed_units_and_missing_warnings(tmp_path: Path) -> None:
    # 1. Generic JSON accuracy/throughput infers higher_is_better from metric name
    a1, a2 = tmp_path / "a1.json", tmp_path / "a2.json"
    a1.write_text(json.dumps({"accuracy": 0.80}), encoding="utf-8")
    a2.write_text(json.dumps({"accuracy": 0.85}), encoding="utf-8")
    code, out, err = run(["diff", str(a1), str(a2), "--fail-on-regression", "1"])
    assert (code, err) == (0, "") and "1 improved, 0 regressed" in out

    m1, m2 = tmp_path / "m1.json", tmp_path / "m2.json"
    m1.write_text(json.dumps([{"metric": "accuracy", "value": 0.80}]), encoding="utf-8")
    m2.write_text(json.dumps([{"metric": "accuracy", "value": 0.85}]), encoding="utf-8")
    code, out, err = run(["diff", str(m1), str(m2), "--fail-on-regression", "1"])
    assert (code, err) == (0, "") and "1 improved, 0 regressed" in out

    # 2. CI crossing 0 is classified as noise (unchanged), does not fail gate unless --no-ci-gate
    n1, n2 = tmp_path / "n1.json", tmp_path / "n2.json"
    n1.write_text(
        json.dumps([{"name": "noisy", "mean": 10.0, "stddev": 3.0, "n": 5, "unit": "ms"}]),
        encoding="utf-8",
    )
    n2.write_text(
        json.dumps([{"name": "noisy", "mean": 11.0, "stddev": 3.0, "n": 5, "unit": "ms"}]),
        encoding="utf-8",
    )
    code, out, err = run(["diff", str(n1), str(n2), "--fail-on-regression", "5"])
    assert (code, err) == (0, "") and "0 regressed, 1 unchanged" in out

    code_ng, out_ng, _ = run(
        ["diff", str(n1), str(n2), "--fail-on-regression", "5", "--no-ci-gate"]
    )
    assert code_ng == 1 and "1 regressed" in out_ng

    # 3. Mixed units / >100x unitless span disables shared delta/ci scale
    mix1, mix2 = tmp_path / "mix1.json", tmp_path / "mix2.json"
    mix1.write_text(
        json.dumps([
            {"name": "accuracy", "value": 0.80, "unit": "%"},
            {"name": "latency", "value": 25.0, "unit": "ms"},
        ]),
        encoding="utf-8",
    )
    mix2.write_text(
        json.dumps([
            {"name": "accuracy", "value": 0.82, "unit": "%"},
            {"name": "latency", "value": 20.0, "unit": "ms"},
        ]),
        encoding="utf-8",
    )
    from mintchip.diff import diff_benchmarks, load_benchmark_entries

    res_mix = diff_benchmarks(
        load_benchmark_entries(mix1.read_text()),
        load_benchmark_entries(mix2.read_text()),
    )
    assert res_mix.table.columns[3].share is False

    wide1 = load_benchmark_entries(json.dumps({"accuracy": 0.80, "throughput": 5000.0}))
    wide2 = load_benchmark_entries(json.dumps({"accuracy": 0.85, "throughput": 5500.0}))
    res_wide = diff_benchmarks(wide1, wide2)
    assert res_wide.table.columns[3].share is False

    # 4. Missing benchmarks in BASE emit warning in DiffResult.warnings and on stderr
    b1, b2 = tmp_path / "b1.json", tmp_path / "b2.json"
    b1.write_text(json.dumps({"kept": 10.0, "dropped_bench": 20.0}), encoding="utf-8")
    b2.write_text(json.dumps({"kept": 9.0}), encoding="utf-8")
    code, out, err = run(["diff", str(b1), str(b2)])
    assert code == 0 and "missing from HEAD" in err and "dropped_bench" in err

    # 5. Diff full HTML vs --fragment, -o, and --format md --ascii
    html_out = tmp_path / "diff.html"
    code, out, err = run(["diff", str(a1), str(a2), "--format", "html", "-o", str(html_out)])
    assert (code, out, err) == (0, "", "")
    h = html_out.read_text(encoding="utf-8")
    assert h.startswith("<!doctype html>") and '<meta charset="utf-8">' in h and "mc-takeaway" in h

    code, frag, err = run(["diff", str(a1), str(a2), "--format", "html", "--fragment"])
    assert (code, err) == (0, "") and frag.startswith("<table") and "<!doctype" not in frag.lower()

    code, md_a, err = run(["diff", str(a1), str(a2), "--format", "markdown", "--ascii"])
    assert (code, err) == (0, "") and md_a.isascii()


def test_ingest_github_actions_k6_esbuild_chrome_trace(tmp_path: Path) -> None:
    # 1. github-actions: single job with steps -> timeline, multi-job with steps -> table
    gha_single = json.dumps({
        "jobs": [
            {
                "name": "ci",
                "conclusion": "success",
                "started_at": "2026-01-15T10:00:00Z",
                "completed_at": "2026-01-15T10:01:00Z",
                "steps": [
                    {"name": "Checkout", "started_at": "2026-01-15T10:00:00Z", "completed_at": "2026-01-15T10:00:08Z"},
                    {"name": "Test", "started_at": "2026-01-15T10:00:08Z", "completed_at": "2026-01-15T10:00:50Z"},
                    {"name": "Upload", "started_at": "2026-01-15T10:00:50Z", "completed_at": "2026-01-15T10:01:00Z"},
                ],
            }
        ]
    })
    assert detect_format(gha_single) == "github-actions"
    chip = ingest(gha_single, fmt="auto")
    assert chip.kind == "timeline" and "Test" in chip.text()

    gha_multi = json.dumps({
        "jobs": [
            {
                "name": "lint",
                "conclusion": "success",
                "startedAt": "2026-01-15T10:00:00Z",
                "completedAt": "2026-01-15T10:00:20Z",
                "steps": [
                    {"name": "Checkout", "startedAt": "2026-01-15T10:00:00Z", "completedAt": "2026-01-15T10:00:05Z"},
                    {"name": "Ruff", "startedAt": "2026-01-15T10:00:05Z", "completedAt": "2026-01-15T10:00:20Z"},
                ],
            },
            {
                "name": "test",
                "conclusion": "success",
                "startedAt": "2026-01-15T10:00:00Z",
                "completedAt": "2026-01-15T10:00:45Z",
                "steps": [
                    {"name": "Checkout", "startedAt": "2026-01-15T10:00:00Z", "completedAt": "2026-01-15T10:00:05Z"},
                    {"name": "Pytest", "startedAt": "2026-01-15T10:00:05Z", "completedAt": "2026-01-15T10:00:45Z"},
                ],
            },
        ]
    })
    code, out, err = run(["from", "auto"], gha_multi)
    assert (code, err) == (0, "") and "lint" in out and "test" in out

    # 2. k6 summary JSON (single -> dist, multi -> table)
    k6_single = json.dumps({
        "metrics": {
            "http_req_duration": {
                "values": {"avg": 24.5, "min": 8.1, "med": 21.3, "max": 142.0, "p(90)": 41.2, "p(95)": 56.8}
            },
            "http_reqs": {"count": 1200, "rate": 40.0},
        }
    })
    assert detect_format(k6_single) == "k6"
    k6_chip = ingest(k6_single, fmt="auto")
    assert k6_chip.kind == "dist" and "21.3 ms" in k6_chip.text()

    k6_multi = json.dumps({
        "metrics": {
            "http_req_duration": {"avg": 24.5, "min": 8.1, "med": 21.3, "max": 142.0, "p(90)": 41.2, "p(95)": 56.8},
            "http_req_waiting": {"avg": 22.1, "min": 7.5, "med": 19.8, "max": 135.0, "p(90)": 38.0, "p(95)": 52.4},
        }
    })
    code, out, err = run(["from", "k6"], k6_multi)
    assert code == 0 and "http_req_duration" in out and "http_req_waiting" in out

    # 3. esbuild metafile JSON (single -> share, multi -> table)
    esb_single = json.dumps({
        "inputs": {"src/app.ts": {"bytes": 14200}, "node_modules/react/index.js": {"bytes": 42000}},
        "outputs": {
            "dist/app.js": {
                "bytes": 58400,
                "inputs": {
                    "src/app.ts": {"bytesInOutput": 12400},
                    "node_modules/react/index.js": {"bytesInOutput": 41000},
                    "node_modules/@scope/ui/btn.js": {"bytesInOutput": 5000},
                },
            },
            "dist/app.js.map": {"bytes": 90000, "inputs": {}},
        },
    })
    assert detect_format(esb_single) == "esbuild"
    esb_chip = ingest(esb_single, fmt="auto")
    assert esb_chip.kind == "share" and "react" in esb_chip.alt and "KB" in esb_chip.facts[0]

    esb_multi = json.dumps({
        "inputs": {},
        "outputs": {
            "dist/app.js": {"bytes": 50000, "inputs": {"src/a.ts": {"bytesInOutput": 30000}, "node_modules/pkg/i.js": {"bytesInOutput": 20000}}},
            "dist/worker.js": {"bytes": 25000, "inputs": {"src/w.ts": {"bytesInOutput": 25000}}},
        },
    })
    code, out, err = run(["from", "esbuild", "--format", "md", "--ascii"], esb_multi)
    assert (code, err) == (0, "") and out.isascii() and "dist/app.js" in out and "dist/worker.js" in out

    # 4. chrome-trace JSON (object form X events -> timeline, array form repeated B/E -> table)
    ct_obj = json.dumps({
        "traceEvents": [
            {"name": "fetch", "ph": "X", "ts": 1000, "dur": 1200, "pid": 1, "tid": 1},
            {"name": "parse", "ph": "X", "ts": 2200, "dur": 4800, "pid": 1, "tid": 1},
            {"name": "render", "ph": "X", "ts": 7000, "dur": 1500, "pid": 1, "tid": 1},
        ]
    })
    assert detect_format(ct_obj) == "chrome-trace"
    ct_chip = ingest(ct_obj, fmt="auto")
    assert ct_chip.kind == "timeline" and "parse" in ct_chip.text()

    ct_arr = json.dumps([
        {"name": "decode", "ph": "B", "ts": 1000, "pid": 1, "tid": 1},
        {"name": "decode", "ph": "E", "ts": 2200, "pid": 1, "tid": 1},
        {"name": "decode", "ph": "B", "ts": 3000, "pid": 1, "tid": 1},
        {"name": "decode", "ph": "E", "ts": 4500, "pid": 1, "tid": 1},
        {"name": "render", "ph": "X", "ts": 5000, "dur": 2000, "pid": 1, "tid": 1},
    ])
    assert detect_format(ct_arr) == "chrome-trace"
    code, out, err = run(["from", "auto"], ct_arr)
    assert (code, err) == (0, "") and "decode" in out and "Calls" in out

    # 5. `from` full HTML vs --fragment and -o
    html_file = tmp_path / "from.html"
    code, out, err = run(["from", "chrome-trace", "--format", "html", "-o", str(html_file)], ct_obj)
    assert (code, out, err) == (0, "", "")
    txt = html_file.read_text(encoding="utf-8")
    assert txt.startswith("<!doctype html>") and '<meta charset="utf-8">' in txt
    code, frag, err = run(["from", "chrome-trace", "--format", "html", "--fragment"], ct_obj)
    assert (code, err) == (0, "") and "<!doctype" not in frag.lower() and "mc-timeline" in frag
