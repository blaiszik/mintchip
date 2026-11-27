"""Zero-dependency benchmark diffing for ``mintchip diff BASE HEAD``.

Compares two JSON, CSV, hyperfine, pytest-benchmark, Go benchmark, or Cargo benchmark runs
and renders a shared-scale ``mintchip table`` with base, head, ``delta``, and ``ci`` (when
intervals or samples exist) plus a one-line takeaway. Exits 1 if any regression exceeds
``--fail-on-regression PCT``.
"""

from __future__ import annotations

import argparse
import csv
import html as _html
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import mintchip as mc

from . import fmt as _fmt
from .ingest import (
    _TIME_TO_SEC,
    BenchEntry,
    detect_format,
    parse_cargo_bench,
    parse_go_bench,
    parse_hyperfine,
    parse_pytest_bench,
    pick_time_unit,
)
from .spec import ChipError

__all__ = [
    "DiffResult",
    "DiffRow",
    "add_diff_parser",
    "cmd_diff",
    "diff_benchmarks",
    "load_benchmark_entries",
    "render_diff",
]

OUTPUT_FORMATS: tuple[str, ...] = ("text", "ansi", "md", "html", "json")

_HIGHER_HINTS = (
    "acc",
    "accuracy",
    "throughput",
    "ops",
    "rps",
    "qps",
    "score",
    "f1",
    "pass",
    "speed",
    "fps",
    "bandwidth",
    "hit",
    "recall",
    "precision",
)


@dataclass(frozen=True)
class DiffRow:
    name: str
    base: float
    head: float
    delta: float
    pct_change: float
    regression_pct: float
    unit: str | None
    ci: tuple[float, float] | None
    higher_is_better: bool


@dataclass(frozen=True)
class DiffResult:
    table: mc.Table
    rows: tuple[DiffRow, ...]
    takeaway: str
    regressions: tuple[DiffRow, ...]
    fail_threshold: float | None
    failed: bool
    warnings: tuple[str, ...]


def _infer_higher_is_better(metric_name: str | None, unit: str | None) -> bool:
    if unit and unit.lower() in _TIME_TO_SEC:
        return False
    low = (metric_name or "").lower()
    if any(tok in low for tok in ("time", "latency", "dur", "ms", "sec", "mem", "err", "loss")):
        return False
    return any(tok in low for tok in _HIGHER_HINTS)


def _to_float(val: Any) -> float | None:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        f = float(val)
        return f if math.isfinite(f) else None
    if isinstance(val, str):
        s = val.strip().replace(",", "")
        if not s:
            return None
        try:
            f = float(s)
            return f if math.isfinite(f) else None
        except ValueError:
            return None
    return None


def _parse_generic_json(text: str) -> list[BenchEntry]:
    data = json.loads(text)
    entries: list[BenchEntry] = []

    if isinstance(data, dict):
        for name, raw in data.items():
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                entries.append(BenchEntry(name=str(name), value=float(raw)))
            elif isinstance(raw, list) and raw and all(_to_float(x) is not None for x in raw):
                xs = [float(x) for x in raw]
                mean = sum(xs) / len(xs)
                sd = (
                    math.sqrt(sum((x - mean) ** 2 for x in xs) / (len(xs) - 1))
                    if len(xs) >= 2
                    else None
                )
                entries.append(
                    BenchEntry(
                        name=str(name),
                        value=mean,
                        samples=tuple(xs) if len(xs) >= 2 else (),
                        stddev=sd,
                        n=len(xs),
                    )
                )
            elif isinstance(raw, dict):
                entry = _entry_from_mapping(str(name), raw)
                if entry is not None:
                    entries.append(entry)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            entry = _entry_from_row(item, idx)
            if entry is not None:
                entries.append(entry)

    if not entries:
        raise ChipError(
            "mintchip diff: could not extract benchmark rows from JSON.",
            fix_hint=(
                'Use hyperfine/pytest-bench JSON, [{"name": "a", "mean": 12.0}], '
                'or {"a": 12.0}.'
            ),
        )
    return entries


