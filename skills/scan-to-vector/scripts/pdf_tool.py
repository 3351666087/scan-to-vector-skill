#!/usr/bin/env python3
"""Local PDF inspection, contact sheets, and conservative structural auditing.

Python >= 3.10; dependencies: PyMuPDF and Pillow. Page numbers in reports are
one-based, while explicitly named ``*_index`` fields are zero-based. Exit codes:
0 = report produced (warnings permitted), 1 = audit found issues, 2 = command
could not complete. Reports go to both --out and stdout; errors are JSON on stderr.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import unquote, urlsplit

try:
    import pymupdf
except ImportError:
    pymupdf = None


SCHEMA_VERSION = "1.0"
LOW_TEXT_THRESHOLD = 20
BOUNDARY_TOLERANCE_PT = 2.0
MAX_EXTERNAL_BYTES = 128 * 1024 * 1024
MAX_SHEET_PIXELS = 60_000_000
BASE14 = {
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
    "Symbol", "ZapfDingbats",
}
LIMITATIONS = [
    "Structural checks do not verify OCR accuracy, reading order, completeness, "
    "or agreement with a source scan. Visual review is still required.",
    "Text, image, and drawing counts do not establish that a PDF is fully vectorized. "
    "Text can be invisible, and images can be appropriate photographs or illustrations.",
    "Text bounds are extraction metrics with a 2-point tolerance; they do not prove "
    "visual clipping, overlap, legibility, or correct layout.",
    "Font checks inspect page font resources, including resources that may be unused. "
    "An embedded font does not establish correct glyph mapping or rendering.",
    "Link checks do not use the network, execute actions, or recursively audit linked "
    "documents. External files are checked only within an explicit --links-root.",
]


class ToolError(Exception):
    """An expected input, dependency, or output error."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ToolError(message)


def positive_int(value):
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if result < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return result


