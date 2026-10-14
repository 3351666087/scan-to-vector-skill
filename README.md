# Scan to Vector · 扫描件重绘技能

把扫描书籍、手册、练习册和表单重建为可搜索、重新排版的 PDF：正文使用真实文字，适合重绘的图表使用矢量对象，照片和复杂插画按需保留为清晰裁图。

这是给 agent 使用的工作流程与质检工具，**不是一键 OCR 转换器**。它把实际长文档重建中的经验组织成可检查、可暂停续做的步骤。

## 能做什么

- 逐页登记来源，区分扫描页序号、印刷页码与输出页码。
- 对照扫描图校正 OCR、栏序、表格、题号和特殊字符。
- 重绘图表、地图、网格和表单，并核对数据、连接关系和标签。
- 处理分页、书内/跨文件引用、字体、图片裁切和生产渲染器兼容问题。
- 生成联系表和 PDF 结构审计，配合逐页视觉验收与可恢复的交接记录。

正文位于 [`skills/scan-to-vector/SKILL.md`](skills/scan-to-vector/SKILL.md)，分支细节在 `references/`。通用脚本不含任何教材原文、扫描图、私人聊天或捆绑字体。

## 安装

将 `skills/scan-to-vector/` 整个目录复制到支持 Agent Skills 的客户端技能目录。以下以 Codex 为例（已有同名技能时先保留你的修改）：

```sh
git clone https://github.com/3351666087/scan-to-vector-skill.git
mkdir -p ~/.codex/skills
cp -R scan-to-vector-skill/skills/scan-to-vector ~/.codex/skills/
cd scan-to-vector-skill
```

`SKILL.md` 与参考文档不依赖特定客户端；`agents/openai.yaml` 是可选的 Codex UI 元数据。使用其他客户端时，放到该客户端支持的技能目录即可。

运行辅助脚本需要 Python 3.10+。在项目自己的虚拟环境安装依赖：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r skills/scan-to-vector/requirements.txt
.venv/bin/python skills/scan-to-vector/scripts/pdf_tool.py --help
```

OCR 和排版引擎沿用项目现有工具或由 agent 按任务选用；它们不由此脚本安装。

## 使用示例

```text
用 $scan-to-vector 把这份扫描练习册重新排版成 PDF。
保留全部题目和答题空白；图表尽量矢量化，照片可以保留。
每页对照原稿检查，交付时说明原稿缺页和无法辨认的地方。
```

```text
用 $scan-to-vector 接手这个已完成一半的扫描书重建项目。
先检查 checkpoint、逐页台账和最后一次输出，从未完成的页继续。
```

辅助脚本示例：

```sh
.venv/bin/python skills/scan-to-vector/scripts/pdf_tool.py inspect source.pdf --out work/source.json
.venv/bin/python skills/scan-to-vector/scripts/pdf_tool.py contacts rebuilt.pdf --out work/contact-sheets
.venv/bin/python skills/scan-to-vector/scripts/pdf_tool.py audit rebuilt.pdf --out work/audit.json --links-root output
```

结构审计不能证明 OCR、图表数据或阅读顺序正确，也不能代替视觉检查。技能要求同时核对源页台账、渲染效果和链接实际落点。含保留照片的结果应准确称为混合内容 PDF。

## 验证

自动测试使用临时生成的合成 PDF，不依赖真实书籍：

```sh
.venv/bin/python -m unittest discover -s tests -v
```

源文件清理与远程发布只按当次用户要求执行。使用此技能不会自动获得删除、上传或发布用户文档的授权。
