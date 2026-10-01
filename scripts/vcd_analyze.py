#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vcd_analyze —— 流式解析 VCD 波形，导出「逐周期信号取值表」(TSV)，便于精确分析与绘图。

为什么不用截图: 表格数值可复核、可 grep、可直接进报告表格，且能一键重跑。

用法::

    # 1) 先看 VCD 里有哪些信号
    python vcd_analyze.py dump.vcd out --list

    # 2) 按正则挑信号，导出逐周期表
    python vcd_analyze.py dump.vcd out --grep 'pc|inst|alu|regFile' --cycles 0:120

    # 3) 用清单文件精确指定列名（JSON: {"列名": "TOP.Tile.core.dpath.pc"}）
    python vcd_analyze.py dump.vcd out --signals sigs.json

输出::
    out.cycles.tsv    cycle  cycle 各信号(十六进制)...
    out.signals.txt   全部信号名与位宽

重要（两个真实踩过的坑）:
  1. Verilator 会把电气上相同的网络归并到同一个 VCD id。多个不同名字可能是同一个 id，
     因此必须建立 id -> [别名...] 的一对多映射；若按「一个 id 只留最后一个名字」处理，
     会有信号永远读到 'x' 且**静默出错**。
  2. 采样时刻要与测试平台对齐。riscv-mini 的 top.cc 每个时钟高/低电平各 dump 一次，
     main_time 每次 +1，故偶数时间戳 = 上升沿后的状态（默认 --sample even）。
"""
import argparse
import json
import re
import sys


def parse_header(path):
    """返回 (name2id, widths)。同一个物理网络会有多个名字指向同一个 id。"""
    name2id, widths = {}, {}
    scope = []
    with open(path, "r", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("$scope"):
                scope.append(s.split()[2])
            elif s.startswith("$upscope"):
                if scope:
                    scope.pop()
            elif s.startswith("$var"):
                p = s.split()
                if len(p) < 5:
                    continue
                width, vid, nm = int(p[2]), p[3], p[4]
                full = ".".join(scope + [nm])
                name2id[full] = vid
                widths[full] = width
            elif s.startswith("$enddefinitions"):
                break
    return name2id, widths


def to_hex(bits):
    if not bits or set(bits) & set("xzXZ"):
        return "x"
    try:
        v = int(bits, 2)
    except ValueError:
        return "x"
    return "0x%0*X" % ((len(bits) + 3) // 4, v)


def analyze(vcd, prefix, cols, c0, c1, sample, verbose=True):
    """cols: [(列名, 信号全名)]"""
    name2id, widths = parse_header(vcd)

    # id -> [列名...]  (一对多！)
    id2cols, missing = {}, []
    for col, full in cols:
        if full in name2id:
            id2cols.setdefault(name2id[full], []).append(col)
        else:
            missing.append(full)
    if missing:
        sys.stderr.write("WARNING 以下信号在 VCD 中不存在: %s\n" % ", ".join(missing))

    names = [c for c, _ in cols]
    state = {c: "x" for c in names}
    rows = []
    t = 0
    started = False
    with open(vcd, "r", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not started:
                if s.startswith("$enddefinitions"):
                    started = True
                continue
            if not s or s[0] == "$":
                continue
            if s[0] == "#":
                nt = int(s[1:])
                if nt != t and _selected(t, sample):
                    cyc = t // 2
                    if c0 <= cyc <= c1:
                        rows.append((cyc, dict(state)))
                t = nt
            elif s[0] in "bB":
                p = s.split()
                if len(p) == 2 and p[1] in id2cols:
                    for c in id2cols[p[1]]:
                        state[c] = p[0][1:]
            elif s[0] in "01xzXZ":
                vid = s[1:]
                if vid in id2cols:
                    for c in id2cols[vid]:
                        state[c] = s[0]

    with open(prefix + ".cycles.tsv", "w", encoding="utf-8") as f:
        f.write("cycle\t" + "\t".join(names) + "\n")
        for cyc, st in rows:
            f.write("%d\t" % cyc + "\t".join(to_hex(st.get(c, "x")) for c in names) + "\n")

    if verbose:
        sys.stderr.write("wrote %s.cycles.tsv (%d 周期, %d 信号)\n" % (prefix, len(rows), len(names)))
    return rows


def _selected(t, sample):
    if sample == "all":
        return True
    return t % 2 == 0 if sample == "even" else t % 2 == 1


def main():
    ap = argparse.ArgumentParser(description="VCD -> 逐周期信号表")
    ap.add_argument("vcd")
    ap.add_argument("prefix")
    ap.add_argument("--grep", default="", help="正则；选出名称匹配的信号（可用 | 组合）")
    ap.add_argument("--signals", default="", help="JSON 文件: {\"列名\": \"信号全名\"}")
    ap.add_argument("--cycles", default="", help="周期范围，如 0:120")
    ap.add_argument("--sample", default="even", choices=["even", "odd", "all"],
                    help="采样时间戳奇偶（默认 even = 上升沿后，适配 riscv-mini top.cc）")
    ap.add_argument("--list", action="store_true", help="只列出全部信号，不导出")
    args = ap.parse_args()

    name2id, widths = parse_header(args.vcd)

    if args.list:
        for n in sorted(name2id):
            print("%-72s %d" % (n, widths.get(n, 0)))
        print("共 %d 个信号" % len(name2id), file=sys.stderr)
        return

    if args.signals:
        spec = json.load(open(args.signals, encoding="utf-8"))
        cols = list(spec.items())
    elif args.grep:
        rx = re.compile(args.grep)
        cols = [(n.split(".")[-1], n) for n in sorted(name2id) if rx.search(n)]
        # 重名时用全名去重后缀
        seen = {}
        out = []
        for col, full in cols:
            if col in seen:
                seen[col] += 1
                col = "%s#%d" % (col, seen[col])
            else:
                seen[col] = 0
            out.append((col, full))
        cols = out
    else:
        cols = [(n.split(".")[-1], n) for n in sorted(name2id)]

    c0, c1 = 0, 10 ** 9
    if args.cycles:
        a, _, b = args.cycles.partition(":")
        c0 = int(a) if a.strip() else 0
        c1 = int(b) if b.strip() else 10 ** 9

    analyze(args.vcd, args.prefix, cols, c0, c1, args.sample)


if __name__ == "__main__":
    main()
