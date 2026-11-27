"""One token grammar for the command line and for ``{{…}}`` directives in prose.

``mintchip spark 1.84 1.32 0.96 --band 0.38:0.48`` and ``{{spark 1.84 1.32 0.96 band=0.38:0.48}}``
are the same call. Bare tokens fill the kind's positional parameters in order; ``--name value``
and ``name=value`` set a parameter (either form works in both places); a ``name=value`` whose
name is not a parameter is an entry of the kind's mapping (``{{share code=62 docs=28}}``).
Values, by ``Param.type``:

- ``number``, ``int``: ``0.82``, ``-1e-3``; ``none`` passes None (e.g. no reference line).
- ``numbers``: numbers separated by spaces or commas; ``null`` or ``nan`` is a gap.
- ``range``: ``lo:hi``.
- ``mapping``: ``name=value`` tokens, ``name=start:end`` for spans; quote names with spaces.
- ``values``: ``pass warn fail skip``, ``true false null`` or numbers.
- ``strings``: comma-separated.
- ``bool``: ``--flag`` / ``--no-flag``, or ``flag=true`` / ``flag=false``.

Directives are tokenised with ``shlex``; a directive may also be a JSON object,
``{{ {"chip": "ci", "estimate": 0.08, "interval": [0.05, 0.11]} }}``. ``\\{{`` is a literal
``{{``. Everything outside directives passes through unchanged.
"""

from __future__ import annotations

import difflib
import html
import json
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .spec import REGISTRY, Chip, ChipError, Param, from_dict

__all__ = [
    "SYNTAX",
    "Directive",
    "DirectiveError",
    "call_text",
    "example_call",
    "find",
    "metavar",
    "parse_tokens",
    "render",
    "shared_domains",
    "spec_tokens",
]

LIST_TYPES = ("numbers", "strings", "values")
GAP = ("null", "none", "nan", "na")
TRUE = ("true", "yes")
FALSE = ("false", "no")

# Metavar and one-line description of each type's token syntax (CLI help, guide, errors).
SYNTAX: dict[str, tuple[str, str]] = {
    "number": ("N", "a number, e.g. 0.82 or -1e-3"),
    "int": ("N", "a whole number"),
    "string": ("TEXT", "text; quote it if it has spaces"),
    "bool": ("", "a flag"),
    "numbers": ("V…", "numbers separated by spaces or commas; null or nan is a gap"),
    "range": ("LO:HI", "two numbers joined by a colon, e.g. 0.05:0.11"),
    "strings": ("A,B,…", "comma-separated text"),
    "values": ("R…", "results: pass warn fail skip, true false null, or numbers"),
    "mapping": ("NAME=V…", "name=value tokens (name=start:end for spans); quote names with spaces"),
}
_GENERIC = {
    "number": "0.82",
    "int": "10",
    "string": "text",
    "numbers": "0.9 0.6 0.4",
    "range": "0.05:0.11",
    "strings": "a,b",
    "values": "pass fail",
    "mapping": "a=1",
}


# --- token grammar --------------------------------------------------------------------------
def parse_tokens(
    kind: str,
    tokens: Sequence[str],
    *,
    extra: Sequence[Param] = (),
    style: str = "cli",
    partial: bool = False,
) -> dict[str, Any]:
    """Turn tokens into constructor keyword arguments for ``kind`` (plus any ``extra`` params,
    such as the CLI's output flags). ``style`` ("cli" or "directive") only shapes the corrected
    form shown in errors; ``partial`` skips the check for required parameters. Raises
    ``ChipError`` naming ``mintchip.<kind>``."""
    return _Parser(kind, tokens, extra, style).parse(partial=partial)


def spec_tokens(
    kind: str, spec: Mapping[str, Any], *, style: str = "cli", omit: Sequence[str] = ()
) -> list[str]:
    """The tokens that ``parse_tokens`` turns back into ``spec`` (the inverse, for examples)."""
    toks: list[str] = []
    bare_ok = True
    for p in REGISTRY[kind].params:
        if p.name in omit or p.name not in spec or spec[p.name] is None:
            bare_ok = bare_ok and not p.positional
            continue
        v = spec[p.name]
        bare = p.positional and (bare_ok or p.type == "mapping")
        if bare or (p.type == "mapping" and style == "directive"):
            toks += _value_tokens(p, v)
        elif p.type == "bool":
            name = p.name.replace("_", "-")
            if style == "cli":
                toks.append(f"--{name}" if v else f"--no-{name}")
            else:
                toks.append(f"{p.name}={'true' if v else 'false'}")
        elif style == "cli":
            toks += [f"--{p.name.replace('_', '-')}", *_value_tokens(p, v)]
        else:
            toks.append(f"{p.name}={','.join(_value_tokens(p, v))}")
    return toks


