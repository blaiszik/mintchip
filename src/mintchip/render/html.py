"""HTML tier: a chip inline in prose, its details on demand, the stylesheet and a reading page.

A chip is a bare ``<span class="mc">``: the value in the surrounding text's own type, a space,
then the inline SVG. Details on demand use the HTML popover API (a ``<button popovertarget>``
and a ``<span popover>``), which needs no JavaScript and, unlike ``<details>``, is phrasing
content, so it does not end the enclosing ``<p>``. The popover reads like a footnote: it holds
only what the sentence does not already say.
"""

from __future__ import annotations

import html
import itertools
import re
import zlib
from collections.abc import Sequence
from typing import Any

__all__ = ["chip_html", "css", "document", "page"]

# Every popover id on a page must be unique, even for one chip rendered twice.
_SEQ = itertools.count(1)
# Inline, so a chip in a page without mintchip.css() still reads as text, not as a button.
_RESET = (
    "font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;"
    "cursor:pointer;white-space:nowrap"
)
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_WORD = re.compile(r"[^\W\d_]+")
_FILLER = frozenset(
    ["a", "an", "and", "at", "exact", "is", "median", "of", "out", "the", "to", "value", "whole"]
)
_BLOCK = re.compile(
    r"<(?:address|article|aside|blockquote|details|div|dl|figure|footer|form|h[1-6]|header|hr|"
    r"nav|ol|p|pre|section|table|ul)\b",
    re.IGNORECASE,
)


# --- one chip -------------------------------------------------------------------------------
def chip_html(
    chip: Any,
    *,
    svg: str,
    value: str | None,
    full: str | None = None,
    label: str | None = None,
    details: bool = True,
    detail: str | None = None,
    warnings: Sequence[str] | None = None,
) -> str:
    """Inline HTML for one chip. ``value`` is the value shown in the sentence, ``full`` the
    uncompacted value offered in the popover, ``detail`` caller-supplied (trusted) HTML,
    ``warnings`` the lines that hold at the rendered scale (default ``chip.warnings``)."""
    parts = []
    if label:
        parts.append(f'<span class="mc-label">{html.escape(label)}</span> ')
    if value:
        parts.append(f'<span class="mc-v">{html.escape(value)}</span>')
    if svg:
        parts.append((" " if value else "") + svg)
    inner = "".join(parts)
    cls = f"mc mc-{chip.kind}"
    notes = chip.warnings if warnings is None else warnings
    body = _popover(chip, value, full, bool(label), detail, notes) if details else ""
    if not body:
        return f'<span class="{cls}" style="white-space:nowrap">{inner}</span>'
    pid = f"mc-{zlib.crc32(repr((chip.kind, chip.args, detail)).encode()):08x}-{next(_SEQ)}"
    return (
        f'<span class="{cls}"><button type="button" class="mc-open" popovertarget="{pid}" '
        f'style="{_RESET};anchor-name:--{pid}" aria-label="{html.escape(chip.alt, quote=True)}">'
        f'{inner}</button><span id="{pid}" class="mc-pop" popover hidden '
        f'style="position-anchor:--{pid}">{body}</span></span>'
    )


def _popover(
    chip: Any, value: str | None, full: str | None, label_shown: bool, detail, warnings
) -> str:
    """Label, full value, the facts that add to what is visible, warnings, then ``detail``."""
    lines = []
    if chip.label and not label_shown:
        lines.append(f'<span class="mc-pop-l">{html.escape(chip.label)}</span>')
    shown = value or ""
    if full and full != value:
        lines.append(html.escape(full))
        shown = f"{shown} {full}"
    lines += [html.escape(f) for f in chip.facts if not restates(f, shown)]
    lines += [f'<span class="mc-pop-w">Note: {html.escape(w)}</span>' for w in warnings]
    if detail:
        lines.append(detail)
    return "<br>".join(lines)


