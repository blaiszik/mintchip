"""Verify mintchip stays strictly zero-dependency and CLI runs cleanly."""

from __future__ import annotations

import subprocess
import sys

from mintchip.cli import main as cli_main


def test_import_and_all_17_chips_zero_external_deps() -> None:
    """Running all 17 chips in a fresh interpreter must never import matplotlib/numpy/PIL."""
    code = """
import sys
import mintchip as mc
from mintchip.cli import _demo_chips

chips = _demo_chips(style="dark", palette="okabe_ito")
assert len(chips) == 17
for name, chip in chips.items():
    assert chip.svg.startswith("<svg "), name
    assert len(chip.to_text()) > 0, name
    assert len(chip.to_text(ascii_only=True)) > 0, name
    assert len(chip.html()) > 0, name
    assert len(chip.facts) >= 1, name

forbidden = {"matplotlib", "numpy", "PIL", "pypdf", "mintfig"}
loaded = forbidden & set(sys.modules)
assert not loaded, f"Unexpected external modules imported: {sorted(loaded)}"
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"


def test_cli_catalog_and_demo(capsys, tmp_path) -> None:
    rc = cli_main(["catalog"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "mintchip" in out
    assert "scatter" in out

    rc_json = cli_main(["catalog", "--json"])
    assert rc_json == 0
    assert '"dual_spark"' in capsys.readouterr().out

    rc_demo = cli_main(["demo", "--ascii"])
    assert rc_demo == 0
    assert "Across 5 seeds" in capsys.readouterr().out

    html_out = tmp_path / "demo.html"
    rc_html = cli_main(["demo", "--html", str(html_out), "--style", "paper"])
    assert rc_html == 0
    assert html_out.exists()
    assert "<svg" in html_out.read_text(encoding="utf-8")
