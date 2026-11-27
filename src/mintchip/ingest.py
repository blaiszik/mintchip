"""Zero-dependency SWE tool ingestors for ``mintchip from <format> [FILE|-]``.

Converts standard developer tool outputs directly into ``mintchip`` chips or shared-scale
tables using only the Python standard library:

- ``git-diff``: ``git diff --numstat`` -> ``share`` chip of changed lines by top-level area
- ``hyperfine``: ``hyperfine --export-json`` -> ``table`` with ``num`` mean + ``dist``
- ``pytest-bench``: ``pytest-benchmark`` JSON -> ``table`` with ``num`` + ``ci`` or ``bar``
- ``go-bench``: ``go test -bench`` text -> ``table``
- ``cargo-bench``: ``cargo bench`` text -> ``table``
- ``junit``: JUnit XML -> ``strip`` chip (1 suite) or ``table`` with ``strip`` + ``bar``
- ``github-actions``: GitHub Actions jobs JSON -> ``timeline`` chip or ``table``
- ``k6``: k6 ``--summary-export`` JSON -> ``dist`` chip or ``table``
- ``esbuild``: esbuild ``--metafile`` JSON -> ``share`` chip or ``table``
- ``chrome-trace``: Chrome trace event JSON -> ``timeline`` chip or ``table``
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
from datetime import datetime
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
    "parse_chrome_trace",
    "parse_esbuild",
    "parse_git_diff",
    "parse_github_actions",
    "parse_go_bench",
    "parse_hyperfine",
    "parse_junit",
    "parse_k6",
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
    "github-actions",
    "k6",
    "esbuild",
    "chrome-trace",
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


@dataclass(frozen=True)
class WorkflowSpan:
    name: str
    start: float | None
    end: float | None
    duration: float


@dataclass(frozen=True)
class WorkflowJob:
    name: str
    start: float | None
    end: float | None
    duration: float
    conclusion: str | None = None
    steps: tuple[WorkflowSpan, ...] = ()


@dataclass(frozen=True)
class K6Metric:
    name: str
    samples: tuple[float, ...]
    avg: float | None = None
    p95: float | None = None


@dataclass(frozen=True)
class BundleShare:
    name: str
    total_bytes: int
    parts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class TraceSpan:
    name: str
    start: float  # seconds
    end: float  # seconds


def _parse_iso_ts(raw: Any) -> float | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def _span_from_item(item: dict[str, Any], fallback_name: str) -> WorkflowSpan | None:
    name = str(item.get("name") or fallback_name).strip() or fallback_name
    st = _parse_iso_ts(item.get("started_at") or item.get("startedAt"))
    en = _parse_iso_ts(item.get("completed_at") or item.get("completedAt"))
    dur: float | None = None
    if st is not None and en is not None and en > st:
        dur = en - st
    else:
        raw_dur = item.get("duration_s")
        if raw_dur is None:
            raw_dur = item.get("duration")
        if isinstance(raw_dur, (int, float)) and not isinstance(raw_dur, bool) and raw_dur > 0:
            dur = float(raw_dur)
    if dur is None or dur <= 0:
        return None
    return WorkflowSpan(name=name, start=st, end=en, duration=dur)


def parse_github_actions(text: str) -> list[WorkflowJob]:
    """Parse GitHub Actions workflow jobs JSON (``gh run view --json jobs`` or REST API)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ChipError(
            f"mintchip from github-actions: invalid JSON (line {e.lineno}: {e.msg}).",
            fix_hint="Pass JSON from: gh run view <id> --json jobs",
        ) from None
    raw_jobs = data.get("jobs") if isinstance(data, dict) else (data if isinstance(data, list) else None)
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise ChipError(
            "mintchip from github-actions: expected a JSON object with a non-empty 'jobs' list.",
            fix_hint="Pass JSON from: gh run view <id> --json jobs",
        )
    jobs: list[WorkflowJob] = []
    for i, item in enumerate(raw_jobs):
        if not isinstance(item, dict):
            continue
        steps: list[WorkflowSpan] = []
        raw_steps = item.get("steps")
        if isinstance(raw_steps, list):
            for si, st_item in enumerate(raw_steps):
                if isinstance(st_item, dict):
                    sp = _span_from_item(st_item, f"step-{si + 1}")
                    if sp is not None:
                        steps.append(sp)
        jspan = _span_from_item(item, f"job-{i + 1}")
        if jspan is None and steps:
            s_starts = [s.start for s in steps if s.start is not None]
            s_ends = [s.end for s in steps if s.end is not None]
            st = min(s_starts) if s_starts else None
            en = max(s_ends) if s_ends else None
            dur = (en - st) if (st is not None and en is not None and en > st) else sum(s.duration for s in steps)
            jspan = WorkflowSpan(
                name=str(item.get("name") or f"job-{i + 1}"),
                start=st,
                end=en,
                duration=dur,
            )
        if jspan is None:
            continue
        concl = item.get("conclusion") or item.get("status")
        jobs.append(
            WorkflowJob(
                name=jspan.name,
                start=jspan.start,
                end=jspan.end,
                duration=jspan.duration,
                conclusion=str(concl) if concl is not None else None,
                steps=tuple(steps),
            )
        )
    if not jobs:
        raise ChipError(
            "mintchip from github-actions: no completed jobs with positive durations found.",
            fix_hint="Ensure jobs include started_at/completed_at (or startedAt/completedAt) timestamps.",
        )
    return jobs


