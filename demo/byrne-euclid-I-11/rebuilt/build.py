#!/usr/bin/env python3
"""Rebuild Byrne's Euclid (1847), Book I, Prop. XI from ../source/scan.jpg.

Every coordinate below was measured on the scan (1920 x 2519 px) by colour
segmentation and OCR word boxes, then checked against overlays of the scan.
Geometry is kept in scan pixels and scaled to points at render time, so the
rebuilt page lines up with the scan. Body copy is real, searchable text;
diagrams and inline symbols are vector paths; the engraved initial is a
cleaned raster crop.

    python build.py                  # writes byrne-euclid-I-11.pdf
    python build.py --layers text    # one layer only (used by the README animation)

Requires PyMuPDF (already a dependency of the skill's helper script).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent.parent / "fonts"
SCAN_W, SCAN_H = 1920, 2519
PAGE_W = 504.0                       # 7 in; height follows the scan's aspect ratio
K = PAGE_W / SCAN_W                  # scan px -> pt
PAGE_H = SCAN_H * K
LAYERS = ("figure", "symbols", "text", "initial")


def rgb(hex_color: str) -> tuple[float, float, float]:
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))


# Inks, white-balanced against the scan's paper colour (239, 235, 210).
INK, RED, BLUE, YELLOW = map(rgb, ("#1d1b16", "#f45f3f", "#3c7496", "#edc345"))
COLORS = {"ink": INK, "red": RED, "blue": BLUE, "yellow": YELLOW}

# Libre Caslon Text (SIL OFL), the closest open revival of Byrne's Caslon.
FACES = {"roman": FONTS / "LibreCaslonText.ttf", "italic": FONTS / "LibreCaslonText-Italic.ttf"}
STYLES = {  # (face, size in scan px), sizes fitted to measured word widths
    "r": ("roman", 43.5),
    "i": ("italic", 43),
    "h": ("italic", 51),
    "cap": ("roman", 48),
}

# (style, baseline y, [(x, word), ...]). The long s (ſ) is modernised to s:
# the face has no ſ, and modern spelling keeps the words searchable.
TEXT = [
    ("h", 178, [(313, "BOOK"), (489, "I."), (582, "PROP."), (775, "XI."), (906, "PROB.")]),
    ("r", 177, [(1261, "11")]),
    ("cap", 504, [(288, "ROM")]),
    ("i", 504, [(451, "a"), (506, "given")]),
    ("i", 572, [(305, "point"), (437, "("), (585, "),")]),
    ("i", 637, [(309, "in"), (417, "a"), (501, "given")]),
    ("i", 703, [(295, "straight"), (542, "line")]),
    ("i", 770, [(69, "("), (345, "),"), (425, "to"), (509, "draw")]),
    ("i", 840, [(66, "a"), (102, "perpendicular.")]),
    ("r", 1188, [(206, "Take"), (333, "any"), (422, "point"), (549, "("), (773, ")"),
                 (808, "in"), (867, "the"), (950, "given"), (1082, "line,")]),
    ("r", 1276, [(269, "cut"), (352, "off"), (941, "(pr."), (1040, "3.),")]),
    ("r", 1487, [(386, "construct"), (837, "(pr."), (938, "1.),")]),
    ("r", 1577, [(185, "draw"), (538, "and"), (631, "it"), (678, "shall"), (787, "be"),
                 (853, "perpendicular"), (1156, "to")]),
    ("r", 1667, [(547, "the"), (630, "given"), (760, "line.")]),
    ("r", 1849, [(317, "For"), (914, "(const.)")]),
    ("r", 1939, [(872, "(const.)")]),
    ("r", 2026, [(215, "and"), (537, "common"), (736, "to"), (795, "the"), (879, "two"),
                 (977, "triangles.")]),
    ("r", 2236, [(328, "Therefore"), (907, "(pr."), (1004, "8.)")]),
    ("r", 2324, [(879, "(def."), (997, "10.).")]),
    ("r", 2420, [(1079, "Q."), (1151, "E."), (1215, "D.")]),
]

# Inline line-symbols: (x0, x1, centre y, colour); pieces of one symbol share an edge.
BARS = [
    [(454, 516, 560, "ink"), (516, 575, 560, "red")],          # a given point
    [(86, 214, 763, "ink"), (214, 336, 763, "red")],           # a given straight line
    [(565, 677, 1174.5, "red")],                               # any point ...
    [(680, 696, 1174.5, "red")], [(700, 716, 1174.5, "red")],  # ... its dotted part
    [(718, 734, 1174.5, "red")], [(740, 755, 1174.5, "red")],
    [(428, 615, 1264, "ink")], [(728, 916, 1264.5, "red")],    # cut off ... = ...
    [(316, 507, 1565, "yellow")],                              # draw ...
    [(412, 591, 1839.5, "blue")], [(710, 886, 1838, "blue")],  # For ... = ...
    [(367, 558, 1926, "ink")], [(657, 845, 1926.5, "red")],
    [(315, 506, 2015.5, "yellow")],                            # and ... common
    [(371, 560, 2309.5, "yellow")],                            # ∴ ... ⊥ ...
    [(671, 758, 2314, "ink"), (758, 850, 2314, "red")],
]
BAR_H = 12
# Equals signs: (x0, x1, top bar (y0, y1), bottom bar (y0, y1)).
EQUALS = [
    (648, 702, (1251, 1258), (1268, 1276)),
    (625, 678, (1826, 1833), (1844, 1851)),
    (584, 636, (1914, 1922), (1932, 1939)),
    (696, 749, (2210, 2219), (2228, 2236)),
]
# Quarter-disc angle symbols: (corner x, corner y, radius, quadrant, colour).
INLINE_ANGLES = [(658, 2242, 105, "upper-left", "red"), (780, 2244, 101, "upper-right", "blue")]
THEREFORE_DOTS = [(304.5, 2319), (320.5, 2297.5), (337.5, 2320)]   # ∴, radius 6.5
PERP_SIGN = [(613, 2285, 620, 2320), (589, 2320, 644, 2327)]       # ⊥ as two rects
SMALL_TRIANGLE = {"apex": (690, 1318), "left": (595, 1494), "right": (798, 1494),
                  "base_y": 1497, "x0": 592, "split_x": 696, "x1": 799}

# Main figure.
APEX, LEFT, RIGHT = (1134, 350), (740, 1044), (1538, 1044)
FOOT, ANGLE_R = (1135, 1044), 148
KAPPA = 0.5523  # cubic Bezier approximation of a quarter circle


def P(x, y):
    return pymupdf.Point(x * K, y * K)


def R(x0, y0, x1, y1):
    return pymupdf.Rect(x0 * K, y0 * K, x1 * K, y1 * K)


def capsule(shape, x0, x1, yc, color, round_left=True, round_right=True, h=BAR_H):
    r = h / 2
    shape.draw_rect(R(x0 + (r if round_left else 0), yc - r, x1 - (r if round_right else 0), yc + r))
    shape.finish(fill=color, color=None, width=0)
    for x, on in ((x0 + r, round_left), (x1 - r, round_right)):
        if on:
            shape.draw_circle(P(x, yc), r * K)
            shape.finish(fill=color, color=None, width=0)


def quarter_disc(shape, cx, cy, r, quadrant, color):
    k = KAPPA * r
    if quadrant == "upper-left":
        start, c1, c2, end = (cx - r, cy), (cx - r, cy - k), (cx - k, cy - r), (cx, cy - r)
    else:
        start, c1, c2, end = (cx, cy - r), (cx + k, cy - r), (cx + r, cy - k), (cx + r, cy)
    shape.draw_line(P(cx, cy), P(*start))
    shape.draw_bezier(P(*start), P(*c1), P(*c2), P(*end))
    shape.draw_line(P(*end), P(cx, cy))
    shape.finish(fill=color, color=None, width=0, closePath=True)


def line(shape, pts, color, width, dashes=None, join=0):
    shape.draw_polyline([P(*p) for p in pts])
    shape.finish(color=color, width=width * K, lineJoin=join, lineCap=0, closePath=False,
                 dashes=f"[{dashes[0] * K:.3f} {dashes[1] * K:.3f}] 0" if dashes else None)


def draw_figure(page):
    s = page.new_shape()
    fx, fy = FOOT
    quarter_disc(s, fx, fy, ANGLE_R, "upper-left", RED)
    quarter_disc(s, fx, fy, ANGLE_R, "upper-right", BLUE)
    line(s, [(736, fy), (fx, fy)], INK, 13)
    line(s, [(fx, fy + 1), (1545, fy + 1)], RED, 13)
    line(s, [(571, fy + 0.5), (736, fy + 0.5)], INK, 13, dashes=(12, 5.6))
    line(s, [(1553, fy + 1.5), (1713, fy + 1.5)], RED, 13, dashes=(11.5, 6))
    line(s, [LEFT, APEX, RIGHT], BLUE, 12.5)
    line(s, [(fx + 0.5, 376), (fx + 0.5, fy)], YELLOW, 12.5)
    s.commit()


def draw_symbols(page):
    s = page.new_shape()
    for pieces in BARS:
        for j, (x0, x1, yc, col) in enumerate(pieces):
            capsule(s, x0, x1, yc, COLORS[col], j == 0, j == len(pieces) - 1)
    for x0, x1, top, bottom in EQUALS:
        for y0, y1 in (top, bottom):
            s.draw_rect(R(x0, y0, x1, y1))
            s.finish(fill=INK, color=None, width=0)
    for cx, cy, r, quadrant, col in INLINE_ANGLES:
        quarter_disc(s, cx, cy, r, quadrant, COLORS[col])
    for cx, cy in THEREFORE_DOTS:  # ∴ is not in the text face, so it is drawn
        s.draw_circle(P(cx, cy), 6.5 * K)
        s.finish(fill=INK, color=None, width=0)
    for rect in PERP_SIGN:         # likewise ⊥
        s.draw_rect(R(*rect))
        s.finish(fill=INK, color=None, width=0)
    t = SMALL_TRIANGLE
    line(s, [t["left"], t["apex"], t["right"]], BLUE, 10)
    capsule(s, t["x0"], t["split_x"], t["base_y"], INK, True, False, 10.5)
    capsule(s, t["split_x"], t["x1"], t["base_y"], RED, False, True, 10.5)
    s.commit()


def draw_text(page, warn=True):
    fonts = {name: pymupdf.Font(fontfile=str(path)) for name, path in FACES.items()}
    for name, path in FACES.items():
        page.insert_font(fontname=name, fontfile=str(path))
    for style, y, words in TEXT:
        face, size = STYLES[style]
        for i, (x, word) in enumerate(words):
            # A trailing space keeps word boundaries in extracted text.
            page.insert_text(P(x, y), word + " ", fontname=face, fontsize=size * K, color=INK)
            if warn and i + 1 < len(words):
                end = x + fonts[face].text_length(word, fontsize=size)
                if end > words[i + 1][0] - 6:
                    print(f"warning: '{word}' runs into '{words[i + 1][1]}' at y={y}", file=sys.stderr)


def draw_initial(page):
    # Engraved initial: retained as a cleaned crop of scan region (64, 460)-(290, 712).
    page.insert_image(R(64, 460, 290, 712), filename=str(HERE / "figures" / "initial-F.png"))


def build(out: Path, layers=LAYERS) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    draw = {"figure": draw_figure, "symbols": draw_symbols, "text": draw_text, "initial": draw_initial}
    for name in layers:
        draw[name](page)
    doc.set_metadata({
        "title": "Euclid, Book I, Proposition XI (after Byrne, 1847)",
        "subject": "Rebuilt from a public-domain scan with the scan-to-vector skill",
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
    ap.add_argument("--out", type=Path, default=HERE / "byrne-euclid-I-11.pdf")
    args = ap.parse_args()
    out = build(args.out, tuple(args.layers))
    print(f"wrote {out} ({PAGE_W:g} x {PAGE_H:.2f} pt, layers: {' '.join(args.layers)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
