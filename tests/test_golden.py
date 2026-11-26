"""Golden text for every registered kind's example.

Regenerate after an intended change with ``MINTCHIP_UPDATE_GOLDEN=1 pytest tests/test_golden.py``
and review the diff. A kind with no golden file fails.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import mintchip as mc

GOLDEN = Path(__file__).parent / "golden"
UPDATE = os.environ.get("MINTCHIP_UPDATE_GOLDEN") == "1"


def rendered(kind: str) -> str:
    c = mc.REGISTRY[kind].example_chip()
    return f"text: {c.text()}\nascii: {c.text(ascii=True)}\ncompact: {c.text(compact=True)}\n"


@pytest.mark.parametrize("kind", sorted(mc.REGISTRY))
def test_golden_text(kind: str) -> None:
    path = GOLDEN / f"{kind}.txt"
    got = rendered(kind)
    if UPDATE:
        path.parent.mkdir(exist_ok=True)
        path.write_text(got, encoding="utf-8")
        return
    if not path.exists():
        pytest.fail(f"no golden file {path}; run MINTCHIP_UPDATE_GOLDEN=1 pytest {__file__}")
    assert got == path.read_text(encoding="utf-8")
