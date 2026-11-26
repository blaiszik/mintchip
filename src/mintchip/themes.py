"""Zero-dependency CVD-safe surface themes and color palettes for ``mintchip``.

Pure Python standard library — no Matplotlib or NumPy imports. Every built-in
theme and palette mirrors ``mintfig``'s quantitatively verified deuteranopia,
protanopia, grayscale luminance, and WCAG contrast tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

__all__ = [
    "PALETTES",
    "THEMES",
    "ChipPalette",
    "Theme",
    "apply_accent",
    "apply_palette",
    "contrast_ratio",
    "get_palette",
    "get_theme",
    "relative_luminance",
]


def _parse_hex_rgb(color: str) -> tuple[float, float, float]:
    """Parse ``#RGB`` or ``#RRGGBB`` into normalized ``(r, g, b)`` in ``[0, 1]``."""
    raw = color.strip()
    if not raw.startswith("#"):
        raise ValueError(f"Expected hex color like '#1F5A9D', got {color!r}.")
    h = raw[1:]
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        raise ValueError(f"Expected 3- or 6-digit hex color, got {color!r}.")
    try:
        r = int(h[0:2], 16) / 255.0
        g = int(h[2:4], 16) / 255.0
        b = int(h[4:6], 16) / 255.0
    except ValueError as exc:
        raise ValueError(f"Invalid hex color {color!r}.") from exc
    return r, g, b


def relative_luminance(color: str) -> float:
    """Compute WCAG 2.1 relative luminance for a hex color."""
    r, g, b = _parse_hex_rgb(color)

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(c1: str, c2: str) -> float:
    """Compute WCAG 2.1 contrast ratio between two hex colors."""
    l1 = relative_luminance(c1)
    l2 = relative_luminance(c2)
    hi, lo = (l1, l2) if l1 >= l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


def _lift_for_dark_ground(color: str, bg: str) -> str:
    """Lighten a series color on dark surfaces so contrast stays >= 4.5:1."""
    if contrast_ratio(color, bg) >= 4.5:
        return color
    rgb = _parse_hex_rgb(color)
    for mix in (0.18, 0.32, 0.45, 0.58, 0.72):
        lifted = tuple(c + (1.0 - c) * mix for c in rgb)
        cand = "#{:02X}{:02X}{:02X}".format(*(round(v * 255) for v in lifted))
        if contrast_ratio(cand, bg) >= 4.5:
            return cand
    return "#DCE6F2"


@dataclass(frozen=True)
class Theme:
    """Immutable visual token set for inline micro-graphics."""

    name: str
    description: str

    background: str = "#FFFFFF"
    ink: str = "#1A1D21"
    muted: str = "#5B6570"
    axis: str = "#8A939E"
    grid: str = "#E3E7EC"
    context_line: str = "#B4BCC6"
    context_fill: str = "#CDD3DA"
    zero_line: str = "#1A1D21"

    series_colors: tuple[str, ...] = ("#1F5A9D", "#CD4324", "#0F9478", "#CC8800")
    accent_colors: tuple[str, ...] = ("#CD4324", "#1F5A9D", "#0F9478")
    seq_stops: tuple[str, ...] = (
        "#F4F7FB",
        "#C9DBEF",
        "#8FB5DF",
        "#4F8ACB",
        "#1F5A9D",
        "#173F70",
    )
    div_low: tuple[str, ...] = ("#1B4E8A", "#4F8ACB", "#A9C7E6")
    div_high: tuple[str, ...] = ("#F0B7A4", "#DD6F50", "#B5391E")
    div_mid: str = "#F1F2F4"


DEFAULT_THEME = Theme(
    name="default",
    description="Clean light surface with restrained editorial palette and quiet rules.",
)

