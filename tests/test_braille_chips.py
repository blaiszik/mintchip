"""Tests for optional high-res 2×4 inline Braille rendering and 24-bit ANSI true-color heat."""

from __future__ import annotations

import json
import re

import pytest

import mintchip as mc
from mintchip.cli import run
from mintchip.render.text_base import (
    BRAILLE_BASE,
    ansi_theme,
    braille_cell,
    braille_level_mask,
    braille_mode,
    braille_row,
    is_braille_mode,
)
from mintchip.themes import THEMES

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
RGB_RE = re.compile(r"\x1b\[38;2;(\d+);(\d+);(\d+)m")


def _is_braille(ch: str) -> bool:
    return BRAILLE_BASE <= ord(ch) <= 0x28FF


def _has_braille(s: str) -> bool:
    return any(_is_braille(ch) for ch in s)


def _rgb_seq(hex_colour: str) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"\x1b[38;2;{r};{g};{b}m"


class TestBrailleHelpersAndDefaults:
    def test_braille_primitives(self) -> None:
        assert braille_cell(0) == "\u2800"
        assert braille_cell(0xFF) == "\u28ff"
        assert braille_row(10.0, 0.0, 10.0) == 0
        assert braille_row(0.0, 0.0, 10.0) == 3
        assert braille_cell(braille_level_mask(0, 4)) == "⡇"
        assert braille_cell(braille_level_mask(1, 4)) == "⢸"
        assert braille_cell(braille_level_mask(0, 1) | braille_level_mask(1, 1)) == "⣀"

    def test_braille_mode_context_manager_restores_state(self) -> None:
        assert not is_braille_mode()
        c = mc.spark([1.84, 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43, 0.42])
        with braille_mode(True):
            assert is_braille_mode()
            assert c.text() == c.text(braille=True)
            assert _has_braille(c.text(value=False))
        assert not is_braille_mode()
        assert not _has_braille(c.text(value=False))

    @pytest.mark.parametrize("kind", sorted(mc.REGISTRY))
    def test_default_braille_false_and_ansi_strip_invariant(self, kind: str) -> None:
        c = mc.REGISTRY[kind].example_chip()
        assert c.text(braille=False) == c.text()
        assert not _has_braille(c.text())
        assert ANSI_RE.sub("", c.text(braille=True, color=True)) == c.text(braille=True)
        with ansi_theme("mint_dark"):
            assert ANSI_RE.sub("", c.text(braille=True, color=True)) == c.text(braille=True)
        # ascii=True cleanly overrides braille=True for every registered kind
        assert c.text(braille=True, ascii=True) == c.text(ascii=True)
        assert c.text(braille=True, ascii=True).isascii()


class TestSparkBraille:
    def test_spark_braille_packs_two_samples_per_cell(self) -> None:
        vals = [1.84, 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43, 0.42]
        c = mc.spark(vals)
        plain_glyph = c.text(value=False)
        braille_glyph = c.text(value=False, braille=True)
        assert len(plain_glyph) == 9
        assert len(braille_glyph) == 5  # ceil(9 / 2) = 5 Braille cells
        assert all(_is_braille(ch) for ch in braille_glyph)
        assert c.text(compact=True, braille=True) == f"0.42 {braille_glyph}"

    def test_spark_braille_24_points_no_downsampling_and_over_24_marks_n(self) -> None:
        pts24 = [float(i % 6) for i in range(24)]
        c24 = mc.spark(pts24)
        assert "n=24" in c24.text(value=False)
        g24 = c24.text(value=False, braille=True)
        assert "n=24" not in g24
        assert len(g24) == 12
        assert all(_is_braille(ch) for ch in g24)

        pts30 = [float(i % 6) for i in range(30)]
        c30 = mc.spark(pts30)
        assert "n=30" in c30.text(value=False, braille=True)

    def test_spark_braille_vs_band_reference_gaps_and_clipping(self) -> None:
        a = [1.8, 1.4, 1.0, 0.7, 0.5, 0.4]
        b = [1.7, 1.5, 1.3, 1.1, 0.9, 0.8]
        dual = mc.spark(a, vs=b)
        dg = dual.text(value=False, braille=True)
        parts = dg.split(" ")
        assert len(parts) == 2
        assert all(len(p) == 3 and all(_is_braille(ch) for ch in p) for p in parts)

        banded = mc.spark(a, band=(0.35, 0.55))
        bg = banded.text(value=False, braille=True)
        assert "│" in bg and _has_braille(bg)

        reffed = mc.spark(a, reference=1.0)
        rg = reffed.text(value=False, braille=True)
        assert "│" in rg and _has_braille(rg)

        both = mc.spark(a, band=(0.35, 0.55), reference=1.2)
        assert "│" in both.text(value=False, braille=True)

        gapped = mc.spark([1.0, 2.0, None, None, 3.0, 4.0])
        assert "·" in gapped.text(value=False, braille=True)

        clipped = mc.spark([1.0, 5.0, 2.0, -3.0], domain=(0.0, 3.0))
        cg = clipped.text(value=False, braille=True)
        assert "^" in cg and "v" in cg


