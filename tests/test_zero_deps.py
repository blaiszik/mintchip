"""mintchip stays standard-library only, and the catalog CLI runs."""

from __future__ import annotations

import json
import subprocess
import sys

from mintchip.cli import main as cli_main


def test_every_example_renders_without_external_modules() -> None:
    code = """
import sys
import mintchip as mc

for kind in mc.REGISTRY.values():
    chip = kind.example_chip()
    assert chip.text() and chip.text(ascii=True).isascii() and chip.html()
    assert chip.svg() == "" or chip.svg().startswith("<svg "), kind.name
loaded = {"matplotlib", "numpy", "pandas", "PIL", "mintfig"} & set(sys.modules)
assert not loaded, sorted(loaded)
"""
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_cli_catalog(capsys) -> None:
    import mintchip as mc

    assert cli_main(["catalog"]) == 0
    out = capsys.readouterr().out
    assert all(e["name"] in out for e in mc.CATALOG)

    assert cli_main(["catalog", "--ascii"]) == 0
    assert capsys.readouterr().out.isascii()

    assert cli_main(["catalog", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["name"] for r in rows] == [e["name"] for e in mc.CATALOG]
    assert all(mc.from_dict(r["spec"]).text() == r["text"] for r in rows)
