"""Tests for ``mintchip.doctor`` and ``mintchip doctor``."""

from __future__ import annotations

import json

import mintchip as mc
from mintchip import doctor
from mintchip.cli import run


def test_doctor_report_structure_and_probes() -> None:
    rep = doctor.doctor_report()
    assert rep["mintchip"] == mc.__version__
    assert rep["python"]
    assert "encoding" in rep["stdout"]
    assert isinstance(rep["stdout"]["isatty"], bool)
    assert isinstance(rep["stdout"]["ansi_color"], bool)

    kinds = [p["kind"] for p in rep["probes"]]
    assert kinds == list(doctor.PROBE_KINDS)
    for probe in rep["probes"]:
        assert probe["unicode"]
        assert "\x1b[" in probe["ansi"]
        assert probe["ascii"].isascii()


def test_cli_doctor_text_ascii_and_json() -> None:
    code, out, err = run(["doctor"])
    assert (code, err) == (0, "")
    assert f"mintchip {mc.__version__}" in out
    for kind in ("spark", "ci", "dist", "bar", "strip"):
        assert kind in out

    code, out_ascii, err = run(["doctor", "--ascii"])
    assert (code, err) == (0, "")
    assert out_ascii.isascii()

    code, out_json, err = run(["doctor", "--json"])
    assert (code, err) == (0, "")
    payload = json.loads(out_json)
    assert payload["mintchip"] == mc.__version__
    assert [p["kind"] for p in payload["probes"]] == ["spark", "ci", "dist", "bar", "strip"]


def test_doctor_respects_no_color_and_force_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    rep = doctor.doctor_report()
    assert rep["stdout"]["ansi_color"] is False
    assert rep["stdout"]["no_color"] is True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    rep2 = doctor.doctor_report()
    assert rep2["stdout"]["ansi_color"] is True
