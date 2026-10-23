"""给软著说明书 docx 注入目录页码（点线引导 + 右对齐页码）。

为什么需要单独一步：`build_copyright_manual.py` 每次重跑都会重建目录域，
目录页码被清空。而提交给版权局的 PDF 里目录必须有页码，否则审核员
无法核对「目录 ↔ 正文章节」是否一致。

做法：
  1. 先转成 PDF，用 PyMuPDF 找出每个章节标题**实际所在页码**；
  2. 回到 docx，把静态目录清单的每一行改写成「标题 …… 页码」（制表位 + 右对齐）；
  3. 页码以 PDF 实测为准，不手写、不推算 —— 手写页码内容一改就漂。

★ 定点迭代（本脚本的关键修正）
  重建目录行的 run 会顺带改掉字体与缩进，目录区高度随之变化（实测 3 页 → 2 页），
  正文整体前移 1 页；若仍按**注入前**的 PDF 取页码，成稿里每个页码都会偏 +1。
  因此这里写成不动点迭代：写页码 → 重新转 PDF → 重新定位 → 直到
  「已写入的页码 == 当前 PDF 实测页码」才收手（通常 2 轮收敛）。

★ 标题精确匹配（避免表格污染）
  早先按「行首裸数字」定位，会被正文表格里的「2 核 CPU」「8 核 CPU」误命中，
  把章号 2 定位到表格所在页。改为「章号 + 标题文本」双条件匹配后即免疫。

用法：
  python scripts/inject_manual_toc_pages.py                     # 主软著说明书
  python scripts/inject_manual_toc_pages.py --docx <路径>       # 拆分登记各篇
  python scripts/inject_manual_toc_pages.py --docx <路径> --verify
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

NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")


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


def parse_toc_line(text: str) -> tuple[str, str, int | None] | None:
    """解析目录行 → (章号, 标题, 已写页码 or None)。

    兼容两种形态：
      · 注入前：「　1.1  编写目的」       （无制表符、无页码）
      · 注入后：「1.1  编写目的\\t5」      （制表符 + 页码）
    """
    text = text.strip()
    if not text:
        return None
    page: int | None = None
    if "\t" in text:
        head, _, tail = text.rpartition("\t")
        if tail.strip().isdigit():
            page = int(tail.strip())
            text = head.strip()
    toks = text.split()
    if len(toks) < 2 or not NUM_RE.fullmatch(toks[0]):
        return None
    return toks[0], " ".join(toks[1:]), page


def collect_toc_paragraphs(doc) -> list[tuple]:
    """收集目录区段落 → [(paragraph, num, title)]。"""
    out: list[tuple] = []
    in_toc = False
    for para in doc.paragraphs:
        text = para.text.strip()
        if text.replace(" ", "").replace("\u3000", "") in ("目录", "章节清单"):
            in_toc = True
            continue
        if not in_toc:
            continue
        if not text:
            if out:
                break
            continue
        if para.style.name.startswith("Heading"):
            break
        parsed = parse_toc_line(text)
        if parsed:
            out.append((para, parsed[0], parsed[1]))
    return out


def locate_headings(pdf: Path, entries: list[tuple[str, str]]) -> dict[str, int]:
    """扫描 PDF，按「章号 + 标题」精确匹配返回 {章号: 页码}。

    取**最后一次**出现：目录页在前、正文标题在后；目录里的行会带点线页码，
    正文标题是干净的一行，二者都能命中，末次即正文真页码。
    """
    res = {num: None for num, _ in entries}
    doc = fitz.open(pdf)
    for num, title in entries:
        pat = re.compile(rf"^\s*{re.escape(num)}(?![\d.])\s+{re.escape(title)}")
        for pno in range(1, doc.page_count + 1):
            for line in doc[pno - 1].get_text().split("\n"):
                if pat.match(line.strip()):
                    res[num] = pno
    doc.close()
    return res


def clear_toc_runs(paragraph) -> None:
    """清空段落所有 run（避免重跑时旧页码残留成第二段点线）。"""
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


def write_numbers(doc, entries: list[tuple], pages: dict[str, int]) -> tuple[int, list[str]]:
    filled = 0
    missing: list[str] = []
    for para, num, title in entries:
        page = pages.get(num)
        if page is None:
            missing.append(num)
            continue
        clear_toc_runs(para)
        pf = para.paragraph_format
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
    return filled, missing


def inject(docx: Path, max_iter: int = 6) -> tuple[dict[str, int], int, list[str], int]:
    """定点迭代注入，返回 (页码表, 注入条数, 未匹配章号, 迭代轮数)。"""
    doc = Document(str(docx))
    entries = collect_toc_paragraphs(doc)
    if not entries:
        return {}, 0, [], 0
    key_entries = [(num, title) for _, num, title in entries]
    pages: dict[str, int] = {}
    filled = 0
    missing: list[str] = []
    rounds = 0
    for it in range(max_iter):
        rounds = it + 1
        pdf = docx_to_pdf(docx)
        pages = locate_headings(pdf, key_entries)
        written = {num: parse_toc_line(para.text)[2] for para, num, _ in entries}
        if it > 0 and written == {n: pages.get(n) for n, _ in key_entries}:
            break
        filled, missing = write_numbers(doc, entries, pages)
        doc.save(str(docx))
    return pages, filled, missing, rounds


def verify(docx: Path) -> None:
    """交叉核验：目录标注页码 vs PDF 里章节实际页码。"""
    doc = Document(str(docx))
    entries = collect_toc_paragraphs(doc)
    key_entries = [(num, title) for _, num, title in entries]
    tmp_pdf = docx_to_pdf(docx)
    pages = locate_headings(tmp_pdf, key_entries)
    ok = bad = 0
    for para, num, _ in entries:
        parsed = parse_toc_line(para.text)
        declared = parsed[2] if parsed else None
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
    ap.add_argument("--docx", default=None,
                    help="目标说明书 docx；缺省为主软著说明书（拆分登记各篇需显式指定）")
    args = ap.parse_args()

    target = Path(args.docx) if args.docx else DOCX
    if not target.exists():
        print(f"找不到 {target}")
        return 1
    pages, filled, missing, rounds = inject(target)
    print(f"已注入 {filled} 条目录页码（{rounds} 轮收敛）；未匹配章节号: {missing or '无'}")
    if args.verify:
        verify(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
