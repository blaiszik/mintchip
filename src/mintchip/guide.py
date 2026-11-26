"""The agent guide: ``mintchip guide``, the Claude Code skill and ``llms.txt``.

Everything here is generated: the data-shape table from each kind's ``have`` and ``example``,
and every example's output by running the real command in-process, so the guide cannot drift
from the code. ``tests/test_guide.py`` keeps it under 6,000 characters and checks that the
committed ``skills/mintchip/SKILL.md`` and ``llms.txt`` match ``write()``.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from .directives import example_call, render
from .spec import catalog

__all__ = ["LIMIT", "SKILL_DESCRIPTION", "agents_snippet", "guide_text", "write"]

LIMIT = 6000  # characters; the guide is meant to be pasted into a system prompt

SKILL_DESCRIPTION = (
    "Turn numbers into word-sized graphics (sparklines, confidence intervals, before/after, "
    "pass/fail strips, small-multiple tables) in text, Markdown or HTML with one shell command. "
    "Use it any time you are about to report numbers: results, benchmarks, test runs, timings, "
    "comparisons."
)

_ROWS = [
    {"model": "retrieval", "acc": 0.82, "lift": [0.08, 0.05, 0.11], "loss": [1.84, 0.96, 0.42]},
    {"model": "warmup", "acc": 0.75, "lift": [0.01, -0.02, 0.04], "loss": [1.8, 1.3, 0.7]},
    {"model": "baseline", "acc": 0.74, "lift": None, "loss": [1.85, 1.4, 0.78]},
]
_TABLE_ARGS = [
    "--col", "model", "--col", "acc:bar", "--col", "lift:ci", "--col", "loss:spark",
    "--set", "lift.level=0.95", "--sort", "acc",
]  # fmt: skip


def _run(argv: list[str], stdin: str | None = None) -> str:
    from .cli import run

    code, out, err = run(argv, stdin)
    if code != 0 or err:
        raise RuntimeError(f"guide example failed: mintchip {' '.join(argv)}\n{err}")
    return out.rstrip("\n")


def _directive(kind: str) -> str:
    return example_call(kind, "directive", omit=("label",))


def _shape_table() -> str:
    lines = ["| You have | Directive | Prints |", "|---|---|---|"]
    for entry in catalog():
        d = _directive(entry["name"])
        lines.append(f"| {entry['have']} | `{d}` | `{render(d)[0]}` |")
    lines.append("| Three or more of the same thing | `mintchip table` (below) | |")
    return "\n".join(lines)


def guide_text() -> str:
    """The agent cheat-sheet printed by ``mintchip guide`` (Markdown, under ``LIMIT``)."""
    one = shlex.split(example_call("ci"))[1:]
    spark, ci = _directive("spark"), "{{ci 0.08 0.05:0.11 level=0.95}}"
    message = f"Val loss settled at {spark}, and retrieval lifted accuracy by {ci}."
    rows = "[\n" + ",\n".join(json.dumps(r) for r in _ROWS) + "\n]"
    table_cmd = " ".join(shlex.quote(t) for t in ["mintchip", "table", "-", *_TABLE_ARGS])
    return f"""\
# mintchip: numbers with shape, from one shell command

mintchip prints numbers as word-sized graphics for a sentence or a table cell, as text,
Markdown or HTML. The number comes first, so the sentence reads even without the glyph.

## When to use a chip
- When the numbers have a shape worth seeing: a trend, an interval, a before and after, a
  pass/fail run, parts of a whole. Put the chip right after the words it supports.
- A number with no shape is just a number: write 0.82, not a chip.
- One chip per sentence is normal; two is the ceiling.
- Three or more comparable values make a table (`mintchip table`), not a sentence.

## Pick a chip by what you have
{_shape_table()}

Reading the glyphs: a spark's number is its latest value (the full form adds the range);
strip `█` pass, `▄` warn, `×` fail, `·` skip; ci `●` when the interval excludes the reference
`│`, `○` when it crosses it.

