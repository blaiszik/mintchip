"""Regenerate every example in the README and the gallery from real mintchip calls.

    python gallery/build_gallery.py           # write README blocks and gallery/output/
    python gallery/build_gallery.py --check   # exit 1 if anything committed is stale

Nothing shown in README.md or gallery/ is typed by hand: each output block comes from
``mintchip.cli.run`` or the Python API, and each image is drawn from the chips' own SVG.
Generated Markdown sits between ``<!-- BEGIN mintchip:NAME -->`` and ``<!-- END mintchip:NAME
-->`` markers; text outside the markers is left alone. ``tests/test_readme.py`` and
``tests/test_gallery.py`` fail when the committed files differ from what this script makes now.

Images are files, because GitHub strips inline SVG and ``data:`` URIs from Markdown. A chip is
saved as a standalone SVG that sets its own light and dark text colour. A sentence or a table
is typeset here as an SVG of ``<text>`` plus the chips' ``<svg>`` elements nested at their real
1em size, with the same light/dark ``<style>``; text runs carry ``textLength`` so a font with
other metrics cannot push text into a chip.
"""

from __future__ import annotations

import argparse
import code
import contextlib
import html
import io
import json
import re
import shlex
import sys
import textwrap
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import mintchip as mc
from mintchip import guide
from mintchip.cli import run
from mintchip.directives import example_call, parse_tokens
from mintchip.themes import DARK_INK, LIGHT_INK

GALLERY = ROOT / "gallery"
OUT = GALLERY / "output"
README = ROOT / "README.md"
GALLERY_README = GALLERY / "README.md"
WRAP = 80  # terminal width for wrapped prose

# ================================================================================================
# Content. Inputs are written here; every output is computed from them.
# ================================================================================================

# fmt: off
LOSS = {
    "retrieval": [1.84, 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43, 0.42],
    "reranker": [1.86, 1.41, 1.05, 0.83, 0.69, 0.6, 0.55, 0.52, 0.51],
    "warmup": [1.8, 1.52, 1.25, 1.04, 0.9, 0.81, 0.75, 0.72, 0.7],
    "baseline": [1.85, 1.6, 1.36, 1.15, 0.99, 0.89, 0.83, 0.8, 0.78],
}

# Three before/after pairs. "before" is the message an agent typically writes; "prose" is the
# same message with {{…}} directives for `mintchip render`; "table" is one `mintchip table`.
PAIRS: dict[str, dict[str, Any]] = {
    "experiment": {
        "title": "An experiment summary",
        "before": (
            "The ablation finished (5 seeds, 8k steps each). Retrieval did best: validation loss "
            "went from 1.84 to 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43 and finally 0.42, which is "
            "inside the 0.38–0.48 target band, and accuracy reached 0.82, a lift of +0.08 over the "
            "baseline (95% CI +0.05 to +0.11). The reranker reached 0.79 accuracy (+0.05, 95% CI "
            "+0.02 to +0.08) with a final validation loss of 0.51. Warmup reached 0.75 (+0.01, "
            "95% CI −0.02 to +0.04), so its effect is not distinguishable from zero; its "
            "validation loss ended at 0.70. The baseline reached 0.74 accuracy and a final "
            "validation loss of 0.78."
        ),
        "prose": (
            "The ablation finished (5 seeds, 8k steps). Retrieval wins: val loss settled at "
            "{{spark 1.84 1.32 0.96 0.74 0.61 0.52 0.46 0.43 0.42 band=0.38:0.48}}, inside the "
            "target band, and accuracy rose by {{ci 0.08 0.05:0.11 level=0.95}}. Warmup's "
            "interval crosses zero, so drop it."
        ),
        "rows": [
            {"variant": v, "acc": a, "lift": lift, "loss": LOSS[v]}
            for v, a, lift in [
                ("retrieval", 0.82, [0.08, 0.05, 0.11]),
                ("reranker", 0.79, [0.05, 0.02, 0.08]),
                ("warmup", 0.75, [0.01, -0.02, 0.04]),
                ("baseline", 0.74, None),
            ]
        ],
        "file": "runs.json",
        "args": [
            "--col", "variant", "--col", "acc:num:accuracy", "--col", "lift:ci:lift, 95% CI",
            "--col", "loss:spark:val loss", "--set", "lift.level=0.95",
        ],
    },
    "tests": {
        "title": "A test run",
        "before": (
            "I ran the full test suite on the branch: 412 of 418 tests passed, 4 failed and 2 "
            "were skipped. All four failures are in the io module (test_parse_dates, "
            "test_tz_roundtrip, test_csv_quoting, test_unicode_names). The last 12 CI runs on "
            "main went pass, pass, pass, pass, fail, pass, pass, pass, pass, pass, fail, fail, so "
            "the breakage started two runs ago. Coverage went from 81.2% to 83.4%. By module: io "
            "ran 96 tests in 22.4 s and failed 4, and was red in 3 of its last 8 runs; parse ran "
            "140 tests in 14.1 s, all passing; api ran 118 in 9.8 s, all passing, but failed once "
            "in its last 8 runs; cli ran 64 in 6.2 s with 2 skipped."
        ),
        "prose": (
            "412 of 418 tests pass. All 4 failures are in io, and main has been red for its last "
            "two runs {{strip pass pass pass pass fail pass pass pass pass pass fail fail}}. "
            "Coverage rose {{delta 81.2 83.4 unit=% higher_is_better=true}}."
        ),
        "rows": [
            {"module": "io", "failed": 4, "time": 22.4,
             "runs": ["pass", "pass", "fail", "pass", "pass", "pass", "fail", "fail"]},
            {"module": "parse", "failed": 0, "time": 14.1, "runs": ["pass"] * 8},
            {"module": "api", "failed": 0, "time": 9.8,
             "runs": ["pass", "pass", "pass", "fail", "pass", "pass", "pass", "pass"]},
            {"module": "cli", "failed": 0, "time": 6.2, "runs": ["pass"] * 8},
        ],
        "file": "modules.json",
        "args": [
            "--col", "module", "--col", "failed:num", "--col", "time:bar:time",
            "--col", "runs:strip:last 8 runs", "--set", "time.total=52.5", "--set", "time.unit=s",
        ],
    },
    "benchmark": {
        "title": "A benchmark comparison",
        "before": (
            "I benchmarked the new parser against main on five inputs, 18 runs each. small.json "
            "went from 1.92 ms to 1.41 ms (−27%, 95% CI −30% to −24%), medium.json from 18.4 ms "
            "to 12.9 ms (−30%, −33% to −27%), large.json from 212 ms to 151 ms (−29%, −31% to "
            "−27%), nested.json from 44.0 ms to 46.1 ms (+5%, +2% to +8%, a regression) and "
            "unicode.json from 31.2 ms to 22.8 ms (−27%, −30% to −24%). On large.json the median "
            "run took 151 ms with an interquartile range of 149 to 153 ms, but one run took "
            "240 ms. Peak memory fell from 84 MB to 61 MB."
        ),
        "prose": (
            "The new parser is about 28% faster on four of five inputs and 5% slower on "
            "nested.json. On large.json the runs took {{dist 146 147 148 148 149 149 150 150 "
            "151 151 151 152 152 153 154 155 156 240 unit=ms}}; the one slow run is an "
            "outlier. Peak memory fell {{delta 84 61 unit=MB higher_is_better=false}}."
        ),
        "rows": [
            {"input": n, "main": a, "new": b, "change": c}
            for n, a, b, c in [
                ("small.json", 1.92, 1.41, [-27, -30, -24]),
                ("medium.json", 18.4, 12.9, [-30, -33, -27]),
                ("large.json", 212, 151, [-29, -31, -27]),
                ("nested.json", 44.0, 46.1, [5, 2, 8]),
                ("unicode.json", 31.2, 22.8, [-27, -30, -24]),
            ]
        ],
        "file": "bench.json",
        "args": [
            "--col", "input", "--col", "main:num:main", "--col", "new:num:new",
            "--col", "change:ci:change, 95% CI", "--set", "main.unit=ms", "--set", "new.unit=ms",
            "--set", "change.unit=%", "--set", "change.level=0.95",
        ],
    },
}

