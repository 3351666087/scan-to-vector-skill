#!/usr/bin/env python3
"""Crop and enlarge part of a page, optionally with a labelled pixel grid.

    python zoom.py work/probe/deskewed.png 300 900 800 1200 --scale 3 --grid 50 --out work/zoom.png

Look at the result instead of the whole page when reading small or doubtful
text, counting items, or reading positions: a page viewed whole is shrunk
before you see it, so small print and exact positions are lost. Grid labels
are in the source image's pixel coordinates, the same ones probe.json and
Canvas use.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image", type=Path)
    ap.add_argument("box", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--grid", type=int, default=0, help="grid spacing in source pixels (0 = none)")
    ap.add_argument("--out", type=Path, default=Path("work/zoom.png"))
    args = ap.parse_args()

    im = Image.open(args.image).convert("RGB")
    x0, y0, x1, y1 = (int(v) for v in args.box)
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, im.width), min(y1, im.height)
    crop = im.crop((x0, y0, x1, y1))
    s = args.scale
    big = crop.resize((max(1, int(crop.width * s)), max(1, int(crop.height * s))), Image.LANCZOS)
    if args.grid:
        d = ImageDraw.Draw(big, "RGBA")
        g = args.grid
        for gx in range((x0 // g + 1) * g, x1, g):
            X = (gx - x0) * s
            d.line([(X, 0), (X, big.height)], fill=(0, 140, 255, 110), width=1)
            d.text((X + 2, 2), str(gx), fill=(0, 90, 220, 255))
        for gy in range((y0 // g + 1) * g, y1, g):
            Y = (gy - y0) * s
            d.line([(0, Y), (big.width, Y)], fill=(0, 140, 255, 110), width=1)
            d.text((2, Y + 2), str(gy), fill=(0, 90, 220, 255))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    big.save(args.out)
    print(f"{args.out}  ({x0},{y0})-({x1},{y1}) at {s:g}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
