# mintchip README hero demo GIF (Remotion)

18-second (270 frames @ 15 fps) lossless-rendered, zero-grain 1280×720 looping GIF for
`mintchip` ("One command. Every surface."), written to `gallery/output/opener.gif`.

Every chip, shared-scale table, ANSI sequence, Markdown table, `currentColor` HTML fragment,
CSS rule, and `stderr` distortion warning is generated from real `mintchip` calls in
`make_assets.py` -> `src/assets.json`.

## Four beats

1. **Wall of numbers → One shell command (0–4 s)** — Noisy coding-agent CI + parser benchmark
   summary with buried numbers highlighted in amber, alongside `mintchip render` + `mintchip table`
   (`0 deps · 12 ms`).
2. **Terminal ANSI + Shared-Scale Forest Plot + Markdown (4–9 s)** — Real ANSI output (`strip`,
   `dist` with clipped outlier `→240`, `delta`, and a 5-row shared-scale `ci` forest plot with a
   mint scan-line tracing the aligned `│` zero line), plus a `--format md` GitHub PR preview.
3. **Same data → `--format html` (9–14.5 s)** — Real `mintchip` HTML + `mc.css()`. Cursor hovers
   and clicks the `dist` chip to open its zero-JS popover (`n=18`, IQR, clipped outlier note),
   followed by a crisp Light ↔ Dark wipe demonstrating automatic `currentColor` adaptation.
4. **Distortions announced + End card (14.5–18 s)** — Highlights the `→240` mark, right-edge SVG
   chevron, and real `stderr` warning, closing on `mintchip` · `uvx mintchip guide`.

## Rebuilding

```bash
# 1. Regenerate real mintchip outputs (uses Python stdlib only)
../../.venv/bin/python make_assets.py

# 2. Render lossless 1280x720 PNG frames with Remotion (reuses sibling mintfig node_modules if present)
node render_frames.mjs /tmp/mintchip_remotion_opener 4

# 3. Quantize (FASTOCTREE + dither=NONE) and deduplicate into gallery/output/opener.gif
../../../mintfig/.venv/bin/python make_gif.py --frames-dir /tmp/mintchip_remotion_opener
```

Or run steps 2 and 3 together:

```bash
../../../mintfig/.venv/bin/python make_gif.py --render
```
