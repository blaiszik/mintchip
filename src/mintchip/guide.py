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

__all__ = [
    "LIMIT",
    "SKILL_DESCRIPTION",
    "agents_snippet",
    "guide_text",
    "llms_text",
    "skill_text",
    "write",
]

LIMIT = 6000  # characters; the guide is meant to be pasted into a system prompt

SKILL_DESCRIPTION = (
    "Turn numbers with shape into word-sized graphics (sparklines, confidence intervals, "
    "before/after deltas, pass/fail strips, distributions, shares, shared-scale tables) in text, "
    "Markdown or HTML with one zero-dep shell command. Use when reporting results, benchmarks, "
    "test runs, timings, diffs, or comparisons. Do NOT use for routine code edits, bug fixes, "
    "refactoring, stack traces, or 1-3 bare scalars with no shape. Reach for mintfig when you "
    "need full multi-panel plots, 2D relationships, publication plates, or Matplotlib auditing."
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
- Give numbers with shape a chip (trend, interval, before/after, pass/fail, share) after the
  words they support.
- A number with no shape is just a number: write 0.82. One chip per sentence is normal;
  two is the ceiling. Three or more comparable values make a table (`mintchip table`).
- Do NOT use for routine code edits, bug fixes, refactoring, stack traces, or 1–3 bare scalars.
- Use `mintchip` for inline chips & terminal/Markdown/PR tables; reach for `mintfig` for
  multi-panel plots, 2D relationships, publication plates, or Matplotlib auditing.

## Pick a chip by what you have
{_shape_table()}

Glyphs: spark shows its latest value; strip `█` pass, `▄` warn, `×` fail, `·` skip; ci `●`
excludes reference `│`, `○` crosses it.

## One grammar for commands and directives
`mintchip spark 1.84 0.96 0.42 --band 0.38:0.48` == `{{{{spark 1.84 0.96 0.42 band=0.38:0.48}}}}`.
Values fill slots in order; options are `--name value` (CLI) or `name=value` (directive).
- numbers: spaces/commas (`null`/`nan` gap, `-0.2` ok); ranges: `lo:hi` (`0.05:0.11`)
- parts: `name=value` (`"signed up"=520`); spans: `name=start:end`; results: `pass warn fail skip`
- flags: `--higher-is-better` / `--no-higher-is-better` (`higher_is_better=true`); `label`, `unit`
  work on most chips; full options: `mintchip KIND --help`

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
Text outside `{{{{…}}}}` (and inside Markdown code blocks/spans) passes through (`\\{{{{` is
literal `{{{{`). `--check` lints chip density.

## 3. A table
```
$ {table_cmd} <<'EOF'
{rows}
EOF
{_run(["table", "-", *_TABLE_ARGS], rows)}
```
Rows: JSON, JSONL, CSV or TSV from a file or stdin (`-`). `--col KEY[:KIND[:HEADER]]` (inferred
if omitted); `ci` cells take `[est, lo, hi]`; columns share scales. `--set KEY.OPTION=VALUE`,
`--sort KEY` (`--asc`/`--desc`), `--limit N`, `--highlight ROW`, `--baseline ROW`.

## 4. SWE tool outputs & benchmark diffs
- `mintchip from auto [FILE]` ingests `git-diff`, `hyperfine`, `junit`, `pytest/go/cargo-bench`,
  `k6`, `esbuild`, `github-actions`, and `chrome-trace` directly into chips or tables.
- `mintchip diff base.json head.json --fail-on-regression 5` compares runs with 95% CI noise gating.

## Output & errors
Use `--format md` for Markdown/PRs (code spans) and `--format text` for terminals (`ansi`, `html`,
`svg`, `json`, `--ascii`, `--compact`, `-o FILE`). Errors go to stderr (`fix:`, exit 2); warnings
exit 1 with `--strict`. Not on PATH? Use `uvx mintchip` or `python -m mintchip`.
More: `mintchip doctor`, `mintchip skill`, `mintchip schema`, `mintchip catalog`.
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
