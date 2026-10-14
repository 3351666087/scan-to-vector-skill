---
name: scan-to-vector
description: Reconstruct scanned books, manuals, forms, and worksheets as searchable, newly typeset PDFs with vector diagrams. Use when the user wants scans redrawn or retypeset, or asks to resume a partial scan reconstruction. Includes OCR reconciliation, page provenance, diagram reconstruction, pagination, cross-references, and visual QA. For adding a hidden OCR layer without changing the page design, use a simpler OCR workflow.
---

# Scan to vector

Rebuild the supplied document while preserving its content and functional meaning. Use the source image as the authority for reading order, labels, blanks, and diagram geometry. Deliver searchable body text and vector artwork where appropriate; describe any retained raster images accurately.

## 1. Establish the job and checkpoint

- Inspect the user's sources, project instructions, existing content, renderer, and latest handoff. Resume verified work in place. Infer scope from the request; ask only for missing decisions that materially change the result, such as facsimile versus redesigned layout.
- Inventory every input PDF and its physical pages. Read [the provenance and content guide](references/content-and-provenance.md) before creating or changing the page ledger. Keep source page index, printed page label, and output page number separate.
- Choose a renderer already working in the project when practical. Verify representative difficult content present in the source through the actual final renderer before committing to a full layout; include diagrams and page boundaries when applicable.
- Create a checkpoint containing scope, source identities, page ledger, build command, current file ownership, unresolved questions, and the next small batch. Use project-relative paths in portable records.

**Done when:** every supplied physical page is accounted for, the desired output is clear, and the next batch can be resumed without the conversation history.

## 2. Reconcile OCR with the scan

- Extract any existing text layer and obtain independent OCR when extraction is absent or unreliable. Save OCR text and word/line coordinates alongside a readable source rendering; retain higher-resolution originals for crops and close inspection.
- Inspect low-text pages visually. Covers, diagrams, forms, and pale artwork can look blank to OCR. Record genuinely blank and duplicate pages explicitly.
- Read columns, footnotes, captions, tables, and callouts in visual order. Correct recognition errors against the image. Preserve intentional errors, answer blanks, question numbers, phonetics, and strikeouts in educational material.
- Save corrected content in small batches, usually 1–3 source pages. Each batch updates the ledger and records unresolved readings. If the source is unclear, mark the uncertainty for review rather than inventing content.
- For parallel work, assign disjoint source ranges and owned files. Keep shared styles, renderer changes, and release builds under one owner.

**Done when:** each in-scope page has source-linked content or an explicit reviewed disposition, with uncertainty resolved or disclosed.

## 3. Reconstruct figures and layout

- Use editable text and table structures for body copy and tabular content. Redraw charts, line art, maps, grids, and forms as vector objects when their structure can be recovered. Retain photographic or complex illustrative regions as clean raster crops where appropriate.
- When a page contains diagrams, charts, forms, or crops, read [the figure reconstruction guide](references/figures.md). Verify data, topology, labels, arrows, and answer spaces against the source before polishing appearance.
- Keep content, styling, and figure data separate enough to revise one without retranscribing the others. Preserve nearby relationships: prompt with answer space, diagram with its legend, caption with its image.
- Render a small batch after each structural change. Check dense tables, long passages, headings near page breaks, and large kept blocks at readable resolution.

**Done when:** the batch is legible, content-complete, and its figure semantics match the source in the production renderer.

## 4. Stabilize pagination and navigation

Read [the rendering and release guide](references/render-and-release.md) before implementing page references or the first full build. It covers semantic anchors, renderer boundary errors, staged output, and final checks.

- Generate page mappings from the final renderer's layout or PDF destinations. Link to the actual chart, exercise, or section when a source page spans multiple output pages.
- Keep headings with their content and size keep-together blocks narrowly. Recheck any pagination affected by anchor or CSS changes.
- Build to a temporary output. Check process success and PDF readability before replacing a previously verified result. Publish the matching page map and related PDFs together.

**Done when:** all references resolve to the intended visible objects, and the verified PDF and page map describe the same build.

## 5. Verify and deliver

- Review every final page using contact sheets, then inspect small, dense, suspicious, or changed pages at readable resolution against the source. Contact sheets establish coverage; they do not verify individual words or diagram values.
- Check source coverage, text extraction, font support/embedding, clipped text, missing assets, unresolved markup, and link targets. Use the bundled helper for mechanical evidence; its limits are described below.
- Resolve findings and rerender affected pages. Rebuild the whole document when pagination or cross-document targets changed. Record remaining uncertainties and missing source material honestly.
- Deliver the PDF(s), a concise coverage/limitations note, and editable source when requested. Retain the reproducible working project. Source deletion, remote upload, and publication follow the user's actual authorization; the workflow itself grants none.

**Done when:** every source disposition and output page has review evidence, final artifacts open successfully, navigation is correct, and unresolved limitations are stated.

## Bundled mechanical helper

`scripts/pdf_tool.py` uses PyMuPDF and Pillow, listed in `requirements.txt`. Install them in a project environment if needed; use that interpreter for the commands below. Resolve `<skill-dir>` to this skill's location.

```sh
python <skill-dir>/scripts/pdf_tool.py inspect source.pdf --out work/source-inspection.json
python <skill-dir>/scripts/pdf_tool.py contacts rebuilt.pdf --out work/contact-sheets
python <skill-dir>/scripts/pdf_tool.py audit rebuilt.pdf --out work/pdf-audit.json --links-root output
```

Inspect `--help` for optional sizing controls. An audit can detect structural problems, not OCR accuracy, reading order, missing source content, chart correctness, or visual quality. Vector-drawing counts and image counts are evidence about PDF objects, not a guarantee that the document is fully vector or searchable. Pair the report with the ledger and human-readable visual review notes.

Reports are JSON, saved to `--out` and printed to stdout; `contacts` writes PNGs and `contacts.json` inside its output directory. Exit code `0` permits warnings, `1` means an audit found structural issues, and `2` means the command could not complete. Review warnings and unchecked links even when the exit code is zero. External PDF checking stays within `--links-root`; unsupported platforms or oversized targets are reported as unchecked.
