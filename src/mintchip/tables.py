"""mintchip.table: several things compared on the same measures, as a table of small multiples.

Each chip column shares one scale: the union of its cells' domains is passed to every cell as
``domain=`` at render time, so a column of ``ci`` chips is a forest plot with one reference line
and a column of ``bar`` chips shares one zero. It shares one precision too: every value is
printed with the most decimal places any cell of the column uses on its own (``0.42``,
``0.90``, ``0.40``, not ``0.42``, ``0.9``, ``0.4``). Three renders: aligned monospace text, a GFM
table with the chips in code spans, and an HTML ``<table class="mc-table">``.

HTML classes (styled by ``mintchip.css()``): ``mc-table`` on the table; ``mc-text`` on text
cells and their headers; ``mc-chip`` on a chip column's header; ``mc-num`` on a chip column's
value cells (numbers, right-aligned); ``mc-graph`` on its graphic cells; ``mc-empty`` on an
empty cell; ``mc-scale`` on the header row holding a position column's two ends, which sit in
``mc-lo`` and ``mc-hi`` spans; ``mc-v`` on each value.
"""

from __future__ import annotations

import csv
import html as _html
import json
import math
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from . import fmt
from .render.text_base import to_ascii
from .spec import REGISTRY, Chip, ChipError, Kind, from_dict, sibling_domain

__all__ = ["Table", "table"]

WIDTH = 80  # the text render's target width
GAP = 2  # spaces between text columns
MIN_TEXT = 8  # a text column is never shortened below this
POSITION = frozenset({"ci", "dist", "gauge", "delta", "rank"})  # kinds drawn on a bracketed axis
EMPTY, EMPTY_ASCII = "—", "-"
FIGURE_SPACE = "\u2007"  # a digit-wide space, for decimal alignment in HTML

_HINT_ROWS = (
    'Pass a list of dicts, e.g. [{"model": "a", "acc": 0.82}], or a .json/.jsonl/.csv/.tsv path.'
)
_PLAIN_NUM = re.compile(r"^([+\-−]?\d[\d,]*)(\.\d+)?((?:e[+\-−]?\d+)?)$")
_NUMBER = re.compile(r"^[+\-−]?(\d+\.?\d*|\.\d+)([eE][+\-−]?\d+)?$")
_THOUSANDS = re.compile(r"^[+\-−]?\d{1,3}(,\d{3})+(\.\d+)?$")


@dataclass(frozen=True)
class _Column:
    key: str
    kind: str  # a registered chip kind, or "text"
    header: str
    share: bool = True
    options: Mapping[str, Any] = field(default_factory=dict)  # constructor kwargs for every cell

    def spec(self) -> dict[str, Any]:
        out: dict[str, Any] = {"chip": self.kind, "header": self.header}
        if not self.share:
            out["share"] = False
        return {**out, **_plain(dict(self.options))}


Cell = Chip | str | None