def call_text(kind: str, tokens: Sequence[str], style: str = "cli") -> str:
    """``mintchip kind tok…`` or ``{{kind tok…}}``, quoted so it parses back to ``tokens``."""
    body = " ".join(_quote(t, style) for t in (kind, *tokens))
    return "{{" + body + "}}" if style == "directive" else f"mintchip {body}"


_SAFE = re.compile(r"[\w@%+=:,./\-\u2212]*", re.ASCII)


def _quote(tok: str, style: str) -> str:
    """Quote a token so the shell (cli) or shlex (directive) reads it back unchanged; a
    ``name=value`` token quotes each side, e.g. ``label="Val loss"``."""
    if tok and _SAFE.fullmatch(tok):
        return tok
    if "=" in tok and not tok.startswith("-"):
        name, _, val = tok.partition("=")
        return f"{_quote1(name, style)}={_quote1(val, style)}"
    return _quote1(tok, style)


def _quote1(s: str, style: str) -> str:
    if s and _SAFE.fullmatch(s):
        return s
    if style == "cli":
        return shlex.quote(s)
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def example_call(kind: str, style: str = "cli", omit: Sequence[str] = ()) -> str:
    """The kind's registered example as a ready-to-run command line or directive."""
    return call_text(kind, spec_tokens(kind, REGISTRY[kind].example, style=style, omit=omit), style)


