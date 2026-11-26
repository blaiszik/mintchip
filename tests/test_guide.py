from __future__ import annotations

from pathlib import Path

import mintchip as mc
from mintchip import guide
from mintchip.cli import run

ROOT = Path(__file__).resolve().parent.parent


def test_guide_is_short_and_covers_every_kind() -> None:
    text = guide.guide_text()
    assert len(text) < guide.LIMIT, len(text)
    for entry in mc.CATALOG:
        k = mc.REGISTRY[entry["name"]]
        assert entry["have"] in text and k.example_chip().text() in text
    for rule in ("two is the ceiling", "make a table", "just a number"):
        assert rule in text
    for command in ("$ mintchip ci ", "$ mintchip render - <<'EOF'", "$ mintchip table - "):
        assert command in text
    assert run(["guide"]) == (0, text, "")


def test_guide_examples_show_real_output() -> None:
    text = guide.guide_text()
    sentence = mc.format_prose(
        "Val loss settled at {s}, and retrieval lifted accuracy by {c}.",
        compact=False,
        s=mc.REGISTRY["spark"].example_chip(),
        c=mc.ci(0.08, (0.05, 0.11), level=0.95),
    )
    assert "\n" + sentence + "\n" in text


def test_agents_snippet() -> None:
    code, out, _ = run(["guide", "--agents"])
    assert code == 0 and out == guide.agents_snippet()
    assert len(out) < 900 and "mintchip render" in out and "mintchip table" in out


def test_committed_files_match_the_generator(tmp_path) -> None:
    code, out, _ = run(["guide", "--write", str(tmp_path)])
    assert code == 0 and out.count("\n") == 2
    for rel in ("skills/mintchip/SKILL.md", "llms.txt"):
        committed = ROOT / rel
        assert committed.is_file(), f"run: mintchip guide --write . ({rel} is missing)"
        assert committed.read_text(encoding="utf-8") == (tmp_path / rel).read_text(
            encoding="utf-8"
        ), f"{rel} is stale; run: mintchip guide --write ."
    skill = (tmp_path / "skills/mintchip/SKILL.md").read_text(encoding="utf-8")
    head = skill.split("---")[1]
    assert "\nname: mintchip\n" in head and "benchmarks" in head and "test runs" in head
    assert not (ROOT / "AGENTS.md").exists()
