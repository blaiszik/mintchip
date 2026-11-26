"""Command-line interface for ``mintchip``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import mintchip as mc


def _demo_chips(style: str = "default", palette: str | None = None) -> dict[str, mc.Chip]:
    ci_dom = mc.shared_domain((0.05, 0.11), (-0.024, 0.048), reference=0.0)
    delta_dom = mc.shared_domain(0.65, 0.88)
    samples_q = [
        14.2, 16.0, 17.5, 18.1, 18.9, 19.3, 19.8, 20.1, 20.6, 21.0,
        21.4, 21.9, 22.3, 22.8, 23.4, 24.1, 24.8, 26.2, 28.5, 31.4,
    ]
    xs = [1.0, 1.8, 2.5, 3.3, 4.1, 4.9, 5.8, 6.6, 7.5, 8.4, 9.2, 10.0]
    ys = [1.8, 2.9, 2.3, 4.6, 3.8, 5.9, 5.2, 7.6, 6.7, 8.9, 8.2, 9.8]
    kw = {"style": style, "palette": palette}
    return {
        "spark": mc.spark(
            [1.84, 1.32, 0.96, 0.74, 0.61, 0.52, 0.46, 0.43, 0.42],
            label="Val loss", band=(0.38, 0.48), reference=0.45, **kw,
        ),
        "ci": mc.ci(
            0.08, (0.05, 0.11), inner_error=(0.07, 0.09),
            error_label="95% CI, 5 seeds", reference=0.0, domain=ci_dom,
            label="Retrieval lift", **kw,
        ),
        "dist": mc.dist(
            [18.2, 19.1, 19.4, 19.8, 20.0, 20.3, 20.6, 21.1, 21.4, 22.0, 47.8],
            label="Shard p95", unit="ms", reference=25.0, **kw,
        ),
        "bar": mc.bar(
            0.82, total=1.0, baseline=0.74, target=0.80, bands=(0.60, 0.80),
            label="Accuracy", **kw,
        ),
        "strip": mc.strip(
            [True, True, True, "warn", True, False, True, "skip"],
            labels=[f"seed_{i}" for i in range(8)], label="Repro seeds", **kw,
        ),
        "delta": mc.delta(0.74, 0.82, label="Accuracy", domain=delta_dom, **kw),
        "waterfall": mc.waterfall(
            {"Fine-tuning": 0.13, "Retrieval": 0.08, "Int4 quant": -0.02},
            start=0.63, label="Ablation bridge", **kw,
        ),
        "scatter": mc.scatter(
            xs, ys, highlight=9, names=[f"m{i}" for i in range(12)],
            fit=True, label="Scaling law", x_label="Compute", y_label="Score", **kw,
        ),
        "share": mc.share(
            {"Weights": 62, "KV cache": 28, "Activations": 10},
            label="GPU memory", unit="GB", **kw,
        ),
        "funnel": mc.funnel(
            {"Screened": 1200, "Eligible": 520, "Enrolled": 350, "Completed": 290},
            label="Cohort", **kw,
        ),
        "ratio": mc.ratio(3, 10, label="Responder rate", **kw),
        "gauge": mc.gauge(7.38, (7.35, 7.45), warn=(7.30, 7.50), label="Blood pH", **kw),
        "quantiles": mc.quantiles(
            samples_q, threshold=25.0, n_dots=10, unit="ms", label="Tail forecast", **kw,
        ),
        "evidence": mc.evidence(p=0.002, n=48, label="Drug vs placebo", **kw),
        "timeline": mc.timeline(
            {"fetch": 1.2, "solve": 4.8, "verify": 1.5}, unit="s", label="Agent turn", **kw,
        ),
        "rank": mc.rank(2, 18, label="MMLU-Pro", **kw),
        "dual_spark": mc.dual_spark(
            [1.40, 1.05, 0.80, 0.62, 0.51, 0.45, 0.42],
            [1.42, 1.10, 0.88, 0.74, 0.66, 0.62, 0.61],
            labels=("train", "val"), label="Loss gap", **kw,
        ),
    }


def _cmd_catalog(args: argparse.Namespace) -> int:
    chips = _demo_chips()
    if args.json:
        payload = [
            {
                **entry,
                "text": chips[entry["name"]].to_text(ascii_only=args.ascii),
                "facts": chips[entry["name"]].facts,
            }
            for entry in mc.CATALOG
        ]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(f"mintchip {mc.__version__} — {len(mc.CATALOG)} word-sized visual chips\n")
    for entry in mc.CATALOG:
        name = entry["name"]
        fam = entry["family"]
        preview = chips[name].to_text(ascii_only=args.ascii)
        print(f"  {fam:<11}  {name:<11}  {preview}")
    return 0


def _cmd_demo(args: argparse.Namespace) -> int:
    chips = _demo_chips(style=args.style, palette=args.palette)
    template = (
        "Across 5 seeds, training settled into the target loss band at {spark}, lifting accuracy "
        "to {bar} ({delta}) via {waterfall}, with retrieval contributing {ci} and compute scaling "
        "at {scatter}.\n\n"
        "VRAM splits {share}; cohort screening retained {funnel} with {ratio} responders, pH "
        "stayed centered at {gauge}, tail breach risk is {quantiles}, and primary support rates "
        "{evidence}. Shard latency clusters at {dist}, repro checks show {strip}, each turn took "
        "{timeline}, placing our model {rank} while train/val curves end at {dual_spark}."
    )
    if args.html:
        p1, p2 = template.split("\n\n")
        html_doc = mc.document(
            "mintchip — Word-Sized Visual Chips Demo",
            [
                mc.format_prose(p1, mode="html", compact=True, **chips),
                mc.format_prose(p2, mode="html", compact=True, **chips),
            ],
            subtitle="Click any inline chip to inspect its computed facts.",
            source=f"mintchip {mc.__version__} CLI demo",
            style=args.style,
            palette=args.palette,
        )
        out_path = Path(args.html)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_doc, encoding="utf-8")
        print(f"Wrote interactive HTML demo to {out_path}")
        return 0

    print(mc.format_prose(template, mode="text", compact=True, ascii_only=args.ascii, **chips))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mintchip",
        description="Zero-dependency word-sized visual chips for AI agents, scientists, and prose.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_cat = sub.add_parser("catalog", help="List all 17 chips with live terminal previews.")
    p_cat.add_argument("--ascii", action="store_true", help="Use pure ASCII glyphs.")
    p_cat.add_argument("--json", action="store_true", help="Emit structured JSON catalog.")
    p_cat.set_defaults(func=_cmd_catalog)

    p_demo = sub.add_parser("demo", help="Print a prose demo or write an interactive HTML note.")
    p_demo.add_argument("--ascii", action="store_true", help="Use pure ASCII glyphs.")
    p_demo.add_argument("--html", type=str, default=None, help="Write standalone HTML to path.")
    p_demo.add_argument("--style", type=str, default="default", choices=sorted(mc.THEMES))
    p_demo.add_argument("--palette", type=str, default=None, choices=sorted(mc.PALETTES))
    p_demo.set_defaults(func=_cmd_demo)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
