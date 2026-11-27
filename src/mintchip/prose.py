"""Prose with chips in it: ``format_prose`` fills ``{name}`` placeholders, ``lint`` checks
density (one chip per sentence is normal, two is the ceiling, three comparable values make a
table) and collects the chips' own warnings."""

from __future__ import annotations

import html
import re
from collections.abc import Iterable, Mapping
from typing import Any

from .spec import Chip, ChipError, sibling_domain

__all__ = ["FORMATS", "format_prose", "lint", "shared_domains"]

FORMATS = ("text", "markdown", "md", "ansi", "html")
_SLOT = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=[.!?][\"')\]”’])\s+")
_PARAGRAPH = re.compile(r"\n[ \t]*\n")
_NUM = re.compile(r"[-+−]?\d[\d,]*(?:\.\d+)?%?")
Domain = tuple[float, float]


def format_prose(
    template: str,
    *,
    format: str = "text",
    ascii: bool = False,
    compact: bool = True,
    color: bool = False,
    share: Any = "auto",
    theme: Any = "auto",
    **chips: Chip,
) -> str:
    """Replace each ``{name}`` in ``template`` with the chip passed as ``name=``.

    ``format`` is "text", "ansi" (text with colour), "markdown" (chips in code spans) or
    "html" (prose escaped, chips from ``Chip.html``). ``ascii`` and ``color`` apply to the
    text forms, ``theme`` to html. ``compact`` gives the short mid-sentence value.

    ``share="auto"`` puts chips of one kind with the same non-empty unit on one scale;
    ``share=[("a", "b"), ...]`` names the groups; ``share=False`` leaves each chip its own.
    """
    if format not in FORMATS:
        raise ChipError(
            f"mintchip.format_prose: unknown format {format!r}.",
            fix_hint=f"Use one of: {', '.join(FORMATS)}.",
        )
    fmt_name = "markdown" if format == "md" else format
    _check_chips("format_prose", chips)
    used = list(dict.fromkeys(_SLOT.findall(template)))
    missing = [n for n in used if n not in chips]
    if missing:
        raise ChipError(
            f"mintchip.format_prose: no chip for {{{missing[0]}}}.",
            fix_hint=f"Pass {missing[0]}=mintchip.<kind>(...), or reword the placeholder.",
        )
    domains = shared_domains(chips, share, used=used)
    out = []
    for i, piece in enumerate(_SLOT.split(template)):
        if i % 2:
            out.append(_render(chips[piece], domains.get(piece), fmt_name, ascii, compact, color,
                               theme))  # fmt: skip
        else:
            out.append(html.escape(piece, quote=False) if fmt_name == "html" else piece)
    return "".join(out)


def _render(c: Chip, domain, format: str, ascii: bool, compact: bool, color: bool, theme) -> str:
    if format == "html":
        return c.html(theme=theme, compact=compact, domain=domain)
    if format == "markdown":
        t = c.text(ascii=ascii, compact=compact, domain=domain)
        return f"`` {t} ``" if "`" in t else f"`{t}`"
    return c.text(ascii=ascii, compact=compact, color=color or format == "ansi", domain=domain)


def _check_chips(fn: str, chips: Mapping[str, Any]) -> None:
    for name, c in chips.items():
        if not isinstance(c, Chip):
            raise ChipError(
                f"mintchip.{fn}: {name} is a {type(c).__name__}, not a chip.",
                fix_hint=f"Pass {name}=mintchip.<kind>(...); type plain values into the prose.",
            )


def shared_domains(
    chips: Mapping[str, Chip], share: Any = "auto", *, used: Iterable[str] | None = None
) -> dict[str, Domain]:
    """The share rule: the scale each grouped chip is drawn on, by name; a chip in no group is
    left out and keeps its own. ``share="auto"`` groups the chips of one kind with the same
    non-empty unit; ``share=[("a", "b"), ...]`` names the groups; ``share=False`` makes none.
    A group's scale is the union of its chips' own. ``used`` limits ``"auto"`` to the chips
    a template actually places (default: all of them)."""
    if share is False or share is None:
        return {}
    if share == "auto" or share is True:
        by_key: dict[tuple[str, str], list[str]] = {}
        for n in chips if used is None else used:
            c = chips[n]
            if c.unit and c._domain(None) is not None:
                by_key.setdefault((c.kind, c.unit), []).append(n)
        groups = list(by_key.values())
    else:
        groups = _explicit_groups(share, chips)
    out: dict[str, Domain] = {}
    for group in groups:
        if len(group) > 1:
            d = sibling_domain(chips[group[0]].kind, (chips[n]._domain(None) for n in group))
            if d is not None:
                out.update(dict.fromkeys(group, d))
    return out


