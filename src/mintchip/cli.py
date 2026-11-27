"""Command line, generated from the chip registry.

``mintchip <kind> …`` for every registered kind, plus ``render`` (prose with ``{{…}}``
directives), ``table``, ``guide``, ``schema`` and ``catalog``. stdout carries only the result;
warnings go to stderr as ``mintchip: warning: …`` (exit 1 under ``--strict``), and errors as
``mintchip: error: …`` with a ``fix:`` line (exit 2).
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import mintchip as mc

from .directives import (
    SYNTAX,
    DirectiveError,
    call_text,
    example_call,
    metavar,
    parse_tokens,
)
from .spec import REGISTRY, Chip, ChipError, Param

FORMATS = ("text", "ansi", "md", "svg", "html", "json")
OUTPUT = (
    Param(
        "format",
        "string",
        "Choose the output: text (default), ansi (colour), md (or markdown), svg, html or json.",
        default="text",
        choices=FORMATS,
    ),
    Param("ascii", "bool", "Print pure ASCII.", default=False),
    Param("compact", "bool", "Shorten the value for use mid-sentence.", default=False),
    Param("strict", "bool", "Exit 1 if the chip has warnings.", default=False),
    Param("out", "string", "Write output to FILE instead of stdout."),
)
COMMANDS = ("render", "table", "from", "diff", "guide", "skill", "doctor", "schema", "catalog")
TABLE_EXAMPLE = "mintchip table results.json --col model --col acc:bar --col lift:ci --sort acc"


# --- output helpers -------------------------------------------------------------------------
def _out(text: str) -> None:
    """Write to stdout, newline-terminated, without newline translation where possible."""
    if not text.endswith("\n"):
        text += "\n"
    _write_raw(text)


def _write_raw(text: str) -> None:
    buf = getattr(sys.stdout, "buffer", None)
    if buf is None:
        sys.stdout.write(text)
        return
    sys.stdout.flush()
    buf.write(text.encode("utf-8", "surrogateescape"))
    buf.flush()


def _err(line: str) -> None:
    print(line, file=sys.stderr)


def _error(e: ChipError, example: str | None = None) -> int:
    errors = e.errors if isinstance(e, DirectiveError) else [(None, e)]
    for where, err in errors:
        msg = err.message
        msg = re.sub(r"^mintchip(: |\.| )", "", msg)
        _err(f"mintchip: error: {where}: {msg}" if where else f"mintchip: error: {msg}")
        if err.fix_hint:
            _err(f"  fix: {err.fix_hint}")
    hint = errors[-1][1].fix_hint or ""
    if example and "mintchip " not in hint:
        _err(f"  example: {example}")
    return 2


def _warn(warnings: Iterable[str], strict: bool) -> int:
    warnings = list(warnings)
    for w in warnings:
        _err(f"mintchip: warning: {w}")
    return 1 if strict and warnings else 0


def _code_span(s: str) -> str:
    return f"`` {s} ``" if "`" in s else f"`{s}`"


def _write_output(text: str, out_path: str | None = None, *, raw: bool = False) -> None:
    """Write output to ``out_path`` (UTF-8) or stdout."""
    if out_path is None:
        if raw:
            _write_raw(text)
        else:
            _out(text)
        return
    dest = Path(out_path)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = text if (raw or text.endswith("\n")) else text + "\n"
        dest.write_text(content, encoding="utf-8")
    except OSError as e:
        raise ChipError(
            f"mintchip: cannot write {out_path!r}: {e.strerror}.",
            fix_hint="Check the output path and directory permissions.",
        ) from None


def _read(path: str) -> str:
    """Read a file or stdin (``-``) as text, keeping line endings and undecodable bytes."""
    try:
        if path == "-":
            isatty_fn = getattr(sys.stdin, "isatty", None)
            if callable(isatty_fn) and isatty_fn():
                raise ChipError(
                    "mintchip: no input piped to stdin.",
                    fix_hint="Pipe input into stdin (e.g. `cat data.json | mintchip table`) or pass a file path.",
                )
            buf = getattr(sys.stdin, "buffer", None)
            data = buf.read() if buf is not None else sys.stdin.read().encode()
        else:
            data = Path(path).read_bytes()
    except OSError as e:
        raise ChipError(
            f"mintchip: cannot read {path!r}: {e.strerror}.",
            fix_hint="Pass an existing file, or - to read stdin.",
        ) from None
    return data.decode("utf-8", "surrogateescape")


# --- kind commands --------------------------------------------------------------------------
def chip_output(c: Chip, *, format: str = "text", ascii: bool = False, compact: bool = False):
    """The text a kind command prints for ``c`` in ``format``."""
    fmt_name = _normalize_format(format, FORMATS)
    if fmt_name == "text":
        return c.text(ascii=ascii, compact=compact)
    if fmt_name == "ansi":
        return c.text(ascii=ascii, compact=compact, color=True)
    if fmt_name == "md":
        return _code_span(c.text(ascii=ascii, compact=compact))
    if fmt_name == "svg":
        svg = c.svg(standalone=True)
        if not svg:
            raise ChipError(
                f"mintchip.{c.kind} has no graphic.", fix_hint="Use --format text, md or html."
            )
        return svg
    if fmt_name == "html":
        return c.html()
    if fmt_name == "json":
        return json.dumps({**c.summary(), "spec": c.to_dict()}, indent=2, ensure_ascii=ascii)
    raise _bad_format(format, FORMATS)


def _normalize_format(fmt: str, allowed: Sequence[str]) -> str:
    norm = "md" if fmt == "markdown" and "md" in allowed else fmt
    if norm not in allowed:
        raise _bad_format(fmt, allowed)
    return norm


def _bad_format(fmt: str, allowed: Sequence[str]) -> ChipError:
    close = difflib.get_close_matches(fmt, allowed, n=1, cutoff=0.5)
    alias = "md" if fmt == "gfm" and "md" in allowed else None
    best = alias or (close[0] if close else None)
    hint = f"Use --format {best}." if best else f"Use one of: {', '.join(allowed)}."
    return ChipError(f"mintchip: unknown format {fmt!r}.", fix_hint=hint)


def _cmd_kind(kind: str, tokens: Sequence[str]) -> int:
    example = example_call(kind)
    norm_tokens: list[str] = []
    after_sep = False
    for tok in tokens:
        if tok == "--":
            after_sep = True
            norm_tokens.append(tok)
        elif not after_sep and tok == "-o":
            norm_tokens.append("--out")
        elif not after_sep and tok.startswith("-o="):
            norm_tokens.append("--out=" + tok[3:])
        else:
            norm_tokens.append(tok)
    try:
        kw = parse_tokens(kind, norm_tokens, extra=OUTPUT, style="cli")
        opts = {p.name: kw.pop(p.name, p.default) for p in OUTPUT}
        fmt_name = _normalize_format(opts["format"], FORMATS)
        c = REGISTRY[kind].fn(**kw)
        text = chip_output(c, format=fmt_name, ascii=opts["ascii"], compact=opts["compact"])
        _write_output(text, opts["out"])
    except ChipError as e:
        return _error(e, example)
    return _warn(c.warnings, opts["strict"])


# --- render ---------------------------------------------------------------------------------
def _cmd_render(args: argparse.Namespace) -> int:
    from . import directives

    try:
        fmt_name = _normalize_format(args.format, ("text", "ansi", "md", "html"))
        text = _read(args.file)
        title = args.title or (Path(args.file).stem if args.file != "-" else "mintchip")
        out, found = directives.render(
            text,
            format=fmt_name,
            ascii=args.ascii,
            compact=args.compact,
            title=title,
            fragment=args.fragment,
        )
        _write_output(out, args.out, raw=(fmt_name != "html"))
    except ChipError as e:
        return _error(e)
    warnings = [
        f"{d.where}: {w}" for d in found for w in (d.chip.warnings_for(d.domain) if d.chip else ())
    ]
    code = _warn(warnings, args.strict)
    if args.check:
        notes = _lint(text, found)
        for n in notes:
            _err(f"mintchip: check: {n}")
        if notes and args.strict:
            code = 1
    return code


def _lint(text: str, found: list[Any]) -> list[str]:
    """Density checks from ``mintchip.lint``, with each directive standing in as a
    placeholder; chips' own warnings are left out (they were already printed). A crowded
    sentence is quoted as written, its directives' locations after the quote."""
    chips: dict[str, Chip] = {}
    shown: dict[str, str] = {}
    written: dict[str, tuple[str, str]] = {}
    parts, pos = [], 0
    for n, d in enumerate(found):
        name = f"d{n}"
        chips[name] = d.chip
        shown["{" + name + "}"] = f"{{{{{d.chip.kind}}}}} at {d.line}:{d.col}"
        written[name] = (d.source, f"{d.line}:{d.col}")
        parts += [text[pos : d.start], "{" + name + "}"]
        pos = d.end
    parts.append(text[pos:])
    notes = []
    for m in mc.lint("".join(parts), chips, written=written):
        if any(m.startswith(f"{slot}: ") for slot in shown):
            continue
        for slot, label in shown.items():
            m = m.replace(slot, label)
        notes.append(m)
    return notes


