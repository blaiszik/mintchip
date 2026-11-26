"""mintchip — Zero-dependency word-sized visual chips for AI agents, scientists, and prose."""

from __future__ import annotations

from .change import delta, scatter, waterfall
from .composition import funnel, ratio, share
from .core import (
    Chip,
    ChipError,
    InlineGraphic,
    bar,
    ci,
    dist,
    document,
    format_prose,
    shared_domain,
    spark,
    strip,
)
from .evidence import evidence, gauge, quantiles
from .structure import dual_spark, rank, timeline
from .themes import (
    PALETTES,
    THEMES,
    ChipPalette,
    Theme,
    apply_accent,
    apply_palette,
    contrast_ratio,
    get_palette,
    get_theme,
    relative_luminance,
)

__version__ = "0.1.0"

CATALOG: tuple[dict[str, str], ...] = (
    # Core (5)
    {"name": "spark", "family": "core", "question": "How did a value evolve over steps or time?"},
    {"name": "ci", "family": "core", "question": "What is the estimate and uncertainty vs. null?"},
    {"name": "dist", "family": "core", "question": "How are raw observations spread (skew & outliers)?"},
    {"name": "bar", "family": "core", "question": "How large is a ratio or score vs. baseline & target?"},
    {"name": "strip", "family": "core", "question": "Which seeds/checks passed, warned, failed, or shifted?"},
    # Change, Attribution & Tradeoffs (3)
    {"name": "delta", "family": "change", "question": "How far and in what direction did a value move?"},
    {"name": "waterfall", "family": "change", "question": "Which positive and negative drivers summed to the net change?"},
    {"name": "scatter", "family": "change", "question": "How do two measures correlate or sit on a Pareto frontier?"},
    # Composition, Funnels & Natural Frequencies (3)
    {"name": "share", "family": "composition", "question": "How is a whole divided across categories (never a pie)?"},
    {"name": "funnel", "family": "composition", "question": "Where did items drop off across sequential pipeline stages?"},
    {"name": "ratio", "family": "composition", "question": "What does a probability or count feel like in natural frequencies?"},
    # Operating Windows, Uncertainty & Evidence (3)
    {"name": "gauge", "family": "evidence", "question": "Where does a reading sit inside normal and caution limits?"},
    {"name": "quantiles", "family": "evidence", "question": "What is the predictive probability mass relative to a threshold?"},
    {"name": "evidence", "family": "evidence", "question": "How strong is the statistical evidence given effect and n?"},
    # Structure, Timelines & Comparisons (3)
    {"name": "timeline", "family": "structure", "question": "Where did wall-clock time go and which phase was the bottleneck?"},
    {"name": "rank", "family": "structure", "question": "Where does this entity sit in its cohort or leaderboard?"},
    {"name": "dual_spark", "family": "structure", "question": "How did two paired trajectories diverge or cross over time?"},
)

__all__ = [
    "CATALOG",
    "PALETTES",
    "THEMES",
    "Chip",
    "ChipError",
    "ChipPalette",
    "InlineGraphic",
    "Theme",
    "__version__",
    "apply_accent",
    "apply_palette",
    "bar",
    "ci",
    "contrast_ratio",
    "delta",
    "dist",
    "document",
    "dual_spark",
    "evidence",
    "format_prose",
    "funnel",
    "gauge",
    "get_palette",
    "get_theme",
    "quantiles",
    "rank",
    "ratio",
    "relative_luminance",
    "scatter",
    "share",
    "shared_domain",
    "spark",
    "strip",
    "timeline",
    "waterfall",
]