# Recipes for coding agents: one real command each.
RECIPES: list[tuple[str, str, list[str]]] = [
    (
        "Test results",
        "CI jobs or test files, each pass, warn, fail or skip:",
        ["strip", "pass", "pass", "pass", "warn", "fail", "pass", "skip",
         "--names", "lint,types,unit,docs,e2e,bench,gpu"],
    ),
    (
        "Diff size",
        "Changed lines by area, from `git diff --numstat`:",
        ["share", "src=310", "tests=142", "docs=48", "--unit", "lines"],
    ),
    (
        "Coverage",
        "Against the previous run and the project's target:",
        ["bar", "0.834", "--baseline", "0.812", "--target", "0.85", "--label", "coverage"],
    ),
    (
        "Benchmark before and after",
        "Say which direction is better, so a regression shows in red:",
        ["delta", "212", "151", "--unit", "ms", "--no-higher-is-better", "--label", "p50"],
    ),
    (
        "Time per phase",
        "Where the seconds of a CI run went:",
        ["timeline", "install=12", "collect=9", "test=61", "report=12"],
    ),
    (
        "Context budget",
        "Tokens used out of the window; past the total, the bar says so:",
        ["bar", "148000", "--total", "200000", "--unit", "tokens", "--label", "context"],
    ),
]

