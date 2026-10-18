#!/usr/bin/env python3
"""Draft a rebuild of one or more scanned pages in one command, then keep it in sync.

    python draft.py page1.jpg [page2.jpg ...] --out work --pdf out/rebuilt.pdf
    python draft.py --rebuild work --pdf out/rebuilt.pdf      # after you edit anything

For each page, `draft` measures it (probe.py), picks the closer text face
(serif or sans), finds shaded and coloured fills and rule colours, traces every
remaining line, outline, arrow and chart series into vector shapes (shapes.py),
and writes work/pNN/:
  probe.json   OCR lines/words, rules, regions (measurements; leave as is)
  fixes.json   your corrections: {"words": {"line.word": "text"}, "add": [...]}
  draft.json   font choice, fills, rules and traced shapes (edit freely)
  build.py     short script that draws the page; add drawings in its marked section
  page.pdf, compare/diff.png, compare/words.png (proofreading sheet), compare/compare.json
Then it joins the pages into --pdf and writes work/report.md: per page, what
still differs from the scan and what to proofread. `--rebuild` reruns every
build.py, compares and joins again.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from canvas import Canvas  # noqa: E402
from canvas import load_probe  # noqa: E402
from compare import compare_page  # noqa: E402
from probe import luminance, probe_page  # noqa: E402
from shapes import find_shapes, find_washes, ink_mask  # noqa: E402

BUILD_TEMPLATE = '''#!/usr/bin/env python3
"""Rebuild page {n} from probe.json (text: fix OCR words there) and draft.json (font,
fills, rules). Add figures in the marked section, then run:
    python {draft} --rebuild {work} --pdf {pdf}
