# mintchip presentation plan

Written 2026-11-25 against `b16bb13` (v0.1.0, 17 chips, no outside users yet).

## The goal

An agent that has numbers should be able to say them with shape, in one tool call, on whatever
surface it is writing to, and the result should read as prose with evidence in it — not as a row
of badges.

Three tests decide whether a change belongs in this plan:

1. **1× test.** The chip is judged at its real size inside a real sentence, never zoomed.
2. **Beats-the-number test.** If the glyph or graphic says less than the bare numbers would, print
   the numbers.
3. **One-call test.** An agent with data in hand gets a finished sentence or table from a single
   shell command, without writing Python.

## What I found

Everything below was checked by running the code or looking at renders, except the two rows
marked *unverified*.

| # | Finding | Where |
|---|---------|-------|
| 1 | The demo is itself a wall: 17 bordered pills in two paragraphs. The pill border, tinted fill, bold value and 0.92em font are all non-data ink, and they outweigh the graphics inside them. | `core.py:375` |
| 2 | At 1× several chips are specks: `quantiles` dots, `rank` ticks, the `ci` reference line, the `gauge` bands. They only read when zoomed 4×. | all chip modules |
| 3 | One outlier flattens `dist`: ten points become a single blob at the left edge so that 47.8 can sit on the same linear scale. | `core.py:908` |
| 4 | Text sparklines drop spikes. Forty points with one value of 50 render as `▁▁▁▁▁▁▁▁▁▁▁▁▁▁`, because downsampling picks every k-th point. | `core.py:593` |
| 5 | `spark` has no `domain=`, so two sparklines in one sentence can never share a y-scale: `[1,2,3,4]` and `[100,200,300,400]` render identically, and 0.4200→0.4206 looks like a steep climb. | `core.py:461` |
| 6 | Shared scales are opt-in and must be computed before the chips exist, because each chip bakes its SVG at construction. A table column cannot impose a scale afterwards. | `core.py:192`, `core.py:270` |
| 7 | Theme is baked in as hex at construction. An agent does not know whether its reader is in light or dark mode, and every dark asset is a duplicate file. | `themes.py`, `gallery/output/chips/*_dark.svg` |
| 8 | Sizes are fixed pixels in 12 different width × height combinations (heights 13, 14 and 16). Chips do not scale with the surrounding font. | `core.py:620` |
| 9 | Red carries eight meanings: latest point (`spark`), negative step (`waterfall`), fail (`strip`), outlier (`dist`), second category (`share`), steepest drop (`funnel`), highlight (`scatter`), past threshold (`quantiles`). | all chip modules |
| 10 | Text glyphs follow no single grammar: `spark`, `bar` and `strip` are bare, `dist` uses `│…│`, the rest use `[…]`. Several are undecodable without a legend: `[▲█▲▅▼▂]`, `[⣀⡤⠢⠊⠊]`, `[▂▃▄▅▇▇█]` for a two-series gap. | all chip modules |
| 11 | `share` and `timeline` separate segments with `▓▒░`, which are moiré textures. `delta` uses `▶`, which can render as an emoji. | `composition.py:41`, `structure.py:43`, `change.py:301` |
| 12 | `--ascii` output is not ASCII: `→`, `–` and `Δ` leak through in `delta`, `gauge` and `dual_spark`. | value formatting |
| 13 | `evidence` turns a p-value into a five-bar signal meter. p=0.049 with n=8 reads "moderate ▰▰▰▱▱"; p=0.051 with n=5000 reads "weak ▰▱▱▱▱". | `evidence.py:149` |
| 14 | Details-on-demand is a full-screen modal that needs JavaScript and mostly repeats the number already visible. | `core.py:1544` |
| 15 | Agent friction: the only path is write Python → construct chips → `format_prose` → run → copy. The CLI has `catalog` and `demo` only. `chip.warnings` never surfaces unless inspected. `repr(chip)` dumps about 1.6 KB of SVG. `bar(1.4, total=1.0)` clips silently. `ci("a", 1)` raises a bare `ValueError`. Error messages still say `inline.spark`. | `cli.py`, `core.py` |
| 16 | Six presentation parameters (`width`, `height`, `style`, `palette`, `accent`, `expand`) repeat on all 17 functions; 6 themes × 6 palettes is 36 looks for a 16-pixel graphic. | all signatures |
| 17 | *Unverified:* `shared_domain` appears to silently ignore NumPy arrays, since `ndarray` is not a `collections.abc.Sequence`. NumPy is not in the dev environment, so I read this from the code only. | `core.py:205` |
| 18 | *Unverified:* GitHub strips `data:` image sources from rendered Markdown, which would make `markdown(mode="svg_uri")` useless on the surface that matters most. Needs a one-file test in a gist. | `core.py:309` |