# Per chip: a sentence around its registered example ({chip}), siblings for a table column
# (rows plus `mintchip table` arguments), and edge cases (title, command tokens).
CHIPS: dict[str, dict[str, Any]] = {
    "num": {
        "sentence": "Held-out accuracy was {chip} across five seeds.",
        "rows": [
            {"model": "retrieval", "acc": {"value": 0.82, "pm": 0.03}},
            {"model": "reranker", "acc": {"value": 0.79, "pm": 0.02}},
            {"model": "baseline", "acc": {"value": 0.74, "pm": 0.04}},
        ],
        "args": ["--col", "model", "--col", "acc:num:accuracy"],
        "edges": [
            ("Significant figures", ["num", "0.0012345", "--unit", "s", "--sig", "2"]),
            ("A signed change", ["num", "0.08", "--signed"]),
        ],
    },
    "spark": {
        "sentence": "Val loss settled at {chip} after 8k steps.",
        "rows": [{"run": k, "loss": LOSS[k]} for k in ("retrieval", "warmup", "baseline")],
        "args": ["--col", "run", "--col", "loss:spark:val loss"],
        "edges": [
            ("Two series", ["spark", *map(str, LOSS["retrieval"]), "--vs",
                            *map(str, LOSS["baseline"])]),
            ("A range under 2 % of the level",
             ["spark", "0.4200", "0.4201", "0.4203", "0.4206", "0.4204", "0.4206"]),
            ("A spike in 40 points", ["spark", *(["1"] * 17), "50", *(["1"] * 22)]),
            ("A domain that cuts the data",
             ["spark", "1.84", "1.32", "0.96", "0.74", "0.61", "--domain", "0.5:1.5"]),
        ],
    },
    "ci": {
        "sentence": "Retrieval lifted accuracy by {chip}.",
        "rows": [
            {"variant": "retrieval", "lift": [0.08, 0.05, 0.11]},
            {"variant": "reranker", "lift": [0.05, 0.02, 0.08]},
            {"variant": "warmup", "lift": [0.01, -0.02, 0.04]},
        ],
        "args": ["--col", "variant", "--col", "lift:ci:lift, 95% CI", "--set", "lift.level=0.95"],
        "edges": [
            ("The interval crosses the reference", ["ci", "0.01", "-0.02:0.04", "--level", "0.95"]),
            ("No level stated", ["ci", "0.08", "0.05:0.11"]),
            ("A domain that cuts the interval",
             ["ci", "0.08", "0.05:0.11", "--level", "0.95", "--domain", "0:0.1"]),
        ],
    },
    "dist": {
        "sentence": "Latency over ten requests was {chip}.",
        "rows": [
            {"region": "us-east", "lat": [18.9, 19.4, 19.8, 20.1, 20.3, 20.3, 20.9, 21.6, 22.8]},
            {"region": "eu-west", "lat": [21.0, 21.8, 22.4, 22.9, 23.1, 23.6, 24.4, 25.9, 27.0]},
            {"region": "ap-south", "lat": [24.2, 25.1, 26.0, 26.4, 27.7, 28.3, 29.9, 31.5, 33.0]},
        ],
        "args": ["--col", "region", "--col", "lat:dist:latency", "--set", "lat.unit=ms"],
        "edges": [
            ("An outlier beyond 3×IQR", ["dist", "18.9", "19.4", "19.8", "20.1", "20.3", "20.3",
                                         "20.9", "21.6", "22.8", "47.8", "--unit", "ms"]),
            ("A threshold", ["dist", "18.9", "19.4", "19.8", "20.1", "20.3", "20.3", "20.9",
                             "21.6", "22.8", "25.7", "--unit", "ms", "--threshold", "21"]),
            ("Missing samples", ["dist", "18.9", "null", "19.8", "20.1", "nan", "20.3", "20.9",
                                 "--unit", "ms"]),
            ("Three samples", ["dist", "20.1", "20.4", "22.9", "--unit", "ms"]),
            ("All samples equal", ["dist", *(["20"] * 10), "--unit", "ms"]),
        ],
    },
    "bar": {
        "sentence": "Line coverage reached {chip}.",
        "rows": [
            {"package": "core", "cov": 0.82},
            {"package": "io", "cov": 0.64},
            {"package": "cli", "cov": 0.93},
        ],
        "args": ["--col", "package", "--col", "cov:bar:coverage", "--set", "cov.target=0.9"],
        "edges": [
            ("Over the total", ["bar", "1.12"]),
            ("Against a baseline", ["bar", "0.834", "--baseline", "0.812", "--target", "0.85"]),
        ],
    },
    "gauge": {
        "sentence": "Arterial pH read {chip}.",
        "rows": [
            {"sample": "06:00", "ph": 7.38},
            {"sample": "12:00", "ph": 7.47},
            {"sample": "18:00", "ph": 7.31},
        ],
        "args": ["--col", "sample", "--col", "ph:gauge:pH", "--set", "ph.normal=7.35:7.45"],
        "edges": [
            ("Above the normal range", ["gauge", "7.5", "7.35:7.45"]),
            ("A domain that cuts the reading",
             ["gauge", "7.6", "7.35:7.45", "--domain", "7.3:7.5"]),
        ],
    },
    "delta": {
        "sentence": "Accuracy went {chip} with retrieval.",
        "rows": [
            {"metric": "accuracy", "d": [0.74, 0.82]},
            {"metric": "recall", "d": [0.61, 0.7]},
            {"metric": "precision", "d": [0.8, 0.78]},
        ],
        "args": ["--col", "metric", "--col", "d:delta:before → after",
                 "--set", "d.higher_is_better=true"],
        "edges": [
            ("A change for the worse", ["delta", "0.80", "0.78", "--higher-is-better"]),
            ("Lower is better", ["delta", "212", "151", "--unit", "ms", "--no-higher-is-better"]),
            ("No direction stated", ["delta", "0.74", "0.82"]),
            ("A domain that cuts the change", ["delta", "0.74", "0.82", "--domain", "0.7:0.8"]),
        ],
    },
    "strip": {
        "sentence": "The last eight runs on main went {chip}.",
        "rows": [
            {"job": "lint", "runs": ["pass"] * 8},
            {"job": "unit", "runs": ["pass", "pass", "fail", "pass", "pass", "pass", "pass",
                                     "pass"]},
            {"job": "e2e", "runs": ["pass", "warn", "pass", "fail", "fail", "pass", "skip",
                                    "fail"]},
        ],
        "args": ["--col", "job", "--col", "runs:strip:last 8 runs"],
        "edges": [
            ("More items than cells",
             ["strip", *(["pass"] * 13), "fail", *(["pass"] * 9), "warn", *(["pass"] * 6)]),
            ("Named items", ["strip", "pass", "fail", "pass", "--names", "lint,unit,e2e"]),
        ],
    },
    "share": {
        "sentence": "The diff is {chip} code, docs and tests.",
        "rows": [
            {"pr": "#412", "split": {"code": 62, "docs": 28, "tests": 10}},
            {"pr": "#415", "split": {"code": 48, "docs": 40, "tests": 12}},
            {"pr": "#418", "split": {"code": 85, "docs": 10, "tests": 5}},
        ],
        "args": ["--col", "pr", "--col", "split:share:code · docs · tests"],
        "edges": [
            ("A part under one cell", ["share", "code=97", "docs=2.5", "tests=0.5"]),
            ("More parts than segments", ["share", "a=30", "b=20", "c=15", "d=10", "e=8", "f=7",
                                          "g=5", "h=5"]),
            ("In the given order", ["share", "tests=10", "docs=28", "code=62", "--no-sort"]),
        ],
    },
    "ratio": {
        "sentence": "Only {chip} seeds converged.",
        "rows": [
            {"config": "lr 3e-4", "ok": [3, 10]},
            {"config": "lr 1e-4", "ok": [7, 10]},
            {"config": "lr 3e-5", "ok": [9, 10]},
        ],
        "args": ["--col", "config", "--col", "ok:ratio:converged"],
        "edges": [
            ("A ratio that does not round to whole icons", ["ratio", "412", "418"]),
            ("A small total", ["ratio", "1", "3"]),
        ],
    },
    "timeline": {
        "sentence": "The agent's turn took {chip}.",
        "rows": [
            {"turn": "plan", "phases": {"fetch": 1.2, "solve": 4.8, "write": 1.5}},
            {"turn": "edit", "phases": {"fetch": 0.8, "solve": 2.1, "write": 1.0}},
            {"turn": "test", "phases": {"fetch": 3.9, "solve": 5.2, "write": 1.1}},
        ],
        "args": ["--col", "turn", "--col", "phases:timeline:time"],
        "edges": [
            ("A phase under one cell", ["timeline", "fetch=0.1", "solve=6.8", "write=0.6"]),
            ("Overlapping phases", ["timeline", "fetch=0:1.2", "solve=1:6", "write=5.5:7"]),
        ],
    },
    "rank": {
        "sentence": "Our model placed {chip} on the leaderboard.",
        "rows": [
            {"model": "ours", "rank": [2, 18]},
            {"model": "last release", "rank": [7, 18]},
            {"model": "baseline", "rank": [15, 18]},
        ],
        "args": ["--col", "model", "--col", "rank:rank:rank"],
        "edges": [
            ("Ranked among values", ["rank", "--values", "0.72", "0.81", "0.88", "0.79",
                                     "--value", "0.85"]),
        ],
    },
    "waterfall": {
        "sentence": "Accuracy went from {chip}.",
        "rows": [
            {"release": "v2", "steps": {"start": 0.63, "steps": {"retrieval": 0.13,
                                                                  "reranker": 0.08,
                                                                  "latency cap": -0.02}}},
            {"release": "v3", "steps": {"start": 0.82, "steps": {"distill": -0.03,
                                                                  "data": 0.05}}},
        ],
        "args": ["--col", "release", "--col", "steps:waterfall:accuracy"],
        "edges": [
            ("More steps than terms", ["waterfall", "a=0.05", "b=0.04", "c=-0.03", "d=0.02",
                                       "e=0.02", "f=-0.01", "g=0.01", "--start", "0.6"]),
        ],
    },
    "funnel": {
        "sentence": "Of the visitors, {chip} stayed a month.",
        "rows": [
            {"cohort": "March", "f": {"visited": 1200, "signed up": 520, "activated": 350,
                                      "retained": 290}},
            {"cohort": "April", "f": {"visited": 1450, "signed up": 480, "activated": 410,
                                      "retained": 380}},
        ],
        "args": ["--col", "cohort", "--col", "f:funnel:funnel"],
        "edges": [
            ("A stage larger than the one before",
             ["funnel", "visited=1200", "signed=520", "activated=560"]),
        ],
    },
}

# fmt: on


# Specimens for tests/test_presentation.py: every edge case above, as chips.
def edge_chips() -> list[tuple[str, mc.Chip]]:
    out = []
    for kind, entry in CHIPS.items():
        if kind not in mc.REGISTRY:
            continue
        for title, argv in entry["edges"]:
            out.append((f"{kind}: {title}", chip_from_argv(argv)))
    return out


def chip_from_argv(argv: list[str]) -> mc.Chip:
    kind, *tokens = argv
    return mc.REGISTRY[kind].fn(**parse_tokens(kind, tokens))


# ================================================================================================
# Running commands
# ================================================================================================


def mintchip(argv: list[str], stdin: str | None = None) -> tuple[str, str]:
    """Run ``mintchip argv`` in-process; returns (stdout, stderr). Errors stop the build."""
    status, out, err = run(argv, stdin)
    if status == 2:
        raise SystemExit(f"build_gallery: mintchip {shlex.join(argv)} failed:\n{err}")
    return out.rstrip("\n"), err.rstrip("\n")


def shell(argv: list[str]) -> str:
    """``$ mintchip …`` quoted for a POSIX shell, broken before options past ~88 columns."""
    words = ["mintchip"] + [shlex.quote(a) for a in argv]
    lines, cur = [], "$"
    for w in words:
        if len(cur) + 1 + len(w) > 88 and w.startswith("--") and cur != "$":
            lines.append(cur + " \\")
            cur = "   "
        cur += " " + w
    lines.append(cur)
    return "\n".join(lines)


