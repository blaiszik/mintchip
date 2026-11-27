"""Build crisp, high-DPI, zero-grain README demo GIF for mintchip.

Pipeline:
1. Render ``MintchipOpener`` from ``src/index.ts`` at native ``1280x720`` (15 fps, 270 frames)
   using lossless PNG frames so text and inline ``currentColor`` SVGs never suffer JPEG
   mosquito noise or fractional CSS scaling.
2. Deduplicate static hold frames (combining consecutive near-identical frames' durations)
   and quantize with 256-color ``FASTOCTREE`` + ``dither=NONE`` so solid ``#0B1020`` dark
   backdrops, ``#0D1426`` terminal cards, and ``#FFFFFF`` / ``#14181F`` HTML panels stay
   100% flat with zero grain.

Usage:
    # Encode from already-rendered PNG sequence directory:
    /Users/blaiszik/Desktop/git/mintfig/.venv/bin/python make_gif.py --frames-dir /tmp/mintchip_remotion_opener

    # Or render + encode end-to-end:
    /Users/blaiszik/Desktop/git/mintfig/.venv/bin/python make_gif.py --render
"""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_OUT = REPO_ROOT / "gallery" / "output" / "opener.gif"


def render_png_sequence(frames_dir: Path, *, concurrency: int = 4) -> None:
    """Bundle src/index.ts and render MintchipOpener to lossless PNG frames."""
    with tempfile.TemporaryDirectory(prefix="mintchip_remotion_bundle_") as bundle_dir:
        subprocess.run(
            [
                "node",
                str(HERE / "render_frames.mjs"),
                str(frames_dir),
                str(concurrency),
                bundle_dir,
            ],
            cwd=HERE,
            check=True,
        )


def _frame_sort_key(path: Path) -> tuple[int, str]:
    m = re.search(r"(\d+)", path.stem)
    return (int(m.group(1)) if m else 0, path.name)


def png_sequence_to_gif(
    seq_dir: Path,
    gif_path: Path,
    *,
    fps: int = 15,
    width: int | None = None,
    height: int | None = None,
    static_mad_threshold: float = 0.005,
    hold_end_ms: int = 2800,
) -> tuple[int, int, float]:
    """Encode a lossless PNG frame sequence into a crisp, deduplicated looping GIF."""
    paths = sorted(seq_dir.glob("*.png"), key=_frame_sort_key)
    if not paths:
        raise FileNotFoundError(f"No PNG frames found in {seq_dir}")

    frame_ms = round(1000.0 / fps)
    kept_rgb: list[Image.Image] = []
    durations: list[int] = []
    prev_arr: np.ndarray | None = None

    for idx, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        if width is not None and height is not None and im.size != (width, height):
            im = im.resize((width, height), Image.Resampling.LANCZOS)
        arr = np.asarray(im, dtype=np.int16)
        is_last = idx == len(paths) - 1
        if prev_arr is not None:
            mad = float(np.abs(arr - prev_arr).mean())
            if mad <= static_mad_threshold and not (is_last and mad > 0.0):
                durations[-1] += frame_ms
                continue
        kept_rgb.append(im)
        durations.append(frame_ms)
        prev_arr = arr

    if durations:
        durations[-1] = max(durations[-1], hold_end_ms)

    # Per-frame 256-color FASTOCTREE with zero dithering preserves razor-sharp text
    # anti-aliasing, flat #0B1020 studio backdrops, and clean light/dark HTML cards.
    quantized = [
        im.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
        for im in kept_rgb
    ]

    gif_path.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        gif_path,
        save_all=True,
        append_images=quantized[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    size_kb = gif_path.stat().st_size / 1024.0
    return len(paths), len(quantized), size_kb


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true", help="Render PNG frames with Remotion first.")
    parser.add_argument("--frames-dir", type=Path, default=None, help="Directory of rendered PNG frames.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output GIF path.")
    parser.add_argument("--width", type=int, default=1280, help="Output GIF width (default: native 1280).")
    parser.add_argument("--height", type=int, default=720, help="Output GIF height (default: native 720).")
    parser.add_argument("--fps", type=int, default=15, help="Source sequence FPS (default: 15).")
    parser.add_argument("--concurrency", type=int, default=4, help="Remotion render concurrency.")
    args = parser.parse_args()

    tmp_ctx = (
        tempfile.TemporaryDirectory(prefix="mintchip_gif_seq_")
        if (args.render and args.frames_dir is None)
        else None
    )
    try:
        if args.render:
            frames_dir = args.frames_dir or Path(tmp_ctx.name)  # type: ignore[union-attr]
            render_png_sequence(frames_dir, concurrency=args.concurrency)
        elif args.frames_dir is not None:
            frames_dir = args.frames_dir
        else:
            parser.error("Pass --render or --frames-dir.")

        raw, kept, kb = png_sequence_to_gif(
            frames_dir,
            args.out,
            fps=args.fps,
            width=args.width,
            height=args.height,
            hold_end_ms=2800,
        )
        print(f"{args.out.name} ({args.width}x{args.height}): {raw} -> {kept} deduped frames, {kb:.1f} KB")
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
