"""End-to-end check of the one-command draft on synthetic pages with known ground truth.

Needs the `tesseract` command; skipped without it."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "skills/scan-to-vector/scripts/draft.py"
sys.path.insert(0, str(ROOT / "bench"))


@unittest.skipUnless(shutil.which("tesseract"), "tesseract is not installed")
class DraftTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def draft(self, kind, seed, hard=False):
        from generate import make  # noqa: E402
        from score import score  # noqa: E402
        page = self.root / f"{kind}-{seed}"
        make(kind, seed, page, hard)
        work, pdf = self.root / "work", self.root / "out/rebuilt.pdf"
        subprocess.run([sys.executable, str(DRAFT), str(page / "scan.jpg"), "--out", str(work), "--pdf", str(pdf)],
                       capture_output=True, text=True)
        self.assertTrue(pdf.exists(), "draft wrote no PDF")
        return work, score(page, pdf)

    def test_flowchart_is_traced_into_vectors(self):
        work, result = self.draft("flowchart", 7)
        shapes = json.loads((work / "p01/draft.json").read_text())["shapes"]
        self.assertTrue(shapes, "no diagram shapes were traced")
        self.assertGreater(result["score"], 0.95)
        self.assertEqual(result["raster"], 0.0)

    def test_report_and_proofreading_sheet(self):
        work, result = self.draft("worksheet", 3, hard=True)
        report = (work / "report.md").read_text()
        self.assertIn("## p01:", report)
        self.assertIn("proofread", report)
        self.assertGreater(result["text_f1"], 0.85)

    def test_fixes_json_corrects_a_word(self):
        work, _ = self.draft("article", 5)
        probe = json.loads((work / "p01/probe.json").read_text())
        (work / "p01/fixes.json").write_text(json.dumps({"words": {"0.0": "Corrected"}}))
        subprocess.run([sys.executable, str(DRAFT), "--rebuild", str(work), "--pdf", str(self.root / "out/rebuilt.pdf")],
                       capture_output=True, text=True)
        import pymupdf
        text = pymupdf.open(self.root / "out/rebuilt.pdf")[0].get_text()
        self.assertIn("Corrected", text)
        self.assertNotEqual(probe["lines"][0]["words"][0]["text"], "Corrected")


if __name__ == "__main__":
    unittest.main()