def transcript(argv: list[str], stdin: str | None = None, *, file: str | None = None) -> str:
    """A command and what it prints, stderr included, as a reader would see it. With
    ``stdin``, the command reads ``-`` and is shown with a heredoc, or, given ``file``, as
    reading that file (whose content is ``stdin``)."""
    out, err = mintchip(argv, stdin)
    if stdin is None:
        head = shell(argv)
    elif file is None:
        head = shell(argv) + " <<'EOF'\n" + stdin.rstrip("\n") + "\nEOF"
    else:
        head = shell([file if a == "-" else a for a in argv])
    return "\n".join(x for x in (head, out, err) if x)


def rows_json(rows: list[dict[str, Any]]) -> str:
    return "[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n]\n"


def wrap_render(prose: str, rendered: str) -> str:
    """Wrap ``mintchip render`` output at ``WRAP`` columns without breaking inside a chip."""
    from mintchip.directives import find, shared_domains

    _, found = find(prose)
    keep = rendered
    for d, dom in zip(found, shared_domains([d.chip for d in found]), strict=True):
        t = d.chip.text(domain=dom)
        keep = keep.replace(t, t.replace(" ", "\u00a0"), 1)
    paragraphs = keep.split("\n\n")
    wrapped = "\n\n".join(
        textwrap.fill(p, WRAP, break_long_words=False, break_on_hyphens=False) for p in paragraphs
    )
    out = wrapped.replace("\u00a0", " ")
    assert " ".join(out.split()) == " ".join(rendered.split()), "wrapping changed the text"
    return out


# ================================================================================================
# Typesetting text plus chips as SVG
# ================================================================================================

FS = 15.0  # px; the chips are 1em of this
FONT = "Arial, Helvetica, 'Liberation Sans', sans-serif"  # metric-compatible faces
ASCENT = 0.905

# Advance widths of Arial/Helvetica, in thousandths of an em.
_W = dict(zip(" !\"#$%&'()*+,-./", [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584,
                                     278, 333, 278, 278], strict=True))  # fmt: skip
_W.update(dict.fromkeys("0123456789", 556))
_W.update(dict(zip(":;<=>?@", [278, 278, 584, 584, 584, 556, 1015], strict=True)))
_W.update(dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", [667, 667, 722, 722, 667, 611, 778, 722, 278,
               500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667,
               611], strict=True)))  # fmt: skip
_W.update(dict(zip("[\\]^_`", [278, 278, 278, 469, 556, 333], strict=True)))
_W.update(dict(zip("abcdefghijklmnopqrstuvwxyz", [556, 556, 500, 556, 556, 278, 556, 556, 222,
               222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500,
               500], strict=True)))  # fmt: skip
_W.update({"{": 334, "|": 260, "}": 334, "~": 584, "–": 556, "—": 1000, "−": 584, "±": 584,
           "×": 584, "·": 278, "→": 1000, "’": 222, "‘": 222, "“": 333, "”": 333, "…": 1000,
           "\u2007": 556, "\u00a0": 278})  # fmt: skip
_BOLD = dict(zip("abcdefghijklmnopqrstuvwxyz", [556, 611, 556, 611, 556, 333, 611, 611, 278,
             278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556,
             500], strict=True))  # fmt: skip


def text_width(s: str, size: float = FS, bold: bool = False) -> float:
    total = 0
    for ch in s:
        w = _BOLD.get(ch) if bold else None
        total += w if w is not None else _W.get(ch, 556) * (1.06 if bold else 1)
    return total * size / 1000


