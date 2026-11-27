"""Terminal & environment diagnostics for ``mintchip doctor``.

Reports Python version, mintchip version, stdout encoding/TTY/ANSI color support, and
renders compact Unicode, ANSI, and ASCII probe lines across key chips so users and agents
can verify glyph legibility in their terminal or editor.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from typing import Any

import mintchip as mc

__all__ = ["PROBE_KINDS", "add_doctor_parser", "cmd_doctor", "doctor_report", "format_doctor"]

PROBE_KINDS: tuple[str, ...] = ("spark", "ci", "dist", "bar", "strip")


def _probe_chips() -> list[tuple[str, mc.Chip]]:
    return [
        ("spark", mc.spark([1.84, 1.32, 0.96, 0.62, 0.42], band=(0.38, 0.48))),
        ("ci", mc.ci(0.08, (0.05, 0.11), level=0.95)),
        (
            "dist",
            mc.dist(
                [18.9, 19.4, 19.8, 20.1, 20.3, 20.9, 21.6, 22.8, 47.8],
                threshold=21.0,
                unit="ms",
            ),
        ),
        ("bar", mc.bar(0.82, target=0.9)),
        ("strip", mc.strip([True, True, True, "warn", True, False, True, None])),
    ]


def _ansi_color_status(isatty: bool) -> tuple[bool, str]:
    """Determine ANSI color readiness from standard env vars and TTY state."""
    if os.environ.get("NO_COLOR", "") != "":
        return False, "disabled (NO_COLOR is set)"
    if os.environ.get("FORCE_COLOR", "") not in ("", "0"):
        return True, "enabled (FORCE_COLOR is set)"
    term = os.environ.get("TERM", "")
    if term.lower() == "dumb":
        return False, "disabled (TERM=dumb)"
    if isatty:
        return True, f"enabled (TTY, TERM={term or 'unset'})"
    return False, "inactive (stdout is not a TTY; pass --format ansi to force)"


def doctor_report() -> dict[str, Any]:
    """Collect environment details and Unicode/ANSI/ASCII chip probe lines."""
    encoding = getattr(sys.stdout, "encoding", None) or "unknown"
    isatty_fn = getattr(sys.stdout, "isatty", None)
    isatty = bool(isatty_fn()) if callable(isatty_fn) else False
    unicode_ok = encoding.lower().replace("_", "-").startswith("utf")
    ansi_ok, ansi_reason = _ansi_color_status(isatty)

    probes: list[dict[str, str]] = []
    for kind, chip in _probe_chips():
        probes.append(
            {
                "kind": kind,
                "unicode": chip.text(ascii=False, compact=True, color=False),
                "ansi": chip.text(ascii=False, compact=True, color=True),
                "ascii": chip.text(ascii=True, compact=True, color=False),
            }
        )

    return {
        "mintchip": mc.__version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "stdout": {
            "encoding": encoding,
            "isatty": isatty,
            "unicode": unicode_ok,
            "ansi_color": ansi_ok,
            "ansi_reason": ansi_reason,
            "term": os.environ.get("TERM", ""),
            "no_color": os.environ.get("NO_COLOR", "") != "",
        },
        "probes": probes,
    }


def format_doctor(report: dict[str, Any], *, ascii: bool = False) -> str:
    """Format a :func:`doctor_report` dictionary for human/agent terminal display."""
    out = report["stdout"]
    rule = "-" * 64 if ascii else "─" * 64
    lines = [
        f"mintchip doctor (mintchip {report['mintchip']})",
        rule,
        f"  Python          : {report['python']}",
        f"  mintchip        : {report['mintchip']}",
        f"  stdout encoding : {out['encoding']} ({'UTF ok' if out['unicode'] else 'non-UTF; use --ascii'})",
        f"  stdout TTY      : {'yes' if out['isatty'] else 'no'}",
        f"  ANSI color      : {out['ansi_reason']}",
        "",
        "Glyph probes (verify sparkline blocks, whiskers, histogram, bars, and strip cells):",
    ]
    kind_w = max(len(p["kind"]) for p in report["probes"])
    for probe in report["probes"]:
        k = f"{probe['kind']:<{kind_w}}"
        if ascii:
            lines.append(f"  {k}  ascii  {probe['ascii']}")
        else:
            lines.append(f"  {k}  uni    {probe['unicode']}")
            lines.append(f"  {' ' * kind_w}  ansi   {probe['ansi']}")
            lines.append(f"  {' ' * kind_w}  ascii  {probe['ascii']}")
    return "\n".join(lines)


def add_doctor_parser(sub: Any, formatter_class: Any) -> argparse.ArgumentParser:
    """Register the ``mintchip doctor`` subcommand."""
    p = sub.add_parser(
        "doctor",
        help="Check Python/TTY/UTF-8/ANSI readiness and print chip glyph probes.",
        description=(
            "Report Python version, mintchip version, stdout encoding, TTY and ANSI color status,\n"
            "and render compact Unicode, ANSI, and ASCII probe lines across spark, ci, dist, bar,\n"
            "and strip so you can verify glyph legibility in your terminal or editor."
        ),
        formatter_class=formatter_class,
    )
    p.add_argument("--json", dest="as_json", action="store_true", help="Print report as JSON.")
    p.add_argument("--ascii", action="store_true", help="ASCII-only probe output.")
    p.set_defaults(func=cmd_doctor, _parser=p)
    return p


def cmd_doctor(args: argparse.Namespace) -> int:
    """Execute ``mintchip doctor``."""
    from .cli import _out

    report = doctor_report()
    if args.as_json:
        _out(json.dumps(report, indent=2, ensure_ascii=args.ascii))
    else:
        _out(format_doctor(report, ascii=args.ascii))
    return 0
