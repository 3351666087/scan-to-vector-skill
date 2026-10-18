#!/usr/bin/env python3
"""Generate benchmark pages: a clean ground-truth PDF and a simulated scan.

Each page is drawn with PyMuPDF from a seeded template (worksheet, table,
chart, flowchart, form, two-column article), so its text, figure regions and
chart data are known exactly. The page is rendered at 200 dpi and degraded
like a real scan: slight skew, paper tint, uneven light, blur, noise, JPEG.

    python bench/generate.py --out work/bench --split dev --count 6 --seed 100

Writes <out>/<split>/<id>/{scan.jpg, truth.pdf, truth.json}.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import random
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter

DPI = 200
PAGE_W, PAGE_H = 612, 792            # US Letter, points
PX = DPI / 72
FONTS = Path(__file__).resolve().parent.parent / "demo" / "fonts"
KINDS = ("worksheet", "table", "chart", "flowchart", "form", "article")

SENTENCES = [
    "Read each question carefully before you write your answer.",
    "Show all of your working in the space provided below each question.",
    "The survey was carried out in three districts during the spring term.",
    "Values marked with an asterisk are estimates based on partial returns.",
    "Store the samples in a cool, dry place away from direct sunlight.",
    "Each team recorded its results twice and reported the average value.",
    "Costs rose sharply in the second quarter as fuel prices increased.",
    "The new schedule reduces waiting times at the north entrance.",
    "Check that the power switch is off before opening the cover.",
    "Return the completed form to the front office by Friday afternoon.",
    "Measurements were taken at the same time each morning for two weeks.",
    "The committee approved the proposal after a short discussion.",
    "Plants grown near the window reached the greatest average height.",
    "A second inspection is required if any seal shows signs of damage.",
    "Visitors must sign in at reception and wear a badge at all times.",
    "The bridge was closed for repairs between March and early June.",
    "Demand for evening classes has grown steadily over five years.",
    "Use a sharp pencil and a ruler when drawing the diagram.",
    "Both methods gave similar results within the expected margin of error.",
    "The library extends its opening hours during the examination period.",
    "Rainfall in the valley was well below the long-term average.",
    "Wear gloves and safety glasses when handling the cleaning solution.",
    "Sales of the compact model doubled after the price was reduced.",
    "The water level is checked daily and recorded in the site log.",
    "Students who finish early may attempt the challenge question.",
    "Attach receipts for any expense larger than fifty dollars.",
    "The pump should run for ten minutes before readings are taken.",
    "Most respondents preferred the morning timetable to the evening one.",
    "Label every container clearly with its contents and the date.",
    "The final report will be published at the end of the month.",
]
ITEMS = ["Paper", "Glass", "Metal", "Plastic", "Textile", "Timber", "Organic", "Electronics",
         "North", "South", "East", "West", "Central", "Harbour", "Airport", "Valley"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PALETTE = [(0.20, 0.38, 0.62), (0.85, 0.42, 0.18), (0.22, 0.58, 0.34), (0.62, 0.24, 0.48)]


SYS = Path("/System/Library/Fonts/Supplemental")
FAMILIES = {  # (regular, bold, italic): base-14 names or font files
    "times": ("tiro", "tibo", "tiit"),
    "helvetica": ("helv", "hebo", "heit"),
    "caslon": (FONTS / "LibreCaslonText.ttf", "tibo", FONTS / "LibreCaslonText-Italic.ttf"),
    "georgia": (SYS / "Georgia.ttf", SYS / "Georgia Bold.ttf", SYS / "Georgia Italic.ttf"),
    "verdana": (SYS / "Verdana.ttf", SYS / "Verdana Bold.ttf", SYS / "Verdana Italic.ttf"),
    "trebuchet": (SYS / "Trebuchet MS.ttf", SYS / "Trebuchet MS Bold.ttf", SYS / "Trebuchet MS Italic.ttf"),
    "arial-narrow": (SYS / "Arial Narrow.ttf", SYS / "Arial Narrow Bold.ttf", SYS / "Arial Narrow Italic.ttf"),
}
HARD_FAMILIES = ["georgia", "verdana", "trebuchet", "arial-narrow", "caslon", "times"]


class Page:
    """Thin drawing layer that also records figure regions (in points)."""

    def __init__(self, rng: random.Random, hard: bool = False):
        self.rng = rng
        self.hard = hard
        self.doc = pymupdf.open()
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        self.figures: list[dict] = []
        pool = [f for f in HARD_FAMILIES if all(isinstance(x, str) or Path(x).exists() for x in FAMILIES[f])]
        self.family = rng.choice(pool) if hard else rng.choice(["times", "helvetica"])
        self.font_objs = {}
        names = []
        for i, src in enumerate(FAMILIES[self.family]):
            if isinstance(src, str):
                names.append(src)
            else:
                name = f"F{i}"
                self.page.insert_font(fontname=name, fontfile=str(src))
                self.font_objs[name] = pymupdf.Font(fontfile=str(src))
                names.append(name)
        self.body, self.bold, self.italic = names

    def font(self, name):
        if name not in self.font_objs:
            self.font_objs[name] = pymupdf.Font(name)
        return self.font_objs[name]

    def width(self, s, size, font=None):
        return self.font(font or self.body).text_length(s, fontsize=size)

    def text(self, x, y, s, size=10.5, font=None, color=(0, 0, 0)):
        self.page.insert_text((x, y), s, fontname=font or self.body, fontsize=size, color=color)
        return x + self.width(s, size, font)

    def ctext(self, cx, y, s, size=10.5, font=None, color=(0, 0, 0)):
        self.text(cx - self.width(s, size, font) / 2, y, s, size, font, color)

    def wrap(self, x, y, width, s, size=10.5, leading=1.35, font=None):
        words, line = s.split(), ""
        for w in words:
            trial = (line + " " + w).strip()
            if self.width(trial, size, font) > width and line:
                self.text(x, y, line, size, font)
                y += size * leading
                line = w
            else:
                line = trial
        if line:
            self.text(x, y, line, size, font)
            y += size * leading
        return y

    def shape(self):
        return self.page.new_shape()

    def figure(self, kind, rect):
        self.figures.append({"kind": kind, "bbox_pt": [round(v, 2) for v in rect]})

    def paragraph(self, x, y, width, n, size=10.5):
        text = " ".join(self.rng.sample(SENTENCES, n))
        return self.wrap(x, y, width, text, size)

    def header(self, title, sub=None):
        y = 72
        self.text(54, y, title, 17, self.bold)
        if sub:
            y += 18
            self.text(54, y, sub, 10.5, self.italic)
        s = self.shape()
        s.draw_line((54, y + 8), (PAGE_W - 54, y + 8))
        s.finish(width=0.8, color=(0, 0, 0))
        s.commit()
        return y + 30

    def footer(self, n):
        self.ctext(PAGE_W / 2, PAGE_H - 36, f"Page {n}", 9)


def arrow(s, a, b, head=6):
    s.draw_line(a, b)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for d in (-0.45, 0.45):
        s.draw_line(b, (b[0] - head * math.cos(ang + d), b[1] - head * math.sin(ang + d)))


# ---------------------------------------------------------------- templates

def worksheet(p: Page, n):
    r = p.rng
    topic = r.choice(["Linear Equations", "Fractions", "Area and Perimeter", "Angles", "Ratios"])
    y = p.header(f"Worksheet {r.randint(1, 12)}: {topic}", "Mathematics, Year 8")
    s = p.shape()
    for label, x0, x1 in (("Name:", 54, 330), ("Date:", 360, 558)):
        end = p.text(x0, y, label, 10.5)
        s.draw_line((end + 6, y + 2), (x1, y + 2))
    s.finish(width=0.6, color=(0, 0, 0))
    s.commit()
    y = p.wrap(54, y + 28, 504, p.rng.choice(SENTENCES[:2]) + " Calculators are not allowed.")
    y += 10
    q = 1
    for _ in range(r.randint(3, 4)):
        a, b, c = r.randint(2, 9), r.randint(1, 20), r.randint(21, 60)
        p.text(54, y, f"{q}.", 10.5, p.bold)
        p.text(74, y, f"Solve for x: {a}x + {b} = {c}", 10.5)
        s = p.shape()
        s.draw_line((330, y + 2), (480, y + 2))
        s.finish(width=0.6, color=(0, 0, 0))
        s.commit()
        p.text(486, y, "[2 marks]", 9, p.italic)
        y += 34
        q += 1
    # multiple choice with bubbles
    p.text(54, y, f"{q}.", 10.5, p.bold)
    v = r.randint(12, 60)
    y = p.wrap(74, y, 480, f"Which number is closest to the square root of {v * v + r.randint(1, 9)}?")
    opts = [v - 2, v - 1, v, v + 1]
    r.shuffle(opts)
    s = p.shape()
    x = 80
    for letter, o in zip("ABCD", opts):
        s.draw_circle((x, y + 2), 6)
        p.text(x + 12, y + 6, f"({letter}) {o}", 10.5)
        x += 110
    s.finish(width=0.7, color=(0, 0, 0))
    s.commit()
    y += 36
    q += 1
    # right triangle figure
    p.text(54, y, f"{q}.", 10.5, p.bold)
    a, b = r.choice([(3, 4), (6, 8), (5, 12), (9, 12), (8, 15)])
    y = p.wrap(74, y, 300, f"The right triangle has legs of {a} cm and {b} cm. Find the hypotenuse h.")
    ox, oy = 110, y + 150
    w, h = 170, 170 * a / b + 30
    s = p.shape()
    s.draw_polyline([(ox, oy), (ox + w, oy), (ox, oy - h), (ox, oy)])
    s.finish(width=1.4, color=(0, 0, 0), closePath=True)
    s.draw_polyline([(ox + 12, oy), (ox + 12, oy - 12), (ox, oy - 12)])
    s.finish(width=0.8, color=(0, 0, 0), closePath=False)
    s.commit()
    p.ctext(ox + w / 2, oy + 16, f"{b} cm", 10)
    p.text(ox - 40, oy - h / 2, f"{a} cm", 10)
    p.text(ox + w / 2 + 8, oy - h / 2 - 6, "h", 11, p.italic)
    p.figure("diagram", (ox - 44, oy - h - 6, ox + w + 6, oy + 20))
    s = p.shape()
    for i in range(4):
        s.draw_line((330, oy - 120 + i * 32), (558, oy - 120 + i * 32))
    s.finish(width=0.5, color=(0.35, 0.35, 0.35))
    s.commit()
    p.text(330, oy - 132, "Working:", 9.5, p.italic)
    p.footer(n)


def table(p: Page, n):
    r = p.rng
    year = r.randint(2009, 2024)
    y = p.header(f"Annual Recycling Report {year}", "Prepared by the Environmental Services Unit")
    y = p.paragraph(54, y, 504, 3)
    y += 12
    cols = ["Material", "Collected (t)", "Recycled (t)", "Rate (%)", "Change"][: r.randint(4, 5)]
    rows = r.sample(ITEMS[:8], r.randint(6, 8))
    if p.hard:
        cols = ["Site", "Collected (t)", "Recycled (t)", "Rate (%)", "Target (%)", "Change"]
        rows = r.sample(ITEMS, r.randint(10, 14))
    widths = [150] + [(504 - 150) / (len(cols) - 1)] * (len(cols) - 1)
    rh = 22 if not p.hard else 17
    fs = 10 if not p.hard else 8.5
    x0, top = 54, y
    full_grid = r.random() < 0.5
    s = p.shape()
    s.draw_rect((x0, top, x0 + 504, top + rh))
    s.finish(width=0, fill=(0.88, 0.88, 0.88), color=None)
    s.commit()
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    for i, c in enumerate(cols):
        p.text(xs[i] + 6, top + rh - 6, c, fs, p.bold)
    data = []
    for j, name in enumerate(rows):
        yy = top + rh * (j + 1)
        coll = r.randint(120, 4800)
        rec = int(coll * r.uniform(0.35, 0.92))
        rate = 100 * rec / coll
        ch = r.uniform(-8, 12)
        vals = [name, f"{coll:,}", f"{rec:,}", f"{rate:.1f}", f"{ch:+.1f}"][: len(cols)]
        if p.hard:
            vals = [name, f"{coll:,}", f"{rec:,}", f"{rate:.1f}", f"{r.choice([50, 55, 60, 65, 70, 75])}", f"{ch:+.1f}"]
            if j % 2 == 1:
                zs = p.shape()
                zs.draw_rect((x0, yy, x0 + 504, yy + rh))
                zs.finish(width=0, fill=(0.94, 0.94, 0.94), color=None)
                zs.commit()
        data.append(vals)
        for i, v in enumerate(vals):
            if i == 0:
                p.text(xs[i] + 6, yy + rh - 6, v, fs)
            else:
                p.text(xs[i + 1] - 8 - p.width(v, fs), yy + rh - 6, v, fs)
    bottom = top + rh * (len(rows) + 1)
    s = p.shape()
    if full_grid:
        for k in range(len(rows) + 2):
            s.draw_line((x0, top + rh * k), (x0 + 504, top + rh * k))
        for x in xs:
            s.draw_line((x, top), (x, bottom))
        s.finish(width=0.7, color=(0, 0, 0))
    else:
        for yy, wdt in ((top, 1.2), (top + rh, 0.7), (bottom, 1.2)):
            s.draw_line((x0, yy), (x0 + 504, yy))
            s.finish(width=wdt, color=(0, 0, 0))
    s.commit()
    p.figure("table", (x0 - 2, top - 2, x0 + 506, bottom + 2))
    y = bottom + 18
    p.text(54, y, f"Table {r.randint(1, 6)}. Material collected and recycled, {year}.", 9.5, p.italic)
    y = p.paragraph(54, y + 28, 504, 4)
    p.text(54, PAGE_H - 60, "* Change is measured against the previous year.", 8.5)
    p.footer(n)
    return {"table": {"columns": cols, "rows": data}}


def chart(p: Page, n):
    r = p.rng
    y = p.header(f"Monthly Visitors to {r.choice(ITEMS[8:])} Centre", "Figures in thousands")
    y = p.paragraph(54, y, 504, 2)
    y += 16
    kind = r.choice(["bar", "line"])
    k = r.randint(6, 9) if not p.hard else (12 if kind == "line" else r.randint(8, 10))
    labels = MONTHS[:k]
    series = 1 if kind == "bar" and r.random() < 0.5 else 2
    if p.hard and kind == "line":
        series = r.randint(2, 3)
    names = r.sample(["Adults", "Children", "Groups", "Online"], series)
    vmax = r.choice([40, 50, 60, 80, 100])
    data = [[round(r.uniform(0.15, 0.95) * vmax, 1) for _ in labels] for _ in names]
    cx0, cy0, cw, ch = 96, y + 10, 440, 260
    s = p.shape()
    ticks = 5
    for t in range(ticks + 1):
        yy = cy0 + ch - ch * t / ticks
        s.draw_line((cx0, yy), (cx0 + cw, yy))
        s.finish(width=0.4 if t else 1.0, color=(0.6, 0.6, 0.6) if t else (0, 0, 0))
        lab = str(int(vmax * t / ticks))
        p.text(cx0 - 8 - p.width(lab, 9), yy + 3, lab, 9)
    s.draw_line((cx0, cy0), (cx0, cy0 + ch))
    s.finish(width=1.0, color=(0, 0, 0))
    step = cw / len(labels)
    for i, lab in enumerate(labels):
        p.ctext(cx0 + step * (i + 0.5), cy0 + ch + 14, lab, 9)
    if kind == "bar":
        bw = step * 0.7 / series
        for si, vals in enumerate(data):
            for i, v in enumerate(vals):
                x = cx0 + step * i + step * 0.15 + bw * si
                s.draw_rect((x, cy0 + ch - ch * v / vmax, x + bw, cy0 + ch))
                s.finish(fill=PALETTE[si], color=None, width=0)
    else:
        for si, vals in enumerate(data):
            pts = [(cx0 + step * (i + 0.5), cy0 + ch - ch * v / vmax) for i, v in enumerate(vals)]
            s.draw_polyline(pts)
            s.finish(width=1.8, color=PALETTE[si], closePath=False)
            for pt in pts:
                s.draw_circle(pt, 3)
                s.finish(fill=PALETTE[si], color=(1, 1, 1), width=0.6)
    s.commit()
    p.text(cx0 - 52, cy0 - 10, "Visitors (000s)", 9, p.italic)
    lx = cx0 + cw - 110
    s = p.shape()
    for si, name in enumerate(names):
        s.draw_rect((lx, cy0 + 6 + si * 16, lx + 10, cy0 + 16 + si * 16))
        s.finish(fill=PALETTE[si], color=None, width=0)
        p.text(lx + 16, cy0 + 15 + si * 16, name, 9)
    s.commit()
    p.figure("chart", (cx0 - 56, cy0 - 22, cx0 + cw + 4, cy0 + ch + 20))
    y = cy0 + ch + 40
    p.text(54, y, f"Figure {r.randint(1, 5)}. Visitors per month, {r.randint(2015, 2024)}.", 9.5, p.italic)
    p.paragraph(54, y + 26, 504, 3)
    p.footer(n)
    return {"chart": {"kind": kind, "labels": labels, "series": dict(zip(names, data)), "y_max": vmax}}


def flowchart(p: Page, n):
    r = p.rng
    y = p.header(f"Procedure {r.randint(1, 9)}.{r.randint(1, 9)}: {r.choice(['Filter Replacement', 'Pump Start-up', 'Sample Handling', 'Fault Reset'])}")
    steps = r.sample(SENTENCES[3:], 4)
    for i, st in enumerate(steps, 1):
        p.text(54, y, f"{i}.", 10.5, p.bold)
        y = p.wrap(72, y, 486, st)
        y += 4
    y += 6
    s = p.shape()
    s.draw_rect((54, y, 558, y + 40))
    s.finish(width=1.2, color=(0.7, 0.1, 0.1), fill=(1, 0.95, 0.93))
    s.commit()
    p.text(64, y + 16, "CAUTION:", 10, p.bold, color=(0.7, 0.1, 0.1))
    p.wrap(128, y + 16, 420, r.choice([SENTENCES[8], SENTENCES[21], SENTENCES[13]]), 10)
    y += 64
    cx = PAGE_W / 2
    boxes = r.sample(["Isolate power", "Remove cover", "Inspect seal", "Fit new filter", "Run pump", "Record reading"], 3)
    s = p.shape()
    top = y
    s.draw_oval((cx - 50, y, cx + 50, y + 26))
    p.ctext(cx, y + 17, "Start", 10)
    y += 26
    for label in boxes[:2]:
        arrow(s, (cx, y), (cx, y + 22))
        y += 22
        s.draw_rect((cx - 80, y, cx + 80, y + 30))
        p.ctext(cx, y + 19, label, 10)
        y += 30
    arrow(s, (cx, y), (cx, y + 22))
    y += 22
    s.draw_polyline([(cx, y), (cx + 80, y + 30), (cx, y + 60), (cx - 80, y + 30), (cx, y)])
    p.ctext(cx, y + 34, "Reading OK?", 10)
    arrow(s, (cx + 80, y + 30), (cx + 150, y + 30))
    p.text(cx + 92, y + 24, "No", 9)
    s.draw_rect((cx + 150, y + 15, cx + 250, y + 45))
    p.ctext(cx + 200, y + 34, boxes[2], 9.5)
    s.draw_polyline([(cx + 200, y + 15), (cx + 200, y - 30), (cx + 80, y - 30)])
    arrow(s, (cx + 81, y - 30), (cx + 80, y - 30))
    arrow(s, (cx, y + 60), (cx, y + 84))
    p.text(cx + 6, y + 76, "Yes", 9)
    y += 84
    s.draw_oval((cx - 50, y, cx + 50, y + 26))
    p.ctext(cx, y + 17, "End", 10)
    s.finish(width=1.1, color=(0, 0, 0), closePath=False)
    s.commit()
    p.figure("flowchart", (cx - 84, top - 2, cx + 254, y + 28))
    p.footer(n)


def form(p: Page, n):
    r = p.rng
    y = p.header(f"{r.choice(['Equipment Request', 'Room Booking', 'Field Trip Consent', 'Maintenance Report'])} Form")
    s = p.shape()
    fields = r.sample(["Full name", "Department", "Phone", "Email", "Date", "Reference no."], 4)
    for i, f in enumerate(fields):
        x0 = 54 if i % 2 == 0 else 312
        yy = y + (i // 2) * 30
        end = p.text(x0, yy, f + ":", 10.5)
        s.draw_line((end + 6, yy + 2), (x0 + 246, yy + 2))
    s.finish(width=0.6, color=(0, 0, 0))
    y += 74
    p.text(54, y, "Type of request (tick one or more):", 10.5, p.bold)
    y += 22
    opts = r.sample(["Laptop", "Projector", "Camera", "Microphone", "Vehicle", "Tools", "Lab bench", "Meeting room"], 6)
    checks = []
    for i, o in enumerate(opts):
        x0 = 60 + (i % 3) * 170
        yy = y + (i // 3) * 24
        s.draw_rect((x0, yy - 9, x0 + 11, yy + 2))
        on = r.random() < 0.4
        checks.append([o, on])
        if on:
            s.draw_line((x0 + 2, yy - 3), (x0 + 5, yy))
            s.draw_line((x0 + 5, yy), (x0 + 10, yy - 8))
        p.text(x0 + 18, yy, o, 10.5)
    s.finish(width=0.8, color=(0, 0, 0))
    s.commit()
    y += 64
    p.text(54, y, "Items required", 10.5, p.bold)
    y += 10
    s = p.shape()
    cols = [("Item", 220), ("Qty", 60), ("From", 112), ("Until", 112)]
    rows = 5
    top = y
    x = 54
    for name, w in cols:
        p.text(x + 5, y + 15, name, 10, p.bold)
        x += w
    for k in range(rows + 2):
        s.draw_line((54, top + 22 * k), (558, top + 22 * k))
    x = 54
    for _, w in cols:
        s.draw_line((x, top), (x, top + 22 * (rows + 1)))
        x += w
    s.draw_line((558, top), (558, top + 22 * (rows + 1)))
    s.finish(width=0.7, color=(0, 0, 0))
    s.commit()
    p.figure("table", (52, top - 2, 560, top + 22 * (rows + 1) + 2))
    y = top + 22 * (rows + 1) + 30
    y = p.wrap(54, y, 504, "I confirm that the information above is correct and that I will return all items in good condition.", 10)
    y += 30
    s = p.shape()
    s.draw_line((54, y), (300, y))
    s.draw_line((340, y), (558, y))
    s.finish(width=0.6, color=(0, 0, 0))
    s.commit()
    p.text(54, y + 14, "Signature", 9, p.italic)
    p.text(340, y + 14, "Date", 9, p.italic)
    p.figure("form", (50, top - 160, 562, top - 26))
    p.footer(n)
    return {"checkboxes": checks}


def article(p: Page, n):
    r = p.rng
    title = r.choice(["Water Use in Small Towns", "Evening Classes Grow", "The Valley Bridge Project", "A Year of Rainfall"])
    p.text(54, 78, title, 20, p.bold)
    p.text(54, 98, f"By {r.choice(['A. Moreno', 'J. Clarke', 'L. Chen', 'R. Okafor'])}", 10, p.italic)
    s = p.shape()
    s.draw_line((54, 108), (558, 108))
    s.finish(width=0.8, color=(0, 0, 0))
    s.commit()
    colw, gap = 240, 24
    y1 = p.paragraph(54, 130, colw, 6, 10)
    y1 = p.paragraph(54, y1 + 8, colw, 5, 10)
    # small inline figure in the left column
    fy = y1 + 12
    vals = [r.uniform(0.2, 1) for _ in range(7)]
    s = p.shape()
    s.draw_rect((54, fy, 54 + colw, fy + 90))
    s.finish(width=0.6, color=(0, 0, 0))
    for i, v in enumerate(vals):
        x = 70 + i * 30
        s.draw_rect((x, fy + 80 - 64 * v, x + 18, fy + 80))
        s.finish(fill=(0.35, 0.35, 0.35), color=None, width=0)
    s.commit()
    p.figure("chart", (52, fy - 2, 56 + colw, fy + 92))
    p.text(54, fy + 104, "Figure 1. Weekly totals, first quarter.", 8.5, p.italic)
    y2 = p.paragraph(54 + colw + gap, 130, colw, 8, 10)
    y2 = p.paragraph(54 + colw + gap, y2 + 8, colw, 6, 10)
    s = p.shape()
    s.draw_line((54, PAGE_H - 92), (200, PAGE_H - 92))
    s.finish(width=0.5, color=(0, 0, 0))
    s.commit()
    p.wrap(54, PAGE_H - 80, 504, "1. " + r.choice(SENTENCES), 8)
    p.wrap(54, PAGE_H - 68, 504, "2. " + r.choice(SENTENCES), 8)
    p.footer(n)


TEMPLATES = dict(worksheet=worksheet, table=table, chart=chart, flowchart=flowchart, form=form, article=article)


# ---------------------------------------------------------------- scanning

def degrade(img: Image.Image, rng: random.Random) -> tuple[Image.Image, dict]:
    a = np.asarray(img.convert("RGB")).astype(np.float32) / 255
    h, w, _ = a.shape
    ang = rng.uniform(-1.2, 1.2)
    blur = rng.uniform(0.5, 1.1)
    noise = rng.uniform(0.015, 0.035)
    tint = np.array([rng.uniform(0.94, 0.99), rng.uniform(0.92, 0.97), rng.uniform(0.82, 0.92)])
    q = rng.randint(50, 75)
    # ink spread and slight darkening of ink
    im = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur))
    im = im.rotate(ang, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))
    a = np.asarray(im).astype(np.float32) / 255
    yy, xx = np.mgrid[0:h, 0:w]
    light = 1 - 0.08 * ((xx / w - rng.uniform(0.2, 0.8)) ** 2 + (yy / h - rng.uniform(0.2, 0.8)) ** 2)
    a = a * tint * light[..., None]
    nrng = np.random.default_rng(rng.randint(0, 2**31))
    a = a + nrng.normal(0, noise, a.shape)
    a = np.clip(a, 0, 1)
    out = Image.fromarray((a * 255).astype(np.uint8))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB"), {"rotation_deg": round(ang, 3), "blur": round(blur, 2),
                                             "noise": round(noise, 3), "jpeg_quality": q}


def photograph(img: Image.Image, rng: random.Random) -> tuple[Image.Image, dict]:
    """A phone photo of the sheet lying on a desk: perspective, background, shadow, blur."""
    page = np.asarray(img.convert("RGB")).astype(np.float32) / 255
    h, w, _ = page.shape
    W, H = int(w * rng.uniform(1.12, 1.22)), int(h * rng.uniform(1.08, 1.15))
    desk = np.array(rng.choice([(0.45, 0.33, 0.24), (0.36, 0.37, 0.40), (0.55, 0.52, 0.47), (0.25, 0.28, 0.33)]))
    nrng = np.random.default_rng(rng.randint(0, 2**31))
    tex = ndi_blur(nrng.normal(0, 1, (H // 8, W // 8)), 2)
    tex = np.asarray(Image.fromarray(((tex - tex.min()) / (np.ptp(tex) + 1e-6) * 255).astype(np.uint8)).resize((W, H)))
    bg = desk[None, None, :] * (0.85 + 0.3 * tex[..., None] / 255)
    j = lambda: rng.uniform(-0.035, 0.035)
    mx, my = (W - w) / 2, (H - h) / 2
    quad = [(mx + j() * w, my + j() * h), (mx + w + j() * w, my + j() * h),
            (mx + w + j() * w, my + h + j() * h), (mx + j() * w, my + h + j() * h)]
    src = [(0, 0), (w, 0), (w, h), (0, h)]
    a, b = [], []
    for (u, v), (x, y) in zip(quad, src):          # canvas (u, v) -> page (x, y)
        a.append([u, v, 1, 0, 0, 0, -x * u, -x * v]); b.append(x)
        a.append([0, 0, 0, u, v, 1, -y * u, -y * v]); b.append(y)
    coeffs = tuple(np.linalg.solve(np.array(a, float), np.array(b, float)))
    warped = np.asarray(Image.fromarray((page * 255).astype(np.uint8)).transform(
        (W, H), Image.PERSPECTIVE, coeffs, resample=Image.BICUBIC, fillcolor=(0, 0, 0))).astype(np.float32) / 255
    mask = np.asarray(Image.new("L", (w, h), 255).transform((W, H), Image.PERSPECTIVE, coeffs,
                                                             resample=Image.BILINEAR, fillcolor=0)).astype(np.float32) / 255
    paper = np.array([rng.uniform(0.95, 0.99), rng.uniform(0.93, 0.98), rng.uniform(0.86, 0.94)])
    out = bg * (1 - mask[..., None]) + warped * paper * mask[..., None]
    yy, xx = np.mgrid[0:H, 0:W]
    ang = rng.uniform(0, 2 * math.pi)
    t = ((xx - W / 2) * math.cos(ang) + (yy - H / 2) * math.sin(ang)) / max(W, H)
    shadow = 1 - rng.uniform(0.12, 0.28) / (1 + np.exp(-(t - rng.uniform(0.05, 0.3)) * 18))
    vignette = 1 - 0.18 * (((xx / W - 0.5) ** 2 + (yy / H - 0.5) ** 2) * 2)
    out = out * shadow[..., None] * vignette[..., None]
    im = Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(rng.uniform(0.8, 1.5)))
    a = np.asarray(im).astype(np.float32) / 255 + nrng.normal(0, rng.uniform(0.015, 0.03), (H, W, 3))
    q = rng.randint(55, 80)
    buf = io.BytesIO()
    Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).save(buf, "JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB"), {"capture": "photo", "quad": [[round(x), round(y)] for x, y in quad],
                                             "jpeg_quality": q}


def ndi_blur(a, sigma):
    from scipy import ndimage
    return ndimage.gaussian_filter(a, sigma)


def make(kind: str, seed: int, out: Path, hard: bool = False) -> dict:
    rng = random.Random(seed)
    p = Page(rng, hard)
    extra = TEMPLATES[kind](p, rng.randint(1, 40)) or {}
    out.mkdir(parents=True, exist_ok=True)
    p.doc.save(out / "truth.pdf", garbage=3, deflate=True)
    pix = p.page.get_pixmap(dpi=DPI, alpha=False)
    clean = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if hard and rng.random() < 0.5:
        scan, params = photograph(clean, rng)
    else:
        scan, params = degrade(clean, rng)
        params["capture"] = "scanner"
    scan.save(out / "scan.jpg", quality=95)
    words = [w[4] for w in p.page.get_text("words")]
    truth = {
        "id": out.name, "kind": kind, "seed": seed, "dpi": DPI,
        "page_pt": [PAGE_W, PAGE_H], "scan_px": [pix.width, pix.height],
        "words": words, "figures": p.figures, "scan_params": params, "font_family": p.family, **extra,
    }
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    return truth


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--split", default="dev")
    ap.add_argument("--count", type=int, default=1, help="pages per template kind")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--kinds", nargs="+", default=list(KINDS), choices=KINDS)
    ap.add_argument("--hard", action="store_true", help="unfamiliar fonts, denser content, half phone photos")
    args = ap.parse_args()
    i = 0
    for c in range(args.count):
        for kind in args.kinds:
            seed = args.seed + i
            t = make(kind, seed, args.out / args.split / f"{kind}-{seed}", args.hard)
            print(f"{t['id']}: {len(t['words'])} words, {len(t['figures'])} figures, "
                  f"{t['font_family']}, {t['scan_params'].get('capture')}")
            i += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
