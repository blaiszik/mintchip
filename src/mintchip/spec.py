"""The chip record, the kind registry and the registration decorators.

A chip kind is one module in ``mintchip/chips/`` that registers three functions::

    @chip("spark", question=..., have=..., params=(Param(...), ...), example={...}, size="m")
    def spark(values, *, band=None, ...) -> Built: ...     # validate, compute stats

    @text_renderer("spark")
    def _text(chip: Chip, o: TextOptions) -> TextOut: ...

    @svg_renderer("spark")
    def _svg(chip: Chip, c: Canvas) -> None: ...

``@chip`` checks the function signature against ``params`` at import, and wraps it so that
every argument arrives already type-checked and normalised (see ``Param``), any ``ChipError``
names ``mintchip.<kind>``, and the returned ``Built`` becomes a ``Chip``.
"""

from __future__ import annotations

import functools
import inspect
import json
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .render import html as _html
from .render.svg_base import SIZES, Canvas, svg_root
from .render.text_base import TextOptions, TextOut, ansi, plain, to_ascii
from .themes import resolve_theme

__all__ = [
    "CATALOG_ORDER",
    "REGISTRY",
    "Built",
    "Chip",
    "ChipError",
    "Kind",
    "Param",
    "catalog",
    "chip",
    "domain_warnings",
    "from_dict",
    "own_scale",
    "sibling_domain",
    "svg_renderer",
    "text_renderer",
]

CATALOG_ORDER = (
    "num", "spark", "ci", "dist", "bar", "gauge", "delta", "strip", "share", "ratio",
    "timeline", "rank", "waterfall", "funnel",
)  # fmt: skip

PARAM_TYPES = ("number", "int", "string", "bool", "numbers", "range", "strings", "values",
               "mapping")  # fmt: skip


class ChipError(ValueError):
    """A validation failure, with a ``fix_hint`` an agent or a person can act on."""

    def __init__(self, message: str, *, fix_hint: str | None = None) -> None:
        self.message = message
        self.fix_hint = fix_hint
        super().__init__(f"{message} Fix: {fix_hint}" if fix_hint else message)


@dataclass(frozen=True)
class Param:
    """One constructor argument. The CLI, JSON Schema and guide are generated from these.

    Types, and what the constructor body receives after normalisation:
    ``number`` float · ``int`` int · ``string`` str · ``bool`` bool ·
    ``numbers`` list[float | None] (None or NaN is a gap) · ``range`` (lo, hi) tuple, lo ≤ hi ·
    ``strings`` list[str] · ``values`` list[bool | str | float | None] ·
    ``mapping`` dict[str, float | (float, float)] from a dict or a list of pairs.
    Sequence types accept any iterable. None always means "not given".
    """

    name: str
    type: str
    help: str
    required: bool = False
    positional: bool = False
    default: Any = None
    choices: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Built:
    """What a constructor body returns; ``@chip`` adds kind, args, label and unit."""

    stats: Mapping[str, Any]
    facts: Iterable[str]
    alt: str
    warnings: Iterable[str] = ()
    domain: tuple[float, float] | None = None


@dataclass(frozen=True)
class Kind:
    """A registered chip kind. ``fn`` is the public, validating constructor."""

    name: str
    fn: Callable[..., Chip]
    question: str
    have: str
    params: tuple[Param, ...]
    example: Mapping[str, Any]
    size: str = "m"
    text: Callable[[Chip, TextOptions], TextOut] | None = None
    svg: Callable[[Chip, Canvas], None] | None = None
    cuts: Callable[[Chip, tuple[float, float], bool], list[str]] | None = None
    own_scale: bool = False  # the natural scale is each chip's own total (bar)

    def example_chip(self) -> Chip:
        return self.fn(**self.example)


REGISTRY: dict[str, Kind] = {}