def _num(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _style() -> str:
    """Light and dark colours for a composed image, taken from mintchip.css()."""
    css = mc.css()
    light = re.search(r"^:root\{([^}]*)\}", css)
    dark = re.search(r"prefers-color-scheme:dark\)\{:root\{([^}]*)\}", css)
    assert light and dark, "mintchip.css() no longer declares :root colours"
    return (
        f"<style>svg{{color:{LIGHT_INK};{light[1]}}}"
        f"@media (prefers-color-scheme:dark){{svg{{color:{DARK_INK};{dark[1]}}}}}"
        "text{fill:currentColor}.m{fill-opacity:.66}.b{font-weight:600}"
        ".r{stroke:currentColor;stroke-opacity:.4;stroke-width:1}</style>"
    )


def nest(svg: str, x: float, top: float, size: float = FS) -> tuple[str, float]:
    """Place a chip's SVG at (x, top), 1em = ``size`` px; returns (markup, width in px)."""
    m = re.match(r'<svg [^>]*viewBox="0 0 ([\d.]+) 16"', svg)
    assert m, svg[:80]
    w = float(m[1]) / 16 * size
    svg = re.sub(
        r' width="[\d.]+em" height="1em"',
        f' x="{_num(x)}" y="{_num(top)}" width="{_num(w)}" height="{_num(size)}"',
        svg,
        count=1,
    )
    return svg, w


class _Tokens(HTMLParser):
    """HTML (chip markup, a <p>, or an mc-table) to a flat token list, skipping popovers.
    SVGs are swapped for placeholders first, because HTMLParser lower-cases viewBox."""

    VOID = frozenset({"br", "img", "hr", "meta", "input", "link"})

    def __init__(self, svgs: list[str]) -> None:
        super().__init__(convert_charrefs=True)
        self.svgs, self.out, self.stack, self.skip = svgs, [], [], 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if self.skip:
            self.skip += tag not in self.VOID
            return
        if "popover" in a:
            self.skip = 1
            return
        if tag in self.VOID:
            return
        self.stack.append(set((a.get("class") or "").split()))
        if tag in ("tr", "th", "td", "p", "thead", "tbody"):
            self.out.append(("open", tag, a))

    def handle_endtag(self, tag: str) -> None:
        if self.skip:
            self.skip -= 1
            return
        if self.stack:
            self.stack.pop()
        if tag in ("tr", "th", "td", "p", "thead", "tbody"):
            self.out.append(("close", tag, {}))

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        classes = set().union(*self.stack) if self.stack else set()
        for n, piece in enumerate(re.split(r"\x00(\d+)\x00", data)):
            if n % 2:
                self.out.append(("svg", self.svgs[int(piece)], classes))
            elif piece:
                self.out.append(("text", piece, classes))


def tokens(markup: str) -> list[tuple[Any, ...]]:
    svgs: list[str] = []

    def stash(m: re.Match[str]) -> str:
        svgs.append(m[0])
        return f"\x00{len(svgs) - 1}\x00"

    p = _Tokens(svgs)
    p.feed(re.sub(r"<svg\b.*?</svg>", stash, markup, flags=re.DOTALL))
    p.close()
    return p.out


class Sheet:
    """A column of typeset blocks, drawn as one SVG with light/dark text colour."""

    def __init__(self, measure: float = 34 * FS) -> None:
        self.measure, self.y, self.width, self.parts = measure, 0.0, 0.0, []

    # -- prose ---------------------------------------------------------------------------------
    def paragraph(self, markup: str, lh: float = 1.55) -> None:
        """Typeset the inline content of one <p>: words and chips, wrapped to the measure."""
        words: list[list[tuple[Any, ...]]] = [[]]
        value = None
        for t in tokens(markup):
            if t[0] == "text" and "mc-v" in t[2]:
                value = t[1]
            elif t[0] == "svg":
                words[-1].append(("chip", value or "", t[1]))
                value = None
            elif t[0] == "text":
                if value is not None and not t[1].strip():
                    continue  # the space between a chip's value and its graphic
                if value is not None:
                    words[-1].append(("chip", value, ""))
                    value = None
                for n, w in enumerate(re.split(r"[ \n]+", t[1])):
                    if n:
                        words.append([])
                    if w:
                        words[-1].append(("t", w))
        if value is not None:
            words[-1].append(("chip", value, ""))
        words = [w for w in words if w]
        space = text_width(" ")
        lines: list[list[list[tuple[Any, ...]]]] = [[]]
        x = 0.0
        for w in words:
            ww = sum(self._seg_width(s) for s in w)
            if lines[-1] and x + space + ww > self.measure:
                lines.append([])
                x = 0.0
            x += (space if lines[-1] else 0) + ww
            lines[-1].append(w)
        line_h = lh * FS
        for line in lines:
            base = self.y + (line_h - 1.117 * FS) / 2 + ASCENT * FS
            self._line(line, base)
            self.y += line_h

    def _seg_width(self, seg: tuple[Any, ...]) -> float:
        if seg[0] == "t":
            return text_width(seg[1])
        _, value, svg = seg
        w = text_width(value)
        if svg:
            m = re.match(r'<svg [^>]*viewBox="0 0 ([\d.]+) 16"', svg)
            w += (text_width(" ") if value else 0) + float(m[1]) / 16 * FS  # type: ignore[index]
        return w

    def _line(self, line: list[list[tuple[Any, ...]]], base: float) -> None:
        x, run, run_x = 0.0, "", 0.0
        space = text_width(" ")

        def flush() -> None:
            nonlocal run
            if run:
                self.text(run, run_x, base)
            run = ""

        for i, word in enumerate(line):
            for k, seg in enumerate(word):
                lead = bool(i and not k)  # a space before this segment
                if seg[0] == "t":
                    if run:
                        run += " " * lead + seg[1]
                    else:
                        run_x, run = x + space * lead, seg[1]
                    x += space * lead + text_width(seg[1])
                    continue
                flush()
                x += space * lead
                _, value, svg = seg
                if value:
                    self.text(value, x, base)
                    x += text_width(value)
                if svg:
                    x += space if value else 0
                    markup, w = nest(svg, x, base + 0.15 * FS - FS)
                    self.parts.append(markup)
                    x += w
        flush()
        self.width = max(self.width, x)

    def text(self, s: str, x: float, base: float, *, cls: str = "", anchor: str = "",
             size: float = FS, fit: bool = True) -> None:  # fmt: skip
        """One run of text; ``textLength`` pins its width to the Arial metrics used for
        layout, so another font cannot run it into the next chip."""
        attrs = f'x="{_num(x)}" y="{_num(base)}"'
        if cls:
            attrs += f' class="{cls}"'
        if anchor:
            attrs += f' text-anchor="{anchor}"'
        if size != FS:
            attrs += f' font-size="{_num(size)}"'
        if fit and len(s) > 1:
            w = text_width(s, size, bold="b" in cls.split())
            attrs += f' textLength="{_num(w)}" lengthAdjust="spacing"'
        self.parts.append(f"<text {attrs}>{html.escape(s, quote=False)}</text>")

    def gap(self, px: float) -> None:
        self.y += px

    def label(self, s: str) -> None:
        """A small muted heading above a block."""
        self.text(s, 0, self.y + 0.8 * FS * 0.85, cls="m", size=0.8 * FS)
        self.y += 1.6 * FS * 0.85

    # -- tables --------------------------------------------------------------------------------
    def table(self, markup: str) -> None:
        """Typeset ``Table.html()``: hairlines under the header and the last row, values
        right-aligned, each chip column's graphics on its shared scale."""
        rows: list[dict[str, Any]] = []
        section = ""
        for t in tokens(markup):
            if t[0] == "open" and t[1] in ("thead", "tbody"):
                section = t[1]
            elif t[0] == "open" and t[1] == "tr":
                rows.append({"section": section, "cls": t[2].get("class") or "", "cells": []})
            elif t[0] == "open" and t[1] in ("th", "td"):
                a = t[2]
                rows[-1]["cells"].append({
                    "tag": t[1], "cls": (a.get("class") or "").split(),
                    "span": int(a.get("colspan") or 1), "segs": [],
                })  # fmt: skip
            elif t[0] in ("text", "svg") and rows and rows[-1]["cells"]:
                rows[-1]["cells"][-1]["segs"].append(t)
        body = [r for r in rows if r["section"] == "tbody"]
        ncols = sum(c["span"] for c in body[0]["cells"])
        # As in mintchip.css(): a gutter of 1.25em before every column, .45em between a value
        # and its own graphic, so a numbers-only column is as far from the next as any other.
        cells = body[0]["cells"]
        pad = [
            0 if j == len(cells) - 1 else (0.45 if "mc-graph" in cells[j + 1]["cls"] else 1.25) * FS
            for j in range(len(cells))
        ]
        widths = [0.0] * ncols

        def content(cell: dict[str, Any], bold: bool) -> float:
            w = 0.0
            for s in cell["segs"]:
                if s[0] == "svg":
                    m = re.match(r'<svg [^>]*viewBox="0 0 ([\d.]+) 16"', s[1])
                    w += float(m[1]) / 16 * FS  # type: ignore[index]
                elif "mc-lo" in s[2] or "mc-hi" in s[2]:
                    w += text_width(s[1].strip(), 0.75 * FS) + (0.5 * FS if "mc-lo" in s[2] else 0)
                else:
                    w += text_width(s[1].strip(), bold=bold)
            return w

        for r in rows:
            j = 0
            for c in r["cells"]:
                need = content(c, r["section"] == "thead" and "mc-scale" not in r["cls"])
                span = range(j, j + c["span"])
                have = sum(widths[k] for k in span)
                if need > have:
                    widths[span[-1]] += need - have
                j += c["span"]
        xs = [0.0]
        for w, p in zip(widths, pad, strict=True):
            xs.append(xs[-1] + w + p)
        total = xs[-1]
        lh, vpad = 1.4 * FS, 0.3 * FS
        for n, r in enumerate(rows):
            scale = "mc-scale" in r["cls"]
            first_body = r["section"] == "tbody" and (n == 0 or rows[n - 1]["section"] != "tbody")
            last_body = r["section"] == "tbody" and n == len(rows) - 1
            last_head = r["section"] == "thead" and rows[n + 1]["section"] != "thead"
            top = 0 if scale else (0.5 * FS if first_body else vpad)
            bottom = 0.5 * FS if last_body else vpad
            size = 0.75 * FS if scale else FS
            row_h = top + (1.4 * size if scale else lh) + bottom
            base = self.y + top + ((1.4 * size if scale else lh) - 1.117 * size) / 2 + ASCENT * size
            j = 0
            for c in r["cells"]:
                x0, x1 = xs[j], xs[j + c["span"] - 1] + widths[j + c["span"] - 1]
                self._cell(c, r["section"] == "thead" and not scale, x0, x1, base)
                j += c["span"]
            self.y += row_h
            if last_head or last_body:
                self.parts.append(f'<path class="r" d="M0 {_num(self.y - 0.5)}H{_num(total)}"/>')
        self.width = max(self.width, total)

    def _cell(self, c: dict[str, Any], head: bool, x0: float, x1: float, base: float) -> None:
        num = "mc-num" in c["cls"]
        for s in c["segs"]:
            if s[0] == "svg":
                markup, _ = nest(s[1], x0, base + 0.15 * FS - FS)
                self.parts.append(markup)
                continue
            raw = s[1]
            if not raw.strip():
                continue
            cls = " ".join(x for x in ("b" * head, "m" * ("mc-empty" in c["cls"])) if x)
            if "mc-lo" in s[2] or "mc-hi" in s[2]:
                graph_end = x0 + (x1 - x0)
                x, anchor = (x0, "") if "mc-lo" in s[2] else (graph_end, "end")
                self.text(raw.strip(), x, base, cls="m", anchor=anchor, size=0.75 * FS)
            elif num:
                trail = len(raw) - len(raw.rstrip("\u2007"))
                x = x1 - trail * text_width("\u2007")
                self.text(raw.strip("\u2007 "), x, base, cls=cls, anchor="end")
            else:
                self.text(raw.strip(), x0, base, cls=cls)

    def svg(self, title: str) -> str:
        w, h = max(self.width, 1.0), self.y
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(w + 2)}" height="{_num(h)}" '
            f'viewBox="-1 0 {_num(w + 2)} {_num(h)}" font-family="{FONT}" font-size="{_num(FS)}" '
            f'role="img" aria-label="{html.escape(title, quote=True)}">'
            f"<title>{html.escape(title)}</title>{_style()}{''.join(self.parts)}</svg>\n"
        )


