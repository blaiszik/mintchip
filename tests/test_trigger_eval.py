"""Tests for the 20-prompt offline mintchip skill trigger evaluation suite."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from mintchip import guide

REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = REPO_ROOT / "evals" / "trigger_eval"
PROMPTS_PATH = EVAL_DIR / "prompts.json"
SCRIPT_PATH = EVAL_DIR / "eval_triggers.py"


def _load_eval_module():
    spec = importlib.util.spec_from_file_location("mintchip_eval_triggers", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_prompts_json_integrity() -> None:
    data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    prompts = data["prompts"]
    assert len(prompts) == 20

    positives = [p for p in prompts if p["should_trigger"] is True]
    negatives = [p for p in prompts if p["should_trigger"] is False]
    assert len(positives) == 10
    assert len(negatives) == 10

    ids = [p["id"] for p in prompts]
    assert len(set(ids)) == 20

    for item in prompts:
        text = item["prompt"]
        assert isinstance(text, str) and len(text.strip()) >= 20
        assert "mintchip" not in text.lower(), f"Prompt {item['id']} must never mention mintchip"
        assert "mintchip" not in item["id"].lower()
        assert "mintchip" not in item["category"].lower()


def test_offline_trigger_eval_passes_exit_gates() -> None:
    mod = _load_eval_module()
    prompts_data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))
    report = mod.evaluate_prompts(prompts_data, guide.skill_text(), guide.agents_snippet())

    assert report["passed"] is True
    assert report["metrics"]["recall"] >= 0.90
    assert report["metrics"]["false_trigger_rate"] == 0.0
    assert report["metrics"]["total"] == 20

    for key, ok in report["skill_spec_checks"].items():
        assert ok is True, f"Expected {key} to be declared in SKILL_DESCRIPTION / guide"


def test_offline_scorer_catches_regressed_skill_description() -> None:
    mod = _load_eval_module()
    prompts_data = json.loads(PROMPTS_PATH.read_text(encoding="utf-8"))

    stripped_skill = "---\nname: mintchip\ndescription: A CLI tool.\n---\n"
    stripped_snippet = "Use mintchip.\n"
    report = mod.evaluate_prompts(prompts_data, stripped_skill, stripped_snippet)
    assert report["passed"] is False
    assert report["metrics"]["recall"] < 0.90
    assert report["metrics"]["false_trigger_rate"] > 0.0


def test_eval_cli_writes_markdown_report(tmp_path: Path, capsys) -> None:
    mod = _load_eval_module()
    out_report = tmp_path / "REPORT.md"
    rc = mod.main(["--report", str(out_report)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[PASS]" in out
    md = out_report.read_text(encoding="utf-8")
    assert "Mintchip Skill Trigger Evaluation Report" in md
    assert "Recall (TP / Pos)" in md
    assert "False-trigger rate (FP / Neg)" in md
