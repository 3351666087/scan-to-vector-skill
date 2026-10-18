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
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-22c55e?style=flat-square"></a>
</p>

---

OCR 交给你的是“扫描图 + 一层看不见的文字”。**scan-to-vector 交给你的是重建后的页面**：文字是真文字，能搜索、能复制；图示和图表重绘为矢量路径，怎么放大都清晰；照片和雕版插画保留为干净的裁图，并在交付说明里注明。每一页原稿都登记在台账里，交付前还要把重建结果叠在原稿上逐页核对。

> **用数据说话：** 在两份从未见过的 9 页扫描文档上，我们测试的四个模型用了本技能后得分全部提高：Haiku 5.5 从 0.841 升到 0.997，Sonnet 5.5 用时缩短 37%。[查看评测](#用了它agent-真的更强吗)

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

## 用了它，agent 真的更强吗？

会。我们用四个模型做了对照实验。同一个简短需求（“把这几页扫描件重建成一份干净的 PDF……”），每个模型各做两次：一次不用技能，一次用本技能。测试文档都是技能从未调过参的：练习册、表格、图表、流程图、表单、双栏文章，全部是困难模式，即陌生字体、内容密集，一半是手机斜拍的照片，带阴影、能拍到桌面。每页按真值对文字、版式、图形和矢量比例打分（1.0 为满分）。

**长文档（技能 v6）：两份 9 页文档，共 18 页，16 次运行**

<p align="center">
  <img src="assets/benchmark.svg" width="100%" alt="两份 9 页文档的哑铃图。页面质量（不用 → 用技能）：Haiku 5.5 0.841 → 0.997，Sonnet 5.5 0.994 → 0.998，Opus 5.5 0.993 → 0.998，Fable 5.1 0.837 → 0.997。每份 9 页文档耗时（分钟）：Haiku 9.4 → 9.0，Sonnet 25.7 → 16.2，Opus 13.3 → 14.7，Fable 10.0 → 14.7。">
</p>

| 模型 | 得分（不用 → 用） | 提升的 95% 置信区间 | 逐页好–差 | 最差页 | 每 9 页耗时（分钟） | 每 9 页 token |
| --- | --- | --- | --- | --- | --- | --- |
| Haiku 5.5 | 0.841 → **0.997** | +0.089 至 +0.228 | 17–1 | 0.558 → 0.989 | 9.4 → 9.0 | 239k → 258k |
| Fable 5.1 | 0.837 → **0.997** | +0.118 至 +0.207 | 18–0 | 0.631 → 0.989 | 10.0 → 14.7 | 172k → 251k |
| Sonnet 5.5 | 0.994 → **0.998** | +0.001 至 +0.008 | 6–1 | 0.970 → 0.990 | 25.7 → 16.2 | 370k → 320k |
| Opus 5.5 | 0.993 → **0.998** | +0.002 至 +0.007 | 9–1 | 0.982 → 0.989 | 13.3 → 14.7 | 244k → 283k |

**短任务（技能 v5）：6 组、每组 3 页，共 18 页，48 次运行**

<p align="center">
  <img src="assets/benchmark-short.svg" width="100%" alt="6 组 3 页任务的哑铃图。页面质量（不用 → 用技能）：Haiku 5.5 0.894 → 0.993，Sonnet 5.5 0.994 → 0.996，Opus 5.5 0.994 → 0.994，Fable 5.1 0.904 → 0.992。每 3 页耗时（分钟）：Haiku 4.1 → 6.2，Sonnet 14.4 → 13.4，Opus 7.9 → 8.3，Fable 7.6 → 10.4。">
</p>

| 模型 | 得分（不用 → 用） | 提升的 95% 置信区间 | 逐页好–差 | 最差页 | 每 3 页耗时（分钟） | 每 3 页 token |
| --- | --- | --- | --- | --- | --- | --- |
| Haiku 5.5 | 0.894 → **0.993** | +0.050 至 +0.160 | 16–0 | 0.634 → 0.952 | 4.1 → 6.2 | 133k → 180k |
| Fable 5.1 | 0.904 → **0.992** | +0.050 至 +0.133 | 18–0 | 0.711 → 0.951 | 7.6 → 10.4 | 124k → 187k |
| Sonnet 5.5 | 0.994 → 0.996 | −0.003 至 +0.007 | 4–2 | 0.953 → 0.972 | 14.4 → 13.4 | 215k → 235k |
| Opus 5.5 | 0.994 → 0.994 | −0.005 至 +0.006 | 7–3 | 0.985 → 0.951 | 7.9 → 8.3 | 155k → 188k |

- **长文档上，四个模型用了技能都更好**，而且提升的 95% 置信区间都在零以上。
- **便宜的模型追上来了。** Haiku 和 Fable 自己处理长文档时会顾此失彼：页面比例被拉伸、表格错位、图形缺线，最差页只有 0.56 和 0.63。用了技能后两者都达到 0.997，和 Sonnet、Opus 持平。
- **强模型更快、更稳。** Sonnet 做 9 页文档快了 37%，token 也更少；Sonnet 和 Opus 的最差页都有提升。在 3 页的短任务上它们本来就接近满分，提升落在误差范围内。
- **多花的时间都用在了核对上。** 短任务里 Fable 和 Haiku 用了技能会多花些时间，因为技能要求它们先校对、再对照原稿，确认过才收工。

长文档的耗时数据每个模型只有两份文档，仅供参考。

### 为什么有效

agent 做这类任务时的失败方式是可预测的，技能的每个部分各对付一种。

- **它们看到的是缩小的页面。** 视觉模型读的是缩小后的图，位置、字号和小数字都靠猜。草稿脚本按扫描像素实测一切；拿不准的词裁出来放大，每页汇总到一张校对图上。
- **它们发现不了自己漏了什么。** 每次重建都会叠在原稿上比对，报告逐页给出 PASS 或 FIX，并列出还缺什么、哪里放错了。
- **它们会走最短的路。** 那就让正确的路最短：一条命令起草所有页面，改正一个读错的词只需在 `fixes.json` 里写一行。

### 迭代过程

每个版本都在没调过参的页面上测量，失败案例决定下一版改什么。

- v1（只有说明文字）让 Sonnet 变快了，但没有变好。
- v3 加入一条命令起草全部页面。Haiku 和 Fable 大幅提升，但一个照片比例 bug 让 Sonnet 丢了两页，v4 修复。
- v5 把所有线条、箭头和图表曲线描成矢量，并加入校对图，得到上面的短任务结果。
- v6 修复了那 48 次运行暴露的问题：阴影遮住的照片角点、暗照片上的倾斜校正 bug、分栏阅读顺序、网格线粗细，以及用方形复选框判断纸张尺寸。在 18 页全新测试页上，不经 agent、只看草稿的得分为 0.917（v4）、0.969（v5）、0.989（v6）。上面的长文档结果用的就是 v6。

原始数据见 [`bench/results/`](bench/results)，评测代码见 [`bench/`](bench)。

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

### Claude Code 插件（推荐）

在 Claude Code 会话里运行：

```text
/plugin marketplace add 3351666087/scan-to-vector-skill
/plugin install scan-to-vector@scan-to-vector-skill
```

在终端里，同样的两步是 `claude plugin marketplace add 3351666087/scan-to-vector-skill` 和 `claude plugin install scan-to-vector@scan-to-vector-skill`。以后用 `claude plugin update scan-to-vector@scan-to-vector-skill` 更新。插件里的技能会带上插件名前缀，所以列表里显示为 `scan-to-vector:scan-to-vector`；直接用自然语言提出需求，效果相同。

### Claude Code 和 Codex 一行安装

```bash
curl -fsSL https://raw.githubusercontent.com/3351666087/scan-to-vector-skill/main/install.sh | bash
```

[`install.sh`](install.sh) 会检测本机装了哪些 agent，把技能复制到 `~/.claude/skills` 和/或 `~/.codex/skills`。想自己指定目标，把命令结尾换成 `| bash -s -- --claude`、`--codex` 或 `--dir DIR`（其他客户端的技能目录）。再次运行会更新它装过的副本；你改动过的副本不会被覆盖，除非加上 `--force`，此时旧副本会先移到技能目录旁边的 `skill-backups/`。想先读一遍脚本再运行，可以克隆仓库后执行 `./install.sh`。

插件和 `~/.claude/skills` 里的副本二选一即可，两者都装的话 Claude Code 会列出两个同名技能。

### 手动复制

```bash
git clone https://github.com/3351666087/scan-to-vector-skill.git
```

| Agent | 命令 |
| --- | --- |
| Claude Code | `mkdir -p ~/.claude/skills && cp -R scan-to-vector-skill/skills/scan-to-vector ~/.claude/skills/` |
| Codex | `mkdir -p ~/.codex/skills && cp -R scan-to-vector-skill/skills/scan-to-vector ~/.codex/skills/` |
| 其他 | 把 `skills/scan-to-vector/` 复制到客户端加载 Agent Skills 的目录 |

### Python 依赖

不论用哪种方式安装，技能的脚本都需要 Python 3.10+，以及 PyMuPDF、Pillow、numpy、scipy，OCR 还需要 `tesseract` 命令（缺少时 `install.sh` 会给出提示）：

```bash
python3 -m pip install "PyMuPDF>=1.28.2,<2" "Pillow>=12.3.0" "numpy>=1.26" "scipy>=1.11"
brew install tesseract        # 或：sudo apt install tesseract-ocr
```

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

1. **一条命令起草所有页面。** `draft.py` 把照片拉平、把每页摆正、把光照校匀，用 Tesseract 以双倍分辨率读两遍文字，再按实测的位置、字号和字重把每个词放回原处，并按阅读顺序排列。线条、底纹、柱子和色块直接绘制，其余线条、箭头、轮廓和图表曲线描成矢量图形。
2. **每页一张校对图。** 拿不准的词和还没画出的笔迹会被裁出、放大，连同编号汇总到一张图上。agent 在 `fixes.json` 里改正读错的词；看不清的字绝不瞎猜。
3. **与原稿比对。** 每次重建都叠在原稿上比较。报告逐页给出 PASS 或 FIX，并列出仍缺失的区域；agent 补上后重新构建。
4. **长任务可续做。** 整本书会建逐页台账和 checkpoint，脱离聊天记录也能接着做（[`references/long-documents.md`](skills/scan-to-vector/references/long-documents.md)）。
5. **交付** PDF 和一段简短说明：哪些是文字和矢量，哪些仍是光栅，哪些没有把握。

细节见 [`SKILL.md`](skills/scan-to-vector/SKILL.md) 和 [`references/`](skills/scan-to-vector/references) 中的分项指南。

## 脚本

```bash
S=skills/scan-to-vector/scripts
python $S/draft.py page1.jpg page2.jpg --out work --pdf out/rebuilt.pdf   # 起草、比对、出报告
python $S/draft.py --rebuild work --pdf out/rebuilt.pdf                   # 改完 fixes.json 后重建
python $S/zoom.py work/p01/deskewed.png 100 200 600 500 --grid 50 --out work/zoom.png
python $S/pdf_tool.py audit out/rebuilt.pdf --out work/audit.json
```

比对和审计能找出缺失和结构问题，但证明不了每个词都读对了，所以技能始终要求对照原稿校对。

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

## 复现评测

```bash
.venv/bin/python bench/generate.py --out data --split test --count 3 --seed 9100 --hard   # 18 页带真值的测试页
.venv/bin/python bench/packets.py make --data data/test --size 3 --out packets
# 让你的 agent 对每组各跑两次（用与不用技能），
# 每次输出写到 runs/<arm>/<packet>/out/rebuilt.pdf
.venv/bin/python bench/packets.py score --packets packets --runs runs --arms baseline skill
```

评分脚本（[`bench/score.py`](bench/score.py)）先把重建页与真值对齐，再综合文字 F1、版式墨迹 F1、图形墨迹 F1 和矢量比例。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

测试会临时生成合成页面和 PDF，不需要真实书籍。起草相关的测试需要 `tesseract`，没装时会自动跳过。

## 局限

- 这是给 agent 用的工作流程，不是一键转换器。重建每页要花几分钟，也会消耗模型额度。
- 审计通过不代表内容正确，技能要求对照原稿复核。
- 评测集是合成的：印刷体英文页面，真值已知。手写、密集的雕版画和其他文字更难；Tesseract 默认只认英文，其他语言需要另装语言包。
- 保留了照片或雕版插画的结果属于混合内容 PDF，交付说明会写明。
- 删除原稿、对外发布只在你明确要求时进行，技能本身不授予这些权限。

## 致谢与来源

- Oliver Byrne，*The First Six Books of the Elements of Euclid*（1847），扫描件来自 [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:First_six_books_of_the_elements_of_Euclid_1847_Byrne.djvu) / [Internet Archive](https://archive.org/details/firstsixbooksofe00byrn)，公有领域。
- William Playfair，*The Commercial and Political Atlas*（1786），扫描件来自 [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Playfair_TimeSeries-2.png)，公有领域。
- [Libre Caslon Text](https://github.com/thundernixon/Libre-Caslon)，SIL Open Font License（[`demo/fonts/OFL.txt`](demo/fonts/OFL.txt)）。

## 许可证

代码和文档以 [MIT 许可证](LICENSE) 发布。演示所用扫描件属于公有领域；Libre Caslon Text 字体仍遵循其自身的 SIL Open Font License（[`demo/fonts/OFL.txt`](demo/fonts/OFL.txt)）。
