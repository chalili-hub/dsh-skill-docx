# dsh-skill-docx

一个 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (DSH) 技能：**按实验要求真实完成实验，并产出可交付的实验报告 Word 文档**。

面向硬件 / 嵌入式 / 计算机体系结构类课程实验（如 RISC-V 处理器、FPGA、操作系统实验），
把"做完实验 → 取证 → 出图 → 写报告 → 校验排版 → 交付"整条链路固化成可复用的流程和工具。

## 它解决什么问题

让 coding agent 写实验报告时最容易犯的几类错：

- **编数据** —— 报告里的数字不是跑出来的，是"应该差不多是这样"
- **不做实验只写报告** —— 遇到环境不通就退回纯写作
- **把截图当证据** —— 无法复核、无法精确定位到某个时钟周期
- **生成成功 ≠ 排版正确** —— 中文字体没生效、图表溢出页边、编号对不上
- **不交代失败** —— 没做成的部分假装做成了

这个技能用「三条铁律 + 六个阶段」把上面每一条都堵住。

## 安装

```bash
# Linux / macOS
git clone https://github.com/chalili-hub/dsh-skill-docx.git ~/.dsh/skills/lab-report
```

```powershell
# Windows PowerShell
git clone https://github.com/chalili-hub/dsh-skill-docx.git "$env:USERPROFILE\.dsh\skills\lab-report"
```

技能目录名不必与技能同名（技能名取自 `SKILL.md` frontmatter 的 `name`），
所以克隆成任何 kebab-case 目录名都能被识别；`~/.dsh/skills/` 下每多一层目录就多一个技能。
DSH 会监听技能目录，**无需重启**，新增/修改后下次会话即可使用。

## 使用

| 方式 | 做法 |
| --- | --- |
| 自动 | 正常提要求，例如"按实验要求完成实验，给我写个报告文档"，任务匹配时 agent 会自行加载 |
| 斜杠菜单 | 在 Web GUI 输入框打 `/`，在「技能 / Skills」分组里选 `lab-report` |
| 手打 | 在消息任意位置写 `/lab-report`（需空格/换行边界），效果与菜单选完全一致 |

`/lab-report` 是宿主在消息预处理阶段识别的字面量 token，菜单只是帮你补全，两者等价。

## 目录结构

```
lab-report/
├── SKILL.md                技能主体：三条铁律 + 六阶段流程 + 坑位速查
├── references/
│   ├── recon.md            要求文档解析、环境探测、执行通道选择（含 vmrun 通道要点）
│   ├── evidence.md         远程执行、环境搭建坑位、波形/日志取证、GUI 截图取舍
│   ├── writing.md          报告骨架、各章写法、图表规范、交付前自检清单
│   └── toolchain.md        docx/PDF/图表工具链配方与交付物组织
└── scripts/
    ├── docx_kit.py         python-docx 中文排版工具库
    ├── verify_docx.py      docx → PDF → PNG 逐页校验
    ├── vcd_analyze.py      VCD → 逐周期信号表
    └── wave_plot.py        逐周期表 → 数字波形图
```

## 依赖

```bash
python -m pip install python-docx python-pptx pymupdf matplotlib pillow
```

- `docx_kit.py` — 需要 `python-docx`
- `verify_docx.py` — 需要 `pymupdf`；PDF 转换用 Word COM（Windows）或 `soffice`（LibreOffice）
- `vcd_analyze.py` — 纯标准库，无依赖
- `wave_plot.py` — 需要 `matplotlib`

## 脚本

### `docx_kit.py` —— 中文排版工具库

python-docx 只设 `run.font.name` 对中文**无效**，必须显式写 `w:rFonts/@w:eastAsia`。
这个库把标题(黑体)/正文(宋体)/代码(Consolas)/表格/图注/封面全部封装好：

```python
from docx_kit import Doc

d = Doc()                                   # A4 + 2.6cm 边距 + 宋体正文
d.cover(title="实验报告", meta=[("姓　　名", ""), ("学　　号", "")])
d.h("一、实验目的", 1)
d.p("正文段落，自动首行缩进两个字符。")
d.code("riscv32-unknown-elf-objdump -d test.elf")
d.table(["地址", "机器码"], [["0x200", "01400313"]], widths=[3, 4])
d.pic("fig1.png", width_cm=15.8)
d.caption("图 1  取指阶段波形")
d.save("报告.docx")
```

### `verify_docx.py` —— 排版校验（必做）

把 docx 渲染成 PDF 再逐页转 PNG，用来**真的看一眼**成品：

```bash
python verify_docx.py 报告.docx 预览目录 --pages 1,5,9,13
```

这一步能抓到字体没生效、图片溢出页边、表格断行、编号错位等所有问题。
"生成成功"从来不等于"排版正确"。

### `vcd_analyze.py` —— VCD 波形解析

```bash
python vcd_analyze.py dump.vcd out --list                     # 先看有哪些信号
python vcd_analyze.py dump.vcd out --grep 'pc|inst|alu' --cycles 0:120
python vcd_analyze.py dump.vcd out --signals sigs.json        # 精确指定列名
```

输出 `out.cycles.tsv`（每周期一行的十六进制信号表）+ `out.signals.txt`。

**内含两个真实踩过的坑：**
1. Verilator 会把电气上相同的网络归并到同一个 VCD id（`fe_reg_inst` / `immGen_io_inst` /
   `io_ctrl_inst` 可能是同一个 id）。必须建 **`id → [别名列表]`** 的一对多映射；
   若按"一个 id 只留最后一个名字"处理，会有信号永远读到 `x` 且**不报错**——静默产出错数据。
2. 采样时刻要与测试平台对齐。riscv-mini 的 `top.cc` 每个时钟高低电平各 dump 一次，
   故偶数时间戳 = 上升沿后的状态。

### `wave_plot.py` —— 数字波形绘图

```bash
python wave_plot.py cycles.tsv spec.json out.png
```

`spec.json` 描述要画哪些行、行标签、位宽、标题：

```json
{
  "title": "图2  PC=0x210 取指阶段波形",
  "cycles": [13, 22],
  "rows": [
    {"col": "pc",           "label": "pc[32:0]",         "width": 8},
    {"col": "stall",        "label": "stall"},
    {"col": "ic_resp_data", "label": "icache.resp.data", "width": 8}
  ]
}
```

位宽自动识别 1-bit / 总线；已处理好中文（**含中文的文本绝不能设 `family="monospace"`**，
等宽字体普遍缺 CJK 字形，会渲染成方框）。

## 设计要点

- **不编数据**：报告里每个数字都要能追溯到落盘的产物，先取证再从文件取数。
- **不做"对答案"式圆场**：要求文档给出的预期地址/寄存器值用来反向校验复现结果，对不上就查清楚。
- **脚本优先于截图**：数值表可 grep、可复核、可重跑，截图不行。
- **诚实标注边界**：Wayland 下 Xwayland 窗口常 `IsUnMapped`，`xwd`/`captureScreen` 抓不到 GUI 截图——
  技能明确要求"别承诺 GUI 截图"，改用数据绘图并在报告里说明原因。

## License

MIT