## One grammar for commands and directives
`mintchip spark 1.84 0.96 0.42 --band 0.38:0.48` is the directive
`{{{{spark 1.84 0.96 0.42 band=0.38:0.48}}}}`. Values fill the chip's slots in order; options
are `--name value` on the command line and `name=value` in a directive.
- numbers: spaces or commas; `null` or `nan` is a gap; negatives work: `-0.2`
- ranges: `lo:hi`, e.g. `0.05:0.11`
- named parts: `name=value` (`"signed up"=520`); spans: `name=start:end`
- results: `pass warn fail skip`, or `true false null`
- flags: `--higher-is-better` / `--no-higher-is-better`; `higher_is_better=true` in a directive
- `label` and `unit` work on most chips; quote text with spaces: `--label 'Val loss'`,
  `label="Val loss"`, `unit=ms`
- all options of a chip: `mintchip KIND --help`

## 1. One chip
```
$ {example_call("ci")}
{_run(one)}
```

## 2. A whole message: render
```
$ mintchip render - <<'EOF'
{message}
EOF
{_run(["render", "-"], message + chr(10))}
```
Text outside `{{{{…}}}}` is copied unchanged (`\\{{{{` is a literal `{{{{`). A file works in
place of `-`. `--check` also flags too many chips per sentence.

## 3. A table
```
$ {table_cmd} <<'EOF'
{rows}
EOF
{_run(["table", "-", *_TABLE_ARGS], rows)}
```
Rows: a JSON list of objects or CSV, from a file or `-`. `--col KEY[:KIND[:HEADER]]` in order;
KIND is any chip name above or `text` (left out: inferred). A `ci` cell is `[estimate, low,
high]`; each chip column shares one scale. `--set KEY.OPTION=VALUE` applies to a whole column,
e.g. `--set KEY.unit=s`. `--sort KEY` (largest first, text A to Z; `--asc` or `--desc` to
choose), `--limit N`.

## Output
`--format text` (default), `md` (code spans, for GitHub and Slack), `ansi`, `html` (render: a
full page), `svg` (one chip), `json`. `--ascii` for ASCII only; `--compact` for a short value.

## When something goes wrong
stdout carries only the result. An error goes to stderr as `mintchip: error: …` plus a `fix:`
line, usually the corrected command, and exits 2: apply the fix and rerun. A
`mintchip: warning: …` (exit 0) means the chip marks a distortion, such as a clipped outlier:
say so in your text or fix the data. `--strict` makes warnings exit 1.

More: `mintchip schema` (JSON Schema for tool definitions), `mintchip catalog`. If `mintchip`
is not on PATH, run `python -m mintchip`.
"""


def agents_snippet() -> str:
    """A short block for a user's own AGENTS.md or CLAUDE.md."""
    return """\
## Reporting numbers with mintchip
When you report numbers (results, benchmarks, test runs, timings, comparisons), give the ones
with a shape a word-sized chip. Run `mintchip guide` once for the syntax. Then write the
message with `{{kind …}}` directives, e.g. `{{spark 1.84 0.96 0.42}}` or
`{{ci 0.08 0.05:0.11 level=0.95}}`, and pipe it through `mintchip render` (`--format md` for
Markdown); put three or more comparable rows in `mintchip table`. Keep one chip per sentence,
two at most, and leave numbers with no shape as plain numbers.
"""


def skill_text() -> str:
    """``skills/mintchip/SKILL.md``: the guide with Claude Code skill frontmatter."""
    desc = json.dumps(SKILL_DESCRIPTION, ensure_ascii=False)  # a valid YAML quoted scalar
    return f"---\nname: mintchip\ndescription: {desc}\n---\n\n{guide_text()}"


def llms_text() -> str:
    """``llms.txt``: a title, a one-line summary, then the guide."""
    body = guide_text().split("\n", 1)[1].lstrip("\n")
    return f"# mintchip\n\n> {SKILL_DESCRIPTION}\n\n{body}"


def write(dest: str | Path) -> list[Path]:
    """Write ``dest/skills/mintchip/SKILL.md`` and ``dest/llms.txt``; returns the paths."""
    root = Path(dest)
    files = {
        root / "skills" / "mintchip" / "SKILL.md": skill_text(),
        root / "llms.txt": llms_text(),
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return list(files)
