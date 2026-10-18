#!/usr/bin/env python3
"""Score a rebuilt PDF against a benchmark page's ground truth.

    python bench/score.py <page dir with truth.pdf/truth.json> <rebuilt.pdf> [--diff out.png]

Metrics (all 0..1, higher is better unless noted):
  text_f1     bag-of-words F1 between the PDF's extractable text and the truth
  text_prec   share of output words that exist in the truth (low = invented text)
  layout_f1   ink overlap with the true page after automatic registration
              (tolerance 4 px at 200 dpi, about 0.5 mm)
  figure      ink F1 inside each true figure region x share of it that is vector
  raster      share of the page covered by embedded images (lower is better)
  score       0.35 text_f1 + 0.25 layout_f1 + 0.30 figure + 0.10 (1 - raster)

Registration searches small rotations, scales and shifts so that page size,
margins and deskewing do not decide the result; content placement does.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image
from scipy import ndimage as ndi

INK_LUMA = 200
TOL = 4
WEIGHTS = {"text_f1": 0.35, "layout_f1": 0.25, "figure": 0.30, "vector": 0.10}


def norm_words(words):
    out = []
    for w in words:
        w = unicodedata.normalize("NFKC", w).lower()
        w = re.sub(r"^[^\w]+|[^\w]+$", "", w)
        if w:
            out.append(w)
    return out


def text_scores(truth_words, out_words):
    t, o = Counter(norm_words(truth_words)), Counter(norm_words(out_words))
    hit = sum((t & o).values())
    rec = hit / max(sum(t.values()), 1)
    prec = hit / max(sum(o.values()), 1) if o else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return f1, prec, rec


def render(page, width_px):
    z = width_px / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False, colorspace=pymupdf.csRGB)
    return np.asarray(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))


def ink(rgb):
    luma = rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114
    return luma < INK_LUMA


def fit(mask, shape):
    """Place mask on a canvas of `shape` (crop or pad at bottom/right)."""
    out = np.zeros(shape, bool)
    h, w = min(shape[0], mask.shape[0]), min(shape[1], mask.shape[1])
    out[:h, :w] = mask[:h, :w]
    return out


def transform(mask, angle, scale, shape):
    im = Image.fromarray(mask.astype(np.uint8) * 255)
    if scale != 1:
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.BILINEAR)
    if angle:
        im = im.rotate(angle, resample=Image.BILINEAR, expand=False)
    return fit(np.asarray(im) > 127, shape)


def best_shift(a, b, max_shift):
    """Shift (dy, dx) applied to b that maximises overlap with a (FFT cross-correlation)."""
    fa, fb = np.fft.rfft2(a), np.fft.rfft2(b)
    corr = np.fft.irfft2(fa * np.conj(fb), s=a.shape)
    corr = np.roll(np.roll(corr, max_shift, 0), max_shift, 1)[: 2 * max_shift + 1, : 2 * max_shift + 1]
    dy, dx = np.unravel_index(np.argmax(corr), corr.shape)
    return dy - max_shift, dx - max_shift, corr.max()


def shift(mask, dy, dx):
    out = np.zeros_like(mask)
    h, w = mask.shape
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = mask[ys, xs]
    return out


def register(truth_mask, out_mask):
    k = 4
    small = lambda m: ndi.uniform_filter(m.astype(np.float32), 3)[::k, ::k]
    ts = small(truth_mask)
    best = (-1, 0, 1.0, 0, 0)
    for scale in np.arange(0.90, 1.101, 0.02):
        for angle in np.arange(-1.5, 1.51, 0.25):
            cand = transform(out_mask, float(angle), float(scale), out_mask.shape)
            dy, dx, val = best_shift(ts, small(cand), 60)
            if val > best[0]:
                best = (val, float(angle), round(float(scale), 3), int(dy) * k, int(dx) * k)
    _, angle, scale, dy, dx = best
    moved = shift(transform(out_mask, angle, scale, out_mask.shape), dy, dx)
    # refine the shift at full resolution
    blur = lambda m: ndi.uniform_filter(m.astype(np.float32), 5)
    fy, fx, _ = best_shift(blur(truth_mask), blur(moved), 6)
    moved = shift(moved, int(fy), int(fx))
    return moved, {"angle": angle, "scale": scale, "dy": dy + int(fy), "dx": dx + int(fx)}


def ink_f1(truth, out, disk):
    if not truth.any() and not out.any():
        return 1.0
    if not truth.any() or not out.any():
        return 0.0
    td, od = ndi.binary_dilation(truth, disk), ndi.binary_dilation(out, disk)
    prec = (out & td).sum() / out.sum()
    rec = (truth & od).sum() / truth.sum()
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def raster_mask(page, shape, z, reg):
    m = np.zeros(shape, bool)
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & page.rect
        if r.is_empty:
            continue
        x0, y0, x1, y1 = (int(v * z) for v in r)
        m[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)] = True
    return shift(transform(m, reg["angle"], reg["scale"], shape), reg["dy"], reg["dx"])


def score(page_dir: Path, pdf: Path, diff: Path | None = None, page_index: int = 0) -> dict:
    truth = json.loads((page_dir / "truth.json").read_text())
    zero = {"text_f1": 0, "text_prec": 0, "text_rec": 0, "layout_f1": 0, "figure": 0, "raster": 1,
            "score": 0, "ok": False}
    if not pdf.exists():
        return {**zero, "error": "missing output"}
    try:
        doc = pymupdf.open(pdf)
        if page_index >= doc.page_count:
            return {**zero, "error": f"page {page_index + 1} missing"}
        page = doc[page_index]
    except Exception as exc:  # unreadable PDF
        return {**zero, "error": f"unreadable: {exc}"}
    words = [w[4] for w in page.get_text("words")] if doc.page_count > 1 else \
        [w[4] for p in doc for w in p.get_text("words")]
    t_f1, t_prec, t_rec = text_scores(truth["words"], words)

    with pymupdf.open(page_dir / "truth.pdf") as tdoc:
        tr = render(tdoc[0], truth["scan_px"][0])
    tmask = ink(tr)
    orgb = render(page, truth["scan_px"][0])
    omask = fit(ink(orgb), tmask.shape)
    moved, reg = register(tmask, omask)
    disk = ndi.generate_binary_structure(2, 1)
    disk = ndi.iterate_structure(disk, TOL)
    layout = ink_f1(tmask, moved, disk)

    z = truth["scan_px"][0] / page.rect.width
    rmask = raster_mask(page, tmask.shape, z, reg)
    raster = float(rmask.mean())
    px = truth["dpi"] / 72
    figs = []
    for f in truth["figures"]:
        x0, y0, x1, y1 = (int(round(v * px)) for v in f["bbox_pt"])
        x0, y0 = max(x0 - 6, 0), max(y0 - 6, 0)
        sl = (slice(y0, y1 + 6), slice(x0, x1 + 6))
        f1 = ink_f1(tmask[sl], moved[sl], disk)
        vec = 1 - float(rmask[sl].mean())
        figs.append({"kind": f["kind"], "ink_f1": round(f1, 3), "vector": round(vec, 3), "score": round(f1 * vec, 3)})
    figure = float(np.mean([f["score"] for f in figs])) if figs else layout
    total = (WEIGHTS["text_f1"] * t_f1 + WEIGHTS["layout_f1"] * layout
             + WEIGHTS["figure"] * figure + WEIGHTS["vector"] * (1 - raster))
    if diff:
        vis = np.full(tmask.shape + (3,), 255, np.uint8)
        vis[tmask & moved] = (40, 40, 40)
        vis[tmask & ~ndi.binary_dilation(moved, disk)] = (230, 40, 40)   # missing
        vis[moved & ~ndi.binary_dilation(tmask, disk)] = (40, 90, 230)   # extra / misplaced
        Image.fromarray(vis).save(diff)
    return {"text_f1": round(t_f1, 3), "text_prec": round(t_prec, 3), "text_rec": round(t_rec, 3),
            "layout_f1": round(layout, 3), "figure": round(figure, 3), "raster": round(raster, 3),
            "score": round(total, 3), "ok": True, "pages": doc.page_count, "registration": reg,
            "figures": figs, "out_words": len(words)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("page_dir", type=Path)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--diff", type=Path)
    args = ap.parse_args()
    print(json.dumps(score(args.page_dir, args.pdf, args.diff), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
