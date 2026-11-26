"""Scales shared across chips: common domains, quantiles, robust extents, downsampling."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

from .spec import Chip, ChipError

__all__ = [
    "downsample_minmax",
    "padded",
    "quantile",
    "robust_extent",
    "shared_domain",
    "union_domain",
]

Domain = tuple[float, float]


def padded(lo: float, hi: float, frac: float = 0.08) -> Domain:
    """Widen ``(lo, hi)`` by ``frac`` of its span on each side; a zero span gets a small width."""
    span = hi - lo
    margin = span * frac if span > 0 else max(abs(lo) * 0.05, 1e-9)
    return lo - margin, hi + margin


def union_domain(*domains: Domain | None) -> Domain | None:
    """The smallest ``(lo, hi)`` covering every non-None domain, or None if there are none."""
    ds = [d for d in domains if d is not None]
    if not ds:
        return None
    return min(d[0] for d in ds), max(d[1] for d in ds)


def shared_domain(*items: Any, reference: float | None = None, pad: float = 0.08) -> Domain:
    """One ``(lo, hi)`` for sibling chips, to pass as ``domain=`` when rendering them.

    Each item is a chip (contributes its own domain, already padded), a number, or any iterable
    of numbers (lists, tuples, NumPy arrays, generators; None and NaN are skipped). Raw numbers
    are padded by ``pad`` × their span; ``reference`` is included as a raw number.
    """
    hint = "Pass chips, numbers or lists of numbers, e.g. mintchip.shared_domain(a, b)."
    raw: list[float] = []
    chip_domains: list[Domain | None] = []
    for item in items:
        if isinstance(item, Chip):
            dom = item.args.get("domain") or item.domain
            chip_domains.append((dom[0], dom[1]) if dom is not None else None)
            continue
        if isinstance(item, (str, bytes)) or not isinstance(item, Iterable):
            item = [item]
        for v in item:
            if v is None:
                continue
            try:
                if isinstance(v, (str, bytes, bool)):
                    raise TypeError
                f = float(v)
            except (TypeError, ValueError):
                raise ChipError(
                    f"mintchip.shared_domain: {v!r} is not a number.", fix_hint=hint
                ) from None
            if math.isfinite(f):
                raw.append(f)
    if reference is not None:
        raw.append(float(reference))
    dom = union_domain(padded(min(raw), max(raw), pad) if raw else None, *chip_domains)
    if dom is None:
        raise ChipError("mintchip.shared_domain: no finite number or domain given.", fix_hint=hint)
    return dom


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile (type 7) of already-sorted values."""
    n = len(sorted_values)
    if n == 0:
        raise ValueError("quantile of an empty sequence")
    pos = q * (n - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, n - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def robust_extent(values: Iterable[float], k: float = 3.0) -> Domain:
    """``(lo, hi)`` of the values that lie within ``k`` × IQR of the quartiles.

    Values outside are outliers for the caller to mark at an edge. With a zero IQR the full
    extent is returned, since every non-median value would otherwise count as an outlier.
    """
    s = sorted(float(v) for v in values)
    q1, q3 = quantile(s, 0.25), quantile(s, 0.75)
    iqr = q3 - q1
    if iqr <= 0:
        return s[0], s[-1]
    lo_fence, hi_fence = q1 - k * iqr, q3 + k * iqr
    inside = [v for v in s if lo_fence <= v <= hi_fence]
    return inside[0], inside[-1]


def downsample_minmax(values: Sequence[float | None], n: int) -> list[float | None]:
    """Reduce a series to ``n`` buckets, keeping in each the value farthest from the series
    median, so a single spike survives. All-gap buckets stay None. Shorter series pass through.
    """
    if len(values) <= n:
        return list(values)
    finite = sorted(v for v in values if v is not None)
    med = quantile(finite, 0.5) if finite else 0.0
    out: list[float | None] = []
    for b in range(n):
        bucket = [
            v for v in values[b * len(values) // n : (b + 1) * len(values) // n] if v is not None
        ]
        out.append(max(bucket, key=lambda v: abs(v - med)) if bucket else None)
    return out
