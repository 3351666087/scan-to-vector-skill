#!/usr/bin/env python3
"""Measure a scanned page so it can be redrawn from numbers, not guesses.

    python probe.py scan.jpg --out work/probe

Writes, in one coordinate system (pixels of the straightened scan):
  deskewed.png   the page flattened (photos) and rotated upright, paper white-balanced
  probe.json     page size, skew, OCR lines and words with boxes and font
                 sizes, ruled lines, filled colour regions, figure candidates
  preview.png    the measurements drawn over the scan, to check at a glance

Needs Pillow, numpy and the `tesseract` command. scipy is used if present.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

try:
    from scipy import ndimage as ndi
except ImportError:  # pragma: no cover - degraded mode without scipy
    ndi = None

PAPER = {"letter": (612, 792), "a4": (595.28, 841.89), "legal": (612, 1008), "a5": (419.53, 595.28)}
DESCENDERS = set("gjpqy,;")


def luminance(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def find_page_quad(rgb):
    """Corners of a bright sheet photographed on a darker background, or None if the
    page already fills the frame. Returns [tl, tr, br, bl] in pixels."""
    lum = luminance(rgb)
    h, w = lum.shape
    small = lum[::4, ::4]
    thr = (np.percentile(small, 95) + np.percentile(small, 5)) / 2
    bright = small > thr
    bright = ndi.binary_closing(bright, np.ones((9, 9), bool))
    lab, n = ndi.label(bright)
    if n == 0:
        return None
    sizes = ndi.sum(bright, lab, range(1, n + 1))
    page = lab == (int(np.argmax(sizes)) + 1)
    page = ndi.binary_fill_holes(page)
    if page.mean() > 0.93:
        return None
    border = np.concatenate([page[0], page[-1], page[:, 0], page[:, -1]])
    if border.mean() > 0.6:
        return None
    inside, outside = np.median(small[page]), np.median(small[~page])
    if outside > 0.75 * inside:                     # a flatbed scan's pale margin, not a desk
        return None
    ys, xs = np.nonzero(page)
    s, d = xs + ys, xs - ys
    corners = [(xs[np.argmin(s)], ys[np.argmin(s)]), (xs[np.argmax(d)], ys[np.argmax(d)]),
               (xs[np.argmax(s)], ys[np.argmax(s)]), (xs[np.argmin(d)], ys[np.argmin(d)])]
    return [(float(x) * 4 + 2, float(y) * 4 + 2) for x, y in corners]


def sheet_aspect(quad, size):
    """Width/height of the real sheet behind a photographed quadrilateral.

    Edge lengths are foreshortened, so first try the projective estimate for a
    rectangle seen by a pinhole camera (Zhang, "Whiteboard scanning", 2007): it
    recovers the focal length and the true aspect from the four corners. If that
    is degenerate (sheet nearly facing the camera, or corners not from a real
    camera), fall back to averaged edge lengths."""
    tl, tr, br, bl = quad
    w, h = size
    edge = ((np.hypot(*np.subtract(tr, tl)) + np.hypot(*np.subtract(br, bl))) /
            (np.hypot(*np.subtract(bl, tl)) + np.hypot(*np.subtract(br, tr))))
    m1, m2, m3, m4 = (np.array([x - w / 2, y - h / 2, 1.0]) for x, y in (tl, tr, bl, br))
    try:
        k2 = np.dot(np.cross(m1, m4), m3) / np.dot(np.cross(m2, m4), m3)
        k3 = np.dot(np.cross(m1, m4), m2) / np.dot(np.cross(m3, m4), m2)
        n2, n3 = k2 * m2 - m1, k3 * m3 - m1
        f2 = -(n2[0] * n3[0] + n2[1] * n3[1]) / (n2[2] * n3[2])
        if f2 > 0 and abs(n2[2]) > 1e-6 and abs(n3[2]) > 1e-6:
            a = np.sqrt((n2[0] ** 2 / f2 + n2[1] ** 2 / f2 + n2[2] ** 2) /
                        (n3[0] ** 2 / f2 + n3[1] ** 2 / f2 + n3[2] ** 2))
            if 0.85 * edge < a < 1.15 * edge:      # trust it only near the edge estimate
                return float(a), "projective"
    except (ZeroDivisionError, FloatingPointError, ValueError):
        pass
    return float(edge), "edges"


def flatten(rgb, quad, out_w, paper="auto"):
    """Perspective-correct the sheet inside `quad` to an upright rectangle `out_w` wide.
    paper: "auto" snaps to the nearest standard size within 12% (a photo cannot pin the
    aspect closer than that); "none" keeps the estimate; or a size name from PAPER."""
    aspect, method = sheet_aspect(quad, (rgb.shape[1], rgb.shape[0]))
    snapped = None
    if paper in PAPER:
        snapped = paper
    elif paper == "auto":
        name = min(PAPER, key=lambda k: abs(PAPER[k][0] / PAPER[k][1] - aspect))
        if abs(PAPER[name][0] / PAPER[name][1] - aspect) / aspect < 0.12:
            snapped = name
    if snapped:
        out_h = int(round(out_w * PAPER[snapped][1] / PAPER[snapped][0]))
    else:
        out_h = int(round(out_w / aspect))
    flatten.info = {"aspect_estimate": round(aspect, 4), "method": method, "snapped_to": snapped}
    dst = [(0, 0), (out_w, 0), (out_w, out_h), (0, out_h)]
    a = []
    b = []
    for (x, y), (u, v) in zip(quad, dst):        # map output (u, v) -> source (x, y)
        a.append([u, v, 1, 0, 0, 0, -x * u, -x * v]); b.append(x)
        a.append([0, 0, 0, u, v, 1, -y * u, -y * v]); b.append(y)
    coeffs = np.linalg.solve(np.array(a, float), np.array(b, float))
    im = Image.fromarray(rgb.astype(np.uint8)).transform((out_w, out_h), Image.PERSPECTIVE, tuple(coeffs),
                                                          resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    return np.asarray(im).astype(np.float32)


def estimate_skew(gray):
    """Counter-clockwise rotation (degrees) that makes text rows sharpest, i.e. straightens the page."""
    small = Image.fromarray(gray.astype(np.uint8)).resize((gray.shape[1] // 2, gray.shape[0] // 2))
    ink = (255 - np.asarray(small, np.float32)) > 60
    img = Image.fromarray((ink * 255).astype(np.uint8))
    def sharpness(angle):
        rows = np.asarray(img.rotate(angle, resample=Image.BILINEAR), np.float32).sum(1)
        return float(np.var(rows))
    coarse = max(np.arange(-3, 3.001, 0.1), key=sharpness)
    fine = max(np.arange(coarse - 0.12, coarse + 0.121, 0.02), key=sharpness)
    return round(float(fine), 2)


def normalize_light(rgb):
    """Divide out paper colour, shadows and uneven light, channel by channel, so paper is
    white everywhere and ink keeps its colour."""
    h, w, _ = rgb.shape
    out = np.empty_like(rgb)
    k = 8
    for c in range(3):
        small = rgb[::k, ::k, c]
        bg = ndi.maximum_filter(small, size=25)                 # wider than any stroke or bar
        bg = ndi.uniform_filter(bg, size=15)
        bg = np.asarray(Image.fromarray(bg.astype(np.float32)).resize((w, h), Image.BILINEAR))
        out[..., c] = rgb[..., c] / np.maximum(bg, 1) * 255
    lum = luminance(rgb)
    paper = np.median(rgb[lum >= np.percentile(lum, 70)], axis=0)
    return np.clip(out, 0, 255), paper


def is_italic(sub):
    """True when shearing the strokes upright sharpens them: slanted (italic) type."""
    if sub.shape[0] < 8 or sub.sum() < 50:
        return False
    def sharp(shear):
        h = sub.shape[0]
        cols = np.zeros(sub.shape[1] + h, np.float32)
        for y in range(h):
            off = int(round(y * shear))             # push lower rows right = lean the top back left
            cols[off:off + sub.shape[1]] += sub[y]
        return float(np.var(cols))
    upright, sheared = sharp(0.0), sharp(0.21)
    return sheared > 1.18 * upright


def measure_line(ink, line):
    """Baseline, ascender/cap height and font size from the ink itself (OCR boxes are often
    the full line height for every word)."""
    x0, y0, x1, y1 = line["box"]
    pad = max(2, (y1 - y0) // 6)
    top = max(y0 - pad, 0)
    sub = ink[top:y1 + pad, x0:x1]
    prof = sub.sum(1).astype(float)
    if prof.max() <= 0:
        return
    main = np.flatnonzero(prof > 0.35 * prof.max())
    body = np.flatnonzero(prof > 0.04 * prof.max())
    baseline = top + int(main[-1]) + 1
    asc = baseline - (top + int(body[0]))
    line["baseline"] = baseline
    line["x_height"] = int(main[-1] - main[0] + 1)
    line["cap_height"] = int(asc)
    line["size_px"] = round(asc / 0.72, 1)              # ascenders and capitals reach ~0.72 em
    for wd in line["words"]:
        wx0, _, wx1, _ = wd["box"]
        cols = np.flatnonzero(ink[baseline - asc:baseline + 2, wx0:wx1].any(0))
        if len(cols):
            wd["box"] = [wx0 + int(cols[0]), wd["box"][1], wx0 + int(cols[-1]) + 1, wd["box"][3]]
        word_ink = ink[max(baseline - asc, 0):baseline + 2, wd["box"][0]:wd["box"][2]]
        if word_ink.sum() > 10:                          # mean stroke width = 2 * area / edge length
            edges = (word_ink[1:] != word_ink[:-1]).sum() + (word_ink[:, 1:] != word_ink[:, :-1]).sum()
            edges += word_ink[0].sum() + word_ink[-1].sum() + word_ink[:, 0].sum() + word_ink[:, -1].sum()
            wd["weight"] = float(2 * word_ink.sum() / max(edges, 1) / max(line["size_px"], 1))
    band = ink[max(baseline - line["x_height"], 0):baseline, x0:x1]
    line["italic"] = bool(is_italic(band.astype(np.float32)))


def mark_bold(lines):
    """Flag words whose stroke width, relative to their font size, is clearly heavier than
    the page's typical text (size- and case-independent)."""
    weights = [wd["weight"] for l in lines for wd in l["words"] if wd.get("weight") and len(wd["text"]) >= 3]
    if len(weights) < 8:
        return
    typical = float(np.median(weights))
    for l in lines:
        ws = [wd.get("weight", 0) for wd in l["words"] if wd.get("weight") and len(wd["text"]) >= 2]
        l["bold"] = bool(ws) and float(np.median(ws)) > 1.25 * typical     # lines are usually set in one weight
        for wd in l["words"]:
            r = wd.pop("weight", 0) / typical
            wd["bold"] = bool(len(wd["text"]) >= 2 and (r > 1.08 if l["bold"] else r > 1.45))
        if l["bold"] and not any(wd["bold"] for wd in l["words"]):
            l["bold"] = False


