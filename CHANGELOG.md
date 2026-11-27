# Changelog

All notable changes to `mintchip` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once 1.0 is reached.

## [0.2.1] - 2026-11-27

### Added
- **Zero-yellow mint themes (`mint` and `mint_dark`):** All ink/accent/good/bad/warn roles pass WCAG AA ≥ 4.5:1 contrast on `#FFFFFF` and `#14181F`, with automatic `data-mc-scheme` support in `mintchip.document()` and `Table.save()`.
- **4 new zero-dependency inline micro-graphic chips:**
  - `mintchip.bullet(value, target, ranges=...)`: Stephen Few inline bullet graph with qualitative bands, actual bar, and target tick.
  - `mintchip.heat(values, ...)`: single-row word-sized heatmap strip with graduated intensity slots.
  - `mintchip.hist(samples, bins=..., reference=...)`: miniature inline histogram with modal-bin highlight and skew/bimodality facts.
  - `mintchip.status(passed, failed=0, skipped=0)`: stacked CI pass/fail/skip bar preserving visible failure slivers even at 1/1,000.
- Updated `README.md`, `gallery/README.md`, `skills/mintchip/SKILL.md`, `llms.txt`, and golden tests.

## [0.2.0] - 2026-11-27

### Added
- **Bare word-sized graphics and 14-kind registry:**
  - Separated chip data records (`Chip`) from rendering (`chip.text()`, `chip.markdown()`, `chip.svg()`, `chip.html()`, `chip.save()`, `chip.to_dict()` / `Chip.from_dict()`).
  - 14 registered kinds (`num`, `spark`, `ci`, `dist`, `bar`, `gauge`, `delta`, `strip`, `share`, `ratio`, `timeline`, `rank`, `waterfall`, `funnel`) with 1em SVG height, automatic light/dark theming, and a single unified text/ASCII/ANSI grammar.
- **Shared-scale tables (`mintchip table` / `mc.table`):**
  - Small-multiple tables with automatic shared column scales (forest plots, aligned bars, sparklines, strips) in terminal text, ANSI, Markdown, HTML, and JSON, plus row sorting, highlighting, and baseline separators.
- **One-command CLI (`mintchip`):**
  - Subcommand per chip kind, `mintchip render` for prose with `{{kind ...}}` directives (skipping Markdown fenced and inline code spans), `mintchip table`, `mintchip guide`, `mintchip schema`, `mintchip catalog`, `mintchip doctor`, and `mintchip skill`.
  - `-V` / `--version`, `-o` / `--out FILE`, unified `--format html` (with `--fragment` for embeddable markup), and `--format md` / `markdown` with pure-ASCII support.
- **Zero-dependency developer tool ingestors & benchmark diffing (`mintchip from`, `mintchip diff`):**
  - Built-in parsers for `git-diff`, `hyperfine`, `junit`, `pytest-benchmark`, `go-bench`, `cargo-bench`, `github-actions`, `k6`, `esbuild`, and `chrome-trace`.
  - `mintchip diff BASE HEAD` with shared-scale delta + 95% CI tables, CI-overlap noise gating, `--fail-on-regression PCT`, and missing-benchmark warnings.
- **Agent skills & evaluation:**
  - `mintchip skill --install --global` supporting Claude Code, Codex, Cursor, Gemini CLI, GitHub Copilot, Antigravity, `AGENTS.md`, and `CLAUDE.md`.
  - Generated `skills/mintchip/SKILL.md` and `llms.txt` synced from `mintchip guide --write .`, plus trigger evaluation suite in `evals/trigger_eval/`.
- **CI/CD, typing, and GitHub integrations:**
  - PEP 561 `py.typed` marker included in wheels.
  - Cross-platform CI matrix (Linux/macOS/Windows across Python 3.10, 3.12, 3.13) with isolated wheel install smoke test.
  - Reusable composite GitHub Action at `.github/actions/mintchip-diff/action.yml` for PR benchmark diffs.
  - GitHub Pages workflow publishing the live interactive gallery (`gallery/output/index.html` and `baseline.html`).
  - Static light/dark SVG pairs and absolute raw GitHub URLs in `README.md` so PyPI and GitHub both render cleanly in light and dark modes.

### Changed (Breaking)
- Rebuilt `mintchip` from v0.1.0's 17 pill-styled chips to 14 bare, 1em word-sized chips (`evidence` and `scatter` removed; `dual_spark` and `quantiles` merged into `spark` and `dist`; `num` added).
- Removed presentation parameters (`width`, `height`, `style`, `palette`, `accent`, `expand`) from chip constructors; theme, accent, width, and domain are now render-time arguments.
- Trimmed generated `gallery/output/` assets from the PyPI source distribution (`sdist`) to keep downloads compact.

## [0.1.0] - 2026-11-25

### Added
- Initial zero-dependency prototype with 17 inline graphic chips, basic CLI (`catalog`, `demo`), test suite, and visual gallery.