DARK_THEME = Theme(
    name="dark",
    description="Deep charcoal slate ground with luminous CVD-safe hues for dark UIs and slides.",
    background="#14181F",
    ink="#ECEFF4",
    muted="#9AA5B4",
    axis="#657082",
    grid="#272E3B",
    context_line="#586375",
    context_fill="#3A4354",
    zero_line="#CBD3DF",
    series_colors=("#4A89DC", "#F47E62", "#4BD9BA", "#F6DF78"),
    accent_colors=("#F47E62", "#4A89DC", "#4BD9BA"),
    seq_stops=("#1C2330", "#223654", "#2B5182", "#3B72B3", "#589BE3", "#8CC4F8"),
    div_low=("#78B8F5", "#4381C4", "#233C59"),
    div_high=("#5B2B24", "#B84C3B", "#F4866C"),
    div_mid="#222936",
)

PAPER_THEME = Theme(
    name="paper",
    description="Warm ivory parchment ground with espresso ink and refined earth-editorial hues.",
    background="#FAF7F0",
    ink="#221E1A",
    muted="#635B52",
    axis="#8F867A",
    grid="#E7E0D3",
    context_line="#BEB5A7",
    context_fill="#D7CFC2",
    zero_line="#221E1A",
    series_colors=("#1E446E", "#B83B1E", "#36997A", "#DAA424"),
    accent_colors=("#B83B1E", "#1E446E", "#36997A"),
    seq_stops=("#F7F3EA", "#D8E1E8", "#A3BACD", "#608AB0", "#1E446E", "#132D4A"),
    div_low=("#153559", "#4B7CA8", "#A8C3DA"),
    div_high=("#EBB4A2", "#D96B4D", "#A32F14"),
    div_mid="#EFEAE0",
)

EDITORIAL_THEME = Theme(
    name="editorial",
    description="Crisp white newspaper-graphics surface with steel blue, terracotta, sage, and ochre.",
    background="#FFFFFF",
    ink="#121212",
    muted="#666666",
    axis="#333333",
    grid="#D6D6D6",
    context_line="#C0C0C0",
    context_fill="#D8D8D8",
    zero_line="#222222",
    series_colors=("#285F8A", "#D44D27", "#4B9B88", "#D9A226"),
    accent_colors=("#D44D27", "#285F8A", "#4B9B88"),
    seq_stops=("#F5F7F9", "#D3E0EA", "#9EBBD1", "#6191B5", "#285F8A", "#193F5E"),
    div_low=("#1A476A", "#4A7FA8", "#A7C4DA"),
    div_high=("#F0B8A5", "#DF7452", "#B83B19"),
    div_mid="#F2F2F2",
)

BOLD_THEME = Theme(
    name="bold",
    description="High-contrast data journalism look on a matte-gray ground.",
    background="#F0F0F0",
    ink="#222222",
    muted="#525252",
    axis="#7A7A7A",
    grid="#CBCBCB",
    context_line="#A6A6A6",
    context_fill="#C6C6C6",
    zero_line="#3A3A3A",
    series_colors=("#008FD5", "#D6381C", "#6B1C6D", "#DDA324"),
    accent_colors=("#D6381C", "#008FD5", "#6B1C6D"),
    seq_stops=("#E6EEF4", "#B8D8EE", "#74B9E3", "#2A9FD9", "#0079B8", "#005380"),
    div_low=("#005B8C", "#008FD5", "#94CDEB"),
    div_high=("#F0B0A1", "#E36249", "#B82910"),
    div_mid="#E4E4E4",
)

MONO_THEME = Theme(
    name="mono",
    description="High-contrast monochrome print theme with a single vermilion highlight accent.",
    background="#FFFFFF",
    ink="#111111",
    muted="#555555",
    axis="#787878",
    grid="#E5E5E5",
    context_line="#B0B0B0",
    context_fill="#D0D0D0",
    zero_line="#111111",
    series_colors=("#3F4954", "#C8321E", "#7C858F", "#B0B8C0"),
    accent_colors=("#C8321E", "#3F4954", "#7C858F"),
    seq_stops=("#F5F5F5", "#DCDCDC", "#B4B4B4", "#828282", "#4E4E4E", "#222222"),
    div_low=("#222222", "#666666", "#B8B8B8"),
    div_high=("#F0B8AE", "#DE6A56", "#B82814"),
    div_mid="#F0F0F0",
)