# --- table ----------------------------------------------------------------------------------
def table_columns(cols: Sequence[str], sets: Sequence[str]) -> dict[str, Any] | None:
    """Columns for ``mintchip.table`` from ``--col key[:kind[:header]]`` and
    ``--set key.option=value`` arguments."""
    if not cols:
        if sets:
            raise ChipError(
                "mintchip table: --set needs the column listed with --col.",
                fix_hint=f"e.g. {TABLE_EXAMPLE} --set acc.target=0.9",
            )
        return None
    columns: dict[str, dict[str, Any]] = {}
    for spec in cols:
        key, _, rest = spec.partition(":")
        kind, _, header = rest.partition(":")
        kind = kind.strip()
        if not key:
            raise ChipError(
                f"mintchip table: --col {spec!r} has no key.", fix_hint="Write --col KEY:KIND."
            )
        if kind and kind != "text" and kind not in REGISTRY:
            names = ["text", *REGISTRY]
            close = difflib.get_close_matches(kind, names, n=1)
            hint = f"Did you mean --col {key}:{close[0]}? " if close else ""
            raise ChipError(
                f"mintchip table: unknown column kind {kind!r} in --col {spec!r}.",
                fix_hint=f"{hint}Kinds: {', '.join(names)}.",
            )
        columns[key] = {
            **({"chip": kind} if kind else {}),
            **({"header": header} if header else {}),
        }
    for s in sets:
        lhs, eq, value = s.partition("=")
        key, dot, opt = lhs.rpartition(".")
        if not (eq and dot and key and opt):
            raise ChipError(
                f"mintchip table: --set {s!r} must be KEY.OPTION=VALUE.",
                fix_hint="e.g. --set acc.target=0.9",
            )
        if key not in columns:
            raise ChipError(
                f"mintchip table: --set {s!r} names column {key!r}, which has no --col.",
                fix_hint=f"Add --col {key}:KIND first. Columns: {', '.join(columns)}.",
            )
        kind = columns[key].get("chip")
        if opt == "header":
            columns[key]["header"] = value
        elif opt == "share":
            columns[key]["share"] = value.lower() not in ("false", "no", "0")
        elif kind in (None, "text"):
            raise ChipError(
                f"mintchip table: column {key!r} has no chip kind, so only header can be set.",
                fix_hint=f"Give it a kind, e.g. --col {key}:bar.",
            )
        else:
            names = [p.name for p in REGISTRY[kind].params]
            if opt.replace("-", "_") not in names:
                close = difflib.get_close_matches(opt, names, n=1)
                hint = f"Did you mean --set {key}.{close[0]}=…? " if close else ""
                raise ChipError(
                    f"mintchip table: {kind} has no option {opt!r} (in --set {s!r}).",
                    fix_hint=f"{hint}Options: {', '.join([*names, 'header', 'share'])}.",
                )
            columns[key].update(parse_tokens(kind, [f"{opt}={value}"], partial=True))
    return {k: (v["chip"] if list(v) == ["chip"] else v) for k, v in columns.items()}