## Design rules

These are the rules every later section applies. They go into the README and the agent guide
verbatim.

1. **Bare by default.** A chip is a number set in the text's own type, followed by a graphic with
   no frame, fill or border. Interactivity shows as a dotted underline on hover, not a button.
2. **Design at 1×.** At most three kinds of mark per chip. Minimum stroke 1.25 px, minimum dot
   radius 1.75 px at a 16 px line. If a chip needs more, it is a figure, not a word.
3. **Ink has four roles, and red has one.** *Data* (the text colour), *context* (the text
   colour at reduced opacity, for bands, axes and references), *accent* (blue, meaning "look
   here": the latest point, the highlighted item), and *good/bad/warn* (used only when the
   caller has declared a direction with `higher_is_better`, or the data is literally
   pass/warn/fail). Red means bad and nothing else. Parts of a whole use one hue in opacity
   steps, never categorical colours.
4. **Comparable things share a scale automatically.** Chips in one table column, or passed as a
   group to one sentence, get one domain without the caller computing it.
5. **Number first, glyph second, and the number is always enough.** A reader who sees only the
   number loses the shape, never the fact.
6. **If the glyph cannot beat the numbers, print the numbers.**
7. **Three or more comparable values make a table, not a sentence.** One chip per sentence is
   normal, two is the ceiling.
8. **Distortions are announced.** A clipped outlier, a truncated axis, a downsampled series or a
   y-range under 2 % of the value shows a mark in the chip and a line in `warnings`.

## Work, in order

### 1. Split what a chip is from how it is drawn

This is the foundation; rules 4 and 7 are impossible without it.

- `Chip` becomes a small frozen record: `kind`, validated data, computed statistics, `facts`,
  `warnings`. No SVG, no theme.
- Rendering moves to methods that take the surface's options: `chip.text()`, `chip.svg()`,
  `chip.html()`, `chip.markdown()`. Width, theme and domain are render arguments, so a container
  can override the domain at render time.
- `chip.to_dict()` and `Chip.from_dict()` round-trip through JSON. This one format drives the
  CLI, the table, and any later JavaScript renderer.
- Chip functions lose `width`, `height`, `style`, `palette`, `accent` and `expand`. What remains
  is data and meaning: `label`, `unit`, `reference`, `band`, `domain`, `higher_is_better`.
- `repr(chip)` prints one line: kind, value, text glyph.
- Remove the mintfig residue: `ExplainError`, `InlineGraphic`, `mf-` class names,
  `__mintfigInlineInit`, `inline.*` in messages. The mintfig bridge (`expand=`) is removed;
  `chip.html(detail=…)` accepts any caller-supplied HTML for the details popover, which covers
  a mintfig figure without coupling the two packages.
- One file per chip (`chips/<kind>.py`: constructor, text renderer, SVG renderer), registered
  with its parameters and an example. The CLI, JSON Schema, guide, catalog, gallery and golden
  tests are all generated from that registry.

Done when: all chips construct with no theme argument, `Chip.from_dict(c.to_dict()).text() ==
c.text()` for every chip, and import stays under 15 ms.

### 2. Redraw the SVG layer

- **Colour follows the reader.** Inline SVG uses `currentColor` for data ink and CSS custom
  properties with fallbacks for the rest (`var(--mc-accent, #C8321E)`). Standalone `.svg` files
  carry an embedded `<style>` with a `prefers-color-scheme` rule, so one file serves both modes
  and the `_dark.svg` duplicates go away.
