#!/usr/bin/env python3
"""Redraw William Playfair's 1786 time-series chart from data.csv.

The curves and the two balance areas come only from the yearly values in
data.csv (recovered from ../source/scan.png by digitize.py). Grid, frame and
lettering positions were measured on the scan (2067 x 1527 px) and are kept in
scan pixels, so the redrawn chart can be overlaid on the engraving. Labels
are real text; curve labels are set letter by letter along the data curves.

    python build.py                  # writes playfair-1786.pdf
    python build.py --layers text    # one layer only (used by the README animation)

Requires PyMuPDF (already a dependency of the skill's helper script).
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent.parent / "fonts"
SCAN_W, SCAN_H = 2067, 1527
PAGE_W = 720.0                   # 10 in; height follows the scan's aspect ratio
K = PAGE_W / SCAN_W              # scan px -> pt
PAGE_H = SCAN_H * K
LAYERS = ("areas", "grid", "curves", "text")


def rgb(hex_color: str) -> tuple[float, float, float]:
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))


INK, GRID = rgb("#3a332e"), rgb("#5b524b")
EXPORTS, IMPORTS = rgb("#af4c53"), rgb("#db9a53")
AGAINST, FAVOUR = rgb("#f7dad7"), rgb("#e7d9b5")   # hand-colouring of the two balances

FACES = {"roman": FONTS / "LibreCaslonText.ttf", "italic": FONTS / "LibreCaslonText-Italic.ttf"}

# Calibration (scan px): decade gridlines and value gridlines (0, 10, ... 200).
X_GRID = [87, 304, 520, 738, 964, 1178, 1405, 1625, 1849]
Y_GRID = [1301, 1245, 1189, 1131, 1074, 1013, 955, 897, 839, 783, 721.5,
          668, 611, 555, 499, 439, 380, 325, 268, 211, 152]
FRAME_OUTER, FRAME_INNER = (74.5, 142.5, 1995.5, 1315.5), (87, 153.5, 1985, 1302)

# Lettering: (face, size px, bold, baseline y, [(x, text), ...]).
TEXT = [
    ("roman", 39, False, 103, [(312, "Exports"), (500, "and"), (592, "Imports"), (764, "to"),
                               (820, "and"), (913, "from"), (1589, "from"), (1756, "to")]),
    ("roman", 42, True, 104, [(1319, "&")]),
    ("roman", 29, False, 102, [(1682, "1700"), (1807, "1780.")]),
    ("italic", 34, False, 1420, [(346, "The"), (421, "Bottom"), (564, "line"), (643, "is"),
                                 (687, "divided"), (828, "into"), (919, "Years,"), (1028, "the"),
                                 (1101, "Right"), (1214, "hand"), (1313, "line"), (1398, "into"),
                                 (1499, "L10,000"), (1642, "each.")]),
    ("italic", 21.3, True, 1447, [(55, "Published as the Act directs, 1st May 1786, by Wm. Playfair")]),
    ("italic", 19.4, True, 1449, [(1639, "Neele sculpt. 352, Strand, London.")]),
    ("italic", 46, True, 549, [(1488, "BALANCE"), (1755, "in")]),
    ("italic", 45, True, 607, [(1525, "FAVOUR"), (1748, "of")]),
]
# Spaced lettering fitted to a measured width: (face, size, bold, baseline, x0, x1, text).
# Letter gaps stay under ~0.13 em so text extraction still reads whole words.
SPACED = [("italic", 56, True, 661, 1474, 1826, "ENGLAND."),
          ("roman", 43, True, 104, 1020, 1293, "DENMARK"),
          ("roman", 43, True, 104, 1365, 1571, "NORWAY")]
YEAR_LABEL = ("roman", 28, 1346)     # centred under each decade line
VALUE_LABEL = ("roman", 28.5, 1859)  # left edge, after a tick from the axis
# Curve labels: (series, text, x0, x1, offset from the line centre; + is below, size).
CURVE_LABELS = [
    ("imports", "Line of Imports", 525, 785, -6, 33),
    ("exports", "Line of Exports", 540, 785, 27, 33),
    ("exports", "Exports", 1468, 1572, -6, 31),
    ("imports", "Imports", 1640, 1755, 29, 32),
]
# "BALANCE AGAINST" follows its own engraved baseline (letter bottoms measured on the scan).
ARC_LABEL = ("BALANCE AGAINST", [(665, 833), (735, 852), (785, 872), (840, 880), (895, 878),
                                 (940, 868), (1000, 848), (1040, 836), (1080, 828), (1124, 824)], 46)


def P(x, y):
    return pymupdf.Point(x * K, y * K)


def year_x(year: float) -> float:
    return interp(year, range(1700, 1781, 10), X_GRID)


def value_y(value: float) -> float:
    return interp(value, range(0, 201, 10), Y_GRID)


def interp(v, xs, ys):
    xs, ys = list(xs), list(ys)
    for i in range(len(xs) - 1):
        if xs[i] <= v <= xs[i + 1]:
            t = (v - xs[i]) / (xs[i + 1] - xs[i])
            return ys[i] + t * (ys[i + 1] - ys[i])
    return ys[0] if v < xs[0] else ys[-1]


def load_data():
    with (HERE / "data.csv").open() as fh:
        rows = [(int(r["year"]), float(r["exports"]), float(r["imports"])) for r in csv.DictReader(fh)]
    return {"exports": [(y, e) for y, e, _ in rows], "imports": [(y, i) for y, _, i in rows]}


def smooth(points, steps=4):
    """Catmull-Rom spline through yearly points, sampled `steps` times per year (scan px)."""
    return catmull_rom([(year_x(y), value_y(v)) for y, v in points], steps)


def catmull_rom(pts, steps):
    out = []
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = pts[max(i - 1, 0)], pts[i], pts[i + 1], pts[min(i + 2, len(pts) - 1)]
        for s in range(steps):
            t = s / steps
            out.append(tuple(0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t
                                    + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t * t
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t ** 3) for k in (0, 1)))
    out.append(pts[-1])
    return out


def crossing(ex, im):
    """Where the two sampled curves cross (same x samples): (index, point)."""
    for i in range(len(ex) - 1):
        d0, d1 = ex[i][1] - im[i][1], ex[i + 1][1] - im[i + 1][1]
        if d0 > 0 >= d1:
            t = d0 / (d0 - d1)
            return i, (ex[i][0] + t * (ex[i + 1][0] - ex[i][0]), ex[i][1] + t * (ex[i + 1][1] - ex[i][1]))
    raise SystemExit("exports never overtake imports in data.csv")


def polygon(shape, pts, fill):
    shape.draw_polyline([P(*p) for p in pts])
    shape.finish(fill=fill, color=None, width=0, closePath=True)


def stroke(shape, pts, color, width, cap=0, join=1):
    shape.draw_polyline([P(*p) for p in pts])
    shape.finish(color=color, width=width * K, lineCap=cap, lineJoin=join, closePath=False)


def draw_areas(page, curves):
    ex, im = curves["exports"], curves["imports"]
    i, cross = crossing(ex, im)
    s = page.new_shape()
    polygon(s, im[:i + 1] + [cross] + ex[i::-1], AGAINST)          # imports above exports
    polygon(s, [cross] + ex[i + 1:] + im[:i:-1], FAVOUR)            # exports above imports
    s.commit()


def draw_grid(page, curves=None):
    s = page.new_shape()
    x0, x1 = X_GRID[0], X_GRID[-1]
    for v, y in zip(range(0, 201, 10), Y_GRID):
        if v in (0, 200):
            continue
        if v == 100:  # engraved as a double rule running through its label to the frame
            for yy in (717, 726.5):
                stroke(s, [(x0, yy), (FRAME_INNER[2], yy)], GRID, 3)
        else:
            stroke(s, [(x0, y), (x1, y)], GRID, 2.6)
            stroke(s, [(x1, y), (x1 + 9, y)], GRID, 2.6)  # tick before the value label
    for x in X_GRID[1:]:
        stroke(s, [(x, FRAME_INNER[1]), (x, FRAME_INNER[3])], GRID, 2)
    l, t, r, b = FRAME_INNER
    stroke(s, [(l, t), (r, t), (r, b), (l, b), (l, t)], INK, 2)
    l, t, r, b = FRAME_OUTER
    stroke(s, [(l, t), (r, t), (r, b), (l, b), (l, t)], INK, 8, join=0)
    s.commit()


def draw_curves(page, curves):
    s = page.new_shape()
    for name, color in (("imports", IMPORTS), ("exports", EXPORTS)):
        stroke(s, curves[name], color, 9, cap=1)
        stroke(s, curves[name], INK, 1.6, cap=1)
    s.commit()


def put(page, x, y, text, face, size, bold=False, angle=0.0):
    kw = dict(fontname=face, fontsize=size * K, color=INK)
    if bold:  # engraved capitals are heavier than the text face: fill + thin stroke
        kw.update(render_mode=2, border_width=0.035, fill=INK)
    if angle:
        kw["morph"] = (P(x, y), pymupdf.Matrix(-math.degrees(angle)))
    page.insert_text(P(x, y), text, **kw)


def offset_path(path, d):
    """Parallel polyline at distance d (+ is down the page), using vertex normals."""
    out = []
    for i, (x, y) in enumerate(path):
        (xa, ya), (xb, yb) = path[max(i - 1, 0)], path[min(i + 1, len(path) - 1)]
        ang = math.atan2(yb - ya, xb - xa)
        out.append((x - math.sin(ang) * d, y + math.cos(ang) * d))
    return out


def point_at(path, s):
    acc = 0.0
    for i in range(len(path) - 1):
        L = math.dist(path[i], path[i + 1])
        if acc + L >= s or i == len(path) - 2:
            t = (s - acc) / L if L else 0.0
            (xa, ya), (xb, yb) = path[i], path[i + 1]
            return xa + t * (xb - xa), ya + t * (yb - ya)
        acc += L
    return path[-1]


def along(page, fonts, path, text, x0, x1, offset, face, size, bold=False):
    """Set text letter by letter on the curve offset from `path`, spread from x0 to x1.

    Each letter sits with its left baseline on the offset curve and is turned
    to the chord it spans, so spacing stays even on tight bends.
    """
    base = offset_path(path, offset)
    s0, s1 = arclen_at_x(base, x0), arclen_at_x(base, x1)
    natural = fonts[face].text_length(text, fontsize=size)
    gap = (s1 - s0 - natural) / max(len(text) - 1, 1)
    pos = s0
    for ch in text:
        w = fonts[face].text_length(ch, fontsize=size)
        (xa, ya), (xb, yb) = point_at(base, pos), point_at(base, pos + w)
        if ch != " ":
            put(page, xa, ya, ch, face, size, bold, math.atan2(yb - ya, xb - xa))
        pos += w + gap


def arclen_at_x(path, x):
    acc = 0.0
    for i in range(len(path) - 1):
        (xa, ya), (xb, yb) = path[i], path[i + 1]
        L = math.dist(path[i], path[i + 1])
        if xa <= x <= xb:
            return acc + L * (x - xa) / (xb - xa)
        acc += L
    return acc


def draw_text(page, curves):
    fonts = {name: pymupdf.Font(fontfile=str(path)) for name, path in FACES.items()}
    for name, path in FACES.items():
        page.insert_font(fontname=name, fontfile=str(path))
    for face, size, bold, y, words in TEXT:
        for i, (x, word) in enumerate(words):
            put(page, x, y, word + " ", face, size, bold)
            nxt = [wx for wx, _ in words if wx > x]
            if nxt and x + fonts[face].text_length(word, fontsize=size) > min(nxt) - 6:
                print(f"warning: '{word}' runs into the next word at y={y}", file=sys.stderr)
    for face, size, bold, y, x0, x1, word in SPACED:
        gap = (x1 - x0 - fonts[face].text_length(word, fontsize=size)) / (len(word) - 1)
        if gap > 0.13 * size:
            print(f"warning: letter gap in '{word}' may split it in extracted text", file=sys.stderr)
        x = x0
        for ch in word:
            put(page, x, y, ch, face, size, bold)
            x += fonts[face].text_length(ch, fontsize=size) + gap
    face, size, y = YEAR_LABEL
    for year, x in zip(range(1700, 1781, 10), X_GRID):
        w = fonts[face].text_length(str(year), fontsize=size)
        put(page, max(x - w / 2, FRAME_OUTER[0] + 2), y, f"{year} ", face, size)
    face, size, x = VALUE_LABEL
    for v, y in zip(range(0, 201, 10), Y_GRID):
        if 0 < v < 200:
            put(page, x, y + 9, ("100,000" if v == 100 else str(v)) + " ", face, size)
    for series, text, x0, x1, offset, size in CURVE_LABELS:
        along(page, fonts, curves[series], text, x0, x1, offset, "roman", size)
    text, baseline, size = ARC_LABEL
    along(page, fonts, catmull_rom(baseline, 8), text, baseline[0][0], baseline[-1][0], 0,
          "italic", size, bold=True)


def build(out: Path, layers=LAYERS) -> Path:
    data = load_data()
    curves = {name: smooth(points) for name, points in data.items()}
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    draw = {"areas": draw_areas, "grid": draw_grid, "curves": draw_curves, "text": draw_text}
    for name in layers:
        draw[name](page, curves)
    doc.set_metadata({
        "title": "Exports and Imports to and from Denmark & Norway, 1700-1780 (after Playfair, 1786)",
        "subject": "Redrawn from data recovered from a public-domain scan with the scan-to-vector skill",
    })
    tmp = out.with_suffix(".pending.pdf")
    doc.subset_fonts()
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    with pymupdf.open(tmp) as check:
        if check.page_count != 1:
            raise SystemExit(f"unexpected page count in {tmp}")
    tmp.replace(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--layers", nargs="+", choices=LAYERS, default=list(LAYERS))
    ap.add_argument("--out", type=Path, default=HERE / "playfair-1786.pdf")
    args = ap.parse_args()
    out = build(args.out, tuple(args.layers))
    print(f"wrote {out} ({PAGE_W:g} x {PAGE_H:.2f} pt, layers: {' '.join(args.layers)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