def _entry_from_mapping(name: str, obj: dict[str, Any]) -> BenchEntry | None:
    unit = str(obj["unit"]) if obj.get("unit") is not None else None
    raw_samples = obj.get("times") or obj.get("samples") or obj.get("data")
    samples: tuple[float, ...] = ()
    if isinstance(raw_samples, list):
        parsed = [f for x in raw_samples if (f := _to_float(x)) is not None]
        if len(parsed) >= 2:
            samples = tuple(parsed)

    val: float | None = None
    metric_key: str | None = None
    for k in ("mean", "value", "median", "time", "latency", "score", "acc", "ops"):
        if k in obj and (f := _to_float(obj[k])) is not None:
            val = f
            metric_key = k
            break
    if val is None and samples:
        val = sum(samples) / len(samples)
    if val is None:
        return None

    stddev = _to_float(obj.get("stddev") or obj.get("std") or obj.get("sd"))
    n_val = _to_float(obj.get("rounds") or obj.get("n"))
    n = int(n_val) if n_val is not None and n_val >= 1 else (len(samples) if samples else None)

    ci_bounds: tuple[float, float] | None = None
    raw_ci = obj.get("ci") or obj.get("interval")
    if isinstance(raw_ci, list) and len(raw_ci) == 2:
        lo, hi = _to_float(raw_ci[0]), _to_float(raw_ci[1])
        if lo is not None and hi is not None and lo <= hi:
            ci_bounds = (lo, hi)
    elif obj.get("ci_low") is not None and obj.get("ci_high") is not None:
        lo, hi = _to_float(obj.get("ci_low")), _to_float(obj.get("ci_high"))
        if lo is not None and hi is not None and lo <= hi:
            ci_bounds = (lo, hi)

    return BenchEntry(
        name=name,
        value=val,
        unit=unit,
        samples=samples,
        stddev=stddev,
        n=n,
        ci=ci_bounds,
        higher_is_better=_infer_higher_is_better(metric_key, unit),
    )


def _entry_from_row(row: dict[str, Any], idx: int) -> BenchEntry | None:
    name: str | None = None
    for k in ("name", "benchmark", "command", "model", "metric", "test", "id", "label"):
        if k in row and row[k] is not None and str(row[k]).strip():
            name = str(row[k]).strip()
            break
    if name is None:
        for v in row.values():
            if isinstance(v, str) and v.strip() and _to_float(v) is None:
                name = v.strip()
                break
    if name is None:
        name = f"row-{idx + 1}"

    entry = _entry_from_mapping(name, row)
    if entry is not None:
        return entry

    # Fall back to first numeric column in the row
    for k, v in row.items():
        if k.lower() in ("stddev", "std", "sd", "n", "rounds", "ci_low", "ci_high"):
            continue
        f = _to_float(v)
        if f is not None:
            unit = str(row["unit"]) if row.get("unit") is not None else None
            stddev = _to_float(row.get("stddev") or row.get("std") or row.get("sd"))
            n_val = _to_float(row.get("rounds") or row.get("n"))
            ci_bounds: tuple[float, float] | None = None
            lo, hi = _to_float(row.get("ci_low")), _to_float(row.get("ci_high"))
            if lo is not None and hi is not None and lo <= hi:
                ci_bounds = (lo, hi)
            return BenchEntry(
                name=name,
                value=f,
                unit=unit,
                stddev=stddev,
                n=int(n_val) if n_val is not None and n_val >= 1 else None,
                ci=ci_bounds,
                higher_is_better=_infer_higher_is_better(k, unit),
            )
    return None


def _parse_generic_csv(text: str) -> list[BenchEntry]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ChipError(
            "mintchip diff: CSV input needs a header and at least one data row.",
            fix_hint="Provide CSV with at least name and numeric columns.",
        )
    delimiter = "\t" if "\t" in lines[0] and "," not in lines[0] else ","
    reader = csv.DictReader(lines, delimiter=delimiter)
    entries: list[BenchEntry] = []
    for idx, row in enumerate(reader):
        clean = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
        entry = _entry_from_row(clean, idx)
        if entry is not None:
            entries.append(entry)
    if not entries:
        raise ChipError(
            "mintchip diff: no numeric benchmark rows found in CSV.",
            fix_hint="Provide CSV rows with a name column and a numeric measurement column.",
        )
    return entries