def run_tesseract(image_path: Path, psm: int, scale: float = 1.0):
    if not shutil.which("tesseract"):
        sys.exit("probe.py needs the `tesseract` command (brew install tesseract / apt install tesseract-ocr)")
    res = subprocess.run(["tesseract", str(image_path), "-", "--psm", str(psm), "tsv"],
                         capture_output=True, text=True)
    if res.returncode:
        sys.exit(f"tesseract failed: {res.stderr.strip()}")
    words = []
    for r in csv.DictReader(io.StringIO(res.stdout), delimiter="\t", quoting=csv.QUOTE_NONE):
        if r["level"] != "5" or not r["text"].strip():
            continue
        x, y, w, h = (round(int(r[k]) / scale) for k in ("left", "top", "width", "height"))
        words.append({"text": r["text"], "conf": round(float(r["conf"]), 1), "box": [x, y, x + w, y + h],
                      "key": (r["block_num"], r["par_num"], r["line_num"]), "pass": f"psm{psm}"})
    return words


def overlaps(a, b):
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return False
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ix * iy > 0.3 * small


def group_lines(words):
    """Group words into lines by vertical overlap and horizontal proximity."""
    words = sorted(words, key=lambda w: ((w["box"][1] + w["box"][3]) / 2, w["box"][0]))
    lines = []
    for w in words:
        h = w["box"][3] - w["box"][1]
        cy = (w["box"][1] + w["box"][3]) / 2
        for line in lines:
            last = line[-1]
            lh = last["box"][3] - last["box"][1]
            lcy = (last["box"][1] + last["box"][3]) / 2
            if abs(cy - lcy) < 0.45 * max(h, lh) and 0 <= w["box"][0] - last["box"][2] < 2.2 * max(h, lh):
                line.append(w)
                break
        else:
            lines.append([w])
    return lines