# --- the record -----------------------------------------------------------------------------
@dataclass(frozen=True)
class Chip:
    """A chip is data: validated arguments, computed stats, facts and warnings. It holds no
    theme, size or drawing; everything visual is a render argument."""

    kind: str
    args: Mapping[str, Any]
    stats: Mapping[str, Any]
    facts: tuple[str, ...]
    warnings: tuple[str, ...]
    alt: str
    label: str | None = None
    unit: str | None = None
    domain: tuple[float, float] | None = None

    @property
    def _kind(self) -> Kind:
        if self.kind not in REGISTRY:
            raise ChipError(f"mintchip: unknown chip kind {self.kind!r}.", fix_hint=_kinds_hint())
        return REGISTRY[self.kind]

    def _domain(self, domain: Any) -> tuple[float, float] | None:
        """Render argument, then ``args["domain"]``, then ``chip.domain``."""
        if domain is not None:
            lo, hi = _range(f"{self.kind}.render", "domain", domain)
            if not lo < hi:
                raise ChipError(
                    f"mintchip.{self.kind}: domain must have lo < hi; got {domain!r}.",
                    fix_hint="Pass domain=(lo, hi), e.g. from mintchip.shared_domain(a, b).",
                )
            return lo, hi
        if self.args.get("domain") is not None:
            lo, hi = self.args["domain"]
            return float(lo), float(hi)
        return self.domain

    def _text_out(
        self, ascii: bool, compact: bool, domain: Any, decimals: int | None = None
    ) -> TextOut:
        render = self._kind.text
        if render is None:
            raise ChipError(f"mintchip.{self.kind} has no text renderer.")
        if decimals is not None and (isinstance(decimals, bool) or not isinstance(decimals, int)):
            raise ChipError(
                f"mintchip.{self.kind}: decimals must be a whole number; got {decimals!r}.",
                fix_hint="Pass decimals=2, or leave it out for the chip's own precision.",
            )
        o = TextOptions(
            ascii=ascii, compact=compact, domain=self._domain(domain), decimals=decimals
        )
        return render(self, o)

    def text(
        self,
        *,
        ascii: bool = False,
        compact: bool = False,
        value: bool = True,
        color: bool = False,
        domain: Any = None,
        decimals: int | None = None,
    ) -> str:
        """``"{value} {glyph}"``. ``ascii`` is pure ASCII, ``compact`` shortens the value,
        ``color`` adds ANSI colour by ink role, ``domain`` imposes a shared scale, ``decimals``
        sets the decimal places of the primary value (kinds whose value is a decimal number)."""
        out = self._text_out(ascii, compact, domain, decimals)
        glyph = ansi(out.glyph, ascii=ascii) if color else plain(out.glyph, ascii=ascii)
        if not value:
            return glyph
        val = to_ascii(out.value) if ascii else out.value
        return f"{val} {glyph}" if glyph else val

    def value(
        self, *, compact: bool = False, ascii: bool = False, decimals: int | None = None
    ) -> str:
        """The value part of ``text()`` alone, without the glyph: ``compact`` shortens it,
        ``ascii`` makes it pure ASCII, ``decimals`` sets the primary value's decimal places."""
        v = self._text_out(ascii, compact, None, decimals).value
        return to_ascii(v) if ascii else v

    @property
    def value_text(self) -> str:
        """The value part of ``text()``, in full: ``value()`` with no options."""
        return self.value()

    def warnings_for(self, domain: Any = None) -> tuple[str, ...]:
        """The warnings that hold when the chip is drawn on ``domain``, as a table column or a
        prose group imposes one: a shared scale can bring a clipped value back on scale, or cut
        data the chip's own scale kept. ``warnings`` is the set for the chip's own scale, and
        ``warnings_for(None)`` returns it."""
        cuts = self._kind.cuts
        if domain is None or cuts is None:
            return self.warnings
        own = self._domain(None)
        stale = set(cuts(self, own, self.args.get("domain") is None)) if own else set()
        kept = tuple(w for w in self.warnings if w not in stale)
        return kept + tuple(cuts(self, self._domain(domain), False))

    def svg(
        self,
        *,
        theme: Any = "auto",
        accent: str | None = None,
        domain: Any = None,
        size: str | None = None,
        standalone: bool = False,
    ) -> str:
        """Inline SVG, 1em tall. ``theme`` is auto (follows the text colour), light, dark or
        mono; ``size`` is s, m or l; ``standalone`` embeds light/dark CSS for a .svg file.
        Returns "" for kinds that have no graphic."""
        k = self._kind
        if k.svg is None:
            return ""
        try:
            th = resolve_theme(theme, accent)
        except (TypeError, ValueError) as e:
            raise ChipError(f"mintchip.{self.kind}: {e}.", fix_hint="Use theme='auto'.") from None
        size = size or k.size
        if size not in SIZES:
            raise ChipError(
                f"mintchip.{self.kind}: unknown size {size!r}.", fix_hint="Use 's', 'm' or 'l'."
            )
        natural = domain is None and self.args.get("domain") is None
        c = Canvas(SIZES[size], th, self._domain(domain), natural=natural)
        k.svg(self, c)
        return svg_root(
            c, alt=self.alt, facts=self.facts, spec=self.to_dict(), standalone=standalone
        )

    def html(
        self,
        *,
        theme: Any = "auto",
        accent: str | None = None,
        domain: Any = None,
        value: bool = True,
        label: bool = False,
        details: bool = True,
        detail: str | None = None,
        compact: bool = True,
        decimals: int | None = None,
    ) -> str:
        """Inline HTML, valid inside ``<p>`` and ``<td>``: the value in the text's own type,
        then the SVG. ``compact`` shows the short value; ``decimals`` sets the primary value's
        decimal places; ``details`` adds a no-JavaScript popover with the label, the full
        value, the facts the sentence does not already show, the warnings that hold on this
        ``domain`` and ``detail`` (trusted HTML, appended)."""
        full = self._text_out(False, False, domain, decimals).value
        shown = self._text_out(False, True, domain, decimals).value if compact else full
        return _html.chip_html(
            self,
            svg=self.svg(theme=theme, accent=accent, domain=domain),
            value=shown if value else None,
            full=full,
            label=self.label if label else None,
            details=details,
            detail=detail,
            warnings=self.warnings_for(domain),
        )

    def markdown(self, *, compact: bool = False, ascii: bool = False) -> str:
        """The text form in a code span."""
        t = self.text(ascii=ascii, compact=compact)
        return f"`` {t} ``" if "`" in t else f"`{t}`"

    def to_dict(self) -> dict[str, Any]:
        """``{"chip": kind, **args}``: JSON-safe, and ``from_dict`` rebuilds the chip."""
        return {"chip": self.kind, **json.loads(json.dumps(dict(self.args)))}

    def summary(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "value": self.value_text,
            "text": self.text(),
            "alt": self.alt,
            "facts": list(self.facts),
            "warnings": list(self.warnings),
        }

    def save(self, path: str | Path, **render_options: Any) -> dict[str, Any]:
        """Write ``.svg`` (standalone), ``.html``, ``.txt`` or ``.json``; returns the summary."""
        dest = Path(path)
        suffix = dest.suffix.lower()
        try:
            if suffix == ".svg":
                content = self.svg(standalone=True, **render_options)
                if not content:
                    raise ChipError(
                        f"mintchip.{self.kind} has no graphic to save as .svg.",
                        fix_hint="Save as .html, .txt or .json.",
                    )
            elif suffix in (".html", ".htm"):
                opts = {"label": True, "compact": False, **render_options}
                content = _html.page(self.html(**opts), title=self.alt)
            elif suffix == ".txt":
                content = self.text(**render_options) + "\n"
            elif suffix == ".json":
                content = json.dumps(self.to_dict(), ensure_ascii=False, **render_options) + "\n"
            else:
                raise ChipError(
                    f"mintchip.{self.kind}.save: unsupported extension {suffix!r}.",
                    fix_hint="Save as .svg, .html, .txt or .json.",
                )
        except TypeError as e:
            raise ChipError(
                f"mintchip.{self.kind}.save: {e}.",
                fix_hint="Pass only the options of the matching render method.",
            ) from None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        return {**self.summary(), "path": str(dest)}

    def __str__(self) -> str:
        return self.text()

    def __repr__(self) -> str:
        t = self.text()
        return f"<Chip {self.kind}: {t if len(t) <= 80 else t[:79] + '…'}>"

    def _repr_html_(self) -> str:
        return f"<style>{_html.css()}</style>{self.html()}"


