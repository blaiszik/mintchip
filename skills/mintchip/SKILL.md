---
name: mintchip
description: "Turn numbers with shape into word-sized graphics (sparklines, confidence intervals, before/after deltas, pass/fail strips, distributions, shares, shared-scale tables) in text, Markdown or HTML with one zero-dep shell command. Use when reporting results, benchmarks, test runs, timings, diffs, or comparisons. Do NOT use for routine code edits, bug fixes, refactoring, stack traces, or 1-3 bare scalars with no shape. Reach for mintfig when you need full multi-panel plots, 2D relationships, publication plates, or Matplotlib auditing."
---

# mintchip: numbers with shape, from one shell command

mintchip prints numbers as word-sized graphics for a sentence or a table cell, as text,
Markdown or HTML. The number comes first, so the sentence reads even without the glyph.

## When to use a chip
- Give numbers with shape a chip (trend, interval, before/after, pass/fail, share) right after
  the words it supports.
- A number with no shape is just a number: write 0.82. One chip per sentence is normal;
  two is the ceiling. Three or more comparable values make a table (`mintchip table`).
- Do NOT use for routine code edits, bug fixes, refactoring, stack traces, or 1–3 bare scalars
  with no shape.
- Use `mintchip` for inline chips & zero-dep terminal/Markdown/PR tables; reach for `mintfig`
  for multi-panel plots, 2D relationships, publication plates, or Matplotlib auditing.

## Pick a chip by what you have
| You have | Directive | Prints |
|---|---|---|
| One number, no context | `{{num 0.82 pm=0.03}}` | `0.82 ± 0.03` |
| A series over time or steps | `{{spark 1.84 1.32 0.96 0.74 0.61 0.52 0.46 0.43 0.42 band=0.38:0.48}}` | `0.42 (range 0.42 to 1.84) █▆▄▃▂▂▁▁▁` |
| An estimate with an interval | `{{ci 0.08 0.05:0.11 level=0.95}}` | `+0.08 (95% CI +0.05 to +0.11) [·│···├─●─┤·]` |
| Raw samples of one measurement | `{{dist 18.9 19.4 19.8 20.1 20.3 20.3 20.9 21.6 22.8 47.8 unit=ms}}` | `med 20.3 ms (n=10, IQR 19.9 to 21.4) [▃▃▃█·▃▃··▃]→47.8` |
| A value against a total | `{{bar 0.82 target=0.9}}` | `82% (target 90%) ██████▌│` |
| A reading with a normal range | `{{gauge 7.38 7.35:7.45}}` | `7.38 (normal 7.35 to 7.45) [···├●───┤··]` |
| A before and an after value | `{{delta 0.74 0.82 higher_is_better=true}}` | `0.74→0.82 (+0.08) [··○────●··]` |
| A pass/warn/fail/skip result per item | `{{strip true true true warn true false true null}}` | `5/8 pass (1 fail, 1 warn, 1 skip) ███▄█×█·` |
| Parts of a whole | `{{share code=62 docs=28 tests=10}}` | `62·28·10% ██████▏███▏█` |
| A count out of a total, or a probability | `{{ratio 3 10}}` | `3/10 ●●●○○○○○○○` |
| Durations of phases | `{{timeline fetch=1.2 solve=4.8 write=1.5}}` | `7.5 s (solve 64%) ██▏██████▏██` |
| A position in a ranked field | `{{rank 2 18}}` | `#2/18 [········●·]` |
| Signed contributions from a start to a total | `{{waterfall retrieval=0.13 reranker=0.08 "latency cap"=-0.02 start=0.63}}` | `0.63 +0.13 +0.08 −0.02 = 0.82` |
| Counts through ordered stages | `{{funnel visited=1200 "signed up"=520 activated=350 retained=290}}` | `1,200 → 520 → 350 → 290 (24%)` |
| Three or more of the same thing | `mintchip table` (below) | |

