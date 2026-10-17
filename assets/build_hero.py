#!/usr/bin/env python3
"""Build assets/hero.svg, the animated README banner.

The banner is generated from the real demo artefacts: the Byrne scan and the
PDF rebuilt from it (demo/byrne-euclid-I-11). The rebuilt page is embedded
with its text converted to outlines so it renders the same on every system;
the downloadable PDF keeps real, searchable text. Animation is SMIL, which
GitHub plays when it shows an SVG through <img>.

    python assets/build_hero.py      # needs PyMuPDF and Pillow
"""

from __future__ import annotations

import base64
import importlib.util
import io
import re
from pathlib import Path

import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo" / "byrne-euclid-I-11"
OUT = ROOT / "assets" / "hero.svg"

spec = importlib.util.spec_from_file_location("byrne", DEMO / "rebuilt" / "build.py")
byrne = importlib.util.module_from_spec(spec)
spec.loader.exec_module(byrne)

W, H, DUR = 1280, 720, 12          # canvas px, loop seconds
PX, PY, PH = 72, 40, 640           # page placement on the canvas
S = PH / byrne.SCAN_H              # scan px -> canvas px
PW = byrne.SCAN_W * S
SWEEP = (0.08, 0.33)               # reveal sweep, as fractions of the loop
HIDE = (0.93, 0.99)                # sweep back to the scan before looping
ZOOM = (850, 1524, 200, 104)       # inset region in scan px (x, y, w, h): "perpendic…"
INSET = (640, 372, 560, 290)       # inset box on the canvas
SANS = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
TEAL, AMBER, PINK = "#2dd4bf", "#fbbf24", "#f472b6"


def cx(x):
    return PX + x * S


def cy(y):
    return PY + y * S


def anim(attr, frames, ease=True, kind="animate"):
    """SMIL animation over the shared loop; frames = [(t, value), ...] with t in 0..1."""
    frames = sorted(frames)
    if frames[0][0] > 0:
        frames.insert(0, (0, frames[0][1]))
    if frames[-1][0] < 1:
        frames.append((1, frames[-1][1]))
    times = ";".join(f"{t:.4f}".rstrip("0").rstrip(".") or "0" for t, _ in frames)
    values = ";".join(str(v) for _, v in frames)
    spline = ""
    if ease:
        spline = (' calcMode="spline" keySplines="'
                  + ";".join(["0.45 0 0.25 1"] * (len(frames) - 1)) + '"')
    extra = ' type="translate"' if kind == "animateTransform" else ""
    return (f'<{kind} attributeName="{attr}"{extra} dur="{DUR}s" repeatCount="indefinite" '
            f'keyTimes="{times}" values="{values}"{spline}/>')


def sweep_time(y_canvas):
    return SWEEP[0] + (SWEEP[1] - SWEEP[0]) * (y_canvas - PY) / PH


def data_uri(img: Image.Image, fmt: str, **save) -> str:
    buf = io.BytesIO()
    img.save(buf, fmt, **save)
    mime = "jpeg" if fmt == "JPEG" else fmt.lower()
    return f"data:image/{mime};base64," + base64.b64encode(buf.getvalue()).decode()


def vector_page_symbol() -> str:
    pdf = DEMO / "rebuilt" / "byrne-euclid-I-11.pdf"
    with pymupdf.open(pdf) as doc:
        page = doc[0]
        svg = page.get_svg_image(text_as_path=True)
        vb = f"0 0 {page.rect.width:g} {page.rect.height:g}"
    inner = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")]
    inner = re.sub(r'\bid="([^"]+)"', r'id="v-\1"', inner)
    inner = re.sub(r'href="#([^"]+)"', r'href="#v-\1"', inner)
    return (f'<symbol id="vpage" viewBox="{vb}" preserveAspectRatio="none">'
            f'<rect width="100%" height="100%" fill="#fff"/>{inner}</symbol>')