# --- registration ---------------------------------------------------------------------------
def chip(
    name: str,
    *,
    question: str,
    have: str,
    params: tuple[Param, ...],
    example: Mapping[str, Any],
    size: str = "m",
) -> Callable[[Callable[..., Built]], Callable[..., Chip]]:
    """Register a chip constructor. The body receives normalised arguments and returns
    ``Built(stats=..., facts=..., alt=..., warnings=..., domain=...)``."""

    def register(fn: Callable[..., Built]) -> Callable[..., Chip]:
        sig = inspect.signature(fn)
        _check_params(name, fn, sig, params, size)

        @functools.wraps(fn)
        def build(*a: Any, **kw: Any) -> Chip:
            try:
                bound = sig.bind(*a, **kw)
            except TypeError as e:
                raise _call_error(name, params, kw, e) from None
            bound.apply_defaults()
            values = {p.name: _coerce(name, p, bound.arguments[p.name]) for p in params}
            try:
                out = fn(**values)
            except ChipError as e:
                if e.message.startswith("mintchip."):
                    raise
                raise ChipError(f"mintchip.{name}: {e.message}", fix_hint=e.fix_hint) from None
            args = {}
            for p in params:
                v = _jsonable(values[p.name])
                if v != _jsonable(p.default):
                    args[p.name] = v
            return Chip(
                kind=name,
                args=args,
                stats=dict(out.stats),
                facts=tuple(out.facts),
                warnings=tuple(out.warnings),
                alt=out.alt,
                label=values.get("label"),
                unit=values.get("unit"),
                domain=None if out.domain is None else (float(out.domain[0]), float(out.domain[1])),
            )

        prior = REGISTRY.get(name)
        if prior is not None and prior.fn.__module__ != fn.__module__:
            raise ValueError(f"chip kind {name!r} is already registered by {prior.fn.__module__}")
        REGISTRY[name] = Kind(name, build, question, have, tuple(params), dict(example), size)
        return build

    return register