class Table:
    """A table of chips. Build one with ``mintchip.table(rows, columns, ...)``."""

    def __init__(
        self,
        columns: Sequence[_Column],
        rows: Sequence[Sequence[Cell]],
        *,
        index: Sequence[int] | None = None,
        sort: str | None = None,
        descending: bool | None = None,
        limit: int | None = None,
        title: str | None = None,
        highlight: Sequence[str] = (),
        baseline: str | None = None,
    ) -> None:
        self.columns = tuple(columns)
        self.rows = tuple(tuple(r) for r in rows)
        self.index = tuple(index) if index is not None else tuple(range(len(self.rows)))
        self.sort, self.descending, self.limit, self.title = sort, descending, limit, title
        self.highlight = tuple(highlight)
        self.baseline = baseline
        self.domains = tuple(self._shared_domain(j) for j in range(len(self.columns)))
        self.decimals = tuple(self._shared_decimals(j) for j in range(len(self.columns)))

    def _row_role(self, i: int) -> tuple[bool, bool]:
        """Return ``(is_highlight, is_baseline)`` for display row ``i``."""
        if not self.highlight and self.baseline is None:
            return False, False
        name_col = next((j for j, c in enumerate(self.columns) if c.kind == "text"), None)
        if name_col is None:
            return False, False
        cell = self.rows[i][name_col]
        if not isinstance(cell, str):
            return False, False
        return cell in self.highlight, cell == self.baseline

    def _shared_decimals(self, j: int) -> int | None:
        """The most decimal places a cell of chip column ``j`` prints its value with on its
        own, so the whole column can use it; None for kinds whose value is not a decimal, or
        when the column spans two or more orders of magnitude (so ``212`` beside ``1.92`` does
        not become ``212.00``)."""
        col = self.columns[j]
        if col.kind == "text":
            return None
        cells = [r[j] for r in self.rows if isinstance(r[j], Chip) and r[j].kind == col.kind]
        found = [d for c in cells if (d := c._text_out(False, True, None).decimals) is not None]
        if not found:
            return None
        mags = [abs(float(v)) for c in cells if (v := c.stats.get("value")) is not None and v != 0]
        if len(mags) >= 2 and max(mags) / min(mags) >= 100:
            return None
        return max(found)

    def _shared_domain(self, j: int) -> tuple[float, float] | None:
        col = self.columns[j]
        if col.kind == "text" or not col.share:
            return None
        cells = [r[j] for r in self.rows if isinstance(r[j], Chip) and r[j].kind == col.kind]
        return sibling_domain(col.kind, (_domain_of(c) for c in cells))

    def _domain_for(self, j: int, cell: Chip) -> tuple[float, float] | None:
        return self.domains[j] if cell.kind == self.columns[j].kind else None

    # --- warnings -----------------------------------------------------------------------------
    @cached_property
    def warnings(self) -> tuple[str, ...]:
        """Every cell's warnings, prefixed with its row and column, then any layout notes from
        the text render (a shortened column, a table wider than 80 characters)."""
        name_col = next((j for j, c in enumerate(self.columns) if c.kind == "text"), None)
        out = []
        for i, row in zip(self.index, self.rows, strict=True):
            who = f"row {i}"
            if name_col is not None and isinstance(row[name_col], str):
                who += f" ({row[name_col]})"
            for j, (col, cell) in enumerate(zip(self.columns, row, strict=True)):
                if isinstance(cell, Chip):
                    on = cell.warnings_for(self._domain_for(j, cell))
                    out += [f"{who}, column {col.key!r}: {w}" for w in on]
        return (*out, *self._layout(ascii=False, color=False)[1])

    # --- text ---------------------------------------------------------------------------------
    def text(self, *, ascii: bool = False, color: bool = False, width: int = WIDTH) -> str:
        """Aligned monospace: a header, one rule, one line per row; at most ``width`` characters
        wide where it can be (text columns are shortened first)."""
        if isinstance(width, bool) or not isinstance(width, int) or width < 1:
            raise ChipError(
                f"mintchip.Table.text: width must be a whole number of 1 or more; got {width!r}.",
                fix_hint="Pass width=80 or width=120.",
            )
        return self._layout(ascii=ascii, color=color, width=width)[0]

    def __str__(self) -> str:
        return self.text()

    def __repr__(self) -> str:
        return f"<Table {len(self.rows)} rows × {len(self.columns)} columns>"

    def _blocks(self, ascii: bool, color: bool) -> list[_Block]:
        return [
            self._text_block(j, ascii) if c.kind == "text" else self._chip_block(j, ascii, color)
            for j, c in enumerate(self.columns)
        ]

    def _text_block(self, j: int, ascii: bool) -> _Block:
        dash = EMPTY_ASCII if ascii else EMPTY
        cells = [dash if r[j] is None else _tx(str(r[j]), ascii) for r in self.rows]
        return _Block(_tx(self.columns[j].header, ascii), [(c, c) for c in cells], text=True)

    def _chip_block(self, j: int, ascii: bool, color: bool) -> _Block:
        col = self.columns[j]
        parts = [self._parts(j, r[j], ascii, color) for r in self.rows]
        values = _align([None if p is None else p[0] for p in parts], ascii)
        glyphs = _align_glyphs(col.kind, [("", "") if p is None else p[1:] for p in parts])
        gw = max((len(g) for g, _ in glyphs), default=0)
        rows = []
        for v, (g, rendered) in zip(values, glyphs, strict=True):
            if gw:
                rows.append((f"{v} {g.ljust(gw)}", f"{v} {rendered}{' ' * (gw - len(g))}"))
            else:
                rows.append((v, v))
        block = _Block(_tx(col.header, ascii), rows, right=not gw)
        if gw and self.domains[j] is not None and col.kind in POSITION:
            scale = self._scale(j, glyphs, ascii)
            if scale:
                vw = len(values[0]) if values else 0
                block.scale = " " * (vw + 1) + scale
        return block

    def _parts(self, j: int, cell: Cell, ascii: bool, color: bool) -> tuple[str, str, str] | None:
        """(compact value, plain glyph, rendered glyph) for one chip cell."""
        if not isinstance(cell, Chip):
            return None
        d = self._domain_for(j, cell)
        glyph = cell.text(value=False, ascii=ascii, domain=d)
        dec = self.decimals[j] if cell.kind == self.columns[j].kind else None
        value = cell.value(compact=True, ascii=ascii, decimals=dec)
        rendered = cell.text(value=False, ascii=ascii, color=True, domain=d) if color else glyph
        return value, glyph, rendered

    def _scale(self, j: int, glyphs: list[tuple[str, str]], ascii: bool) -> str:
        """The column's two ends (and a shared ci reference) placed over the bracketed axis."""
        col, (lo, hi) = self.columns[j], self.domains[j]  # type: ignore[misc]
        cells = [r[j] for r in self.rows if isinstance(r[j], Chip) and r[j].kind == col.kind]
        if not cells:
            return ""
        first = next(g for (g, _), r in zip(glyphs, self.rows, strict=True) if r[j] in cells)
        opened = _open(first)
        close = next((k for k in range(opened + 1, len(first)) if first[k] in "]>"), -1)
        if opened < 0 or close < 0:
            return ""
        flips = {bool(c.stats.get("higher_is_better") is False) for c in cells}
        if col.kind == "rank" and flips == {True}:
            lo, hi = hi, lo  # the rank axis runs best-right
        elif col.kind == "rank" and len(flips) > 1:
            return ""
        for sig in (2, 1):
            left = _tx(fmt.num(lo, sig=sig), ascii)
            right = _tx(fmt.num(hi, sig=sig, signed=lo < 0 < hi), ascii)
            if opened + len(left) < close + 1 - len(right):
                break
        start = max(close + 1 - len(right), opened + len(left) + 1)
        line = [" "] * max(start + len(right), len(first))
        line[opened : opened + len(left)] = left
        line[start : start + len(right)] = right
        refs = {c.stats.get("reference") for c in cells}
        if col.kind == "ci" and len(refs) == 1 and None not in refs:
            ref = float(refs.pop())  # type: ignore[arg-type]
            if min(lo, hi) < ref < max(lo, hi):
                n = close - opened - 1
                at = opened + 1 + round((ref - lo) / (hi - lo) * (n - 1))
                label = _tx(fmt.num(ref), ascii)
                a = at - (len(label) - 1) // 2
                if a > opened + len(left) and a + len(label) < start:
                    line[a : a + len(label)] = label
        return "".join(line).rstrip()

    def _layout(self, *, ascii: bool, color: bool, width: int = WIDTH) -> tuple[str, list[str]]:
        blocks = self._blocks(ascii, color)
        notes: list[str] = []
        roles = [self._row_role(i) for i in range(len(self.rows))]
        gutter = 2 if any(hi or base for hi, base in roles) else 0
        widths = [b.width for b in blocks]
        total = gutter + sum(widths) + GAP * (len(widths) - 1)
        if total > width:  # shorten text columns first, widest first
            texts = [k for k, b in enumerate(blocks) if b.text]
            while total > width:
                k = max(texts, key=lambda k: widths[k], default=None)
                if k is None or widths[k] <= MIN_TEXT:
                    break
                widths[k] -= 1
                total -= 1
            for k in texts:
                if widths[k] < blocks[k].width:
                    blocks[k].clip(widths[k], ascii)
                    notes.append(
                        f"text render: column {self.columns[k].key!r} shortened to "
                        f"{widths[k]} characters to fit {width} columns."
                    )
        if total > width:  # then headers wider than their column's content
            for k, b in enumerate(blocks):
                content = b.content_width
                if not b.text and len(b.header) > content and total > width:
                    cut = max(content, len(b.header) - (total - width))
                    b.header = _clip(b.header, cut, ascii)
                    total -= widths[k] - b.width
                    widths[k] = b.width
        if total > width:
            notes.append(
                f"text render is {total} characters wide, over {width}; drop a column or "
                "use shorter values."
            )
        sep = " " * GAP
        pad = " " * gutter
        lines = []
        if self.title:
            lines.append(_tx(self.title, ascii))
        lines.append(pad + sep.join(b.head(w) for b, w in zip(blocks, widths, strict=True)))
        if any(b.scale for b in blocks):
            lines.append(
                pad + sep.join(b.scale.ljust(w) for b, w in zip(blocks, widths, strict=True))
            )
        lines.append(("-" if ascii else "─") * total)
        for i in range(len(self.rows)):
            hi, base = roles[i]
            if gutter:
                prefix = ("> " if ascii else "▸ ") if hi else (". " if ascii else "· ") if base else "  "
            else:
                prefix = ""
            line = (
                prefix + sep.join(b.cell(i, w) for b, w in zip(blocks, widths, strict=True))
            ).rstrip()
            if color:
                if hi:
                    line = _ansi_wrap(line, "1")
                elif base:
                    line = _ansi_wrap(line, "2")
            lines.append(line)
        return "\n".join(line.rstrip() for line in lines), notes

    # --- markdown -----------------------------------------------------------------------------
    def markdown(self, *, ascii: bool = False) -> str:
        """A GFM table: text cells as text, chip cells as their compact text in code spans,
        values padded so the glyphs line up in a monospace code font."""
        blocks = self._blocks(ascii, False)
        dash = EMPTY_ASCII if ascii else EMPTY
        head, rule = [], []
        for j, (col, b) in enumerate(zip(self.columns, blocks, strict=True)):
            h = _tx(col.header, ascii)
            if b.scale and self.domains[j] is not None:
                lo, hi = self.domains[j]  # type: ignore[misc]
                lo_s = _tx(fmt.num(lo, sig=2), ascii)
                hi_s = _tx(fmt.num(hi, sig=2, signed=lo < 0 < hi), ascii)
                h += f" ({lo_s} to {hi_s})"
            head.append(_md_escape(h))
            rule.append("--:" if b.right else ":--")
        lines = [f"**{_md_escape(_tx(self.title, ascii))}**", ""] if self.title else []
        lines += ["| " + " | ".join(head) + " |", "|" + "|".join(rule) + "|"]
        for i, row in enumerate(self.rows):
            hi, base = self._row_role(i)
            out = []
            for j, b in enumerate(blocks):
                cell = row[j]
                if cell is None:
                    out.append(dash)
                elif b.text:
                    txt = _md_escape(_tx(str(cell), ascii))
                    if hi:
                        txt = f"**{txt}**"
                    elif base:
                        txt = f"*{txt}*"
                    out.append(txt)
                else:
                    code = _code(b.rows[i][0].rstrip())
                    out.append(f"**{code}**" if hi else code)
            lines.append("| " + " | ".join(out) + " |")
        return "\n".join(lines)

    # --- html ---------------------------------------------------------------------------------
    def html(self, *, theme: Any = "auto", accent: str | None = None) -> str:
        """``<table class="mc-table">``: values and graphics in separate sub-columns sharing the
        column's scale, numbers right-aligned. Styled by ``mintchip.css()``; legible without it
        (only presentational attributes, which any stylesheet overrides)."""
        esc = _html.escape
        graph = [
            c.kind != "text"
            and any(isinstance(r[j], Chip) and REGISTRY[r[j].kind].svg for r in self.rows)
            for j, c in enumerate(self.columns)
        ]
        values = {
            j: _align(
                [p[0] if (p := self._parts(j, r[j], False, False)) else None for r in self.rows],
                False,
                fill=FIGURE_SPACE,
                pad_int=False,
            )
            for j, c in enumerate(self.columns)
            if c.kind != "text"
        }
        out = ['<table class="mc-table" cellspacing="0" cellpadding="3">']
        if self.title:
            out.append(f"<caption>{esc(self.title)}</caption>")
        head = []
        for j, c in enumerate(self.columns):
            if c.kind == "text":
                head.append(f'<th scope="col" class="mc-text" align="left">{esc(c.header)}</th>')
            else:
                attrs = ' class="mc-chip" colspan="2" align="left"'
                if not graph[j]:
                    attrs = ' class="mc-chip mc-num" align="right"'
                head.append(f'<th scope="col"{attrs}>{esc(c.header)}</th>')
        out.append("<thead><tr>" + "".join(head) + "</tr>")
        scales = [self._html_scale(j) if graph[j] else "" for j in range(len(self.columns))]
        if any(scales):
            row = "".join(
                "<th></th>" + (scales[j] or ("<th></th>" if graph[j] else ""))
                for j in range(len(self.columns))
            )
            out.append(f'<tr class="mc-scale">{row}</tr>')
        out.append("</thead><tbody>")
        for i, r in enumerate(self.rows):
            tds = []
            for j, c in enumerate(self.columns):
                cell = r[j]
                if c.kind == "text":
                    text = EMPTY if cell is None else esc(str(cell))
                    tds.append(f'<td class="mc-text">{text}</td>')
                    continue
                if not isinstance(cell, Chip):
                    tds.append(f'<td class="mc-num mc-empty" align="right">{EMPTY}</td>')
                    if graph[j]:
                        tds.append('<td class="mc-graph mc-empty"></td>')
                    continue
                v = esc(values[j][i])
                tds.append(f'<td class="mc-num" align="right"><span class="mc-v">{v}</span></td>')
                if graph[j]:
                    g = cell.html(
                        theme=theme,
                        accent=accent,
                        domain=self._domain_for(j, cell),
                        value=False,
                        details=False,
                    )
                    tds.append(f'<td class="mc-graph">{g}</td>')
            hi, base = self._row_role(i)
            row_cls = " ".join(c for c, on in (("mc-highlight", hi), ("mc-baseline", base)) if on)
            tr_open = f'<tr class="{row_cls}">' if row_cls else "<tr>"
            out.append(tr_open + "".join(tds) + "</tr>")
        out.append("</tbody></table>")
        return "\n".join(out)

    def _html_scale(self, j: int) -> str:
        col, d = self.columns[j], self.domains[j]
        if d is None or col.kind not in POSITION or not self._blocks_scale(j):
            return ""
        lo, hi = d
        cells = [r[j] for r in self.rows if isinstance(r[j], Chip) and r[j].kind == col.kind]
        if col.kind == "rank" and all(c.stats.get("higher_is_better") is False for c in cells):
            lo, hi = hi, lo
        left, right = fmt.num(lo, sig=2), fmt.num(hi, sig=2, signed=lo < 0 < hi)
        return (
            '<th class="mc-graph" style="font-weight:normal;font-size:.75em">'
            '<span style="display:flex;justify-content:space-between;gap:.5em">'
            f'<span class="mc-lo">{_html.escape(left)}</span>'
            f'<span class="mc-hi">{_html.escape(right)}</span></span></th>'
        )

    def _blocks_scale(self, j: int) -> bool:
        return bool(self._chip_block(j, False, False).scale)

    # --- data & save --------------------------------------------------------------------------
    def save(self, path: str | Path, **render_options: Any) -> dict[str, Any]:
        """Write ``.html`` (standalone page, or bare table with ``fragment=True``), ``.md``,
        ``.txt`` or ``.json``; returns a summary dict with ``path``."""
        dest = Path(path)
        suffix = dest.suffix.lower()
        try:
            if suffix in (".html", ".htm"):
                from .render import html as _html_mod
                from .themes import resolve_theme

                opts = dict(render_options)
                fragment = opts.pop("fragment", False)
                compact = opts.pop("compact", False)
                table_html = self.html(**opts)
                if fragment:
                    content = table_html + "\n"
                else:
                    theme = opts.get("theme", "auto")
                    accent = opts.get("accent")
                    try:
                        name = resolve_theme(theme, accent).name
                    except (TypeError, ValueError) as e:
                        raise ChipError(
                            f"mintchip.Table.save: {e}.", fix_hint="Use theme='auto'."
                        ) from None
                    scheme = {"dark": "dark", "light": "light", "mono": "light"}.get(name)
                    content = _html_mod._shell(
                        self.title or "mintchip",
                        f'<div class="mc-wide">{table_html}</div>',
                        scheme,
                        accent=accent,
                        compact=compact,
                    )
            elif suffix in (".md", ".markdown"):
                content = self.markdown(**render_options) + "\n"
            elif suffix == ".txt":
                content = self.text(**render_options) + "\n"
            elif suffix == ".json":
                content = json.dumps(self.to_dict(), ensure_ascii=False, **render_options) + "\n"
            else:
                raise ChipError(
                    f"mintchip.Table.save: unsupported extension {suffix!r}.",
                    fix_hint="Save as .html, .md, .txt or .json.",
                )
        except TypeError as e:
            raise ChipError(
                f"mintchip.Table.save: {e}.",
                fix_hint="Pass only the options of the matching render method.",
            ) from None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        return {
            "rows": len(self.rows),
            "columns": [c.key for c in self.columns],
            "title": self.title,
            "warnings": list(self.warnings),
            "path": str(dest),
        }

    def _repr_html_(self) -> str:
        from .render import html as _html_mod

        return f"<style>{_html_mod.css()}</style>{self.html()}"

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe; ``Table.from_dict(t.to_dict())`` (or ``table(**d)``) rebuilds the table.
        Rows are stored in display order, each chip cell as its ``chip.to_dict()`` spec."""
        rows = []
        for r in self.rows:
            row: dict[str, Any] = {}
            for col, cell in zip(self.columns, r, strict=True):
                row[col.key] = cell.to_dict() if isinstance(cell, Chip) else cell
            rows.append(row)
        out: dict[str, Any] = {
            "rows": rows,
            "columns": {c.key: c.spec() for c in self.columns},
            "sort": self.sort,
            "descending": self.descending,
            "limit": self.limit,
            "title": self.title,
        }
        if self.highlight:
            out["highlight"] = list(self.highlight)
        if self.baseline is not None:
            out["baseline"] = self.baseline
        return out

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Table:
        """Rebuild a table from ``to_dict()``."""
        if not isinstance(d, Mapping) or "rows" not in d:
            raise ChipError(
                "mintchip.Table.from_dict needs a dict with a 'rows' key.",
                fix_hint="Pass the output of Table.to_dict().",
            )
        keys = ("rows", "columns", "sort", "descending", "limit", "title", "highlight", "baseline")
        return table(**{k: d[k] for k in keys if k in d})


# --- the text layout ----------------------------------------------------------------------------
@dataclass
class _Block:
    """One column of the text render: a header, an optional scale line, rows as
    (plain, rendered) pairs (rendered may carry ANSI codes; widths come from plain)."""

    header: str
    rows: list[tuple[str, str]]
    text: bool = False
    right: bool = False  # right-align (a chip column with no glyph)
    scale: str = ""

    @property
    def content_width(self) -> int:
        return max([len(p) for p, _ in self.rows] + [len(self.scale)], default=0)

    @property
    def width(self) -> int:
        return max(self.content_width, len(self.header))

    def clip(self, w: int, ascii: bool) -> None:
        self.header = _clip(self.header, w, ascii)
        self.rows = [(c, c) for c in (_clip(p, w, ascii) for p, _ in self.rows)]

    def head(self, w: int) -> str:
        return self.header.rjust(w) if self.right else self.header.ljust(w)

    def cell(self, i: int, w: int) -> str:
        plain, rendered = self.rows[i]
        pad = " " * (w - len(plain))
        return pad + rendered if self.right else rendered + pad


def _align(
    values: list[str | None], ascii: bool, *, fill: str = " ", pad_int: bool = True
) -> list[str]:
    """Values on the decimal point when every one is a plain number, else right-aligned.
    ``None`` is an empty cell. With ``pad_int=False`` only the fraction side is padded (with
    ``fill``), for a renderer that right-aligns the cell itself."""
    dash = EMPTY_ASCII if ascii else EMPTY
    present = [v for v in values if v is not None]
    matches = [_PLAIN_NUM.match(v) for v in present]
    if present and all(matches):
        split = {v: (m[1], (m[2] or "") + m[3]) for v, m in zip(present, matches, strict=True)}
        iw = max(len(a) for a, _ in split.values()) if pad_int else 0
        fw = max(len(b) for _, b in split.values())
        out = []
        for v in values:
            a, b = (dash, "") if v is None else split[v]
            out.append(a.rjust(iw) + b + fill * (fw - len(b)))
        return out
    if not pad_int:
        return [dash if v is None else v for v in values]
    w = max([len(v) for v in present] + [len(dash)])
    return [(dash if v is None else v).rjust(w) for v in values]


def _open(glyph: str) -> int:
    """Index of a position glyph's opening bracket (``[``, or ``<`` when clipped), or -1."""
    return next((k for k, ch in enumerate(glyph) if ch in "[<"), -1)


