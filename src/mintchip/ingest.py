"""Zero-dependency SWE tool ingestors for ``mintchip from <format> [FILE|-]``.

Converts standard developer tool outputs directly into ``mintchip`` chips or shared-scale
tables using only the Python standard library:

- ``git-diff``: ``git diff --numstat`` -> ``share`` chip of changed lines by top-level area
- ``hyperfine``: ``hyperfine --export-json`` -> ``table`` with ``num`` mean + ``dist``
- ``pytest-bench``: ``pytest-benchmark`` JSON -> ``table`` with ``num`` + ``ci`` or ``bar``
- ``go-bench``: ``go test -bench`` text -> ``table``
- ``cargo-bench``: ``cargo bench`` text -> ``table``
- ``junit``: JUnit XML -> ``strip`` chip (1 suite) or ``table`` with ``strip`` + ``bar``
- ``auto``: auto-detect any of the above from input content
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import mintchip as mc

from .spec import Chip, ChipError

__all__ = [
    "INGEST_FORMATS",
    "BenchEntry",
    "add_from_parser",
    "cmd_from",
    "detect_format",
    "ingest",
    "parse_cargo_bench",
    "parse_git_diff",
    "parse_go_bench",
    "parse_hyperfine",
    "parse_junit",
    "parse_pytest_bench",
]

INGEST_FORMATS: tuple[str, ...] = (
    "auto",
    "git-diff",
    "hyperfine",
    "pytest-bench",
    "go-bench",
    "cargo-bench",
    "junit",
)

OUTPUT_FORMATS: tuple[str, ...] = ("text", "ansi", "md", "html", "json")

_TIME_TO_SEC: dict[str, float] = {
    "ns": 1e-9,
    "us": 1e-6,
    "µs": 1e-6,
    "μs": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
}

_GIT_NUMSTAT_RE = re.compile(r"^(\d+|-)\t(\d+|-)\t(.+)$")
_GO_BENCH_RE = re.compile(
    r"^(Benchmark\S+)\s+(\d+)\s+([0-9]+(?:\.[0-9]+)?)\s+(ns|us|µs|μs|ms|s)/op"
    r"(?:\s+([0-9]+(?:\.[0-9]+)?)\s+B/op)?"
    r"(?:\s+(\d+)\s+allocs/op)?"
)
_CARGO_BENCH_RE = re.compile(
    r"^test\s+(\S+)\s+\.\.\.\s+bench:\s+([0-9,]+(?:\.[0-9]+)?)\s+"
    r"(ns|us|µs|μs|ms|s)/iter\s+\(\+/-\s+([0-9,]+(?:\.[0-9]+)?)\)"
)
_RENAME_BRACE_RE = re.compile(r"\{[^{}]*?\s*=>\s*([^{}]*?)\}")


@dataclass(frozen=True)
class BenchEntry:
    """Normalized benchmark observation shared between ``ingest`` and ``diff``."""

    name: str
    value: float
    unit: str | None = None
    samples: tuple[float, ...] = ()
    stddev: float | None = None
    n: int | None = None
    ci: tuple[float, float] | None = None
    higher_is_better: bool = False
    extra: tuple[tuple[str, float], ...] = ()


def pick_time_unit(seconds: Sequence[float]) -> tuple[float, str]:
    """Choose a clean display multiplier and unit string for a list of durations in seconds."""
    vals = [abs(v) for v in seconds if v is not None and math.isfinite(v)]
    peak = max(vals, default=0.0)
    if peak == 0.0:
        return 1.0, "s"
    if peak < 1e-6:
        return 1e9, "ns"
    if peak < 1e-3:
        return 1e6, "us"
    if peak < 1.0:
        return 1e3, "ms"
    return 1.0, "s"


def _normalize_git_path(raw: str) -> str:
    path = raw.strip()
    if "=>" in path:
        if "{" in path and "}" in path:
            path = _RENAME_BRACE_RE.sub(r"\1", path)
        else:
            path = path.split("=>")[-1].strip()
    path = path.strip('"').strip("/")
    return re.sub(r"/+", "/", path)


def _top_area(path: str) -> str:
    norm = _normalize_git_path(path)
    if "/" not in norm:
        return "root"
    return norm.split("/", 1)[0] or "root"


# --- parsers returning normalized data -------------------------------------------------------
def parse_git_diff(text: str) -> dict[str, int]:
    """Parse ``git diff --numstat`` output into ``{top_level_area: changed_lines}``."""
    totals: dict[str, int] = defaultdict(int)
    matched = 0
    for line in text.splitlines():
        m = _GIT_NUMSTAT_RE.match(line.strip("\r\n"))
        if not m:
            continue
        matched += 1
        added_s, deleted_s, path = m.groups()
        if added_s == "-" or deleted_s == "-":
            continue
        changed = int(added_s) + int(deleted_s)
        if changed > 0:
            totals[_top_area(path)] += changed
    if matched == 0:
        raise ChipError(
            "mintchip from git-diff: no git diff --numstat lines found.",
            fix_hint="Pipe output from: git diff --numstat | mintchip from git-diff",
        )
    if not totals:
        raise ChipError(
            "mintchip from git-diff: all matched files had 0 changed text lines.",
            fix_hint="Run git diff --numstat against a commit with text changes.",
        )
    return dict(totals)


def parse_hyperfine(text: str) -> list[BenchEntry]:
    """Parse ``hyperfine --export-json`` into normalized :class:`BenchEntry` records (seconds)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ChipError(
            f"mintchip from hyperfine: invalid JSON (line {e.lineno}: {e.msg}).",
            fix_hint="Pass a file created with: hyperfine --export-json bench.json ...",
        ) from None
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list) or not results:
        raise ChipError(
            "mintchip from hyperfine: expected a JSON object with a non-empty 'results' list.",
            fix_hint="Pass output from: hyperfine --export-json bench.json ...",
        )
    entries: list[BenchEntry] = []
    for i, item in enumerate(results):
        if not isinstance(item, dict) or "mean" not in item:
            raise ChipError(
                f"mintchip from hyperfine: results[{i}] is missing 'mean'.",
                fix_hint="Export directly with hyperfine --export-json.",
            )
        name = str(item.get("command") or f"cmd-{i + 1}")
        mean = float(item["mean"])
        raw_times = item.get("times")
        samples = (
            tuple(float(t) for t in raw_times if t is not None)
            if isinstance(raw_times, list)
            else ()
        )
        stddev = float(item["stddev"]) if item.get("stddev") is not None else None
        n = len(samples) if samples else None
        entries.append(
            BenchEntry(
                name=name,
                value=mean,
                unit="s",
                samples=samples,
                stddev=stddev,
                n=n,
                higher_is_better=False,
            )
        )
    return entries