class TestHistBraille:
    def test_hist_braille_packs_two_bins_per_cell_with_reference_and_clipping(self) -> None:
        samples = [18, 19, 20, 20, 21, 22, 26, 31]
        c = mc.hist(samples, bins=8, unit="ms")
        g_plain = c.text(value=False)
        g_braille = c.text(value=False, braille=True)
        assert len(g_plain) == 8
        assert len(g_braille) == 4  # 8 bins -> 4 Braille cells
        assert _has_braille(g_braille)

        # Reference marker in non-empty and empty bins
        c_ref = mc.hist(samples, bins=8, reference=25, unit="ms")
        assert "│" in c_ref.text(value=False, braille=True)
        c_ref_empty = mc.hist([10, 10, 11, 30, 30], bins=6, reference=20)
        assert "│" in c_ref_empty.text(value=False, braille=True)

        # Modal bin highlighted with accent in ANSI
        with ansi_theme("mint_dark"):
            colored = c.text(color=True, braille=True)
            assert _rgb_seq(THEMES["mint_dark"].accent) in colored

        # Domain clipping markers preserved
        clipped = c.text(value=False, braille=True, domain=(19.0, 28.0))
        assert clipped.startswith("<") and clipped.endswith(">")

        # 16 bins pack into 8 cells
        c16 = mc.hist([float(i) for i in range(32)], bins=16)
        assert len(c16.text(value=False, braille=True)) == 8


class TestBulletBraille:
    def test_bullet_braille_bands_bar_target_and_overflow(self) -> None:
        c = mc.bullet(0.82, 0.9, ranges=(0.6, 0.85, 1.0), label="SLA")
        g = c.text(value=False, braille=True)
        assert len(g) == 8
        assert all(_is_braille(ch) for ch in g)
        # Middle-row bar cells (⠶) and full-height target tick (⡇ / ⢸)
        assert "⠶" in g
        assert any(ch in ("⡇", "⢸", "⡷", "⢾", "⣇", "⣸") for ch in g)

        # Low value reveals distinct low/mid qualitative bottom-row band dots (⣀ / ⡀)
        low = mc.bullet(0.35, 0.9, ranges=(0.6, 0.85, 1.0))
        lg = low.text(value=False, braille=True)
        assert "⣀" in lg and "⡀" in lg

        # Exceeding target still keeps the full-height target tick visible through the bar (⡷ / ⢾)
        met = mc.bullet(0.95, 0.75, ranges=(0.6, 0.85, 1.0))
        mg = met.text(value=False, braille=True)
        assert any(ch in ("⡷", "⢾") for ch in mg)

        # Overflow appends +
        over = mc.bullet(1.15, 0.9)
        og = over.text(value=False, braille=True)
        assert og.endswith("+")
        assert all(_is_braille(ch) for ch in og[:-1])

        # ANSI mint_dark uses accent for bar
        with ansi_theme("mint_dark"):
            colored = c.text(color=True, braille=True)
            assert _rgb_seq(THEMES["mint_dark"].accent) in colored