def _k6_samples(vals: dict[str, Any]) -> tuple[float, ...] | None:
    def _num(k: str) -> float | None:
        v = vals.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            return float(v)
        return None

    lo = _num("min")
    med = _num("med")
    if med is None:
        med = _num("p(50)")
    avg = _num("avg")
    p90 = _num("p(90)")
    p95 = _num("p(95)")
    p99 = _num("p(99)")
    hi = _num("max")

    present = [v for v in (lo, med, avg, p90, p95, p99, hi) if v is not None]
    if len(present) < 2:
        return None
    if med is None:
        med = avg if avg is not None else sorted(present)[len(present) // 2]
    if lo is None:
        lo = min(present)
    if hi is None:
        hi = max(present)

    upper = [v for v in (p90, p95, p99, hi) if v is not None and v >= med]
    if not upper:
        upper = [hi]
    k = len(upper)
    lower = [lo + (med - lo) * (i / k) for i in range(k)]
    return tuple(sorted([*lower, med, *upper]))


def parse_k6(text: str) -> list[K6Metric]:
    """Parse ``k6 run --summary-export`` JSON into latency distribution metrics (ms)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ChipError(
            f"mintchip from k6: invalid JSON (line {e.lineno}: {e.msg}).",
            fix_hint="Pass a file created with: k6 run --summary-export=summary.json script.js",
        ) from None
    raw_metrics = data.get("metrics") if isinstance(data, dict) else None
    if not isinstance(raw_metrics, dict) or not raw_metrics:
        raise ChipError(
            "mintchip from k6: expected a JSON object with a non-empty 'metrics' map.",
            fix_hint="Pass a file created with: k6 run --summary-export=summary.json script.js",
        )
    metrics: list[K6Metric] = []
    for name, obj in raw_metrics.items():
        if not isinstance(obj, dict):
            continue
        vals = obj.get("values") if isinstance(obj.get("values"), dict) else obj
        samples = _k6_samples(vals)
        if samples is None:
            continue
        avg_v = vals.get("avg")
        p95_v = vals.get("p(95)")
        avg = float(avg_v) if isinstance(avg_v, (int, float)) and not isinstance(avg_v, bool) else None
        p95 = float(p95_v) if isinstance(p95_v, (int, float)) and not isinstance(p95_v, bool) else None
        metrics.append(K6Metric(name=str(name), samples=samples, avg=avg, p95=p95))
    if not metrics:
        raise ChipError(
            "mintchip from k6: no latency trend metrics (min/med/p(90)/p(95)/max) found.",
            fix_hint="Export k6 summary JSON containing trend metrics such as http_req_duration.",
        )
    # Put http_req_duration first when present
    metrics.sort(key=lambda m: (0 if m.name == "http_req_duration" else 1))
    return metrics


def _esbuild_area(path: str) -> str:
    norm = path.strip().replace("\\", "/")
    if "node_modules/" in norm:
        after = norm.rsplit("node_modules/", 1)[1]
        parts = [p for p in after.split("/") if p]
        if len(parts) >= 2 and parts[0].startswith("@"):
            return f"{parts[0]}/{parts[1]}"
        if parts:
            return parts[0]
    norm = norm.lstrip("./")
    if "/" not in norm:
        return norm or "root"
    return norm.split("/", 1)[0] or "root"


def parse_esbuild(text: str) -> list[BundleShare]:
    """Parse ``esbuild --metafile`` JSON into per-bundle byte composition records."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ChipError(
            f"mintchip from esbuild: invalid JSON (line {e.lineno}: {e.msg}).",
            fix_hint="Pass a file created with: esbuild app.ts --bundle --metafile=meta.json",
        ) from None
    if not isinstance(data, dict) or (
        not isinstance(data.get("outputs"), dict) and not isinstance(data.get("inputs"), dict)
    ):
        raise ChipError(
            "mintchip from esbuild: expected a metafile JSON with 'outputs' and/or 'inputs'.",
            fix_hint="Pass a file created with: esbuild app.ts --bundle --metafile=meta.json",
        )
    raw_outputs = data.get("outputs") if isinstance(data.get("outputs"), dict) else {}
    raw_inputs = data.get("inputs") if isinstance(data.get("inputs"), dict) else {}

    non_map_keys = [k for k in raw_outputs if not str(k).endswith(".map")]
    out_keys = non_map_keys or list(raw_outputs)

    bundles: list[BundleShare] = []
    for out_name in out_keys:
        out_obj = raw_outputs.get(out_name)
        if not isinstance(out_obj, dict):
            continue
        out_inputs = out_obj.get("inputs")
        grouped: dict[str, int] = defaultdict(int)
        if isinstance(out_inputs, dict):
            for inp_path, info in out_inputs.items():
                if isinstance(info, dict):
                    b = info.get("bytesInOutput")
                    if isinstance(b, (int, float)) and b > 0:
                        grouped[_esbuild_area(str(inp_path))] += int(b)
        if grouped:
            total = int(out_obj.get("bytes") or sum(grouped.values()))
            parts = tuple(sorted(grouped.items(), key=lambda kv: -kv[1]))
            bundles.append(BundleShare(name=str(out_name), total_bytes=total, parts=parts))

    if not bundles and raw_outputs:
        grouped_out: dict[str, int] = defaultdict(int)
        for out_name in out_keys:
            out_obj = raw_outputs.get(out_name)
            if isinstance(out_obj, dict):
                b = out_obj.get("bytes")
                if isinstance(b, (int, float)) and b > 0:
                    grouped_out[str(out_name)] += int(b)
        if grouped_out:
            parts = tuple(sorted(grouped_out.items(), key=lambda kv: -kv[1]))
            bundles.append(
                BundleShare(name="Bundle outputs", total_bytes=sum(grouped_out.values()), parts=parts)
            )

    if not bundles and raw_inputs:
        grouped_in: dict[str, int] = defaultdict(int)
        for inp_path, info in raw_inputs.items():
            if isinstance(info, dict):
                b = info.get("bytes")
                if isinstance(b, (int, float)) and b > 0:
                    grouped_in[_esbuild_area(str(inp_path))] += int(b)
        if grouped_in:
            parts = tuple(sorted(grouped_in.items(), key=lambda kv: -kv[1]))
            bundles.append(
                BundleShare(name="Bundle inputs", total_bytes=sum(grouped_in.values()), parts=parts)
            )

    if not bundles:
        raise ChipError(
            "mintchip from esbuild: no positive byte counts found in metafile.",
            fix_hint="Pass a non-empty esbuild --metafile JSON.",
        )
    return bundles