def _align_glyphs(kind: str, glyphs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Left-aligned glyphs; for position kinds the opening brackets line up, so a prefix such
    as dist's clipped-outlier note never shifts the axis."""
    if kind not in POSITION:
        return glyphs
    opens = [_open(g) for g, _ in glyphs if g]
    at = max(opens, default=0)
    out = []
    for g, rendered in glyphs:
        pad = " " * (at - _open(g)) if g and _open(g) >= 0 else ""
        out.append((pad + g, pad + rendered))
    return out


def _ansi_wrap(line: str, sgr: str) -> str:
    """Wrap a line in an ANSI SGR code, re-opening it after any inner reset."""
    return f"\x1b[{sgr}m" + line.replace("\x1b[0m", f"\x1b[0m\x1b[{sgr}m") + "\x1b[0m"


def _clip(s: str, w: int, ascii: bool) -> str:
    if len(s) <= w:
        return s
    return s[: max(w - 1, 0)] + ("~" if ascii else "…")


def _tx(s: str, ascii: bool) -> str:
    return to_ascii(s) if ascii else s


def _md_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def _code(s: str) -> str:
    s = s.replace("|", "\\|")
    tick = "``" if "`" in s else "`"
    if s.startswith(" ") and s.endswith(" ") or tick == "``":
        s = f" {s} "  # GFM strips one space from each side of a code span
    return f"{tick}{s}{tick}"


# --- building -----------------------------------------------------------------------------------
def table(
    rows: Any,
    columns: Mapping[str, Any] | None = None,
    *,
    sort: str | None = None,
    descending: bool | None = None,
    limit: int | None = None,
    title: str | None = None,
    highlight: str | Sequence[str] | None = None,
    baseline: str | None = None,
) -> Table:
    """A table of small multiples: one row per item, one shared scale per chip column.

    ``rows`` is a sequence of mappings, or a path to a ``.json`` (list of objects), ``.jsonl``,
    ``.csv`` or ``.tsv`` file. ``columns`` maps row key → spec, in display order: a kind name
    (``"bar"``, ``"ci"``, ``"spark"``, ``"num"``, …), ``"text"``, or a dict ``{"chip": kind,
    "header": str, "share": bool, **constructor keyword arguments for every cell}``. With
    ``columns=None`` every key of the first row is shown: strings as text, numbers as ``num``,
    lists of numbers as ``spark``.

    A cell is a ``Chip``, a dict of constructor arguments, or a bare value filling the kind's
    positional parameters in order (a list or tuple is unpacked when the kind has several, and a
    ``range`` parameter may be given as two numbers: ``ci`` takes ``(estimate, low, high)``).
    ``None`` or a missing key is an empty cell. ``sort`` names a column: chip columns sort by
    their primary value, largest first, and text columns alphabetically, A to Z; ``descending``
    True or False overrides either direction. Empty cells sort last. ``limit`` keeps the first
    rows after sorting. ``highlight`` and ``baseline`` emphasise rows matching the first text
    column.
    """
    data = _load_rows(rows)
    cols = _columns(columns, data)
    keys = [c.key for c in cols]
    if sort is not None and sort not in keys:
        raise ChipError(
            f"mintchip.table: sort key {sort!r} is not a column.",
            fix_hint=f"Sort by one of: {', '.join(map(repr, keys))}.",
        )
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ChipError(
            f"mintchip.table: limit must be a whole number of 1 or more; got {limit!r}.",
            fix_hint="Pass limit=10, or leave it out to show every row.",
        )
    if title is not None and not isinstance(title, str):
        raise ChipError(
            f"mintchip.table: title must be a string; got {title!r}.",
            fix_hint='Pass title="Benchmark results".',
        )
    hi = _normalize_highlight(highlight)
    base = _normalize_baseline(baseline)
    built = [[_cell(i, c, row.get(c.key)) for c in cols] for i, row in enumerate(data)]
    for j, c in enumerate(cols):
        if c.kind == "share" and "sort" not in c.options:
            _keep_part_order(built, j)
        elif c.kind == "bar" and "percent" not in c.options:
            _keep_bar_wording(built, j)
    order = list(range(len(built)))
    if descending is not None and not isinstance(descending, bool):
        raise ChipError(
            f"mintchip.table: descending must be True, False or None; got {descending!r}.",
            fix_hint="Leave it out for largest first (A to Z for a text column).",
        )
    if sort is not None:
        j = keys.index(sort)
        down = cols[j].kind != "text" if descending is None else descending
        has = [i for i in order if _sort_key(built[i][j]) is not None]
        has.sort(key=lambda i: _sort_key(built[i][j]), reverse=down)
        order = has + [i for i in order if _sort_key(built[i][j]) is None]
    if limit is not None:
        order = order[:limit]
    return Table(
        cols,
        [built[i] for i in order],
        index=order,
        sort=sort,
        descending=descending,
        limit=limit,
        title=title,
        highlight=hi,
        baseline=base,
    )


def _normalize_highlight(highlight: Any) -> tuple[str, ...]:
    if highlight is None:
        return ()
    if isinstance(highlight, str):
        return (highlight,) if highlight else ()
    if isinstance(highlight, (bytes, Mapping)) or not isinstance(highlight, Iterable):
        raise ChipError(
            "mintchip.table: highlight must be a string or sequence of strings; "
            f"got {type(highlight).__name__}.",
            fix_hint='Pass highlight="model_a" or highlight=["model_a", "model_b"].',
        )
    items = list(highlight)
    if not all(isinstance(x, str) for x in items):
        raise ChipError(
            "mintchip.table: highlight entries must be strings.",
            fix_hint='Pass highlight=["model_a", "model_b"].',
        )
    return tuple(x for x in items if x)


def _normalize_baseline(baseline: Any) -> str | None:
    if baseline is None:
        return None
    if not isinstance(baseline, str):
        raise ChipError(
            f"mintchip.table: baseline must be a string; got {type(baseline).__name__}.",
            fix_hint='Pass baseline="baseline".',
        )
    return baseline or None


def _keep_part_order(built: list[list[Cell]], j: int) -> None:
    """A share column whose rows name the same parts in the same order is drawn in that order
    (``sort=False``), so each part keeps its place and shade down the column; sorted largest
    first, the first segment would be a different part in each row."""
    cells = [(i, r[j]) for i, r in enumerate(built) if isinstance(r[j], Chip)]
    if len(cells) < 2 or any(c.kind != "share" or "sort" in c.args for _, c in cells):
        return
    if len({tuple(c.args["parts"]) for _, c in cells}) != 1:
        return
    for i, c in cells:
        built[i][j] = from_dict({**c.to_dict(), "sort": False})


def _keep_bar_wording(built: list[list[Cell]], j: int) -> None:
    """When a bar column mixes count totals (e.g. 38/40) with a row whose total happens to be
    1 (e.g. 1/1), keep count wording instead of switching that single cell to ``100%``."""
    cells = [(i, r[j]) for i, r in enumerate(built) if isinstance(r[j], Chip) and r[j].kind == "bar"]
    if len(cells) < 2 or not any(not c.stats["pct_mode"] for _, c in cells):
        return
    for i, c in cells:
        if c.stats["pct_mode"] and c.unit != "%" and "percent" not in c.args:
            built[i][j] = from_dict({**c.to_dict(), "percent": False})


def _sort_key(cell: Cell) -> Any:
    if isinstance(cell, Chip):
        v = cell.stats.get("value")
        return None if v is None else float(v)
    return None if cell is None else cell.casefold()


def _load_rows(rows: Any) -> list[Mapping[str, Any]]:
    if isinstance(rows, (str, os.PathLike)):
        path = Path(rows)
        suffix = path.suffix.lower()
        if suffix not in (".json", ".jsonl", ".csv", ".tsv"):
            raise ChipError(
                f"mintchip.table: rows path {str(path)!r} is not .json, .jsonl, .csv or .tsv.",
                fix_hint=_HINT_ROWS,
            )
        try:
            raw = path.read_text(encoding="utf-8-sig")
        except OSError as e:
            raise ChipError(f"mintchip.table: cannot read {str(path)!r}: {e.strerror}.",
                            fix_hint="Check the path.") from None  # fmt: skip
        if suffix == ".csv":
            return list(csv.DictReader(raw.splitlines()))
        if suffix == ".tsv":
            return list(csv.DictReader(raw.splitlines(), delimiter="\t"))
        if suffix == ".jsonl":
            parsed = []
            for lineno, line in enumerate(raw.splitlines(), 1):
                s = line.strip()
                if not s:
                    continue
                try:
                    parsed.append(json.loads(s))
                except ValueError as e:
                    raise ChipError(
                        f"mintchip.table: {str(path)!r} line {lineno} is not valid JSON ({e}).",
                        fix_hint="Each non-empty line in a .jsonl file must be a JSON object.",
                    ) from None
            rows = parsed
        else:
            try:
                rows = json.loads(raw)
            except ValueError as e:
                raise ChipError(f"mintchip.table: {str(path)!r} is not valid JSON ({e}).",
                                fix_hint="The file must hold a list of objects.") from None  # fmt: skip
    if isinstance(rows, (bytes, Mapping)) or not isinstance(rows, Iterable):
        raise ChipError(
            f"mintchip.table: rows must be a list of dicts; got {type(rows).__name__}.",
            fix_hint=_HINT_ROWS,
        )
    out = list(rows)
    for i, r in enumerate(out):
        if not isinstance(r, Mapping):
            raise ChipError(
                f"mintchip.table: row {i} is a {type(r).__name__}, not a dict.",
                fix_hint=_HINT_ROWS,
            )
    return out


def _columns(columns: Any, rows: list[Mapping[str, Any]]) -> list[_Column]:
    if columns is None:
        if not rows:
            raise ChipError(
                "mintchip.table: no rows to infer columns from.",
                fix_hint='Pass columns=, e.g. {"model": "text", "acc": "bar"}.',
            )
        return [_Column(k, _infer(k, rows), str(k)) for k in rows[0]]
    if not isinstance(columns, Mapping):
        raise ChipError(
            f"mintchip.table: columns must be a dict of key → spec; got {type(columns).__name__}.",
            fix_hint='Pass e.g. columns={"model": "text", "acc": "bar", "lift": "ci"}.',
        )
    return [_column(str(k), spec, rows) for k, spec in columns.items()]


def _column(key: str, spec: Any, rows: list[Mapping[str, Any]]) -> _Column:
    where = f"mintchip.table: column {key!r}"
    if isinstance(spec, str):
        _check_kind(where, spec)
        return _Column(key, spec, key)
    if not isinstance(spec, Mapping):
        raise ChipError(
            f"{where}: spec must be a kind name or a dict; got {spec!r}.",
            fix_hint='Pass "bar", "text", or {"chip": "bar", "header": "Accuracy"}.',
        )
    opts = dict(spec)
    kind = opts.pop("chip", None) or _infer(key, rows)
    _check_kind(where, kind)
    header = opts.pop("header", key)
    share = opts.pop("share", True)
    if not isinstance(header, str) or not isinstance(share, bool):
        raise ChipError(
            f"{where}: header must be a string and share True or False.",
            fix_hint='Pass e.g. {"chip": "ci", "header": "Lift", "share": False}.',
        )
    if opts:
        if kind == "text":
            raise ChipError(f"{where}: a text column takes only header.",
                            fix_hint=f"Remove {', '.join(opts)}.")  # fmt: skip
        names = [p.name for p in REGISTRY[kind].params]
        for name in opts:
            if name not in names:
                import difflib

                close = difflib.get_close_matches(name, names, n=1)
                hint = f"Did you mean {close[0]}=?" if close else f"Accepted: {', '.join(names)}."
                raise ChipError(f"{where}: mintchip.{kind} has no argument {name!r}.",
                                fix_hint=hint)  # fmt: skip
    return _Column(key, kind, header, share, opts)


def _check_kind(where: str, kind: Any) -> None:
    if kind == "text" or (isinstance(kind, str) and kind in REGISTRY):
        return
    import difflib

    names = sorted(REGISTRY)
    close = difflib.get_close_matches(str(kind), [*names, "text"], n=1)
    hint = f"Did you mean {close[0]!r}? " if close else ""
    raise ChipError(f"{where}: unknown kind {kind!r}.",
                    fix_hint=f"{hint}Use 'text' or one of: {', '.join(names)}.")  # fmt: skip


def _infer(key: str, rows: list[Mapping[str, Any]]) -> str:
    """The kind for a column from its first non-empty value."""
    for r in rows:
        v = r.get(key)
        if isinstance(v, str):
            if not v.strip():
                continue
            v = _parse(v) if _parse_numeric(v) is not None else v
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        if isinstance(v, Chip):
            return v.kind
        if isinstance(v, Mapping) and v.get("chip") in REGISTRY:
            return str(v["chip"])
        if _is_number(v):
            return "num"
        if isinstance(v, (list, tuple)) and v and all(x is None or _is_number(x) for x in v):
            return "spark"
        return "text"
    return "text"


def _cell(i: int, col: _Column, v: Any) -> Cell:
    if v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and not v):
        return None
    if col.kind == "text":
        if isinstance(v, Chip):
            return v.text(compact=True)
        return _text_value(v)
    if isinstance(v, Chip):
        return v
    try:
        if isinstance(v, str):
            v = _parse(v)
            if v is None:
                return None
        return _build(REGISTRY[col.kind], col, v)
    except ChipError as e:
        raise ChipError(
            f"mintchip.table: row {i}, column {col.key!r}: {e.message}",
            fix_hint=e.fix_hint
            or f"Give the cell as a mintchip.{col.kind} argument dict or its positional values.",
        ) from None


