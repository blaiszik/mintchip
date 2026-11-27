# Mintchip Offline Skill Trigger Eval

Deterministic 20-prompt evaluation suite (10 positive, 10 negative, none naming `mintchip`)
testing `mintchip.guide.SKILL_DESCRIPTION`, `mintchip.guide.skill_text()`, and
`mintchip.guide.agents_snippet()`.

## Exit Gates

- **Recall:** `>= 90%` on positive prompts (inline chips, shared-scale tables, SWE tool outputs, benchmark diffs)
- **False-trigger rate:** `0%` on negative prompts (routine code edits, bug fixes, refactoring, stack traces, 1–3 bare scalars, and full multi-panel publication plots that belong in `mintfig`)

## Usage

```bash
python evals/trigger_eval/eval_triggers.py
python evals/trigger_eval/eval_triggers.py --report evals/trigger_eval/REPORT.md
pytest tests/test_trigger_eval.py
```