def load_benchmark_entries(text: str, *, source: str = "<input>") -> list[BenchEntry]:
    """Auto-detect and parse any supported benchmark format into :class:`BenchEntry` records."""
    stripped = text.lstrip()
    if not stripped:
        raise ChipError(
            f"mintchip diff: {source!r} is empty.",
            fix_hint="Pass two non-empty benchmark files (JSON, CSV, hyperfine, pytest/go/cargo bench).",
        )

    # Try structured SWE tool detectors first
    try:
        detected = detect_format(text)
    except ChipError:
        detected = ""

    if detected == "hyperfine":
        return parse_hyperfine(text)
    if detected == "pytest-bench":
        return parse_pytest_bench(text)
    if detected == "go-bench":
        return parse_go_bench(text)
    if detected == "cargo-bench":
        return parse_cargo_bench(text)

    if stripped[0] in ("{", "["):
        try:
            return _parse_generic_json(text)
        except json.JSONDecodeError as e:
            raise ChipError(
                f"mintchip diff: {source!r} is not valid JSON (line {e.lineno}: {e.msg}).",
                fix_hint="Pass valid JSON, CSV, or benchmark text output.",
            ) from None

    if "," in stripped.splitlines()[0] or "\t" in stripped.splitlines()[0]:
        return _parse_generic_csv(text)

    raise ChipError(
        f"mintchip diff: could not parse benchmark format in {source!r}.",
        fix_hint="Supported inputs: JSON, CSV, hyperfine, pytest-bench, go-bench, cargo-bench.",
    )


def _entry_se_or_half(entry: BenchEntry, scale: float) -> tuple[float | None, float | None]:
    """Return ``(standard_error, half_width_95)`` scaled by ``scale``."""
    if len(entry.samples) >= 2:
        xs = [x * scale for x in entry.samples]
        mean = sum(xs) / len(xs)
        var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
        se = math.sqrt(var / len(xs))
        return se, 1.96 * se
    if entry.ci is not None:
        half = ((entry.ci[1] - entry.ci[0]) * scale) / 2.0
        return half / 1.96, half
    if entry.stddev is not None and entry.stddev > 0:
        sd = entry.stddev * scale
        se = sd / math.sqrt(entry.n) if entry.n and entry.n > 1 else sd
        return se, 1.96 * se
    return None, None


def _diff_ci(
    base: BenchEntry, head: BenchEntry, scale_b: float, scale_h: float
) -> tuple[float, float] | None:
    """Compute a 95% confidence interval for ``head - base`` when uncertainty info exists."""
    _se_b, half_b = _entry_se_or_half(base, scale_b)
    _se_h, half_h = _entry_se_or_half(head, scale_h)
    if half_b is None and half_h is None:
        return None
    half = math.hypot(half_b or 0.0, half_h or 0.0)
    diff = head.value * scale_h - base.value * scale_b
    return (diff - half, diff + half)


def _scale_pair(
    base_entries: Sequence[BenchEntry], head_entries: Sequence[BenchEntry]
) -> tuple[float, float, str | None]:
    """Harmonize units when both sides are time measurements (ns/us/ms/s)."""
    units_b = {e.unit for e in base_entries if e.unit}
    units_h = {e.unit for e in head_entries if e.unit}
    if (
        len(units_b) == 1
        and len(units_h) == 1
        and next(iter(units_b)) in _TIME_TO_SEC
        and next(iter(units_h)) in _TIME_TO_SEC
    ):
        to_sec_b = _TIME_TO_SEC[next(iter(units_b))]
        to_sec_h = _TIME_TO_SEC[next(iter(units_h))]
        all_secs = [e.value * to_sec_b for e in base_entries] + [
            e.value * to_sec_h for e in head_entries
        ]
        mult, unit = pick_time_unit(all_secs)
        return to_sec_b * mult, to_sec_h * mult, unit
    common = next(iter(units_b)) if len(units_b) == 1 and units_b == units_h else None
    return 1.0, 1.0, common


def _format_pct(pct: float) -> str:
    sign = "+" if pct > 0 else ("-" if pct < 0 else "")
    return f"{sign}{abs(pct):.1f}%"


