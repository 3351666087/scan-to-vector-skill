"""Chinese text without Tesseract: the canvas fallback face, spacing, the CJK size calibration,
character cells and text comparison."""

from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pymupdf
from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/scan-to-vector/scripts"))

from canvas import CJK_ASCENT, CJK_DESCENT, Canvas, join_words, side_bearings  # noqa: E402
from compare import tokens  # noqa: E402
from probe import JunkFilter, cjk_cells, cjk_lang, measure_line, small_shapes  # noqa: E402

COMMON = "的一是不了人我在有他这中大来上国个到说们为子和你地出道也时年得就那要下以生会自着去之过家学对可她里后小么心多天而能好都然没日于起还发成事只作当想看文无开手十用主行方又如前所本见经头面公同三已老从动两长知民样现分将外但身些与高意进把法此实回二理美点月明其种声全工己话儿者向情部正名定女问力机给等几很业最间新什打便位因重被走电四第门相次东政海口使教西再平真听世气信北少关并内加化由却代军产入先山五太水万市眼体别处总才场师书比住员九笑性通目华报立马命张活难神数件安表原车白应路期叫死常提感金何更反合放做系计或司利受光王果亲界及今京务制解各任至清物台象记边共风战干接它许八特觉望直服毛林题建南度统色字请交爱让认算论百吃义科怎元社术结六功指思非流每青管夫连远资队跟带花快条院变联言权往展该领传近留红治决周保达办运武半候七必城父强步完革深区即求品士转量空甚众技轻程告江语英基派满式李息写呢识极令黄德收脸钱党倒未持取设始版双历越史商千片容研像找友孩站广改议形委早房音火际则首单据导影失拿网香似斯专石若兵弟谁校读志飞观争究包组造落视济喜离虽坏兴切团故料且局乐吧值"


def pdf_of(canvas):
    """The canvas saved and reopened, as the deliverable would be."""
    with tempfile.TemporaryDirectory() as tmp:
        path = canvas.save(Path(tmp) / "page.pdf")
        return pymupdf.open("pdf", path.read_bytes())


def render_line(text, size_px, x=40, baseline=120, width=1400, height=200):
    """A line of text drawn in the fallback face as a 72-dpi raster scan (1 px = 1 pt)."""
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    page.insert_font(fontname="cjk", fontbuffer=pymupdf.Font("cjk").buffer)
    page.insert_text((x, baseline), text, fontname="cjk", fontsize=size_px)
    pix = page.get_pixmap(colorspace=pymupdf.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width) < 150


class FallbackTests(unittest.TestCase):
    def test_chinese_is_drawn_in_an_embedded_font(self):
        c = Canvas(1000, 400)
        c.text(50, 100, "中文扫描", 40, font="serif")
        c.text(50, 200, "English and 中文", 40, font="sans")
        doc = pdf_of(c)
        fonts = doc[0].get_fonts(full=True)
        fallback = [f for f in fonts if "Droid Sans Fallback" in f[3]]
        self.assertEqual(len(fallback), 1, fonts)
        self.assertEqual(fallback[0][1], "ttf")            # a font program, not a name to look up
        self.assertEqual(fallback[0][2], "Type0")
        self.assertNotIn("Heiti", " ".join(f[3] for f in fonts))
        self.assertLess(len(doc.tobytes()), 60_000, "the fallback face should be subset")
        text = doc[0].get_text()
        self.assertIn("中文扫描", text)
        self.assertIn("English and 中文", text)

    def test_chinese_text_is_visible_where_it_was_placed(self):
        c = Canvas(600, 200, page_width_pt=600)
        c.text(100, 120, "中文", 60)
        pix = pdf_of(c)[0].get_pixmap(colorspace=pymupdf.csGRAY, alpha=False)
        ink = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width) < 128
        ys, xs = np.nonzero(ink)
        self.assertTrue(len(xs), "nothing was drawn")
        self.assertAlmostEqual(xs.min(), 100 + side_bearings("中")[0] * 60, delta=2)
        self.assertAlmostEqual(xs.max() + 1, 220 - side_bearings("文")[1] * 60, delta=2)   # two 60 px cells
        self.assertAlmostEqual(ys.max() + 1, 120 + CJK_DESCENT * 60, delta=2)

    def test_latin_text_alone_does_not_embed_the_fallback(self):
        c = Canvas(600, 200)
        c.text_width("中文", 30)                            # measured, never drawn
        c.text(50, 100, "Plain English", 30)
        doc = pdf_of(c)
        self.assertEqual([f[3] for f in doc[0].get_fonts(full=True)], ["Times-Roman"])
        self.assertLess(len(doc.tobytes()), 20_000)

    def test_punctuation_outside_latin1_is_not_a_dot(self):
        c = Canvas(800, 200)
        c.text(50, 100, "don’t “quote” a—b", 30)          # Base14 text can only be Latin-1
        text = pdf_of(c)[0].get_text()
        self.assertIn("don’t “quote” a—b", text)
        self.assertNotIn("·", text)

    def test_text_width_counts_the_fallback_glyphs(self):
        c = Canvas(600, 200)
        self.assertAlmostEqual(c.text_width("中文", 50), 100, delta=0.5)
        self.assertAlmostEqual(c.text_width("ab中", 50), c.text_width("ab", 50) + 50, delta=0.5)

    def test_stretched_mixed_text_keeps_its_runs_in_order(self):
        c = Canvas(1000, 200, page_width_pt=1000)
        width = 1.2 * c.text_width("AB中文CD", 40, font="sans")
        right = c.text(100, 120, "AB中文CD", 40, font="sans", width=width)
        self.assertAlmostEqual(right, 100 + width, delta=0.5)
        words = pdf_of(c)[0].get_text("words")
        self.assertEqual([w[4] for w in words], ["AB中文CD"])
        self.assertAlmostEqual(words[0][2], 100 + width, delta=3)    # the runs end where the fit says

    def test_a_registered_font_can_be_the_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            ttf = Path(tmp) / "mine.ttf"
            ttf.write_bytes(pymupdf.Font("cjk").buffer)
            c = Canvas(600, 200)
            c.add_font("mine", ttf, fallback=True)
            c.text(50, 100, "Mixed 中文", 30)
            doc = pdf_of(c)
        names = {f[4] for f in doc[0].get_fonts(full=True)}
        self.assertIn("mine", names)
        self.assertNotIn("fallback", names)
        self.assertIn("Mixed 中文", doc[0].get_text())