def _num(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v
    f = float(v)
    return str(int(f)) if f.is_integer() and abs(f) < 1e15 else repr(f)


def _value_tokens(p: Param, v: Any) -> list[str]:
    t = p.type
    if t in ("numbers", "values"):
        return [_num(x) for x in v]
    if t == "range":
        return [f"{_num(v[0])}:{_num(v[1])}"]
    if t == "strings":
        return [",".join(v)]
    if t == "mapping":
        items = v.items() if isinstance(v, Mapping) else v
        out = []
        for name, x in items:
            is_span = isinstance(x, (list, tuple))
            out.append(f"{name}={_num(x[0])}:{_num(x[1])}" if is_span else f"{name}={_num(x)}")
        return out
    return [_num(v)]


def _float(s: str) -> float | None:
    try:
        return float(s.replace("−", "-"))
    except ValueError:
        return None


def _split(raw: Sequence[str]) -> list[str]:
    out: list[str] = []
    for tok in raw:
        out += [x.strip() for x in tok.strip("[]").split(",") if x.strip()]
    return out


def _norm(name: str) -> str:
    return name.strip().replace("-", "_").lower()


def _is_option(tok: str) -> bool:
    if tok.startswith("--"):
        return len(tok) > 2
    return len(tok) > 1 and tok[0] == "-" and tok[1].isalpha() and _float(tok) is None


class _Parser:
    def __init__(self, kind: str, tokens: Sequence[str], extra: Sequence[Param], style: str):
        if kind not in REGISTRY:
            raise _unknown_kind(kind, style)
        self.kind, self.style, self.toks = kind, style, list(tokens)
        params = (*REGISTRY[kind].params, *extra)
        self.params = {p.name: p for p in params}
        self.mapping = next((p for p in params if p.type == "mapping"), None)
        self.example = REGISTRY[kind].example
        self.text_tail: dict[str, tuple[Param, str]] = {}  # token after a text value -> option

    # -- messages ---------------------------------------------------------------------------
    def opt(self, p: Param) -> str:
        if self.style == "cli":
            return "--" + p.name.replace("_", "-")
        return p.name + "="

    def usage(self) -> str:
        parts = [self.kind]
        for p in REGISTRY[self.kind].params:
            if p.positional:
                meta = metavar(p)
                parts.append(meta if p.required else f"[{meta}]")
        tail = " [options]}}" if self.style == "directive" else " [--option value …]"
        return ("{{" if self.style == "directive" else "mintchip ") + " ".join(parts) + tail

    def fail(
        self,
        msg: str,
        fix: str | None = None,
        *,
        at: int | None = None,
        repl: Sequence[str] = (),
        span: int = 1,
    ) -> ChipError:
        """An error naming the kind; with ``at``, the fix shows the whole call with tokens
        ``at`` to ``at + span`` replaced by ``repl``."""
        hint = fix
        if at is not None:
            fixed = self.toks[:at] + list(repl) + self.toks[at + span :]
            call = call_text(self.kind, fixed, self.style)
            hint = f"{fix}: {call}" if fix else call
        return ChipError(f"mintchip.{self.kind}: {msg}", fix_hint=hint)

    def example_for(self, p: Param) -> str:
        if p.name in self.example and self.example[p.name] is not None:
            return " ".join(_value_tokens(p, self.example[p.name]))
        return _GENERIC.get(p.type, "")

    def type_fail(self, p: Param, got: str, at: int | None, why: str = "") -> ChipError:
        meta, desc = SYNTAX[p.type]
        got_s = got if len(got) <= 40 else got[:37] + "..."
        msg = why or f"{p.name} must be {desc}; got {got_s!r}."
        if self.style == "cli":
            fix = f"e.g. {self.opt(p)} {self.example_for(p)}"
        else:
            fix = f"e.g. {p.name}={self.example_for(p).replace(' ', ',')}"
        if p.positional:
            fix = f"e.g. {example_call(self.kind, self.style)}"
        if got in self.text_tail:
            opt, first = self.text_tail[got]
            both = _quote(f"{first} {got}", self.style)
            sep = "" if self.style == "directive" else " "
            return self.fail(msg, f"Quote text that has spaces: {self.opt(opt)}{sep}{both}")
        return self.fail(msg, f"Write {p.name} as {meta or 'a flag'}, {fix}.")

    # -- parsing ----------------------------------------------------------------------------
    def lookup(self, name: str, at: int) -> tuple[Param, bool]:
        key = _norm(name)
        if key in self.params:
            return self.params[key], False
        if key.startswith("no_") and key[3:] in self.params:
            p = self.params[key[3:]]
            if p.type == "bool":
                return p, True
            raise self.fail(f"--no-{name[3:]} only works for flags; {p.name} takes a value.")
        names = list(self.params)
        close = difflib.get_close_matches(key, names, n=1, cutoff=0.6)
        tok = self.toks[at]
        shown = f"--{name}" if tok.startswith("-") else f"{name}="
        listed = ", ".join(self.opt(self.params[n]).rstrip("=") for n in names)
        if not close:
            raise self.fail(f"unknown option {shown}.", f"Options: {listed}.")
        good = close[0].replace("_", "-") if tok.startswith("-") else close[0]
        raise self.fail(
            f"unknown option {shown}.",
            f"Use {self.opt(self.params[close[0]]).rstrip('=')}",
            at=at,
            repl=[tok.replace(name, good, 1)],
        )

    def set(self, kw: dict[str, Any], p: Param, value: Any) -> None:
        if p.name in kw:
            raise self.fail(f"{p.name} is given twice.", "Give each option once.")
        kw[p.name] = value

    def parse(self, *, partial: bool = False) -> dict[str, Any]:
        kw: dict[str, Any] = {}
        bare: list[tuple[int, str]] = []
        entries: list[tuple[int, str]] = []
        toks, i = self.toks, 0
        while i < len(toks):
            t = toks[i]
            if t == "--":
                bare += list(enumerate(toks[i + 1 :], i + 1))
                break
            if _is_option(t):
                name, eq, val = t.lstrip("-").partition("=")
                p, neg = self.lookup(name, i)
                if p.type == "bool":
                    if neg:
                        v = False
                    elif eq:
                        v = self.boolean(p, val, i)
                    elif i + 1 < len(toks) and toks[i + 1].lower() in TRUE + FALSE:
                        i += 1
                        v = self.boolean(p, toks[i], i)
                    else:
                        v = True
                elif eq:
                    v = (
                        self.mapping_value(p, [val], i)
                        if p.type == "mapping"
                        else (self.convert(p, [val], i))
                    )
                else:
                    multi = p.type in LIST_TYPES or p.type == "mapping"
                    j = i + 1
                    while j < len(toks) and not _is_option(toks[j]) and (multi or j == i + 1):
                        if multi and self.keyed(toks[j]):
                            break
                        j += 1
                    if j == i + 1:
                        meta, desc = SYNTAX[p.type]
                        raise self.fail(
                            f"{self.opt(p)} needs a value: {desc}.",
                            f"e.g. {self.opt(p)} {self.example_for(p)}.",
                        )
                    vals = toks[i + 1 : j]
                    if p.type == "string" and j < len(toks):
                        self.text_tail.setdefault(toks[j], (p, vals[0]))
                    v = (
                        self.mapping_value(p, vals, i)
                        if p.type == "mapping"
                        else (self.convert(p, vals, i + 1))
                    )
                    i = j - 1
                self.set(kw, p, v)
            elif "=" in t and not t.startswith("="):
                name, _, val = t.partition("=")
                if _norm(name) in self.params:
                    p = self.params[_norm(name)]
                    if p.type == "string" and i + 1 < len(toks):
                        self.text_tail.setdefault(toks[i + 1], (p, val))
                    if p.type == "bool":
                        v = self.boolean(p, val, i)
                    elif p.type == "mapping":
                        v = self.mapping_value(p, [val], i)
                    else:
                        v = self.convert(p, [val], i)
                    self.set(kw, p, v)
                elif self.mapping is not None:
                    entries.append((i, t))
                else:
                    self.lookup(name, i)  # raises with a suggestion
            else:
                bare.append((i, t))
            i += 1
        if entries:
            p = self.mapping
            assert p is not None
            v = self.mapping_value(p, [t for _, t in entries], entries[0][0])
            if p.name in kw:
                kw[p.name] = {**kw[p.name], **v}
            else:
                kw[p.name] = v
        self.fill_positionals(kw, bare)
        for p in self.params.values():
            if p.required and p.name not in kw and not partial:
                meta = metavar(p)
                raise self.fail(
                    f"missing {p.name} ({meta}: {SYNTAX[p.type][1]}).",
                    f"Usage: {self.usage()}, e.g. {example_call(self.kind, self.style)}",
                )
        return kw

    def keyed(self, tok: str) -> bool:
        return "=" in tok and _norm(tok.partition("=")[0]) in self.params

    def fill_positionals(self, kw: dict[str, Any], bare: list[tuple[int, str]]) -> None:
        open_ = [
            p for p in self.params.values()
            if p.positional and p.name not in kw and p.type != "mapping"
        ]  # fmt: skip
        k = 0
        for n, p in enumerate(open_):
            if k >= len(bare):
                break
            if p.type in LIST_TYPES:
                take = max(1, len(bare) - k - (len(open_) - n - 1))
                kw[p.name] = self.convert(p, [t for _, t in bare[k : k + take]], bare[k][0])
                k += take
            else:
                kw[p.name] = self.convert(p, [bare[k][1]], bare[k][0])
                k += 1
        if k < len(bare):
            extra = " ".join(t for _, t in bare[k:])
            takes = [metavar(p) for p in self.params.values() if p.positional]
            if not takes:
                msg = f"takes no bare values; got {extra!r}."
            else:
                msg = f"takes positional values {' '.join(takes)}; {extra!r} is left over."
            raise self.fail(msg, f"Usage: {self.usage()}. Put options after the values.")

    # -- conversion -------------------------------------------------------------------------
    def boolean(self, p: Param, s: str, at: int) -> bool:
        low = s.strip().lower()
        if low in TRUE:
            return True
        if low in FALSE:
            return False
        raise self.fail(
            f"{p.name} is a flag; got {s!r}.",
            f"Write {_flag_forms(p, self.style)}.",
        )

    def number(self, p: Param, s: str, at: int, *, gaps: bool = False) -> float | None:
        if s.strip().lower() in GAP and (gaps or not p.required):
            return None
        f = _float(s)
        if f is not None:
            return f
        if s.endswith("%") and _float(s[:-1]) is not None:
            frac = _float(s[:-1]) / 100  # type: ignore[operator]
            raise self.fail(
                f"{p.name} must be a plain number; got {s!r}.",
                f"Drop the % sign: write {frac:g} for {s} (or the count, with its total).",
            )
        raise self.type_fail(p, s, at)

    def convert(self, p: Param, raw: Sequence[str], at: int) -> Any:
        t = p.type
        if t in ("number", "int"):
            if len(raw) != 1:
                raise self.type_fail(p, " ".join(raw), at)
            f = self.number(p, raw[0], at)
            if t == "int" and f is not None:
                if not f.is_integer():
                    raise self.type_fail(p, raw[0], at, f"{p.name} must be a whole number; got "
                                         f"{raw[0]!r}.")  # fmt: skip
                return int(f)
            return f
        if t == "string":
            return raw[0] if len(raw) == 1 else " ".join(raw)
        if t == "bool":
            return self.boolean(p, raw[0], at)
        if t == "numbers":
            return [self.number(p, x, at, gaps=True) for x in _split(raw)]
        if t == "range":
            return self.range(p, " ".join(raw), at)
        if t == "strings":
            return _split(raw)
        if t == "values":
            out: list[Any] = []
            for x in _split(raw):
                low = x.lower()
                if low in TRUE + FALSE:
                    out.append(low in TRUE)
                elif low in GAP:
                    out.append(None)
                elif _float(x) is not None:
                    out.append(_float(x))
                else:
                    out.append(x)
            return out
        raise TypeError(f"unknown param type {t!r}")

    def range(self, p: Param, s: str, at: int) -> tuple[float, float] | None:
        if s.strip().lower() in GAP and not p.required:
            return None
        parts = s.split(":") if ":" in s else s.strip("()[]").split(",")
        nums = [_float(x.strip().strip("()[]")) for x in parts]
        if len(nums) == 2 and None not in nums:
            lo, hi = nums
            if lo > hi:  # type: ignore[operator]
                good = f"{_num(hi)}:{_num(lo)}"
                raise self.fix(
                    f"{p.name} must have lo <= hi; got {s!r}.", "Swap the ends", at, s, good
                )
            return lo, hi  # type: ignore[return-value]
        nxt = self.toks[at + 1] if 0 <= at < len(self.toks) - 1 else None
        if len(nums) == 1 and nums[0] is not None and nxt is not None and _float(nxt) is not None:
            good = f"{s}:{nxt}"
            raise self.fail(
                f"{p.name} must be one lo:hi token; got {s!r} then {nxt!r}.",
                "Join the ends with a colon",
                at=at,
                repl=[self.toks[at].replace(s, good, 1)],
                span=2,
            )
        m = re.fullmatch(r"\s*(-?[\d.eE+]+)\s*(?:-|\.\.|to)\s*(-?[\d.eE+]+)\s*", s)
        if m and _float(m[1]) is not None and _float(m[2]) is not None:
            good = f"{m[1]}:{m[2]}"
            raise self.fix(
                f"{p.name} must be lo:hi with a colon; got {s!r}.", "Use a colon", at, s, good
            )
        raise self.type_fail(p, s, at)

    def fix(self, msg: str, how: str, at: int, old: str, new: str) -> ChipError:
        """An error whose fix replaces ``old`` with ``new`` in the token at (or after) ``at``."""
        for n in range(max(at, 0), len(self.toks)):
            if old in self.toks[n]:
                return self.fail(msg, how, at=n, repl=[self.toks[n].replace(old, new, 1)])
        return self.fail(msg, f"{how}: {new}.")

    def mapping_value(self, p: Param, raw: Sequence[str], at: int) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for tok in raw:
            name, eq, val = tok.partition("=")
            if not eq or not name.strip():
                raise self.fail(
                    f"{p.name} entries must be name=value; got {tok!r}.",
                    f"e.g. {' '.join(_value_tokens(p, self.example[p.name]))}"
                    if p.name in self.example
                    else None,
                )
            name = name.strip()
            if name in out:
                raise self.fail(f"{p.name} has {name!r} twice.", "Give each name once.")
            if ":" in val:
                out[name] = self.range(p, val, at)
            else:
                f = _float(val)
                if f is None:
                    raise self.fail(
                        f"{p.name}: {name}={val!r} is not a number.",
                        "Write name=value, e.g. fetch=1.2 (or name=start:end for spans).",
                    )
                out[name] = f
        return out


def metavar(p: Param) -> str:
    meta = SYNTAX[p.type][0]
    if p.type in ("number", "int", "numbers", "values"):
        meta = p.name.upper() + ("…" if p.type in ("numbers", "values") else "")
    return meta


def _flag_forms(p: Param, style: str) -> str:
    dashed = p.name.replace("_", "-")
    if style == "cli":
        return f"--{dashed} or --no-{dashed}"
    return f"{p.name}=true or {p.name}=false"


def _unknown_kind(kind: str, style: str) -> ChipError:
    names = sorted(REGISTRY)
    close = difflib.get_close_matches(kind, names, n=1)
    hint = f"Did you mean {close[0]!r}? " if close else ""
    return ChipError(
        f"mintchip: unknown chip {kind!r}.", fix_hint=f"{hint}Chips: {', '.join(names)}."
    )


# --- directives in prose --------------------------------------------------------------------
@dataclass
class Directive:
    """One ``{{…}}`` in a document: where it is, its source text and the chip it makes."""

    start: int
    end: int
    line: int
    col: int
    source: str
    chip: Chip | None = None
    domain: tuple[float, float] | None = field(default=None)

    @property
    def where(self) -> str:
        src = self.source if len(self.source) <= 48 else self.source[:45] + "...}}"
        return f"line {self.line}, column {self.col}: {src}"


class DirectiveError(ChipError):
    """Malformed directives; ``errors`` holds one ``(where, ChipError)`` pair per directive."""

    def __init__(self, errors: list[tuple[str, ChipError]]) -> None:
        self.errors = errors
        first_where, first = errors[0]
        more = f" (and {len(errors) - 1} more)" if len(errors) > 1 else ""
        super().__init__(f"{first_where}: {first.message}{more}", fix_hint=first.fix_hint)


def _location(text: str, pos: int) -> tuple[int, int]:
    line = text.count("\n", 0, pos) + 1
    return line, pos - (text.rfind("\n", 0, pos) + 1) + 1


def find(text: str) -> tuple[list[str], list[Directive]]:
    """Split ``text`` into literal pieces and directives (``len(pieces) == len(directives)+1``),
    building each directive's chip. Raises ``DirectiveError`` listing every bad directive."""
    pieces: list[str] = []
    found: list[Directive] = []
    errors: list[tuple[str, ChipError]] = []
    buf, i = [], 0
    while True:
        j = text.find("{{", i)
        if j < 0:
            buf.append(text[i:])
            break
        if j > 0 and text[j - 1] == "\\":
            buf.append(text[i : j - 1] + "{{")
            i = j + 2
            continue
        buf.append(text[i:j])
        line, col = _location(text, j)
        end, body, err = _scan(text, j)
        d = Directive(j, end, line, col, text[j:end])
        if err is not None:
            errors.append((f"line {line}, column {col}: {d.source.splitlines()[0]}", err))
        else:
            try:
                d.chip = _build(body)
            except ChipError as e:
                errors.append((d.where, e))
        pieces.append("".join(buf))
        buf = []
        found.append(d)
        i = end
    pieces.append("".join(buf))
    if errors:
        raise DirectiveError(errors)
    return pieces, found


def _scan(text: str, j: int) -> tuple[int, str, ChipError | None]:
    """Find the end of the directive opening at ``j``: (end, body, error)."""
    k = j + 2
    while k < len(text) and text[k] in " \t":
        k += 1
    if k < len(text) and text[k] == "{":
        try:
            _, stop = json.JSONDecoder().raw_decode(text, k)
        except json.JSONDecodeError as e:
            line, col = _location(text, e.pos)
            return (
                _line_end(text, j),
                "",
                ChipError(
                    f"mintchip: bad JSON in directive at line {line}, column {col}: {e.msg}.",
                    fix_hint='Write {{ {"chip": "ci", "estimate": 0.08, "interval": [0.05, 0.11]} }}.',
                ),
            )
        m = re.compile(r"\s*\}\}").match(text, stop)
        if not m:
            return (
                _line_end(text, j),
                "",
                ChipError(
                    "mintchip: a JSON directive must end with }} right after the object.",
                    fix_hint="Close it: {{ {...} }}.",
                ),
            )
        return m.end(), text[j + 2 : stop], None
    end = text.find("}}", j + 2)
    nl = text.find("\n", j + 2)
    if end < 0 or 0 <= nl < end:
        stop = _line_end(text, j)
        src = text[j:stop].rstrip()
        m = re.fullmatch(r"(.*?)([.,;:!?)]*)", src)
        src = f"{m[1]}}}}}{m[2]}" if m else src + "}}"
        return (
            stop,
            "",
            ChipError(
                "mintchip: directive is not closed with }} on the same line.",
                fix_hint=f"Close it: {src} (For literal braces write \\{{{{.)",
            ),
        )
    return end + 2, text[j + 2 : end], None


def _line_end(text: str, j: int) -> int:
    nl = text.find("\n", j)
    return len(text) if nl < 0 else nl


def _build(body: str) -> Chip:
    s = body.strip()
    if s.startswith("{"):
        return from_dict(json.loads(s))
    try:
        toks = shlex.split(s)
    except ValueError as e:
        raise ChipError(
            f"mintchip: cannot split the directive into tokens ({e}).",
            fix_hint="Close the quote, or drop a stray apostrophe (write it inside double quotes).",
        ) from None
    if not toks:
        raise ChipError(
            "mintchip: empty directive.", fix_hint="Write {{kind values…}}, e.g. {{spark 3 1 2}}."
        )
    kind, *rest = toks
    if kind not in REGISTRY:
        err = _unknown_kind(kind, "directive")
        close = difflib.get_close_matches(kind, sorted(REGISTRY), n=1)
        if close:
            err = ChipError(err.message, fix_hint=f"Write {call_text(close[0], rest, 'directive')}")
        raise err
    return REGISTRY[kind].fn(**parse_tokens(kind, rest, style="directive"))


def shared_domains(chips: Sequence[Chip]) -> list[tuple[float, float] | None]:
    """The domain each chip gets under ``format_prose``'s ``share="auto"`` rule: chips of one
    kind with the same non-empty unit are read on one scale."""
    from .prose import shared_domains as share

    names = [f"c{n}" for n in range(len(chips))]
    domains = share(dict(zip(names, chips, strict=True)))
    return [domains.get(n) for n in names]


def render(
    text: str,
    *,
    format: str = "text",
    ascii: bool = False,
    compact: bool = False,
    title: str = "mintchip",
    theme: str = "auto",
    fragment: bool = False,
) -> tuple[str, list[Directive]]:
    """Replace every directive in ``text`` with its chip. Formats: ``text``, ``ansi``, ``md``
    (code spans), ``html`` (a full page via ``mintchip.document``, or embeddable ``<p>``
    blocks when ``fragment=True``). Returns the output and the directives (each with its
    ``chip``), so callers can report warnings by location."""
    if format not in ("text", "ansi", "md", "html"):
        raise ChipError(
            f"mintchip render: unknown format {format!r}.", fix_hint="Use text, ansi, md or html."
        )
    pieces, found = find(text)
    for d, dom in zip(found, shared_domains([d.chip for d in found]), strict=True):  # type: ignore[misc]
        d.domain = dom
    if format == "html":
        return _html_page(pieces, found, title=title, theme=theme, fragment=fragment), found
    out = [pieces[0]]
    for d, piece in zip(found, pieces[1:], strict=True):
        c = d.chip
        assert c is not None
        s = c.text(ascii=ascii, compact=compact, color=format == "ansi", domain=d.domain)
        if format == "md":
            s = f"`` {s} ``" if "`" in s else f"`{s}`"
        out += [s, piece]
    return "".join(out), found


def _html_page(
    pieces: list[str],
    found: list[Directive],
    *,
    title: str,
    theme: str,
    fragment: bool = False,
) -> str:
    import mintchip

    parts = [html.escape(pieces[0])]
    for d, piece in zip(found, pieces[1:], strict=True):
        assert d.chip is not None
        parts += [d.chip.html(theme=theme, domain=d.domain), html.escape(piece)]
    body = "".join(parts)
    blocks = [f"<p>{b.strip()}</p>" for b in re.split(r"\n[ \t]*\n", body) if b.strip()]
    if fragment:
        return "\n".join(blocks)
    return mintchip.document(title, blocks, theme=theme)