def paragraphs(page: str) -> list[str]:
    """The inner HTML of each <p> in a ``mintchip render --format html`` page."""
    return re.findall(r"<p>(.*?)</p>", page, flags=re.DOTALL)


def table_markup(html_out: str) -> str:
    m = re.search(r'<table class="mc-table".*?</table>', html_out, flags=re.DOTALL)
    assert m, "no mc-table in the table command's html output"
    return m[0]


# ================================================================================================
# Building blocks
# ================================================================================================


def pair_outputs(slug: str) -> dict[str, Any]:
    """Everything one before/after pair shows: text, commands and the HTML pieces."""
    p = PAIRS[slug]
    prose, rows = p["prose"] + "\n", rows_json(p["rows"])
    text, _ = mintchip(["render", "-"], prose)
    table_text, _ = mintchip(["table", "-", *p["args"]], rows)
    page, _ = mintchip(["render", "-", "--format", "html"], prose)
    table_html, _ = mintchip(["table", "-", *p["args"], "--format", "html"], rows)
    return {
        "before": textwrap.fill(p["before"], WRAP),
        "after": wrap_render(p["prose"], text) + "\n\n" + table_text,
        "commands": (
            f"$ cat message.txt\n{p['prose']}\n"
            + transcript(["render", "-"], prose, file="message.txt")
            + f"\n\n$ cat {p['file']}\n{rows}"
            + transcript(["table", "-", *p["args"]], rows, file=p["file"])
        ),
        "paragraphs": paragraphs(page),
        "table": table_markup(table_html),
    }  # fmt: skip


def pair_image(slug: str) -> str:
    o = pair_outputs(slug)
    sheet = Sheet()
    for para in o["paragraphs"]:
        sheet.paragraph(para)
    sheet.gap(0.8 * FS)
    sheet.table(o["table"])
    sheet.gap(2)
    return sheet.svg(f"{PAIRS[slug]['title']}, rendered as HTML by mintchip")


def para(s: str) -> str:
    """A Markdown paragraph wrapped at 100 columns (never inside a code span)."""
    words = re.findall(r"`[^`]*`\S*|\S+", s)
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > 100:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    return "\n".join([*lines, cur])


def pair_markdown(slug: str, image: str, *, heading: str | None = None) -> str:
    """Before as text; after as the HTML render (an image), then as it prints in a terminal."""
    o = pair_outputs(slug)
    head = f"### {heading}\n\n" if heading else ""
    title = PAIRS[slug]["title"]
    return (
        f"{head}**Before**: the report as an agent usually writes it.\n\n"
        f"```text\n{o['before']}\n```\n\n"
        + para(
            "**After**: the same report with two chips and one table, rendered as HTML "
            "(`--format html`) in your light or dark theme,"
        )
        + "\n\n"
        f"![{title}, rendered as HTML]({image})\n\n"
        f"and as it prints in a terminal:\n\n```text\n{o['after']}\n```\n\n"
        "<details><summary>The two commands that wrote it</summary>\n\n"
        f"```text\n{o['commands']}\n```\n\n</details>"
    )


def sentence_prose(kind: str) -> str:
    directive = example_call(kind, "directive", omit=("label",))
    template = CHIPS.get(kind, {}).get("sentence", "The result came to {chip}.")
    return template.replace("{chip}", directive)


def chip_card(kind: str) -> str:
    """The chip at 1× in a sentence, then beside its siblings in one table column."""
    sheet = Sheet()
    page, _ = mintchip(["render", "-", "--format", "html"], sentence_prose(kind) + "\n")
    for para in paragraphs(page):
        sheet.paragraph(para)
    entry = CHIPS.get(kind)
    if entry:
        sheet.gap(0.5 * FS)
        out, _ = mintchip(["table", "-", *entry["args"], "--format", "html"],
                          rows_json(entry["rows"]))  # fmt: skip
        sheet.table(table_markup(out))
    sheet.gap(2)
    return sheet.svg(f"mintchip {kind} in a sentence and in a table")


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def kinds() -> list[str]:
    return [e["name"] for e in mc.CATALOG]


def has_svg(kind: str) -> bool:
    return mc.REGISTRY[kind].svg is not None


def python_session(lines: list[str]) -> str:
    """Run ``lines`` as an interactive session and return it with real output, doctest-style."""
    console = code.InteractiveConsole({})
    shown = []
    for line in lines:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            more = console.push(line)
        assert not more, f"incomplete statement: {line}"
        shown.append(f">>> {line}")
        if buf.getvalue():
            shown.append(buf.getvalue().rstrip("\n"))
    return "\n".join(shown)


# ================================================================================================
# README.md
# ================================================================================================


