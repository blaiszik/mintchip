"""mintchip: word-sized graphics for numbers, in text, SVG and HTML, with no dependencies.

A chip is a small data record (``mintchip.spark([...])``); drawing happens when you render it
with ``.text()``, ``.svg()``, ``.html()`` or ``.markdown()``.
"""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any

from . import chips as _chips  # noqa: F401  (registers every chip kind found in chips/)
from .chips.bar import bar
from .chips.bullet import bullet
from .chips.ci import ci
from .chips.delta import delta
from .chips.dist import dist
from .chips.funnel import funnel
from .chips.gauge import gauge
from .chips.heat import heat
from .chips.hist import hist
from .chips.num import num
from .chips.rank import rank
from .chips.ratio import ratio
from .chips.share import share
from .chips.spark import spark
from .chips.status import status
from .chips.strip import strip
from .chips.timeline import timeline
from .chips.waterfall import waterfall
from .scales import shared_domain, union_domain
from .spec import REGISTRY, Chip, ChipError, Kind, Param, catalog, from_dict
from .themes import THEMES, Theme, contrast_ratio, relative_luminance

# Importing `.spec` binds the internal `mintchip.render` subpackage onto this module; remove the
# attribute so `mintchip.render` resolves lazily to `mintchip.directives.render` while
# `from mintchip.render.html import ...` still works via `sys.modules`.
globals().pop("render", None)

__version__ = "0.2.0"

CATALOG = catalog()

# Loaded on first use, so `import mintchip` pays only for chips and text.
_LAZY = {
    "Table": "tables",
    "table": "tables",
    "format_prose": "prose",
    "lint": "prose",
    "render": "directives",
    "css": "render.html",
    "document": "render.html",
    "ingest": "ingest",
    "diff_benchmarks": "diff",
    "schema": "cli",
    "install_skill": "skill",
}


class _MintchipModule(types.ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        if name in _LAZY and isinstance(value, types.ModuleType):
            return
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _MintchipModule


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
    "bullet",
    "ci",
    "contrast_ratio",
    "css",
    "delta",
    "diff_benchmarks",
    "dist",
    "document",
    "format_prose",
    "from_dict",
    "funnel",
    "gauge",
    "heat",
    "hist",
    "ingest",
    "install_skill",
    "lint",
    "num",
    "rank",
    "ratio",
    "relative_luminance",
    "render",
    "schema",
    "share",
    "shared_domain",
    "spark",
    "status",
    "strip",
    "table",
    "timeline",
    "union_domain",
    "waterfall",
]
