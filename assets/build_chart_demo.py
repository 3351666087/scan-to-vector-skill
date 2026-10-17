#!/usr/bin/env python3
"""Build assets/playfair.svg: the chart-to-data animation for the README.

A cursor sweeps Playfair's 1786 chart year by year. Behind it the engraving
gives way to the chart redrawn from data.csv, while a readout shows the
values recovered for each year. Everything comes from demo/playfair-1786.

    python assets/build_chart_demo.py      # needs PyMuPDF and Pillow
"""

from __future__ import annotations

import base64
import csv
import importlib.util
import io
import re
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo" / "playfair-1786"
OUT = ROOT / "assets" / "playfair.svg"

spec = importlib.util.spec_from_file_location("playfair", DEMO / "rebuilt" / "build.py")
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)

W, H, DUR = 1280, 624, 10
CX, CY, CW = 32, 32, 760                  # chart placement on the canvas
S = CW / pf.SCAN_W
CH = pf.SCAN_H * S
SWEEP = (0.06, 0.66)
BACK = (0.92, 0.98)
SANS = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
TEAL, EXP, IMP = "#2dd4bf", "#e0607a", "#f0a14e"


def X(x):
    return CX + x * S


def Y(y):
    return CY + y * S


def kt(t):
    return f"{t:.4f}".rstrip("0").rstrip(".") or "0"


def anim(attr, frames, mode="linear", kind="animate"):
    frames = sorted(frames)
    if frames[0][0] > 0:
        frames.insert(0, (0, frames[0][1]))
    if frames[-1][0] < 1:
        frames.append((1, frames[-1][1]))
    extra = ' type="translate"' if kind == "animateTransform" else ""
    return (f'<{kind} attributeName="{attr}"{extra} dur="{DUR}s" repeatCount="indefinite" calcMode="{mode}" '
            f'keyTimes="{";".join(kt(t) for t, _ in frames)}" values="{";".join(str(v) for _, v in frames)}"/>')


def year_t(year):
    return SWEEP[0] + (SWEEP[1] - SWEEP[0]) * (year - 1700) / 80


def vector_symbol():
    with pymupdf.open(DEMO / "rebuilt" / "playfair-1786.pdf") as doc:
        page = doc[0]
        svg = page.get_svg_image(text_as_path=True)
        vb = f"0 0 {page.rect.width:g} {page.rect.height:g}"
    inner = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")]
    inner = re.sub(r'\bid="([^"]+)"', r'id="p-\1"', inner)
    inner = re.sub(r'href="#([^"]+)"', r'href="#p-\1"', inner)
    return (f'<symbol id="chart" viewBox="{vb}" preserveAspectRatio="none">'
            f'<rect width="100%" height="100%" fill="#fff"/>{inner}</symbol>')


