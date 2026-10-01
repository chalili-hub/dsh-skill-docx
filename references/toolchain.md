# 工具链配方

## 1. 依赖

```
python -m pip install python-docx python-pptx pymupdf matplotlib pillow
```

有 Word 时用 Word COM 导出 PDF（最准）；没有就用 LibreOffice
（`soffice --headless --convert-to pdf`）。

## 2. python-docx 中文字体（最容易踩的坑）

**只设 `run.font.name` 对中文无效**，必须写 `w:rFonts` 的 `w:eastAsia`：

```python
from docx.oxml.ns import qn
def _fix(run, ea="宋体", ascii_f="Times New Roman"):
    run.font.name = ascii_f
    rPr = run._element.get_or_add_rPr()
    rF = rPr.find(qn("w:rFonts")) or rPr.makeelement(qn("w:rFonts"), {})
    if rF.getparent() is None:
        rPr.append(rF)
    rF.set(qn("w:ascii"), ascii_f)
    rF.set(qn("w:hAnsi"), ascii_f)
    rF.set(qn("w:eastAsia"), ea)
```

`scripts/docx_kit.py` 已经把标题(黑体)/正文(宋体)/代码(Consolas)/表格/图注/封面全部封装好，直接调用。

三套字体建议：标题 **黑体**，正文 **宋体**，代码 **Consolas**。

## 3. 代码块底纹

```python
pPr = p._element.get_or_add_pPr()
sh = OxmlElement("w:shd"); sh.set(qn("w:val"), "clear"); sh.set(qn("w:fill"), "F5F5F5")
pPr.append(sh)
```

一行一个段落（不要用 `\n` 在单段落里换行，底纹和行距会不准）。
字号 8~8.5pt，行距 1.0，末行留一点 space_after。

## 4. 表格

- `style = "Table Grid"`，表头单元格加 `w:shd` 底纹（`DCE6F1`）。
- 通过 `cell.width` 设列宽，宽度之和 ≈ 正文宽度（A4 左右边距各 2.6cm → 约 15.8cm）。
- 数字/十六进制用等宽字体：
  `str(txt).startswith("0x")` 或纯 8 位十六进制串就判为数值列。

## 5. 图片

```python
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.add_run().add_picture(path, width=Cm(15.8))   # 满宽；小图用 Cm(13)
```
满宽 15.8cm 的图在 A4 上观感最好；三行小图（如寄存器变化）用 13cm。

## 6. 渲染校验（必做）

```
python scripts/verify_docx.py 报告.docx 预览目录 [--pages 1,5,9,13]
```

流程：Word COM / LibreOffice 转 PDF → PyMuPDF 栅格化 → 输出 PNG 路径。
然后**用 read_image 真的看几张**：封面、表格密集页、图片页、末页。
这一步能抓到字体没生效、图片溢出页边、表格断行、页码错位等所有问题。

Word COM 片段（脚本已封装）：

```powershell
$w = New-Object -ComObject Word.Application; $w.Visible = $false
$d = $w.Documents.Open($doc, $false, $true)     # ReadOnly
$d.ExportAsFixedFormat($pdf, 17)                # 17 = wdExportFormatPDF
$d.Close(0); $w.Quit()
```

## 7. 常见运行环境坑

| 现象 | 处理 |
| --- | --- |
| `print` 中文报 gbk 错 | 写 UTF-8 文件再读；不要往控制台打中文 |
| `json.load` 报 `Unexpected UTF-8 BOM` | PowerShell `Set-Content -Encoding UTF8` 会写 BOM。读 JSON/CSV/TSV 一律用 `encoding="utf-8-sig"`（同时兼容有/无 BOM） |
| Windows PowerShell 5.1 里中文乱码 | 控制台默认 GBK 且不会自动切 UTF-8，同一份 UTF-8 文件可能"看起来"是乱码（`read` 工具读却是好的）。判断文件是否真损坏：`[Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($f))` 并检查有无 U+FFFD |
| 调 HTTP API 发含中文的 JSON body 变成 `?` | PS 5.1 的 `Invoke-RestMethod -Body <字符串>` 不按 UTF-8 编码。必须传字节数组：`-Body ([Text.Encoding]::UTF8.GetBytes($json)) -ContentType 'application/json; charset=utf-8'` |
| matplotlib 中文方框 | 见 writing.md：含中文的文本别用 `family="monospace"` |
| matplotlib `tight_layout` 警告 | 改用 `fig.subplots_adjust(left=..., right=..., top=..., bottom=...)` 显式给边距（长 y 标签需要更宽的左边距） |
| docx 打开提示"内容有问题" | 检查是否用了非法 XML 元素顺序（`w:shd` 必须在 `pPr` 内的正确位置附近，追加到末尾通常安全） |

## 8. 交付物组织

```
<工作目录>/
├── <课程>-<实验名>-实验报告.docx      ← 交付主件，放顶层
├── 实验材料/                          ← 配套材料
│   ├── README.md                      ← 内容说明 + 目标机路径 + 复现命令 + 关键结论速查
│   ├── 波形图/                        ← 所有图（可直接插入 PPT/论文）
│   ├── 波形文件/                      ← 原始数据（VCD/CSV），可复核
│   ├── 源码/                          ← 本次编写的源文件
│   ├── 数据/                          ← 逐周期表、反汇编、readelf 等
│   └── 脚本/                          ← 解析/绘图/报告生成脚本
```

README 必须写：各目录内容、**目标机上的产物路径**、**一键复现命令**、**关键结论速查表**、
以及用户自己需要补的项。

清理：中间工作目录（如 `_vmio/`）在交付前删除或并入 `实验材料/`，不要在用户目录里留一堆 `_extract.py`、`_req.txt` 之类的临时文件。
