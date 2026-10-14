# Content and provenance

## A ledger that survives repagination

Use a JSON, CSV, or equivalent machine-readable ledger with one entry per physical source PDF page. The structure can follow the project; these are its required meanings:

| Field | Meaning |
| --- | --- |
| `document_id` | Stable document identifier, also used in cross-document references. |
| `source_file`, `source_sha256`, `source_page_count` | Identity of the supplied input; hashes detect later replacement. |
| `source_page` | One-based physical PDF page index. |
| `printed_label` | Visible page label as a string, or null; may be Roman, repeated, absent, or discontinuous. |
| `disposition` | Pending, included, blank, duplicate, or intentionally omitted within the requested scope. |
| `content_file` | Project-relative transcription/layout source, when applicable. |
| `target_ids` | Stable semantic IDs for content on this source page. |
| `output_pages` | One-based pages in the verified final PDF; an array because mappings are many-to-many. |
| `review` | What was checked, unresolved readings, and why any content was excluded or consolidated. |

A spread or chapter may share a content file across several ledger entries. A consolidated cover may map several source pages to one output page. A blank page may have no output page when the chosen layout omits it, but must retain a reviewed disposition. Record apparent gaps in printed numbering separately; they do not create new physical source pages.

For example, source page 8 can be printed label `vi`, source page 9 can be printed label `1`, and one chart on source page 9 may land on output page 12. A universal offset cannot represent this reliably.

Before release, check that the ledger contains each integer from 1 through the input page count exactly once, every included entry has content and final output destinations, and every exclusion has a reason consistent with the user's scope. Printed-label gaps stay disclosed unless an additional source actually supplies them.

## Working files and resumability

A practical layout is `sources/`, `ocr/`, `content/`, `figures/`, `build/`, and `review/`; adapt an existing project instead of moving it gratuitously. Store raw extraction separately from corrected content. OCR coordinates must state their image dimensions or transform so crops remain reproducible.

Keep a compact checkpoint with:

- Source identity and ledger location.
- Last completed source range and exact next range.
- Interpreter/dependencies and the reproducible render command.
- Existing conventions for markup, IDs, fonts, and figure coordinates.
- Open questions, known renderer limitations, and delegated file ownership.
- Last verified output and which edits invalidate its page map.

Persist small batches before proceeding. For long passages, assemble from local corrected text rather than retransmitting whole chapters through a tool call. On resumption, compare files and source hashes with the checkpoint, then verify the last boundary before continuing. A partial transcript or previous agent's claim is a lead to inspect, not proof that the artifact is complete.

## OCR reconciliation

Use text extraction and OCR as draft material. Hidden PDF text may have the right words in the wrong column order. Word-coordinate output helps recover columns, tables, and captions, but the scan decides their relationship.

Prioritize visually fragile content: numerals, punctuation, footnotes, superscripts, units, phonetics, mathematical symbols, crossed-out examples, answer keys, and question numbering. Preserve a deliberately ungrammatical exercise sentence; change only recognition errors supported by the source.

Save uncertain readings with the source page and region. Examine higher resolution or a second OCR pass if useful. If still unresolved, report the ambiguity instead of silently completing a word, answer, chart value, or missing page.

## Review evidence

Track source checks separately from output checks. A source page can be transcribed correctly while its rendered table is clipped. An attractive rendered page can still omit a paragraph.

Record completed review ranges, findings, and repairs without repeating the whole document. Delegate independent proofreading or contact-sheet review where available. A reviewer should compare the actual artifacts, and should receive the scope and source mapping rather than an assurance that everything is already correct.