def ocr(image_path: Path, ink=None, scale: float = 1.0):
    """Two OCR passes: full layout (psm 3), then sparse text (psm 11) for what the first pass missed,
    such as table cells, chart labels and words inside boxes. Pieces of drawings are dropped."""
    first = run_tesseract(image_path, 3, scale)
    first = [w for w in first if any(c.isalnum() for c in w["text"]) or w["conf"] > 60]
    junk = JunkFilter(ink, first) if ink is not None else (lambda w: False)
    first = [w for w in first if not junk(w)]
    second = [w for w in run_tesseract(image_path, 11, scale) if any(c.isalnum() for c in w["text"]) and not junk(w)]
    for f in first:                                  # a doubtful word: take the sparse pass's reading if it is surer
        if f["conf"] < 60:
            alt = [w for w in second if overlaps(w["box"], f["box"]) and w["conf"] >= max(60, f["conf"] + 20)]
            if len(alt) == 1:
                f.update(text=alt[0]["text"], conf=alt[0]["conf"], box=alt[0]["box"], **{"pass": "psm11"})
    extra = [w for w in second if w["conf"] >= 45 and not any(overlaps(w["box"], f["box"]) for f in first)]
    by_key = {}
    for w in first:
        by_key.setdefault(w["key"], []).append(w)
    groups = list(by_key.values()) + group_lines(extra)
    out = []
    for words in groups:
        words.sort(key=lambda w: w["box"][0])
        for w in words:
            w.pop("key", None)
            if w["text"] == "|" and len(words) > 1:
                w["text"] = "I"                      # a sans-serif capital I, not a bar
        plain = [w for w in words if not (set(w["text"]) & DESCENDERS)] or words
        baseline = int(np.median([w["box"][3] for w in plain]))
        tops = [w["box"][1] for w in words if any(c.isupper() or c.isdigit() or c in "bdfhklt" for c in w["text"])]
        cap = baseline - (int(np.median(tops)) if tops else min(w["box"][1] for w in words))
        out.append({
            "text": " ".join(w["text"] for w in words),
            "box": [min(w["box"][0] for w in words), min(w["box"][1] for w in words),
                    max(w["box"][2] for w in words), max(w["box"][3] for w in words)],
            "baseline": baseline,
            "cap_height": cap,
            "size_px": round(cap / 0.70, 1),       # typical cap height is ~0.70 of the font size
            "min_conf": min(w["conf"] for w in words),
            "words": words,
        })
    out.sort(key=lambda l: (l["box"][1], l["box"][0]))
    return out


