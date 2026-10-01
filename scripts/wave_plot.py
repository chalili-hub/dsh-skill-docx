#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wave_plot —— 把 vcd_analyze.py 导出的逐周期信号表画成数字波形图（matplotlib）。

用法::

    python wave_plot.py cycles.tsv spec.json out.png

spec.json::

    {
      "title": "图2  PC=0x210 取指阶段波形",
      "cycles": [13, 22],
      "fig_width": 15.5,
      "rows": [
        {"col": "pc",          "label": "pc[32:0]",      "width": 8},
        {"col": "stall",       "label": "stall"},                       // 自动识别为 1bit
        {"col": "ic_resp_data","label": "icache.resp.data", "width": 8}
      ]
    }

也可作为库使用::

    from wave_plot import load_cycles, draw_waveform
    rows = load_cycles("fac_.cycles.tsv")
    draw_waveform(rows, spec, "fig2.png")

中文提示: 本脚本已把 font.sans-serif 设为 Microsoft YaHei / SimHei；
**不要把含中文的文本设为 family="monospace"**，等宽字体普遍缺 CJK 字形，会渲染成方框。
"""
import csv
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                                   "Source Han Sans SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def load_cycles(path):
    # utf-8-sig: 兼容 Windows 记事本 / PowerShell Set-Content 写入的 BOM
    with open(path, encoding="utf-8-sig") as f:
        return {int(r["cycle"]): r for r in csv.DictReader(f, delimiter="\t")}


def hx(v, width=None):
    if v is None or v == "x":
        return "x"
    if v.startswith("0x"):
        v = v[2:]
    v = v.strip()
    if not v or set(v) & set("xzXZ"):
        return "x"
    n = (len(v) + 3) // 4
    s = "%0*X" % (n, int(v, 16))
    return s[-width:] if width else s


def num(v, width=None):
    s = hx(v, width)
    return None if s == "x" else int(s, 16)


def _draw_row(ax, y0, values, cycles, label, width=None,
              color="#00A000", txtcolor="#004000", is_bit=None, note=None,
              label_ea=True):
    n = len(values)
    if is_bit is None:
        is_bit = all(v in ("0", "1", "x", None) for v in values)

    if is_bit:
        for i in range(n):
            v = values[i]
            yv = y0 + 0.80 if v == "1" else (y0 + 0.20 if v == "0" else y0 + 0.50)
            if v == "x":
                ax.plot([cycles[i], cycles[i] + 1], [yv, yv], color="#B0B0B0",
                        lw=1.1, ls=(0, (2, 2)))
            else:
                ax.plot([cycles[i], cycles[i] + 1], [yv, yv], color=color, lw=1.4)
        for i in range(n - 1):
            a, b = values[i], values[i + 1]
            if a != b and "x" not in (a, b):
                ya = y0 + 0.80 if a == "1" else y0 + 0.20
                yb = y0 + 0.80 if b == "1" else y0 + 0.20
                ax.plot([cycles[i] + 1, cycles[i] + 1], [ya, yb], color=color, lw=1.4)
    else:
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[j + 1] == values[i]:
                j += 1
            x0, x1 = cycles[i], cycles[j] + 1
            t = min(0.18, (x1 - x0) * 0.25)
            v = hx(values[i], width)
            if v == "x":
                ax.plot([x0, x1], [y0 + 0.5, y0 + 0.5], color="#B0B0B0",
                        lw=1.1, ls=(0, (2, 2)))
            else:
                pts = [(x0, y0 + 0.15), (x0 + (t if i > 0 else 0), y0 + 0.85),
                       (x1 - (t if j < n - 1 else 0), y0 + 0.85), (x1, y0 + 0.15)]
                ax.add_patch(Polygon(pts, closed=True, facecolor="#EAF7EA",
                                     edgecolor=color, lw=1.1))
                if x1 - x0 >= 0.9:
                    ax.text((x0 + x1) / 2.0, y0 + 0.5, v, ha="center", va="center",
                            fontsize=7.2, family="monospace", color=txtcolor)
                else:
                    ax.text((x0 + x1) / 2.0, y0 + 0.98, v, ha="center", va="bottom",
                            fontsize=6.4, family="monospace", color=txtcolor)
            i = j + 1

    # 行标签：绝不设 family="monospace"（中文会变方框）
    ax.text(cycles[0] - 0.25, y0 + 0.5, label, ha="right", va="center",
            fontsize=8, color="#202020")
    if note:
        ax.text(cycles[-1] + 0.35, y0 + 0.5, note, ha="left", va="center",
                fontsize=7.5, color="#A00000")


def draw_waveform(rows, spec, out_path, dpi=170):
    cyc0, cyc1 = spec["cycles"]
    cycle_list = list(range(cyc0, cyc1 + 1))
    row_specs = spec["rows"]
    nrow = len(row_specs)
    fig_w = spec.get("fig_width", 15.5)
    fig_h = 0.40 * nrow + 1.4

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    for k, rs in enumerate(row_specs):
        col = rs["col"]
        vals = [rows[c][col] if c in rows and col in rows[c] else "x" for c in cycle_list]
        _draw_row(ax, nrow - 1 - k, vals, cycle_list, rs.get("label", col),
                  width=rs.get("width"), is_bit=rs.get("bit"), note=rs.get("note"))

    step = max(1, (cyc1 - cyc0) // 20)
    ax.set_xlim(cyc0 - 6.5, cyc1 + 3.5)
    ax.set_ylim(-0.35, nrow + 0.55)
    ax.set_yticks([])
    ax.set_xticks(range(cyc0, cyc1 + 1, step))
    ax.tick_params(axis="x", labelsize=8)
    ax.set_xlabel("时钟周期 (cycle)", fontsize=9)
    for c in range(cyc0, cyc1 + 2):
        ax.axvline(c, color="#DDDDDD", lw=0.6, zorder=0)
    ax.set_title(spec.get("title", ""), fontsize=11, pad=12)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    # 长 y 标签需要更宽的左边距；tight_layout 常常给不够
    fig.subplots_adjust(left=spec.get("left", 0.20), right=0.98, top=0.90, bottom=0.10)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    tsv, spec_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    rows = load_cycles(tsv)
    # utf-8-sig: PowerShell Set-Content -Encoding UTF8 会写 BOM，用 utf-8 解析会报
    # "Unexpected UTF-8 BOM"；utf-8-sig 同时兼容有/无 BOM。
    with open(spec_path, encoding="utf-8-sig") as f:
        spec = json.load(f)
    print("saved", draw_waveform(rows, spec, out))


if __name__ == "__main__":
    main()