def restates(fact: str, shown: str) -> bool:
    """Whether ``fact`` only repeats ``shown``: every number in it is visible already and its
    other words are visible or filler ("exact value 0.82" next to "0.82"). A fact with no
    number is never a restatement."""
    nums = {n.replace(",", "") for n in _NUM.findall(fact)}
    if not nums or not nums <= {n.replace(",", "") for n in _NUM.findall(shown)}:
        return False
    words = {w.lower() for w in _WORD.findall(fact)} - _FILLER
    return words <= {w.lower() for w in _WORD.findall(shown)}


# --- the stylesheet -------------------------------------------------------------------------
_LIGHT = "--mc-accent:#3B7DDD;--mc-good:#2A9152;--mc-bad:#DC4535;--mc-warn:#B87A00"
_DARK = "--mc-accent:#5590E8;--mc-good:#31A05C;--mc-bad:#E85A48;--mc-warn:#C08000"
_PAPER = {
    "light": "--mc-paper:#FFFFFF;--mc-ink:#1A1D21",
    "dark": "--mc-paper:#14181F;--mc-ink:#E6E9EE",
}
_RULE = "1px solid color-mix(in srgb,currentColor 40%,transparent)"
_MUTED = "color-mix(in srgb,currentColor 66%,transparent)"