class SpacingTests(unittest.TestCase):
    def line(self, c, *words, size=40):
        """A probe.json line laid out as a scan would have it; "␣" marks a measured blank."""
        out, x = [], 100
        for text in words:
            gap = text.startswith("␣")
            text = text.lstrip("␣")
            x += 10 if gap else 0
            w = {"text": text, "conf": 95.0, "box": [x, 60, round(x + c.text_width(text, size, font="sans")), 100]}
            if gap:
                w["space_before"] = True
            out.append(w)
            x = w["box"][2] + (0 if all(ord(ch) > 0x2E7F for ch in text) else 10)
        return {"words": out, "baseline": 96, "size_px": size}

    def test_no_space_between_chinese_words(self):
        c = Canvas(1600, 200, page_width_pt=1600)
        c.place_lines([self.line(c, "本", "工具", "把", "扫描", "的", "页面", "。")], font="sans")
        text = pdf_of(c)[0].get_text().strip()
        self.assertEqual(text, "本工具把扫描的页面。")

    def test_spaces_stay_around_latin_and_measured_gaps(self):
        c = Canvas(1600, 200, page_width_pt=1600)
        c.place_lines([self.line(c, "测试", "Python", "3.12", "与", "中文", "␣第二", "节", "（", "注", "）")], font="sans")
        text = pdf_of(c)[0].get_text().strip()
        self.assertEqual(text, "测试 Python 3.12 与中文 第二节（注）")

    def test_english_lines_are_unchanged(self):
        c = Canvas(1600, 200, page_width_pt=1600)
        c.place_lines([self.line(c, "Plain", "English", "text.")], font="sans")
        self.assertEqual(pdf_of(c)[0].get_text(), "Plain English text. \n")

    def test_join_words(self):
        self.assertEqual(join_words(["中", "文", "and", "English", "，", "好"]), "中文 and English，好")
        self.assertEqual(join_words(["see", "（", "注", "）", "here"]), "see（注）here")
        self.assertEqual(join_words([{"text": "第一章"}, {"text": "总则", "space_before": True}]), "第一章 总则")
        self.assertEqual(join_words(["two", "words"]), "two words")

    def test_compare_counts_chinese_per_character(self):
        self.assertEqual(tokens("本工具 Python3 把，"), ["本", "工", "具", "Python3", "把", "，"])
        self.assertEqual(tokens("plain English words"), ["plain", "English", "words"])

    def test_which_languages_are_cjk(self):
        for lang in ("chi_sim", "chi_sim+eng", "eng+chi_tra", "jpn", "script/HanS"):
            self.assertTrue(cjk_lang(lang), lang)
        for lang in (None, "", "eng", "deu+fra", "kor"):
            self.assertFalse(cjk_lang(lang), lang)


