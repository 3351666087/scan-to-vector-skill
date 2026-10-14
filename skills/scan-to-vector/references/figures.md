# Figures, diagrams, and crops

## Choose the representation by content

| Source region | Reconstruction | Verify against the source |
| --- | --- | --- |
| Chart | SVG or renderer-native paths/text from explicit data | Values, axis ranges, tick spacing, legend, units, category/color mapping. |
| Table | Text cells with vector borders | Row/column associations, spans, totals, alignment, footnotes. |
| Map or process diagram | Paths, shapes, editable labels | Relative placement, connectivity, orientation, arrow targets, label association. |
| Crossword or grid | Explicit rows/columns and cell types | Dimensions, blocked cells, numbering, intersections, original empty answer cells. |
| Form or answer sheet | Text and vector lines/boxes | Number of fields, labels, usable writing space, line weight. |
| Photograph or complex illustration | Source crop at sufficient effective resolution | Crop bounds, caption, detail, adjacent content accidentally included. |

Trace semantic structure before applying a new visual style. A more attractive chart with different values or a map with the wrong path is an incorrect reconstruction. Store recoverable numerical data and geometry separately from rendering code where useful.

## Cropping

Define crop rectangles in a known coordinate system. Keep both the source region and its intended display size. Include full labels, descenders, subtitles, and edges; inspect the resulting crop at its final size. Automatic whitespace trimming can cut pale lines or the last row of a caption, so support explicit bounds and bypass trimming where needed.

When a diagram mixes a schematic background and complex illustrations, separate clean raster regions from vector geometry only if their alignment remains dependable in the production renderer. Otherwise retain the composite region and disclose the raster portion.

## Renderer compatibility

Test SVGs through the engine that produces the deliverable, not only a browser or image preview. Clip paths, masks, filters, transparency, text positioning, and embedded images can behave differently across engines. Reduce unsupported effects to simple paths and explicit coordinates when needed, then compare the production output again.

Embedding a bitmap in SVG does not make it vector. Text converted to outlines is vector but may not be searchable or accessible as text. Keep body copy as extractable text, choose compatible fonts, and describe diagram text separately when outlining is necessary.

## Useful visual checks

- Read every label and confirm which object it belongs to.
- Count cells, fields, arrows, series, and plotted categories against the source.
- Check boundaries and legends at the final print scale, not only while zoomed in.
- Inspect light rules, handwriting spaces, and checkbox outlines in a full-page render.
- Keep answer spaces unfilled when the source is a worksheet.

Complete the figure only after both its semantics and its production rendering have been reviewed.
