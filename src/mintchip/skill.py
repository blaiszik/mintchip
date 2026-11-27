"""Bundled agent skill and project instruction installers for mintchip.

Generates ``SKILL.md`` and marker-wrapped ``AGENTS.md`` / ``CLAUDE.md`` snippets directly
from :mod:`mintchip.guide`, so installed skills never drift from the code and work cleanly
from an installed wheel without requiring repository-root ``skills/`` files.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import guide
from .spec import ChipError

__all__ = [
    "GLOBAL_TARGETS",
    "MARKER_END",
    "MARKER_START",
    "VALID_TARGETS",
    "add_skill_parser",
    "cmd_skill",
    "detect_installed_agents",
    "get_agents_snippet",
    "get_skill_markdown",
    "install_skill",
]

VALID_TARGETS: tuple[str, ...] = (
    "claude",
    "antigravity",
    "cursor",
    "codex",
    "agents-md",
    "claude-md",
)

GLOBAL_TARGETS: tuple[str, ...] = (
    "claude",
    "antigravity",
    "cursor",
    "codex",
)

_DEFAULT_LOCAL_TARGETS: tuple[str, ...] = ("claude", "antigravity", "agents-md")
_DEFAULT_GLOBAL_FALLBACK: tuple[str, ...] = ("claude", "antigravity")

_AGENT_HOME_DIRS: tuple[tuple[str, str], ...] = (
    ("claude", ".claude"),
    ("codex", ".codex"),
    ("antigravity", ".gemini"),
    ("cursor", ".cursor"),
)

MARKER_START: str = "<!-- mintchip:start -->"
MARKER_END: str = "<!-- mintchip:end -->"


def detect_installed_agents(home: str | Path | None = None) -> list[str]:
    """Return agent targets whose standard home directory exists under ``home``.

    Checks ``~/.claude`` (``"claude"``), ``~/.codex`` (``"codex"``),
    ``~/.gemini`` (``"antigravity"``), and ``~/.cursor`` (``"cursor"``).
    """
    home_path = Path(home).expanduser() if home is not None else Path.home()
    detected: list[str] = []
    for target, dirname in _AGENT_HOME_DIRS:
        if (home_path / dirname).is_dir():
            detected.append(target)
    return detected


def get_skill_markdown() -> str:
    """Return the generated ``SKILL.md`` directly from :func:`mintchip.guide.skill_text`."""
    return guide.skill_text()


def get_agents_snippet() -> str:
    """Return the marker-wrapped ``AGENTS.md`` / ``CLAUDE.md`` snippet."""
    body = guide.agents_snippet().strip()
    return f"{MARKER_START}\n{body}\n{MARKER_END}\n"


def _strip_yaml_frontmatter(markdown: str) -> str:
    """Remove leading YAML frontmatter block if present."""
    if not markdown.startswith("---\n"):
        return markdown
    end = markdown.find("\n---\n", 4)
    if end == -1:
        return markdown
    return markdown[end + len("\n---\n") :].lstrip("\n")


def _build_cursor_mdc(skill_md: str) -> str:
    """Wrap the skill body with valid Cursor ``.mdc`` rule frontmatter."""
    body = _strip_yaml_frontmatter(skill_md).rstrip() + "\n"
    desc = json.dumps(guide.SKILL_DESCRIPTION, ensure_ascii=False)
    frontmatter = (
        "---\n"
        f"description: {desc}\n"
        "globs:\n"
        '  - "**/*.py"\n'
        '  - "**/*.md"\n'
        '  - "**/*.csv"\n'
        '  - "**/*.json"\n'
        "alwaysApply: false\n"
        "---\n\n"
    )
    return frontmatter + body


def _upsert_marked_block(path: Path, snippet: str) -> Path:
    """Idempotently insert or replace the marker-wrapped snippet inside ``path``."""
    block = snippet.strip()
    if MARKER_START not in block or MARKER_END not in block:
        block = f"{MARKER_START}\n{block}\n{MARKER_END}"

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(block + "\n", encoding="utf-8")
        return path

    existing = path.read_text(encoding="utf-8")
    start_idx = existing.find(MARKER_START)
    end_idx = existing.find(MARKER_END, start_idx + len(MARKER_START)) if start_idx != -1 else -1

    if start_idx != -1 and end_idx != -1:
        updated = existing[:start_idx] + block + existing[end_idx + len(MARKER_END) :]
    elif not existing.strip():
        updated = block + "\n"
    else:
        sep = (
            "\n\n"
            if not existing.endswith("\n")
            else ("\n" if not existing.endswith("\n\n") else "")
        )
        updated = existing + sep + block + "\n"

    path.write_text(updated, encoding="utf-8")
    return path


def _normalize_targets(
    targets: Sequence[str] | None,
    *,
    global_install: bool,
    home_path: Path,
) -> list[str]:
    if targets is None:
        if global_install:
            detected = detect_installed_agents(home_path)
            return detected if detected else list(_DEFAULT_GLOBAL_FALLBACK)
        return list(_DEFAULT_LOCAL_TARGETS)

    expanded: list[str] = []
    for raw in targets:
        for part in raw.split(","):
            key = part.strip().lower()
            if not key:
                continue
            if key == "all":
                expanded.extend(GLOBAL_TARGETS if global_install else VALID_TARGETS)
            else:
                expanded.append(key)

    if not expanded:
        return _normalize_targets(None, global_install=global_install, home_path=home_path)

    normalized: list[str] = []
    seen: set[str] = set()
    for key in expanded:
        if key not in VALID_TARGETS:
            valid = ", ".join((*VALID_TARGETS, "all"))
            raise ChipError(
                f"mintchip skill: unknown install target {key!r}.",
                fix_hint=f"Use --target with one of: {valid}.",
            )
        if key not in seen:
            normalized.append(key)
            seen.add(key)
    return normalized


def install_skill(
    root: str | Path = ".",
    *,
    targets: Sequence[str] | None = None,
    global_install: bool = False,
    home: str | Path | None = None,
) -> list[Path]:
    """Install mintchip agent skills and/or project instruction snippets.

    When ``targets`` is omitted:
    - Project-local installs default to ``("claude", "antigravity", "agents-md")``.
    - Global installs auto-detect ``~/.claude``, ``~/.codex``, ``~/.gemini``,
      and ``~/.cursor``, falling back to ``("claude", "antigravity")``.
    """
    home_path = Path(home).expanduser() if home is not None else Path.home()
    normalized = _normalize_targets(targets, global_install=global_install, home_path=home_path)

    root_path = Path(root)
    skill_md = get_skill_markdown()
    snippet = get_agents_snippet()
    written: list[Path] = []

    def _write_skill_file(dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(skill_md, encoding="utf-8")
        return dest

    for target in normalized:
        if target == "claude":
            base = home_path if global_install else root_path
            written.append(_write_skill_file(base / ".claude" / "skills" / "mintchip" / "SKILL.md"))
        elif target == "antigravity":
            if global_install:
                dest = home_path / ".gemini" / "config" / "skills" / "mintchip" / "SKILL.md"
            else:
                dest = root_path / ".agents" / "skills" / "mintchip" / "SKILL.md"
            written.append(_write_skill_file(dest))
        elif target == "cursor":
            base = home_path if global_install else root_path
            dest = base / ".cursor" / "rules" / "mintchip.mdc"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(_build_cursor_mdc(skill_md), encoding="utf-8")
            written.append(dest)
        elif target == "codex":
            base = home_path if global_install else root_path
            written.append(_write_skill_file(base / ".codex" / "skills" / "mintchip" / "SKILL.md"))
        elif target == "agents-md":
            dest = (
                (home_path / ".codex" / "AGENTS.md")
                if global_install
                else (root_path / "AGENTS.md")
            )
            written.append(_upsert_marked_block(dest, snippet))
        elif target == "claude-md":
            dest = (
                (home_path / ".claude" / "CLAUDE.md")
                if global_install
                else (root_path / "CLAUDE.md")
            )
            written.append(_upsert_marked_block(dest, snippet))

    return written


def add_skill_parser(sub: Any, formatter_class: Any) -> argparse.ArgumentParser:
    """Register the ``mintchip skill`` subcommand."""
    p = sub.add_parser(
        "skill",
        help="Print or install the mintchip agent skill for Claude, Antigravity, Cursor, or Codex.",
        description=(
            "Print the generated SKILL.md (default / --print) or install it into local project\n"
            "or user-home agent directories (--install). Upserts AGENTS.md / CLAUDE.md blocks\n"
            "idempotently between <!-- mintchip:start --> and <!-- mintchip:end -->."
        ),
        formatter_class=formatter_class,
    )
    p.add_argument(
        "--install",
        action="store_true",
        help="Install skill files and/or AGENTS.md/CLAUDE.md snippets.",
    )
    p.add_argument(
        "--print",
        dest="print_skill",
        action="store_true",
        help="Print the generated SKILL.md to stdout (default when --install is not given).",
    )
    p.add_argument(
        "--snippet",
        action="store_true",
        help="Print the marker-wrapped AGENTS.md / CLAUDE.md snippet.",
    )
    p.add_argument(
        "--global",
        dest="global_install",
        action="store_true",
        help="Install into user-home agent directories (~/.claude, ~/.codex, ~/.gemini, ~/.cursor).",
    )
    p.add_argument(
        "--root",
        default=".",
        metavar="DIR",
        help="Target project root directory for local installs (default: .).",
    )
    p.add_argument(
        "--home",
        default=None,
        metavar="DIR",
        help="Override home directory for --global installs.",
    )
    p.add_argument(
        "--target",
        action="append",
        default=None,
        metavar="TARGET",
        help=(
            "Install target (repeatable or comma-separated): "
            "claude, antigravity, cursor, codex, agents-md, claude-md, or all."
        ),
    )
    p.set_defaults(func=cmd_skill, _parser=p)
    return p


def cmd_skill(args: argparse.Namespace) -> int:
    """Execute ``mintchip skill``."""
    from .cli import _error, _out

    if args.snippet:
        _out(get_agents_snippet())
        return 0
    if args.install:
        try:
            written = install_skill(
                root=args.root,
                targets=args.target,
                global_install=args.global_install,
                home=args.home,
            )
        except ChipError as e:
            return _error(e)
        for path in written:
            _out(f"Installed: {path}")
        return 0
    _out(get_skill_markdown())
    return 0