- **Size follows the font.** One height, `1em`, and three widths (`2.5em`, `4.5em`, `6.5em`),
  set as `em` on the `<svg>` with a fixed `viewBox`.
- **Themes shrink to four**: `auto` (default, described above), and static `light`, `dark` and
  `mono` for renderers that do not support CSS variables. A custom `accent` works in any of
  them. Palettes are removed.
- **Apply rule 3** chip by chip. `share` becomes one hue in opacity steps with thin gaps
  between segments. `spark` marks its end-point in the accent colour. (Tufte's end-point is
  red; here red is reserved for "bad", so the accent is blue.)
- **Apply rule 2.** Drop the hollow start anchor and interior extrema dots from `spark` unless
  asked for; thicken the `ci` reference line; cut `rank` to one ruler and one dot.
- **Robust scales.** `dist` clips outliers beyond 3 × IQR to an edge marker with the value in
  the tooltip and a warning. `spark` gains `domain=` and a low-variation marker (rule 8).
- **Machine-readable.** Every SVG carries its facts in `<desc>` and its spec in a `data-mc`
  attribute, so an agent reading the HTML gets the data back.

Done when: a screenshot of every chip at 1× in a 15 px paragraph, light and dark, passes a
written checklist (every mark visible, no chip taller than the line, no colour used outside its
role), and the screenshots are committed as the visual baseline.

### 3. One text grammar

| Rule | Before | After |
|------|--------|-------|
| No brackets around a run of marks; brackets only around an axis with ends | `[▓▓██████▒▒]` | `██▏██████▏██` |
| Segments separated by gaps, never textures | `62/28/10% [██████▓▓▓░]` | `62·28·10% ██████▏███▏█` |
| Numbers when the glyph loses | `+0.19 [▲█▲▅▼▂]` | `0.63 +0.13 +0.08 −0.02 = 0.82` |
| | `24% [█▄▃▃]` | `1,200 → 520 → 350 → 290 (24%)` |
| Safe glyphs only: `▁`–`█`, `▏`–`▉`, `─│├┤`, `●○`, `·` | `[····○─▶●···]` | `[····○──●···]` |
| Downsampling keeps the minimum and maximum of each bucket | `▁▁▁▁▁▁▁▁▁▁▁▁▁▁` | `▁▁█▁▁▁▁▁▁▁▁▁▁▁` |
| ASCII means ASCII | `0.74→0.82 [....o->*...]` | `0.74->0.82 [....o->*...]` |

The final glyph choices are settled by a font matrix, not by taste: render every chip in a
monospace terminal, GitHub Markdown, Slack and a proportional chat font, and keep only glyphs
that hold their width and never turn into emoji.

Text gets a third tier, ANSI colour, for terminals: the same glyphs with the four ink roles.

Done when: golden-text snapshot tests cover every chip in Unicode and ASCII, `text(ascii=True)
.isascii()` holds for every chip, and the spike test above passes.

### 4. Change the chip set: 17 → 13 chips, plus a table

| Chip | Decision | Reason |
|------|----------|--------|
| `spark` | Keep; absorbs `dual_spark` as `spark(a, vs=b)` | One trajectory idea, one function. |
| `ci` | Keep | The best chip in the set; solid/hollow dot is the model for redundant encoding. |
| `dist` | Keep; absorbs `quantiles` via `threshold=` | Both answer "how is it spread"; the dotplot is a rendering choice by n. |
| `bar` | Keep; mark overflow instead of clipping | Bullet graph. |
| `gauge` | Keep | Position inside a normal range is not length from zero. |
| `strip` | Keep | Pass/fail history is the most common thing coding agents report. |
| `delta` | Keep | |
| `share` | Keep; redrawn (rule 3) | |
| `ratio` | Keep | Natural frequencies are the right way to say a probability. |
| `timeline` | Keep; redrawn without textures | |
| `rank` | Keep; simplified | |
| `waterfall` | Keep in SVG; text prints the signed sum | Rule 6. |
| `funnel` | Keep in SVG; text prints the stage counts | Rule 6. |
| `scatter` | **Remove** from inline chips | Two dimensions do not fit in a word; five Braille cells are not a scatterplot. Text falls back to `r=0.96, n=12`; the plot belongs to mintfig. |
| `evidence` | **Remove** | It re-encodes a p-value as a signal-strength icon (finding 13). `ci` shows effect size and uncertainty, which is the honest version. |
| `dual_spark`, `quantiles` | **Merge** (above) | |
| `num` | **Add** | A formatted number with unit, significant figures and optional ± — the chip for values with no shape, and the cell formatter for tables. |
| `table` | **Add** (next section) | |

