"""README.md shows only real output: its generated blocks must match gallery/build_gallery.py.

After an intended change in what mintchip prints, run ``python gallery/build_gallery.py`` and
review the diff.
"""

from __future__ import annotations

import difflib
import importlib.util
import re
from functools import cache
from pathlib import Path

import mintchip as mc

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
FIX = "run `python gallery/build_gallery.py` and review the diff"


@cache
def gallery():
    spec = importlib.util.spec_from_file_location(
        "build_gallery", ROOT / "gallery/build_gallery.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def diff(old: str, new: str) -> str:
    lines = difflib.unified_diff(old.splitlines(), new.splitlines(), "committed", "now", n=1)
    return "\n".join(list(lines)[:40])


def test_readme_matches_the_generator() -> None:
    text = README.read_text(encoding="utf-8")
    expected = gallery().documents()[README]
    assert text == expected, f"README.md is stale; {FIX}:\n{diff(text, expected)}"


def test_readme_opens_with_the_before_and_after() -> None:
    text = README.read_text(encoding="utf-8")
    hero = text.index("<!-- BEGIN mintchip:hero -->")
    assert text.index("## ") > hero, "the before/after comes before any section"
    assert "**Before**" in text[hero:] and "**After**" in text[hero:]


def test_readme_images_are_committed_files() -> None:
    """GitHub strips inline SVG and data: URIs, so every image is a relative file path."""
    text = README.read_text(encoding="utf-8")
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert images, "the README shows images"
    for src in images:
        assert not src.startswith(("data:", "http")), src
        assert (ROOT / src).is_file(), f"{src} is missing; {FIX}"
    assert "<svg" not in text and "data:image" not in text


def test_catalog_covers_every_chip() -> None:
    text = README.read_text(encoding="utf-8")
    for entry in mc.CATALOG:
        assert f"| {entry['have']} | [`{entry['name']}`]" in text, entry["name"]


def test_no_v01_leftovers() -> None:
    text = README.read_text(encoding="utf-8").lower()
    for gone in ("mintfig", "pill", "palette", "17 chips", "evidence", "scatter", "dual_spark"):
        assert gone not in text, gone