# Role colours meet 3:1 on #FFFFFF and on #14181F in both sets, so a host page whose colour
# scheme disagrees with the reader's system setting still reads.
_CSS = f"""
:root{{{_LIGHT}}}
@media (prefers-color-scheme:dark){{:root{{{_DARK}}}}}
.mc{{white-space:nowrap;font-variant-numeric:tabular-nums}}
.mc-open{{text-decoration:none}}
.mc-open:hover,.mc-open:focus-visible,.mc:has(>.mc-pop:popover-open)>.mc-open{{
text-decoration:underline dotted 1px;text-decoration-color:{_MUTED};
text-underline-offset:.22em;outline:none}}
.mc-open:focus-visible:not(:has(.mc-v)){{outline:1px dotted;outline-offset:2px}}
.mc-pop{{margin:auto;padding:.35em .6em .4em;max-width:min(22em,calc(100vw - 2em));
border:1px solid color-mix(in srgb,currentColor 22%,transparent);border-radius:3px;
background:var(--mc-paper,Canvas);color:var(--mc-ink,CanvasText);font-size:.84em;
line-height:1.45;font-weight:400;font-style:normal;text-align:left;white-space:normal;
overflow-wrap:break-word}}
.mc-pop:popover-open{{display:block}}
.mc-pop-l{{font-weight:600}}
.mc-pop-w{{color:{_MUTED}}}
@supports (position-area:bottom) or (inset-area:bottom){{.mc-pop{{inset:auto;margin:.3em 0;
inset-area:bottom span-right;position-area:bottom span-right;
position-try-options:flip-block,flip-inline;position-try-fallbacks:flip-block,flip-inline}}}}
.mc-table{{border-collapse:collapse;font-variant-numeric:tabular-nums;line-height:1.4}}
.mc-table caption{{caption-side:top;text-align:left;font-weight:600;padding:0 0 .4em}}
.mc-table th,.mc-table td{{padding:.3em 0 .3em 1.25em;border:0;text-align:left;
vertical-align:baseline}}
.mc-table :is(th,td):first-child{{padding-left:0}}
.mc-table .mc-graph{{padding-left:.45em}}
.mc-table thead th{{font-weight:600;vertical-align:bottom}}
.mc-table thead tr:last-child>th{{border-bottom:{_RULE}}}
.mc-table .mc-scale>th{{font-weight:400;font-size:.75em;color:{_MUTED};padding-top:0}}
.mc-table tbody th{{font-weight:inherit}}
.mc-table tbody tr:first-child>*{{padding-top:.5em}}
.mc-table tbody tr:last-child>*{{padding-bottom:.5em;border-bottom:{_RULE}}}
.mc-table .mc-num{{text-align:right}}
.mc-table .mc-empty{{color:{_MUTED}}}
.mc-table tr.mc-highlight>*{{font-weight:600;background:color-mix(in srgb,var(--mc-accent) 9%,transparent)}}
.mc-table tr.mc-baseline>*{{color:{_MUTED}}}
.mc-table tr.mc-baseline:not(:first-child)>*{{border-top:1px dashed color-mix(in srgb,currentColor 28%,transparent)}}
.mc-page{{color-scheme:light dark;{_PAPER["light"]};background:var(--mc-paper);
color:var(--mc-ink)}}
@media (prefers-color-scheme:dark){{.mc-page{{{_PAPER["dark"]}}}}}
[data-mc-scheme="light"],[data-mc-scheme="light"] .mc,.mc[data-mc-scheme="light"],.mc-page[data-mc-scheme="light"]{{color-scheme:light;{_PAPER["light"]};{_LIGHT}}}
[data-mc-scheme="dark"],[data-mc-scheme="dark"] .mc,.mc[data-mc-scheme="dark"],.mc-page[data-mc-scheme="dark"]{{color-scheme:dark;{_PAPER["dark"]};{_DARK}}}
.mc-page body{{margin:0}}
.mc-doc{{display:grid;grid-template-columns:1fr min(34em,100%) 1fr;
padding:clamp(2em,8vh,4.5em) 1.25em 4em;font:1.0625rem/1.55 system-ui,-apple-system,
"Segoe UI",Roboto,sans-serif;-webkit-text-size-adjust:100%}}
.mc-doc>*{{grid-column:2;margin:0 0 1em}}
.mc-doc p{{text-wrap:pretty}}
.mc-doc>h1{{font-size:1.55em;line-height:1.2;font-weight:650;letter-spacing:-.01em;
margin-bottom:.3em;text-wrap:balance}}
.mc-doc>.mc-sub{{color:{_MUTED};margin-bottom:1.75em}}
.mc-doc>h2{{font-size:1.1em;font-weight:600;margin:.8em 0 .4em}}
.mc-doc>.mc-wide{{grid-column:1/-1;justify-self:center;width:max-content;
min-width:min(34em,100%);max-width:100%;overflow-x:auto;margin:.25em 0 1.25em}}
.mc-doc .mc-table{{font-size:.94em}}
.mc-doc>.mc-src{{margin-top:1.5em;font-size:.85em;color:{_MUTED}}}
"""
_CSS = "".join(line.strip() for line in _CSS.strip().splitlines())
_COMPACT_CSS = (
    ".mc-compact,.mc-compact body{background:transparent}"
    ".mc-compact .mc-doc{display:block;padding:4px 0}"
    ".mc-compact .mc-doc>.mc-wide{width:auto;min-width:0}"
)
_THEME_SYNC_JS = (
    "(function(){var H=document.documentElement;"
    "function sync(){"
    "var c=H.classList,t=H.getAttribute('data-theme');"
    "if(c.contains('light')||t==='light'){H.setAttribute('data-mc-scheme','light');}"
    "else if(c.contains('dark')||t==='dark'){H.setAttribute('data-mc-scheme','dark');}"
    "else if(window.matchMedia){"
    "H.setAttribute('data-mc-scheme',"
    "window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');}"
    "}"
    "sync();"
    "window.addEventListener('themechange',sync);"
    "if(window.matchMedia){"
    "var mq=window.matchMedia('(prefers-color-scheme:dark)');"
    "if(mq.addEventListener)mq.addEventListener('change',sync);}"
    "})();"
)


def css(accent: str | None = None) -> str:
    """The one stylesheet for chips, popovers, ``mintchip.table`` and ``document()``. It
    sets ``--mc-accent``, ``--mc-good``, ``--mc-bad`` and ``--mc-warn`` (with dark values under
    ``prefers-color-scheme: dark``); override them on any ancestor or pass ``accent="#HEX"``
    to restyle."""
    if accent is None:
        return _CSS
    from ..spec import ChipError
    from ..themes import resolve_theme

    try:
        colour = resolve_theme("auto", accent).accent
    except (TypeError, ValueError) as e:
        raise ChipError(
            f"mintchip.css: {e}.", fix_hint="Pass a hex colour like '#2563EB'."
        ) from None
    return _CSS.replace("--mc-accent:#3B7DDD", f"--mc-accent:{colour}").replace(
        "--mc-accent:#5590E8", f"--mc-accent:{colour}"
    )