class TestHeatBrailleAndTrueColor:
    def test_heat_plain_text_and_classic_ansi_unchanged(self) -> None:
        vals = [12, 24, 68, 95, 78, 30, 15]
        c = mc.heat(vals, unit="ms")
        assert c.text() == "12 to 95 ms ░░▓█▓▒░"
        classic = c.text(color=True)
        assert "\x1b[2m" in classic and "\x1b[34m" in classic
        assert "38;2;" not in classic
        assert ANSI_RE.sub("", classic) == c.text()

    @pytest.mark.parametrize("theme_name", ["mint", "mint_dark"])
    def test_heat_graduated_24bit_ansi_along_theme_accent_ramp(self, theme_name: str) -> None:
        th = THEMES[theme_name]
        c = mc.heat([12, 24, 68, 95, 78, 30, 15], unit="ms")
        with ansi_theme(theme_name):
            shaded = c.text(color=True)
            brailled = c.text(color=True, braille=True)

        # Plain shade cells keep exact glyph text while receiving graduated 24-bit RGB codes
        assert ANSI_RE.sub("", shaded) == c.text()
        rgb_shaded = set(RGB_RE.findall(shaded))
        assert len(rgb_shaded) >= 4
        assert _rgb_seq(th.accent) in shaded

        # Braille heat packs 2 slots per cell and emits graduated 24-bit RGB codes
        assert ANSI_RE.sub("", brailled) == c.text(braille=True)
        assert _has_braille(c.text(value=False, braille=True))
        assert len(c.text(value=False, braille=True)) == 4  # ceil(7 / 2)
        rgb_brailled = set(RGB_RE.findall(brailled))
        assert len(rgb_brailled) >= 3
        assert _rgb_seq(th.accent) in brailled

    def test_heat_braille_ansi_auto_theme_emits_truecolor_and_handles_gaps_and_long(self) -> None:
        c = mc.heat([10, 40, 90, 20], unit="ms")
        ansi_braille = c.text(color=True, braille=True)
        assert "38;2;" in ansi_braille
        assert ANSI_RE.sub("", ansi_braille) == c.text(braille=True)

        gapped = mc.heat([10, 20, None, None, 80, 90])
        assert "·" in gapped.text(value=False, braille=True)

        # Up to 48 slots without downsampling in Braille mode; >48 adds n=
        c40 = mc.heat([float(i % 10) for i in range(40)])
        assert "n=40" in c40.text(value=False)
        assert "n=40" not in c40.text(value=False, braille=True)
        assert len(c40.text(value=False, braille=True)) == 20

        c60 = mc.heat([float(i % 10) for i in range(60)])
        assert "n=60" in c60.text(value=False, braille=True)


