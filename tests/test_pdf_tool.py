"""Synthetic, temporary PDF integration tests; no source books are used."""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pymupdf
from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "skills/scan-to-vector/scripts/pdf_tool.py"


class PDFToolTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.input = self.root / "input.pdf"
        self.report = self.root / "report.json"

    def make_pdf(self, path=None, pages=1, text="A synthetic document with enough extractable text.",
                 embedded=False, rotation=0):
        path = path or self.input
        with pymupdf.open() as document:
            for index in range(pages):
                page = document.new_page(width=300, height=400)
                fontname = "helv"
                if embedded:
                    fontname = "custom"
                    page.insert_font(fontname=fontname, fontbuffer=pymupdf.Font("helv").buffer)
                if text:
                    page.insert_text((25, 50), text, fontsize=9, fontname=fontname)
                page.set_rotation(rotation)
            document.save(path)
        return path

    def run_cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        if expected == 2:
            self.assertEqual(result.stdout, "")
            report = json.loads(result.stderr)
            self.assertEqual(report["status"], "error")
            self.assertTrue(report["error"])
        else:
            self.assertEqual(result.stderr, "")
            report = json.loads(result.stdout)
            self.assertEqual(report["schema_version"], "1.0")
        return report

    def audit(self, *, expected=0, root=None):
        args = ["audit", self.input, "--out", self.report]
        if root is not None:
            args.extend(["--links-root", root])
        report = self.run_cli(*args, expected=expected)
        self.assertEqual(report, json.loads(self.report.read_text(encoding="utf-8")))
        return report

    def codes(self, report, severity):
        return {finding["code"] for finding in report[severity]}

    def add_links(self, links):
        with pymupdf.open(self.input) as document:
            for offset, link in enumerate(links):
                document[0].insert_link({"from": pymupdf.Rect(25, 70 + offset * 22, 150, 85 + offset * 22), **link})
            document.saveIncr()

    def test_inspect_counts_fonts_bookmarks_links_and_json_file(self):
        self.make_pdf(pages=2)
        with pymupdf.open(self.input) as document:
            page = document[0]
            page.draw_rect(pymupdf.Rect(20, 100, 80, 160), color=(1, 0, 0))
            with Image.new("RGB", (8, 8), "blue") as image:
                stream = io.BytesIO()
                image.save(stream, format="PNG")
            page.insert_image(pymupdf.Rect(120, 100, 160, 140), stream=stream.getvalue())
            page.insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(20, 200, 100, 220), "page": 1})
            document.set_toc([[1, "Synthetic chapter", 2]])
            document.saveIncr()
        report = self.run_cli("inspect", self.input, "--out", self.report)
        self.assertEqual(report, json.loads(self.report.read_text(encoding="utf-8")))
        self.assertEqual(report["page_count"], 2)
        self.assertGreater(report["pages"][0]["text_chars"], 20)
        self.assertEqual(report["pages"][0]["image_count"], 1)
        self.assertEqual(report["pages"][0]["vector_drawing_count"], 1)
        self.assertEqual(report["pages"][1]["image_count"], 0)
        self.assertEqual(report["summary"]["link_count"], 1)
        self.assertEqual(report["links"][0]["target_page"], 2)
        self.assertEqual(report["bookmarks"][0]["title"], "Synthetic chapter")
        self.assertEqual(report["fonts"][0]["pages"], [1, 2])
        self.assertFalse(report["fonts"][0]["embedded"])

    def test_contacts_cover_every_page_and_save_valid_images(self):
        self.make_pdf(pages=5)
        output = self.root / "sheets"
        report = self.run_cli("contacts", self.input, "--out", output,
                              "--thumb-width", 100, "--columns", 2, "--rows", 2)
        self.assertEqual([sheet["pages"] for sheet in report["sheets"]], [[1, 2, 3, 4], [5]])
        self.assertEqual(report, json.loads((output / "contacts.json").read_text(encoding="utf-8")))
        for sheet in report["sheets"]:
            with Image.open(sheet["file"]) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (sheet["width"], sheet["height"]))
                # A label occupies the strip below the first thumbnail box.
                strip = image.crop((12, 12 + report["thumbnail_box"]["height"], 100,
                                    12 + report["thumbnail_box"]["height"] + 24))
                self.assertLess(strip.getextrema()[0][0], 80)
                strip.close()
        self.assertLess(report["sheets"][1]["height"], report["sheets"][0]["height"])

    def test_contacts_mixed_orientation(self):
        with pymupdf.open() as document:
            for width, height in [(1200, 100), (100, 1200), (300, 400)]:
                document.new_page(width=width, height=height)
            document.save(self.input)
        report = self.run_cli("contacts", self.input, "--out", self.root / "mixed",
                              "--thumb-width", 120, "--columns", 3, "--rows", 1)
        self.assertEqual(report["sheets"][0]["pages"], [1, 2, 3])

    def test_warnings_do_not_fail_audit_and_limitations_are_explicit(self):
        self.make_pdf(text="Short")
        report = self.audit()
        self.assertEqual(report["issues"], [])
        self.assertIn("low_text_page", self.codes(report, "warnings"))
        self.assertIn("font_not_embedded_base14", self.codes(report, "warnings"))
        self.assertTrue(any("OCR accuracy" in item for item in report["limitations"]))
        self.assertTrue(any("fully vectorized" in item for item in report["limitations"]))

    def test_embedded_font_and_rotated_page(self):
        self.make_pdf(embedded=True, rotation=90)
        report = self.audit()
        self.assertTrue(report["fonts"][0]["embedded"])
        self.assertGreater(report["fonts"][0]["embedded_bytes"], 0)
        self.assertEqual(report["issues"], [])
        self.assertNotIn("font_not_embedded", self.codes(report, "warnings"))

    def test_out_of_bounds_text_is_reported_even_outside_page_clip(self):
        self.make_pdf()
        with pymupdf.open(self.input) as document:
            document[0].insert_text((290, 100), "This extends beyond the edge", fontsize=12)
            document.saveIncr()
        report = self.audit(expected=1)
        findings = [issue for issue in report["issues"] if issue["code"] == "text_out_of_bounds"]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["page"], 1)
        self.assertGreater(findings[0]["bbox"][2], 300)

    def test_replacement_character_in_synthetic_font_mapping(self):
        self.make_pdf(text="abc", embedded=True)
        with pymupdf.open(self.input) as document:
            font_xref = document.get_page_fonts(0)[0][0]
            unicode_xref = int(document.xref_get_key(font_xref, "ToUnicode")[1].split()[0])
            document.update_stream(unicode_xref, b"""/CIDInit /ProcSet findresource begin
12 dict begin begincmap
/CIDSystemInfo <</Registry(Adobe)/Ordering(UCS)/Supplement 0>> def
/CMapName /Synthetic def /CMapType 2 def
1 begincodespacerange <0000> <FFFF> endcodespacerange
3 beginbfchar <0042> <FFFD> <0043> <0062> <0044> <0063> endbfchar
endcmap CMapName currentdict /CMap defineresource pop end end""")
            document.saveIncr()
        report = self.audit(expected=1)
        self.assertIn("replacement_character", self.codes(report, "issues"))
        issue = next(item for item in report["issues"] if item["code"] == "replacement_character")
        self.assertEqual(issue["count"], 1)

    def test_internal_links_and_bookmarks_checked(self):
        self.make_pdf(pages=2)
        self.add_links([{"kind": pymupdf.LINK_GOTO, "page": 1}])
        with pymupdf.open(self.input) as document:
            document.set_toc([[1, "Destination", 2]])
            document.saveIncr()
        report = self.audit()
        self.assertEqual(len(report["link_checks"]), 2)
        self.assertTrue(all(check["status"] == "valid" for check in report["link_checks"]))

    def test_broken_internal_link_not_silently_dropped_by_extractor(self):
        self.make_pdf(pages=2)
        self.add_links([{"kind": pymupdf.LINK_GOTO, "page": 1}])
        with pymupdf.open(self.input) as document:
            xref = document[0].get_links()[0]["xref"]
            document.xref_set_key(xref, "A/D", "[99 /Fit]")
            document.saveIncr()
        report = self.audit(expected=1)
        self.assertIn("internal_target_out_of_range", self.codes(report, "issues"))
        self.assertEqual(report["summary"]["link_count"], 1)

    def test_unresolved_internal_named_destination_gets_warning(self):
        self.make_pdf(pages=2)
        self.add_links([{"kind": pymupdf.LINK_GOTO, "page": 1}])
        with pymupdf.open(self.input) as document:
            xref = document[0].get_links()[0]["xref"]
            document.xref_set_key(xref, "A/D", "(MissingDestination)")
            document.saveIncr()
        report = self.audit()
        self.assertIn("internal_destination_unresolved", self.codes(report, "warnings"))
        self.assertEqual(report["link_checks"][0]["status"], "not_checked")

    def test_internal_named_destination_is_resolved(self):
        self.make_pdf(pages=2)
        self.add_links([{"kind": pymupdf.LINK_GOTO, "page": 1}])
        with pymupdf.open(self.input) as document:
            xref = document[0].get_links()[0]["xref"]
            destination = f"[{document.page_xref(1)} 0 R /XYZ 0 400 0]"
            document.xref_set_key(document.pdf_catalog(), "Names",
                                  f"<< /Dests << /Names [(Found) {destination}] >> >>")
            document.xref_set_key(xref, "A/D", "(Found)")
            document.saveIncr()
        report = self.audit()
        self.assertNotIn("internal_destination_unresolved", self.codes(report, "warnings"))
        self.assertEqual(report["link_checks"][0]["status"], "valid")
        self.assertEqual(report["link_checks"][0]["target_page"], 2)

    def test_external_local_targets_and_page_ranges(self):
        self.make_pdf()
        self.make_pdf(self.root / "target.pdf", pages=2)
        self.add_links([
            {"kind": pymupdf.LINK_GOTOR, "file": "target.pdf", "page": 1},
            {"kind": pymupdf.LINK_GOTOR, "file": "target.pdf", "page": 5},
            {"kind": pymupdf.LINK_GOTOR, "file": "missing.pdf", "page": 0},
        ])
        report = self.audit(expected=1, root=self.root)
        self.assertEqual([check["status"] for check in report["link_checks"]], ["valid", "invalid", "invalid"])
        self.assertIn("external_target_out_of_range", self.codes(report, "issues"))
        self.assertIn("external_file_missing", self.codes(report, "issues"))
        self.assertEqual(report["link_checks"][0]["target_page"], 2)

    def test_external_file_is_not_opened_without_explicit_root(self):
        self.make_pdf()
        self.add_links([{"kind": pymupdf.LINK_GOTOR, "file": "missing.pdf", "page": 0}])
        report = self.audit()
        self.assertIn("external_file_not_checked", self.codes(report, "warnings"))
        self.assertEqual(report["issues"], [])

    def test_external_path_traversal_and_symlink_escape_are_blocked(self):
        confined = self.root / "allowed"
        confined.mkdir()
        outside = self.root / "outside.pdf"
        outside.write_bytes(b"Not a PDF. This file must not be opened.")
        self.input = confined / "input.pdf"
        self.make_pdf()
        (confined / "escape.pdf").symlink_to(outside)
        (confined / "escape-directory").symlink_to(self.root, target_is_directory=True)
        self.add_links([
            {"kind": pymupdf.LINK_GOTOR, "file": "../outside.pdf", "page": 0},
            {"kind": pymupdf.LINK_GOTOR, "file": "escape.pdf", "page": 0},
            {"kind": pymupdf.LINK_GOTOR, "file": "escape-directory/outside.pdf", "page": 0},
        ])
        report = self.audit(root=confined)
        self.assertEqual(report["issues"], [])
        blocked = [warning for warning in report["warnings"] if warning["code"] == "external_target_blocked"]
        self.assertEqual(len(blocked), 3)
        self.assertTrue(all(check["status"] == "not_checked" for check in report["link_checks"]))

    def test_symlink_to_target_within_root_is_allowed(self):
        self.make_pdf()
        target = self.make_pdf(self.root / "target.pdf")
        (self.root / "alias.pdf").symlink_to(target)
        self.add_links([{"kind": pymupdf.LINK_GOTOR, "file": "alias.pdf", "page": 0}])
        report = self.audit(root=self.root)
        self.assertEqual(report["link_checks"][0]["status"], "valid")

    def test_nonlocal_destinations_never_fetch_network(self):
        self.make_pdf()
        self.add_links([
            {"kind": pymupdf.LINK_URI, "uri": "https://example.invalid/"},
            {"kind": pymupdf.LINK_GOTOR, "file": "https://example.invalid/target.pdf", "page": 0},
        ])
        report = self.audit(root=self.root)
        self.assertEqual(report["link_checks"][0]["kind"], "uri")
        self.assertEqual(report["link_checks"][0]["status"], "not_checked")
        self.assertIn("external_target_not_local", self.codes(report, "warnings"))

    def test_corrupt_external_target_is_an_issue(self):
        self.make_pdf()
        (self.root / "broken.pdf").write_bytes(b"not a pdf")
        self.add_links([{"kind": pymupdf.LINK_GOTOR, "file": "broken.pdf", "page": 0}])
        report = self.audit(expected=1, root=self.root)
        self.assertIn("external_file_unreadable", self.codes(report, "issues"))

    def test_missing_corrupt_nonpdf_and_encrypted_inputs_fail_as_json(self):
        self.run_cli("inspect", self.input, "--out", self.report, expected=2)
        self.input.write_bytes(b"not a PDF")
        self.run_cli("inspect", self.input, "--out", self.report, expected=2)
        with Image.new("RGB", (10, 10), "red") as image:
            image.save(self.root / "image.png")
        self.run_cli("inspect", self.root / "image.png", "--out", self.report, expected=2)
        self.input.unlink()
        with pymupdf.open() as document:
            document.new_page()
            document.save(self.input, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                          owner_pw="owner", user_pw="reader")
        self.run_cli("audit", self.input, "--out", self.report, expected=2)

    def test_invalid_arguments_and_output_conflicts_fail_as_json(self):
        self.make_pdf()
        for arguments in [[], ["inspect", self.input], ["unknown"],
                          ["contacts", self.input, "--out", self.root / "sheets", "--columns", "0"],
                          ["contacts", self.input, "--out", self.root / "sheets", "--rows", "many"],
                          ["contacts", self.input, "--out", self.root / "sheets", "--thumb-width", "79"],
                          ["contacts", self.input, "--out", self.root / "sheets", "--columns", "100"],
                          ["audit", self.input, "--out", self.report, "--links-root", self.root / "missing"],
                          ["inspect", self.input, "--out", self.input]]:
            with self.subTest(arguments=arguments):
                self.run_cli(*arguments, expected=2)
        with pymupdf.open(self.input) as document:
            self.assertEqual(document.page_count, 1)


if __name__ == "__main__":
    unittest.main()
