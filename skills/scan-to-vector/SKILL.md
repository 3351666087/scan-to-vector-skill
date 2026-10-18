---
name: scan-to-vector
description: Rebuild scanned or photographed pages (worksheets, forms, tables, charts, flowcharts, manuals, book pages, multi-page packets) as clean, newly typeset PDFs with real searchable text, vector diagrams and charts, the original layout, and nothing invented. Use whenever someone wants a scan or phone photo of a document turned into a clean, editable, searchable or vector PDF, redrawn or retypeset, or a printed chart turned back into data. One command drafts every page; you proofread from one image per page and fix by id. For only adding a hidden OCR layer to an unchanged scan, use an OCR tool instead.
---

# Scan to vector

## Done means
Check all four before you report success.
1. **Real text.** Every word on the page is selectable text. No word is invented.
2. **Vector graphics.** Rules, tables, boxes, diagrams and charts are paths. No full-page image and no hidden OCR layer. Keep a raster crop only for photographs or engravings, and name it in your note.
3. **Same layout.** Same elements in the same places, on upright, flat pages with the original's proportions.
4. **Verified.** The report says PASS for every page and you have proofread every page, or your note lists what remains.

## Why it works this way
- **The draft does the mechanical 95%.** One command flattens photos, straightens pages, evens the light and reads the text twice. It places every word at its measured spot, size and weight. It draws rules, shading and fills, and traces every remaining line, arrow, outline and chart series into vector shapes. Your job is what scripts can't judge: reading the words OCR doubted, and checking.
- **You see a shrunken page.** Small print read off a whole page is guesswork. The draft crops every doubtful word, enlarges it and puts them all on one sheet per page, so one look checks them all.
- **Looking right is not being right.** Every rebuild is compared with the scan. The report lists exactly what is missing or misplaced.

## Method
`S` is this skill's folder. `PY` is a Python with PyMuPDF, Pillow, numpy and scipy, plus the `tesseract` command.

1. **Draft every page at once:** `PY S/scripts/draft.py page1.jpg [page2.jpg ...] --out work --pdf out/rebuilt.pdf`.
   It writes `work/pNN/` per page and `work/report.md`. Photos are snapped to the nearest standard paper size; for books, receipts and other odd sizes add `--paper none` (or force one: `--paper a4`).
2. **Proofread each page from its sheet.** Open `work/pNN/compare/words.png`. Each crop from the scan has an id and the current reading under it.
   - **A wrong reading:** put the right text in `work/pNN/fixes.json` under its id. Use `""` to delete a reading that is not text.
   - **"?" (ink not drawn yet):** if it is text, add it with the position from the report's box (x = left edge, baseline = bottom of letters without descenders). Use the size of the neighbouring line in `probe.json` (`size_px`).
   ```json
   {"words": {"13.0": "(B)", "19.0": "8 cm", "4.2": ""},
    "add": [{"text": "h", "x": 561, "baseline": 1122, "size": 30, "italic": true}]}
   ```
   - Never guess text you cannot read. Keep the reading and list it as uncertain.
3. **Check the rest on the diff.** Open `work/pNN/compare/diff.png`. Red is on the scan but not drawn; blue is drawn where the scan is blank. For anything red or blue that is not text, zoom in: `PY S/scripts/zoom.py work/pNN/deskewed.png X0 Y0 X1 Y1 --grid 50 --out work/zoom.png`. Then:
   - **Traced shapes, fills and rules** are in `draft.json` ("shapes", "fills", "rules"). Delete strays such as specks and shadows there. A traced outline may be replaced by a clean `c.line`/`c.ellipse`/`c.polyline` if you want it more editable.
   - **Anything still missing:** add drawing calls in the marked section of `build.py`, using coordinates from a gridded zoom.
4. **Rebuild:** `PY S/scripts/draft.py --rebuild work --pdf out/rebuilt.pdf`.
   - **When to stop:** every page is PASS and every sheet is proofread. Don't polish beyond that. If a page isn't PASS after three rounds, stop and note what remains.
   - "check" lines in the report are advisory.
5. **Deliver** the PDF and a 3–6 line note: pages, what is text and vector, any raster crops, uncertain words.

## Drawing calls (in build.py; coordinates are pixels of that page's deskewed.png)
```python
c.text(x, baseline, "Label", size=28, font=d["font"], bold=False, italic=False, align="center")
c.line(p0, p1, width=2, dash=(8, 4))      c.polyline([(x, y), ...], width=3, color="#1f5fa8", closed=False)
c.rect((x0, y0, x1, y1), width=2, fill=None)   c.circle((cx, cy), r, width=2)   c.ellipse((x0, y0, x1, y1))
c.arrow(p0, p1, width=2, head=12)         c.checkbox((x0, y0, x1, y1), checked=True)
c.arc((cx, cy), r, 0, 90, sector=True, fill="#f45f3f")
```
Sample colours from `deskewed.png` instead of guessing. `c.add_font(name, path)` registers a TTF for glyphs the built-in fonts lack. Keep measured sizes and widths; "tidy" round values drift from the original.

## Larger jobs
For books, multi-file sets and resumable projects, read `references/long-documents.md` (page ledger, checkpoints, parallel work). Charts as data, and figures the tracer can't handle (photos, engravings): `references/figures.md`. Pagination, links and release: `references/render-and-release.md`. `scripts/pdf_tool.py` audits fonts, images and links in the finished PDFs. Single-page tools remain available: `probe.py`, `canvas.py`, `compare.py`.