def parse_chrome_trace(text: str) -> list[TraceSpan]:
    """Parse Chrome Trace Event JSON (``{"traceEvents": [...]}`` or ``[...]``) into spans (s)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ChipError(
            f"mintchip from chrome-trace: invalid JSON (line {e.lineno}: {e.msg}).",
            fix_hint="Pass a Chrome trace JSON file ({'traceEvents': [...]} or [...]).",
        ) from None
    events = data.get("traceEvents") if isinstance(data, dict) else (data if isinstance(data, list) else None)
    if not isinstance(events, list) or not events:
        raise ChipError(
            "mintchip from chrome-trace: expected a non-empty 'traceEvents' list or JSON array.",
            fix_hint="Pass a Chrome trace JSON file with complete (X) or begin/end (B/E) events.",
        )
    spans: list[TraceSpan] = []
    stacks: dict[tuple[Any, Any, str], list[float]] = defaultdict(list)
    for ev in events:
        if not isinstance(ev, dict):
            continue
        ph = ev.get("ph")
        ts = ev.get("ts")
        name = ev.get("name")
        if not isinstance(ts, (int, float)) or isinstance(ts, bool) or not name:
            continue
        ts_sec = float(ts) * 1e-6
        if ph == "X":
            dur = ev.get("dur")
            if isinstance(dur, (int, float)) and not isinstance(dur, bool) and dur > 0:
                spans.append(TraceSpan(name=str(name), start=ts_sec, end=ts_sec + float(dur) * 1e-6))
        elif ph == "B":
            key = (ev.get("pid", 0), ev.get("tid", 0), str(name))
            stacks[key].append(ts_sec)
        elif ph == "E":
            key = (ev.get("pid", 0), ev.get("tid", 0), str(name))
            if stacks[key]:
                st = stacks[key].pop()
                if ts_sec > st:
                    spans.append(TraceSpan(name=str(name), start=st, end=ts_sec))
    if not spans:
        raise ChipError(
            "mintchip from chrome-trace: no timed duration events (ph='X' or matched 'B'/'E') found.",
            fix_hint="Provide Chrome trace events with positive 'dur' (ph='X') or matched B/E pairs.",
        )
    spans.sort(key=lambda s: s.start)
    return spans


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
    if stripped.startswith(("{", "[")):
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
            if isinstance(obj.get("traceEvents"), list) and obj["traceEvents"]:
                first = obj["traceEvents"][0]
                if isinstance(first, dict) and "ph" in first and "ts" in first:
                    return "chrome-trace"
            if isinstance(obj.get("jobs"), list) and obj["jobs"]:
                first = obj["jobs"][0]
                if isinstance(first, dict) and any(
                    k in first for k in ("started_at", "startedAt", "completed_at", "completedAt", "steps", "conclusion")
                ):
                    return "github-actions"
            if isinstance(obj.get("metrics"), dict) and obj["metrics"]:
                for mval in obj["metrics"].values():
                    if isinstance(mval, dict):
                        inner = mval.get("values") if isinstance(mval.get("values"), dict) else mval
                        if any(k in inner for k in ("p(95)", "p(90)", "med", "avg")) or mval.get("type") == "trend":
                            return "k6"
            if isinstance(obj.get("inputs"), dict) and isinstance(obj.get("outputs"), dict):
                out_vals = list(obj["outputs"].values())
                in_vals = list(obj["inputs"].values())
                if any(isinstance(v, dict) and "bytes" in v for v in (*out_vals, *in_vals)):
                    return "esbuild"
        elif isinstance(obj, list) and obj:
            first = obj[0]
            if isinstance(first, dict) and "ph" in first and "ts" in first and "name" in first:
                return "chrome-trace"
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


def _lane_count(spans: Sequence[tuple[float, float]]) -> int:
    ordered = sorted(spans, key=lambda ab: ab[0])
    ends: list[float] = []
    for a, b in ordered:
        k = next((i for i, e in enumerate(ends) if e <= a), len(ends))
        ends[k : k + 1] = [b]
    return len(ends)


def _unique_names(names: Sequence[str]) -> list[str]:
    seen: dict[str, int] = defaultdict(int)
    out: list[str] = []
    for n in names:
        seen[n] += 1
        out.append(n if seen[n] == 1 else f"{n} #{seen[n]}")
    return out


def _group_spans_to_limit(spans: Sequence[WorkflowSpan], limit: int = 10) -> list[WorkflowSpan]:
    if len(spans) <= limit:
        return list(spans)
    head = list(spans[: limit - 1])
    rest = spans[limit - 1 :]
    s_starts = [s.start for s in rest if s.start is not None]
    s_ends = [s.end for s in rest if s.end is not None]
    st = min(s_starts) if s_starts else None
    en = max(s_ends) if s_ends else None
    dur = (en - st) if (st is not None and en is not None and en > st) else sum(s.duration for s in rest)
    head.append(WorkflowSpan(name=f"other ({len(rest)})", start=st, end=en, duration=dur))
    return head


def _spans_to_timeline(
    spans: Sequence[WorkflowSpan], *, label: str | None, mult: float, unit: str
) -> Chip | None:
    grouped = _group_spans_to_limit(spans, 10)
    names = _unique_names([s.name for s in grouped])
    if all(s.start is not None and s.end is not None for s in grouped):
        t0 = min(float(s.start) for s in grouped)  # type: ignore[arg-type]
        rel = [((float(s.start) - t0) * mult, (float(s.end) - t0) * mult) for s in grouped]  # type: ignore[arg-type]
        if _lane_count(rel) <= 3:
            return mc.timeline(dict(zip(names, rel, strict=True)), label=label, unit=unit)
        return None
    durs = {n: s.duration * mult for n, s in zip(names, grouped, strict=True)}
    return mc.timeline(durs, label=label, unit=unit)


def _build_github_actions(jobs: Sequence[WorkflowJob], title: str | None) -> Chip | mc.Table:
    all_secs = [j.duration for j in jobs] + [s.duration for j in jobs for s in j.steps]
    mult, unit = pick_time_unit(all_secs)

    if len(jobs) == 1:
        j = jobs[0]
        if j.steps:
            chip = _spans_to_timeline(j.steps, label=title or j.name, mult=mult, unit=unit)
            if chip is not None:
                return chip
        return mc.timeline({j.name: j.duration * mult}, label=title or j.name, unit=unit)

    has_steps = any(j.steps for j in jobs)
    if not has_steps and len(jobs) <= 10:
        job_spans = [WorkflowSpan(j.name, j.start, j.end, j.duration) for j in jobs]
        chip = _spans_to_timeline(job_spans, label=title or "Workflow jobs", mult=mult, unit=unit)
        if chip is not None:
            return chip

    max_val = max((j.duration * mult for j in jobs), default=1.0) or 1.0
    has_status = any(j.conclusion for j in jobs)
    rows: list[dict[str, Any]] = []
    for j in jobs:
        row: dict[str, Any] = {
            "job": j.name,
            "duration": {"value": j.duration * mult, "total": max_val},
        }
        if has_steps:
            if j.steps:
                grouped = _group_spans_to_limit(j.steps, 10)
                names = _unique_names([s.name for s in grouped])
                row["phases"] = {
                    "stages": {n: s.duration * mult for n, s in zip(names, grouped, strict=True)},
                    "unit": unit,
                }
            else:
                row["phases"] = {"stages": {j.name: j.duration * mult}, "unit": unit}
        if has_status:
            row["status"] = j.conclusion
        rows.append(row)

    columns: dict[str, Any] = {
        "job": {"chip": "text", "header": "Job"},
        "duration": {"chip": "bar", "header": "Duration", "unit": unit},
    }
    if has_steps:
        columns["phases"] = {"chip": "timeline", "header": "Steps", "unit": unit}
    if has_status:
        columns["status"] = {"chip": "text", "header": "Status"}
    return mc.table(rows, columns, title=title)


def _build_k6(metrics: Sequence[K6Metric], title: str | None) -> Chip | mc.Table:
    if len(metrics) == 1:
        m = metrics[0]
        return mc.dist(list(m.samples), unit="ms", label=title or m.name)
    has_avg = any(m.avg is not None for m in metrics)
    has_p95 = any(m.p95 is not None for m in metrics)
    rows: list[dict[str, Any]] = []
    for m in metrics:
        row: dict[str, Any] = {"metric": m.name, "latency": list(m.samples)}
        if has_avg:
            row["avg"] = m.avg
        if has_p95:
            row["p95"] = m.p95
        rows.append(row)
    columns: dict[str, Any] = {"metric": {"chip": "text", "header": "Metric"}}
    if has_avg:
        columns["avg"] = {"chip": "num", "header": "Avg", "unit": "ms"}
    if has_p95:
        columns["p95"] = {"chip": "num", "header": "p95", "unit": "ms"}
    columns["latency"] = {"chip": "dist", "header": "Latency", "unit": "ms"}
    return mc.table(rows, columns, title=title)


def _pick_byte_unit(sizes: Sequence[int]) -> tuple[float, str]:
    peak = max(sizes, default=0)
    if peak >= 1_000_000:
        return 1e-6, "MB"
    if peak >= 1_000:
        return 1e-3, "KB"
    return 1.0, "B"


def _build_esbuild(bundles: Sequence[BundleShare], title: str | None) -> Chip | mc.Table:
    scale, unit = _pick_byte_unit([b.total_bytes for b in bundles])
    if len(bundles) == 1:
        b = bundles[0]
        parts = {k: v * scale for k, v in b.parts}
        return mc.share(parts, label=title or b.name, unit=unit)
    max_val = max((b.total_bytes * scale for b in bundles), default=1.0) or 1.0
    rows = [
        {
            "bundle": b.name,
            "size": {"value": b.total_bytes * scale, "total": max_val},
            "composition": {k: v * scale for k, v in b.parts},
        }
        for b in bundles
    ]
    columns = {
        "bundle": {"chip": "text", "header": "Bundle"},
        "size": {"chip": "bar", "header": "Size", "unit": unit},
        "composition": {"chip": "share", "header": "Composition", "unit": unit},
    }
    return mc.table(rows, columns, title=title)


def _build_chrome_trace(spans: Sequence[TraceSpan], title: str | None) -> Chip | mc.Table:
    durs = [s.end - s.start for s in spans]
    wall = max(s.end for s in spans) - min(s.start for s in spans)
    mult, unit = pick_time_unit([*durs, wall])

    unique = len({s.name for s in spans}) == len(spans)
    if unique and len(spans) <= 10:
        t0 = min(s.start for s in spans)
        rel = [((s.start - t0) * mult, (s.end - t0) * mult) for s in spans]
        if _lane_count(rel) <= 3:
            stages = {s.name: ab for s, ab in zip(spans, rel, strict=True)}
            return mc.timeline(stages, label=title or "Trace", unit=unit)

    grouped: dict[str, list[float]] = defaultdict(list)
    for s in spans:
        grouped[s.name].append((s.end - s.start) * mult)
    ranked = sorted(grouped.items(), key=lambda kv: -sum(kv[1]))
    max_total = max((sum(vs) for _, vs in ranked), default=1.0) or 1.0
    has_dist = any(len(vs) >= 2 for _, vs in ranked)

    rows: list[dict[str, Any]] = []
    for name, vs in ranked:
        row: dict[str, Any] = {
            "phase": name,
            "total": {"value": sum(vs), "total": max_total},
            "calls": len(vs),
        }
        if has_dist:
            row["duration"] = vs if len(vs) >= 2 else None
        rows.append(row)
    columns: dict[str, Any] = {
        "phase": {"chip": "text", "header": "Phase"},
        "total": {"chip": "bar", "header": "Total", "unit": unit},
        "calls": {"chip": "num", "header": "Calls"},
    }
    if has_dist:
        columns["duration"] = {"chip": "dist", "header": "Duration", "unit": unit}
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
    if chosen == "github-actions":
        return _build_github_actions(parse_github_actions(text), title=title)
    if chosen == "k6":
        return _build_k6(parse_k6(text), title=title)
    if chosen == "esbuild":
        return _build_esbuild(parse_esbuild(text), title=title)
    if chosen == "chrome-trace":
        return _build_chrome_trace(parse_chrome_trace(text), title=title)
    raise AssertionError(f"unhandled format {chosen!r}")


def render_result(
    obj: Chip | mc.Table,
    *,
    format: str = "text",
    ascii: bool = False,
    fragment: bool = False,
) -> str:
    """Render either a :class:`Chip` or :class:`Table` in ``format``."""
    from .cli import _normalize_format, chip_output

    fmt_name = _normalize_format(format, OUTPUT_FORMATS)
    if isinstance(obj, Chip):
        if fmt_name == "html" and not fragment:
            from .render import html as _html_mod

            return _html_mod.page(obj.html(label=True, compact=False), title=obj.alt)
        return chip_output(obj, format=fmt_name, ascii=ascii)
    if fmt_name == "json":
        return json.dumps(obj.to_dict(), indent=2, ensure_ascii=ascii)
    if fmt_name == "md":
        return obj.markdown(ascii=ascii)
    if fmt_name == "html":
        if fragment:
            return obj.html()
        from .render import html as _html_mod

        return _html_mod._shell(
            obj.title or "mintchip",
            f'<div class="mc-wide">{obj.html()}</div>',
            None,
        )
    return obj.text(ascii=ascii, color=fmt_name == "ansi")


def add_from_parser(sub: Any, formatter_class: Any) -> argparse.ArgumentParser:
    """Register the ``mintchip from`` subcommand."""
    fmt_list = ", ".join(INGEST_FORMATS)
    p = sub.add_parser(
        "from",
        help="Ingest SWE tool output (git-diff, hyperfine, bench, junit, actions, k6, esbuild, trace).",
        description=(
            "Convert standard developer tool output directly into a chip or shared-scale table\n"
            "with zero external dependencies. Pass 'auto' to auto-detect the tool format.\n"
            f"Formats: {fmt_list}."
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
        help=f"Input tool format: {fmt_list}.",
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
        default="text",
        help="Output format: text (default), ansi, md (or markdown), html or json.",
    )
    p.add_argument("--ascii", action="store_true", help="Pure ASCII output.")
    p.add_argument("--strict", action="store_true", help="Exit 1 on any warning.")
    p.add_argument(
        "--fragment",
        action="store_true",
        help="Emit bare HTML without the page shell (for --format html).",
    )
    p.add_argument("-o", "--out", metavar="FILE", help="Write output to FILE instead of stdout.")
    p.add_argument("--title", help="Optional label (for chips) or title (for tables).")
    p.set_defaults(func=cmd_from, _parser=p)
    return p


def cmd_from(args: argparse.Namespace) -> int:
    """Execute ``mintchip from``."""
    from .cli import _error, _read, _warn, _write_output

    try:
        raw = _read(args.file)
        obj = ingest(raw, fmt=args.source_format, title=args.title)
        out = render_result(obj, format=args.format, ascii=args.ascii, fragment=args.fragment)
        _write_output(out, args.out)
    except ChipError as e:
        return _error(e, "mintchip from auto bench.json")
    return _warn(obj.warnings, args.strict)