def diff_benchmarks(
    base_entries: Sequence[BenchEntry],
    head_entries: Sequence[BenchEntry],
    *,
    higher_is_better: bool | None = None,
    fail_on_regression: float | None = None,
    title: str | None = None,
) -> DiffResult:
    """Compare two benchmark runs and produce a shared-scale table + takeaway."""
    head_map = {e.name: e for e in head_entries}
    matched: list[tuple[BenchEntry, BenchEntry]] = [
        (b, head_map[b.name]) for b in base_entries if b.name in head_map
    ]
    if not matched:
        base_names = ", ".join(e.name for e in base_entries[:4])
        head_names = ", ".join(e.name for e in head_entries[:4])
        raise ChipError(
            "mintchip diff: no matching benchmark names between BASE and HEAD.",
            fix_hint=f"BASE has [{base_names}]; HEAD has [{head_names}].",
        )

    scale_b, scale_h, common_unit = _scale_pair(
        [b for b, _ in matched], [h for _, h in matched]
    )

    rows: list[DiffRow] = []
    for b, h in matched:
        hib = higher_is_better if higher_is_better is not None else b.higher_is_better
        bv = b.value * scale_b
        hv = h.value * scale_h
        dv = hv - bv
        pct = (dv / abs(bv) * 100.0) if bv != 0 else 0.0
        reg_pct = -pct if hib else pct
        ci_bounds = _diff_ci(b, h, scale_b, scale_h)
        rows.append(
            DiffRow(
                name=b.name,
                base=bv,
                head=hv,
                delta=dv,
                pct_change=pct,
                regression_pct=reg_pct,
                unit=common_unit or b.unit or h.unit,
                ci=ci_bounds,
                higher_is_better=hib,
            )
        )

    has_ci = any(r.ci is not None for r in rows)
    table_rows: list[dict[str, Any]] = []
    for r in rows:
        trow: dict[str, Any] = {
            "name": r.name,
            "base": mc.num(r.base, unit=r.unit),
            "head": mc.num(r.head, unit=r.unit),
            "change": mc.delta(
                r.base, r.head, higher_is_better=r.higher_is_better, unit=r.unit
            ),
        }
        if has_ci:
            if r.ci is not None:
                trow["ci"] = mc.ci(r.delta, r.ci, reference=0.0, level=0.95, unit=r.unit)
            else:
                trow["ci"] = None
        table_rows.append(trow)

    columns: dict[str, Any] = {
        "name": {"chip": "text", "header": "Benchmark"},
        "base": {"chip": "num", "header": "Base"},
        "head": {"chip": "num", "header": "Head"},
        "change": {"chip": "delta", "header": "Delta"},
    }
    if has_ci:
        columns["ci"] = {"chip": "ci", "header": "95% CI"}

    tbl = mc.table(table_rows, columns, title=title)

    # Classify outcomes (treat < 0.1% as unchanged)
    improved = [r for r in rows if r.regression_pct < -0.1]
    regressed = [r for r in rows if r.regression_pct > 0.1]
    unchanged = len(rows) - len(improved) - len(regressed)

    worst = max(rows, key=lambda r: r.regression_pct)
    best = min(rows, key=lambda r: r.regression_pct)

    regressions_over = (
        tuple(r for r in rows if r.regression_pct > fail_on_regression)
        if fail_on_regression is not None
        else ()
    )
    failed = bool(regressions_over)

    parts = [
        (
            f"Compared {len(rows)} benchmark{'s' if len(rows) != 1 else ''}: "
            f"{len(improved)} improved, {len(regressed)} regressed, {unchanged} unchanged"
        )
    ]
    if worst.regression_pct > 0.1:
        parts.append(
            f"worst regression {worst.name} ({_format_pct(worst.pct_change)}, "
            f"{_fmt.num(worst.base)}→{_fmt.num(worst.head, unit=worst.unit)})"
        )
    elif best.regression_pct < -0.1:
        parts.append(
            f"largest improvement {best.name} ({_format_pct(best.pct_change)}, "
            f"{_fmt.num(best.base)}→{_fmt.num(best.head, unit=best.unit)})"
        )
    if failed and fail_on_regression is not None:
        names = ", ".join(r.name for r in regressions_over)
        parts.append(f"FAILED >{fail_on_regression:g}% gate ({names})")

    takeaway = "; ".join(parts) + "."
    return DiffResult(
        table=tbl,
        rows=tuple(rows),
        takeaway=takeaway,
        regressions=regressions_over,
        fail_threshold=fail_on_regression,
        failed=failed,
        warnings=tbl.warnings,
    )