class CalibrationTests(unittest.TestCase):
    def test_ink_ratios_match_the_fallback_face(self):
        font = ImageFont.truetype(io.BytesIO(pymupdf.Font("cjk").buffer), 1000)
        up, down = [], []
        for ch in COMMON:
            x0, top, x1, bottom = font.getbbox(ch, anchor="ls")
            up.append(-top / 1000)
            down.append(bottom / 1000)
        self.assertAlmostEqual(float(np.median(up)), CJK_ASCENT, delta=0.01)
        self.assertAlmostEqual(float(np.median(down)), CJK_DESCENT, delta=0.01)

    def test_measured_size_and_baseline(self):
        for size in (30, 44, 61):
            ink = render_line("保留原来的版式文字可以搜索和复制", size, baseline=150, height=240)
            line = {"box": [40, 150 - int(0.85 * size), 40 + 16 * size, 150 + int(0.1 * size)],
                    "words": [{"text": "保留原来的版式文字可以搜索和复制", "conf": 95.0,
                               "box": [40, 150 - int(0.85 * size), 40 + 16 * size, 150 + int(0.1 * size)]}]}
            measure_line(ink, line)
            self.assertAlmostEqual(line["size_px"], size, delta=0.05 * size, msg=f"size {size}")
            self.assertAlmostEqual(line["baseline"], 150, delta=2, msg=f"size {size}")
            self.assertFalse(line["italic"])


class CellTests(unittest.TestCase):
    def ocr_words(self, chars, size, x=40, baseline=120, drift=0.0):
        """Words as Tesseract boxes them: one per character, each `drift` em further off."""
        out = []
        for i, ch in enumerate(chars):
            x0 = x + (i + i * drift) * size
            out.append({"text": ch, "conf": 95.0, "box": [int(x0), int(baseline - 0.8 * size), int(x0 + 0.6 * size),
                                                      int(baseline + 0.1 * size)]})
        return out

    def test_loose_boxes_are_redrawn_on_the_characters(self):
        text, size = "本工具把扫描的纸质页面重新排版为清晰的矢量文档，", 39
        ink = render_line(text, size)
        words = cjk_cells(self.ocr_words(text, size, drift=0.03), ink)
        for i, w in enumerate(words):
            self.assertTrue(w.get("cell"), w)
            self.assertAlmostEqual(w["box"][0], 40 + i * size, delta=2, msg=w["text"])
            self.assertAlmostEqual(w["box"][2], 40 + (i + 1) * size, delta=2, msg=w["text"])

    def test_a_space_between_characters_is_found(self):
        size = 40
        ink = render_line("第一章　总则共计十二节", size)              # ideographic space after 章
        words = self.ocr_words("第一章", size) + self.ocr_words("总则共计十二节", size, x=40 + 4 * size)
        cjk_cells(words, ink)
        self.assertTrue(words[3].get("space_before"))
        self.assertAlmostEqual(words[3]["box"][0], 40 + 4 * size, delta=2)
        self.assertAlmostEqual(words[-1]["box"][2], 40 + 11 * size, delta=2)
        self.assertEqual(join_words(words), "第一章 总则共计十二节")

    def test_latin_words_keep_their_boxes(self):
        size = 40
        ink = render_line("测试", size)
        latin = {"text": "Python", "conf": 96.0, "box": [140, 92, 250, 128]}
        words = cjk_cells(self.ocr_words("测试", size) + [latin], ink)
        self.assertEqual(latin["box"], [140, 92, 250, 128])
        self.assertNotIn("cell", latin)
        self.assertAlmostEqual(words[1]["box"][2], 40 + 2 * size, delta=2)

    def test_han_characters_are_not_tick_boxes(self):
        size = 40
        ink = render_line("中国人口回田", size)
        self.assertTrue(small_shapes(ink, size, [])[0], "the test needs box-like characters")
        words = cjk_cells(self.ocr_words("中国人口回田", size), ink)
        boxes, circles = small_shapes(ink, size, [{"words": words}])
        self.assertEqual(boxes, [])
        self.assertEqual(circles, [])

    def test_loosely_boxed_han_characters_are_not_junk(self):
        size = 40
        ink = render_line("本工具一把扫描的纸质页面", size)
        words = self.ocr_words("本工具一把扫描的纸质页面", size)
        thin = {"text": "一", "conf": 95.0, "box": [160, 101, 199, 104]}         # 一 is a single stroke
        tall = {"text": "把", "conf": 93.0, "box": [200, 70, 230, 155]}          # boxed two lines tall
        junk = JunkFilter(ink, words)
        self.assertFalse(junk(thin))
        self.assertFalse(junk(tall))
        self.assertTrue(junk(dict(thin, text="-")), "a Latin sliver is still junk")


if __name__ == "__main__":
    unittest.main()