def _table_rows(path: str) -> Any:
    """A path ``mintchip.table`` can read, or rows parsed from stdin (JSON, JSONL, CSV or TSV)."""
    if path != "-":
        if not Path(path).is_file():
            raise ChipError(
                f"mintchip table: no such file {path!r}.",
                fix_hint="Pass a .json, .jsonl, .csv or .tsv file, or - for stdin.",
            )
        return path
    text = _read("-")
    stripped = text.lstrip()
    if stripped[:1] in ("[", "{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if stripped[:1] == "{" and len(lines) > 1:
                try:
                    return [json.loads(ln) for ln in lines]
                except json.JSONDecodeError:
                    pass
            raise ChipError(
                f"mintchip table: stdin is not valid JSON (line {e.lineno}, column {e.colno}: "
                f"{e.msg}).",
                fix_hint='Pass a list of objects, e.g. [{"model": "a", "acc": 0.82}].',
            ) from None
    lines = text.splitlines()
    if lines and "\t" in lines[0] and "," not in lines[0]:
        return list(csv.DictReader(lines, delimiter="\t"))
    return list(csv.DictReader(lines))


def _cmd_table(args: argparse.Namespace) -> int:
    try:
        fmt_name = _normalize_format(args.format, ("text", "ansi", "md", "html", "json"))
        columns = table_columns(args.col, args.set)
        t = mc.table(
            _table_rows(args.file),
            columns,
            sort=args.sort,
            descending=False if args.asc else True if args.desc else None,
            limit=args.limit,
            title=args.title,
            highlight=args.highlight or None,
            baseline=args.baseline,
        )
        if fmt_name == "json":
            text = json.dumps(t.to_dict(), indent=2, ensure_ascii=args.ascii)
        elif fmt_name == "md":
            text = t.markdown(ascii=args.ascii)
        elif fmt_name == "html":
            if args.fragment:
                text = t.html()
            else:
                from .render import html as _html_mod

                text = _html_mod._shell(
                    t.title or "mintchip",
                    f'<div class="mc-wide">{t.html()}</div>',
                    None,
                )
        else:
            text = t.text(ascii=args.ascii, color=fmt_name == "ansi", width=args.width)
        _write_output(text, args.out)
    except ChipError as e:
        return _error(e, TABLE_EXAMPLE)
    return _warn(t.warnings, args.strict)


# --- schema ---------------------------------------------------------------------------------
_SCHEMA_TYPES: dict[str, dict[str, Any]] = {
    "number": {"type": "number"},
    "int": {"type": "integer"},
    "string": {"type": "string"},
    "bool": {"type": "boolean"},
    "numbers": {"type": "array", "items": {"type": ["number", "null"]}},
    "range": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
    "strings": {"type": "array", "items": {"type": "string"}},
    "values": {"type": "array", "items": {"type": ["boolean", "string", "number", "null"]}},
}
_PAIR = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
_SCHEMA_TYPES["mapping"] = {
    "type": "object",
    "additionalProperties": {"anyOf": [{"type": "number"}, _PAIR]},
}

DRAFT = "https://json-schema.org/draft/2020-12/schema"


def kind_schema(kind: str) -> dict[str, Any]:
    """JSON Schema for one kind's spec, ``{"chip": kind, **args}``."""
    k = REGISTRY[kind]
    props: dict[str, Any] = {"chip": {"const": kind}}
    for p in k.params:
        s = json.loads(json.dumps(_SCHEMA_TYPES[p.type]))
        if p.choices:
            s["enum"] = list(p.choices)
        if p.default is not None:
            s["default"] = p.default
            if not p.required:  # null overrides the default, e.g. no reference line
                t = s["type"]
                s["type"] = [t, "null"] if isinstance(t, str) else [*t, "null"]
        props[p.name] = {"description": p.help, **s}
    return {
        "title": f"mintchip {kind}",
        "description": f"{k.question} Use for: {k.have[0].lower()}{k.have[1:]}.",
        "type": "object",
        "properties": props,
        "required": ["chip", *(p.name for p in k.params if p.required)],
        "additionalProperties": False,
        "examples": [k.example_chip().to_dict()],
    }


def schema(kind: str | None = None) -> dict[str, Any]:
    """Draft 2020-12 JSON Schema for one kind, or a ``oneOf`` over all kinds on ``"chip"``."""
    if kind is not None:
        if kind not in REGISTRY:
            close = difflib.get_close_matches(kind, sorted(REGISTRY), n=1)
            hint = f"Did you mean {close[0]!r}? " if close else ""
            raise ChipError(
                f"mintchip schema: unknown chip {kind!r}.",
                fix_hint=f"{hint}Chips: {', '.join(e['name'] for e in mc.CATALOG)}.",
            )
        return {"$schema": DRAFT, "$id": f"mintchip:{kind}", **kind_schema(kind)}
    names = [e["name"] for e in mc.CATALOG]
    return {
        "$schema": DRAFT,
        "$id": "mintchip:chip",
        "title": "mintchip chip spec",
        "description": 'One chip as {"chip": kind, ...arguments}; "chip" picks the kind.',
        "type": "object",
        "required": ["chip"],
        "properties": {"chip": {"enum": names}},
        "oneOf": [{"$ref": f"#/$defs/{n}"} for n in names],
        "$defs": {n: kind_schema(n) for n in names},
    }


def _cmd_schema(args: argparse.Namespace) -> int:
    try:
        _out(json.dumps(schema(args.kind), indent=2, ensure_ascii=False))
    except ChipError as e:
        return _error(e)
    return 0


# --- catalog and guide ----------------------------------------------------------------------
def _cmd_catalog(args: argparse.Namespace) -> int:
    rows = []
    for entry in mc.CATALOG:
        example = mc.REGISTRY[entry["name"]].example_chip()
        rows.append({**entry, "spec": example.to_dict(), "text": example.text(ascii=args.ascii)})
    if args.json:
        _out(json.dumps(rows, indent=2, ensure_ascii=args.ascii))
        return 0
    width = max(len(r["name"]) for r in rows)
    lines = [f"mintchip {mc.__version__}: {len(rows)} chips", ""]
    for r in rows:
        lines.append(f"  {r['name']:<{width}}  {r['text']}")
        lines.append(f"  {'':<{width}}  {r['have']}: {r['question']}")
    _out("\n".join(lines))
    return 0


def _cmd_guide(args: argparse.Namespace) -> int:
    from . import guide

    if args.write:
        for path in guide.write(args.write):
            _out(str(path))
        return 0
    _out(guide.agents_snippet() if args.agents else guide.guide_text())
    return 0


# --- parser ---------------------------------------------------------------------------------
class _Help(argparse.RawDescriptionHelpFormatter):
    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=26, width=100)


def _pct(s: str) -> str:
    return s.replace("%", "%%")


def _param_help(p: Param) -> str:
    text = p.help
    if p.type in ("numbers", "range", "mapping", "values", "strings"):
        text += f" Syntax: {SYNTAX[p.type][1]}."
    if p.default is not None and p.type != "bool":
        default = int(p.default) if isinstance(p.default, float) and p.default.is_integer() else (
            p.default)  # fmt: skip
        text += f" Default: {default}."
    return _pct(text)


def _kind_parser(sub: Any, kind: str) -> None:
    k = REGISTRY[kind]
    positional = [p for p in k.params if p.positional]
    metas = [metavar(p) if p.required else f"[{metavar(p)}]" for p in positional]
    c = k.example_chip()
    epilog = (
        f"example:\n  $ {example_call(kind)}\n  {c.text()}\n\n"
        f"as a directive in `mintchip render`:\n  {example_call(kind, 'directive')}"
    )
    p = sub.add_parser(
        kind,
        help=_pct(k.question),
        usage=_pct(f"mintchip {kind} {' '.join(metas)} [--option value …]"),
        description=f"{k.question}\nUse it for: {k.have[0].lower()}{k.have[1:]}.",
        epilog=epilog,
        formatter_class=_Help,
    )
    for param in positional:
        p.add_argument(param.name, metavar=metavar(param), nargs="?", help=_param_help(param))
    for param in k.params:
        if param.positional:
            continue
        flag = "--" + param.name.replace("_", "-")
        if param.type == "bool":
            p.add_argument(flag, action=argparse.BooleanOptionalAction, help=_param_help(param))
        else:
            p.add_argument(flag, metavar=SYNTAX[param.type][0], help=_param_help(param))
    out = p.add_argument_group("output")
    for param in OUTPUT:
        flag = "--" + param.name
        if param.name == "out":
            out.add_argument("-o", flag, metavar="FILE", help=_pct(param.help))
        elif param.type == "bool":
            out.add_argument(flag, action="store_true", help=_pct(param.help))
        else:
            out.add_argument(flag, metavar="FORMAT", help=_pct(param.help))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mintchip",
        description="Word-sized graphics for numbers: one chip, a sentence, or a table.",
        epilog="Start with: mintchip guide",
        formatter_class=_Help,
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"mintchip {mc.__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=False, metavar="COMMAND")

    p = sub.add_parser(
        "render",
        help="Replace {{kind …}} directives in prose with chips.",
        description=(
            "Read prose from FILE (or stdin) and replace each {{kind tokens…}} directive with\n"
            "its chip. Directives use the same tokens as the kind commands, with options as\n"
            "name=value: {{spark 1.84 1.32 0.96 band=0.38:0.48}} is\n"
            "`mintchip spark 1.84 1.32 0.96 --band 0.38:0.48`. A directive may also be a JSON\n"
            'spec: {{ {"chip": "ci", "estimate": 0.08, "interval": [0.05, 0.11]} }}.\n'
            "Text outside directives is copied unchanged; write \\{{ for a literal {{."
        ),
        formatter_class=_Help,
    )
    p.add_argument("file", nargs="?", default="-", metavar="FILE", help="Prose file; - is stdin.")
    p.add_argument("--format", default="text",
                   help="text (default), ansi, md (or markdown) or html (a full page).")  # fmt: skip
    p.add_argument("--ascii", action="store_true", help="Pure ASCII chips.")
    p.add_argument("--compact", action="store_true", help="Shorter chip values.")
    p.add_argument("--strict", action="store_true", help="Exit 1 on any warning.")
    p.add_argument("--check", action="store_true", help="Also lint density to stderr.")
    p.add_argument("--title", help="Page title for --format html.")
    p.add_argument("--fragment", action="store_true",
                   help="Emit embeddable HTML without the page shell (for --format html).")  # fmt: skip
    p.add_argument("-o", "--out", metavar="FILE", help="Write output to FILE instead of stdout.")
    p.set_defaults(func=_cmd_render, _parser=p)

    p = sub.add_parser(
        "table",
        help="Render rows from a JSON, JSONL, CSV or TSV file as a table with shared scales.",
        description=(
            "Rows come from a .json (list of objects), .jsonl, .csv or .tsv file, or stdin (-).\n"
            "Each --col KEY[:KIND[:HEADER]] adds a column in order; KIND is a chip kind or\n"
            "text, inferred from the values if left out. A cell is a number, a list for the\n"
            "kind's values (ci takes [estimate, low, high]) or an object of arguments. Every\n"
            "chip column shares one scale. --set KEY.OPTION=VALUE applies an option to every\n"
            "cell in a column."
        ),
        epilog=f"example:\n  $ {TABLE_EXAMPLE} --set acc.target=0.9",
        formatter_class=_Help,
    )
    p.add_argument(
        "file",
        nargs="?",
        default="-",
        metavar="FILE",
        help="A .json, .jsonl, .csv or .tsv file; - (default) is stdin.",
    )
    p.add_argument("--col", action="append", default=[], metavar="KEY[:KIND[:HEADER]]",
                   help="Add a column; repeat in display order. No --col: every key.")  # fmt: skip
    p.add_argument("--set", action="append", default=[], metavar="KEY.OPTION=VALUE",
                   help="Apply a chip option to a whole column, e.g. acc.target=0.9.")  # fmt: skip
    p.add_argument(
        "--sort", metavar="KEY", help="Sort by this column (largest first; text A to Z)."
    )
    order = p.add_mutually_exclusive_group()
    order.add_argument("--asc", action="store_true", help="Sort smallest first (A to Z for text).")
    order.add_argument("--desc", action="store_true", help="Sort largest first (Z to A for text).")
    p.add_argument("--limit", type=int, metavar="N", help="Keep the first N rows after sorting.")
    p.add_argument("--title", help="A title above the table.")
    p.add_argument("--highlight", action="append", default=[], metavar="ROW",
                   help="Emphasise a row matching ROW in the first text column (repeatable).")  # fmt: skip
    p.add_argument("--baseline", metavar="ROW",
                   help="Mark a row matching ROW as the baseline.")  # fmt: skip
    p.add_argument("--width", type=int, default=80, metavar="N",
                   help="Target width for text output (default: 80).")  # fmt: skip
    p.add_argument("--format", default="text",
                   help="text (default), ansi, md (or markdown), html or json.")  # fmt: skip
    p.add_argument("--fragment", action="store_true",
                   help="Emit bare HTML without the page shell (for --format html).")  # fmt: skip
    p.add_argument("-o", "--out", metavar="FILE", help="Write output to FILE instead of stdout.")
    p.add_argument("--ascii", action="store_true", help="Pure ASCII.")
    p.add_argument("--strict", action="store_true", help="Exit 1 on any warning.")
    p.set_defaults(func=_cmd_table, _parser=p)

    p = sub.add_parser("guide", help="Print the agent guide (start here).", formatter_class=_Help)
    p.add_argument("--agents", action="store_true",
                   help="Print a short snippet to paste into AGENTS.md or CLAUDE.md.")  # fmt: skip
    p.add_argument("--write", metavar="DIR",
                   help="Write DIR/skills/mintchip/SKILL.md and DIR/llms.txt.")  # fmt: skip
    p.set_defaults(func=_cmd_guide, _parser=p)

    p = sub.add_parser("schema", help="Print JSON Schema for chip specs.", formatter_class=_Help)
    p.add_argument("kind", nargs="?", metavar="KIND", help="One kind; default: all, as oneOf.")
    p.set_defaults(func=_cmd_schema, _parser=p)

    p = sub.add_parser("catalog", help="List every chip with its example rendered as text.")
    p.add_argument("--ascii", action="store_true", help="Print pure ASCII.")
    p.add_argument("--json", action="store_true", help="Print the catalog as JSON.")
    p.set_defaults(func=_cmd_catalog, _parser=p)

    from . import diff as _diff
    from . import doctor as _doctor
    from . import skill as _skill
    from .ingest import add_from_parser as _add_from_parser

    _add_from_parser(sub, _Help)
    _diff.add_diff_parser(sub, _Help)
    _skill.add_skill_parser(sub, _Help)
    _doctor.add_doctor_parser(sub, _Help)

    for entry in mc.CATALOG:
        _kind_parser(sub, entry["name"])
    return parser


def _wants_help(tokens: Sequence[str]) -> bool:
    for t in tokens:
        if t == "--":
            return False
        if t in ("-h", "--help"):
            return True
    return False


def _unknown_option(parser: argparse.ArgumentParser, extra: Sequence[str]) -> ChipError:
    options = sorted({s for a in parser._actions for s in a.option_strings if s.startswith("--")})
    bad = next((t for t in extra if t.startswith("-")), extra[0])
    close = difflib.get_close_matches(bad.split("=")[0], options, n=1)
    hint = f"Did you mean {close[0]}? " if close else ""
    if not bad.startswith("-"):
        return ChipError(
            f"mintchip: unexpected argument {bad!r}.", fix_hint=f"See {parser.prog} -h."
        )
    return ChipError(
        f"mintchip: unknown option {bad!r} for {parser.prog}.",
        fix_hint=f"{hint}Options: {', '.join(options)}.",
    )


def _main(argv: list[str]) -> int:
    if not argv:
        build_parser().print_help()
        return 0
    if argv and argv[0] in REGISTRY and not _wants_help(argv[1:]):
        return _cmd_kind(argv[0], argv[1:])
    if argv and not argv[0].startswith("-") and argv[0] not in (*COMMANDS, *REGISTRY):
        names = [*COMMANDS, *(e["name"] for e in mc.CATALOG)]
        close = difflib.get_close_matches(argv[0], names, n=1)
        hint = f"Did you mean {close[0]!r}? " if close else ""
        return _error(
            ChipError(
                f"mintchip: unknown command {argv[0]!r}.",
                fix_hint=f"{hint}Commands: {', '.join(names)}. Start with: mintchip guide",
            )
        )
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    if extra:
        return _error(_unknown_option(getattr(args, "_parser", parser), extra))
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return int(args.func(args))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit status (0 ok, 1 warnings under --strict,
    2 errors)."""
    try:
        return _main(list(sys.argv[1:] if argv is None else argv))
    except ChipError as e:
        return _error(e)
    except SystemExit as e:  # argparse --help and usage errors
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 2)
    except BrokenPipeError:
        return 0


def run(argv: Sequence[str], stdin: str | None = None) -> tuple[int, str, str]:
    """Run ``mintchip argv`` in-process with ``stdin`` text; returns (status, stdout, stderr).
    Used by the guide so its examples show real output."""
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    old_in = sys.stdin
    sys.stdin = io.StringIO(stdin or "")
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
    finally:
        sys.stdin = old_in
    return code, out.getvalue(), err.getvalue()


__all__ = ["build_parser", "call_text", "chip_output", "kind_schema", "main", "run", "schema"]

if __name__ == "__main__":
    sys.exit(main())
