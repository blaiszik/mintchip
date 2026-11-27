"""Tests for ``mintchip.skill`` and the ``mintchip skill`` CLI subcommand."""

from __future__ import annotations

from pathlib import Path

import pytest

from mintchip import guide, skill
from mintchip.cli import run
from mintchip.spec import ChipError


def test_skill_markdown_matches_guide_with_zero_drift() -> None:
    md = skill.get_skill_markdown()
    assert md == guide.skill_text()
    assert md.startswith("---\nname: mintchip\n")
    assert "Do NOT use" in md
    assert "mintfig" in md


def test_cli_skill_print_default_and_explicit() -> None:
    code1, out1, err1 = run(["skill"])
    code2, out2, err2 = run(["skill", "--print"])
    assert (code1, err1) == (0, "")
    assert (code2, err2) == (0, "")
    assert out1 == out2 == guide.skill_text()


def test_cli_skill_snippet() -> None:
    code, out, err = run(["skill", "--snippet"])
    assert (code, err) == (0, "")
    assert out.startswith(skill.MARKER_START)
    assert skill.MARKER_END in out
    assert "mintchip render" in out


def test_local_install_defaults_and_all_targets(tmp_path: Path) -> None:
    written = skill.install_skill(root=tmp_path)
    expected = [
        tmp_path / ".claude" / "skills" / "mintchip" / "SKILL.md",
        tmp_path / ".agents" / "skills" / "mintchip" / "SKILL.md",
        tmp_path / "AGENTS.md",
    ]
    assert written == expected
    for p in expected:
        assert p.is_file()
    assert expected[0].read_text(encoding="utf-8") == guide.skill_text()
    assert skill.MARKER_START in expected[2].read_text(encoding="utf-8")

    # Install all targets including cursor, codex, claude-md
    all_written = skill.install_skill(root=tmp_path, targets=["all"])
    assert len(all_written) == len(skill.VALID_TARGETS)
    cursor_mdc = tmp_path / ".cursor" / "rules" / "mintchip.mdc"
    assert cursor_mdc.is_file()
    mdc_text = cursor_mdc.read_text(encoding="utf-8")
    assert mdc_text.startswith("---\ndescription:")
    assert "alwaysApply: false" in mdc_text
    assert (tmp_path / ".codex" / "skills" / "mintchip" / "SKILL.md").is_file()
    assert (tmp_path / "CLAUDE.md").is_file()


def test_upsert_marked_block_is_idempotent_and_preserves_user_text(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# My Repo\n\nExisting user rules.\n", encoding="utf-8")

    skill.install_skill(root=tmp_path, targets=["agents-md"])
    first = agents.read_text(encoding="utf-8")
    assert "# My Repo" in first
    assert "Existing user rules." in first
    assert first.count(skill.MARKER_START) == 1
    assert first.count(skill.MARKER_END) == 1

    # Second run updates in place without duplicating
    skill.install_skill(root=tmp_path, targets=["agents-md"])
    second = agents.read_text(encoding="utf-8")
    assert second == first

    # Works identically for CLAUDE.md
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("Custom header\n<!-- mintchip:start -->\nold\n<!-- mintchip:end -->\nFooter\n", encoding="utf-8")
    skill.install_skill(root=tmp_path, targets=["claude-md"])
    updated = claude_md.read_text(encoding="utf-8")
    assert updated.startswith("Custom header\n")
    assert updated.endswith("\nFooter\n")
    assert "old\n" not in updated
    assert "mintchip render" in updated


def test_global_install_auto_detects_agent_homes(tmp_path: Path) -> None:
    # Empty home falls back to claude + antigravity
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()
    assert skill.detect_installed_agents(empty_home) == []
    fallback_paths = skill.install_skill(global_install=True, home=empty_home)
    assert fallback_paths == [
        empty_home / ".claude" / "skills" / "mintchip" / "SKILL.md",
        empty_home / ".gemini" / "config" / "skills" / "mintchip" / "SKILL.md",
    ]

    # Home with .codex and .cursor auto-detects exactly those
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    (home / ".cursor").mkdir(parents=True)
    assert skill.detect_installed_agents(home) == ["codex", "cursor"]
    detected_paths = skill.install_skill(global_install=True, home=home)
    assert detected_paths == [
        home / ".codex" / "skills" / "mintchip" / "SKILL.md",
        home / ".cursor" / "rules" / "mintchip.mdc",
    ]


def test_cli_skill_install_and_bad_target(tmp_path: Path) -> None:
    code, out, err = run(
        ["skill", "--install", "--root", str(tmp_path), "--target", "claude,claude-md"]
    )
    assert (code, err) == (0, "")
    assert "Installed:" in out
    assert (tmp_path / ".claude" / "skills" / "mintchip" / "SKILL.md").is_file()
    assert (tmp_path / "CLAUDE.md").is_file()

    code, out, err = run(["skill", "--install", "--root", str(tmp_path), "--target", "vim"])
    assert (code, out) == (2, "")
    assert "unknown install target" in err

    with pytest.raises(ChipError):
        skill.install_skill(root=tmp_path, targets=["unknown-agent"])