def safe_json(value):
    """Convert PyMuPDF coordinate objects and non-finite floats to JSON values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): safe_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_json(item) for item in value]
    if pymupdf and isinstance(value, (pymupdf.Point, pymupdf.Rect, pymupdf.Quad)):
        return [safe_json(item) for item in value]
    return str(value)


def encode_json(report):
    return json.dumps(safe_json(report), ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def write_json(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encode_json(report))
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def source_path(value):
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ToolError(f"PDF does not exist or is not a regular file: {path}")
    return path


def output_path(value, source):
    path = Path(value).expanduser().resolve()
    if path == source:
        raise ToolError("--out must not overwrite the input PDF")
    if path.exists() and source.exists() and os.path.samefile(path, source):
        raise ToolError("--out must not overwrite the input PDF")
    return path


def open_pdf(path):
    try:
        document = pymupdf.open(path)
    except Exception as exc:
        raise ToolError(f"Cannot open PDF: {path}: {exc}") from exc
    if not document.is_pdf or document.needs_pass or document.page_count == 0:
        reason = ("not a PDF" if not document.is_pdf else
                  "password required" if document.needs_pass else "PDF has no pages")
        document.close()
        raise ToolError(f"Cannot inspect {path}: {reason}")
    return document


def link_record(link, page_number=None):
    kind = link.get("kind", 0)
    names = {0: "none", 1: "goto", 2: "uri", 3: "launch", 4: "named", 5: "gotor"}
    result = {"kind": names.get(kind, "unknown"), "kind_id": kind}
    if page_number is not None:
        result["source_page"] = page_number
    for key in ("xref", "from", "file", "uri", "name", "nameddest", "to", "zoom"):
        if key in link:
            result["rect" if key == "from" else key] = safe_json(link[key])
    if "page" in link:
        index = link["page"]
        result["target_page_index"] = index
        result["target_page"] = index + 1 if isinstance(index, int) and index >= 0 else None
    return result


def font_inventory(document):
    """Collect font resources and their extractable embedded programs once per font."""
    found = {}
    for page_index in range(document.page_count):
        for entry in document.get_page_fonts(page_index, full=True):
            xref, extension, font_type, basefont, resource, encoding = entry[:6]
            key = (xref, basefont, font_type)
            if key not in found:
                record = {
                    "xref": xref, "name": basefont, "type": font_type,
                    "extension": extension, "encoding": encoding,
                    "standard_base14": re.sub(r"^[A-Z]{6}\+", "", basefont) in BASE14,
                    "embedded": None, "embedding": "unknown", "embedded_bytes": 0,
                    "pages": [], "resource_names": [],
                }
                try:
                    extracted = document.extract_font(xref)
                    program = extracted[3] if len(extracted) > 3 else b""
                    if program:
                        record.update(embedded=True, embedding="font_program", embedded_bytes=len(program))
                    elif font_type == "Type3" and document.xref_get_key(xref, "CharProcs")[0] != "null":
                        record.update(embedded=True, embedding="type3_glyph_programs")
                    else:
                        record.update(embedded=False, embedding="not_embedded")
                except Exception as exc:
                    record["check_error"] = str(exc)
                found[key] = record
            record = found[key]
            if page_index + 1 not in record["pages"]:
                record["pages"].append(page_index + 1)
            if resource not in record["resource_names"]:
                record["resource_names"].append(resource)
    return list(found.values())


def original_file_spec(document, record):
    # get_links() URI-escapes and normalizes some file specifications. Preserve
    # the PDF's actual filename, including spaces and file:// / https:// schemes.
    if record["kind"] == "gotor" and record.get("xref"):
        for key in ("A/F/UF", "A/F/F", "A/F"):
            value_type, value = document.xref_get_key(record["xref"], key)
            if value_type == "string":
                record["file"] = value
                break
    return record


def page_links(document, page, page_number):
    records = [link_record(link, page_number) for link in page.get_links()]
    for record in records:
        original_file_spec(document, record)
    seen = {record.get("xref") for record in records}
    # MuPDF may omit a broken GoTo annotation entirely from get_links(). Inspect
    # its raw destination so an out-of-range target cannot silently disappear.
    for xref, annotation_type, _ in page.annot_xrefs():
        if annotation_type != pymupdf.PDF_ANNOT_LINK or xref in seen:
            continue
        action = document.xref_get_key(xref, "A/S")[1]
        destination_type, destination = document.xref_get_key(xref, "A/D")
        if destination_type == "null":
            destination_type, destination = document.xref_get_key(xref, "Dest")
        if action not in ("/GoTo", "null") or destination_type == "null":
            records.append({"kind": "unknown", "kind_id": -1, "source_page": page_number,
                            "xref": xref, "extraction_incomplete": True})
            continue
        record = {"kind": "goto", "kind_id": 1, "source_page": page_number, "xref": xref,
                  "raw_destination": destination, "extraction_incomplete": True}
        match = re.match(r"\[\s*(\d+)(?:\s+(\d+)\s+R)?", destination)
        if match:
            value = int(match.group(1))
            if match.group(2) is not None:
                index = next((i for i in range(document.page_count) if document.page_xref(i) == value), -2)
            else:
                index = value
            record.update(target_page_index=index, target_page=index + 1 if index >= 0 else None)
        elif destination_type in ("name", "string"):
            record["nameddest"] = destination.lstrip("/") if destination_type == "name" else destination
        records.append(record)
    return records


def collect(document, source):
    pages = []
    links = []
    for index, page in enumerate(document):
        text = page.get_text("text")
        links_on_page = page_links(document, page, index + 1)
        links.extend(links_on_page)
        pages.append({
            "page": index + 1,
            "width_pt": page.rect.width, "height_pt": page.rect.height,
            "rotation": page.rotation,
            "text_chars": len(text),
            "non_whitespace_text_chars": sum(not char.isspace() for char in text),
            "image_count": len(page.get_image_info()),
            "vector_drawing_count": len(page.get_drawings()),
            "font_xrefs": sorted({font[0] for font in page.get_fonts(full=True)}),
            "link_count": len(links_on_page),
        })
    bookmarks = []
    for level, title, page_number, destination in document.get_toc(simple=False):
        bookmarks.append({"level": level, "title": title, "page": page_number if page_number > 0 else None,
                          "destination": original_file_spec(document, link_record(destination))})
    fonts = font_inventory(document)
    return {
        "schema_version": SCHEMA_VERSION, "command": "inspect", "source": str(source),
        "page_count": document.page_count, "page_numbers": "one-based; *_index is zero-based",
        "summary": {
            "text_chars": sum(page["text_chars"] for page in pages),
            "image_count": sum(page["image_count"] for page in pages),
            "vector_drawing_count": sum(page["vector_drawing_count"] for page in pages),
            "font_count": len(fonts), "link_count": len(links), "bookmark_count": len(bookmarks),
        },
        "pages": pages, "fonts": fonts, "links": links, "bookmarks": bookmarks,
        "count_definitions": {
            "text_chars": "Characters in extracted page text, including whitespace; not an OCR quality score.",
            "image_count": "Displayed image occurrences, including inline images; repeated uses count separately.",
            "vector_drawing_count": "Extracted vector drawing paths; text is counted separately.",
            "fonts": "Page font resources, which may include unused fonts.",
        },
    }


def add_finding(report, severity, code, message, **details):
    report[severity].append({"code": code, "message": message, **safe_json(details)})


def check_text(document, report):
    # Disable CID fallback: otherwise unknown Unicode may appear as an unrelated
    # character rather than U+FFFD and escape this audit.
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES & ~pymupdf.TEXT_CID_FOR_UNKNOWN_UNICODE
    for index, page in enumerate(document):
        # Extract unrotated text coordinates beyond the visible page as well.
        bounds = pymupdf.Rect(0, 0, page.cropbox.width, page.cropbox.height)
        allowed = bounds + (-BOUNDARY_TOLERANCE_PT, -BOUNDARY_TOLERANCE_PT,
                            BOUNDARY_TOLERANCE_PT, BOUNDARY_TOLERANCE_PT)
        blocks = page.get_text("dict", flags=flags, clip=pymupdf.INFINITE_RECT())["blocks"]
        spans = [span for block in blocks for line in block.get("lines", [])
                 for span in line.get("spans", []) if span.get("text", "").strip()]
        replacement_count = sum(span["text"].count("\ufffd") for span in spans)
        if replacement_count:
            add_finding(report, "issues", "replacement_character", "Extracted text contains U+FFFD.",
                        page=index + 1, count=replacement_count)
        for span in spans:
            rect = pymupdf.Rect(span["bbox"])
            if not allowed.contains(rect):
                add_finding(report, "issues", "text_out_of_bounds",
                            "Extracted text metrics extend beyond the visible page bounds.",
                            page=index + 1, bbox=list(rect), page_bounds=list(bounds),
                            text_excerpt=span["text"][:160])
        if report["pages"][index]["non_whitespace_text_chars"] < LOW_TEXT_THRESHOLD:
            add_finding(report, "warnings", "low_text_page",
                        "Page has little extractable text; inspect whether this is intentional.",
                        page=index + 1,
                        non_whitespace_text_chars=report["pages"][index]["non_whitespace_text_chars"],
                        threshold=LOW_TEXT_THRESHOLD)


def named_page(document, name):
    if not isinstance(name, str) or not name:
        return None
    try:
        entry = document.resolve_names().get(name, {})
        page = entry.get("page")
        return page if isinstance(page, int) and page >= 0 else None
    except Exception:
        return None


def check_internal(document, report, record, context):
    index = record.get("target_page_index")
    if index is None or index == -1:
        name = record.get("nameddest") or record.get("name") or record.get("to")
        index = named_page(document, name)
        if index is None:
            add_finding(report, "warnings", "internal_destination_unresolved",
                        "The internal named or unspecified destination could not be resolved.", **context)
            return {**context, "status": "not_checked", "kind": "goto"}
    if not isinstance(index, int) or not 0 <= index < document.page_count:
        add_finding(report, "issues", "internal_target_out_of_range",
                    "Internal destination refers to a page outside this PDF.",
                    target_page_index=index, page_count=document.page_count, **context)
        return {**context, "status": "invalid", "kind": "goto", "target_page_index": index}
    return {**context, "status": "valid", "kind": "goto", "target_page": index + 1}


def local_link_path(raw, source):
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        return None
    # Do not reinterpret foreign drive / UNC paths as ordinary local filenames.
    if re.match(r"^[A-Za-z]:[\\/]", raw) or raw.startswith(("\\\\", "//")):
        return None
    parts = urlsplit(raw)
    if parts.scheme:
        if parts.scheme.lower() != "file" or parts.netloc not in ("", "localhost"):
            return None
        raw = unquote(parts.path)
    path = Path(raw)
    return path if path.is_absolute() else source.parent / path


def read_confined(path, root):
    """Read a regular file beneath root without following symlinks during open.

    Resolve permitted in-root symlinks first; then use descriptor-relative opens
    with O_NOFOLLOW for every path component to prevent a resolve/open race.
    """
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError("Target resolves outside --links-root") from exc
    if not relative.parts:
        raise IsADirectoryError("Link target is a directory")
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise NotImplementedError("Secure descriptor-relative file opening is unavailable")
    directory = None
    file_descriptor = None
    try:
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        for component in relative.parts[:-1]:
            next_directory = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=directory)
            os.close(directory)
            directory = next_directory
        file_descriptor = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                  dir_fd=directory)
        file_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("External link target is not a regular file")
        if file_stat.st_size > MAX_EXTERNAL_BYTES:
            raise OverflowError("External target exceeds the 128 MiB inspection limit")
        with os.fdopen(file_descriptor, "rb") as handle:
            file_descriptor = None
            data = handle.read(MAX_EXTERNAL_BYTES + 1)
        if len(data) > MAX_EXTERNAL_BYTES:
            raise OverflowError("External target exceeds the 128 MiB inspection limit")
        return resolved, data
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        if directory is not None:
            os.close(directory)


def external_info(path, root, cache):
    # Cache only metadata. No linked documents or file handles survive this call.
    cache_key = str(path)
    if cache_key in cache:
        return cache[cache_key]
    try:
        resolved, data = read_confined(path, root)
        with pymupdf.open(stream=data, filetype="pdf") as linked:
            if not linked.is_pdf:
                raise ValueError("External target is not a PDF")
            if linked.needs_pass:
                result = {"status": "not_checked", "code": "external_password_required",
                          "message": "External PDF requires a password.", "path": str(resolved)}
            else:
                try:
                    names = linked.resolve_names()
                except Exception:
                    names = {}
                result = {"status": "opened", "page_count": linked.page_count,
                          "names": names, "path": str(resolved)}
    except PermissionError as exc:
        result = {"status": "not_checked", "code": "external_target_blocked", "message": str(exc)}
    except (NotImplementedError, OverflowError) as exc:
        result = {"status": "not_checked", "code": "external_target_not_checked", "message": str(exc)}
    except FileNotFoundError:
        result = {"status": "invalid", "code": "external_file_missing", "message": "External PDF does not exist."}
    except Exception as exc:
        result = {"status": "invalid", "code": "external_file_unreadable", "message": f"Cannot read external PDF: {exc}"}
    cache[cache_key] = result
    return result


def check_external(record, report, source, root, cache, context):
    result = {**context, "kind": "gotor", "file": record.get("file"), "status": "not_checked"}
    if root is None:
        add_finding(report, "warnings", "external_file_not_checked",
                    "Supply --links-root to check local external PDF destinations.", **result)
        return result
    target = local_link_path(record.get("file"), source)
    if target is None:
        add_finding(report, "warnings", "external_target_not_local",
                    "Destination is not a supported local file; no network access was attempted.", **result)
        return result
    info = external_info(target, root, cache)
    if info["status"] != "opened":
        result["status"] = info["status"]
        add_finding(report, "issues" if info["status"] == "invalid" else "warnings",
                    info["code"], info["message"], **result)
        return result
    result.update(path=info["path"], target_page_count=info["page_count"])
    index = record.get("target_page_index")
    if index is None or index == -1:
        name = record.get("nameddest") or record.get("name") or record.get("to")
        entry = info["names"].get(name, {}) if isinstance(name, str) else {}
        index = entry.get("page")
        if not isinstance(index, int) or index < 0:
            add_finding(report, "warnings", "external_destination_unresolved",
                        "Local PDF opened, but its named destination could not be resolved.", **result)
            return result
    result["target_page_index"] = index
    if not isinstance(index, int) or not 0 <= index < info["page_count"]:
        result["status"] = "invalid"
        add_finding(report, "issues", "external_target_out_of_range",
                    "External destination refers to a page outside its target PDF.", **result)
    else:
        result.update(status="valid", target_page=index + 1)
    return result


def audit(document, source, root):
    report = collect(document, source)
    report.update(command="audit", issues=[], warnings=[], link_checks=[],
                  links_root=str(root) if root is not None else None,
                  limitations=LIMITATIONS,
                  thresholds={"low_text_non_whitespace_chars": LOW_TEXT_THRESHOLD,
                              "text_bounds_tolerance_pt": BOUNDARY_TOLERANCE_PT})
    check_text(document, report)
    for font in report["fonts"]:
        if font["embedded"] is False:
            add_finding(report, "warnings",
                        "font_not_embedded_base14" if font["standard_base14"] else "font_not_embedded",
                        "Font program is not embedded; rendering depends on a viewer's substitute font.",
                        font_xref=font["xref"], font_name=font["name"], pages=font["pages"])
        elif font["embedded"] is None:
            add_finding(report, "warnings", "font_embedding_unknown",
                        "Font embedding could not be determined.", font_xref=font["xref"],
                        font_name=font["name"], pages=font["pages"])
    candidates = [(record, {"source_page": record["source_page"], "link_xref": record.get("xref")})
                  for record in report["links"]]
    candidates.extend((bookmark["destination"], {"bookmark_index": index + 1, "title": bookmark["title"]})
                      for index, bookmark in enumerate(report["bookmarks"]))
    cache = {}
    for record, context in candidates:
        if record["kind"] == "goto" or (record["kind"] == "named" and record.get("nameddest")):
            check = check_internal(document, report, record, context)
        elif record["kind"] == "gotor":
            check = check_external(record, report, source, root, cache, context)
        else:
            check = {**context, "kind": record["kind"], "status": "not_checked"}
            if record.get("extraction_incomplete"):
                add_finding(report, "warnings", "link_extraction_incomplete",
                            "A link annotation could not be interpreted; review its action manually.", **context)
        report["link_checks"].append(check)
    report["summary"].update(issue_count=len(report["issues"]), warning_count=len(report["warnings"]))
    report["status"] = "issues_found" if report["issues"] else "no_structural_issues_found"
    return report


def contacts(document, source, output, thumb_width, columns, rows):
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise ToolError("Pillow is required for contact sheets. Install Pillow.") from exc
    if not 80 <= thumb_width <= 2000 or columns > 20 or rows > 20:
        raise ToolError("contacts requires 80 <= --thumb-width <= 2000 and --columns/--rows <= 20")
    margin, label_height = 12, 24
    thumb_height = math.ceil(thumb_width * math.sqrt(2))
    cell_width, cell_height = thumb_width + margin, thumb_height + label_height + margin
    sheet_width, sheet_height = columns * cell_width + margin, rows * cell_height + margin
    if sheet_width * sheet_height > MAX_SHEET_PIXELS:
        raise ToolError("Contact sheet exceeds the 60-million-pixel safety limit; use smaller dimensions")
    output.mkdir(parents=True, exist_ok=True)
    batch_size = columns * rows
    manifest = {"schema_version": SCHEMA_VERSION, "command": "contacts", "source": str(source),
                "page_count": document.page_count, "page_numbers": "one-based",
                "output_dir": str(output), "manifest": str(output / "contacts.json"),
                "thumbnail_box": {"width": thumb_width, "height": thumb_height},
                "columns": columns, "rows": rows, "sheets": []}
    for first in range(0, document.page_count, batch_size):
        last = min(first + batch_size, document.page_count)
        destination = output / f"contact-{first + 1:04d}-{last:04d}.png"
        output_path(destination, source)
        used_rows = math.ceil((last - first) / columns)
        height = used_rows * cell_height + margin
        with Image.new("RGB", (sheet_width, height), "#e6e6e6") as sheet:
            draw = ImageDraw.Draw(sheet)
            for index in range(first, last):
                page = document[index]
                scale = min(thumb_width / page.rect.width, thumb_height / page.rect.height)
                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale),
                                         colorspace=pymupdf.csRGB, alpha=False)
                with Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples) as thumbnail:
                    thumbnail.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
                    column, row = (index - first) % columns, (index - first) // columns
                    x = margin + column * cell_width + (thumb_width - thumbnail.width) // 2
                    y = margin + row * cell_height
                    sheet.paste(thumbnail, (x, y))
                    draw.rectangle((x, y, x + thumbnail.width - 1, y + thumbnail.height - 1), outline="#b3b3b3")
                    draw.text((margin + column * cell_width, y + thumb_height + 5),
                              f"Page {index + 1}", fill="#202020")
            sheet.save(destination, format="PNG")
        manifest["sheets"].append({"file": str(destination), "first_page": first + 1,
                                   "last_page": last, "pages": list(range(first + 1, last + 1)),
                                   "width": sheet_width, "height": height})
    output_path(output / "contacts.json", source)
    write_json(output / "contacts.json", manifest)
    return manifest


def build_parser():
    parser = Parser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=Parser)
    for command in ("inspect", "contacts", "audit"):
        child = subparsers.add_parser(command)
        child.add_argument("pdf", help="Local input PDF")
        child.add_argument("--out", required=True, help="JSON path, or directory for contacts")
        if command == "contacts":
            child.add_argument("--thumb-width", type=positive_int, default=300)
            child.add_argument("--columns", type=positive_int, default=4)
            child.add_argument("--rows", type=positive_int, default=4)
        if command == "audit":
            child.add_argument("--links-root", help="Only check external PDFs confined to this directory")
    return parser


def main(argv=None):
    try:
        args = build_parser().parse_args(argv)
        if pymupdf is None:
            raise ToolError("PyMuPDF is required. Install PyMuPDF and Pillow.")
        pymupdf.TOOLS.mupdf_display_errors(False)
        pymupdf.TOOLS.mupdf_display_warnings(False)
        source = source_path(args.pdf)
        output = output_path(args.out, source)
        root = None
        if args.command == "audit" and args.links_root is not None:
            root = Path(args.links_root).expanduser().resolve()
            if not root.is_dir():
                raise ToolError("--links-root must be an existing directory")
        with open_pdf(source) as document:
            if args.command == "inspect":
                report = collect(document, source)
            elif args.command == "audit":
                report = audit(document, source, root)
            else:
                report = contacts(document, source, output, args.thumb_width, args.columns, args.rows)
        if args.command != "contacts":
            write_json(output, report)
        sys.stdout.write(encode_json(report))
        return 1 if args.command == "audit" and report["issues"] else 0
    except Exception as exc:
        sys.stderr.write(encode_json({"schema_version": SCHEMA_VERSION, "status": "error", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
