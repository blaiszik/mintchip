"""20-prompt skill trigger evaluation for mintchip.

Evaluates ``guide.SKILL_DESCRIPTION`` / generated ``SKILL.md`` and ``guide.agents_snippet()``
against 20 realistic prompts (10 positive, 10 negative, none naming ``mintchip``).

Modes:
- **Offline deterministic rubric (default):** zero network calls and zero external dependencies.
- **Live agent adapter (``--live``):** invokes ``claude -p``, ``codex exec``, or ``gemini -p``
  with the skill description context to measure real LLM routing.

Exit codes:
- ``0``: passed exit gates (recall >= 90%, false-trigger rate == 0%)
- ``1``: failed one or more exit gates
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_PROMPTS = HERE / "prompts.json"
DEFAULT_REPORT = HERE / "REPORT.md"


@dataclass(frozen=True)
class SkillTriggerSpec:
    """Trigger and negative-exclusion clauses extracted from SKILL.md + agents snippet."""

    name: str
    description: str
    snippet: str
    covers_word_sized_chips: bool
    covers_tables: bool
    covers_benchmarks_and_tests: bool
    forbids_routine_code: bool
    forbids_bare_scalars: bool
    escalates_full_plots_to_mintfig: bool


@dataclass(frozen=True)
class PromptResult:
    id: str
    category: str
    should_trigger: bool
    predicted_trigger: bool
    correct: bool
    matched_rule: str
    positive_signals: list[str]
    negative_signals: list[str]
    reason: str
    prompt: str


def parse_frontmatter(skill_md: str) -> dict[str, str]:
    """Extract simple YAML frontmatter key/value pairs from SKILL.md."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", skill_md, flags=re.DOTALL)
    if not match:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            raw = val.strip()
            if raw.startswith('"') and raw.endswith('"'):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    raw = raw.strip('"')
            else:
                raw = raw.strip("'")
            fields[key.strip()] = raw
    return fields


def extract_skill_spec(skill_md: str, snippet_md: str) -> SkillTriggerSpec:
    """Inspect SKILL.md frontmatter + body and AGENTS snippet for declared trigger rules."""
    fm = parse_frontmatter(skill_md)
    desc = fm.get("description", "")
    combined = f"{desc}\n{snippet_md}".lower()

    return SkillTriggerSpec(
        name=fm.get("name", ""),
        description=desc,
        snippet=snippet_md,
        covers_word_sized_chips=bool(
            re.search(r"word-sized", combined)
            and re.search(r"sparkline|confidence interval|before/after|pass/fail", combined)
        ),
        covers_tables=bool(
            re.search(r"(small-multiple|shared-scale)\s+tables|mintchip table", combined)
        ),
        covers_benchmarks_and_tests=bool(
            re.search(r"benchmark", combined)
            and re.search(r"test runs?", combined)
            and re.search(r"timing|diff|comparison", combined)
        ),
        forbids_routine_code=bool(
            re.search(r"do not\b", combined)
            and re.search(r"routine code|bug fix|refactor|stack trace", combined)
        ),
        forbids_bare_scalars=bool(
            re.search(r"do not\b|just a number", combined)
            and re.search(r"1[–-]3\s+bare\s+scalars|no shape", combined)
        ),
        escalates_full_plots_to_mintfig=bool(
            re.search(r"mintfig", combined)
            and re.search(r"multi-panel|publication plates?|matplotlib", combined)
        ),
    )


_FULL_PLOT_PATTERNS: list[tuple[str, str]] = [
    ("publication_journal", r"\b(nature|science|cell|pnas|neurips|manuscript)\b"),
    (
        "full_plot_artifact",
        r"\b(multi-panel|double-column|single-column|millimeters?|violin|scatter|matplotlib|pdf preflight)\b",
    ),
]

_ROUTINE_CODE_PATTERNS: list[tuple[str, str]] = [
    ("bug_fix", r"\b(fix the|keyerror|attributeerror|typeerror|bug)\b"),
    ("refactor", r"\b(refactor|helper classes|call sites|imports)\b"),
    ("stack_trace", r"\b(traceback|stack trace|nonetype)\b"),
    ("routine_edit", r"\b(argparse|cli flag|--timeout|urllib)\b"),
    ("unit_test_authoring", r"\b(write pytest unit tests?|expired jwt|hmac signatures?)\b"),
    ("git_conflict", r"\b(git rebase|merge conflict)\b"),
    ("architecture_walkthrough", r"\b(architecture of this repository|requests flow|middleware)\b"),
]

_BARE_SCALAR_PATTERNS: list[tuple[str, str]] = [
    (
        "bare_scalar_request",
        r"\b(single peak|just tell me the number|just give me those two counts|how many tests passed and how many failed)\b",
    ),
]

