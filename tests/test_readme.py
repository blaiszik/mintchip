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
RAW_PREFIX = "https://raw.githubusercontent.com/blaiszik/mintchip/main/"
BLOB_PREFIX = "https://github.com/blaiszik/mintchip/blob/main/"


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
    """Every README image uses an absolute GitHub raw URL backed by a committed file,
    with static light fallbacks so PyPI never renders dark-on-dark/white-on-white SVGs."""
    text = README.read_text(encoding="utf-8")
    md_images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    img_srcs = re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', text)
    source_srcs = re.findall(r'<source\b[^>]*\bsrcset="([^"]+)"', text)
    images = md_images + img_srcs + source_srcs
    assert images, "the README shows images"
    for src in images:
        assert not src.startswith("data:"), src
        assert src.startswith(RAW_PREFIX), (
            f"README image must use absolute GitHub raw URL for PyPI rendering: {src}"
        )
        rel = src.removeprefix(RAW_PREFIX)
        local = ROOT / rel
        assert local.is_file(), f"{rel} is missing; {FIX}"
    for src in img_srcs:
        if src.endswith(".svg"):
            rel = src.removeprefix(RAW_PREFIX)
            assert rel.endswith("_light.svg"), (
                f"fallback <img> must be a static light SVG for PyPI white background: {rel}"
            )
            svg_text = (ROOT / rel).read_text(encoding="utf-8")
            assert "prefers-color-scheme:dark" not in svg_text, (
                f"static light SVG {rel} must not switch ink on OS dark mode"
            )
    assert "<svg" not in text and "data:image" not in text


def test_readme_repo_links_are_absolute_and_exist() -> None:
    """PyPI cannot resolve relative repo links; every repo link must be an absolute blob URL."""
    text = README.read_text(encoding="utf-8")
    # Strip fenced code blocks so shell/python examples aren't scanned as markdown links.
    no_code = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    links = re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", no_code)
    assert links, "the README links to repo docs"
    for href in links:
        assert href.startswith(("https://", "http://", "#")), (
            f"README link must be absolute for PyPI: {href}"
        )
        if href.startswith(BLOB_PREFIX):
            rel = href.removeprefix(BLOB_PREFIX).split("#", 1)[0]
            assert (ROOT / rel).exists(), f"linked repo path {rel!r} does not exist"


def test_catalog_covers_every_chip() -> None:
    text = README.read_text(encoding="utf-8")
    for entry in mc.CATALOG:
        assert f"| {entry['have']} | [`{entry['name']}`]" in text, entry["name"]


def test_no_v01_leftovers() -> None:
    text = README.read_text(encoding="utf-8").lower()
    for gone in ("pill", "palette", "17 chips", "evidence", "scatter", "dual_spark"):
        assert gone not in text, gone
