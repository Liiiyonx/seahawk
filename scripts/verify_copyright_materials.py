"""软著材料实测校验（PyMuPDF 版）。

实测项：页数 / 每页正文行数 / 页眉 / 页码连续性 / 行号列连续性 / 首尾页内容。

行数口径（沿用历史踩坑结论）：直接数 `get_text()` 的文本行，再扣除
页眉行与页脚行。**不要用 y 坐标聚类** —— 中西文混排基线微差会少算 1 行，
误报 49 行。
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

HDR_SUB = "探海灵眸海洋环境治理智能体软件"
SRC = "源代码鉴别材料_探海灵眸海洋环境治理智能体软件V1.0.pdf"
MAN = "软件说明书_探海灵眸海洋环境治理智能体软件V1.0.pdf"


def page_lines(page) -> list[str]:
    return [l for l in page.get_text().split("\n") if l.strip()]


ROW_TOLERANCE_PT = 4.0
HEADER_Y_MAX = 55.0
FOOTER_Y_MIN = 780.0


def visual_rows(page, tol: float = ROW_TOLERANCE_PT) -> list[tuple[float, str]]:
    """把页面按 y 坐标聚成**视觉行**，返回 [(y, 整行文本)]。

    ★ 为什么必须聚类，不能直接数 `get_text().split("\\n")`：
      源码行是「行号 + 制表符 + 代码」三段。制表符落点恰好在行号右边界时，
      PyMuPDF 会把同一视觉行拆成两条 text line（本机实测第 7/17/18/29 页
      各多出 1~2 条，分布为 {50:56, 51:2, 52:2}），而 PDF 上肉眼仍是 50 行。
      直接数文本行会**误报**行数不足 —— 这正是历史踩坑记录里
      「不要用文本行数 / y 聚类」那条建议的 nuanced 版本：
        · 数 `get_text()` 文本行 → 拆行误报偏多；
        · 纯 y 聚类不设容差 → 中西文基线微差会少算 1 行。
      正确做法是 **y 聚类 + 容差 4pt**，本机实测 60 页全部恰好 50 行。
    """
    spans: list[tuple[float, float, str]] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"])
            if text.strip():
                spans.append((line["bbox"][1], line["bbox"][0], text))
    spans.sort()
    rows: list[list] = []
    for y, x, text in spans:
        if rows and abs(y - rows[-1][0]) <= tol:
            rows[-1][1].append((x, text))
        else:
            rows.append([y, [(x, text)]])
    out = []
    for y, parts in rows:
        parts.sort()
        out.append((y, "".join(t for _, t in parts)))
    return out


def body_rows(page, page_no: int) -> list[str]:
    """返回去掉页眉页脚后的正文视觉行。"""
    rows = visual_rows(page)
    body = []
    for y, text in rows:
        if y <= HEADER_Y_MAX or y >= FOOTER_Y_MIN:
            continue
        if HDR_SUB in text or re.fullmatch(rf"第\s*{page_no}\s*页", text.strip()):
            continue
        body.append(text)
    return body


def check(path: Path, expect_pages: int, lines_per_page: int | None) -> None:
    print(f"\n{'=' * 74}\n{path.name}\n{'=' * 74}")
    doc = fitz.open(path)
    n = doc.page_count
    ok_pages = "OK" if n == expect_pages else f"MISMATCH(期望{expect_pages})"
    print(f"页数: {n}  {ok_pages}")

    dist: Counter = Counter()
    bad_hdr: list[int] = []
    bad_pageno: list[int] = []
    empty: list[int] = []
    linenos: list[int] = []
    last_lineno = 0
    probes: list[tuple[int, str]] = []

    for i in range(1, n + 1):
        rows = visual_rows(doc[i - 1])
        if not rows:
            empty.append(i)
            continue
        hdr = [t for _, t in rows if HDR_SUB in t]
        ftr = [t for _, t in rows if re.fullmatch(rf"第\s*{i}\s*页", t.strip())]
        if not hdr:
            bad_hdr.append(i)
        if not ftr:
            bad_pageno.append(i)
        body = body_rows(doc[i - 1], i)
        if lines_per_page:
            dist[len(body)] += 1
        if body:
            # 取本页**首个带行号**的行：模块分隔注释行以「# =====」开头、
            # 行号与「#」之间无空格，用 r"^\d+\s" 会漏掉它。
            for text in body:
                m = re.match(r"^(\d+)", text)
                if m:
                    linenos.append(int(m.group(1)))
                    break
            m2 = re.match(r"^(\d+)", body[-1])
            if m2:
                last_lineno = int(m2.group(1))
            if i in (1, 2, 30, 31, n):
                probes.append((i, body[0][:76]))
    doc.close()

    if lines_per_page:
        print(f"每页正文行数分布: {dict(sorted(dist.items()))}")
        good = all(k == lines_per_page for k in dist)
        print(f"  全部 {lines_per_page} 行: {'OK' if good else 'MISMATCH'}")
    print(f"空白页: {empty or '无'}")
    print(f"页眉异常: {bad_hdr or '无'}")
    print(f"页码异常: {bad_pageno or '无'}")
    if linenos:
        # 取的是每页**首个带号行**，故合法步长恒为 50（每页 50 行）。
        gaps = {linenos[i + 1] - linenos[i] for i in range(len(linenos) - 1)}
        bad = gaps - {50}
        print(f"行号列: 每页首行 {linenos[0]} → {linenos[-1]}  跨页连续: "
              f"{'OK' if not bad else f'异常步长{bad}'}（末行 {last_lineno}）")
    for pno, t in probes:
        print(f"  p{pno:>2} 首行: {t}")


if __name__ == "__main__":
    base = Path(r"C:\Users\Liii\Desktop\Oceanus软著材料")
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("both", "src"):
        check(base / SRC, 60, 50)
    if which in ("both", "man"):
        check(base / MAN, 22, None)