def parse_pytest_bench(text: str) -> list[BenchEntry]:
    """Parse ``pytest-benchmark`` JSON into normalized :class:`BenchEntry` records (seconds)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ChipError(
            f"mintchip from pytest-bench: invalid JSON (line {e.lineno}: {e.msg}).",
            fix_hint="Pass a file created with: pytest --benchmark-json=bench.json",
        ) from None
    benches = data.get("benchmarks") if isinstance(data, dict) else None
    if not isinstance(benches, list) or not benches:
        raise ChipError(
            "mintchip from pytest-bench: expected a JSON object with a non-empty 'benchmarks' list.",
            fix_hint="Pass output from: pytest --benchmark-json=bench.json",
        )
    entries: list[BenchEntry] = []
    for i, item in enumerate(benches):
        if not isinstance(item, dict) or not isinstance(item.get("stats"), dict):
            raise ChipError(
                f"mintchip from pytest-bench: benchmarks[{i}] is missing 'stats'.",
                fix_hint="Export directly with pytest --benchmark-json=bench.json.",
            )
        stats = item["stats"]
        if "mean" not in stats:
            raise ChipError(
                f"mintchip from pytest-bench: benchmarks[{i}].stats is missing 'mean'.",
                fix_hint="Export directly with pytest --benchmark-json=bench.json.",
            )
        name = str(item.get("name") or item.get("fullname") or f"bench-{i + 1}")
        mean = float(stats["mean"])
        stddev = float(stats["stddev"]) if stats.get("stddev") is not None else None
        rounds = int(stats["rounds"]) if stats.get("rounds") is not None else None
        raw_data = stats.get("data")
        samples = (
            tuple(float(v) for v in raw_data if v is not None)
            if isinstance(raw_data, list)
            else ()
        )
        ci_bounds: tuple[float, float] | None = None
        if stddev is not None and stddev > 0:
            se = stddev / math.sqrt(rounds) if rounds and rounds > 1 else stddev
            half = 1.96 * se
            ci_bounds = (max(0.0, mean - half), mean + half)
        elif stats.get("q1") is not None and stats.get("q3") is not None:
            lo, hi = float(stats["q1"]), float(stats["q3"])
            if lo <= mean <= hi:
                ci_bounds = (lo, hi)
        entries.append(
            BenchEntry(
                name=name,
                value=mean,
                unit="s",
                samples=samples,
                stddev=stddev,
                n=rounds or (len(samples) if samples else None),
                ci=ci_bounds,
                higher_is_better=False,
            )
        )
    return entries


def parse_go_bench(text: str) -> list[BenchEntry]:
    """Parse ``go test -bench`` text output into normalized :class:`BenchEntry` records (seconds)."""
    grouped_times: dict[str, list[float]] = defaultdict(list)
    grouped_bytes: dict[str, list[float]] = defaultdict(list)
    grouped_allocs: dict[str, list[float]] = defaultdict(list)
    order: list[str] = []

    for line in text.splitlines():
        m = _GO_BENCH_RE.match(line.strip())
        if not m:
            continue
        raw_name, _iters, val_s, unit_s, bytes_s, allocs_s = m.groups()
        name = re.sub(r"-\d+$", "", raw_name)
        if name not in grouped_times:
            order.append(name)
        sec = float(val_s) * _TIME_TO_SEC[unit_s]
        grouped_times[name].append(sec)
        if bytes_s is not None:
            grouped_bytes[name].append(float(bytes_s))
        if allocs_s is not None:
            grouped_allocs[name].append(float(allocs_s))

    if not order:
        raise ChipError(
            "mintchip from go-bench: no 'go test -bench' lines found.",
            fix_hint="Pipe output from: go test -bench=. -benchmem | mintchip from go-bench",
        )

    entries: list[BenchEntry] = []
    for name in order:
        ts = grouped_times[name]
        mean = sum(ts) / len(ts)
        stddev: float | None = None
        if len(ts) >= 2:
            var = sum((x - mean) ** 2 for x in ts) / (len(ts) - 1)
            stddev = math.sqrt(var)
        extras: list[tuple[str, float]] = []
        if name in grouped_bytes:
            bs = grouped_bytes[name]
            extras.append(("bytes", sum(bs) / len(bs)))
        if name in grouped_allocs:
            al = grouped_allocs[name]
            extras.append(("allocs", sum(al) / len(al)))
        entries.append(
            BenchEntry(
                name=name,
                value=mean,
                unit="s",
                samples=tuple(ts) if len(ts) >= 2 else (),
                stddev=stddev,
                n=len(ts),
                higher_is_better=False,
                extra=tuple(extras),
            )
        )
    return entries


def parse_cargo_bench(text: str) -> list[BenchEntry]:
    """Parse ``cargo bench`` output into normalized :class:`BenchEntry` records (seconds)."""
    entries: list[BenchEntry] = []
    for line in text.splitlines():
        m = _CARGO_BENCH_RE.match(line.strip())
        if not m:
            continue
        name, val_s, unit_s, dev_s = m.groups()
        mult = _TIME_TO_SEC[unit_s]
        val = float(val_s.replace(",", "")) * mult
        dev = float(dev_s.replace(",", "")) * mult
        ci_bounds = (max(0.0, val - dev), val + dev) if dev > 0 else None
        entries.append(
            BenchEntry(
                name=name,
                value=val,
                unit="s",
                stddev=dev / 1.96 if dev > 0 else 0.0,
                ci=ci_bounds,
                higher_is_better=False,
            )
        )
    if not entries:
        raise ChipError(
            "mintchip from cargo-bench: no 'cargo bench' lines found.",
            fix_hint="Pipe output from: cargo bench | mintchip from cargo-bench",
        )
    return entries


@dataclass(frozen=True)
class JUnitSuite:
    name: str
    states: tuple[str, ...]
    case_names: tuple[str, ...]


def parse_junit(text: str) -> list[JUnitSuite]:
    """Parse JUnit XML into per-suite pass/fail/skip state sequences."""
    try:
        root = ET.fromstring(text.strip())
    except ET.ParseError as e:
        raise ChipError(
            f"mintchip from junit: invalid XML ({e}).",
            fix_hint="Pass a JUnit XML report (e.g. pytest --junitxml=report.xml).",
        ) from None

    tag = root.tag.split("}")[-1]
    if tag == "testsuite":
        suite_elems = [root]
    elif tag == "testsuites":
        suite_elems = [el for el in root if el.tag.split("}")[-1] == "testsuite"]
    else:
        raise ChipError(
            f"mintchip from junit: unexpected root element <{tag}>.",
            fix_hint="Expected <testsuite> or <testsuites> JUnit XML.",
        )

    suites: list[JUnitSuite] = []
    for idx, suite in enumerate(suite_elems):
        sname = suite.attrib.get("name") or f"suite-{idx + 1}"
        cases = [el for el in suite.iter() if el.tag.split("}")[-1] == "testcase"]
        states: list[str] = []
        cnames: list[str] = []
        if cases:
            for ci, tc in enumerate(cases):
                cname = tc.attrib.get("name") or f"case-{ci + 1}"
                child_tags = {c.tag.split("}")[-1] for c in tc}
                if "failure" in child_tags or "error" in child_tags:
                    st = "fail"
                elif "skipped" in child_tags:
                    st = "skip"
                else:
                    st = "pass"
                states.append(st)
                cnames.append(cname)
        else:
            total = int(suite.attrib.get("tests", "0") or 0)
            failed = int(suite.attrib.get("failures", "0") or 0) + int(
                suite.attrib.get("errors", "0") or 0
            )
            skipped = int(suite.attrib.get("skipped", "0") or 0)
            passed = max(0, total - failed - skipped)
            states = ["pass"] * passed + ["fail"] * failed + ["skip"] * skipped
            cnames = [f"test-{i + 1}" for i in range(len(states))]
        if states:
            suites.append(JUnitSuite(name=sname, states=tuple(states), case_names=tuple(cnames)))

    if not suites:
        raise ChipError(
            "mintchip from junit: no test cases found in JUnit XML.",
            fix_hint="Ensure the JUnit XML contains at least one <testsuite> with <testcase> entries.",
        )
    return suites


# --- format detection ------------------------------------------------------------------------
def detect_format(text: str) -> str:
    """Auto-detect the input tool format from its content."""
    stripped = text.lstrip()
    if not stripped:
        raise ChipError(
            "mintchip from auto: input is empty.",
            fix_hint="Pipe tool output to stdin or pass a non-empty file path.",
        )
    if stripped.startswith("<") and ("<testsuite" in stripped or "<testcase" in stripped):
        return "junit"
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            if isinstance(obj.get("results"), list) and obj["results"]:
                first = obj["results"][0]
                if isinstance(first, dict) and "mean" in first and "command" in first:
                    return "hyperfine"
            if isinstance(obj.get("benchmarks"), list) and obj["benchmarks"]:
                first = obj["benchmarks"][0]
                if isinstance(first, dict) and isinstance(first.get("stats"), dict):
                    return "pytest-bench"
    lines = text.splitlines()
    if any(_CARGO_BENCH_RE.match(ln.strip()) for ln in lines):
        return "cargo-bench"
    if any(_GO_BENCH_RE.match(ln.strip()) for ln in lines):
        return "go-bench"
    if any(_GIT_NUMSTAT_RE.match(ln.strip("\r\n")) for ln in lines):
        return "git-diff"
    raise ChipError(
        "mintchip from auto: could not detect input format.",
        fix_hint=(
            "Specify the format explicitly: "
            + ", ".join(f for f in INGEST_FORMATS if f != "auto")
            + "."
        ),
    )


# --- builders turning parsed outputs into Chip / Table ---------------------------------------
def _build_hyperfine(entries: Sequence[BenchEntry], title: str | None) -> mc.Table:
    all_secs = [e.value for e in entries] + [s for e in entries for s in e.samples]
    mult, unit = pick_time_unit(all_secs)
    has_dist = any(len(e.samples) >= 2 for e in entries)
    has_ci = not has_dist and any(e.stddev and e.stddev > 0 for e in entries)

    rows: list[dict[str, Any]] = []
    for e in entries:
        row: dict[str, Any] = {
            "command": e.name,
            "mean": e.value * mult,
        }
        if has_dist:
            row["times"] = [s * mult for s in e.samples] if len(e.samples) >= 2 else None
        elif has_ci:
            half = 1.96 * (e.stddev or 0.0) * mult
            v = e.value * mult
            row["ci"] = [v, max(0.0, v - half), v + half]
        rows.append(row)

    columns: dict[str, Any] = {
        "command": {"chip": "text", "header": "Command"},
        "mean": {"chip": "num", "header": "Mean", "unit": unit},
    }
    if has_dist:
        columns["times"] = {"chip": "dist", "header": "Distribution", "unit": unit}
    elif has_ci:
        columns["ci"] = {
            "chip": "ci",
            "header": "95% CI",
            "unit": unit,
            "level": 0.95,
            "reference": None,
        }
    return mc.table(rows, columns, title=title)


def _build_pytest_bench(entries: Sequence[BenchEntry], title: str | None) -> mc.Table:
    all_secs = [e.value for e in entries] + [
        b for e in entries if e.ci is not None for b in e.ci
    ]
    mult, unit = pick_time_unit(all_secs)
    has_ci = any(e.ci is not None for e in entries)
    max_val = max((e.value * mult for e in entries), default=1.0) or 1.0

    rows: list[dict[str, Any]] = []
    for e in entries:
        v = e.value * mult
        row: dict[str, Any] = {"benchmark": e.name, "mean": v}
        if has_ci:
            if e.ci is not None:
                row["spread"] = [v, e.ci[0] * mult, e.ci[1] * mult]
            else:
                row["spread"] = [v, v, v]
        else:
            row["rel"] = {"value": v, "total": max_val}
        rows.append(row)

    columns: dict[str, Any] = {
        "benchmark": {"chip": "text", "header": "Benchmark"},
        "mean": {"chip": "num", "header": "Mean", "unit": unit},
    }
    if has_ci:
        columns["spread"] = {
            "chip": "ci",
            "header": "95% CI",
            "unit": unit,
            "level": 0.95,
            "reference": None,
        }
    else:
        columns["rel"] = {"chip": "bar", "header": "Relative", "unit": unit}
    return mc.table(rows, columns, title=title)


def _build_go_bench(entries: Sequence[BenchEntry], title: str | None) -> mc.Table:
    all_secs = [e.value for e in entries] + [s for e in entries for s in e.samples]
    mult, unit = pick_time_unit(all_secs)
    has_dist = any(len(e.samples) >= 2 for e in entries)
    max_val = max((e.value * mult for e in entries), default=1.0) or 1.0
    extra_keys = {k for e in entries for k, _ in e.extra}

    rows: list[dict[str, Any]] = []
    for e in entries:
        v = e.value * mult
        ex = dict(e.extra)
        row: dict[str, Any] = {"benchmark": e.name}
        if has_dist:
            row["mean"] = v
            row["dist"] = [s * mult for s in e.samples] if len(e.samples) >= 2 else None
        else:
            row["time"] = {"value": v, "total": max_val}
        if "bytes" in extra_keys:
            row["bytes"] = ex.get("bytes")
        if "allocs" in extra_keys:
            row["allocs"] = ex.get("allocs")
        rows.append(row)

    columns: dict[str, Any] = {"benchmark": {"chip": "text", "header": "Benchmark"}}
    if has_dist:
        columns["mean"] = {"chip": "num", "header": "Mean", "unit": unit}
        columns["dist"] = {"chip": "dist", "header": "Distribution", "unit": unit}
    else:
        columns["time"] = {"chip": "bar", "header": "Time/op", "unit": unit}
    if "bytes" in extra_keys:
        columns["bytes"] = {"chip": "num", "header": "B/op", "unit": "B"}
    if "allocs" in extra_keys:
        columns["allocs"] = {"chip": "num", "header": "Allocs"}
    return mc.table(rows, columns, title=title)


def _build_cargo_bench(entries: Sequence[BenchEntry], title: str | None) -> mc.Table:
    all_secs = [e.value for e in entries] + [
        b for e in entries if e.ci is not None for b in e.ci
    ]
    mult, unit = pick_time_unit(all_secs)
    has_jitter = any(e.ci is not None for e in entries)
    max_val = max((e.value * mult for e in entries), default=1.0) or 1.0

    rows: list[dict[str, Any]] = []
    for e in entries:
        v = e.value * mult
        row: dict[str, Any] = {
            "benchmark": e.name,
            "time": {"value": v, "total": max_val},
        }
        if has_jitter:
            row["jitter"] = ((e.ci[1] - e.ci[0]) / 2.0 * mult) if e.ci is not None else 0.0
        rows.append(row)

    columns: dict[str, Any] = {
        "benchmark": {"chip": "text", "header": "Benchmark"},
        "time": {"chip": "bar", "header": "Time/iter", "unit": unit},
    }
    if has_jitter:
        columns["jitter"] = {"chip": "num", "header": "+/-", "unit": unit}
    return mc.table(rows, columns, title=title)


def _build_junit(suites: Sequence[JUnitSuite], title: str | None) -> Chip | mc.Table:
    if len(suites) == 1:
        s = suites[0]
        return mc.strip(list(s.states), names=list(s.case_names), label=title or s.name)
    rows: list[dict[str, Any]] = []
    for s in suites:
        passed = s.states.count("pass")
        total = len(s.states)
        rows.append(
            {
                "suite": s.name,
                "results": {"values": list(s.states), "names": list(s.case_names)},
                "pass_rate": {"value": passed, "total": total},
            }
        )
    columns = {
        "suite": {"chip": "text", "header": "Suite"},
        "results": {"chip": "strip", "header": "Results"},
        "pass_rate": {"chip": "bar", "header": "Passed"},
    }
    return mc.table(rows, columns, title=title)


def ingest(text: str, *, fmt: str = "auto", title: str | None = None) -> Chip | mc.Table:
    """Parse tool output in ``fmt`` (or ``auto``) and return a :class:`Chip` or :class:`Table`."""
    chosen = fmt.strip().lower()
    if chosen not in INGEST_FORMATS:
        close = difflib.get_close_matches(chosen, INGEST_FORMATS, n=1, cutoff=0.5)
        hint = f"Did you mean {close[0]!r}? " if close else ""
        raise ChipError(
            f"mintchip from: unknown format {fmt!r}.",
            fix_hint=f"{hint}Formats: {', '.join(INGEST_FORMATS)}.",
        )
    if chosen == "auto":
        chosen = detect_format(text)

    if chosen == "git-diff":
        parts = parse_git_diff(text)
        return mc.share(parts, label=title or "Changed lines", unit="lines")
    if chosen == "hyperfine":
        return _build_hyperfine(parse_hyperfine(text), title=title)
    if chosen == "pytest-bench":
        return _build_pytest_bench(parse_pytest_bench(text), title=title)
    if chosen == "go-bench":
        return _build_go_bench(parse_go_bench(text), title=title)
    if chosen == "cargo-bench":
        return _build_cargo_bench(parse_cargo_bench(text), title=title)
    if chosen == "junit":
        return _build_junit(parse_junit(text), title=title)
    raise AssertionError(f"unhandled format {chosen!r}")


def render_result(obj: Chip | mc.Table, *, format: str = "text", ascii: bool = False) -> str:
    """Render either a :class:`Chip` or :class:`Table` in ``format``."""
    from .cli import _bad_format, chip_output

    if format not in OUTPUT_FORMATS:
        raise _bad_format(format, OUTPUT_FORMATS)
    if isinstance(obj, Chip):
        return chip_output(obj, format=format, ascii=ascii)
    if format == "json":
        return json.dumps(obj.to_dict(), indent=2, ensure_ascii=ascii)
    if format == "md":
        return obj.markdown()
    if format == "html":
        return obj.html()
    return obj.text(ascii=ascii, color=format == "ansi")


def add_from_parser(sub: Any, formatter_class: Any) -> argparse.ArgumentParser:
    """Register the ``mintchip from`` subcommand."""
    p = sub.add_parser(
        "from",
        help="Ingest SWE tool output (git-diff, hyperfine, pytest/go/cargo bench, junit).",
        description=(
            "Convert standard developer tool output directly into a chip or shared-scale table\n"
            "with zero external dependencies. Pass 'auto' to auto-detect the tool format.\n"
            "Formats: auto, git-diff, hyperfine, pytest-bench, go-bench, cargo-bench, junit."
        ),
        epilog=(
            "examples:\n"
            "  $ git diff --numstat | mintchip from git-diff\n"
            "  $ mintchip from hyperfine bench.json --format md\n"
            "  $ mintchip from auto report.xml"
        ),
        formatter_class=formatter_class,
    )
    p.add_argument(
        "source_format",
        metavar="FORMAT",
        help="Input tool format: auto, git-diff, hyperfine, pytest-bench, go-bench, cargo-bench, junit.",
    )
    p.add_argument(
        "file",
        nargs="?",
        default="-",
        metavar="FILE",
        help="Input file path; - (default) reads stdin.",
    )
    p.add_argument(
        "--format",
        choices=OUTPUT_FORMATS,
        default="text",
        help="Output format: text (default), ansi, md, html or json.",
    )
    p.add_argument("--ascii", action="store_true", help="Pure ASCII output.")
    p.add_argument("--strict", action="store_true", help="Exit 1 on any warning.")
    p.add_argument("--title", help="Optional label (for chips) or title (for tables).")
    p.set_defaults(func=cmd_from, _parser=p)
    return p


def cmd_from(args: argparse.Namespace) -> int:
    """Execute ``mintchip from``."""
    from .cli import _error, _out, _read, _warn

    try:
        raw = _read(args.file)
        obj = ingest(raw, fmt=args.source_format, title=args.title)
        out = render_result(obj, format=args.format, ascii=args.ascii)
    except ChipError as e:
        return _error(e, "mintchip from auto bench.json")
    _out(out)
    return _warn(obj.warnings, args.strict)