def _explicit_groups(share: Any, chips: Mapping[str, Chip]) -> list[list[str]]:
    hint = 'Pass share="auto", share=False, or groups of chip names: share=[("a", "b")].'
    if isinstance(share, (str, bytes)) or not isinstance(share, Iterable):
        raise ChipError(f"mintchip.format_prose: share must be groups; got {share!r}.",
                        fix_hint=hint)  # fmt: skip
    groups, seen = [], set()
    for g in share:
        if isinstance(g, (str, bytes)) or not isinstance(g, Iterable):
            raise ChipError(f"mintchip.format_prose: share group {g!r} is not a list of names.",
                            fix_hint=hint)  # fmt: skip
        g = list(g)
        for n in g:
            if n not in chips:
                raise ChipError(f"mintchip.format_prose: share names {n!r}, which is not a chip.",
                                fix_hint=f"Name chips passed as keywords: {', '.join(chips)}.")  # fmt: skip
            if n in seen:
                raise ChipError(f"mintchip.format_prose: {n!r} is in two share groups.",
                                fix_hint="Put each chip in at most one group.")  # fmt: skip
            seen.add(n)
        kinds = {chips[n].kind for n in g}
        if len(kinds) > 1:
            raise ChipError(
                f"mintchip.format_prose: share group {g} mixes kinds ({', '.join(sorted(kinds))}).",
                fix_hint="Share a scale only among chips of one kind.",
            )
        if any(chips[n]._domain(None) is None for n in g):
            raise ChipError(
                f"mintchip.format_prose: {chips[g[0]].kind} chips have no scale to share.",
                fix_hint="Leave them out of share=; only position and series chips share a scale.",
            )
        groups.append(g)
    return groups


# --- lint -----------------------------------------------------------------------------------
def lint(
    template: str,
    chips: Mapping[str, Chip],
    *,
    share: Any = "auto",
    written: Mapping[str, tuple[str, str]] | None = None,
) -> list[str]:
    """Density problems in ``template``, then each placed chip's own warnings, one message
    per line, each saying what to do instead. An empty list means nothing to fix. ``share``
    is ``format_prose``'s: the warnings are those that hold on the scale each chip is drawn
    on there. ``written`` maps a placeholder name to the text it stands for and where that
    is (``mintchip render --check`` passes each directive and its line:column), so a crowded
    sentence is quoted as its writer wrote it, with the locations after the quote."""
    _check_chips("lint", chips)
    used = list(dict.fromkeys(n for n in _SLOT.findall(template) if n in chips))
    domains = shared_domains(chips, share, used=used)
    msgs: list[str] = []
    for p, para in enumerate(_PARAGRAPH.split(template), 1):
        for sentence in _SENTENCE_END.split(para):
            slots = [n for n in _SLOT.findall(sentence) if n in chips]
            if len(slots) > 2:
                shown, at = sentence, ""
                if written:
                    shown = _SLOT.sub(lambda m: written.get(m[1], (m[0],))[0], sentence)
                    places = [written[n][1] for n in slots if n in written]
                    at = f" (at {', '.join(places)})" if places else ""
                msgs.append(
                    f"{_quote(shown)} has {len(slots)} chips{at}; keep one or two per "
                    "sentence, or use a table."
                )
            msgs += _typed_copies(sentence, slots, chips)
        by_kind: dict[str, list[str]] = {}
        for n in dict.fromkeys(_SLOT.findall(para)):
            if n in chips:
                by_kind.setdefault(chips[n].kind, []).append(n)
        for kind, names in by_kind.items():
            if len(names) >= 3:
                listed = ", ".join(f"{{{n}}}" for n in names)
                msgs.append(
                    f"Paragraph {p} has {len(names)} {kind} chips ({listed}); put comparable "
                    "values in a table."
                )
    for n in used:
        msgs += [f"{{{n}}}: {w}" for w in chips[n].warnings_for(domains.get(n))]
    return msgs


def _typed_copies(sentence: str, slots: list[str], chips: Mapping[str, Chip]) -> list[str]:
    """A num chip next to the same number typed by hand says it twice."""
    typed = _NUM.findall(_SLOT.sub(" ", sentence))
    out = []
    for n in dict.fromkeys(slots):
        c = chips[n]
        if c.kind != "num":
            continue
        shown = _NUM.findall(c.text(compact=True))
        if not shown:
            continue
        copy = next((t for t in typed if _same(t, shown[0])), None)
        if copy is not None:
            out.append(f"{{{n}}} repeats the typed {copy} beside it; delete the typed number.")
    return out


def _same(a: str, b: str) -> bool:
    if a.endswith("%") != b.endswith("%"):
        return False

    def val(s: str) -> float:
        return float(s.rstrip("%").replace(",", "").replace("−", "-").lstrip("+"))

    return val(a) == val(b)


def _quote(sentence: str) -> str:
    s = " ".join(sentence.split())
    return f'"{s[:40]}…"' if len(s) > 41 else f'"{s}"'
