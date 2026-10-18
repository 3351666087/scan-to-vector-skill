#!/usr/bin/env python3
"""Sanity-check score.py with reference outputs of known quality.

For each page it builds and scores:
  truth        the ground-truth PDF itself                     -> near 1
  truth-moved  truth on A4, scaled, shifted and turned 1 degree -> near 1 (registration works)
  ocr-layer    the scan as an image plus Tesseract's hidden text (what OCRmyPDF makes)
  text-only    Tesseract's text reflowed onto a blank page

    python bench/calibrate.py <split dir>
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import score  # noqa: E402


def truth_moved(page_dir: Path, out: Path):
    src = pymupdf.open(page_dir / "truth.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)               # A4
    page.show_pdf_page(pymupdf.Rect(30, 40, 30 + 580, 40 + 750), src, 0, rotate=-1)
    doc.save(out)


def ocr_layer(page_dir: Path, out: Path):
    base = out.with_suffix("")
    subprocess.run(["tesseract", str(page_dir / "scan.jpg"), str(base), "pdf"], check=True,
                   capture_output=True)


def text_only(page_dir: Path, out: Path):
    txt = subprocess.run(["tesseract", str(page_dir / "scan.jpg"), "-"], check=True,
                         capture_output=True, text=True).stdout
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_textbox(pymupdf.Rect(54, 54, 558, 760), txt, fontsize=10, fontname="helv")
    doc.save(out)


def main() -> int:
    split = Path(sys.argv[1])
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for page_dir in sorted(p for p in split.iterdir() if (p / "truth.json").exists()):
            row = {"page": page_dir.name}
            for name, make in (("truth", None), ("truth-moved", truth_moved),
                               ("ocr-layer", ocr_layer), ("text-only", text_only)):
                pdf = page_dir / "truth.pdf" if make is None else Path(tmp) / f"{page_dir.name}-{name}.pdf"
                if make:
                    make(page_dir, pdf)
                s = score(page_dir, pdf)
                row[name] = {k: s[k] for k in ("score", "text_f1", "layout_f1", "figure", "raster")}
            rows.append(row)
            print(page_dir.name, "  ".join(f"{k}={v['score']:.2f}" for k, v in row.items() if k != "page"))
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
