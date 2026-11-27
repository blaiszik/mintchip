"""Ink roles and the six themes (auto, light, dark, mono, mint, mint_dark).

A theme says how each ink role is painted. It never names a background: chips paint no
background, so the reader's surface shows through. In the ``auto`` theme, ``ink`` is
``currentColor`` and the other roles are CSS custom properties with fallbacks that reach 3:1
contrast on both a white (#FFFFFF) and a dark (#14181F) surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

__all__ = ["ROLES", "THEMES", "Theme", "contrast_ratio", "relative_luminance", "resolve_theme"]

# Paint roles a renderer may ask for. "context" is ink at reduced opacity (see svg_base).
ROLES = ("ink", "context", "accent", "good", "bad", "warn")

# Text colours a standalone SVG sets for itself in light and dark mode.
LIGHT_INK = "#1A1D21"
DARK_INK = "#E6E9EE"

_ACCENT = "#3B7DDD"  # blue: "look here", never red
_GOOD = "#2A9152"
_BAD = "#DC4535"
_WARN = "#B87A00"

_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


@dataclass(frozen=True)
class Theme:
    """How each ink role is painted. ``auto`` themes emit CSS (currentColor, var())."""

    name: str
    ink: str
    accent: str
    good: str
    bad: str
    warn: str
    auto: bool = False

    def paint(self, role: str) -> str:
        """CSS colour for a role. ``context`` uses ink; svg_base lowers its opacity."""
        if role in ("ink", "context"):
            return "currentColor" if self.auto else self.ink
        if role not in ROLES:
            raise ValueError(f"unknown ink role {role!r}; use one of {', '.join(ROLES)}")
        colour = getattr(self, role)
        if self.auto and colour == AUTO_FALLBACKS[role]:
            return f"var(--mc-{role}, {colour})"
        return colour


AUTO_FALLBACKS = {"accent": _ACCENT, "good": _GOOD, "bad": _BAD, "warn": _WARN}

THEMES: dict[str, Theme] = {
    "auto": Theme("auto", "currentColor", _ACCENT, _GOOD, _BAD, _WARN, auto=True),
    "light": Theme("light", LIGHT_INK, _ACCENT, _GOOD, _BAD, _WARN),
    "dark": Theme("dark", DARK_INK, _ACCENT, _GOOD, _BAD, _WARN),
    "mono": Theme("mono", "#111111", "#111111", "#111111", "#111111", "#111111"),
    "mint": Theme("mint", LIGHT_INK, "#0D8366", "#1E7D54", "#C83E4D", "#8A4B76"),
    "mint_dark": Theme("mint_dark", DARK_INK, "#3DD6A8", "#52D18A", "#F07178", "#D68FD6"),
}


def resolve_theme(theme: str | Theme = "auto", accent: str | None = None) -> Theme:
    """Look up a theme by name (or pass one through) and apply an ``accent`` override."""
    if isinstance(theme, str):
        if theme not in THEMES:
            raise ValueError(f"unknown theme {theme!r}; use one of {', '.join(THEMES)}")
        theme = THEMES[theme]
    elif not isinstance(theme, Theme):
        raise TypeError(f"theme must be a name or a Theme, not {type(theme).__name__}")
    if accent is not None:
        if not isinstance(accent, str) or not _HEX.fullmatch(accent):
            raise ValueError(f"accent must be a hex colour like '#2563EB', not {accent!r}")
        theme = replace(theme, accent=accent)
    return theme


def _rgb(colour: str) -> tuple[float, float, float]:
    if not _HEX.fullmatch(colour):
        raise ValueError(f"expected a hex colour like '#1F5A9D', got {colour!r}")
    h = colour[1:]
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255


def relative_luminance(colour: str) -> float:
    """WCAG 2.1 relative luminance of a hex colour."""

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = _rgb(colour)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2.1 contrast ratio between two hex colours (1 to 21)."""
    hi, lo = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)
