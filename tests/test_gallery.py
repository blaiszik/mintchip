"""gallery/ is generated: every committed file must match gallery/build_gallery.py, with no
stale files left over, and every registered chip must be documented."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest
from test_readme import FIX, ROOT, diff, gallery

import mintchip as mc

GALLERY_README = ROOT / "gallery" / "README.md"


@pytest.fixture(scope="module")
def outputs() -> dict:
    return gallery().outputs()


def test_gallery_readme_matches_the_generator() -> None:
    text = GALLERY_README.read_text(encoding="utf-8")
    expected = gallery().documents()[GALLERY_README]
    assert text == expected, f"gallery/README.md is stale; {FIX}:\n{diff(text, expected)}"


def test_output_files_match_the_generator(outputs: dict) -> None:
    stale = [
        p for p, content in outputs.items() if not p.exists() or p.read_text("utf-8") != content
    ]
    assert not stale, f"{len(stale)} stale file(s), e.g. {stale[0].relative_to(ROOT)}; {FIX}"
    left = gallery().stale(outputs)
    assert not left, f"files the build no longer makes: {left[:3]}; {FIX}"


def test_every_chip_is_documented(outputs: dict) -> None:
    text = GALLERY_README.read_text(encoding="utf-8")
    index = (ROOT / "gallery/output/index.html").read_text(encoding="utf-8")
    baseline = (ROOT / "gallery/output/baseline.html").read_text(encoding="utf-8")
    for entry in mc.CATALOG:
        kind = entry["name"]
        assert f'<a id="{kind}"></a>' in text and f"output/cards/{kind}.svg" in text, kind
        assert f'id="{kind}"' in index and f">{kind}</div>" in baseline, kind


def test_markdown_images_are_committed_files() -> None:
    text = GALLERY_README.read_text(encoding="utf-8")
    for src in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
        assert not src.startswith(("data:", "http")), src
        assert (GALLERY_README.parent / src).is_file(), src


def test_standalone_chips_adapt_to_light_and_dark(outputs: dict) -> None:
    svgs = [p for p in outputs if p.suffix == ".svg"]
    assert svgs and not [p for p in svgs if p.stem.endswith("_dark")], "one file serves both modes"
    for path in svgs:
        content = outputs[path]
        assert "prefers-color-scheme:dark" in content, path.name
        ET.fromstring(content)  # well-formed, so GitHub's image proxy will serve it


def test_composed_images_show_chips_at_their_real_size(outputs: dict) -> None:
    g = gallery()
    for path, content in outputs.items():
        if path.parent.name not in ("pairs", "cards"):
            continue
        root = ET.fromstring(content)
        assert root.get("font-size") == f"{g.FS:g}"
        nested = [el for el in root.iter() if el.tag.endswith("svg") and el is not root]
        for el in nested:
            w = float(el.get("viewBox").split()[2])
            assert float(el.get("height")) == g.FS, path.name
            assert abs(float(el.get("width")) - w / 16 * g.FS) < 0.01, path.name


def test_index_is_a_mintchip_document(outputs: dict) -> None:
    page = outputs[ROOT / "gallery/output/index.html"]
    assert mc.css() in page and 'class="mc-doc"' in page and "<script" not in page
    ids = re.findall(r' id="(mc-[0-9a-f]{8}-\d+)"', page)
    assert ids and len(ids) == len(set(ids)), "popover ids are unique"