### 5. Tables: small multiples

Most agent results are several things compared on the same measure, which rule 7 sends to a
table. This is the largest single improvement to "more visual than a wall of text".

```python
mc.table(
    rows,                                   # list of dicts, or a CSV/JSON path
    columns={"acc": "bar", "lift": "ci", "loss": "spark"},
    sort="acc",
)
```

- Each column gets one domain and one reference line running down it; a column of `ci` chips is
  a forest plot with no extra work.
- Numbers align on the decimal point. The scale's ends are printed once, in the header.
- Rules are thin and horizontal only; no cell borders, no zebra stripes.
- Three renders: aligned monospace for terminals, a GFM table with code-span glyphs, and HTML.

Sketch of the text render:

```text
model       acc              lift, 95% CI          val loss
                             −0.02   0     +0.11
retrieval   0.82 ████████▏     ·│···├──●──┤          ▇▅▃▂▁▁▁ 0.42
warmup      0.75 ███████▌      ├┼○─┤······           ▇▆▅▄▃▃▃ 0.61
```

Done when: the three renders exist, columns share scales with no caller arithmetic, and a
12-row table stays under 80 columns in text mode.

### 6. The agent interface

- **A subcommand per chip**, arguments in the order the function takes them:

  ```bash
  mintchip spark 1.84 1.32 0.96 0.74 0.61 --band 0.38:0.48
  ```

  ```bash
  mintchip ci 0.08 0.05:0.11 --label "95% CI, 5 seeds"
  ```

- **`mintchip render`** reads prose from stdin and replaces inline directives, so a whole message
  is one call:

  ```bash
  echo 'Loss settled at {{spark 1.84 1.32 0.96 band=0.38:0.48}}.' | mintchip render
  ```

- **`mintchip table results.json --col acc:bar --col lift:ci --sort acc`** for the table.
- **`--format text|ansi|md|svg|html|json`** on all of them; `text` is the default.
- **`mintchip guide`** prints the agent cheat-sheet in under 1,500 tokens: the data-shape table
  below, the density rules, and the three commands. **`mintchip schema`** prints the JSON Schema
  for every chip spec, ready to register as a tool definition.
- **Warnings go to stderr**; `--strict` turns them into a non-zero exit. `render --check` also
  lints density (more than two chips in a sentence, three or more comparable values in prose).
- **Errors** are always `ChipError` with a fix hint, including bad types and unknown options
  (with a nearest-name suggestion).
- **Inputs are forgiving**: anything iterable, including NumPy arrays and pandas Series, with a
  test for finding 17.
- **Ship the instructions**: `skills/mintchip/SKILL.md` for Claude Code, an `AGENTS.md` snippet,
  and `llms.txt`, all generated from `mintchip guide` so they cannot drift.

The data-shape table the guide is built on:

| You have | Use |
|----------|-----|
| One number, no context | `num` |
| A series over time or steps | `spark` |
| Two series over the same steps | `spark(a, vs=b)` |
| An estimate with an interval | `ci` |
| Raw samples | `dist` |
| A value against a total or target | `bar` |
| A value against a normal range | `gauge` |
| A before and an after | `delta` |
| Pass/fail per item | `strip` |
| Parts of a whole | `share` |
| k out of n | `ratio` |
| Durations of phases | `timeline` |
| A position in a field | `rank` |
| Signed contributions to a change | `waterfall` |
| Counts through stages | `funnel` |
| Three or more of the same thing | `table` |

Done when: a fresh agent given only the output of `mintchip guide` produces a correct chipped
sentence and a correct table in one command each.