Coordinates are pixels of deskewed.png in this folder."""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, {scripts!r})
from canvas import Canvas

c = Canvas.from_probe(HERE / "probe.json")
d = json.loads((HERE / "draft.json").read_text())
for w in d.get("washes", []):                          # light colour washes, under everything
    c.outline(w["paths"], fill=w["color"])
for f in d["fills"]:                                    # shading and solid shapes, under the text
    c.rect(f["box"], stroke=None, width=0, fill=f["color"])
for s in d.get("polylines", []):                       # traced coloured lines (chart series)
    c.polyline(s["points"], width=s["width"], color=s["color"], join="round")
for r in d["rules"]:
    if r["dir"] == "h":
        c.line((r["x0"], r["y"]), (r["x1"], r["y"]), width=r["width"], color=r["color"])
    else:
        c.line((r["x"], r["y0"]), (r["x"], r["y1"]), width=r["width"], color=r["color"])
for s in d.get("shapes", []):                          # diagrams traced from the scan (delete strays)
    if s["kind"] == "line":
        c.line(*s["points"], width=s["width"], color=s["color"])
    elif s["kind"] == "ellipse":
        c.ellipse(s["box"], stroke=s["color"], width=s["width"])
    elif s["kind"] == "polygon":
        c.polyline(s["points"], width=s["width"], color=s["color"], closed=True)
    else:
        c.outline(s["paths"], fill=s["color"])
for b in c.probe.get("checkboxes", []):               # tick boxes and option bubbles found by the probe
    c.checkbox(b["box"], checked=b["checked"], width=max(2, (b["box"][2] - b["box"][0]) * 0.08))
for o in c.probe.get("circles", []):
    c.circle((o["cx"], o["cy"]), o["r"] - 1, width=max(2, o["r"] * 0.15), fill="#000000" if o["filled"] else None)
c.place_lines(c.probe["lines"], font=d["font"])
c.place_added(font=d["font"])                          # words added in fixes.json

# ---- anything the report still lists as missing ------------------------------------
# Figure areas found by the probe (most are already traced into draft.json "shapes"):
{figures}
# Examples: c.polyline([(x, y), ...], width=3, color="#000000", closed=True)
#           c.circle((cx, cy), r, width=2)   c.arrow(p0, p1, width=2)   c.checkbox(box, checked=True)
#           c.text(x, baseline, "Label", size=28, font=d["font"], align="center")
# --------------------------------------------------------------------------------

c.save(HERE / "page.pdf")
'''


def hexcol(c):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, v))) for v in c)


def detect_fills(rgb, probe):
    """Shaded boxes, table header and zebra rows, bars and other solid rectangles."""
    lum = luminance(rgb)
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    smooth = ndi.uniform_filter(lum, 5)
    fills = []
    light = (smooth > 165) & (smooth < 246) & (ndi.uniform_filter(sat, 5) < 0.12)
    light = ndi.binary_opening(ndi.binary_closing(light, np.ones((7, 7), bool)), np.ones((9, 9), bool))
    lab, n = ndi.label(light)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        comp = lab[sl] == i
        h, w = comp.shape
        if comp.sum() < 4000 or comp.sum() / (h * w) < 0.85 or min(h, w) < 12 or h * w > 0.5 * lum.size:
            continue
        px = rgb[sl][comp & (lum[sl] > 165)]
        fills.append({"box": [sl[1].start, sl[0].start, sl[1].stop, sl[0].stop],
                      "color": hexcol(np.median(px, 0)), "kind": "shade"})
    for r in probe.get("colour_regions", []):
        x0, y0, x1, y1 = r["box"]
        if r["fill_ratio"] >= 0.92 and min(x1 - x0, y1 - y0) >= 6:     # rectangles; other shapes are traced
            fills.append({"box": r["box"], "color": r["color"], "kind": "solid"})
    # dark solid shapes (grey or black bars, filled boxes): thick, rectangular, not text
    words = np.zeros(lum.shape, bool)
    for l in probe["lines"]:
        for w in l["words"]:
            x0, y0, x1, y1 = w["box"]
            words[y0:y1, x0:x1] = True
    dark = ndi.binary_opening(lum < 150, np.ones((7, 7), bool)) & ~words
    lab, n = ndi.label(dark)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        comp = lab[sl] == i
        h, w = comp.shape
        if comp.sum() < 300 or comp.sum() / (h * w) < 0.85 or min(h, w) < 8:
            continue
        box = [sl[1].start, sl[0].start, sl[1].stop, sl[0].stop]
        if any(abs(f["box"][0] - box[0]) < 4 and abs(f["box"][1] - box[1]) < 4 for f in fills):
            continue
        fills.append({"box": box, "color": hexcol(np.median(rgb[sl][comp], 0)), "kind": "solid"})
    return fills


def simplify(pts, eps=1.0):
    """Ramer-Douglas-Peucker polyline simplification."""
    if len(pts) < 3:
        return pts
    a, b = np.array(pts[0], float), np.array(pts[-1], float)
    ab = b - a
    norm = np.hypot(*ab) or 1.0
    d = [abs(ab[0] * (p[1] - a[1]) - ab[1] * (p[0] - a[0])) / norm for p in pts[1:-1]]
    i = int(np.argmax(d)) + 1
    if d[i - 1] > eps:
        return simplify(pts[:i + 1], eps)[:-1] + simplify(pts[i:], eps)
    return [pts[0], pts[-1]]


def trace_series(rgb, probe):
    """Coloured lines that pass once through each column (chart series, coloured curves):
    traced into polylines with their colour and stroke width."""
    out = []
    for r in probe.get("colour_regions", []):
        x0, y0, x1, y1 = r["box"]
        if r["fill_ratio"] > 0.3 or x1 - x0 < 120 or y1 - y0 < 20 or r["area"] < 1500:
            continue
        target = np.array([int(r["color"][i:i + 2], 16) for i in (1, 3, 5)], float)
        sub = rgb[y0:y1, x0:x1]
        mask = np.linalg.norm(sub - target, axis=-1) < 70
        cols, single, widths = [], 0, []
        for x in range(mask.shape[1]):
            ys = np.flatnonzero(mask[:, x])
            if not len(ys):
                cols.append(None)
                continue
            runs = np.split(ys, np.flatnonzero(np.diff(ys) > 2) + 1)
            if len(runs) == 1:
                single += 1
                widths.append(len(runs[0]))
            run = max(runs, key=len)
            cols.append((x0 + x + 0.5, y0 + (run[0] + run[-1]) / 2 + 0.5))
        present = [c for c in cols if c]
        if len(present) < 0.6 * mask.shape[1] or single < 0.8 * len(present):
            continue                                  # frames, text and fills are not series
        width = float(np.clip(np.median(widths) * 0.85, 1, 8))
        seg, segs = [], []
        for c in cols:
            if c is None:
                if len(seg) > 3:
                    segs.append(seg)
                seg = []
            else:
                seg.append(c)
        if len(seg) > 3:
            segs.append(seg)
        for sg in segs:
            pts = [[round(x, 1), round(y, 1)] for x, y in simplify(sg, 1.2)]
            out.append({"points": pts, "color": r["color"], "width": round(width, 1)})
    return out


def rule_colours(rgb, rules):
    out = []
    for r in rules:
        if r["width"] > 10:                      # a bar or block, drawn as a fill instead
            continue
        if r["dir"] == "h":
            y0 = int(r["y"] - r["width"] / 2)
            px = rgb[max(y0, 0):y0 + r["width"] + 1, r["x0"]:r["x1"]].reshape(-1, 3)
        else:
            x0 = int(r["x"] - r["width"] / 2)
            px = rgb[r["y0"]:r["y1"], max(x0, 0):x0 + r["width"] + 1].reshape(-1, 3)
        lum = luminance(px) if len(px) else np.array([])
        dark = px[lum <= np.percentile(lum, 35)] if len(px) else px       # the rule's core, not the paper
        col = np.median(dark, 0) if len(dark) else np.array([0, 0, 0])
        if luminance(col[None])[0] < 70:
            col = np.array([0, 0, 0])
        out.append({**r, "color": hexcol(col)})
    return out


def choose_font(page_dir, probe, rgb):
    """Render the text in serif and in sans; keep the one whose ink sits closer to the scan's."""
    lum = luminance(rgb)
    scan_ink = lum < 150
    mask = np.zeros_like(scan_ink)
    for l in probe["lines"]:
        for w in l["words"]:
            x0, y0, x1, y1 = w["box"]
            mask[max(l["baseline"] - int(l.get("cap_height", 30)) - 3, 0):l["baseline"] + 8, x0:x1] = True
    scan_t = scan_ink & mask
    disk = ndi.iterate_structure(ndi.generate_binary_structure(2, 1), 2)
    sd = ndi.binary_dilation(scan_t, disk)
    best = ("serif", -1.0)
    for font in ("serif", "sans"):
        c = Canvas.from_probe(page_dir / "probe.json")
        c.place_lines(c.probe["lines"], font=font)
        z = rgb.shape[1] / c.page.rect.width
        pix = c.page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False, colorspace=pymupdf.csRGB)
        img = np.asarray(Image.frombytes("RGB", (pix.width, pix.height), pix.samples)).astype(np.float32)
        out = np.zeros_like(scan_ink)
        hh, ww = min(out.shape[0], img.shape[0]), min(out.shape[1], img.shape[1])
        out[:hh, :ww] = luminance(img[:hh, :ww]) < 150
        out &= mask
        od = ndi.binary_dilation(out, disk)
        p = (out & sd).sum() / max(out.sum(), 1)
        r = (scan_t & od).sum() / max(scan_t.sum(), 1)
        f1 = 2 * p * r / (p + r) if p + r else 0
        if f1 > best[1]:
            best = (font, float(f1))
    return best


