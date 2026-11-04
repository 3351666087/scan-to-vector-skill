"""End-to-end check of the one-command draft on synthetic pages with known ground truth.

Needs the `tesseract` command; skipped without it. The Chinese page also needs Tesseract's
chi_sim data (apt install tesseract-ocr-chi-sim / brew install tesseract-lang)."""

from __future__ import annotations

from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "skills/scan-to-vector/scripts/draft.py"
sys.path.insert(0, str(ROOT / "bench"))
sys.path.insert(0, str(ROOT / "skills/scan-to-vector/scripts"))

CHINESE = [  # (size in pt, text): a heading and body text, no Latin letters, digits or spaces
    (18, "扫描页面重建为矢量文档"),
    (12, "本工具把扫描的纸质页面重新排版为清晰的矢量文档，"),
    (12, "保留原来的版式，文字可以搜索和复制。"),
    (12, "国家统计局发布的数据显示，今年前三季度经济运行总体平稳。"),
    (12, "第一章介绍中国人口与经济发展的概况，共计十二节。"),
    (12, "这是一个用于测试光学字符识别效果的段落，包含常见汉字。"),
]


def tesseract_langs():
    if not shutil.which("tesseract"):
        return set()
    res = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
    return {l.strip() for l in (res.stdout + res.stderr).splitlines()[1:] if l.strip()}


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


@unittest.skipUnless("chi_sim" in tesseract_langs(), "tesseract has no chi_sim language data")
class ChineseDraftTests(unittest.TestCase):
    """--lang chi_sim+eng (experimental): a printed Chinese page comes back as embedded,
    unspaced Chinese text at the scan's size."""

    def test_chinese_page(self):
        import pymupdf
        from canvas import CJK_CLASS
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = pymupdf.open()
            page = doc.new_page(width=612, height=792)
            page.insert_font(fontname="cjk", fontbuffer=pymupdf.Font("cjk").buffer)
            y = 100
            for size, text in CHINESE:
                page.insert_text((72, y), text, fontname="cjk", fontsize=size)
                y += size * 2.2
            page.get_pixmap(dpi=200, colorspace=pymupdf.csRGB, alpha=False).save(root / "scan.jpg", jpg_quality=85)
            work, pdf = root / "work", root / "out/rebuilt.pdf"
            res = subprocess.run([sys.executable, str(DRAFT), str(root / "scan.jpg"), "--lang", "chi_sim+eng",
                                  "--out", str(work), "--pdf", str(pdf)], capture_output=True, text=True)
            self.assertTrue(pdf.exists(), res.stderr[-2000:])
            probe = json.loads((work / "p01/probe.json").read_text())
            draft = json.loads((work / "p01/draft.json").read_text())
            cmp = json.loads((work / "p01/compare/compare.json").read_text())
            out = pymupdf.open(pdf)
            text = out[0].get_text()
            fonts = out[0].get_fonts(full=True)

        truth = "".join(t for _, t in CHINESE)
        self.assertGreater(SequenceMatcher(None, truth, "".join(text.split())).ratio(), 0.9, text)
        for phrase in ("保留原来的版式，文字可以搜索和复制。", "国家统计局发布的数据显示"):
            self.assertIn(phrase, text)
        self.assertIsNone(re.search(f"[{CJK_CLASS}] +[{CJK_CLASS}]", text), f"spaces between characters: {text!r}")
        self.assertTrue(fonts)
        for f in fonts:
            self.assertNotEqual(f[1], "n/a", f"font not embedded: {f}")
        self.assertIn("Droid Sans Fallback", " ".join(f[3] for f in fonts))
        body = sorted(l["size_px"] for l in probe["lines"] if len(l["text"]) > 15)
        self.assertTrue(body)
        self.assertAlmostEqual(body[len(body) // 2], 12 * 200 / 72, delta=0.06 * 12 * 200 / 72)
        self.assertGreater(cmp["ink_f1"], 0.9)
        self.assertEqual(probe["checkboxes"], [])                   # 国 and 口 stay text
        self.assertIn(draft["font"], ("serif", "sans"))


if __name__ == "__main__":
    unittest.main()
