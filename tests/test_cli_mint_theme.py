"""Tests for mintchip CLI --theme support and 24-bit ANSI mint palette rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import mintchip as mc
from mintchip.cli import run
from mintchip.render.text_base import ansi, ansi_theme
from mintchip.themes import THEMES


def _rgb(hex_colour: str) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"\x1b[38;2;{r};{g};{b}m"


class TestTextBaseTrueColorAnsi:
    def test_default_auto_preserves_classic_16_color_sgr(self) -> None:
        segs = [("hi", "accent"), ("ok", "good"), ("no", "bad"), ("wn", "warn"), ("bg", "context")]
        classic = ansi(segs)
        assert "\x1b[34mhi\x1b[0m" in classic
        assert "\x1b[32mok\x1b[0m" in classic
        assert "\x1b[31mno\x1b[0m" in classic
        assert "\x1b[33mwn\x1b[0m" in classic
        assert "\x1b[2mbg\x1b[0m" in classic
        assert "38;2;" not in classic
        assert ansi(segs, theme="auto") == classic

    @pytest.mark.parametrize("theme_name", ["mint", "mint_dark", "light", "dark", "mono"])
    def test_explicit_themes_emit_24bit_rgb_sgr(self, theme_name: str) -> None:
        th = THEMES[theme_name]
        segs = [("A", "accent"), ("G", "good"), ("B", "bad"), ("W", "warn"), ("C", "context")]
        out = ansi(segs, theme=theme_name)
        assert f"{_rgb(th.accent)}A\x1b[0m" in out
        assert f"{_rgb(th.good)}G\x1b[0m" in out
        assert f"{_rgb(th.bad)}B\x1b[0m" in out
        assert f"{_rgb(th.warn)}W\x1b[0m" in out
        assert "\x1b[2mC\x1b[0m" in out

        # Context manager produces identical output and restores default on exit
        with ansi_theme(theme_name):
            assert ansi(segs) == out
        assert "38;2;" not in ansi(segs)


class TestCliThemeAcrossSubcommands:
    @pytest.mark.parametrize("theme_name", ["mint", "mint_dark"])
    def test_kind_commands_theme_for_svg_html_and_ansi(self, theme_name: str) -> None:
        th = THEMES[theme_name]

        # SVG
        code, svg, err = run(["spark", "1.8", "1.3", "0.9", "0.6", "--format", "svg", "--theme", theme_name])
        assert (code, err) == (0, "")
        assert svg.startswith("<svg")
        assert th.accent.lower() in svg.lower()
        assert "var(--mc-" not in svg

        # HTML
        code, html_out, err = run(
            ["delta", "0.78", "0.86", "--higher-is-better", "--format", "html", "--theme", theme_name]
        )
        assert (code, err) == (0, "")
        assert th.good.lower() in html_out.lower()
        assert "var(--mc-" not in html_out

        # ANSI 24-bit RGB
        code, ansi_out, err = run(
            ["delta", "0.78", "0.86", "--higher-is-better", "--format", "ansi", "--theme", theme_name]
        )
        assert (code, err) == (0, "")
        assert _rgb(th.good) in ansi_out

        code, bad_ansi, err = run(
            ["delta", "0.86", "0.72", "--higher-is-better", "--format", "ansi", "--theme", theme_name]
        )
        assert (code, err) == (0, "")
        assert _rgb(th.bad) in bad_ansi

        code, warn_ansi, err = run(
            ["gauge", "0.78", "--normal", "0:0.6", "--warn", "0:0.85", "--format", "ansi", "--theme", theme_name]
        )
        assert (code, err) == (0, "")
        assert _rgb(th.warn) in warn_ansi

    def test_default_ansi_cli_remains_backwards_compatible(self) -> None:
        c = mc.delta(0.78, 0.86, higher_is_better=True)
        code, out, err = run(["delta", "0.78", "0.86", "--higher-is-better", "--format", "ansi"])
        assert (code, err) == (0, "")
        assert out == c.text(color=True) + "\n"
        assert "\x1b[32m" in out and "38;2;" not in out

    @pytest.mark.parametrize("theme_name", ["mint", "mint_dark"])
    def test_render_command_theme_html_and_ansi(self, theme_name: str) -> None:
        th = THEMES[theme_name]
        src = "Recall {{delta 0.78 0.86 higher_is_better=true}} and loss {{spark 1.8 1.2 0.7}}.\n"

        code, ansi_out, err = run(["render", "-", "--format", "ansi", "--theme", theme_name], src)
        assert (code, err) == (0, "")
        assert _rgb(th.good) in ansi_out

        code, html_out, err = run(["render", "-", "--format", "html", "--theme", theme_name], src)
        assert (code, err) == (0, "")
        assert th.good.lower() in html_out.lower()
        assert th.accent.lower() in html_out.lower()
        expected_scheme = "dark" if theme_name == "mint_dark" else "light"
        assert f'data-mc-scheme="{expected_scheme}"' in html_out

    @pytest.mark.parametrize("theme_name", ["mint", "mint_dark"])
    def test_table_command_theme_html_and_ansi(self, theme_name: str) -> None:
        th = THEMES[theme_name]
        rows = json.dumps(
            [
                {"model": "emerald", "acc": 0.91, "change": [0.82, 0.91]},
                {"model": "base", "acc": 0.82, "change": [0.85, 0.82]},
            ]
        )
        cols = [
            "--col", "model",
            "--col", "acc:bar",
            "--col", "change:delta",
            "--set", "change.higher_is_better=true",
        ]

        code, ansi_out, err = run(["table", "-", *cols, "--format", "ansi", "--theme", theme_name], rows)
        assert (code, err) == (0, "")
        assert _rgb(th.good) in ansi_out
        assert _rgb(th.bad) in ansi_out

        code, html_out, err = run(["table", "-", *cols, "--format", "html", "--theme", theme_name], rows)
        assert (code, err) == (0, "")
        assert th.good.lower() in html_out.lower()
        assert th.bad.lower() in html_out.lower()
        expected_scheme = "dark" if theme_name == "mint_dark" else "light"
        assert f'data-mc-scheme="{expected_scheme}"' in html_out

        code, frag_out, err = run(
            ["table", "-", *cols, "--format", "html", "--fragment", "--theme", theme_name], rows
        )
        assert (code, err) == (0, "")
        assert frag_out.startswith("<table") and th.good.lower() in frag_out.lower()

    @pytest.mark.parametrize("theme_name", ["mint", "mint_dark"])
    def test_diff_command_theme_html_and_ansi(self, tmp_path: Path, theme_name: str) -> None:
        th = THEMES[theme_name]
        base = tmp_path / "base.json"
        head = tmp_path / "head.json"
        base.write_text(json.dumps({"parse_ms": 100.0, "render_ms": 50.0}), encoding="utf-8")
        head.write_text(json.dumps({"parse_ms": 80.0, "render_ms": 62.0}), encoding="utf-8")

        code, ansi_out, err = run(
            ["diff", str(base), str(head), "--format", "ansi", "--theme", theme_name]
        )
        assert (code, err) == (0, "")
        assert _rgb(th.good) in ansi_out
        assert _rgb(th.bad) in ansi_out

        code, html_out, err = run(
            ["diff", str(base), str(head), "--format", "html", "--theme", theme_name]
        )
        assert (code, err) == (0, "")
        assert th.good.lower() in html_out.lower()
        assert th.bad.lower() in html_out.lower()
        expected_scheme = "dark" if theme_name == "mint_dark" else "light"
        assert f'data-mc-scheme="{expected_scheme}"' in html_out

        # Regression threshold exit code still works with themed HTML
        code_fail, _, err_fail = run(
            [
                "diff", str(base), str(head),
                "--format", "html", "--theme", theme_name, "--fail-on-regression", "5",
            ]
        )
        assert code_fail == 1 and "regression exceeded" in err_fail

    @pytest.mark.parametrize("theme_name", ["mint", "mint_dark"])
    def test_from_command_theme_html_and_ansi(self, theme_name: str) -> None:
        th = THEMES[theme_name]
        diff_input = "42\t8\tsrc/app.py\n15\t5\ttests/test_app.py\n"

        code, html_out, err = run(
            ["from", "git-diff", "-", "--format", "html", "--theme", theme_name], diff_input
        )
        assert (code, err) == (0, "")
        assert th.ink.lower() in html_out.lower()
        expected_scheme = "dark" if theme_name == "mint_dark" else "light"
        assert f'data-mc-scheme="{expected_scheme}"' in html_out

        # Hyperfine JSON produces a Table
        hf = json.dumps(
            {
                "results": [
                    {"command": "fast", "mean": 0.012, "stddev": 0.001, "times": [0.011, 0.012, 0.013]},
                    {"command": "slow", "mean": 0.045, "stddev": 0.002, "times": [0.043, 0.045, 0.047]},
                ]
            }
        )
        code, tbl_html, err = run(
            ["from", "hyperfine", "-", "--format", "html", "--theme", theme_name], hf
        )
        assert (code, err) == (0, "")
        assert th.ink.lower() in tbl_html.lower()
        assert f'data-mc-scheme="{expected_scheme}"' in tbl_html

        code, tbl_ansi, err = run(
            ["from", "hyperfine", "-", "--format", "ansi", "--theme", theme_name], hf
        )
        assert (code, err) == (0, "")
        assert "fast" in tbl_ansi and "slow" in tbl_ansi

    def test_invalid_theme_returns_exit_2_with_suggestion(self) -> None:
        for argv in (
            ["spark", "1", "2", "3", "--theme", "mnt"],
            ["render", "--theme", "mnt"],
            ["table", "--theme", "mnt"],
            ["from", "git-diff", "--theme", "mnt"],
        ):
            code, out, err = run(argv, "42\t8\tsrc/a.py\n")
            assert (code, out) == (2, "")
            assert "unknown theme" in err
            assert "Use --theme mint" in err