### 7. Details on demand

- Replace the modal with an inline popover anchored to the chip, built on `<details>` so it
  works with JavaScript disabled; hover shows the `<title>`.
- Facts must add something the chip does not show (n, method, range, what the interval is).
  A fact that restates the visible value is deleted.
- `document()` gets a text-first layout: a 34 em measure, the page's own type, tables as in
  section 5, and chip CSS in one `<style>` block with classes instead of inline styles on every
  chip (now about 2.6 KB per chip, mostly repeated style).

### 8. Show it

- **README opens with a before/after**: a real agent message as a wall of text, then the same
  message with two chips and one table. Three such pairs: a test run, a benchmark comparison,
  an experiment summary.
- **The gallery becomes the documentation**: one page, each chip at 1× in a sentence, in a
  table, and in text, with the question it answers. The Keep/Refine/Drop workbench moves to a
  dev-only script.
- **Recipes for coding agents**, since they are the first users: test results, diff size,
  coverage, benchmark before/after, time per phase, context budget.
- **Tests that guard the presentation**: golden text, the 1× screenshot baseline, an SVG lint
  (nothing outside the viewBox, minimum mark sizes, colours only from the four roles), and the
  zero-dependency test that already exists.
- Resolve finding 18 before documenting any GitHub embedding path.

## Sequence

As built: sections 1–4 are done together, because porting a chip to the new record, redrawing
it and rewriting its text are one edit to one file, and there is no point porting chips that
section 4 removes.

1. Kernel: the chip record, registry, formatting, scales, themes, render bases, and three
   exemplar chips (`num`, `spark`, `ci`).
2. The other eleven chips, in parallel, one file each.
3. Table, CLI and guide, and HTML (details, `document()`, `format_prose()`), in parallel.
4. Gallery, README and the presentation tests.

## Not now

- A JavaScript renderer or `<mint-chip>` web component that draws the same JSON spec in chat
  interfaces. Worth doing once the spec has been stable for a release.
- An MCP server. `mintchip schema` plus the CLI covers the same ground with nothing to host.
- Block-level callouts (a large number with a sparkline). Wait to see whether tables leave a gap.
- Publishing to PyPI, which `uvx mintchip` depends on. Do it after section 6, when the CLI is
  the thing worth installing.

---

# Status after implementation (2026-11-25)

Sections 1–8 are implemented as v0.2.0.dev0. 845 tests pass, ruff is clean, `import mintchip`
takes about 12 ms with cached bytecode, and the generated files (README blocks, gallery,
`skills/mintchip/SKILL.md`, `llms.txt`, golden text) match their generators. Nothing is
committed.

## The three tests

| Test | Result |
|------|--------|
| 1× test | Every chip was judged by eye in a 15 px sentence on white and on `#14181F` (`gallery/output/baseline.html` is the page to open). `tests/test_presentation.py` enforces what can be checked from the SVG: marks inside the viewBox, stroke ≥ 1.25, dot radius ≥ 1.75, at most three kinds of mark, paint by role only. |
| Beats-the-number test | `waterfall` and `funnel` print their numbers and no glyph in text; `scatter` and `evidence` are gone; `num` exists for numbers with no shape. |
| One-call test | A small-model agent that had read only `mintchip guide` produced a chipped sentence, a four-row table and a pass/fail line, each on its first command, and corrected a deliberate mistake from the error message alone. Its complaints about the output (below) were then fixed; the agent test was not repeated after those fixes. |

## The 18 findings