def rules(ink, min_len):
    """Long straight horizontal and vertical strokes (table rules, underlines, frames, axes)."""
    found, mask = [], np.zeros_like(ink)
    for axis in ("h", "v"):
        size = (1, min_len) if axis == "h" else (min_len, 1)
        opened = ndi.binary_opening(ink, structure=np.ones(size, bool))
        mask |= opened
        lab, n = ndi.label(opened)
        for sl in ndi.find_objects(lab):
            y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
            if axis == "h":
                found.append({"dir": "h", "x0": x0, "x1": x1, "y": round((y0 + y1 - 1) / 2, 1), "width": y1 - y0})
            else:
                found.append({"dir": "v", "y0": y0, "y1": y1, "x": round((x0 + x1 - 1) / 2, 1), "width": x1 - x0})
    return found, ndi.binary_dilation(mask, np.ones((5, 5), bool))


def on_paper(lum, r, gap=4):
    """True when blank paper lies on both sides of a pale rule (a grid line), not when the
    'rule' is a strip of a shaded band or table header."""
    h, w = lum.shape
    if r["dir"] == "h":
        y0, y1 = int(r["y"] - r["width"] / 2), int(r["y"] + r["width"] / 2) + 1
        sides = [lum[max(y0 - gap - 2, 0):max(y0 - gap, 1), r["x0"]:r["x1"]], lum[y1 + gap:y1 + gap + 2, r["x0"]:r["x1"]]]
    else:
        x0, x1 = int(r["x"] - r["width"] / 2), int(r["x"] + r["width"] / 2) + 1
        sides = [lum[r["y0"]:r["y1"], max(x0 - gap - 2, 0):max(x0 - gap, 1)], lum[r["y0"]:r["y1"], x1 + gap:x1 + gap + 2]]
    return all(sd.size and np.median(sd) > 235 for sd in sides)