def _build(kind: Kind, col: _Column, v: Any) -> Chip:
    names = {p.name for p in kind.params}
    if isinstance(v, Mapping) and v and ("chip" in v or set(v) <= names):
        spec = dict(v)
        k = spec.pop("chip", col.kind)
        if k not in REGISTRY:
            _check_kind(f"cell chip {k!r}", k)
        opts = col.options if k == col.kind else {}
        return REGISTRY[k].fn(**{**opts, **spec})
    positional = [p for p in kind.params if p.positional]
    if len(positional) > 1 and isinstance(v, (list, tuple)):
        args = _group(kind, positional, list(v))
    else:
        args = {positional[0].name: v}
    return kind.fn(**{**col.options, **args})


def _group(kind: Kind, positional: list[Any], items: list[Any]) -> dict[str, Any]:
    """Fill positional parameters in order; a ``range`` may take two bare numbers."""
    out: dict[str, Any] = {}
    for p in positional:
        if not items:
            break
        if p.type == "range" and len(items) >= 2 and _is_number(items[0]) and _is_number(items[1]):
            out[p.name], items = (items[0], items[1]), items[2:]
        else:
            out[p.name], items = items[0], items[1:]
    if items:
        names = ", ".join(p.name for p in positional)
        raise ChipError(
            f"the cell has {len(items)} value(s) more than mintchip.{kind.name} takes ({names}).",
            fix_hint=f"Give mintchip.{kind.name}'s positional values in order: {names}.",
        )
    return out