def readme_blocks() -> dict[str, str]:
    blocks: dict[str, str] = {}
    blocks["hero"] = pair_markdown("experiment", "gallery/output/pairs/experiment.svg")

    one = ["spark", *map(str, LOSS["retrieval"]), "--band", "0.38:0.48"]
    message = (
        "Val loss settled at {{spark 1.84 1.32 0.96 0.74 0.61 0.52 0.46 0.43 0.42 "
        "band=0.38:0.48}}, and retrieval lifted accuracy by {{ci 0.08 0.05:0.11 level=0.95}}."
    )
    rows = rows_json([{k: r[k] for k in ("variant", "acc", "lift")}
                      for r in PAIRS["experiment"]["rows"]])  # fmt: skip
    table = ["table", "-", "--col", "variant", "--col", "acc:num:accuracy",
             "--col", "lift:ci:lift, 95% CI", "--set", "lift.level=0.95"]  # fmt: skip
    blocks["commands"] = "\n\n".join([
        para("**One chip.** Values fill the chip's slots in order; options are `--name value`."),
        f"```text\n{transcript(one)}\n```",
        para(
            "**A message.** `render` replaces each `{{kind …}}` directive in the prose with its "
            "chip. The tokens are the ones the command line takes, with options as `name=value`."
        ),
        f"```text\n{transcript(['render', '-'], message + chr(10))}\n```",
        para(
            "**A table.** Three or more comparable things go in a table, and each chip column "
            "shares one scale: the `ci` column below is a forest plot with one zero line."
        ),
        f"```text\n{transcript(table, rows)}\n```",
        para(
            "Every command takes `--format text|md|ansi|html|svg|json`, `--ascii` and "
            "`--compact`. stdout carries only the result. A distortion, such as a clipped outlier "
            "or a cut axis, is marked in the chip and named in a warning on stderr; `--strict` "
            "makes that exit 1."
        ),
    ])  # fmt: skip

    lines = ["| You have | Chip | At 1× | As text |", "|---|---|---|---|"]
    for entry in mc.CATALOG:
        k = entry["name"]
        c = mc.REGISTRY[k].example_chip()
        img = f"![{k}](gallery/output/chips/{k}.svg)" if has_svg(k) else "—"
        text = c.text(compact=True).replace("|", "\\|")
        lines.append(f"| {entry['have']} | [`{k}`](gallery/README.md#{k}) | {img} | `{text}` |")
    lines.append("| Three or more of the same thing | `mintchip table` | | |")
    blocks["catalog"] = "\n".join(lines)

    blocks["agents"] = f"```markdown\n{guide.agents_snippet().rstrip()}\n```"

    session = python_session([
        "import mintchip as mc",
        f"loss = mc.spark({LOSS['retrieval']}, band=(0.38, 0.48))",
        "print(loss)",
        "lift = mc.ci(0.08, (0.05, 0.11), level=0.95)",
        ('print(mc.format_prose("Loss settled at {loss}; accuracy rose by {lift}.", '
         "loss=loss, lift=lift))"),
        "lift.to_dict()",
        ('rows = [{"run": "retrieval", "lift": (0.08, 0.05, 0.11)}, '
         '{"run": "warmup", "lift": (0.01, -0.02, 0.04)}]'),
        'print(mc.table(rows, {"run": "text", "lift": {"chip": "ci", "level": 0.95}}))',
    ])  # fmt: skip
    blocks["python"] = f"```python\n{session}\n```\n\n" + para(
        "A chip is a small record; drawing happens when you render it: `chip.text(ascii=, "
        "compact=, color=)`, `chip.markdown()`, `chip.svg(theme=, standalone=)`, `chip.html()` "
        "(inline, with a popover that needs no JavaScript) and `chip.save('x.svg')`. Prose and "
        "tables render the same ways, and `mc.document(title, blocks)` makes a whole page "
        "styled by `mc.css()`."
    )
    return blocks


# ================================================================================================
# gallery/README.md and gallery/output
# ================================================================================================


def recipe_blocks() -> list[tuple[str, str, str]]:
    return [(title, why, transcript(argv)) for title, why, argv in RECIPES]


def edge_blocks(kind: str) -> list[tuple[str, str, str, mc.Chip]]:
    """(title, file name, transcript, chip) per edge case."""
    out = []
    for title, argv in CHIPS.get(kind, {}).get("edges", []):
        out.append((title, f"{kind}-{slug(title)}.svg", transcript(argv), chip_from_argv(argv)))
    return out


def example_transcript(kind: str) -> str:
    """The kind's registered example as a command, plain, --ascii and --compact."""
    argv = shlex.split(example_call(kind))[1:]
    return "\n".join(transcript(argv + extra) for extra in ([], ["--ascii"], ["--compact"]))


def chip_section_md(kind: str) -> str:
    k = mc.REGISTRY[kind]
    lines = [
        f'<a id="{kind}"></a>',
        f"### `{kind}`: {k.question}",
        "",
        f"You have: {k.have[0].lower()}{k.have[1:]}.",
        "",
        f"![{kind} in a sentence and in a table](output/cards/{kind}.svg)",
        "",
        f"```text\n{example_transcript(kind)}\n```",
    ]
    edges = edge_blocks(kind)
    if edges:
        lines += ["", "Edge cases:", ""]
        for title, fname, shown, chip in edges:
            img = f" ![{title}](output/edge/{fname})" if has_svg(kind) and chip.svg() else ""
            lines += [f"- **{title}.**{img}", "", textwrap.indent(f"```text\n{shown}\n```", "  ")]
    return "\n".join(lines)


def gallery_blocks() -> dict[str, str]:
    blocks: dict[str, str] = {}
    blocks["pairs"] = "\n\n".join(
        pair_markdown(s, f"output/pairs/{s}.svg", heading=PAIRS[s]["title"])
        for s in ("tests", "benchmark")
    )
    blocks["recipes"] = "\n\n".join(
        f"**{title}.** {why}\n\n```text\n{shown}\n```" for title, why, shown in recipe_blocks()
    )
    blocks["chips"] = "\n\n".join(chip_section_md(k) for k in kinds())
    return blocks


_EXTRA_CSS = (
    ".mc-doc>pre{grid-column:2/4;font:.8em/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,"
    "monospace;overflow-x:auto;white-space:pre;margin:0 0 1.2em;padding:.6em 0;"
    "border-top:1px solid color-mix(in srgb,currentColor 18%,transparent);"
    "border-bottom:1px solid color-mix(in srgb,currentColor 18%,transparent)}"
    ".mc-doc>h2{margin-top:2.2em}.mc-doc>h3{font-size:1em;margin:1.6em 0 .3em}"
    ".mc-doc>.q{color:color-mix(in srgb,currentColor 66%,transparent);margin-bottom:.3em}"
    ".mc-doc .before{color:color-mix(in srgb,currentColor 80%,transparent)}"
    ".mc-doc code{font-size:.9em}"
)


def _pre(s: str) -> str:
    return f"<pre>{html.escape(s)}</pre>"


def _render_html(prose: str) -> list[str]:
    page, _ = mintchip(["render", "-", "--format", "html"], prose + "\n")
    return [f"<p>{p}</p>" for p in paragraphs(page)]