def render_diff(result: DiffResult, *, format: str = "text", ascii: bool = False) -> str:
    """Render a :class:`DiffResult` in text, ANSI, Markdown, HTML, or JSON."""
    from .cli import _bad_format

    if format not in OUTPUT_FORMATS:
        raise _bad_format(format, OUTPUT_FORMATS)

    takeaway = result.takeaway.replace("→", "->") if ascii else result.takeaway

    if format == "json":
        payload = {
            "takeaway": takeaway,
            "failed": result.failed,
            "fail_threshold": result.fail_threshold,
            "regressions": [
                {
                    "name": r.name,
                    "base": r.base,
                    "head": r.head,
                    "delta": r.delta,
                    "pct_change": round(r.pct_change, 4),
                    "regression_pct": round(r.regression_pct, 4),
                    "unit": r.unit,
                }
                for r in result.regressions
            ],
            "rows": [
                {
                    "name": r.name,
                    "base": r.base,
                    "head": r.head,
                    "delta": r.delta,
                    "pct_change": round(r.pct_change, 4),
                    "regression_pct": round(r.regression_pct, 4),
                    "unit": r.unit,
                    "ci": list(r.ci) if r.ci is not None else None,
                }
                for r in result.rows
            ],
            "table": result.table.to_dict(),
        }
        return json.dumps(payload, indent=2, ensure_ascii=ascii)

    if format == "md":
        return f"{result.table.markdown()}\n\n{takeaway}"

    if format == "html":
        return f'{result.table.html()}\n<p class="mc-takeaway">{_html.escape(takeaway)}</p>'

    body = result.table.text(ascii=ascii, color=format == "ansi")
    return f"{body}\n\n{takeaway}"


def add_diff_parser(sub: Any, formatter_class: Any) -> argparse.ArgumentParser:
    """Register the ``mintchip diff`` subcommand."""
    p = sub.add_parser(
        "diff",
        help="Compare two benchmark runs (JSON, CSV, hyperfine, pytest/go/cargo bench).",
        description=(
            "Compare BASE and HEAD benchmark files with zero dependencies. Outputs a shared-scale\n"
            "table with Base, Head, Delta, and 95% CI (when samples or intervals exist) plus a\n"
            "one-line takeaway. Exits 1 if any regression exceeds --fail-on-regression PCT."
        ),
        epilog="example:\n  $ mintchip diff base.json head.json --fail-on-regression 5",
        formatter_class=formatter_class,
    )
    p.add_argument("base", metavar="BASE", help="Baseline benchmark file (or - for stdin).")
    p.add_argument("head", metavar="HEAD", help="Candidate benchmark file.")
    p.add_argument(
        "--format",
        choices=OUTPUT_FORMATS,
        default="text",
        help="Output format: text (default), ansi, md, html or json.",
    )
    p.add_argument("--ascii", action="store_true", help="Pure ASCII output.")
    p.add_argument("--strict", action="store_true", help="Exit 1 on any warning.")
    p.add_argument(
        "--fail-on-regression",
        type=float,
        default=None,
        metavar="PCT",
        help="Exit 1 if any benchmark regresses by more than PCT percent (e.g. 5).",
    )
    direction = p.add_mutually_exclusive_group()
    direction.add_argument(
        "--higher-is-better",
        action="store_true",
        help="Treat higher values as better (e.g. throughput or accuracy).",
    )
    direction.add_argument(
        "--lower-is-better",
        action="store_true",
        help="Treat lower values as better (default for timings/latency).",
    )
    p.add_argument("--title", help="Optional title above the table.")
    p.set_defaults(func=cmd_diff, _parser=p)
    return p


def cmd_diff(args: argparse.Namespace) -> int:
    """Execute ``mintchip diff``."""
    from .cli import _err, _error, _out, _read, _warn

    if args.fail_on_regression is not None and args.fail_on_regression < 0:
        return _error(
            ChipError(
                f"mintchip diff: --fail-on-regression must be >= 0; got {args.fail_on_regression}.",
                fix_hint="Pass a non-negative percentage, e.g. --fail-on-regression 5.",
            )
        )

    hib: bool | None = None
    if args.higher_is_better:
        hib = True
    elif args.lower_is_better:
        hib = False

    try:
        base_entries = load_benchmark_entries(_read(args.base), source=args.base)
        head_entries = load_benchmark_entries(_read(args.head), source=args.head)
        res = diff_benchmarks(
            base_entries,
            head_entries,
            higher_is_better=hib,
            fail_on_regression=args.fail_on_regression,
            title=args.title,
        )
        out = render_diff(res, format=args.format, ascii=args.ascii)
    except ChipError as e:
        return _error(e, "mintchip diff base.json head.json")

    _out(out)
    warn_code = _warn(res.warnings, args.strict)
    if res.failed:
        names = ", ".join(
            f"{r.name} ({_format_pct(r.pct_change)})" for r in res.regressions
        )
        _err(
            f"mintchip: diff: regression exceeded {res.fail_threshold:g}% threshold: {names}"
        )
        return 1
    return warn_code
