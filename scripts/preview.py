"""Dev tool: one static HTML page for judging chips at 1x, light and dark.

    python scripts/preview.py [KIND ...] --out page.html [--specs specs.json]

For each kind (default: every registered kind, in catalog order) and each extra spec in the
JSON list (``[{"chip": "spark", "values": [...]}, ...]``), the page shows the chip inside a
15 px sentence on a light and a dark panel styled by ``mintchip.css()`` (click a chip for its
popover), a 4x zoom, and the Unicode and ASCII text. Screenshot it at scale 1 to judge.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import mintchip as mc

CSS = """
body{margin:16px;font:13px/1.4 system-ui,sans-serif;color:#1A1D21;background:#F4F5F7}
.row{margin:0 0 14px}
.head{font:600 12px ui-monospace,monospace;margin:0 0 4px}
.head small{font-weight:400;color:#6B7280;overflow-wrap:anywhere}
.panels{display:flex;gap:8px}
.panel{flex:1 1 0;min-width:0;padding:8px 12px;border-radius:4px;overflow:hidden}
.sentence{font:15px/1.5 system-ui,sans-serif;margin:0}
.zoom{font-size:60px;line-height:1;margin:6px 0 0;height:72px;overflow:hidden}
pre{margin:4px 0 0;font:13px/1.35 ui-monospace,Menlo,monospace;white-space:pre-wrap;
overflow-wrap:anywhere}
.warn{color:#B87A00;margin:2px 0 0}
"""


def _row(title: str, chip: mc.Chip) -> str:
    spec = html.escape(json.dumps(chip.to_dict(), ensure_ascii=False))
    panels = []
    for scheme in ("light", "dark"):
        sentence = f"Across five seeds the result came to {chip.html()} and held steady."
        panels.append(
            f'<div class="panel mc-page" data-mc-scheme="{scheme}">'
            f'<p class="sentence">{sentence}</p>'
            f'<div class="zoom">{chip.svg()}</div></div>'
        )
    warn = "".join(f'<p class="warn">warning: {html.escape(w)}</p>' for w in chip.warnings)
    texts = html.escape(f"{chip.text()}\n{chip.text(ascii=True)}\n{chip.text(compact=True)}")
    return (
        f'<section class="row"><p class="head">{html.escape(title)} <small>{spec}</small></p>'
        f'<div class="panels">{"".join(panels)}</div><pre>{texts}</pre>{warn}</section>'
    )


def build(kinds: list[str], specs: list[dict]) -> str:
    rows = [_row(k, mc.REGISTRY[k].example_chip()) for k in kinds]
    rows += [_row(f"{s['chip']} (spec)", mc.from_dict(s)) for s in specs]
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>mintchip preview</title>'
        f"<style>{mc.css()}{CSS}</style><body>{''.join(rows)}</body></html>\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("kinds", nargs="*", help="kinds to show (default: all registered)")
    ap.add_argument("--out", required=True, help="HTML file to write")
    ap.add_argument("--specs", help="JSON file with a list of extra chip specs")
    a = ap.parse_args(argv)
    unknown = [k for k in a.kinds if k not in mc.REGISTRY]
    if unknown:
        ap.error(f"unknown kind(s): {', '.join(unknown)}; registered: {', '.join(mc.REGISTRY)}")
    kinds = a.kinds or [e["name"] for e in mc.CATALOG]
    specs = json.loads(Path(a.specs).read_text(encoding="utf-8")) if a.specs else []
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(kinds, specs), encoding="utf-8")
    print(f"wrote {out} ({len(kinds)} kinds, {len(specs)} specs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
