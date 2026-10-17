#!/usr/bin/env python3
"""Recover yearly values from Playfair's 1786 chart (../source/scan.png).

Calibrates the engraved grid, traces the exports (crimson) and imports
(orange) lines column by column, and writes data.csv in the chart's own
unit (£10,000). Values are readings of a hand-engraved, hand-coloured
plate, so treat them as about ±1 unit.

    python digitize.py      # needs numpy, scipy and Pillow (demo/requirements.txt)
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.signal import medfilt

HERE = Path(__file__).resolve().parent
SCAN = HERE.parent / "source" / "scan.png"

# Gridline centres measured on the scan (px): decades along x, tens of £10,000 up y.
X_GRID = [87, 304, 520, 738, 964, 1178, 1405, 1625, 1849]
X_YEARS = list(range(1700, 1781, 10))
Y_GRID = [1301, 1245, 1189, 1131, 1074, 1013, 955, 897, 839, 783, 721.5,
          668, 611, 555, 499, 439, 380, 325, 268, 211, 152]
Y_VALUES = list(range(0, 201, 10))


def masks(rgb):
    r, g, b = (rgb[..., i].astype(int) for i in range(3))
    exports = (r > 120) & (r - g > 70) & (b >= g - 8) & (g < 110)            # crimson leans magenta
    imports = (r > 165) & (r - b > 80) & (g > b + 15) & (g < 210) & (b < 130)  # orange leans yellow
    return exports, imports


def track(mask, y_start, x0=X_GRID[0] + 1, x1=X_GRID[-1]):
    """Follow one line left to right, choosing the run nearest the previous column."""
    xs, ys, prev = [], [], y_start
    for x in range(x0, x1 + 1):
        rows = np.flatnonzero(mask[150:1305, x]) + 150
        runs = [run for run in np.split(rows, np.flatnonzero(np.diff(rows) > 3) + 1) if len(run) >= 3]
        if not runs:
            continue
        centre = min(((run[0] + run[-1]) / 2 for run in runs), key=lambda c: abs(c - prev))
        if abs(centre - prev) > 25:
            continue
        xs.append(x)
        ys.append(centre)
        prev = centre
    return np.array(xs), medfilt(np.array(ys), 9)


def main() -> int:
    rgb = np.asarray(Image.open(SCAN).convert("RGB"))
    exports_mask, imports_mask = masks(rgb)
    years = np.arange(1700, 1781)
    x_at_year = np.interp(years, X_YEARS, X_GRID)
    to_value = lambda y: np.interp(-np.asarray(y), [-v for v in Y_GRID], Y_VALUES)
    series = {}
    for name, mask, y0 in (("exports", exports_mask, 1109), ("imports", imports_mask, 889)):
        xs, ys = track(mask, y0)
        if np.diff(xs).max() > 20:
            raise SystemExit(f"{name}: trace has a gap wider than 20 px; check the colour mask")
        series[name] = to_value(np.interp(x_at_year, xs, ys))
    out = HERE / "data.csv"
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "exports", "imports"])
        for i, year in enumerate(years):
            w.writerow([int(year), f"{series['exports'][i]:.1f}", f"{series['imports'][i]:.1f}"])
    print(f"wrote {out} ({len(years)} years, unit £10,000)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
