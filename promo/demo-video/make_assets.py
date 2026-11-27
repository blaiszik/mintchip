"""Generate real mintchip assets (src/assets.json) for the README hero demo GIF.

Every chip, table, ANSI sequence, Markdown table, HTML fragment, CSS rule, and
stderr distortion warning is produced directly by mintchip with zero mocked output.

Run with mintchip's virtualenv:
    /Users/blaiszik/Desktop/git/mintchip/.venv/bin/python make_assets.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import mintchip as mc

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE / "src"

CI_RUNS = [
    "pass",
    "pass",
    "pass",
    "pass",
    "fail",
    "pass",
    "pass",
    "pass",
    "pass",
    "pass",
    "fail",
    "fail",
]
DIST_SAMPLES = [
    146, 147, 148, 148, 149, 149, 150, 150, 151,
    151, 151, 152, 152, 153, 154, 155, 156, 240,
]

BENCH_ROWS = [
    {"input": "small.json", "main": 1.92, "new": 1.41, "change": (-27, -30, -24)},
    {"input": "medium.json", "main": 18.4, "new": 12.9, "change": (-30, -33, -27)},
    {"input": "large.json", "main": 212.0, "new": 151.0, "change": (-29, -31, -27)},
    {"input": "nested.json", "main": 44.0, "new": 46.1, "change": (5, 2, 8)},
    {"input": "unicode.json", "main": 31.2, "new": 22.8, "change": (-27, -30, -24)},
]

BENCH_COLUMNS = {
    "input": "text",
    "main": {"chip": "num", "header": "main", "unit": "ms"},
    "new": {"chip": "num", "header": "new", "unit": "ms"},
    "change": {"chip": "ci", "header": "change, 95% CI", "unit": "%", "level": 0.95},
}

BEFORE_TEXT = (
    "I ran CI and benchmarked the new parser against main (18 runs each). "
    "The last 12 CI runs on main went pass, pass, pass, pass, fail, pass, pass, pass, "
    "pass, pass, fail, fail (9 of 12 passed, 3 failed). "
    "small.json went from 1.92 ms to 1.41 ms (−27%, 95% CI −30% to −24%), "
    "medium.json from 18.4 ms to 12.9 ms (−30%, −33% to −27%), "
    "large.json from 212 ms to 151 ms (−29%, −31% to −27%), "
    "nested.json from 44.0 ms to 46.1 ms (+5%, +2% to +8%, a regression), "
    "and unicode.json from 31.2 ms to 22.8 ms (−27%, −30% to −24%). "
    "On large.json median latency was 151 ms (IQR 149 to 153 ms) with one 240 ms outlier. "
    "Peak memory fell from 84 MB to 61 MB."
)

PROSE_TEMPLATE = (
    "CI on main is {ci_strip}. The new parser is ~28% faster on 4 of 5 inputs "
    "and 5% slower on nested.json. On large.json runs took {dist_chip}; "
    "peak memory fell {mem_delta}."
)

DIRECTIVES = (
    "CI on main is {{strip " + " ".join(CI_RUNS) + "}}. "
    "The new parser is ~28% faster on 4 of 5 inputs and 5% slower on nested.json. "
    "On large.json runs took {{dist " + " ".join(str(x) for x in DIST_SAMPLES) + " unit=ms}}; "
    "peak memory fell {{delta 84 61 unit=MB higher_is_better=false}}."
)

ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")
ANSI_COLOR_MAP = {
    "31": "red",
    "32": "green",
    "33": "amber",
    "34": "blue",
    "36": "cyan",
}


def parse_ansi(text: str) -> list[dict[str, object]]:
    """Convert real ANSI SGR escape sequences into structured spans for crisp rendering."""
    spans: list[dict[str, object]] = []
    pos = 0
    color: str | None = None
    dim = False
    bold = False

    for m in ANSI_RE.finditer(text):
        if m.start() > pos:
            spans.append({"t": text[pos : m.start()], "c": color, "dim": dim, "b": bold})
        codes = [c for c in m.group(1).split(";") if c] or ["0"]
        for code in codes:
            if code == "0":
                color, dim, bold = None, False, False
            elif code == "1":
                bold = True
            elif code == "2":
                dim = True
            elif code in ANSI_COLOR_MAP:
                color = ANSI_COLOR_MAP[code]
        pos = m.end()

    if pos < len(text):
        spans.append({"t": text[pos:], "c": color, "dim": dim, "b": bold})
    return spans


def main() -> None:
    t0 = time.perf_counter()
    ci_strip = mc.strip(CI_RUNS)
    dist_chip = mc.dist(DIST_SAMPLES, unit="ms")
    mem_delta = mc.delta(84, 61, unit="MB", higher_is_better=False)
    bench_table = mc.table(BENCH_ROWS, BENCH_COLUMNS)
    ci_demo = mc.ci(-29, (-31, -27), unit="%", level=0.95)
    render_ms = round((time.perf_counter() - t0) * 1000, 1)

    prose_ansi = mc.format_prose(
        PROSE_TEMPLATE,
        format="text",
        compact=True,
        color=True,
        ci_strip=ci_strip,
        dist_chip=dist_chip,
        mem_delta=mem_delta,
    )
    prose_text = mc.format_prose(
        PROSE_TEMPLATE,
        format="text",
        compact=True,
        color=False,
        ci_strip=ci_strip,
        dist_chip=dist_chip,
        mem_delta=mem_delta,
    )
    prose_md = mc.format_prose(
        PROSE_TEMPLATE,
        format="markdown",
        compact=True,
        ci_strip=ci_strip,
        dist_chip=dist_chip,
        mem_delta=mem_delta,
    )
    # Default theme="auto" emits currentColor SVGs so light and dark themes adapt automatically.
    prose_html = mc.format_prose(
        PROSE_TEMPLATE,
        format="html",
        compact=True,
        theme="auto",
        ci_strip=ci_strip,
        dist_chip=dist_chip,
        mem_delta=mem_delta,
    )

    table_ansi = bench_table.text(color=True)
    table_text = bench_table.text(color=False)
    table_md = bench_table.markdown()
    table_html = bench_table.html(theme="auto")

    # Capture real CLI stderr warning verbatim from `mintchip render`
    cli_proc = subprocess.run(
        [sys.executable, "-m", "mintchip", "render", "--compact", "-"],
        input=DIRECTIVES,
        capture_output=True,
        text=True,
        check=True,
    )
    stderr_warning = cli_proc.stderr.strip()
    assert "beyond 3×IQR clipped" in stderr_warning, f"Unexpected stderr: {stderr_warning!r}"

    # Verify the aligned zero-line column index in the rendered forest plot table
    table_lines_plain = table_text.splitlines()
    zero_cols = {
        line.index("│") for line in table_lines_plain if "│" in line
    }
    assert len(zero_cols) == 1, f"Expected single aligned zero column, got {zero_cols}"
    zero_col = next(iter(zero_cols))

    # End-card showcase chips (real currentColor SVGs)
    end_chips = [
        {"kind": "strip", "label": "9/12 pass", "svg": ci_strip.svg(theme="auto")},
        {"kind": "dist", "label": "med 151.0 ms", "svg": dist_chip.svg(theme="auto")},
        {"kind": "delta", "label": "84→61 MB", "svg": mem_delta.svg(theme="auto")},
        {"kind": "ci", "label": "−29% (95% CI)", "svg": ci_demo.svg(theme="auto")},
    ]

    numbers_before = len(re.findall(r"[-+−]?\d+(?:\.\d+)?", BEFORE_TEXT))

    assets = {
        "before_text": BEFORE_TEXT,
        "numbers_before": numbers_before,
        "render_ms": render_ms,
        "css": mc.css(),
        "prose": {
            "text": prose_text,
            "ansi": prose_ansi,
            "ansi_spans": parse_ansi(prose_ansi),
            "md": prose_md,
            "html": prose_html,
        },
        "table": {
            "text": table_text,
            "ansi": table_ansi,
            "ansi_lines": [parse_ansi(line) for line in table_ansi.splitlines()],
            "plain_lines": table_lines_plain,
            "zero_col": zero_col,
            "md": table_md,
            "md_lines": table_md.splitlines(),
            "html": table_html,
        },
        "distortion": {
            "dist_compact_text": dist_chip.text(compact=True),
            "dist_full_text": dist_chip.text(compact=False),
            "dist_svg": dist_chip.svg(theme="auto"),
            "dist_html": dist_chip.html(theme="auto"),
            "stderr_warning": stderr_warning,
            "warnings": list(dist_chip.warnings),
        },
        "end_chips": end_chips,
    }

    SRC_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SRC_DIR / "assets.json"
    out_path.write_text(json.dumps(assets, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB, render_ms={render_ms})")
    print(f"numbers_before={numbers_before}, zero_col={zero_col}")
    print("\n--- PROSE TEXT ---")
    print(prose_text)
    print("\n--- TABLE TEXT ---")
    print(table_text)
    print("\n--- STDERR WARNING ---")
    print(stderr_warning)


if __name__ == "__main__":
    main()