class TestTableAndCliBraille:
    def test_table_text_and_markdown_braille(self) -> None:
        rows = [
            {
                "svc": "api",
                "loss": [1.8, 1.4, 1.0, 0.7, 0.5, 0.42],
                "lat": [18, 19, 20, 20, 21, 26, 31],
                "sla": [0.82, 0.90],
                "load": [12, 24, 68, 95, 78, 30],
            },
            {
                "svc": "worker",
                "loss": [2.0, 1.7, 1.5, 1.3, 1.1, 0.95],
                "lat": [25, 26, 27, 29, 30, 35, 42],
                "sla": [0.68, 0.90],
                "load": [20, 35, 50, 62, 48, 25],
            },
        ]
        cols = {
            "svc": "text",
            "loss": "spark",
            "lat": {"chip": "hist", "bins": 8, "unit": "ms"},
            "sla": "bullet",
            "load": {"chip": "heat", "unit": "ms"},
        }
        tbl = mc.table(rows, cols)
        default_txt = tbl.text()
        braille_txt = tbl.text(braille=True)
        assert not _has_braille(default_txt)
        assert _has_braille(braille_txt)
        assert tbl.text(braille=True, ascii=True) == tbl.text(ascii=True)
        assert tbl.text(braille=True, ascii=True).isascii()
        assert _has_braille(tbl.markdown(braille=True))
        assert tbl.markdown(braille=True, ascii=True).isascii()

        with ansi_theme("mint_dark"):
            ansi_tbl = tbl.text(braille=True, color=True)
        assert _rgb_seq(THEMES["mint_dark"].accent) in ansi_tbl
        assert ANSI_RE.sub("", ansi_tbl) == braille_txt

    @pytest.mark.parametrize(
        "argv",
        [
            ["spark", "1.84", "1.32", "0.96", "0.74", "0.61", "0.52", "0.46", "0.43", "0.42"],
            ["hist", "18", "19", "20", "20", "21", "22", "26", "31", "--bins", "8", "--reference", "25"],
            ["bullet", "0.82", "0.9", "--ranges", "0.6,0.85,1.0"],
            ["heat", "12", "24", "68", "95", "78", "30", "15", "--unit", "ms"],
        ],
    )
    def test_cli_kind_commands_braille_theme_and_ascii_override(self, argv: list[str]) -> None:
        code, out, err = run([*argv, "--braille"])
        assert (code, err) == (0, "")
        assert _has_braille(out)

        code, ansi_out, err = run(
            [*argv, "--braille", "--format", "ansi", "--theme", "mint_dark"]
        )
        assert (code, err) == (0, "")
        assert _rgb_seq(THEMES["mint_dark"].accent) in ansi_out
        assert ANSI_RE.sub("", ansi_out) == out

        code, ascii_braille, err = run([*argv, "--braille", "--ascii"])
        code2, ascii_only, err2 = run([*argv, "--ascii"])
        assert (code, err) == (0, "")
        assert (code2, err2) == (0, "")
        assert ascii_braille == ascii_only
        assert ascii_braille.isascii()

    def test_cli_table_and_render_with_braille_and_mint_dark(self) -> None:
        rows = json.dumps(
            [
                {"svc": "api", "loss": [1.8, 1.3, 0.9, 0.5, 0.42], "sla": [0.82, 0.90]},
                {"svc": "job", "loss": [1.5, 1.2, 1.0, 0.8, 0.70], "sla": [0.95, 0.90]},
            ]
        )
        cols = ["--col", "svc", "--col", "loss:spark", "--col", "sla:bullet"]
        code, tbl_out, err = run(["table", "-", *cols, "--braille"], rows)
        assert (code, err) == (0, "")
        assert _has_braille(tbl_out)

        code, tbl_ansi, err = run(
            ["table", "-", *cols, "--braille", "--format", "ansi", "--theme", "mint_dark"], rows
        )
        assert (code, err) == (0, "")
        assert _rgb_seq(THEMES["mint_dark"].accent) in tbl_ansi
        assert ANSI_RE.sub("", tbl_ansi) == tbl_out

        code, tbl_ascii, err = run(["table", "-", *cols, "--braille", "--ascii"], rows)
        assert (code, err) == (0, "")
        assert tbl_ascii.isascii()

        doc = (
            "Loss {{spark 1.84 1.32 0.96 0.74 0.61 0.52 0.46 0.43 0.42}}.\n"
            "Hist {{hist 18 19 20 20 21 22 26 31 bins=8 reference=25 unit=ms}}.\n"
            "SLA {{bullet 0.82 0.9}}.\n"
            "Load {{heat 12 24 68 95 78 30 15 unit=ms}}.\n"
        )
        code, ren_out, err = run(["render", "-", "--braille"], doc)
        assert (code, err) == (0, "")
        assert all(_has_braille(line) for line in ren_out.strip().splitlines())

        code, ren_ansi, err = run(
            ["render", "-", "--braille", "--format", "ansi", "--theme", "mint_dark"], doc
        )
        assert (code, err) == (0, "")
        assert _rgb_seq(THEMES["mint_dark"].accent) in ren_ansi
        assert ANSI_RE.sub("", ren_ansi) == ren_out

        code, ren_ascii, err = run(["render", "-", "--braille", "--ascii"], doc)
        assert (code, err) == (0, "")
        assert ren_ascii.isascii()
