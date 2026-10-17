<p align="center">
  <img src="assets/hero.svg" width="100%" alt="A scanned page of Byrne's 1847 Euclid is swept by a scanning beam and replaced by a clean vector rebuild; a zoomed split view compares the scan's JPEG pixels with sharp vector letters.">
</p>

<h1 align="center">scan-to-vector</h1>

<p align="center">
  <b>Rebuild scanned books, manuals, worksheets and charts as searchable PDFs with vector diagrams, checked page by page against the scan.</b><br>
  An agent skill for Claude Code, Codex and any client that reads <code>SKILL.md</code>.
</p>

<p align="center">
  English · <a href="README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  <img alt="Agent Skill" src="https://img.shields.io/badge/Agent%20Skill-SKILL.md-2dd4bf?style=flat-square">
  <img alt="Works with Claude Code" src="https://img.shields.io/badge/Claude%20Code-ready-d97757?style=flat-square">
  <img alt="Works with Codex" src="https://img.shields.io/badge/Codex-ready-111827?style=flat-square">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square">
</p>

---

OCR gives you a scan with invisible text on top. **scan-to-vector gives you the page rebuilt**: real text you can search and copy, diagrams and charts redrawn as vector paths that stay sharp at any zoom, photographs and engravings kept as clean, labelled crops. Every source page is tracked in a ledger and the rebuild is overlaid on the scan before it ships.

## Demos

Both demos are real public-domain scans. The rebuilt PDFs in this repository were produced by an agent following [`SKILL.md`](skills/scan-to-vector/SKILL.md). Every measured coordinate is recorded in a build script, so you can regenerate them yourself.

### Byrne's *Euclid* (1847): text, colour diagrams and an engraved initial

| | Scan (input) | Rebuild (output) |
| --- | --- | --- |
| File | [`scan.jpg`](demo/byrne-euclid-I-11/source/scan.jpg), 1920×2519 JPEG, 300 KB | [`byrne-euclid-I-11.pdf`](demo/byrne-euclid-I-11/rebuilt/byrne-euclid-I-11.pdf), 80 KB |
| Text | pixels | searchable text in an open Caslon (Libre Caslon Text) |
| Diagrams and inline symbols | pixels | 82 vector paths, positions measured on the scan |
| Engraved initial "F" | pixels | kept as a cleaned raster crop, and listed as such |
| Checks | | overlay against the scan, [page ledger](demo/byrne-euclid-I-11/ledger.json), [structural audit](demo/byrne-euclid-I-11/review/audit.json): 0 issues |

Two editorial choices are recorded in the ledger rather than made silently: the long s (ſ) is modernised so that *straight* and *shall* stay searchable, and ∴ and ⊥ are drawn because the text face has no glyphs for them.

### Playfair's trade chart (1786): chart → data → vector

<p align="center">
  <img src="assets/playfair.svg" width="100%" alt="A cursor sweeps Playfair's 1786 chart year by year; behind it the engraving is replaced by a chart redrawn from the recovered yearly values, which a readout shows.">
</p>

The agent calibrated the engraved grid, traced both lines and recovered **81 yearly values per series** into [`data.csv`](demo/playfair-1786/rebuilt/data.csv). The [rebuilt chart](demo/playfair-1786/rebuilt/playfair-1786.pdf) is drawn only from that file, and its curves land back on the engraving, crossing in 1754 as the original does. The PDF contains no raster images.

## Is this the right tool?

| | OCR layer (e.g. OCRmyPDF) | PDF → Markdown (e.g. Marker, MinerU) | **scan-to-vector** |
| --- | --- | --- | --- |
| Output | original scan + hidden text | Markdown / JSON | a newly typeset PDF |
| Page appearance | identical to the scan | layout dropped | clean, close to the source |
| Diagrams and charts | stay raster | extracted as images | redrawn as vectors; chart data recovered |
| Provenance and checks | none | none | page ledger, overlay review, PDF audit |
| Speed | seconds | seconds to minutes | an agent working page by page |

If you only need searchable text on top of the scan, use an OCR layer: it is faster and cheaper. Use scan-to-vector when the page itself should be rebuilt: worksheets to print again, manuals with diagrams, old books, charts whose numbers you want back.

## Install

Copy the skill folder into your agent's skills directory.

```bash
git clone https://github.com/3351666087/scan-to-vector-skill.git
```

