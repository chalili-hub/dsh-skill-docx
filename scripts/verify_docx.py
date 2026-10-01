#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_docx —— 把 docx 渲染成 PDF 再栅格化成 PNG，供人（或模型）逐页检查排版。

用法::

    python verify_docx.py 报告.docx 预览目录
    python verify_docx.py 报告.docx 预览目录 --pages 1,5,9,13 --dpi 110

流程: docx --(Word COM / LibreOffice)--> pdf --(PyMuPDF)--> png
退出码非 0 表示转换失败。输出的 PNG 路径会打印出来，可直接交给 read_image 查看。

依赖: pymupdf          pip install pymupdf
可选: Word(Windows) 或 libreoffice/soffice
"""
import argparse
import os
import shutil
import subprocess
import sys


def find_soffice():
    for name in ("soffice", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if os.path.exists(p):
            return p
    return None


def docx_to_pdf_word(docx_path, pdf_path):
    """Windows + Microsoft Word 的 COM 导出（排版最准）。"""
    ps = r"""
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject Word.Application
$w.Visible = $false
try {
  $d = $w.Documents.Open('%s', $false, $true)
  $d.ExportAsFixedFormat('%s', 17)
  $d.Close(0)
} finally { $w.Quit() }
""" % (docx_path.replace("'", "''"), pdf_path.replace("'", "''"))

    for exe in ("pwsh", "powershell"):
        if shutil.which(exe):
            r = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", ps],
                               capture_output=True, text=True)
            if r.returncode == 0 and os.path.exists(pdf_path):
                return True
            sys.stderr.write((r.stderr or r.stdout or "")[:2000] + "\n")
            return False
    return False


def docx_to_pdf_soffice(docx_path, pdf_path):
    soffice = find_soffice()
    if not soffice:
        return False
    outdir = os.path.dirname(os.path.abspath(pdf_path)) or "."
    os.makedirs(outdir, exist_ok=True)
    subprocess.run([soffice, "--headless", "--norestore",
                    "--convert-to", "pdf", "--outdir", outdir, docx_path],
                   capture_output=True, text=True, timeout=600)
    produced = os.path.join(outdir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
    if produced != pdf_path and os.path.exists(produced):
        shutil.move(produced, pdf_path)
    return os.path.exists(pdf_path)


def to_pdf(docx_path, pdf_path, prefer="auto"):
    if prefer in ("auto", "word") and sys.platform == "win32":
        if docx_to_pdf_word(docx_path, pdf_path):
            return "word"
        if prefer == "word":
            return None
    if prefer in ("auto", "soffice") and docx_to_pdf_soffice(docx_path, pdf_path):
        return "soffice"
    return None


def rasterize(pdf_path, outdir, pages=None, dpi=110):
    import fitz  # PyMuPDF
    os.makedirs(outdir, exist_ok=True)
    d = fitz.open(pdf_path)
    total = d.page_count
    idxs = range(total) if not pages else [p - 1 for p in pages if 1 <= p <= total]
    out = []
    for i in idxs:
        path = os.path.join(outdir, "page-%02d.png" % (i + 1))
        d[i].get_pixmap(dpi=dpi).save(path)
        out.append(path)
    d.close()
    return total, out


def main():
    ap = argparse.ArgumentParser(description="渲染 docx 为 PDF 并栅格化，用于排版校验")
    ap.add_argument("docx")
    ap.add_argument("outdir", nargs="?", default="_preview")
    ap.add_argument("--pages", default="", help="只渲染这些页，如 1,5,9；默认全部")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--engine", default="auto", choices=["auto", "word", "soffice"])
    args = ap.parse_args()

    docx_path = os.path.abspath(args.docx)
    if not os.path.exists(docx_path):
        sys.exit("找不到文件: %s" % docx_path)

    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)
    pdf_path = os.path.join(outdir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")

    engine = to_pdf(docx_path, pdf_path, args.engine)
    if not engine:
        sys.exit("docx -> pdf 失败：既没有可用的 Word COM，也没有 soffice/libreoffice")
    print("pdf: %s  (engine=%s)" % (pdf_path, engine))

    pages = [int(x) for x in args.pages.split(",") if x.strip()] if args.pages else None
    total, pngs = rasterize(pdf_path, outdir, pages, args.dpi)
    print("总页数: %d，已渲染 %d 页" % (total, len(pngs)))
    for p in pngs:
        print(p)
    print("\n提示: 用 read_image 打开上面几张（封面、表格密集页、图片页、末页）确认排版。")


if __name__ == "__main__":
    main()
