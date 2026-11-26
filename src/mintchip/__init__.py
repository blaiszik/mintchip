"""mintchip: word-sized graphics for numbers, in text, SVG and HTML, with no dependencies.

A chip is a small data record (``mintchip.spark([...])``); drawing happens when you render it
with ``.text()``, ``.svg()``, ``.html()`` or ``.markdown()``.
"""

from __future__ import annotations

import importlib
from typing import Any

from . import chips as _chips  # noqa: F401  (registers every chip kind found in chips/)
from .chips.bar import bar
from .chips.ci import ci
from .chips.delta import delta
from .chips.dist import dist
from .chips.funnel import funnel
from .chips.gauge import gauge
from .chips.num import num
from .chips.rank import rank
from .chips.ratio import ratio
from .chips.share import share
from .chips.spark import spark
from .chips.strip import strip
from .chips.timeline import timeline
from .chips.waterfall import waterfall
from .scales import shared_domain, union_domain
from .spec import REGISTRY, Chip, ChipError, Kind, Param, catalog, from_dict
from .themes import THEMES, Theme, contrast_ratio, relative_luminance

__version__ = "0.2.0.dev0"

CATALOG = catalog()

# Loaded on first use, so `import mintchip` pays only for chips and text.
_LAZY = {
    "Table": "tables",
    "table": "tables",
    "format_prose": "prose",
    "lint": "prose",
    "css": "render.html",
    "document": "render.html",
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module 'mintchip' has no attribute {name!r}")
    value = getattr(importlib.import_module(f"{__name__}.{module}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [
    "CATALOG",
    "REGISTRY",
    "THEMES",
    "Chip",
    "ChipError",
    "Kind",
    "Param",
    "Table",
    "Theme",
    "__version__",
    "bar",
    "ci",
    "contrast_ratio",
    "css",
    "delta",
    "dist",
    "document",
    "format_prose",
    "from_dict",
    "funnel",
    "gauge",
    "lint",
    "num",
    "rank",
    "ratio",
    "relative_luminance",
    "share",
    "shared_domain",
    "spark",
    "strip",
    "table",
    "timeline",
    "union_domain",
    "waterfall",
]