def text_colours(rgb, probe):
    """Give coloured words (red warnings, blue headings) their ink colour; black stays default."""
    lum = luminance(rgb)
    for l in probe["lines"]:
        for w in l["words"]:
            x0, y0, x1, y1 = w["box"]
            px = rgb[y0:y1, x0:x1][lum[y0:y1, x0:x1] < 160]
            if len(px) < 15:
                continue
            c = np.median(px, 0)
            if (c.max() - c.min()) / max(c.max(), 1) > 0.3:
                w["color"] = hexcol(c)


def draft_page(scan: Path, page_dir: Path, n: int, work: Path, pdf: Path, paper: str = "auto"):
    probe = probe_page(scan, page_dir, paper=paper)
    rgb = np.asarray(Image.open(page_dir / probe["image"]).convert("RGB")).astype(np.float32)
    text_colours(rgb, probe)
    (page_dir / "probe.json").write_text(json.dumps(probe, indent=1))
    font, f1 = choose_font(page_dir, probe, rgb)
    fills = detect_fills(rgb, probe)
    draft = {"font": font, "font_fit": round(f1, 3), "washes": find_washes(rgb, fills),
             "fills": fills, "rules": rule_colours(rgb, probe["rules"]), "polylines": []}
    (page_dir / "draft.json").write_text(json.dumps(draft, indent=1))
    figs = "\n".join(f"#   {f['box']}   zoom: python {HERE / 'zoom.py'} {page_dir / 'deskewed.png'} "
                     f"{' '.join(str(v) for v in f['box'])} --grid 50 --out {page_dir / 'zoom.png'}"
                     for f in probe["figures"]) or "#   (none)"
    (page_dir / "build.py").write_text(BUILD_TEMPLATE.format(
        n=n, draft=HERE / "draft.py", work=work, pdf=pdf, scripts=str(HERE), figures=figs))
    # whatever drawing ink is still unexplained becomes vector shapes
    subprocess.run([sys.executable, str(page_dir / "build.py")], check=True, capture_output=True)
    with pymupdf.open(page_dir / "page.pdf") as doc:
        z = rgb.shape[1] / doc[0].rect.width
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False, colorspace=pymupdf.csRGB)
    img = np.asarray(Image.frombytes("RGB", (pix.width, pix.height), pix.samples)).astype(np.float32)
    drawn = np.zeros(rgb.shape[:2], bool)
    hh, ww = min(drawn.shape[0], img.shape[0]), min(drawn.shape[1], img.shape[1])
    drawn[:hh, :ww] = ink_mask(img[:hh, :ww])
    words = [w["box"] for l in probe["lines"] for w in l["words"]]
    size = float(np.median([l["size_px"] for l in probe["lines"]])) if probe["lines"] else 30.0
    palette = []                                        # the page's distinct ink colours
    for r in probe.get("colour_regions", []):
        c = np.array([int(r["color"][i:i + 2], 16) for i in (1, 3, 5)], float)
        if all(np.linalg.norm(c - np.array([int(q[i:i + 2], 16) for i in (1, 3, 5)])) > 60 for q in palette):
            palette.append(r["color"])
    draft["shapes"], draft["unexplained_marks"] = find_shapes(rgb, drawn, words, size, palette)
    (page_dir / "draft.json").write_text(json.dumps(draft, indent=1))