def own_scale(name: str) -> None:
    """Declare that this kind's natural scale is each chip's own total (call after ``@chip``).

    Siblings of such a kind share a scale only when their scales already agree: 38/40 beside
    1,840/1,850 are two shares, and drawing both against 1,850 would empty the first bar.
    """
    REGISTRY[name] = replace(_registered(name), own_scale=True)


def sibling_domain(kind: str, domains: Iterable[Any]) -> tuple[float, float] | None:
    """One scale for sibling chips of one kind (a table column, a group in a sentence), or
    None when each should keep its own."""
    ds = [(float(d[0]), float(d[1])) for d in domains if d is not None]
    if not ds:
        return None
    if _registered(kind).own_scale and len(set(ds)) > 1:
        return None
    return min(d[0] for d in ds), max(d[1] for d in ds)


def text_renderer(name: str) -> Callable[[Callable[[Chip, TextOptions], TextOut]], Any]:
    """Register ``render(chip, o: TextOptions) -> TextOut`` for a kind (after ``@chip``)."""

    def register(fn: Callable[[Chip, TextOptions], TextOut]) -> Callable[..., TextOut]:
        REGISTRY[name] = replace(_registered(name), text=fn)
        return fn

    return register


def svg_renderer(name: str) -> Callable[[Callable[[Chip, Canvas], None]], Any]:
    """Register ``render(chip, c: Canvas) -> None`` for a kind (after ``@chip``)."""

    def register(fn: Callable[[Chip, Canvas], None]) -> Callable[..., None]:
        REGISTRY[name] = replace(_registered(name), svg=fn)
        return fn

    return register


def domain_warnings(
    name: str,
) -> Callable[[Callable[[Chip, tuple[float, float], bool], list[str]]], Any]:
    """Register ``cuts(chip, domain, own) -> [warning, ...]`` for a kind (after ``@chip``): the
    warnings that depend on the scale, for a resolved ``domain``; ``own`` is True when that is
    the chip's natural scale. The constructor must produce the same lines for its own scale, so
    ``Chip.warnings_for`` can swap them for those of an imposed one."""

    def register(fn: Callable[[Chip, tuple[float, float], bool], list[str]]) -> Any:
        REGISTRY[name] = replace(_registered(name), cuts=fn)
        return fn

    return register