# --- pages ----------------------------------------------------------------------------------
def document(
    title: str,
    blocks: Any,
    *,
    subtitle: str | None = None,
    source: str | None = None,
    theme: Any = "auto",
    accent: str | None = None,
    compact: bool = False,
) -> str:
    """A self-contained reading page with no JavaScript (or a transparent flush embed with
    lightweight host theme sync when ``compact=True``): a title, then ``blocks`` on a measure
    of about 34em in the reader's system text face, adapting to light and dark (``theme``
    "light" or "dark" fixes one). A block is an HTML string (block-level markup is kept as is;
    anything else, such as ``format_prose(..., format="html")`` output, becomes a ``<p>``), a
    ``Chip``, or a ``Table``. Strings are HTML: escape untrusted text before passing it.
    ``title``, ``subtitle`` and ``source`` are plain text."""
    from ..spec import Chip, ChipError
    from ..themes import resolve_theme

    try:
        name = resolve_theme(theme, accent).name
    except (TypeError, ValueError) as e:
        raise ChipError(f"mintchip.document: {e}.", fix_hint="Use theme='auto'.") from None
    if isinstance(blocks, str) or not hasattr(blocks, "__iter__"):
        blocks = [blocks]
    parts = [f"<h1>{html.escape(title)}</h1>"] if title else []
    if subtitle:
        parts.append(f'<p class="mc-sub">{html.escape(subtitle)}</p>')
    for i, b in enumerate(blocks):
        if isinstance(b, str):
            if b.lstrip().lower().startswith("<table"):
                parts.append(f'<div class="mc-wide">{b}</div>')
            else:
                parts.append(b if _BLOCK.match(b.lstrip()) else f"<p>{b}</p>")
        elif isinstance(b, Chip):
            parts.append(f"<p>{b.html(theme=theme, accent=accent)}</p>")
        elif callable(getattr(b, "html", None)):
            kw = {"theme": theme, **({"accent": accent} if accent is not None else {})}
            parts.append(f'<div class="mc-wide">{b.html(**kw)}</div>')
        else:
            raise ChipError(
                f"mintchip.document: block {i} is a {type(b).__name__}.",
                fix_hint="Pass HTML strings, plain strings, chips or mintchip.table(...) objects.",
            )
    if source:
        parts.append(f'<footer class="mc-src">Source: {html.escape(source)}</footer>')
    scheme = {"dark": "dark", "light": "light", "mono": "light"}.get(name)
    return _shell(title or "mintchip", "\n".join(parts), scheme, accent=accent, compact=compact)


def page(body: str, *, title: str = "mintchip") -> str:
    """A standalone page around one inline fragment (used by ``Chip.save(".html")``)."""
    return _shell(title, f"<p>{body}</p>", None)


def _shell(
    title: str,
    body: str,
    scheme: str | None,
    *,
    accent: str | None = None,
    compact: bool = False,
) -> str:
    cls = "mc-page mc-compact" if compact else "mc-page"
    attr = f' data-mc-scheme="{scheme}"' if scheme else ""
    style = css(accent) + (_COMPACT_CSS if compact else "")
    sync = f"\n<script>{_THEME_SYNC_JS}</script>" if compact and scheme is None else ""
    return (
        f'<!doctype html>\n<html lang="en" class="{cls}"{attr}>\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<meta name="color-scheme" content="{scheme or "light dark"}">\n'
        f"<title>{html.escape(title)}</title>\n<style>{style}</style>\n</head>\n"
        f'<body>\n<main class="mc-doc">\n{body}\n</main>{sync}\n</body>\n</html>\n'
    )