def index_html() -> str:
    """The gallery as one reading page: live chips (click for details), light and dark."""
    b: list[str] = [
        (
            "<p>Every chip and every output on this page comes from <code>mintchip</code> "
            "itself, generated by <code>gallery/build_gallery.py</code>. Click a chip for its "
            "details.</p>"
        ),
        "<h2>Before and after</h2>",
    ]
    for s, p in PAIRS.items():
        o = pair_outputs(s)
        b += [
            f"<h3>{html.escape(p['title'])}</h3>",
            '<p class="q">Before:</p>',
            f'<p class="before">{html.escape(p["before"])}</p>',
            '<p class="q">After:</p>',
        ]
        b += _render_html(p["prose"])
        out, _ = mintchip(["table", "-", *p["args"], "--format", "html"], rows_json(p["rows"]))
        b += [out, _pre(o["commands"])]  # fmt: skip
    b.append("<h2>Recipes for coding agents</h2>")
    for title, why, shown in recipe_blocks():
        b += [f"<h3>{html.escape(title)}</h3>", f"<p>{_md_inline(why)}</p>", _pre(shown)]
    b.append("<h2>The chips</h2>")
    for kind in kinds():
        k = mc.REGISTRY[kind]
        b += [
            f'<h3 id="{kind}"><code>{kind}</code>: {html.escape(k.question)}</h3>',
            f'<p class="q">You have: {html.escape(k.have[0].lower() + k.have[1:])}.</p>',
        ]
        b += _render_html(sentence_prose(kind))
        entry = CHIPS.get(kind)
        if entry:
            out, _ = mintchip(["table", "-", *entry["args"], "--format", "html"],
                              rows_json(entry["rows"]))  # fmt: skip
            b.append(out)
        b.append(_pre(example_transcript(kind)))
        for title, _, shown, chip in edge_blocks(kind):
            b += [f"<p><b>{html.escape(title)}.</b> {chip.html()}</p>", _pre(shown)]
    page = mc.document(
        "mintchip gallery",
        b,
        subtitle="Word-sized graphics for numbers, at their real size, in light and dark.",
        source="gallery/build_gallery.py",
    )
    return stable_ids(page.replace("</style>", _EXTRA_CSS + "</style>", 1))


def stable_ids(page: str) -> str:
    """Number popover ids by order on the page. mintchip makes them unique per process with a
    counter, so the same page built after other renders would otherwise differ."""
    ids: dict[str, str] = {}

    def renumber(m: re.Match[str]) -> str:
        return ids.setdefault(m[0], f"{m[1]}-{len(ids) + 1}")

    return re.sub(r"\b(mc-[0-9a-f]{8})-\d+\b", renumber, page)


def _md_inline(s: str) -> str:
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(s))


_BASELINE_CSS = (
    "body{margin:0;padding:16px;font:13px/1.4 system-ui,sans-serif}"
    "h1{font-size:16px;margin:0 0 4px}p.note{margin:0 0 12px;max-width:60em}"
    ".row{display:grid;grid-template-columns:9em 1fr 1fr;gap:8px;align-items:stretch;"
    "margin:0 0 6px}.name{font:12px/1.3 ui-monospace,Menlo,monospace;padding-top:6px;"
    "overflow-wrap:anywhere}.panel{padding:4px 12px;border-radius:3px}"
    ".panel p{font:15px/1.5 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;margin:0}"
)


def baseline_html() -> str:
    """Every chip, example and edge cases, in a 15 px sentence on light and dark panels."""
    specimens = [(f"{k}", mc.REGISTRY[k].example_chip()) for k in kinds()]
    specimens += [(f"{k}: {t}", c) for k in kinds() for t, _, _, c in edge_blocks(k)]
    rows = []
    for name, chip in specimens:
        panels = "".join(
            f'<div class="panel mc-page" data-mc-scheme="{scheme}"><p>Over five seeds it came '
            f"to {chip.html(details=False)} and held.</p></div>"
            for scheme in ("light", "dark")
        )
        rows.append(f'<div class="row"><div class="name">{html.escape(name)}</div>{panels}</div>')
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        "<title>mintchip 1× baseline</title>\n"
        f"<style>{mc.css()}{_BASELINE_CSS}</style>\n</head>\n<body>\n"
        "<h1>mintchip 1× baseline</h1>\n"
        '<p class="note">Every chip in a 15 px sentence, light and dark, at device scale 1. '
        "Checklist: every mark visible, no chip taller than the line, no colour outside its "
        "role (blue: look here; green, red, amber: only for a declared direction or "
        "pass/warn/fail).</p>\n" + "\n".join(rows) + "\n</body>\n</html>\n"
    )


# ================================================================================================
# Files
# ================================================================================================


def outputs() -> dict[Path, str]:
    """Every file under gallery/output, by path."""
    files: dict[Path, str] = {}
    for s in PAIRS:
        files[OUT / "pairs" / f"{s}.svg"] = pair_image(s)
    for kind in kinds():
        c = mc.REGISTRY[kind].example_chip()
        if has_svg(kind):
            files[OUT / "chips" / f"{kind}.svg"] = c.svg(standalone=True) + "\n"
        files[OUT / "cards" / f"{kind}.svg"] = chip_card(kind)
        for _, fname, _, chip in edge_blocks(kind):
            if has_svg(kind) and chip.svg():
                files[OUT / "edge" / fname] = chip.svg(standalone=True) + "\n"
    files[OUT / "index.html"] = index_html()
    files[OUT / "baseline.html"] = baseline_html()
    return files


_MARKER = re.compile(
    r"(<!-- BEGIN mintchip:(?P<name>[\w-]+) -->\n)(?P<body>.*?)(<!-- END mintchip:(?P=name) -->)",
    re.DOTALL,
)


def fill(text: str, blocks: dict[str, str], where: str) -> str:
    """Replace the body of every marker block in ``text``; every block must have a marker."""
    seen = set()

    def sub(m: re.Match[str]) -> str:
        name = m["name"]
        if name not in blocks:
            raise SystemExit(f"build_gallery: {where} has a marker for unknown block {name!r}")
        seen.add(name)
        return m[1] + blocks[name].rstrip("\n") + "\n" + m[4]

    out = _MARKER.sub(sub, text)
    missing = set(blocks) - seen
    if missing:
        raise SystemExit(f"build_gallery: {where} lacks markers for {', '.join(sorted(missing))}")
    return out


def documents() -> dict[Path, str]:
    """README.md and gallery/README.md with their generated blocks filled in."""
    return {
        README: fill(README.read_text(encoding="utf-8"), readme_blocks(), "README.md"),
        GALLERY_README: fill(
            GALLERY_README.read_text(encoding="utf-8"), gallery_blocks(), "gallery/README.md"
        ),
    }


def stale(files: dict[Path, str]) -> list[Path]:
    """Files under gallery/output that the build would not write."""
    return sorted(p for p in OUT.rglob("*") if p.is_file() and p not in files)


def build(*, check: bool = False) -> list[str]:
    """Write everything (or, with ``check``, only report); returns what was or would be
    changed."""
    files = {**documents(), **outputs()}
    changed = []
    for path, content in files.items():
        old = path.read_text(encoding="utf-8") if path.exists() else None
        if old != content:
            changed.append(f"{'would write' if check else 'wrote'} {path.relative_to(ROOT)}")
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
    for path in stale(files):
        changed.append(f"{'would delete' if check else 'deleted'} {path.relative_to(ROOT)}")
        if not check:
            path.unlink()
    if not check:
        for d in sorted((p for p in OUT.rglob("*") if p.is_dir()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report stale files; write nothing")
    a = ap.parse_args(argv)
    changed = build(check=a.check)
    for line in changed:
        print(line)
    if a.check:
        return 1 if changed else 0
    print(f"{len(changed)} file(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
