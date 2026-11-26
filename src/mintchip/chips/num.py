"""num: a formatted number with unit, significant figures and optional ±. It has no graphic,
so it registers no SVG renderer and ``svg()`` returns ""."""

from __future__ import annotations

from .. import fmt
from ..render.text_base import TextOptions, TextOut
from ..spec import Built, Chip, ChipError, Param, chip, text_renderer


@chip(
    "num",
    question="What is the value?",
    have="One number, no context",
    params=(
        Param("value", "number", "Give the number to show.", required=True, positional=True),
        Param("unit", "string", "Name the unit printed after the number, e.g. ms or %."),
        Param("sig", "int", "Set significant figures (pm, if given, sets precision).", default=3),
        Param("pm", "number", "Give a ± uncertainty; the value is rounded to match it."),
        Param("signed", "bool", "Print + before positive values.", default=False),
        Param("label", "string", "Say what the number measures."),
    ),
    example={"value": 0.82, "pm": 0.03, "label": "Accuracy"},
    size="s",
)
def num(value, *, unit=None, sig=3, pm=None, signed=False, label=None) -> Built:
    if not 1 <= sig <= 15:
        raise ChipError(f"sig must be between 1 and 15; got {sig}.", fix_hint="Pass sig=3.")
    if pm is not None and pm < 0:
        raise ChipError(f"pm must be zero or positive; got {pm}.", fix_hint="Pass pm=abs(pm).")
    shown = _value(value, pm, sig, signed, unit)
    return Built(
        stats={"value": value, "pm": pm, "sig": sig, "signed": signed},
        facts=(f"exact value {value!r}" + (f" ± {pm!r}" if pm else ""),),
        alt=f"{label}: {shown}" if label else shown,
    )


def _value(value: float, pm: float | None, sig: int, signed: bool, unit: str | None) -> str:
    if pm:
        return fmt.pm(value, pm, signed=signed, unit=unit)
    return fmt.num(value, sig=sig, signed=signed, unit=unit)


@text_renderer("num")
def _text(chip: Chip, o: TextOptions) -> TextOut:
    s = chip.stats
    own = _value(s["value"], s["pm"], s["sig"], s["signed"], None)
    dec = fmt.places(own)
    if o.decimals is None or dec is None:  # scientific notation keeps its form
        return TextOut(_value(s["value"], s["pm"], s["sig"], s["signed"], chip.unit), "", dec)
    shown = fmt.fixed(s["value"], o.decimals, signed=s["signed"])
    if s["pm"]:
        shown += f" ± {fmt.fixed(s['pm'], o.decimals)}"
    return TextOut(fmt.with_unit(shown, chip.unit), "", o.decimals)