_CHIP_SHAPE_PATTERNS: list[tuple[str, str]] = [
    (
        "trend_or_spark",
        r"\b(trajectory|epochs?|sparkline|trend|target band)\b",
    ),
    (
        "interval_ci",
        r"\b(confidence interval|95%\s*ci|relative to zero)\b",
    ),
    (
        "before_after_delta",
        r"\b(before-and-after|from\s+\d+\s*\w*\s+down to\s+\d+|before and after)\b",
    ),
    (
        "test_strip",
        r"\b(junit\s*xml|pass/fail|suites?)\b",
    ),
    (
        "distribution_samples",
        r"\b(raw\s+.*samples?|outlier|distribution|latency samples)\b",
    ),
    (
        "share_composition",
        r"\b(git diff --numstat|breakdown of changed lines|share bar)\b",
    ),
    (
        "target_bar",
        r"\b(coverage at \d+%|against our \d+%.*target)\b",
    ),
]

_TABLE_AND_BENCH_PATTERNS: list[tuple[str, str]] = [
    (
        "benchmark_tool",
        r"\b(hyperfine|pytest-benchmark|go test -bench|cargo bench|ns/op|b/op|benchmark)\b",
    ),
    (
        "multi_row_table",
        r"\b([3-9]\s+model|comparison table|monospace table|terminal and markdown|pull request|pr summary|pr comment)\b",
    ),
    (
        "diff_regression",
        r"\b(diff these two|base\.json|head\.json|regression over \d+%)\b",
    ),
]