def from_dict(d: Mapping[str, Any]) -> Chip:
    """Rebuild a chip from ``chip.to_dict()`` (or any ``{"chip": kind, **args}`` spec)."""
    if not isinstance(d, Mapping) or "chip" not in d:
        raise ChipError(
            "mintchip.from_dict needs a dict with a 'chip' key.",
            fix_hint='Pass e.g. {"chip": "spark", "values": [1, 2, 3]}.',
        )
    kind = d["chip"]
    if kind not in REGISTRY:
        raise ChipError(f"mintchip.from_dict: unknown chip {kind!r}.", fix_hint=_kinds_hint(kind))
    return REGISTRY[kind].fn(**{k: v for k, v in d.items() if k != "chip"})


def catalog() -> tuple[dict[str, str], ...]:
    """Registered kinds in catalog order: name, question, have."""
    order = {k: i for i, k in enumerate(CATALOG_ORDER)}
    kinds = sorted(REGISTRY.values(), key=lambda k: (order.get(k.name, len(order)), k.name))
    return tuple({"name": k.name, "question": k.question, "have": k.have} for k in kinds)


# --- internals ------------------------------------------------------------------------------
def _registered(name: str) -> Kind:
    if name not in REGISTRY:
        raise ValueError(f"register the constructor with @chip({name!r}) before its renderers")
    return REGISTRY[name]


def _kinds_hint(near: Any = None) -> str:
    names = sorted(REGISTRY)
    if isinstance(near, str):
        import difflib

        close = difflib.get_close_matches(near, names, n=1)
        if close:
            return f"Did you mean {close[0]!r}? Kinds: {', '.join(names)}."
    return f"Use one of: {', '.join(names)}."


def _check_params(
    name: str, fn: Callable[..., Any], sig: inspect.Signature, params: tuple[Param, ...], size: str
) -> None:
    where = f"@chip({name!r}) on {fn.__module__}.{fn.__name__}"
    if size not in SIZES:
        raise TypeError(f"{where}: size must be one of {', '.join(SIZES)}")
    fn_names = list(sig.parameters)
    p_names = [p.name for p in params]
    if fn_names != p_names:
        raise TypeError(f"{where}: signature {fn_names} does not match params {p_names}")
    for p, sp in zip(params, sig.parameters.values(), strict=True):
        if p.type not in PARAM_TYPES:
            raise TypeError(f"{where}: param {p.name!r} has unknown type {p.type!r}")
        if p.positional != (sp.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD):
            raise TypeError(f"{where}: {p.name!r} positional={p.positional} disagrees with def")
        if sp.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
            raise TypeError(f"{where}: {p.name!r} must be a plain or keyword-only argument")
        has_default = sp.default is not inspect.Parameter.empty
        if p.required == has_default:
            raise TypeError(f"{where}: {p.name!r} required={p.required} disagrees with def")
        if has_default and sp.default != p.default:
            raise TypeError(f"{where}: {p.name!r} default {sp.default!r} != {p.default!r}")


def _call_error(name: str, params: tuple[Param, ...], kw: Mapping[str, Any], e: TypeError):
    names = [p.name for p in params]
    unknown = [k for k in kw if k not in names]
    if unknown:
        import difflib

        close = difflib.get_close_matches(unknown[0], names, n=1)
        hint = f"Did you mean {close[0]}=?" if close else f"Accepted: {', '.join(names)}."
        return ChipError(f"mintchip.{name}: unknown argument {unknown[0]!r}.", fix_hint=hint)
    usage = ", ".join(p.name for p in params if p.required)
    return ChipError(f"mintchip.{name}: {e}.", fix_hint=f"Call mintchip.{name}({usage}, ...).")


_HINTS = {
    "number": "a finite number, e.g. 0.82",
    "int": "a whole number, e.g. 10",
    "string": "a string",
    "bool": "True or False",
    "numbers": "a list of numbers (None for gaps), e.g. [0.9, 0.6, 0.4]",
    "range": "a (lo, hi) pair with lo <= hi, e.g. (0.05, 0.11)",
    "strings": 'a list of strings, e.g. ["a", "b"]',
    "values": 'a list of booleans, strings, numbers or None, e.g. [True, "warn", False]',
    "mapping": 'a dict or list of (name, number) pairs, e.g. {"fetch": 1.2, "solve": 4.8}',
}