| Agent | Command |
| --- | --- |
| Claude Code | `mkdir -p ~/.claude/skills && cp -R scan-to-vector-skill/skills/scan-to-vector ~/.claude/skills/` |
| Codex | `mkdir -p ~/.codex/skills && cp -R scan-to-vector-skill/skills/scan-to-vector ~/.codex/skills/` |
| Others | copy `skills/scan-to-vector/` into any directory your client loads Agent Skills from |

The bundled PDF helper needs Python 3.10+ with PyMuPDF and Pillow:

```bash
python3 -m pip install -r scan-to-vector-skill/skills/scan-to-vector/requirements.txt
```

OCR and typesetting engines are not bundled. The agent uses what your project already has (Tesseract, LaTeX, an HTML-to-PDF renderer, PyMuPDF and so on) or chooses one for the job.

## Use

Ask your agent in plain language:

```text
Use scan-to-vector to rebuild worksheet.pdf as a clean, searchable PDF.
Keep every question and answer blank; redraw the diagrams as vectors, photos can stay.
Check each page against the scan and tell me about missing pages or unreadable spots.
```

```text
Use scan-to-vector to turn this scanned chart into data.csv and a redrawn vector chart.
```

```text
Use scan-to-vector to resume the half-finished rebuild in ./manual:
read the checkpoint and the page ledger, then continue from the first unfinished page.
```

## How it works

1. **Establish the job.** Inventory every input page, keep the source page index, printed page label and output page apart, and write a checkpoint so the work can resume without the chat history.
2. **Reconcile OCR with the scan.** OCR is a draft. Reading order, numerals, footnotes and answer blanks are corrected against the image, and doubtful readings are recorded, not guessed.
3. **Rebuild figures and layout.** Tables become text, diagrams and charts become vectors from recovered geometry or data, and photographs stay as crops.
4. **Stabilise pagination and links.** Page references are resolved from the final render, and builds are staged so a failed build never overwrites a verified one.
5. **Verify and deliver.** Contact sheets, close inspection and a structural audit, plus a delivery note listing what is vector, what stays raster and what is unresolved.

Details live in [`SKILL.md`](skills/scan-to-vector/SKILL.md) and the [`references/`](skills/scan-to-vector/references) guides.

## Helper script

`scripts/pdf_tool.py` provides the mechanical evidence: text, fonts, images, vector counts and links.

```bash
python skills/scan-to-vector/scripts/pdf_tool.py inspect  source.pdf  --out work/source.json
python skills/scan-to-vector/scripts/pdf_tool.py contacts rebuilt.pdf --out work/contact-sheets
python skills/scan-to-vector/scripts/pdf_tool.py audit    rebuilt.pdf --out work/audit.json --links-root output
```

An audit finds structural problems. It cannot prove that the OCR, a chart's values or the reading order are right, so the skill always pairs it with visual review against the source.

## Reproduce the demos

```bash
python3 -m venv .venv
.venv/bin/pip install -r skills/scan-to-vector/requirements.txt -r demo/requirements.txt
.venv/bin/python demo/byrne-euclid-I-11/rebuilt/build.py
.venv/bin/python demo/playfair-1786/rebuilt/digitize.py      # scan -> data.csv
.venv/bin/python demo/playfair-1786/rebuilt/build.py         # data.csv -> PDF
.venv/bin/python assets/build_hero.py && .venv/bin/python assets/build_chart_demo.py
```

The README animations are generated from these same files. The rebuilt pages are embedded with text as outlines so they look the same on every system, while the PDFs keep real text.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The tests generate synthetic PDFs on the fly and need no real books.

## Limits

- This is a workflow for an agent, not a one-click converter. Rebuilding takes minutes per page and costs model time.
- An audit passing does not mean the content is right; the skill requires review against the source.
- Retained photographs or engravings make the result a mixed-content PDF, and the delivery note says so.
- Deleting sources or publishing results happens only when you ask. The skill grants no such permission by itself.

## Credits

- Oliver Byrne, *The First Six Books of the Elements of Euclid* (1847), scan via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:First_six_books_of_the_elements_of_Euclid_1847_Byrne.djvu) / [Internet Archive](https://archive.org/details/firstsixbooksofe00byrn), public domain.
- William Playfair, *The Commercial and Political Atlas* (1786), scan via [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Playfair_TimeSeries-2.png), public domain.
- [Libre Caslon Text](https://github.com/thundernixon/Libre-Caslon), SIL Open Font License ([`demo/fonts/OFL.txt`](demo/fonts/OFL.txt)).