| # | Finding | Now |
|---|---------|-----|
| 1 | Pills; the demo was a wall | Chips are bare, in the reader's own type. `document()` is a set note; the README opens with a before/after. |
| 2 | Specks at 1× | Marks have enforced minimums; `rank`, `ci` and `gauge` were simplified; small-n `dist` is a rug of ticks. |
| 3 | An outlier flattens `dist` | Values beyond 3×IQR are clipped to an edge chevron, printed past the bracket (`]→47.8`) and warned about. |
| 4 | Text sparklines drop spikes | Downsampling keeps each cell's most extreme value and marks `n=40`. |
| 5 | `spark` cannot share a scale | `domain=` at construction or render time; a range under 2 % of the level is marked (`±0.071%`, an axis break in SVG). |
| 6 | Shared scales are opt-in and early | A table column, and chips of one kind and unit in one `format_prose` call, share a scale automatically at render time. |
| 7 | Theme baked in | Ink is `currentColor`; accent, good, bad and warn are CSS variables with fallbacks that reach 3:1 on both grounds. One `.svg` file serves light and dark. |
| 8 | Twelve pixel sizes | Every chip is `1em` tall with its width in `em`. |
| 9 | Red has eight meanings | Red means bad and nothing else; the accent is blue; good/bad/warn appear only with a declared direction or pass/warn/fail data. |
| 10 | No text grammar | One grammar, golden-tested: brackets only around an axis, number first. |
| 11 | Moiré textures and an emoji-prone arrow | Removed; a test restricts the Unicode tier to the allowed character set. |
| 12 | `--ascii` is not ASCII | `text(ascii=True).isascii()` is tested for every chip. |
| 13 | `evidence` | Removed. |
| 14 | JavaScript modal | A popover (HTML popover API, no JavaScript) holding only what the sentence does not already say. |
| 15 | Agents must write Python | `mintchip <kind>`, `render`, `table`, `guide`, `schema`; warnings on stderr; every error is a `ChipError` with a fix, usually the corrected command. |
| 16 | Six presentation parameters everywhere | Gone from constructors; theme, accent, domain and size are render arguments. |
| 17 | NumPy arrays ignored | Any iterable is accepted; checked with a real NumPy array. |
| 18 | GitHub strips `data:` images | `markdown()` no longer emits them; README images are SVG files in `gallery/output/`. How GitHub renders those files is still unverified (see below). |

## What the fresh-agent test changed

- `strip` counted skipped items out of the denominator (seven jobs printed `5/6 pass`); it now
  counts every item, and a fail prints `×` so it cannot be confused with a skip.
- `bar` rounded 1,840/1,850 to `99%`; values within 1 % of either end now print a decimal.
- `spark`'s number is only the latest point; the full form now adds the range
  (`214 ms (range 208 to 310)`).
- The guide now lists the table column kinds, says `label` and `unit` work on most chips, and
  has a one-line legend for the glyphs that are not self-evident.
- Bars with different totals in one table column were drawn on one absolute scale, which nearly
  emptied 38/40 beside 1,840/1,850. A bar is now a share of its own total; siblings share a
  scale only when their totals agree.

## Differences from the plan

- Fourteen kinds: thirteen graphic chips plus `num`.
- The accent is blue, not Tufte's red, so that red can mean one thing.
- Four themes (`auto`, `light`, `dark`, `mono`), not three: the static ones are for renderers
  without CSS variables.
- The mintfig bridge is removed; `chip.html(detail=…)` takes any HTML for the popover.
- No AGENTS.md at the repo root (it would instruct agents working on this repository);
  `mintchip guide --agents` prints a snippet to paste into one's own.
- The visual baseline is a generated page, not committed screenshots.
- `mintchip demo` is gone; the README and gallery are generated from real calls instead.

## Not done, or not verified

- **Font matrix.** The glyph set is restricted by test, but nobody has looked at the text chips
  in Slack, GitHub Markdown or a proportional chat font.
- **GitHub rendering.** The README images are SVG files with a `prefers-color-scheme` rule.
  Whether GitHub shows them, and whether they follow GitHub's theme or the OS setting, needs a
  push to check.
- **Install.** The package is not on PyPI, so the README installs from git and `uvx mintchip`
  does not work yet.
- **`ci` in a sentence** leaves a visible blank between the reference tick and an interval far
  from it. It is the true distance, but it reads as a gap.
- **Mixed bar wording.** In a column of counts, a cell of 1 out of 1 prints `100%` beside
  `38/40`, because a total of 1 selects percent mode.
- **Column decimals** pad every cell to the column's largest count, so 130 beside 0.25 prints
  `130.00`.
- **`share` in a table** keeps one part order across rows only when every row names the same
  parts in the same order.
