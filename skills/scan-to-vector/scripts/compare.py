#!/usr/bin/env python3
"""Check a rebuilt page against its scan and say what to fix.

    python compare.py out/rebuilt.pdf work/probe/probe.json --out work/compare

Renders the PDF in the scan's coordinates and compares ink:
  ink_f1        overlap of drawn ink with scan ink (tolerance 3 px)
  missing       regions of scan ink with nothing drawn there (largest first)
  extra         regions drawn where the scan is blank (misplaced or invented)
  text          OCR words missing from the PDF text, and PDF words the OCR never saw
  colours       coloured regions whose rebuilt colour is far from the scan's
  raster        share of the page covered by embedded images
Writes compare.json and diff.png (red = missing, blue = extra, grey = matched)
and exits 0 on PASS, 1 when something needs fixing. "checks" are advisory: words you
added by hand and colour differences to confirm, not failures.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canvas import load_probe  # noqa: E402
from shapes import ink_mask  # noqa: E402

INK = 165
TOL = 3


def luminance(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def norm(w):
    return re.sub(r"^[^\w]+|[^\w]+$", "", w.lower())


def components(mask, limit=12, min_area=40):
    mask = ndi.binary_opening(mask, np.ones((2, 2), bool))
    lab, n = ndi.label(ndi.binary_dilation(mask, np.ones((9, 9), bool)))
    out = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        area = int((mask[sl] & (lab[sl] == i)).sum())
        if area >= min_area:
            out.append({"box": [sl[1].start, sl[0].start, sl[1].stop, sl[0].stop], "ink_px": area})
    return sorted(out, key=lambda c: -c["ink_px"])[:limit]


def compare_page(pdf: Path, probe_path: Path, out: Path, pass_f1: float = 0.92,
                 allow_raster: float = 0.0, page_index: int = 0) -> dict:
    """Compare one PDF page with its probed scan; writes compare.json and diff.png to `out`."""
    out.mkdir(parents=True, exist_ok=True)
    probe = load_probe(probe_path)                                       # fixes.json applied
    scan = np.asarray(Image.open(probe_path.parent / probe["image"]).convert("RGB")).astype(np.float32)
    h, w = scan.shape[:2]
    doc = pymupdf.open(pdf)
    page = doc[page_index]
    z = w / page.rect.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False, colorspace=pymupdf.csRGB)
    rendered = np.asarray(Image.frombytes("RGB", (pix.width, pix.height), pix.samples)).astype(np.float32)
    canvas = np.full_like(scan, 255)
    hh, ww = min(h, rendered.shape[0]), min(w, rendered.shape[1])
    canvas[:hh, :ww] = rendered[:hh, :ww]
    rendered = canvas

    s_ink = ink_mask(scan, INK)
    s_ink = ndi.binary_opening(s_ink, np.ones((2, 2), bool))          # drop scan speckle
    o_ink = ink_mask(rendered, INK)
    # tolerate a small global offset
    best = (0, 0, -1)
    for dy in range(-6, 7, 2):
        for dx in range(-6, 7, 2):
            v = (np.roll(np.roll(o_ink, dy, 0), dx, 1) & s_ink).sum()
            if v > best[2]:
                best = (dy, dx, v)
    o_ink = np.roll(np.roll(o_ink, best[0], 0), best[1], 1)
    disk = ndi.iterate_structure(ndi.generate_binary_structure(2, 1), TOL)
    s_d, o_d = ndi.binary_dilation(s_ink, disk), ndi.binary_dilation(o_ink, disk)
    prec = float((o_ink & (s_d | ndi.binary_dilation(luminance(scan) < 215, disk))).sum() / max(o_ink.sum(), 1))
    rec = float((s_ink & o_d).sum() / max(s_ink.sum(), 1))
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    missing_mask = s_ink & ~o_d
    faint = ndi.binary_dilation(luminance(scan) < 215, disk)   # pale rules and tints still count as "on the scan"
    extra_mask = o_ink & ~s_d & ~faint

    ocr = Counter(norm(t) for l in probe["lines"] for wd in l["words"] if wd["conf"] >= 60 for t in wd["text"].split())
    ocr.update(norm(w) for a in probe.get("_added", []) for w in a["text"].split())
    ocr.pop("", None)
    pdf_words = Counter(norm(x[4]) for x in page.get_text("words"))
    pdf_words.pop("", None)
    missing_words = sorted((ocr - pdf_words).elements())
    known = Counter(norm(t) for l in probe["lines"] for wd in l["words"] for t in wd["text"].split())
    known.update(norm(w) for a in probe.get("_added", []) for w in a["text"].split())
    unseen_words = sorted((pdf_words - known).elements())

    colours = []
    for reg in probe.get("colour_regions", []):
        x0, y0, x1, y1 = reg["box"]
        sm = scan[y0:y1, x0:x1].reshape(-1, 3)
        om = rendered[y0:y1, x0:x1].reshape(-1, 3)
        sel = (sm.max(1) - sm.min(1)) > 45
        if sel.sum() < 20:
            continue
        sc, oc = np.median(sm[sel], 0), np.median(om[sel], 0)
        dist = float(np.linalg.norm(sc - oc))
        if dist > 70:
            colours.append({"box": reg["box"], "scan": "#%02x%02x%02x" % tuple(int(c) for c in sc),
                            "rebuilt": "#%02x%02x%02x" % tuple(int(c) for c in oc), "distance": round(dist)})

    area = page.rect.width * page.rect.height
    raster = sum((pymupdf.Rect(i["bbox"]) & page.rect).get_area() for i in page.get_image_info()) / area
    invisible = sum(1 for t in page.get_texttrace() if t.get("type") == 3)

    vis = np.full((h, w, 3), 255, np.uint8)
    vis[s_ink & o_d] = (170, 170, 170)
    vis[missing_mask] = (225, 30, 30)
    vis[extra_mask] = (30, 80, 230)
    Image.fromarray(vis).save(out / "diff.png")

    problems = []
    if f1 < pass_f1:
        problems.append(f"ink_f1 {f1:.3f} below {pass_f1}")
    if raster > allow_raster + 0.01:
        problems.append(f"raster covers {raster:.0%} of the page")
    if invisible:
        problems.append("hidden (invisible) text found: draw real visible text instead")
    big = [m for m in components(missing_mask) if m["ink_px"] >= 500]
    if big:
        problems.append(f"{len(big)} region(s) of the scan not drawn yet: " + ", ".join(str(m["box"]) for m in big[:6]))
    if len(missing_words) > 2:
        problems.append(f"{len(missing_words)} OCR words are not in the PDF text")
    checks = []
    if unseen_words:
        checks.append(f"{len(unseen_words)} PDF words were never seen by OCR: confirm each on a zoom (fine if they are on the scan)")
    if colours:
        checks.append(f"{len(colours)} coloured regions differ in colour from the scan")
    result = {
        "verdict": "PASS" if not problems else "FIX",
        "problems": problems,
        "checks": checks,
        "ink_f1": round(f1, 3), "ink_precision": round(prec, 3), "ink_recall": round(rec, 3),
        "offset_px": [best[1], best[0]],
        "missing_regions": components(missing_mask),
        "extra_regions": components(extra_mask),
        "missing_words": missing_words[:60],
        "unseen_words": unseen_words[:60],
        "colour_mismatches": colours[:12],
        "raster_share": round(raster, 3),
        "diff": str(out / "diff.png"),
    }
    (out / "compare.json").write_text(json.dumps(result, indent=1))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("probe", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--page", type=int, default=1, help="one-based page of the PDF to check")
    ap.add_argument("--pass-f1", type=float, default=0.92)
    ap.add_argument("--allow-raster", type=float, default=0.0,
                    help="share of the page that may stay raster (photos, engravings)")
    args = ap.parse_args()
    result = compare_page(args.pdf, args.probe, args.out, args.pass_f1, args.allow_raster, args.page - 1)
    print(json.dumps(result, indent=1))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