def text_boxes():
    """One detection box per text line of the rebuilt page (scan px)."""
    fonts = {k: pymupdf.Font(fontfile=str(p)) for k, p in byrne.FACES.items()}
    lines = {}
    for style, y, words in byrne.TEXT:
        face, size = byrne.STYLES[style]
        x0 = min(x for x, _ in words)
        x1 = max(x + fonts[face].text_length(w, fontsize=size) for x, w in words)
        top, bottom = y - 0.8 * size, y + 0.25 * size
        key = round(y / 12)
        if key in lines:
            a = lines[key]
            lines[key] = (min(a[0], x0), min(a[1], top), max(a[2], x1), max(a[3], bottom))
        else:
            lines[key] = (x0, top, x1, bottom)
    # widen lines that carry inline symbols
    boxes = []
    for x0, top, x1, bottom in lines.values():
        for pieces in byrne.BARS:
            for bx0, bx1, by, _ in pieces:
                if top - 10 <= by <= bottom + 10:
                    x0, x1 = min(x0, bx0), max(x1, bx1)
        boxes.append((x0, top, x1, bottom))
    return sorted(boxes, key=lambda b: b[1])


def word_box(style, x, y, word):
    face, size = byrne.STYLES[style]
    font = pymupdf.Font(fontfile=str(byrne.FACES[face]))
    return (x - 4, y - 0.82 * size, x + font.text_length(word, fontsize=size) + 4, y + 0.3 * size)


def flash_box(box, color, label=None, hold=0.06):
    x0, y0, x1, y1 = box
    t = sweep_time(cy(y0))
    a, b = max(t - 0.004, 0.0001), t + 0.012
    frames = [(0, 0), (a, 0), (b, 1), (b + hold, 0.9), (b + hold + 0.05, 0)]
    out = [f'<g opacity="0">{anim("opacity", frames)}',
           f'<rect x="{cx(x0) - 3:.1f}" y="{cy(y0) - 2:.1f}" width="{(x1 - x0) * S + 6:.1f}" '
           f'height="{(y1 - y0) * S + 4:.1f}" rx="2" fill="{color}" fill-opacity=".08" '
           f'stroke="{color}" stroke-width="1.1" stroke-dasharray="4 2.5"/>']
    if label:
        out.append(f'<text x="{cx(x0) - 2:.1f}" y="{cy(y0) - 6:.1f}" font-family="{MONO}" '
                   f'font-size="10" fill="{color}" letter-spacing=".5">{label}</text>')
    out.append("</g>")
    return "".join(out)


