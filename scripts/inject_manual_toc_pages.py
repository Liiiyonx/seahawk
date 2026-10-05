"""给软著说明书 docx 注入目录页码（点线引导 + 右对齐页码）。

为什么需要单独一步：`build_copyright_manual.py` 每次重跑都会重建目录域，
目录页码被清空。而提交给版权局的 PDF 里目录必须有页码，否则审核员
无法核对「目录 ↔ 正文章节」是否一致。

做法：
  1. 先转成 PDF，用 PyMuPDF 找出每个章节标题**实际所在页码**；
  2. 回到 docx，把静态目录清单的每一行改写成「标题 …… 页码」（制表位 + 右对齐）；
  3. 页码以 PDF 实测为准，不手写、不推算 —— 手写页码内容一改就漂。

用法：
  python scripts/inject_manual_toc_pages.py            # 注入并报告
  python scripts/inject_manual_toc_pages.py --verify   # 注入后交叉核验
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
BASE = Path(r"C:\Users\Liii\Desktop\Oceanus软著材料")
DOCX = BASE / "软件说明书_探海灵眸海洋环境治理智能体软件V1.0.docx"
# 目录清单行长这样的前缀（build_copyright_manual.py 里的 toc 列表）
TOC_LINE = re.compile(r"^(\d+(?:\.\d+)?)\s{2,}(.+?)\s*$")


def docx_to_pdf(docx: Path) -> Path:
    out = Path(tempfile.mkdtemp())
    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "pdf", str(docx), "--outdir", str(out)],
        check=True,
        capture_output=True,
    )
    pdf = out / (docx.stem + ".pdf")
    if not pdf.exists():
        raise SystemExit("PDF 转换失败")
    return pdf


def locate_sections(pdf: Path) -> dict[str, int]:
    """扫描 PDF，返回 {章节编号: 页码}。

    只认章级标题（「1  引言」「2.3  技术架构」这类），
    避免正文里出现的「5.11」字样被误当标题。
    """
    doc = fitz.open(pdf)
    found: dict[str, int] = {}
    head_re = re.compile(r"^(\d+(?:\.\d+)?)\s{1,3}([^\d].*)$")
    for pno in range(1, doc.page_count + 1):
        text = doc[pno - 1].get_text()
        for line in text.split("\n"):
            line = line.strip()
            if not line or "探海灵眸" in line:
                continue
            m = head_re.match(line)
            if not m:
                continue
            if len(line) > 40 or line.endswith(("。", "，", "；", "：")):
                continue
            num = m.group(1)
            # ★ 取**最后一次**出现的页码，而不是第一次。
            #   目录页在前、正文标题在后，两者文本完全相同；取首次会拿到
            #   目录所在页（实测所有章级页码都被写成 2，即目录页）。
            #   章节标题在正文里只出现一次，末次即真页码；
            #   目录里出现 N 次的，取到的就是正文那一页。
            found[num] = pno
    doc.close()
    return found


def is_toc_title(text: str) -> bool:
    """判断是否目录标题。

    build_copyright_manual.py 里写的是 h1("目  录") —— 「目」与「录」之间
    **两个**全角空格（中文排版惯例）。早先只匹配「目 录」一个空格，
    导致标题没被识别、注入 0 条。这里用「去掉所有空白后比对」兜底。
    """
    return text.replace(" ", "").replace("\u3000", "") in ("目录", "章节清单")


def clear_toc_runs(paragraph) -> None:
    """清空段落所有 run。

    必须整体删 run 再重建，不能只 add_run 追加 —— 重跑本脚本时
    旧段落里已有「标题 \\t 旧页码」，追加会变成「标题 \\t 旧页码 \\t 新页码」，
    制表符留着会在 PDF 里渲出两段点线。本脚本对同一 docx 幂等的前提
    就是这里真的清干净。
    """
    for r in list(paragraph.runs):
        r._element.getparent().remove(r._element)


def set_run_font(run, size: float = 10.0) -> None:
    run.font.size = Pt(size)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), "Times New Roman")
    rfonts.set(qn("w:hAnsi"), "Times New Roman")
    rfonts.set(qn("w:eastAsia"), "SimSun")
    run.font.color.rgb = RGBColor(0, 0, 0)


def inject(docx: Path) -> tuple[dict[str, int], int, int]:
    tmp_pdf = docx_to_pdf(docx)
    pages = locate_sections(tmp_pdf)
    doc = Document(str(docx))

    filled = 0
    missing: list[str] = []
    in_toc = False
    for para in doc.paragraphs:
        text = para.text.strip()
        if is_toc_title(text):
            in_toc = True
            continue
        if in_toc:
            # 目录区遇到空段落或正文标题样式即结束
            if not text:
                if filled:
                    break
                continue
            if para.style.name.startswith("Heading"):
                break
            m = TOC_LINE.match(text)
            if not m:
                continue
            num, title = m.group(1), m.group(2)
            page = pages.get(num)
            if page is None:
                missing.append(num)
                continue

            clear_toc_runs(para)
            pf = para.paragraph_format
            # 章级左对齐、子节缩进；右对齐制表位放页码，点线自动填充
            pf.left_indent = Cm(0 if "." not in num else 0.75)
            pf.line_spacing = 1.5
            pf.tab_stops.add_tab_stop(Cm(15.0), WD_TAB_ALIGNMENT.RIGHT, 2)  # 2=点线引导

            r1 = para.add_run(f"{num}  {title}")
            set_run_font(r1)
            if "." not in num:
                r1.font.bold = True
            r2 = para.add_run("\t")
            set_run_font(r2)
            r3 = para.add_run(str(page))
            set_run_font(r3)
            filled += 1

    doc.save(str(docx))
    return pages, filled, len(missing)


def verify(docx: Path) -> None:
    """交叉核验：目录标注页码 vs PDF 里章节实际页码。"""
    tmp_pdf = docx_to_pdf(docx)
    pages = locate_sections(tmp_pdf)
    doc = Document(str(docx))
    ok = bad = 0
    in_toc = False
    for para in doc.paragraphs:
        text = para.text.strip()
        if is_toc_title(text):
            in_toc = True
            continue
        if in_toc and not text and ok + bad:
            break
        m = TOC_LINE.match(text.replace("\t", "  ")) if in_toc else None
        if not m:
            continue
        num = m.group(1)
        # 页码是**制表符之后**的那一段。用 split('\t') 取末段，
        # 不能用 `(\d+)\s*$` 正则 —— 那会命中标题里的章节号
        # （「5.10 通知中心」会取到 10，把真实页码 18 读成 10）。
        parts = [p.strip() for p in text.split("\t") if p.strip()]
        if len(parts) < 2 or not parts[-1].isdigit():
            continue
        declared = int(parts[-1])
        actual = pages.get(num)
        if actual == declared:
            ok += 1
        else:
            bad += 1
            print(f"  ✗ {num} 目录写 {declared}，实际在第 {actual} 页")
    print(f"交叉核验: {ok} 条吻合, {bad} 条不符")
    shutil.rmtree(tmp_pdf.parent, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    if not DOCX.exists():
        print(f"找不到 {DOCX}")
        return 1
    pages, filled, missing = inject(DOCX)
    print(f"已注入 {filled} 条目录页码；未匹配章节号: {missing or '无'}")
    if args.verify:
        verify(DOCX)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