def colour_regions(rgb, min_area):
    """Connected areas of saturated colour (bars, fills, coloured lines, highlights)."""
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    mask = (sat > 0.28) & (mx > 40) & (mx - mn > 45)
    mask = ndi.binary_opening(mask, np.ones((2, 2), bool))
    lab, n = ndi.label(mask)
    out = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        region = lab[sl] == i
        area = int(region.sum())
        if area < min_area:
            continue
        col = np.median(rgb[sl][region], axis=0)
        h, w = region.shape
        out.append({"box": [sl[1].start, sl[0].start, sl[1].stop, sl[0].stop],
                    "area": area, "fill_ratio": round(area / (h * w), 2),
                    "color": "#%02x%02x%02x" % tuple(int(c) for c in col)})
    return sorted(out, key=lambda r: (r["box"][1], r["box"][0]))


def small_shapes(ink, size_px, lines=()):
    """Checkboxes (square outlines) and option bubbles (circle outlines) of text size.
    Returns (checkboxes, circles); OCR often misreads these as letters or brackets."""
    lab, n = ndi.label(ink)
    boxes, circles = [], []
    lo, hi = max(10, int(size_px * 0.55)), int(size_px * 1.6)
    words = [w["box"] for l in lines for w in l["words"]
             if w["conf"] >= 60 and sum(c.isalnum() for c in w["text"]) >= 2]

    def inside_word(x0, y0, x1, y1):
        return any(b[0] - 2 <= x0 and x1 <= b[2] + 2 and b[1] - 2 <= y0 and y1 <= b[3] + 2 for b in words)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if not (lo <= h <= hi and lo <= w <= hi) or not 0.75 <= w / h <= 1.33:
            continue
        if inside_word(sl[1].start, sl[0].start, sl[1].stop, sl[0].stop):
            continue                                           # a letter of a word OCR read well
        comp = lab[sl] == i
        t = max(2, int(round(min(h, w) * 0.15)))
        ring = np.zeros_like(comp)
        ring[:t, :] = ring[-t:, :] = ring[:, :t] = ring[:, -t:] = True
        sides = [comp[:t, :].mean(), comp[-t:, :].mean(), comp[:, :t].mean(), comp[:, -t:].mean()]
        inner = comp[t + 1:-t - 1, t + 1:-t - 1]
        inner_fill = float(inner.mean()) if inner.size else 1.0
        x0, y0 = sl[1].start, sl[0].start
        if inner_fill > 0.7:
            continue                                           # a solid swatch or block, drawn as a fill
        straight = [comp[:t].mean(1).max(), comp[-t:].mean(1).max(), comp[:, :t].mean(0).max(), comp[:, -t:].mean(0).max()]
        if min(straight) > 0.8:                                # four straight sides: a box
            whole = ink[sl[0].start:sl[0].stop, sl[1].start:sl[1].stop]
            mark = whole[t + 1:-t - 1, t + 1:-t - 1]
            boxes.append({"box": [x0, y0, x0 + w, y0 + h], "checked": bool(mark.size and mark.mean() > 0.06)})
            continue
        corners = [comp[:t, :t].mean(), comp[:t, -t:].mean(), comp[-t:, :t].mean(), comp[-t:, -t:].mean()]
        if max(corners) < 0.35 and min(sides) > 0.25 and inner_fill < 0.25:   # round outline
            circles.append({"cx": round(x0 + w / 2, 1), "cy": round(y0 + h / 2, 1), "r": round((w + h) / 4, 1),
                            "filled": inner_fill > 0.5})
    return boxes, circles