THEMES: dict[str, Theme] = {
    "default": DEFAULT_THEME,
    "dark": DARK_THEME,
    "paper": PAPER_THEME,
    "editorial": EDITORIAL_THEME,
    "bold": BOLD_THEME,
    "mono": MONO_THEME,
}

THEME_ALIASES: dict[str, str] = {
    "mintfig": "default",
    "mintchip": "default",
    "light": "default",
    "warm": "paper",
    "newspaper": "editorial",
    "print": "mono",
}


@dataclass(frozen=True)
class ChipPalette:
    """CVD- and grayscale-verified 4-color + sequential/diverging palette."""

    name: str
    description: str
    series_colors: tuple[str, ...]
    accent_colors: tuple[str, ...]
    seq_stops: tuple[str, ...]
    div_low: tuple[str, ...]
    div_high: tuple[str, ...]
    div_mid: str = "#F1F2F4"


PALETTES: dict[str, ChipPalette] = {
    "default": ChipPalette(
        name="default",
        description="Built-in editorial palette (blue, vermilion, teal, amber).",
        series_colors=DEFAULT_THEME.series_colors,
        accent_colors=DEFAULT_THEME.accent_colors,
        seq_stops=DEFAULT_THEME.seq_stops,
        div_low=DEFAULT_THEME.div_low,
        div_high=DEFAULT_THEME.div_high,
        div_mid=DEFAULT_THEME.div_mid,
    ),
    "okabe_ito": ChipPalette(
        name="okabe_ito",
        description="Okabe-Ito colorblind-safe palette tuned for grayscale separation.",
        series_colors=("#005E94", "#CC5500", "#00A87E", "#E6AF00"),
        accent_colors=("#CC5500", "#005E94", "#00A87E"),
        seq_stops=("#F2F7FB", "#C2DFEE", "#7BB9DA", "#2E8EC2", "#005E94", "#003D63"),
        div_low=("#00446E", "#2E8EC2", "#9CCCE6"),
        div_high=("#F2B896", "#E07938", "#B54800"),
        div_mid="#F2F3F5",
    ),
    "tol": ChipPalette(
        name="tol",
        description="Paul Tol scientific palette: indigo, crimson, emerald, warm gold.",
        series_colors=("#332288", "#CC3344", "#229966", "#DDAA33"),
        accent_colors=("#CC3344", "#332288", "#229966"),
        seq_stops=("#F4F3FA", "#CFCBE8", "#9D95D1", "#685CB2", "#332288", "#21155C"),
        div_low=("#241766", "#5D4FA6", "#ACA4D9"),
        div_high=("#F0B0B8", "#DE6472", "#B52434"),
        div_mid="#F2F2F5",
    ),
    "earth": ChipPalette(
        name="earth",
        description="Warm natural tones: deep slate blue, terracotta, moss green, ochre.",
        series_colors=("#203F60", "#B84228", "#4D8B55", "#D49E2A"),
        accent_colors=("#B84228", "#203F60", "#4D8B55"),
        seq_stops=("#F5F6F8", "#CFD8E2", "#97AEC4", "#5B80A3", "#203F60", "#132940"),
        div_low=("#17304A", "#4F7499", "#A6BCD1"),
        div_high=("#EAB5A6", "#D46D52", "#A1341B"),
        div_mid="#F2F1EE",
    ),
    "ocean": ChipPalette(
        name="ocean",
        description="Marine palette: deep cobalt, reef coral, seafoam teal, sand gold.",
        series_colors=("#143E66", "#D95240", "#1A9E9E", "#DEB030"),
        accent_colors=("#D95240", "#143E66", "#1A9E9E"),
        seq_stops=("#F2F7F9", "#C5E1E6", "#7EC2CC", "#359EA8", "#1A7D8A", "#0F4D59"),
        div_low=("#103252", "#3A729E", "#99BCD6"),
        div_high=("#F2BAB2", "#E47868", "#BF3B2A"),
        div_mid="#F2F4F5",
    ),
    "berry": ChipPalette(
        name="berry",
        description="Rich plum, steel blue, forest emerald, warm honey.",
        series_colors=("#7B2466", "#1D619E", "#128060", "#CE9216"),
        accent_colors=("#7B2466", "#1D619E", "#128060"),
        seq_stops=("#F9F3F7", "#E4C5DC", "#C68DB8", "#A1568E", "#7B2466", "#521444"),
        div_low=("#154878", "#4682B8", "#A3C4E0"),
        div_high=("#E5B3D7", "#BA66A3", "#7B2466"),
        div_mid="#F3F2F4",
    ),
}