Reading the glyphs: a spark's number is its latest value (the full form adds the range);
strip `█` pass, `▄` warn, `×` fail, `·` skip; ci `●` when the interval excludes the reference
`│`, `○` when it crosses it.

## One grammar for commands and directives
`mintchip spark 1.84 0.96 0.42 --band 0.38:0.48` is the directive
`{{spark 1.84 0.96 0.42 band=0.38:0.48}}`. Values fill the chip's slots in order; options
are `--name value` on the command line and `name=value` in a directive.
- numbers: spaces or commas; `null` or `nan` is a gap; negatives work: `-0.2`
- ranges: `lo:hi`, e.g. `0.05:0.11`
- named parts: `name=value` (`"signed up"=520`); spans: `name=start:end`
- results: `pass warn fail skip`, or `true false null`
- flags: `--higher-is-better` / `--no-higher-is-better`; `higher_is_better=true` in a directive
- `label` and `unit` work on most chips; quote text with spaces: `--label 'Val loss'`,
  `label="Val loss"`, `unit=ms`
- all options of a chip: `mintchip KIND --help`

## 1. One chip
```
$ mintchip ci 0.08 0.05:0.11 --level 0.95 --label 'Retrieval lift'
+0.08 (95% CI +0.05 to +0.11) [·│···├─●─┤·]
```

## 2. A whole message: render
```
$ mintchip render - <<'EOF'
Val loss settled at {{spark 1.84 1.32 0.96 0.74 0.61 0.52 0.46 0.43 0.42 band=0.38:0.48}}, and retrieval lifted accuracy by {{ci 0.08 0.05:0.11 level=0.95}}.
EOF
Val loss settled at 0.42 (range 0.42 to 1.84) █▆▄▃▂▂▁▁▁, and retrieval lifted accuracy by +0.08 (95% CI +0.05 to +0.11) [·│···├─●─┤·].
```
Text outside `{{…}}` is copied unchanged (`\{{` is a literal `{{`). A file works in
place of `-`. `--check` also flags too many chips per sentence.

## 3. A table
```
$ mintchip table - --col model --col acc:bar --col lift:ci --col loss:spark --set lift.level=0.95 --sort acc <<'EOF'
[
{"model": "retrieval", "acc": 0.82, "lift": [0.08, 0.05, 0.11], "loss": [1.84, 0.96, 0.42]},
{"model": "warmup", "acc": 0.75, "lift": [0.01, -0.02, 0.04], "loss": [1.8, 1.3, 0.7]},
{"model": "baseline", "acc": 0.74, "lift": null, "loss": [1.85, 1.4, 0.78]}
]
EOF
model      acc           lift                 loss
                               −0.03   +0.13
──────────────────────────────────────────────────────
retrieval  82% ██████▌·  +0.08 [··│··├─●─┤·]  0.42 █▄▁
warmup     75% ██████··  +0.01 [·├┼○┤······]  0.70 █▅▂
baseline   74% █████▉··   —                   0.78 █▆▃
```
Rows: a JSON list of objects or CSV, from a file or `-`. `--col KEY[:KIND[:HEADER]]` in order;
KIND is any chip name above or `text` (left out: inferred). A `ci` cell is `[estimate, low,
high]`; each chip column shares one scale. `--set KEY.OPTION=VALUE` applies to a whole column,
e.g. `--set KEY.unit=s`. `--sort KEY` (largest first, text A to Z; `--asc` or `--desc` to
choose), `--limit N`.

## Output & errors
`--format text|md|ansi|html|svg|json`, `--ascii`, `--compact`. stdout holds only the result.
Errors go to stderr (`mintchip: error: …` + `fix:`, exit 2). Warnings (`mintchip: warning: …`,
exit 0; exit 1 with `--strict`) flag distortions like clipped outliers.

More: `mintchip from`, `mintchip diff`, `mintchip doctor`, `mintchip skill`, `mintchip schema`,
`mintchip catalog`, or `python -m mintchip`.