def _match_patterns(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    low = text.lower()
    return [name for name, pat in patterns if re.search(pat, low)]


def score_prompt_offline(prompt_item: dict[str, Any], spec: SkillTriggerSpec) -> PromptResult:
    """Deterministically score whether the declared skill rules trigger on ``prompt_item``."""
    text = str(prompt_item["prompt"])
    pub_hits = _match_patterns(text, _FULL_PLOT_PATTERNS)
    code_hits = _match_patterns(text, _ROUTINE_CODE_PATTERNS)
    scalar_hits = _match_patterns(text, _BARE_SCALAR_PATTERNS)
    chip_hits = _match_patterns(text, _CHIP_SHAPE_PATTERNS)
    bench_hits = _match_patterns(text, _TABLE_AND_BENCH_PATTERNS)

    pos_signals: list[str] = []
    neg_signals: list[str] = []
    matched_rule = "none"
    predicted = False
    reason = ""

    # 1. Escalation to full plots / publication plates (mintfig)
    if len(pub_hits) >= 2:
        if spec.escalates_full_plots_to_mintfig:
            neg_signals.extend(pub_hits)
            matched_rule = "escalate_to_mintfig"
            predicted = False
            reason = f"Deferred to mintfig for full publication plot ({', '.join(pub_hits)})."
        else:
            pos_signals.extend(pub_hits)
            matched_rule = "false_trigger_missing_escalation"
            predicted = True
            reason = "Triggered falsely because SKILL.md lacks mintfig escalation guidance."
    # 2. Bare scalar suppression (1-3 numbers with no shape)
    elif scalar_hits:
        if spec.forbids_bare_scalars:
            neg_signals.extend(scalar_hits)
            matched_rule = "suppress_bare_scalars"
            predicted = False
            reason = f"Suppressed by bare-scalar rule ({', '.join(scalar_hits)})."
        else:
            pos_signals.extend(scalar_hits)
            matched_rule = "false_trigger_missing_scalar_exclusion"
            predicted = True
            reason = "Triggered falsely because SKILL.md lacks 1-3 bare scalar exclusion."
    # 3. Routine code / bugfix / refactor / stack trace suppression
    elif code_hits and not (chip_hits or bench_hits):
        if spec.forbids_routine_code:
            neg_signals.extend(code_hits)
            matched_rule = "suppress_routine_code"
            predicted = False
            reason = f"Suppressed by routine-code exclusion ({', '.join(code_hits)})."
        elif re.search(r"\b(timeout|error|test|diff|flow|line \d+)\b", text.lower()):
            pos_signals.append("unguarded_code_term")
            matched_rule = "false_trigger_missing_code_exclusion"
            predicted = True
            reason = "Triggered falsely because SKILL.md lacks routine-code exclusion."
        else:
            neg_signals.extend(code_hits)
            matched_rule = "no_match"
            predicted = False
            reason = "No positive trigger matched."
    # 4. Positive benchmark / table trigger
    elif bench_hits and spec.covers_benchmarks_and_tests and spec.covers_tables:
        pos_signals.extend(bench_hits + chip_hits)
        matched_rule = "trigger_bench_or_table"
        predicted = True
        reason = f"Matched benchmark/table criteria ({', '.join(pos_signals)})."
    # 5. Positive word-sized chip trigger
    elif chip_hits and spec.covers_word_sized_chips:
        pos_signals.extend(chip_hits)
        matched_rule = "trigger_word_sized_chip"
        predicted = True
        reason = f"Matched word-sized chip criteria ({', '.join(chip_hits)})."
    else:
        matched_rule = "no_match"
        predicted = False
        reason = "No positive trigger rule matched."

    should = bool(prompt_item["should_trigger"])
    return PromptResult(
        id=str(prompt_item["id"]),
        category=str(prompt_item["category"]),
        should_trigger=should,
        predicted_trigger=predicted,
        correct=(predicted == should),
        matched_rule=matched_rule,
        positive_signals=pos_signals,
        negative_signals=neg_signals,
        reason=reason,
        prompt=text,
    )


def _live_routing_prompt(user_prompt: str, spec: SkillTriggerSpec) -> str:
    """Build a concise routing prompt for --live evaluation via claude/codex/gemini CLIs."""
    return (
        "You are deciding whether to invoke an installed coding-agent skill for a user request.\n\n"
        f"Available skill:\n- name: {spec.name}\n- description: {spec.description}\n\n"
        f"User request:\n{user_prompt}\n\n"
        'Respond with ONLY a single JSON object: {"trigger": true|false, "reason": "<one sentence>"}'
    )


def score_prompt_live(
    prompt_item: dict[str, Any],
    spec: SkillTriggerSpec,
    *,
    agent: str,
    model: str | None = None,
    timeout: int = 45,
) -> PromptResult:
    """Run a live CLI check against claude -p, codex exec, or gemini -p."""
    routing_prompt = _live_routing_prompt(str(prompt_item["prompt"]), spec)
    if agent == "claude":
        cmd = ["claude", "-p", routing_prompt]
        if model:
            cmd.extend(["--model", model])
    elif agent == "codex":
        cmd = ["codex", "exec", routing_prompt]
        if model:
            cmd.extend(["-m", model])
    elif agent == "gemini":
        cmd = ["gemini", "-p", routing_prompt]
        if model:
            cmd.extend(["-m", model])
    else:
        raise ValueError(f"Unsupported live agent: {agent!r} (choose claude, codex, or gemini)")

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    raw = (proc.stdout or "").strip()
    predicted = False
    reason = f"CLI exit={proc.returncode}"
    json_match = re.search(r"\{.*?\}", raw, flags=re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            predicted = bool(parsed.get("trigger", False))
            reason = str(parsed.get("reason", raw[:160]))
        except json.JSONDecodeError:
            predicted = "true" in raw.lower()
            reason = f"Unparsed output: {raw[:160]}"
    elif raw:
        predicted = bool(re.search(r"\b(true|yes|mintchip)\b", raw.lower()))
        reason = f"Plain output: {raw[:160]}"

    should = bool(prompt_item["should_trigger"])
    return PromptResult(
        id=str(prompt_item["id"]),
        category=str(prompt_item["category"]),
        should_trigger=should,
        predicted_trigger=predicted,
        correct=(predicted == should),
        matched_rule=f"live_{agent}",
        positive_signals=["live_yes"] if predicted else [],
        negative_signals=["live_no"] if not predicted else [],
        reason=reason,
        prompt=str(prompt_item["prompt"]),
    )


def evaluate_prompts(
    prompts_data: dict[str, Any],
    skill_md: str,
    snippet_md: str,
    *,
    live: bool = False,
    agent: str = "claude",
    model: str | None = None,
    limit: int | None = None,
    timeout: int = 45,
) -> dict[str, Any]:
    """Run the 20-prompt evaluation (offline or --live) and check exit gates."""
    spec = extract_skill_spec(skill_md, snippet_md)
    gates = prompts_data.get("exit_gates", {})
    min_recall = float(gates.get("min_recall", 0.90))
    max_ftr = float(gates.get("max_false_trigger_rate", 0.0))

    prompts = list(prompts_data["prompts"])
    if limit is not None:
        prompts = prompts[:limit]

    results = [
        score_prompt_live(item, spec, agent=agent, model=model, timeout=timeout)
        if live
        else score_prompt_offline(item, spec)
        for item in prompts
    ]
    tp = sum(1 for r in results if r.should_trigger and r.predicted_trigger)
    fn = sum(1 for r in results if r.should_trigger and not r.predicted_trigger)
    fp = sum(1 for r in results if not r.should_trigger and r.predicted_trigger)
    tn = sum(1 for r in results if not r.should_trigger and not r.predicted_trigger)

    pos_total = tp + fn
    neg_total = fp + tn
    recall = tp / pos_total if pos_total else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    false_trigger_rate = fp / neg_total if neg_total else 0.0
    accuracy = (tp + tn) / len(results) if results else 0.0

    passed = recall >= min_recall and false_trigger_rate <= max_ftr

    return {
        "mode": f"live:{agent}" if live else "offline_rubric",
        "passed": passed,
        "gates": {
            "min_recall": min_recall,
            "max_false_trigger_rate": max_ftr,
        },
        "metrics": {
            "total": len(results),
            "positives": pos_total,
            "negatives": neg_total,
            "tp": tp,
            "fn": fn,
            "fp": fp,
            "tn": tn,
            "recall": recall,
            "precision": precision,
            "false_trigger_rate": false_trigger_rate,
            "accuracy": accuracy,
        },
        "skill_spec_checks": {
            "covers_word_sized_chips": spec.covers_word_sized_chips,
            "covers_tables": spec.covers_tables,
            "covers_benchmarks_and_tests": spec.covers_benchmarks_and_tests,
            "forbids_routine_code": spec.forbids_routine_code,
            "forbids_bare_scalars": spec.forbids_bare_scalars,
            "escalates_full_plots_to_mintfig": spec.escalates_full_plots_to_mintfig,
        },
        "results": [asdict(r) for r in results],
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    """Format an evaluation report as Markdown."""
    m = report["metrics"]
    g = report["gates"]
    status = "PASS" if report["passed"] else "FAIL"
    mode = report.get("mode", "offline_rubric")
    lines = [
        "# Mintchip Skill Trigger Evaluation Report",
        "",
        f"**Status:** `{status}` | **Mode:** `{mode}`",
        "",
        "| Metric | Value | Gate |",
        "|---|---:|---:|",
        f"| Recall (TP / Pos) | {m['recall']:.1%} ({m['tp']}/{m['positives']}) | >= {g['min_recall']:.0%} |",
        f"| False-trigger rate (FP / Neg) | {m['false_trigger_rate']:.1%} ({m['fp']}/{m['negatives']}) | <= {g['max_false_trigger_rate']:.0%} |",
        f"| Precision (TP / (TP+FP)) | {m['precision']:.1%} | — |",
        f"| Accuracy | {m['accuracy']:.1%} ({m['tp'] + m['tn']}/{m['total']}) | — |",
        "",
        "## Skill Spec Checks",
        "",
    ]
    for key, ok in report["skill_spec_checks"].items():
        lines.append(f"- `{'PASS' if ok else 'FAIL'}` {key}")
    lines.extend(["", "## Per-Prompt Outcomes", "", "| ID | Expected | Predicted | Rule |", "|---|---|---|---|"])
    for r in report["results"]:
        exp = "trigger" if r["should_trigger"] else "no"
        pred = "trigger" if r["predicted_trigger"] else "no"
        lines.append(f"| `{r['id']}` | {exp} | {pred} | `{r['matched_rule']}` |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    from mintchip import guide

    parser = argparse.ArgumentParser(description="Run the 20-prompt mintchip skill trigger eval.")
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    parser.add_argument("--skill", type=Path, default=None, help="Optional SKILL.md path (defaults to guide.skill_text()).")
    parser.add_argument("--report", type=Path, default=None, help="Optional path to write Markdown report.")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print JSON summary to stdout.")
    parser.add_argument("--live", action="store_true", help="Run live routing via an installed agent CLI.")
    parser.add_argument(
        "--agent",
        choices=("claude", "codex", "gemini"),
        default="claude",
        help="Agent CLI to invoke in --live mode (default: claude).",
    )
    parser.add_argument("--model", default=None, help="Optional model override for --live mode.")
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only the first N prompts.")
    parser.add_argument("--timeout", type=int, default=45, help="Per-prompt timeout in seconds (--live).")
    args = parser.parse_args(argv)

    prompts_data = json.loads(args.prompts.read_text(encoding="utf-8"))
    skill_md = args.skill.read_text(encoding="utf-8") if args.skill else guide.skill_text()
    snippet_md = guide.agents_snippet()

    report = evaluate_prompts(
        prompts_data,
        skill_md,
        snippet_md,
        live=args.live,
        agent=args.agent,
        model=args.model,
        limit=args.limit,
        timeout=args.timeout,
    )
    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        m = report["metrics"]
        tag = "PASS" if report["passed"] else "FAIL"
        print(
            f"[{tag}] mode={report['mode']} recall={m['recall']:.1%} ({m['tp']}/{m['positives']}) "
            f"false_trigger_rate={m['false_trigger_rate']:.1%} ({m['fp']}/{m['negatives']}) "
            f"precision={m['precision']:.1%}"
        )
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(render_markdown_report(report), encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