def get_theme(theme: str | Theme = "default") -> Theme:
    """Resolve a theme name, alias, or :class:`Theme` instance."""
    if isinstance(theme, Theme):
        return theme
    if not isinstance(theme, str):
        raise TypeError(f"style must be a theme name or Theme instance, got {type(theme).__name__}.")
    key = theme.strip().lower().replace("-", "_").replace(" ", "_")
    canonical = THEME_ALIASES.get(key, key)
    if canonical not in THEMES:
        valid = ", ".join(THEMES)
        raise ValueError(f"Unknown style {theme!r}. Choose one of: {valid}.")
    return THEMES[canonical]


def get_palette(palette: str | ChipPalette = "default") -> ChipPalette:
    """Resolve a palette name or :class:`ChipPalette` instance."""
    if isinstance(palette, ChipPalette):
        return palette
    if not isinstance(palette, str):
        raise TypeError(
            f"palette must be a palette name or ChipPalette instance, got {type(palette).__name__}."
        )
    key = palette.strip().lower().replace("-", "_").replace(" ", "_")
    if key not in PALETTES:
        valid = ", ".join(PALETTES)
        raise ValueError(f"Unknown palette {palette!r}. Choose one of: {valid}.")
    return PALETTES[key]


def apply_palette(theme: Theme, palette: str | ChipPalette | None) -> Theme:
    """Overlay ``palette`` onto ``theme`` with automatic dark-ground contrast lifting."""
    if palette is None:
        return theme
    pal = get_palette(palette)
    if pal.name == "default":
        return theme
    if relative_luminance(theme.background) < 0.2:
        return replace(
            theme,
            series_colors=tuple(_lift_for_dark_ground(c, theme.background) for c in pal.series_colors),
            accent_colors=tuple(_lift_for_dark_ground(c, theme.background) for c in pal.accent_colors),
        )
    return replace(
        theme,
        series_colors=pal.series_colors,
        accent_colors=pal.accent_colors,
        seq_stops=pal.seq_stops,
        div_low=pal.div_low,
        div_high=pal.div_high,
        div_mid=pal.div_mid,
    )


def apply_accent(theme: Theme, accent: str | None) -> Theme:
    """Override the primary highlight color on ``theme`` with a custom hex color."""
    if accent is None:
        return theme
    if not isinstance(accent, str) or not accent.strip():
        raise ValueError(f"accent must be a hex color like '#2563EB', got {accent!r}.")
    r, g, b = _parse_hex_rgb(accent)
    hex_col = f"#{round(r * 255):02X}{round(g * 255):02X}{round(b * 255):02X}"
    if relative_luminance(theme.background) < 0.2:
        hex_col = _lift_for_dark_ground(hex_col, theme.background)
    elif contrast_ratio(hex_col, theme.background) < 3.0:
        for factor in (0.82, 0.68, 0.54, 0.40):
            cand = f"#{round(r * factor * 255):02X}{round(g * factor * 255):02X}{round(b * factor * 255):02X}"
            if contrast_ratio(cand, theme.background) >= 3.0:
                hex_col = cand
                break
    series = list(theme.series_colors)
    if len(series) >= 2:
        series[1] = hex_col
    else:
        series[0] = hex_col
    accents = (hex_col, *theme.accent_colors[1:])
    return replace(theme, series_colors=tuple(series), accent_colors=accents)
