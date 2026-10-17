<p align="center">
  <img src="assets/hero.svg" width="100%" alt="扫描光束扫过 1847 年 Byrne《几何原本》的扫描页，页面被干净的矢量重建版取代；放大对比显示扫描件的 JPEG 像素与清晰的矢量字形。">
</p>

<h1 align="center">scan-to-vector · 扫描件重绘技能</h1>

<p align="center">
  <b>把扫描的书籍、手册、练习册和图表重建为可搜索、图形为矢量的 PDF，并逐页对照原稿核验。</b><br>
  适用于 Claude Code、Codex 以及任何能读取 <code>SKILL.md</code> 的 agent。
</p>

<p align="center">
  <a href="README.md">English</a> · 简体中文
</p>

<p align="center">
  <img alt="Agent Skill" src="https://img.shields.io/badge/Agent%20Skill-SKILL.md-2dd4bf?style=flat-square">
  <img alt="Claude Code" src="https://img.shields.io/badge/Claude%20Code-ready-d97757?style=flat-square">
  <img alt="Codex" src="https://img.shields.io/badge/Codex-ready-111827?style=flat-square">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square">
</p>

---

OCR 交给你的是“扫描图 + 一层看不见的文字”。**scan-to-vector 交给你的是重建后的页面**：文字是真文字，能搜索、能复制；图示和图表重绘为矢量路径，怎么放大都清晰；照片和雕版插画保留为干净的裁图，并在交付说明里注明。每一页原稿都登记在台账里，交付前还要把重建结果叠在原稿上逐页核对。

## 演示

两个演示用的都是真实的公有领域扫描件。仓库里的重建 PDF 由 agent 按照 [`SKILL.md`](skills/scan-to-vector/SKILL.md) 完成，所有测量坐标都记录在构建脚本里，你可以自己重新生成。

### Byrne《几何原本》（1847）：文字、彩色几何图、雕版首字母

| | 扫描件（输入） | 重建结果（输出） |
| --- | --- | --- |
| 文件 | [`scan.jpg`](demo/byrne-euclid-I-11/source/scan.jpg)，1920×2519 JPEG，300 KB | [`byrne-euclid-I-11.pdf`](demo/byrne-euclid-I-11/rebuilt/byrne-euclid-I-11.pdf)，80 KB |
| 文字 | 像素 | 可搜索文字，开源 Caslon 字体（Libre Caslon Text） |
| 几何图与行内符号 | 像素 | 82 条矢量路径，位置都在原稿上实测 |
| 雕版首字母 “F” | 像素 | 保留为清理过的光栅裁图，并在台账中注明 |
| 核验 | | 与原稿叠图对照、[逐页台账](demo/byrne-euclid-I-11/ledger.json)、[结构审计](demo/byrne-euclid-I-11/review/audit.json)：0 个问题 |

有两处编辑取舍写进了台账，而不是悄悄处理：长 s（ſ）改为现代的 s，这样 *straight*、*shall* 才搜得到；∴ 和 ⊥ 在正文字体里没有字形，因此用矢量绘制。

### Playfair 贸易图（1786）：图表 → 数据 → 矢量

<p align="center">
  <img src="assets/playfair.svg" width="100%" alt="光标逐年扫过 Playfair 1786 年的图表，光标后的雕版被按还原数据重绘的矢量图取代，右侧面板显示每一年的数值。">
</p>

agent 先标定雕版网格，再追踪两条曲线，把**每条曲线 81 个年度数值**还原到 [`data.csv`](demo/playfair-1786/rebuilt/data.csv)。[重绘的图表](demo/playfair-1786/rebuilt/playfair-1786.pdf)只用这份数据画成，曲线落回雕版原位，并且和原图一样在 1754 年交叉。PDF 里没有任何光栅图片。

## 适合你吗？

| | 加 OCR 文字层（如 OCRmyPDF） | PDF 转 Markdown（如 Marker、MinerU） | **scan-to-vector** |
| --- | --- | --- | --- |
| 产出 | 原扫描图 + 隐藏文字 | Markdown / JSON | 重新排版的 PDF |
| 页面外观 | 与扫描件相同 | 版式丢失 | 干净，贴近原稿 |
| 图示与图表 | 仍是位图 | 抽成图片 | 重绘为矢量；图表数据可还原 |
| 来源追踪与核验 | 无 | 无 | 逐页台账、叠图复核、PDF 审计 |
| 速度 | 几秒 | 几秒到几分钟 | agent 逐页处理 |

如果你只需要在扫描件上加一层可搜索文字，直接用 OCR 文字层，更快也更便宜。需要把页面本身重建出来时再用 scan-to-vector，比如要重新打印的练习册、带插图的手册、老书，或者想把数字找回来的图表。

## 安装

把技能目录复制到你所用 agent 的技能目录即可。

```bash
git clone https://github.com/3351666087/scan-to-vector-skill.git
```