def build() -> str:
    scan = Image.open(DEMO / "source" / "scan.jpg").convert("RGB")
    scan_uri = data_uri(scan.resize((int(PW * 2), int(PH * 2)), Image.LANCZOS), "JPEG", quality=72)
    zx, zy, zw, zh = ZOOM
    crop_uri = data_uri(scan.crop((zx, zy, zx + zw, zy + zh)), "PNG", optimize=True)
    ix, iy, iw, ih = INSET
    zs = iw / zw

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
        f'aria-label="A scanned page of Byrne\'s 1847 Euclid is swept by a scanning beam and '
        f'replaced by a clean vector rebuild; a zoomed split view compares JPEG pixels with vector paths.">',
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0b1020"/>'
        '<stop offset="1" stop-color="#111a2e"/></linearGradient>',
        f'<radialGradient id="halo" cx=".25" cy=".5" r=".55"><stop offset="0" stop-color="{TEAL}" '
        'stop-opacity=".16"/><stop offset="1" stop-color="#0b1020" stop-opacity="0"/></radialGradient>',
        '<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">'
        '<circle cx="1" cy="1" r="1" fill="#fff" fill-opacity=".05"/></pattern>',
        f'<linearGradient id="beam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{TEAL}" '
        f'stop-opacity="0"/><stop offset=".85" stop-color="{TEAL}" stop-opacity=".35"/>'
        f'<stop offset="1" stop-color="#e0fffb" stop-opacity=".95"/></linearGradient>',
        '<linearGradient id="title" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f8fafc"/>'
        f'<stop offset="1" stop-color="{TEAL}"/></linearGradient>',
        '<filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="2.4" '
        'result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
        '<filter id="shadow" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="14"/></filter>',
        vector_page_symbol(),
        f'<clipPath id="reveal"><rect x="{PX}" y="{PY}" width="{PW:.2f}" height="0">'
        + anim("y", [(0, PY), (HIDE[0], PY), (HIDE[1], PY + PH)])
        + anim("height", [(0, 0), (SWEEP[0], 0), (SWEEP[1], PH), (HIDE[0], PH), (HIDE[1], 0)])
        + "</rect></clipPath>",
        f'<clipPath id="inset"><rect x="{ix}" y="{iy}" width="{iw}" height="{ih}" rx="10"/></clipPath>',
        f'<clipPath id="inset-scan"><rect x="{ix}" y="{iy}" width="{iw / 2}" height="{ih}">'
        + anim("width", [(0.40, iw / 2), (0.47, iw / 2), (0.56, iw * 0.88), (0.68, iw * 0.1),
                         (0.78, iw / 2)])
        + "</rect></clipPath>",
        "</defs>",
        f'<rect width="{W}" height="{H}" rx="28" fill="url(#bg)"/>',
        f'<rect width="{W}" height="{H}" rx="28" fill="url(#halo)"/>',
        f'<rect width="{W}" height="{H}" rx="28" fill="url(#dots)"/>',
        # page, shadow, scan underneath, vector revealed on top
        f'<rect x="{PX + 6}" y="{PY + 14}" width="{PW:.2f}" height="{PH}" fill="#000" opacity=".55" filter="url(#shadow)"/>',
        f'<image x="{PX}" y="{PY}" width="{PW:.2f}" height="{PH}" preserveAspectRatio="none" href="{scan_uri}"/>',
        f'<g clip-path="url(#reveal)"><use href="#vpage" x="{PX}" y="{PY}" width="{PW:.2f}" height="{PH}"/></g>',
    ]

    # detection boxes flash as the beam passes
    for box in text_boxes():
        parts.append(flash_box(box, TEAL))
    parts.append(flash_box((571, 335, 1713, 1060), PINK, "VECTOR · figure", hold=0.12))
    parts.append(flash_box((64, 460, 290, 712), AMBER, "RASTER · engraving", hold=0.1))
    parts.append(flash_box((590, 1312, 802, 1503), PINK, hold=0.08))
    parts.append(flash_box((553, 2130, 884, 2246), PINK, hold=0.06))

    # wireframe of the main figure, drawn as the beam crosses it
    (lx, ly), (ax, ay), (rx, ry) = byrne.LEFT, byrne.APEX, byrne.RIGHT
    fx, fy = byrne.FOOT
    r = byrne.ANGLE_R
    wire = [
        f"M{cx(lx):.1f},{cy(ly):.1f} L{cx(ax):.1f},{cy(ay):.1f} L{cx(rx):.1f},{cy(ry):.1f} Z",
        f"M{cx(fx):.1f},{cy(376):.1f} V{cy(fy):.1f}",
        f"M{cx(fx - r):.1f},{cy(fy):.1f} A{r * S:.1f},{r * S:.1f} 0 0 1 {cx(fx + r):.1f},{cy(fy):.1f}",
        f"M{cx(571):.1f},{cy(fy):.1f} H{cx(1713):.1f}",
    ]
    t0 = sweep_time(cy(ay)) - 0.01
    parts.append(f'<g fill="none" stroke="{TEAL}" stroke-width="1.6" stroke-linecap="round" filter="url(#glow)" opacity="0">'
                 + anim("opacity", [(t0, 0), (t0 + 0.01, 1), (0.36, 1), (0.42, 0)]))
    for i, d in enumerate(wire):
        start = t0 + 0.012 * i
        parts.append(f'<path d="{d}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1">'
                     + anim("stroke-dashoffset", [(start, 1), (start + 0.08, 0), (0.95, 0), (0.96, 1)])
                     + "</path>")
    for x, y in (byrne.LEFT, byrne.APEX, byrne.RIGHT, byrne.FOOT):
        parts.append(f'<circle cx="{cx(x):.1f}" cy="{cy(y):.1f}" r="3.2" fill="{TEAL}"/>')
    parts.append("</g>")

    # the beam itself
    parts.append(f'<g opacity="0">'
                 + anim("opacity", [(SWEEP[0] - 0.01, 0), (SWEEP[0], 1), (SWEEP[1], 1), (SWEEP[1] + 0.01, 0),
                                    (HIDE[0] - 0.005, 0), (HIDE[0], 1), (HIDE[1], 1), (HIDE[1] + 0.005, 0)])
                 + f'<g>{anim("transform", [(0, "0 0"), (SWEEP[0], "0 0"), (SWEEP[1], f"0 {PH}"), (HIDE[0], "0 0"), (HIDE[1], f"0 {PH}")], kind="animateTransform")}'
                 f'<rect x="{PX - 10}" y="{PY - 70}" width="{PW + 20:.1f}" height="70" fill="url(#beam)"/>'
                 f'<rect x="{PX - 14}" y="{PY - 1.5}" width="{PW + 28:.1f}" height="3" rx="1.5" fill="#e0fffb" filter="url(#glow)"/>'
                 "</g></g>")

    # status chips on the page
    def chip(x, y, text, color, frames):
        w = 32 + 7.3 * len(text)
        return (f'<g opacity="0">{anim("opacity", frames, ease=False)}'
                f'<rect x="{x}" y="{y}" width="{w:.0f}" height="24" rx="12" fill="#0b1020" fill-opacity=".86" '
                f'stroke="{color}" stroke-opacity=".7"/><circle cx="{x + 12}" cy="{y + 12}" r="3.5" fill="{color}"/>'
                f'<text x="{x + 22}" y="{y + 16.5}" font-family="{MONO}" font-size="12" fill="#e2e8f0">{text}</text></g>')
    parts.append(chip(PX + 10, PY + PH - 36, "SCAN · JPEG 1920×2519", AMBER,
                      [(0, 1), (0.30, 1), (0.31, 0), (0.97, 0), (0.98, 1)]))
    parts.append(chip(PX + 10, PY + PH - 36, "PDF · text + vector paths", TEAL,
                      [(0, 0), (0.33, 0), (0.34, 1), (0.92, 1), (0.93, 0)]))

    # right-hand panel: title and the three steps
    parts += [
        f'<text x="640" y="112" font-family="{SANS}" font-size="54" font-weight="800" fill="url(#title)" '
        f'letter-spacing="-1">scan-to-vector</text>',
        f'<text x="642" y="152" font-family="{SANS}" font-size="21" fill="#cbd5e1">Scanned pages in. Searchable, vector PDFs out.</text>',
        f'<text x="642" y="180" font-family="{SANS}" font-size="16" fill="#64748b">An agent skill for Claude Code, Codex and other coding agents</text>',
    ]
    steps = [("Read", "OCR, reconciled word by word with the scan"),
             ("Redraw", "diagrams and charts become vector paths"),
             ("Verify", "overlay, structural audit, every page")]
    for i, (verb, rest) in enumerate(steps):
        y = 228 + i * 42
        on = 0.17 + 0.09 * i
        parts.append(
            f'<g><circle cx="656" cy="{y}" r="13" fill="#1e293b" stroke="#334155">'
            + anim("fill", [(on - 0.01, "#1e293b"), (on, TEAL), (0.95, TEAL), (0.96, "#1e293b")], ease=False)
            + f'</circle><text x="656" y="{y + 5}" text-anchor="middle" font-family="{SANS}" font-size="13" '
            f'font-weight="700" fill="#94a3b8">{i + 1}'
            + anim("fill", [(on - 0.01, "#94a3b8"), (on, "#0b1020"), (0.95, "#0b1020"), (0.96, "#94a3b8")], ease=False)
            + f'</text><text x="682" y="{y + 6}" font-family="{SANS}" font-size="17" fill="#64748b">'
            f'<tspan font-weight="700">{verb}</tspan>  {rest}'
            + anim("fill", [(on - 0.01, "#64748b"), (on, "#e2e8f0"), (0.95, "#e2e8f0"), (0.96, "#64748b")], ease=False)
            + "</text></g>")

    # zoom callout: lens on the page, connector, split inset
    lx0, ly0, lw, lh = cx(zx), cy(zy), zw * S, zh * S
    appear = [(0.38, 0), (0.43, 1), (0.93, 1), (0.97, 0)]
    parts.append(f'<g opacity="0">{anim("opacity", appear)}'
                 f'<rect x="{lx0:.1f}" y="{ly0:.1f}" width="{lw:.1f}" height="{lh:.1f}" fill="none" stroke="{TEAL}" '
                 f'stroke-width="1.6" filter="url(#glow)"/>'
                 f'<path d="M{lx0 + lw:.1f},{ly0:.1f} L{ix},{iy} M{lx0 + lw:.1f},{ly0 + lh:.1f} L{ix},{iy + ih}" '
                 f'stroke="{TEAL}" stroke-opacity=".45" stroke-width="1" stroke-dasharray="3 4" fill="none"/></g>')
    parts.append(
        f'<g opacity="0">{anim("opacity", appear)}'
        f'<rect x="{ix - 1}" y="{iy - 1}" width="{iw + 2}" height="{ih + 2}" rx="11" fill="#fff" stroke="#334155" stroke-width="2"/>'
        f'<g clip-path="url(#inset)">'
        f'<use href="#vpage" x="{ix - zx * zs:.1f}" y="{iy - zy * zs:.1f}" width="{byrne.SCAN_W * zs:.1f}" '
        f'height="{byrne.SCAN_H * zs:.1f}"/>'
        f'<g clip-path="url(#inset-scan)"><image x="{ix}" y="{iy}" width="{iw}" height="{ih}" '
        f'preserveAspectRatio="none" image-rendering="pixelated" style="image-rendering:pixelated" href="{crop_uri}"/></g>'
        f'<g>{anim("transform", [(0.40, "0 0"), (0.47, "0 0"), (0.56, f"{iw * 0.38:.1f} 0"), (0.68, f"{-iw * 0.4:.1f} 0"), (0.78, "0 0")], kind="animateTransform")}'
        f'<rect x="{ix + iw / 2 - 1.5}" y="{iy}" width="3" height="{ih}" fill="#fff"/>'
        f'<circle cx="{ix + iw / 2}" cy="{iy + ih / 2}" r="15" fill="#0b1020" stroke="#fff" stroke-width="2"/>'
        f'<path d="M{ix + iw / 2 - 5},{iy + ih / 2 - 5} l-5,5 5,5 M{ix + iw / 2 + 5},{iy + ih / 2 - 5} l5,5 -5,5" '
        f'stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></g>'
        "</g>"
        f'<text x="{ix + 12}" y="{iy + 24}" font-family="{MONO}" font-size="12" fill="#0b1020" font-weight="700">'
        f'<tspan fill="#b45309">●</tspan> SCAN</text>'
        f'<text x="{ix + iw - 12}" y="{iy + 24}" text-anchor="end" font-family="{MONO}" font-size="12" '
        f'fill="#0b1020" font-weight="700">VECTOR <tspan fill="#0d9488">●</tspan></text>'
        f'<text x="{ix}" y="{iy + ih + 26}" font-family="{SANS}" font-size="14" fill="#64748b">'
        f'{zs:.1f}× zoom on the same region: JPEG pixels vs. paths that stay sharp at any size</text>'
        "</g>")

    # searchable text: highlight both matches of "perpendicular"
    search = [(0.0, 0), (0.80, 0), (0.82, 1), (0.92, 1), (0.94, 0)]
    hits = [word_box("i", 102, 840, "perpendicular."), word_box("r", 853, 1577, "perpendicular")]
    parts.append(f'<g opacity="0">{anim("opacity", search)}')
    for x0, y0, x1, y1 in hits:
        parts.append(f'<rect x="{cx(x0):.1f}" y="{cy(y0):.1f}" width="{(x1 - x0) * S:.1f}" height="{(y1 - y0) * S:.1f}" '
                     f'rx="2" fill="{AMBER}" fill-opacity=".45" stroke="{AMBER}" stroke-width="1.2">'
                     + anim("fill-opacity", [(0.82, 0.15), (0.85, 0.55), (0.88, 0.25), (0.91, 0.55)])
                     + "</rect>")
    sx, sy = cx(1240), cy(1720)  # empty margin right of the construction text
    parts.append(f'<rect x="{sx:.1f}" y="{sy:.1f}" width="172" height="48" rx="9" fill="#0b1020" fill-opacity=".94" stroke="{AMBER}"/>'
                 f'<text x="{sx + 12:.1f}" y="{sy + 20:.1f}" font-family="{MONO}" font-size="13" fill="#e2e8f0">'
                 f'<tspan fill="{AMBER}">⌘F</tspan> perpendicular</text>'
                 f'<text x="{sx + 12:.1f}" y="{sy + 38:.1f}" font-family="{MONO}" font-size="11" fill="#94a3b8">2 matches · real text</text></g>')

    parts.append(f'<text x="{PX}" y="{H - 16}" font-family="{SANS}" font-size="13" fill="#64748b">'
                 "Byrne’s Euclid (1847), Book I, Prop. XI · public-domain scan, rebuilt with this skill</text>")
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    svg = build()
    OUT.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT} ({len(svg.encode()) / 1024:.0f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
