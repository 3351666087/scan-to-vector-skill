# Rendering, references, and release

## A representative build first

Use the current project renderer or an available PDF/typesetting engine suited to the layout. This workflow does not require one particular renderer. Confirm font coverage, tables, figures, margins, and page breaks in a small production build before transcribing a whole document into a new format.

Retain fonts according to their licensing and embed the glyphs needed by the document. Check unsupported glyphs, phonetics, math, and replacement characters. A font name in PDF metadata does not by itself establish embedding or complete glyph coverage.

Keep headings with following content, captions with figures, and short tasks with their answer spaces. Apply keep-together rules to the smallest useful block. Keeping an entire long section together can create blank pages or overflow. Look for nearly empty tail pages, orphan borders, split rubrics, and headings stranded at the bottom.

## Page references follow content

Store references by document ID and semantic target ID until rendering. Use source-page IDs for broad source provenance; use object IDs for references to a specific chart, exercise, table, or section. When one source page expands into two output pages, its start anchor may be an incorrect target for an object on the second page.

Derive final page numbers from the renderer's actual layout/destinations. Resolve internal links, contents, bookmarks, and cross-document links from that mapping. Keep related output filenames stable and verify relative PDF links with both files in the delivery directory. Page numbers in reader APIs may be zero-based even when visible numbering is one-based; convert at a single documented boundary.

If resolving references changes pagination, repeat layout and compare the map until stable; bound the attempts and report an unresolved cycle. Reject a stale map from an earlier build.

### Boundary anchors: a production failure pattern

Invisible page markers can land on the preceding page even when the visible heading has flowed to the next one. A border or spacer can remain behind while a label moves. Therefore inspect the *visible target* as well as the recorded destination, especially at section starts.

In one HTML-to-PDF pipeline, the reliable repair was to attach the ID to the visible heading/label while retaining an empty layout placeholder at the original marker position. Globally adding keep-with-next to every source marker, or moving marker boxes around headings, changed pagination elsewhere. Treat this as a diagnostic pattern, not a universal CSS patch: reproduce it in the actual renderer and compare affected page boundaries after any repair.

## Atomic builds

1. Render into a fresh staging directory or unique pending filename.
2. Check the renderer's exit status. Confirm the newly produced file exists, has nonzero size, and opens as a PDF.
3. Write the corresponding page map and build record into the same staging area. Record hashes of the PDFs so the map can be tied to exact artifacts.
4. Run mechanical and visual verification on these staged files.
5. Publish the verified PDF, page map, and dependent documents as one consistent release. An atomic directory rename is useful where supported; otherwise promote only after the entire set passes and write the release manifest last.

Use argument arrays and checked subprocesses in build scripts. Resolve paths from the project, not a particular machine. If a renderer fails, retain the last verified deliverable and mark the new build failed; its old PDF is not evidence that the new build succeeded.

## Final review matrix

| Evidence | Passing condition |
| --- | --- |
| Source ledger | Every physical input page has exactly one reviewed disposition; omissions and duplicate consolidation match scope. |
| Text | Body text extracts sensibly; uncertainties, intentional errors, and source gaps are handled explicitly. |
| Figures | Values, topology, labels, grids, and answer spaces match the scan. |
| Assets/fonts | Required assets load; characters display correctly; embedding and raster regions are understood. |
| Layout | Every output page reviewed; dense details checked at readable scale; no clipped content or unusable writing spaces. |
| Navigation | IDs resolve; displayed page references, bookmark destinations, and local cross-document links target the intended visible content. |
| Release | PDFs open, hashes match the release record, and mappings belong to the delivered build. |

The bundled audit reports object-level evidence: extractable text, drawing/image counts, font metadata, text bounds, replacement characters, and link destinations. Low-text pages need inspection, not automatic rejection. An answer sheet may contain mostly vector lines; an image-only scanned page can also have a hidden OCR layer. Neither case can be judged from counts alone. Mechanical bounds checks cannot see all clipped vector paths or text hidden by an overlapping object.

Check missing assets and raw/unexpanded markup in the source or rendered content according to the project's syntax. Confirm numeric references visually even when their link destinations are technically valid.

After repairing a local content issue, review the affected range. After pagination, renderer, or shared-style changes, rebuild and revalidate the resulting mappings and layout. Stop expanding tests once the required checks pass and no new changes or unresolved findings justify more work.

## Delivery note

State the delivered files, page counts, what was reconstructed as text/vector artwork, which regions remain raster, missing source pages, and any unresolved readings. Include reproducibility details when editable sources are part of the requested delivery. Keep originals recoverable unless the user specifically authorized cleanup; perform authorized cleanup only after the final outputs are verified.