def _is_number(v: Any) -> bool:
    if isinstance(v, (bool, str, bytes)):
        return False
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _text_value(v: Any) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _parse_numeric(s: str) -> float | list[float | None] | None:
    """A number, or a list of numbers (space, comma or semicolon separated), or None."""
    t = s.strip().replace("−", "-")
    if _NUMBER.match(t) or _THOUSANDS.match(t):
        return float(t.replace(",", ""))
    toks = [x for x in re.split(r"[\s;,]+", t.strip("[]")) if x]
    if len(toks) > 1 and all(_NUMBER.match(x) or x.lower() in ("null", "nan") for x in toks):
        return [None if x.lower() in ("null", "nan") else float(x) for x in toks]
    return None


def _parse(s: str) -> Any:
    """A string cell (from CSV, say) as a value for a chip column."""
    t = s.strip()
    if not t or t.lower() in ("null", "none", "nan", "—", "-"):
        return None
    if t[0] in "[{":
        try:
            return json.loads(t)
        except ValueError:
            pass
    numeric = _parse_numeric(t)
    if numeric is not None:
        return numeric
    toks = [x for x in re.split(r"[\s;,]+", t) if x]
    if len(toks) == 1:
        return t
    words = {"true": True, "false": False, "null": None, "nan": None}
    return [words.get(x.lower(), x) for x in toks]


def _domain_of(c: Chip) -> tuple[float, float] | None:
    """The chip's own effective scale: an explicit ``domain`` argument, else its natural one."""
    d = c.args.get("domain")
    return (float(d[0]), float(d[1])) if d is not None else c.domain


def _plain(v: Any) -> Any:
    """JSON-safe copy of a column option value."""
    if isinstance(v, Mapping):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (str, bool, int, float)) or v is None:
        return v
    if isinstance(v, Iterable):
        return [_plain(x) for x in v]
    return float(v)