def _fail(kind: str, p: Param | str, value: Any, why: str = "") -> ChipError:
    name, ptype = (p.name, p.type) if isinstance(p, Param) else (p, "range")
    got = repr(value)
    got = got if len(got) <= 40 else got[:37] + "..."
    msg = f"mintchip.{kind}: {name} must be {_HINTS[ptype].split(', e.g.')[0]}"
    msg += f"; {why}." if why else f"; got {got} ({type(value).__name__})."
    return ChipError(msg, fix_hint=f"Pass {name}= {_HINTS[ptype]}.")


def _number(kind: str, p: Param | str, v: Any, *, gaps: bool = False) -> float | None:
    if v is None and gaps:
        return None
    if isinstance(v, (bool, str, bytes)) or v is None:
        raise _fail(kind, p, v)
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise _fail(kind, p, v) from None
    if math.isnan(f) and gaps:
        return None
    if not math.isfinite(f):
        raise _fail(kind, p, v, f"got {v!r}")
    return f


def _items(kind: str, p: Param | str, v: Any) -> list[Any]:
    if isinstance(v, (str, bytes, Mapping)) or not isinstance(v, Iterable):
        raise _fail(kind, p, v)
    return list(v)


def _range(kind: str, p: Param | str, v: Any) -> tuple[float, float]:
    items = _items(kind, p, v)
    if len(items) != 2:
        raise _fail(kind, p, v, f"got {len(items)} values")
    lo, hi = (_number(kind, p, x) for x in items)
    if lo > hi:  # type: ignore[operator]
        raise _fail(kind, p, v, f"got lo {lo} > hi {hi}")
    return lo, hi  # type: ignore[return-value]


def _coerce(kind: str, p: Param, v: Any) -> Any:
    """Type-check and normalise one argument (None passes through as "not given")."""
    if v is None:
        if p.required:
            raise _fail(kind, p, v, "it is required")
        return None
    t = p.type
    if t == "number":
        return _number(kind, p, v)
    if t == "int":
        if isinstance(v, bool):
            raise _fail(kind, p, v)
        f = _number(kind, p, v)
        if not float(f).is_integer():  # type: ignore[arg-type]
            raise _fail(kind, p, v)
        return int(f)  # type: ignore[arg-type]
    if t == "string":
        if not isinstance(v, str):
            raise _fail(kind, p, v)
        if p.choices and v not in p.choices:
            raise _fail(kind, p, v, f"got {v!r}; choose one of {', '.join(p.choices)}")
        return v
    if t == "bool":
        if not (isinstance(v, bool) or type(v).__name__ == "bool_"):
            raise _fail(kind, p, v)
        return bool(v)
    if t == "numbers":
        return [_number(kind, p, x, gaps=True) for x in _items(kind, p, v)]
    if t == "range":
        lo, hi = _range(kind, p, v)
        if p.name == "domain" and not lo < hi:
            raise _fail(kind, p, v, f"got an empty domain ({lo}, {hi})")
        return lo, hi
    if t == "strings":
        items = _items(kind, p, v)
        if not all(isinstance(x, str) for x in items):
            raise _fail(kind, p, v)
        return items
    if t == "values":
        out: list[Any] = []
        for x in _items(kind, p, v):
            if x is None or isinstance(x, (bool, str)):
                out.append(x)
            else:
                out.append(_number(kind, p, x, gaps=True))
        return out
    if t == "mapping":
        pairs = list(v.items()) if isinstance(v, Mapping) else _items(kind, p, v)
        result: dict[str, Any] = {}
        for pair in pairs:
            if isinstance(pair, (str, bytes)) or not isinstance(pair, Iterable):
                raise _fail(kind, p, v)
            kv = list(pair)
            if len(kv) != 2 or not isinstance(kv[0], str) or kv[0] in result:
                raise _fail(kind, p, v, f"bad or repeated entry {pair!r}")
            val = kv[1]
            is_pair = isinstance(val, Iterable) and not isinstance(val, (str, bytes))
            result[kv[0]] = _range(kind, p, val) if is_pair else _number(kind, p, val)
        return result
    raise TypeError(f"unknown param type {t!r}")


def _jsonable(v: Any) -> Any:
    if isinstance(v, (tuple, list)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v