| Agent | 命令 |
| --- | --- |
| Claude Code | `mkdir -p ~/.claude/skills && cp -R scan-to-vector-skill/skills/scan-to-vector ~/.claude/skills/` |
| Codex | `mkdir -p ~/.codex/skills && cp -R scan-to-vector-skill/skills/scan-to-vector ~/.codex/skills/` |
| 其他 | 把 `skills/scan-to-vector/` 复制到客户端加载 Agent Skills 的目录 |

附带的 PDF 辅助脚本需要 Python 3.10+，以及 PyMuPDF 和 Pillow：

```bash
python3 -m pip install -r scan-to-vector-skill/skills/scan-to-vector/requirements.txt
```

技能不捆绑 OCR 和排版引擎。agent 会优先使用项目里已有的工具（Tesseract、LaTeX、HTML 转 PDF 渲染器、PyMuPDF 等），没有的话再按任务选择。

## 使用

用自然语言告诉 agent 即可：

```text
用 $scan-to-vector 把这份扫描练习册重新排版成 PDF。
保留全部题目和答题空白；图表尽量矢量化，照片可以保留。
每页对照原稿检查，交付时说明原稿缺页和无法辨认的地方。
```

```text
用 $scan-to-vector 把这张扫描的统计图还原成 data.csv，并重绘成矢量图。
```

```text
用 $scan-to-vector 接手这个已完成一半的扫描书重建项目。
先检查 checkpoint、逐页台账和最后一次输出，从未完成的页继续。
```

## 工作流程

1. **明确任务**：清点每一页输入，把扫描页序号、印刷页码和输出页码分开记录，并写好 checkpoint，脱离聊天记录也能接着做。
2. **对照原稿校正 OCR**：OCR 只是草稿。阅读顺序、数字、脚注、答题空白都要对照图像校正；拿不准的地方记录下来，不凭空补全。
3. **重建图示与版式**：表格转成文字，图示和图表依据还原出的几何或数据重绘为矢量，照片保留为裁图。
4. **稳定分页与链接**：页码引用以最终渲染结果为准；构建先输出到暂存位置，失败的构建不会覆盖已验证的成果。
5. **核验与交付**：联系表、逐页细查加结构审计，最后附交付说明，写清哪些是矢量、哪些仍是光栅、还有哪些未解决。

细节见 [`SKILL.md`](skills/scan-to-vector/SKILL.md) 和 [`references/`](skills/scan-to-vector/references) 中的分项指南。

## 辅助脚本

`scripts/pdf_tool.py` 提供机械层面的证据：文字、字体、图片、矢量数量和链接。

```bash
python skills/scan-to-vector/scripts/pdf_tool.py inspect  source.pdf  --out work/source.json
python skills/scan-to-vector/scripts/pdf_tool.py contacts rebuilt.pdf --out work/contact-sheets
python skills/scan-to-vector/scripts/pdf_tool.py audit    rebuilt.pdf --out work/audit.json --links-root output
```

审计只能发现结构问题，证明不了 OCR、图表数值或阅读顺序是对的，所以技能要求它始终与对照原稿的人工视觉复核配合使用。

## 复现演示

```bash
python3 -m venv .venv
.venv/bin/pip install -r skills/scan-to-vector/requirements.txt -r demo/requirements.txt
.venv/bin/python demo/byrne-euclid-I-11/rebuilt/build.py
.venv/bin/python demo/playfair-1786/rebuilt/digitize.py      # 扫描图 -> data.csv
.venv/bin/python demo/playfair-1786/rebuilt/build.py         # data.csv -> PDF
.venv/bin/python assets/build_hero.py && .venv/bin/python assets/build_chart_demo.py
```

README 里的动画也由这些文件生成。动画中的重建页把文字转成了轮廓，在任何系统上显示都一致；PDF 本身保留的是真实文字。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

测试会临时生成合成 PDF，不需要真实书籍。

## 局限

- 这是给 agent 用的工作流程，不是一键转换器。重建每页要花几分钟，也会消耗模型额度。
- 审计通过不代表内容正确，技能要求对照原稿复核。
- 保留了照片或雕版插画的结果属于混合内容 PDF，交付说明会写明。
- 删除原稿、对外发布只在你明确要求时进行，技能本身不授予这些权限。

## 致谢与来源

- Oliver Byrne，*The First Six Books of the Elements of Euclid*（1847），扫描件来自 [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:First_six_books_of_the_elements_of_Euclid_1847_Byrne.djvu) / [Internet Archive](https://archive.org/details/firstsixbooksofe00byrn)，公有领域。
- William Playfair，*The Commercial and Political Atlas*（1786），扫描件来自 [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Playfair_TimeSeries-2.png)，公有领域。
- [Libre Caslon Text](https://github.com/thundernixon/Libre-Caslon)，SIL Open Font License（[`demo/fonts/OFL.txt`](demo/fonts/OFL.txt)）。