def drop_words_on_shapes(lines, shapes):
    """Remove OCR 'words' that are really a checkbox or bubble (e.g. "[Y", "LJ", "O")."""
    def covered(b):
        for s in shapes:
            x0, y0, x1, y1 = s["box"] if "box" in s else (s["cx"] - s["r"], s["cy"] - s["r"], s["cx"] + s["r"], s["cy"] + s["r"])
            ix = min(b[2], x1) - max(b[0], x0)
            iy = min(b[3], y1) - max(b[1], y0)
            if ix > 0 and iy > 0 and ix * iy > 0.5 * (b[2] - b[0]) * (b[3] - b[1]):
                return True
        return False
    out = []
    for l in lines:
        keep = [w for w in l["words"] if not (covered(w["box"]) and len(w["text"]) <= 4)]
        if keep:
            l["words"] = keep
            l["text"] = " ".join(w["text"] for w in keep)
            l["box"] = [min(w["box"][0] for w in keep), l["box"][1], max(w["box"][2] for w in keep), l["box"][3]]
            out.append(l)
    return out


class JunkFilter:
    """Recognise OCR 'words' that are pieces of drawings: slivers read off thin lines, tall
    stacks read down a column of list numbers, and doubtful words whose ink is part of a
    larger shape (an ellipse read as "Ce", an arrowhead read as "V", a chart marker as "e")."""

    def __init__(self, ink, words):
        self.lab, _ = ndi.label(ink, np.ones((3, 3), bool))
        self.objs = ndi.find_objects(self.lab)
        hs = sorted(w["box"][3] - w["box"][1] for w in words if w["conf"] >= 80) or [30]
        self.typical = hs[len(hs) // 2]

    def __call__(self, w):
        x0, y0, x1, y1 = w["box"]
        h, wd = y1 - y0, x1 - x0
        if h < max(6, 0.25 * self.typical):
            return True                                        # a sliver of a rule or dotted line
        if h > 1.8 * self.typical and (h > 1.5 * wd or w["conf"] < 80):
            return True                                        # a column of numbers or a whole shape
        if min(h, wd) > 0.6 * self.typical and (self.lab[y0:y1, x0:x1] > 0).mean() > 0.65:
            return True                                        # a solid block (legend swatch, bar end)
        if w["conf"] >= (92 if len(w["text"]) <= 2 else 80):
            return False
        ids, counts = np.unique(self.lab[y0:y1, x0:x1], return_counts=True)
        counts, ids = counts[ids > 0], ids[ids > 0]
        if not len(ids):
            return False
        sl = self.objs[int(ids[np.argmax(counts)]) - 1]
        over = max(x0 - sl[1].start, sl[1].stop - x1, y0 - sl[0].start, sl[0].stop - y1)
        return over > max(h, 20)                               # its ink runs on into a larger drawing


def drawing_strokes(ink, rule_mask):
    """Large, thin connected strokes that are not just rules (outlines of ellipses and diamonds,
    chart lines, diagonal edges): many times bigger than a letter, mostly empty inside their box.
    Their non-rule pixels are returned; letters touching a table grid are left alone."""
    lab, n = ndi.label(ink, np.ones((3, 3), bool))
    objs = ndi.find_objects(lab)
    hs = np.array([sl[0].stop - sl[0].start for sl in objs]) if objs else np.array([20])
    small = hs[(hs >= 6) & (hs <= 80)]
    letter = float(np.median(small)) if small.size else 20.0
    mask = np.zeros_like(ink)
    for i, sl in enumerate(objs, 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if max(h, w) > 6 * letter:
            comp = lab[sl] == i
            if comp.sum() < 0.3 * h * w:
                free = comp & ~rule_mask[sl]
                if free.sum() > 0.3 * comp.sum():
                    mask[sl] |= free
    return mask


def relayout(line, words):
    line = dict(line)
    line["words"] = words
    line["text"] = " ".join(w["text"] for w in words)
    line["box"] = [min(w["box"][0] for w in words), min(w["box"][1] for w in words),
                   max(w["box"][2] for w in words), max(w["box"][3] for w in words)]
    return line


def split_wide_gaps(lines):
    """Split OCR lines into rows (OCR sometimes strings a column of list numbers into one
    'line') and at very wide gaps (a label beside a drawing, cells of a table row), so each
    piece is measured on its own ink."""
    out = []
    for l in lines:
        rows = []
        for w in sorted(l["words"], key=lambda w: (w["box"][1] + w["box"][3]) / 2):
            cy, h = (w["box"][1] + w["box"][3]) / 2, w["box"][3] - w["box"][1]
            for row in rows:
                rh = np.median([q["box"][3] - q["box"][1] for q in row])
                if abs(cy - np.median([(q["box"][1] + q["box"][3]) / 2 for q in row])) < 0.6 * max(rh, h):
                    row.append(w)
                    break
            else:
                rows.append([w])
        for row in rows:
            ws = sorted(row, key=lambda w: w["box"][0])
            h = max(w["box"][3] - w["box"][1] for w in ws)
            piece = [ws[0]]
            for w in ws[1:]:
                if w["box"][0] - piece[-1]["box"][2] > max(4 * h, 120):
                    out.append(relayout(l, piece))
                    piece = []
                piece.append(w)
            out.append(relayout(l, piece))
    out.sort(key=lambda l: (l["box"][1], l["box"][0]))
    return out


def figure_candidates(ink, lines, rule_mask, pad=6):
    """Ink that is neither OCR text nor a straight rule: drawings, charts, symbols, as merged boxes."""
    rest = ink & ~rule_mask
    for l in lines:
        for w in l["words"]:
            x0, y0, x1, y1 = w["box"]
            rest[max(y0 - 2, 0):y1 + 2, max(x0 - 2, 0):x1 + 2] = False
    grown = ndi.binary_dilation(rest, np.ones((25, 25), bool))
    lab, n = ndi.label(grown)
    out = []
    for sl in ndi.find_objects(lab):
        core = rest[sl]
        if core.sum() < 400:
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        if (x1 - x0) * (y1 - y0) < 60 * 60:
            continue
        out.append({"box": [x0 + 12 - pad, y0 + 12 - pad, x1 - 12 + pad, y1 - 12 + pad],
                    "ink_px": int(core.sum())})
    return out


def guess_page(w, h):
    aspect = w / h
    name = min(PAPER, key=lambda k: abs(PAPER[k][0] / PAPER[k][1] - aspect))
    pw, ph = PAPER[name]
    if abs(pw / ph - aspect) > 0.02:
        name, pw, ph = "scan", w * 72 / 200, h * 72 / 200
    return {"name": name, "width_pt": round(pw, 2), "height_pt": round(ph, 2),
            "dpi": round(w / pw * 72, 1)}


def preview(img, data, path):
    im = Image.fromarray(img.astype(np.uint8)).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    for f in data["figures"]:
        d.rectangle(f["box"], outline=(255, 140, 0, 255), width=4)
    for r in data["rules"]:
        if r["dir"] == "h":
            d.line([(r["x0"], r["y"]), (r["x1"], r["y"])], fill=(0, 90, 255, 200), width=3)
        else:
            d.line([(r["x"], r["y0"]), (r["x"], r["y1"])], fill=(0, 90, 255, 200), width=3)
    for c in data["colour_regions"]:
        d.rectangle(c["box"], outline=(220, 0, 200, 255), width=2)
    for l in data["lines"]:
        for w in l["words"]:
            col = (0, 170, 0, 90) if w["conf"] >= 70 else (255, 0, 0, 110)
            d.rectangle(w["box"], fill=col)
        d.line([(l["box"][0], l["baseline"]), (l["box"][2], l["baseline"])], fill=(0, 120, 0, 255), width=1)
    im.save(path)


def probe_page(scan: Path, out: Path, width: int = 0, no_deskew: bool = False, paper: str = "auto") -> dict:
    """Measure one page; writes deskewed.png, ocr-input.png, probe.json and preview.png to `out`."""
    out.mkdir(parents=True, exist_ok=True)
    rgb = np.asarray(Image.open(scan).convert("RGB")).astype(np.float32)
    quad = None if no_deskew else find_page_quad(rgb)
    if quad:                                     # a photo of a sheet: flatten it first
        rgb = flatten(rgb, quad, width or 1700, paper)
    elif width and abs(rgb.shape[1] - width) > 2:
        im = Image.fromarray(rgb.astype(np.uint8))
        rgb = np.asarray(im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)).astype(np.float32)
    skew = 0.0 if no_deskew else estimate_skew(luminance(rgb))
    if skew:
        im = Image.fromarray(rgb.astype(np.uint8)).rotate(skew, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
        rgb = np.asarray(im).astype(np.float32)
    rgb, paper = normalize_light(rgb)
    deskewed = out / "deskewed.png"
    Image.fromarray(rgb.astype(np.uint8)).save(deskewed)

    h, w = rgb.shape[:2]
    lum = luminance(rgb)
    ink = lum < 150
    rule_list, rule_mask = rules(ink, max(40, w // 25))
    faint, _ = rules((lum < 225) & ~ndi.binary_dilation(rule_mask, np.ones((3, 3), bool)), max(80, w // 12))
    rule_list += [dict(r, light=True) for r in faint if r["width"] <= 6 and on_paper(lum, r)]   # pale grid lines
    ocr_img = rgb.copy()
    ocr_img[rule_mask | drawing_strokes(ink, rule_mask)] = 255   # rules and drawn outlines confuse OCR
    ocr_path = out / "ocr-input.png"            # at twice the size: Tesseract reads small print far better
    im = Image.fromarray(ocr_img.astype(np.uint8))
    im.resize((2 * w, 2 * h), Image.LANCZOS).save(ocr_path, compress_level=1)
    lines = ocr(ocr_path.resolve(), ink, scale=2.0)
    text_ink = ink & ~rule_mask                     # underlines must not pull baselines down
    sizes = [l["box"][3] - l["box"][1] for l in lines] or [30]
    checkboxes, circles = small_shapes(text_ink, float(np.median(sizes)), lines)
    lines = drop_words_on_shapes(lines, checkboxes + circles)
    lines = split_wide_gaps(lines)
    for line in lines:
        measure_line(text_ink, line)
    mark_bold(lines)
    data = {
        "source": str(scan),
        "image": deskewed.name,
        "size_px": [w, h],
        "skew_deg": skew,
        "page_quad_in_source": [[round(x, 1), round(y, 1)] for x, y in quad] if quad else None,
        "photo_aspect": getattr(flatten, "info", None) if quad else None,
        "paper_rgb": [int(c) for c in paper],
        "page": guess_page(w, h),
        "coordinates": "pixels of deskewed.png; x right, y down; text y = baseline; size_px = font size",
        "lines": lines,
        "rules": rule_list,
        "colour_regions": colour_regions(rgb, max(80, (w * h) // 20000)),
        "checkboxes": checkboxes,
        "circles": circles,
    }
    data["figures"] = figure_candidates(ink, lines, rule_mask)
    low = [wd for l in lines for wd in l["words"] if wd["conf"] < 70]
    data["summary"] = {
        "lines": len(lines), "words": sum(len(l["words"]) for l in lines),
        "low_confidence_words": len(low), "rules": len(data["rules"]),
        "colour_regions": len(data["colour_regions"]), "figure_candidates": len(data["figures"]),
        "checkboxes": len(checkboxes), "circles": len(circles),
    }
    (out / "probe.json").write_text(json.dumps(data, indent=1))
    preview(rgb, data, out / "preview.png")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("scan", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--no-deskew", action="store_true", help="skip page detection and straightening")
    ap.add_argument("--paper", default="auto",
                    help="photos: auto (snap to the nearest standard size), none (keep the estimate), or "
                         + ", ".join(PAPER))
    ap.add_argument("--width", type=int, default=0,
                    help="resample the page to this width in px (default: keep; photos become 1700)")
    args = ap.parse_args()
    if ndi is None:
        sys.exit("probe.py needs scipy for line and region detection (pip install scipy)")
    data = probe_page(args.scan, args.out, args.width, args.no_deskew, args.paper)
    print(json.dumps({"out": str(args.out), "skew_deg": data["skew_deg"], "page": data["page"],
                      "photo": bool(data["page_quad_in_source"]), **data["summary"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
