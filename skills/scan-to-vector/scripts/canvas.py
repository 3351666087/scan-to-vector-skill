#!/usr/bin/env python3
"""Draw a rebuilt page in the scan's own pixel coordinates.

Every measurement from probe.py is in pixels of deskewed.png. Canvas keeps
that coordinate system and converts to PDF points on output, so positions
copied from probe.json land exactly where they were on the scan.

    import sys; sys.path.insert(0, "<skill>/scripts")
    from canvas import Canvas

    c = Canvas.from_probe("work/probe/probe.json")       # page size and scale
    c.place_lines(c.probe["lines"], font="serif")        # all OCR text, measured spots
    c.line((120, 400), (1580, 400), width=3)             # a rule
    c.rect((300, 900, 700, 980), stroke="#000", width=2) # a box
    c.text(520, 950, "Start", size=28, align="center")   # a label
    c.save("out/rebuilt.pdf")

Fonts: "serif" (Times), "sans" (Helvetica), "mono" (Courier), each with
bold/italic; or register any TTF/OTF with c.add_font("name", "path.ttf").
Sizes and widths are in scan pixels. Colours are "#rrggbb" or (r, g, b) 0..1.
Raster crops (c.image) are listed in the PDF's metadata so the delivery note
can say which regions are not vector.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pymupdf

BASE14 = {
    ("serif", False, False): "tiro", ("serif", True, False): "tibo",
    ("serif", False, True): "tiit", ("serif", True, True): "tibi",
    ("sans", False, False): "helv", ("sans", True, False): "hebo",
    ("sans", False, True): "heit", ("sans", True, True): "hebi",
    ("mono", False, False): "cour", ("mono", True, False): "cobo",
    ("mono", False, True): "coit", ("mono", True, True): "cobi",
}


def colour(c):
    if c is None:
        return None
    if isinstance(c, str):
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return tuple(c)


def reading_order(lines, page_width=None):
    """Order text lines as a reader would: top to bottom, and column by column where text is
    set in columns (a recursive cut on the gaps between line boxes). Narrow cells, as in a
    table, stay row by row."""
    if not lines:
        return lines
    page_width = page_width or max(l["box"][2] for l in lines)
    hs = sorted(l["box"][3] - l["box"][1] for l in lines)
    gap_y, gap_x = 1.2 * hs[len(hs) // 2], 0.8 * hs[len(hs) // 2]

    def groups(items, axis, gap):
        items = sorted(items, key=lambda l: l["box"][axis])
        out, cur, edge = [], [items[0]], items[0]["box"][axis + 2]
        for l in items[1:]:
            if l["box"][axis] - edge > gap:
                out.append(cur)
                cur = []
            cur.append(l)
            edge = max(edge, l["box"][axis + 2])
        return out + [cur]

    def wide(g):
        ws = sorted(l["box"][2] - l["box"][0] for l in g)
        return ws[len(ws) // 2] > 0.22 * page_width

    def cut(items):
        if len(items) <= 1:
            return items
        bands = groups(items, 1, gap_y)
        if len(bands) > 1:
            return [x for b in bands for x in cut(b)]
        cols = groups(items, 0, gap_x)
        if len(cols) > 1 and all(wide(c) for c in cols):
            return [x for c in cols for x in cut(c)]
        return sorted(items, key=lambda l: (l["baseline"], l["box"][0]))
    return cut(list(lines))


def load_probe(probe_path):
    """probe.json with the corrections in fixes.json (same folder) applied:
        {"words": {"12.2": "6 cm", "3.0": ""},          line.word -> new text ("" deletes it)
         "add": [{"text": "h", "x": 520, "baseline": 1250, "size": 30, "italic": true}]}
    Word ids are "line.word" indexes into probe.json "lines" (shown in words.png)."""
    probe_path = Path(probe_path)
    data = json.loads(probe_path.read_text())
    data["_dir"] = str(probe_path.parent)
    fixes_path = probe_path.parent / "fixes.json"
    fixes = json.loads(fixes_path.read_text()) if fixes_path.exists() else {}
    for key, text in fixes.get("words", {}).items():
        li, wi = (int(v) for v in key.split("."))
        data["lines"][li]["words"][wi]["text"] = text
        data["lines"][li]["words"][wi]["conf"] = 100.0
    for line in data["lines"]:
        line["words"] = [w for w in line["words"] if w["text"].strip()]
        line["text"] = " ".join(w["text"] for w in line["words"])
    data["lines"] = [l for l in data["lines"] if l["words"]]
    added = []
    for a in fixes.get("add", []):                     # text OCR missed, placed in reading order
        size = a.get("size", 30)
        x, base = a["x"], a["baseline"]
        word = {"text": a["text"], "conf": 100.0, "natural": True, "box": [x, base - size * 0.75, x + size * 0.5 * len(a["text"]), base],
                "bold": a.get("bold", False), "italic": a.get("italic", False), "color": a.get("color", "#000000")}
        added.append({"text": a["text"], "box": [round(v) for v in word["box"]], "baseline": base, "size_px": size,
                      "words": [word], "align": a.get("align", "left"), **({"font": a["font"]} if "font" in a else {})})
    if added:
        data["lines"] = reading_order(data["lines"] + added, data.get("size_px", [None])[0])
    data["_added"] = []
    return data


class Canvas:
    def __init__(self, width_px: float, height_px: float, page_width_pt: float = 612,
                 page_height_pt: float | None = None, probe: dict | None = None):
        self.k = page_width_pt / width_px
        self.size_px = (width_px, height_px)
        self.doc = pymupdf.open()
        h_pt = page_height_pt if page_height_pt else height_px * self.k
        self.page = self.doc.new_page(width=page_width_pt, height=h_pt)
        self.probe = probe or {}
        self.fonts: dict[str, pymupdf.Font] = {}
        self.custom: dict[str, str] = {}
        self.rasters: list[list[float]] = []
        self.placed_words = 0

    def place_added(self, font="serif"):
        """Draw the words listed under "add" in fixes.json (text OCR missed)."""
        for a in self.probe.get("_added", []):
            self.text(a["x"], a["baseline"], a["text"], a.get("size", 30), font=a.get("font", font),
                      bold=a.get("bold", False), italic=a.get("italic", False), color=a.get("color", "#000000"),
                      align=a.get("align", "left"))

    # ------------------------------------------------------------ setup
    @classmethod
    def from_probe(cls, probe_path, page=None):
        """Page size and measurements from probe.json, with fixes.json (if present) applied."""
        probe_path = Path(probe_path)
        data = load_probe(probe_path)
        w, h = data["size_px"]
        pg = page or data.get("page", {})
        return cls(w, h, pg.get("width_pt", 612), pg.get("height_pt"), probe=data)

    def add_font(self, name: str, path: str):
        """Register a TTF/OTF (for glyphs the built-in fonts lack, or a closer match)."""
        self.page.insert_font(fontname=name, fontfile=str(path))
        self.fonts[name] = pymupdf.Font(fontfile=str(path))
        self.custom[name] = str(path)

    def _font(self, font, bold, italic):
        if font in self.custom:
            return font
        return BASE14[(font, bool(bold), bool(italic))]

    def _fobj(self, name):
        if name not in self.fonts:
            self.fonts[name] = pymupdf.Font(name)
        return self.fonts[name]

    def P(self, x, y):
        return pymupdf.Point(x * self.k, y * self.k)

    # ------------------------------------------------------------ text
    def text_width(self, s, size, font="serif", bold=False, italic=False):
        return self._fobj(self._font(font, bold, italic)).text_length(s, fontsize=size)

    def text(self, x, baseline, s, size, font="serif", bold=False, italic=False, color="#000000",
             width=None, align="left", angle=0.0, max_stretch=0.3):
        """Place text with its baseline at y. `width` (px) fits the text to a measured width by
        stretching it horizontally up to +/- max_stretch; align is left/center/right."""
        name = self._font(font, bold, italic)
        natural = self._fobj(name).text_length(s, fontsize=size)
        sx = 1.0
        if width and natural > 0:
            sx = min(max(width / natural, 1 - max_stretch), 1 + max_stretch)
        w = natural * sx
        if align == "center":
            x -= w / 2
        elif align == "right":
            x -= w
        pt = self.P(x, baseline)
        m = pymupdf.Matrix(sx, 1)
        if angle:
            m = m * pymupdf.Matrix(-angle)
        self.page.insert_text(pt, s + " ", fontname=name, fontsize=size * self.k, color=colour(color),
                              morph=(pt, m) if (sx != 1 or angle) else None)
        self.placed_words += len(s.split())
        return x + w

    def place_lines(self, lines, font="serif", bold_words=(), italic=False, color="#000000",
                    min_conf=0, skip=None, size_scale=1.0):
        """Place OCR lines word by word at their measured positions and widths.

        lines: probe.json "lines" (edit their "text"/"words" first to fix OCR errors).
        skip:  optional function(line) -> True to leave a line out (e.g. labels you redraw).
        A word whose "text" you corrected keeps its measured box.
        """
        for line in lines:
            if skip and skip(line):
                continue
            size = line.get("size_px", 30) * size_scale
            base = line["baseline"]
            for wd in line["words"]:
                if wd.get("conf", 100) < min_conf or not wd["text"].strip():
                    continue
                x0, _, x1, _ = wd["box"]
                bold = wd.get("bold", line.get("bold", False)) or wd["text"] in bold_words
                self.text(x0, base, wd["text"], size, font=line.get("font", font), bold=bold,
                          italic=wd.get("italic", line.get("italic", italic)), color=wd.get("color", color),
                          width=None if wd.get("natural") else x1 - x0, align=line.get("align", "left"))

    # ------------------------------------------------------------ vector shapes
    def _finish(self, shape, stroke, width, fill=None, dash=None, closed=False, cap=0, join=0):
        shape.finish(color=colour(stroke), fill=colour(fill), width=(width or 0) * self.k,
                     dashes=f"[{dash[0] * self.k:.2f} {dash[1] * self.k:.2f}] 0" if dash else None,
                     closePath=closed, lineCap=cap, lineJoin=join)

    def line(self, p0, p1, width=2, color="#000000", dash=None, cap="butt"):
        s = self.page.new_shape()
        s.draw_line(self.P(*p0), self.P(*p1))
        self._finish(s, color, width, dash=dash, cap={"butt": 0, "round": 1, "square": 2}[cap])
        s.commit()

    def polyline(self, pts, width=2, color="#000000", closed=False, fill=None, dash=None, join="miter"):
        s = self.page.new_shape()
        s.draw_polyline([self.P(*p) for p in pts])
        self._finish(s, color if width else None, width, fill, dash, closed,
                     join={"miter": 0, "round": 1, "bevel": 2}[join])
        s.commit()

    def rect(self, box, stroke="#000000", width=2, fill=None, radius=None, dash=None):
        s = self.page.new_shape()
        r = pymupdf.Rect(box[0] * self.k, box[1] * self.k, box[2] * self.k, box[3] * self.k)
        if radius:
            s.draw_rect(r, radius=radius * self.k / min(r.width, r.height))
        else:
            s.draw_rect(r)
        self._finish(s, stroke if width else None, width, fill, dash, closed=True)
        s.commit()

    def outline(self, paths, fill="#000000"):
        """Filled vector outline (closed paths, even-odd: inner paths are holes), e.g. a shape
        traced from the scan by draft.py."""
        s = self.page.new_shape()
        for p in paths:
            s.draw_polyline([self.P(*q) for q in p] + [self.P(*p[0])])
        s.finish(color=None, fill=colour(fill), width=0, even_odd=True, closePath=True)
        s.commit()

    def circle(self, centre, r, stroke="#000000", width=2, fill=None):
        s = self.page.new_shape()
        s.draw_circle(self.P(*centre), r * self.k)
        self._finish(s, stroke if width else None, width, fill, closed=True)
        s.commit()

    def ellipse(self, box, stroke="#000000", width=2, fill=None):
        s = self.page.new_shape()
        s.draw_oval(pymupdf.Rect(*(v * self.k for v in box)))
        self._finish(s, stroke if width else None, width, fill, closed=True)
        s.commit()

    def bezier(self, p0, c0, c1, p1, width=2, color="#000000"):
        s = self.page.new_shape()
        s.draw_bezier(self.P(*p0), self.P(*c0), self.P(*c1), self.P(*p1))
        self._finish(s, color, width)
        s.commit()

    def arc(self, centre, r, start_deg, end_deg, width=2, color="#000000", fill=None, sector=False):
        """Arc (or pie sector) in scan pixels; angles in degrees, 0 = east, counter-clockwise."""
        steps = max(8, int(abs(end_deg - start_deg) / 4))
        pts = [(centre[0] + r * math.cos(math.radians(a)), centre[1] - r * math.sin(math.radians(a)))
               for a in (start_deg + (end_deg - start_deg) * i / steps for i in range(steps + 1))]
        if sector:
            pts = [centre] + pts + [centre]
        self.polyline(pts, width=width, color=color, fill=fill, closed=sector, join="round")

    def arrow(self, p0, p1, width=2, color="#000000", head=12, filled=True):
        self.line(p0, p1, width, color)
        ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        left = (p1[0] - head * math.cos(ang - 0.42), p1[1] - head * math.sin(ang - 0.42))
        right = (p1[0] - head * math.cos(ang + 0.42), p1[1] - head * math.sin(ang + 0.42))
        if filled:
            self.polyline([left, p1, right], width=0.5, color=color, fill=color, closed=True)
        else:
            self.polyline([left, p1, right], width=width, color=color)

    def checkbox(self, box, checked=False, width=2, color="#000000"):
        self.rect(box, stroke=color, width=width)
        if checked:
            x0, y0, x1, y1 = box
            self.polyline([(x0 + 0.2 * (x1 - x0), y0 + 0.55 * (y1 - y0)), (x0 + 0.42 * (x1 - x0), y1 - 0.18 * (y1 - y0)),
                           (x1 - 0.12 * (x1 - x0), y0 + 0.15 * (y1 - y0))], width=width, color=color, join="round")

    # ------------------------------------------------------------ raster (use sparingly)
    def image(self, box, source=None):
        """Keep a region as a raster crop (photographs, engravings, signatures). It is
        recorded and should be named in the delivery note."""
        source = source or str(Path(self.probe.get("_dir", ".")) / self.probe.get("image", "deskewed.png"))
        from PIL import Image
        import io
        im = Image.open(source).crop(tuple(int(v) for v in box))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        self.page.insert_image(pymupdf.Rect(*(v * self.k for v in box)), stream=buf.getvalue())
        self.rasters.append([round(v) for v in box])

    # ------------------------------------------------------------ output
    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.set_metadata({"producer": "scan-to-vector canvas",
                               "keywords": json.dumps({"raster_regions_px": self.rasters})})
        tmp = path.with_suffix(".pending.pdf")
        self.doc.subset_fonts()
        self.doc.save(tmp, garbage=3, deflate=True)
        tmp.replace(path)
        return path