def proof_sheet(page_dir: Path, probe: dict, cmp: dict, limit: int = 36):
    """compare/words.png: every doubtful OCR word and every undrawn mark, cropped from the scan
    and enlarged, with its id and current reading, so one look checks them all."""
    from PIL import ImageDraw, ImageFont
    scan = Image.open(page_dir / probe["image"]).convert("RGB")
    items = sorted(((w["conf"], f"{li}.{wi}", w["text"], w["box"]) for li, l in enumerate(probe["lines"])
                    for wi, w in enumerate(l["words"]) if w["conf"] < 80), key=lambda t: t[0])[:limit]
    items = [(f"{k}", repr(t), b) for _, k, t, b in items]
    items += [("?", "not drawn yet", m["box"]) for m in cmp.get("missing_regions", [])[:max(0, limit - len(items))]]
    path = page_dir / "compare" / "words.png"
    if not items:
        path.unlink(missing_ok=True)
        return [], None
    cw, ch, cols = 440, 110, 3
    sheet = Image.new("RGB", (cw * cols, 34 + ch * ((len(items) + cols - 1) // cols)), "white")
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=17)
    d.text((8, 7), "Scan crop above, current reading below. Correct wrong readings in fixes.json.", fill="black", font=font)
    for i, (key, label, box) in enumerate(items):
        x0, y0, x1, y1 = box
        crop = scan.crop((max(x0 - 10, 0), max(y0 - 10, 0), x1 + 10, y1 + 10))
        k = min(3.0, 64 / max(crop.height, 1), (cw - 16) / max(crop.width, 1))
        crop = crop.resize((max(1, int(crop.width * k)), max(1, int(crop.height * k))), Image.LANCZOS)
        cx, cy = (i % cols) * cw, 34 + (i // cols) * ch
        sheet.paste(crop, (cx + 8, cy + 4))
        d.rectangle((cx + 2, cy, cx + cw - 2, cy + ch - 2), outline=(200, 200, 200))
        d.text((cx + 8, cy + ch - 26), f"{key}  {label}"[:44], fill=(200, 0, 0) if key == "?" else (0, 0, 160), font=font)
    sheet.save(path)
    return items, path


def rebuild(work: Path, pdf: Path, pass_f1: float):
    pages = sorted(p for p in work.iterdir() if p.is_dir() and (p / "build.py").exists())
    if not pages:
        sys.exit(f"no page folders with build.py in {work}")
    joined = pymupdf.open()
    report = ["# Rebuild report", ""]
    all_pass = True
    for page_dir in pages:
        res = subprocess.run([sys.executable, str(page_dir / "build.py")], capture_output=True, text=True)
        if res.returncode:
            all_pass = False
            report += [f"## {page_dir.name}: build.py failed", "```", res.stderr[-2000:], "```", ""]
            continue
        cmp = compare_page(page_dir / "page.pdf", page_dir / "probe.json", page_dir / "compare", pass_f1)
        probe = load_probe(page_dir / "probe.json")
        draft = json.loads((page_dir / "draft.json").read_text())
        with pymupdf.open(page_dir / "page.pdf") as src:
            joined.insert_pdf(src)
        all_pass &= cmp["verdict"] == "PASS"
        items, sheet = proof_sheet(page_dir, probe, cmp)
        report += [f"## {page_dir.name}: {cmp['verdict']}  (ink F1 {cmp['ink_f1']}, font {draft['font']})",
                   f"- diff: {page_dir / 'compare' / 'diff.png'}  (red = not drawn yet, blue = drawn where the scan is blank)"]
        for p in cmp["problems"]:
            report.append(f"- problem: {p}")
        for p in cmp.get("checks", []):
            report.append(f"- check: {p}")
        if sheet:
            report.append(f"- proofread: {sheet}  (each crop with its id: line.word, or ? for ink not drawn yet)")
            report.append("  " + "; ".join(f"{k} {lab} {b}" for k, lab, b in items))
        else:
            report.append("- proofread: nothing doubtful")
        if cmp["extra_regions"]:
            report.append("- drawn where the scan is blank: " + ", ".join(str(m["box"]) for m in cmp["extra_regions"][:6]))
        if cmp["unseen_words"]:
            report.append("- words in the PDF that OCR never saw (confirm on a zoom): " + ", ".join(cmp["unseen_words"][:25]))
        if cmp["colour_mismatches"]:
            report.append("- colour mismatches: " + "; ".join(f"{c['box']} scan {c['scan']} vs {c['rebuilt']}" for c in cmp["colour_mismatches"][:6]))
        report.append("")
    pdf.parent.mkdir(parents=True, exist_ok=True)
    joined.save(pdf, garbage=3, deflate=True)
    report.insert(1, f"Joined PDF: {pdf} ({joined.page_count} pages). Overall: {'PASS' if all_pass else 'FIX'}")
    (work / "report.md").write_text("\n".join(report) + "\n")
    print("\n".join(report))
    return all_pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("scans", nargs="*", type=Path)
    ap.add_argument("--out", type=Path, default=Path("work"))
    ap.add_argument("--pdf", type=Path, default=Path("out/rebuilt.pdf"))
    ap.add_argument("--rebuild", type=Path, help="rerun build.py in every page folder of this work dir")
    ap.add_argument("--pass-f1", type=float, default=0.92)
    ap.add_argument("--paper", default="auto",
                    help="photographed pages: auto (snap to the nearest standard size), none, or letter/a4/legal/a5")
    args = ap.parse_args()
    if args.rebuild:
        return 0 if rebuild(args.rebuild.resolve(), args.pdf.resolve(), args.pass_f1) else 1
    if not args.scans:
        ap.error("give scan images, or --rebuild WORKDIR")
    work = args.out.resolve()
    for n, scan in enumerate(args.scans, 1):
        page_dir = work / f"p{n:02d}"
        print(f"drafting {scan} -> {page_dir}", file=sys.stderr)
        draft_page(scan.resolve(), page_dir, n, work, args.pdf.resolve(), args.paper)
    return 0 if rebuild(work, args.pdf.resolve(), args.pass_f1) else 1


if __name__ == "__main__":
    raise SystemExit(main())
