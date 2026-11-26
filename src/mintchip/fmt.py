"""Number formatting shared by every chip.

Formatters return Unicode (the minus sign is U+2212). ``Chip.text(ascii=True)`` transliterates
the whole output afterwards, so renderers never branch on ASCII for numbers.
"""

from __future__ import annotations

import math
import re

__all__ = [
    "MINUS", "count", "decimals", "fixed", "num", "pct", "places", "pm", "resolving", "with_unit",
]  # fmt: skip

MINUS = "\N{MINUS SIGN}"
_TIGHT_UNITS = frozenset({"%", "‰", "°", "°C", "°F", "×"})


def with_unit(core: str, unit: str | None) -> str:
    """Attach a unit: ``20.3 ms``, but ``82%`` and ``21°C`` with no space."""
    if not unit:
        return core
    return f"{core}{unit}" if unit in _TIGHT_UNITS else f"{core} {unit}"


def _sign(v: float, core: str, signed: bool) -> str:
    if core == "0":
        return core
    if v < 0:
        return MINUS + core
    return f"+{core}" if signed else core


def _strip(s: str) -> str:
    return s.rstrip("0").rstrip(".") if "." in s else s


def _sci(a: float, sig: int) -> str:
    mant, exp = f"{a:.{max(sig - 1, 0)}e}".split("e")
    e = int(exp)
    return f"{_strip(mant)}e{MINUS if e < 0 else ''}{abs(e)}"


def num(v: float, *, sig: int = 3, signed: bool = False, unit: str | None = None) -> str:
    """``sig`` significant figures, thousands separators, scientific below 1e-3 and from 1e6."""
    if not math.isfinite(v):
        raise ValueError(f"cannot format non-finite value {v!r}")
    a = abs(v)
    if a == 0:
        core = "0"
    elif a >= 1e6 or a < 1e-3:
        core = _sci(a, sig)
    else:
        dec = max(0, sig - 1 - math.floor(math.log10(a)))
        core = _strip(f"{round(a, dec):,.{dec}f}")
    return with_unit(_sign(v, core, signed), unit)


def count(n: float, *, unit: str | None = None) -> str:
    """An integer count with thousands separators: ``1,200``."""
    return with_unit(_sign(n, f"{round(abs(n)):,}", False), unit)


def pct(frac: float, *, sig: int = 2, signed: bool = False, decimals: int | None = None) -> str:
    """A fraction as a percentage: 0.82 → ``82%``, 0.064 → ``6.4%``, 0.9993 → ``99.9%``;
    ``decimals`` fixes the places instead (0.82 at 1 → ``82.0%``)."""
    p = frac * 100
    a = abs(p)
    if decimals is not None:
        core = fixed(a, decimals)
        if float(core.replace(",", "")) >= 100 > a:  # never round a shortfall up to 100%
            step = 10.0 ** -max(decimals, 0)
            core = fixed(math.floor(a / step) * step, decimals)
        return _sign(p, core, signed) + "%"
    if 10 <= a < 1e6:
        core = f"{round(a):,}"
        if core == "100" and a < 100:  # never round a shortfall up to 100%
            core = _strip(f"{math.floor(a * 10) / 10:.1f}")
        return _sign(p, core, signed) + "%"
    return num(p, sig=sig, signed=signed) + "%"


def decimals(err: float) -> int:
    """Decimal places that show an uncertainty at 1 significant figure, or 2 when its first
    digit is 1 or 2 (0.03 → 2, 0.012 → 3, 23 → 0, 230 → −1)."""
    if err <= 0 or not math.isfinite(err):
        raise ValueError(f"decimals needs a positive uncertainty, got {err!r}")
    mag = math.floor(math.log10(err))
    return (1 if int(err / 10**mag + 1e-9) <= 2 else 0) - mag


def resolving(values: list[float], width: float, *, tol: float = 0.03) -> int:
    """The fewest decimal places (negative rounds to tens, hundreds...) at which rounding moves
    none of ``values`` by more than ``tol`` × ``width``: 0.031 within 0.012 to 0.050 → 3,
    0.08 within 0.05 to 0.11 → 2, 1.2 within −0.6 to 3.0 → 1. A zero ``width`` falls back to the
    largest magnitude, so equal values still get a sensible place."""
    if not width > 0:
        width = max((abs(v) for v in values), default=0.0) or 1.0
    allowed = tol * width * (1 + 1e-9)
    dec = -math.floor(math.log10(width)) - 1
    while dec < 15 and any(abs(round(v, dec) - v) > allowed for v in values):
        dec += 1
    return dec


def places(s: str) -> int | None:
    """Decimal places shown by a formatted number (``"0.420 ms"`` → 3, ``"1,200"`` → 0); None
    when it is in scientific notation or holds no number."""
    m = _FIRST.search(s)
    if m is None or m[3]:
        return None
    return len(m[2]) - 1 if m[2] else 0


_FIRST = re.compile(r"(\d[\d,]*)(\.\d+)?(e[−-]?\d+)?")


def fixed(v: float, dec: int, *, signed: bool = False, unit: str | None = None) -> str:
    """``v`` rounded to ``dec`` decimal places (negative ``dec`` rounds to tens, hundreds...),
    keeping trailing zeros so numbers in one chip line up: fixed(0.1, 2) == "0.10", and zero
    too: fixed(0, 2) == "0.00"."""
    core = f"{round(abs(v), dec):,.{max(dec, 0)}f}"
    if float(core.replace(",", "")) == 0:
        return with_unit(core, unit)
    return with_unit(_sign(v, core, signed), unit)


def pm(value: float, err: float, *, unit: str | None = None, signed: bool = False) -> str:
    """``value ± err`` with ``err`` at the precision ``decimals`` gives and ``value`` rounded to
    the same place: ``0.82 ± 0.03``."""
    if err <= 0:
        return num(value, signed=signed, unit=unit)
    dec = decimals(err)
    return with_unit(f"{fixed(value, dec, signed=signed)} ± {fixed(err, dec)}", unit)