def build() -> str:
    with (DEMO / "rebuilt" / "data.csv").open() as fh:
        rows = [(int(r["year"]), float(r["exports"]), float(r["imports"])) for r in csv.DictReader(fh)]
    scan = Image.open(DEMO / "source" / "scan.png").convert("RGB")
    buf = io.BytesIO()
    scan.resize((int(CW * 2), int(CH * 2)), Image.LANCZOS).save(buf, "JPEG", quality=70)
    scan_uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    x0, x1 = pf.X_GRID[0], pf.X_GRID[-1]
    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" aria-label="A cursor sweeps William Playfair\'s 1786 trade chart; '
        f'behind it the engraving is replaced by a vector chart redrawn from the recovered yearly values.">',
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1020"/>'
        '<stop offset="1" stop-color="#111a2e"/></linearGradient>',
        '<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">'
        '<circle cx="1" cy="1" r="1" fill="#fff" fill-opacity=".05"/></pattern>',
        f'<linearGradient id="trail" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{TEAL}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{TEAL}" stop-opacity=".28"/></linearGradient>',
        '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
        vector_symbol(),
        f'<clipPath id="reveal"><rect x="{CX}" y="{CY}" height="{CH:.1f}" width="0">'
        + anim("width", [(SWEEP[0], x0 * S), (SWEEP[1], x1 * S), (SWEEP[1] + 0.02, CW), (BACK[0], CW), (BACK[1], 0)])
        + "</rect></clipPath>",
        "</defs>",
        f'<rect width="{W}" height="{H}" rx="28" fill="url(#bg)"/><rect width="{W}" height="{H}" rx="28" fill="url(#dots)"/>',
        f'<image x="{CX}" y="{CY}" width="{CW}" height="{CH:.1f}" preserveAspectRatio="none" href="{scan_uri}"/>',
        f'<g clip-path="url(#reveal)"><use href="#chart" x="{CX}" y="{CY}" width="{CW}" height="{CH:.1f}"/></g>',
    ]

    # cursor with a soft trail, and a dot riding each curve
    frames_x = [(year_t(y), f"{(pf.year_x(y) - x0) * S:.2f} 0") for y, _, _ in rows]
    p.append(f'<g opacity="0">'
             + anim("opacity", [(SWEEP[0] - 0.005, 0), (SWEEP[0], 1), (SWEEP[1], 1), (SWEEP[1] + 0.03, 0)])
             + f'<g>{anim("transform", [(0, "0 0")] + frames_x, kind="animateTransform")}'
             f'<rect x="{X(x0) - 60:.1f}" y="{Y(pf.FRAME_INNER[1]):.1f}" width="60" '
             f'height="{(pf.FRAME_INNER[3] - pf.FRAME_INNER[1]) * S:.1f}" fill="url(#trail)"/>'
             f'<rect x="{X(x0) - 1:.1f}" y="{Y(pf.FRAME_INNER[1]) - 8:.1f}" width="2" '
             f'height="{(pf.FRAME_INNER[3] - pf.FRAME_INNER[1]) * S + 16:.1f}" fill="{TEAL}" filter="url(#glow)"/>'
             "</g>")
    for idx, color in ((1, EXP), (2, IMP)):
        cxs = [(year_t(r[0]), f"{X(pf.year_x(r[0])):.2f}") for r in rows]
        cys = [(year_t(r[0]), f"{Y(pf.value_y(r[idx])):.2f}") for r in rows]
        p.append(f'<circle r="5.5" fill="{color}" stroke="#fff" stroke-width="2" filter="url(#glow)">'
                 + anim("cx", cxs) + anim("cy", cys) + "</circle>")
    p.append("</g>")

    # crossing marker once the sweep has passed 1754
    cross_year = next(r[0] for r in rows if r[1] >= r[2])
    prev = next(r for r in rows if r[0] == cross_year - 1)
    cur = next(r for r in rows if r[0] == cross_year)
    t = (prev[2] - prev[1]) / ((prev[2] - prev[1]) - (cur[2] - cur[1]))
    yr, val = prev[0] + t, prev[1] + t * (cur[1] - prev[1])
    mx, my = X(pf.year_x(yr)), Y(pf.value_y(val))
    t0 = year_t(yr)
    p.append(f'<g opacity="0">{anim("opacity", [(t0, 0), (t0 + 0.02, 1), (BACK[0], 1), (BACK[0] + 0.02, 0)])}'
             f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="9" fill="none" stroke="{TEAL}" stroke-width="2">'
             + anim("r", [(t0, 6), (t0 + 0.06, 16), (t0 + 0.12, 9)]) + "</circle>"
             f'<path d="M{mx + 6:.1f},{my + 8:.1f} L{mx + 24:.1f},{my + 62:.1f}" stroke="{TEAL}" stroke-width="1.2"/>'
             f'<rect x="{mx + 4:.1f}" y="{my + 62:.1f}" width="256" height="26" rx="13" fill="#0b1020" fill-opacity=".92" stroke="{TEAL}"/>'
             f'<text x="{mx + 132:.1f}" y="{my + 79.5:.1f}" text-anchor="middle" font-family="{MONO}" font-size="12" fill="#e2e8f0">'
             f'{yr:.1f}: exports overtake imports</text></g>')

    # right-hand panel
    px = CX + CW + 40
    p += [
        f'<text x="{px}" y="78" font-family="{SANS}" font-size="34" font-weight="800" fill="#f8fafc" letter-spacing="-.5">'
        f'Chart <tspan fill="{TEAL}">→</tspan> data <tspan fill="{TEAL}">→</tspan> vector</text>',
        f'<text x="{px}" y="110" font-family="{SANS}" font-size="16" fill="#94a3b8">Playfair’s 1786 engraving, read back</text>',
        f'<text x="{px}" y="132" font-family="{SANS}" font-size="16" fill="#94a3b8">into numbers, then redrawn from them.</text>',
        f'<rect x="{px}" y="164" width="400" height="212" rx="16" fill="#0f172a" stroke="#1e293b" stroke-width="1.5"/>',
        f'<text x="{px + 22}" y="198" font-family="{MONO}" font-size="12" fill="#64748b" letter-spacing="1.5">DATA.CSV · £10,000</text>',
    ]
    labels = [("YEAR", None), ("exports", EXP), ("imports", IMP), ("balance", None)]
    for i, (name, color) in enumerate(labels[1:]):
        y = 278 + i * 34
        dot = f'<circle cx="{px + 30}" cy="{y - 5}" r="5" fill="{color}"/>' if color else ""
        p.append(f'{dot}<text x="{px + 44}" y="{y}" font-family="{MONO}" font-size="16" fill="#94a3b8">{name}</text>')
    for j, (year, e, i) in enumerate(rows):
        a = year_t(year) - 0.0001 if j else 0
        b = year_t(rows[j + 1][0]) if j + 1 < len(rows) else BACK[1]
        frames = [(0, 0), (max(a, 0), 1), (b, 0)] if j else [(0, 1), (b, 0), (BACK[1], 1)]
        if j + 1 == len(rows):
            frames = [(0, 0), (a, 1), (BACK[1], 0)]
        bal = e - i
        tone = "#86efac" if bal >= 0 else "#fda4af"
        p.append(f'<g opacity="{1 if j == 0 else 0}">{anim("opacity", frames, mode="discrete")}'
                 f'<text x="{px + 22}" y="240" font-family="{MONO}" font-size="34" font-weight="700" fill="#f8fafc">{year}</text>'
                 f'<text x="{px + 378}" y="278" text-anchor="end" font-family="{MONO}" font-size="16" fill="#f8fafc">{e:.1f}</text>'
                 f'<text x="{px + 378}" y="312" text-anchor="end" font-family="{MONO}" font-size="16" fill="#f8fafc">{i:.1f}</text>'
                 f'<text x="{px + 378}" y="346" text-anchor="end" font-family="{MONO}" font-size="16" fill="{tone}">{bal:+.1f}</text></g>')
    stats = [("81", "yearly readings per series"), ("0", "raster images in the PDF"),
             ("±1", "unit reading precision")]
    for k, (big, small) in enumerate(stats):
        y = 430 + k * 44
        p.append(f'<text x="{px}" y="{y}" font-family="{MONO}" font-size="24" font-weight="700" fill="{TEAL}">{big}</text>'
                 f'<text x="{px + 60}" y="{y - 1}" font-family="{SANS}" font-size="15" fill="#cbd5e1">{small}</text>')
    p.append(f'<text x="{CX}" y="{H - 14}" font-family="{SANS}" font-size="13" fill="#64748b">'
             "William Playfair, Commercial and Political Atlas (1786) · public-domain scan, redrawn from recovered data</text>")
    p.append("</svg>")
    return "\n".join(p)


def main() -> int:
    svg = build()
    OUT.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT} ({len(svg.encode()) / 1024:.0f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
