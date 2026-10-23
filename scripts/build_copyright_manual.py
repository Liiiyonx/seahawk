#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成软件著作权登记的「软件说明书」（文档鉴别材料，操作手册体裁）。

规范依据（中国版权保护中心登记要求）：
  1. 文档鉴别材料可为用户手册 / 操作手册 / 设计说明书之一；
  2. 前、后各连续 30 页，共 60 页；整个文档不足 60 页的，提交全部；
  3. 页眉标注软件全称及版本号，页码；
  4. 有画面的页面可不足 30 行文字。

体裁选择：操作手册（最直观、与系统截图强绑定）。
截图来源：artifacts/ui-responsive/1920x1080-*.png 及 vision-preview 检测效果图。

用法：
    .\\.venv-analysis\\Scripts\\python.exe scripts\\build_copyright_manual.py \
        --out "C:\\Users\\Liii\\Desktop\\Oceanus软著材料"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent

SOFTWARE_FULL_NAME = "探海灵眸海洋环境治理智能体软件"
SOFTWARE_SHORT_NAME = "Oceanus"
VERSION = "V1.0"
# ★ 2026-10-05 格式对齐 `桌面/软著登记材料`（BlindGuard 已提交 / 聆心已过审）：
#   页眉改为「软件著作权操作手册 · <全称> · <版本>」，字号 10.5pt。
#   分隔符用间隔号「 · 」而非空格——PyMuPDF 内置中文字体缺 ASCII 空格
#   字形，空格会被渲染成约 2 倍宽，把名称拆成「AI　减负」「V 3 . 2」。
HEADER_TEXT = (
    f"软件著作权操作手册 · {SOFTWARE_FULL_NAME} · {VERSION}"
)
HEADER_SIZE = 10.5

# ── 变体：拆分登记第 4 篇「水面垃圾打捞机械臂控制软件」────────────────
# 见《方案书_04_水面垃圾打捞机械臂控制软件V1.0》。与主软著共用同一套排版
# 管线（封面 / 页眉 / 页码 / 表格 / 图片），只替换软件名、页眉与正文内容。
# 正文另起一套 build_arm_* 函数链 —— 本篇是机器人本体嵌入式控制软件，
# 操作对象是串口舵机、ROS 关节与标定板，与平台操作手册的内容完全不同，
# 靠参数切换正文是不现实的，只能各写一份。
ARM_FULL_NAME = "探海灵眸水面垃圾打捞机械臂控制软件"
ARM_SHORT_NAME = "Oceanus Arm"
ARM_HEADER_TEXT = (
    f"软件著作权操作手册 · {ARM_FULL_NAME} · {VERSION}"
)

# ── 变体：拆分登记第 2 篇「海洋治理智能体决策与审批软件」───────────────
# 见《方案书_02_海洋治理智能体决策与审批软件V1.0》。说明书视角由
# 「平台整体操作手册」换成「智能体配置 / 审批流管理 / 运维手册」，
# 章节结构与本篇功能边界一一对应（智能体是唯一主角，平台其余只作背景）。
AGENT_FULL_NAME = "探海灵眸海洋治理智能体决策与审批软件"
AGENT_SHORT_NAME = "Oceanus Agent"
AGENT_HEADER_TEXT = f"软件著作权操作手册 · {AGENT_FULL_NAME} · {VERSION}"

# ── 变体：拆分登记第 1 篇「海漂垃圾边缘智能感知软件」───────────────
# 见《方案书_01_海漂垃圾边缘智能感知软件V1.0》。说明书视角由「平台整体
# 操作手册」换成「边缘端部署 / 配置 / 运维手册」，章节结构与本篇功能边界
# 一一对应（感知链路是唯一主角，平台其余只作背景）。
EDGE_FULL_NAME = "探海灵眸海漂垃圾边缘智能感知软件"
EDGE_SHORT_NAME = "Oceanus Edge"
EDGE_HEADER_TEXT = f"软件著作权操作手册 · {EDGE_FULL_NAME} · {VERSION}"

# ── 变体：拆分登记第 3 篇「海域治理三维数字沙盘软件」─────────────────
# 见《方案书_03_海域治理三维数字沙盘软件V1.0》。说明书视角为
# 「三维态势呈现与仿真推演操作手册」：三维地形、载具调度、航线与轨迹、
# 图层与事件联动、仿真推演沙盒、大屏展示（沙盘是唯一主角）。
SANDBOX_FULL_NAME = "探海灵眸海域治理三维数字沙盘软件"
SANDBOX_SHORT_NAME = "Oceanus SandBox"
SANDBOX_HEADER_TEXT = f"软件著作权操作手册 · {SANDBOX_FULL_NAME} · {VERSION}"


def select_variant(key: str) -> None:
    """按拆分登记篇目切换页眉软件名（默认主软著）。

    ★ 这里只切 HEADER_TEXT，不切 SOFTWARE_FULL_NAME —— 各篇的封面标题写在
    build_*_cover 里，用的是自己的 *_FULL_NAME 常量。两份 select_variant
    曾经并存（第 4 篇加入时误加了一个同名函数），后定义覆盖前定义导致
    机械臂篇页眉静默退回主软著名。合并成一个，分支都在这里。
    """
    global HEADER_TEXT
    if key == "agent":
        HEADER_TEXT = AGENT_HEADER_TEXT
    elif key == "edge":
        HEADER_TEXT = EDGE_HEADER_TEXT
    elif key == "arm":
        HEADER_TEXT = ARM_HEADER_TEXT
    elif key == "sandbox":
        HEADER_TEXT = SANDBOX_HEADER_TEXT


NAVY = RGBColor(0x0F, 0x2E, 0x4C)
OCEAN = RGBColor(0x1D, 0x6A, 0x9C)
GRAY = RGBColor(0x60, 0x60, 0x60)
DARK = RGBColor(0x1B, 0x2A, 0x38)
RED = RGBColor(0xB0, 0x30, 0x22)

CJK = "Microsoft YaHei"
MONO = "Consolas"

UI = ROOT / "artifacts" / "ui-responsive"
VP = ROOT / "artifacts" / "vision-preview"
#: 关键区域裁切图（由 _work/crop_agent_figs.py 从整屏截图裁出）
FIGS = ROOT / "artifacts" / "copyright-figs"
#: 机械臂控制台截图（由 scripts/shot_arm_console.mjs 从独立挂载的组件抓取）
ARM_SHOT = ROOT / "artifacts" / "arm-console"


def set_cjk(run, font=CJK, size=10.5, color=DARK, bold=False):
    run.font.name = font
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.bold = bold
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), font)
    rfonts.set(qn("w:ascii"), font)
    rfonts.set(qn("w:hAnsi"), font)


class Manual:
    def __init__(self) -> None:
        self.doc = Document()
        self._setup()

    def _setup(self) -> None:
        section = self.doc.sections[0]
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.4)
        section.bottom_margin = Cm(2.2)
        section.left_margin = Cm(2.6)
        section.right_margin = Cm(2.4)
        section.header_distance = Cm(1.38)
        section.footer_distance = Cm(1.3)

        hp = section.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = hp.add_run(HEADER_TEXT)
        set_cjk(run, size=HEADER_SIZE, color=RGBColor(0, 0, 0))

        fp = section.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pre = fp.add_run("第")
        set_cjk(pre, size=HEADER_SIZE, color=RGBColor(0, 0, 0))
        fld = OxmlElement("w:fldSimple")
        fld.set(qn("w:instr"), "PAGE")
        inner_r = OxmlElement("w:r")
        inner_rpr = OxmlElement("w:rPr")
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), str(int(HEADER_SIZE * 2)))
        inner_rpr.append(sz)
        inner_r.append(inner_rpr)
        t = OxmlElement("w:t")
        t.text = "1"
        inner_r.append(t)
        fld.append(inner_r)
        fp._p.append(fld)
        post = fp.add_run(" 页")
        set_cjk(post, size=HEADER_SIZE, color=RGBColor(0, 0, 0))

    def page_break(self) -> None:
        self._drop_trailing_blank()
        self.doc.add_page_break()

    def _drop_trailing_blank(self) -> None:
        """分页前先删掉正文末尾的空段落。

        ★ 为什么必须做：table() 收尾会补一个空段落把表格与后文隔开（不补，
          表格会紧贴下一段，观感很差）。但表格若正好排到页底，这个空段落
          就单独溢到下一页 —— 紧随其后的 page_break() 再翻一页，中间便夹出
          一张整页空白。提交材料里出现空白页是硬伤（第 4 篇初版实测第 6 页
          全空，正是这样来的）。
        """
        body = self.doc.element.body
        while True:
            paragraphs = [el for el in body if el.tag == qn("w:p")]
            if not paragraphs:
                return
            tail = paragraphs[-1]
            # 只删「确实是正文最后一个可见元素」的空段落：
            # 若它后面还有别的元素（如 sectPr 之外的内容），不动。
            if body[-1] is not tail and body[-1].tag != qn("w:sectPr"):
                return
            # 段落里有文字 / 图片 / 分页符就不算空
            if tail.xpath(".//w:t") or tail.xpath(".//w:drawing") \
                    or tail.xpath(".//w:br") or tail.xpath(".//w:pict"):
                return
            body.remove(tail)

    def h1(self, text: str) -> None:
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(10)
        set_cjk(p.add_run(text), size=17, color=NAVY, bold=True)

    def h2(self, text: str) -> None:
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(6)
        set_cjk(p.add_run(text), size=13.5, color=OCEAN, bold=True)

    def h3(self, text: str) -> None:
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        set_cjk(p.add_run(text), size=11.5, color=NAVY, bold=True)

    def para(self, text: str, size=10.5) -> None:
        p = self.doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0.74)
        p.paragraph_format.line_spacing = 1.4
        set_cjk(p.add_run(text), size=size)

    def bullets(self, items: list[str]) -> None:
        for it in items:
            p = self.doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.35
            set_cjk(p.add_run("•  "), size=10.5, color=OCEAN, bold=True)
            set_cjk(p.add_run(it), size=10.5)

    def steps(self, items: list[str]) -> None:
        for i, it in enumerate(items, 1):
            p = self.doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.6)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.line_spacing = 1.35
            set_cjk(p.add_run(f"步骤{i}  "), size=10.5, color=RED, bold=True)
            set_cjk(p.add_run(it), size=10.5)

    def table(self, headers: list[str], rows: list[list[str]], widths_cm: list[float] | None = None) -> None:
        t = self.doc.add_table(rows=1 + len(rows), cols=len(headers))
        t.style = "Table Grid"
        # 固定列宽 + 单元格文字自动换行关闭。
        # 不设列宽时 Word/LibreOffice 按内容自动分配，中文列宽被压窄就会把
        # 「缓存与事件队列」断成「…事件队/列」，是提交材料上肉眼可见的排版硬伤。
        t.autofit = False
        # ★ python-docx 的 `autofit = False` 只改 tblPr 里的一个属性，
        #   **不足以让 LibreOffice 固定列宽** —— 必须显式写
        #   `<w:tblLayout w:type="fixed"/>`，否则渲染时仍按内容自动分配，
        #   中文列被压窄就会把「缓存与事件队列」断成「…事件队/列」。
        tbl_pr = t._tbl.tblPr
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        tbl_pr.append(layout)
        if widths_cm:
            # ★ tblW 必须从 type="auto" 改成 "dxa" 并给具体总宽。
            #   只设 tblLayout=fixed + tblGrid，LibreOffice 仍按 tblW=auto
            #   重算列宽并压缩到内容宽度 —— 实测 6.7cm 的列被压到 5.6cm，
            #   「缓存与事件队列」照样断成「…事件队/列」。三处都要写。
            total = sum(widths_cm)
            for old in tbl_pr.findall(qn("w:tblW")):
                tbl_pr.remove(old)
            tbl_w = OxmlElement("w:tblW")
            tbl_w.set(qn("w:type"), "dxa")
            tbl_w.set(qn("w:w"), str(int(Cm(total).twips)))
            tbl_pr.append(tbl_w)
            grid = t._tbl.find(qn("w:tblGrid"))
            if grid is not None:
                for gc, w in zip(grid.findall(qn("w:gridCol")), widths_cm):
                    gc.set(qn("w:w"), str(int(Cm(w).twips)))
            for j, w in enumerate(widths_cm):
                for row in t.rows:
                    row.cells[j].width = Cm(w)
        for j, h in enumerate(headers):
            cell = t.rows[0].cells[j]
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            set_cjk(cell.paragraphs[0].add_run(h), size=10, color=NAVY, bold=True)
            tc_pr = cell._tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), "E8F1F7")
            tc_pr.append(shd)
        for i, row in enumerate(rows, 1):
            for j, val in enumerate(row):
                cell = t.rows[i].cells[j]
                set_cjk(cell.paragraphs[0].add_run(val), size=9.5)
        # 表头行跨页重复，且行内不断页，保证一行内容不被拆到两页
        tr_pr = t.rows[0]._tr.get_or_add_trPr()
        for tag in ("w:tblHeader", "w:cantSplit"):
            el = OxmlElement(tag)
            tr_pr.append(el)
        for i in range(1, len(t.rows)):
            tr_pr = t.rows[i]._tr.get_or_add_trPr()
            tr_pr.append(OxmlElement("w:cantSplit"))
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def image(self, path: Path, caption: str, width_cm=15.5) -> None:
        if not path.exists():
            self.para(f"［截图待补：{caption}（{path.name}）］")
            return
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(path), width=Cm(width_cm))
        cap = self.doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cjk(cap.add_run(caption), size=9, color=GRAY)

    def mono_block(self, lines: list[str], caption: str = "") -> None:
        """等宽输出块：终端运行结果、配置文件节录。

        ★ 为什么用渲染的等宽块而不是截图：终端截图要么靠人工去截一张
          真实窗口，要么伪造 —— 后者在提交材料里等于编造证据。这里贴的是
          **实际执行的命令与实际输出**，逐字可复现，比截图更经得起核对。
        """
        for ln in lines:
            p = self.doc.add_paragraph()
            pf = p.paragraph_format
            pf.left_indent = Cm(0.5)
            pf.right_indent = Cm(0.3)
            pf.space_before = Pt(0)
            pf.space_after = Pt(0)
            pf.line_spacing = 1.12
            run = p.add_run(ln if ln else " ")
            run.font.name = MONO
            run.font.size = Pt(8.5)
            run.font.color.rgb = RGBColor(0x1B, 0x2A, 0x38)
            rpr = run._element.get_or_add_rPr()
            rfonts = OxmlElement("w:rFonts")
            rfonts.set(qn("w:ascii"), MONO)
            rfonts.set(qn("w:hAnsi"), MONO)
            rfonts.set(qn("w:eastAsia"), CJK)
            rpr.append(rfonts)
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), "F2F5F8")
            p._element.get_or_add_pPr().append(shd)
        if caption:
            cap = self.doc.add_paragraph()
            cap.paragraph_format.space_before = Pt(2)
            cap.paragraph_format.space_after = Pt(8)
            set_cjk(cap.add_run(caption), size=9, color=GRAY)
        else:
            self.doc.add_paragraph().paragraph_format.space_after = Pt(6)

    def caption_note(self, text: str) -> None:
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        set_cjk(p.add_run(text), size=9, color=GRAY)

    def build(self) -> Document:
        return self.doc


def build_cover(m: Manual) -> None:
    for _ in range(5):
        m.doc.add_paragraph()
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(SOFTWARE_FULL_NAME), size=26, color=NAVY, bold=True)
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(f"（简称：{SOFTWARE_SHORT_NAME}）"), size=16, color=OCEAN)
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(f"{VERSION}"), size=20, color=NAVY, bold=True)
    for _ in range(2):
        m.doc.add_paragraph()
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run("软 件 说 明 书"), size=22, color=DARK, bold=True)
    for _ in range(6):
        m.doc.add_paragraph()
    for line in ("文档类别：操作手册", "著作权人：福州理工学院", "编写日期：2026 年 10 月"):
        p = m.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cjk(p.add_run(line), size=12, color=GRAY)
    m.page_break()


def build_toc(m: Manual) -> None:
    m.h1("目  录")
    toc = [
        "1  引言",
        "　1.1  编写目的",
        "　1.2  软件背景",
        "　1.3  术语与缩略语",
        "2  软件概述",
        "　2.1  软件定位与治理闭环",
        "　2.2  功能清单",
        "　2.3  技术架构",
        "3  运行环境",
        "　3.1  硬件环境",
        "　3.2  软件环境",
        "4  部署与初始化",
        "5  功能操作说明",
        "　5.1  用户登录",
        "　5.2  治理大屏",
        "　5.3  事件管理",
        "　5.4  工单管理",
        "　5.5  设备管理",
        "　5.6  统计报表",
        "　5.7  AI 助手",
        "　5.8  智能体工作台",
        "　5.9  知识域工作台",
        "　5.10  消息通知中心",
        "　5.11  边缘检测效果说明",
        "6  常见问题与处理",
        "7  附录：接口与数据约定",
    ]
    # ★ 目录不用手打页码 —— 手写的页码永远对不上（内容一改就漂）。
    #   改用 Word 的 TOC 域：打开时自动更新，页码由排版引擎计算。
    #   域代码 \\o "1-2" 表示收录 1~2 级标题。
    p = m.doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.6
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    for el in (fld_begin, instr, fld_sep):
        run._element.append(el)
    # 域占位文字：**不得**写入任何脚本操作指引（如「按 Ctrl+A 后 F9 更新目录」），
    # 那类痕迹会随提交材料一起印在 PDF 上，等于向审核员暴露批量生成痕迹。
    # 也不能提「见下方章节清单」——本函数下方紧接着就是「目 录」标题，
    # 重复且指向一个已改名的标题。这里留空占位即可。
    ph = p.add_run("")
    set_cjk(ph, size=9, color=RGBColor(0x80, 0x80, 0x80))
    end_run = p.add_run()
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    end_run._element.append(fld_end)

    # 本函数开头已用 h1 写了「目  录」大标题，这里**不再重复写标题**。
    # 重复标题会在 PDF 上出现两个「目 录」，是低级排版错误。
    for line in toc:
        tp = m.doc.add_paragraph()
        tp.paragraph_format.line_spacing = 1.5
        set_cjk(tp.add_run(line), size=10)
    m.page_break()


def build_intro(m: Manual) -> None:
    m.h1("1  引言")
    m.h2("1.1  编写目的")
    m.para(
        "本说明书是「探海灵眸海洋环境治理智能体软件[简称:Oceanus] V1.0」的操作手册，"
        "面向系统管理员、值班研判人员、业务操作员与审批人员，"
        "说明软件的功能构成、运行环境、部署方式以及各功能模块的操作方法。"
    )
    m.h2("1.2  软件背景")
    m.para(
        "近海养殖区海漂垃圾治理长期依赖人工巡查与人工派工，存在发现不及时、"
        "清理无台账、责任难追溯等问题。本软件面向县域海洋环境治理场景，"
        "构建“岸基感知—平台决策—机器人执行—数据回传”的闭环体系："
        "岸基摄像头实时识别水面漂浮垃圾并上报事件，平台智能体对事件进行研判、"
        "审批与派单，水面机器人执行清理并回传结果，全过程形成可审计的证据链"
        "与量化治理报表。"
    )
    m.h2("1.3  术语与缩略语")
    m.table(
        ["术语", "说明"],
        [
            ["事件（Event）", "边缘端识别到的一片垃圾记录，含类别、位置、时间与证据图"],
            ["工单（Task）", "派发给执行设备的清理任务，具有完整状态机"],
            ["派单（Dispatch）", "把事件转化为工单的决策过程，含五步筛选与防抖合并"],
            ["垃圾四分类", "foam（泡沫）、plastic（塑胶）、fishing_gear（渔具）、other（其他）"],
            ["ACK 回执", "执行设备收到指令后的确认应答，超时未确认自动换设备重派"],
            ["智能体（Agent）", "进行事件研判与决策的运行实体，决策轨迹全程留痕可审计"],
            ["知识资产", "登记入库的文档、表格、图片、事件、遥测等多模态数据资产"],
            ["时序校验", "边缘端误报抑制机制：单帧检测不确认，连续命中方可上报"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.page_break()


def build_overview(m: Manual) -> None:
    m.h1("2  软件概述")
    m.h2("2.1  软件定位与治理闭环")
    m.para(
        "本软件是一套面向海洋养殖区海漂垃圾治理的三端协同智能系统，"
        "覆盖“感知—决策—执行—数据价值”全链路："
    )
    m.bullets([
        "感知：岸基摄像头旁的边缘盒完成取流、检测、时序校验与事件上报；",
        "决策：平台对事件进行智能研判、防抖合并、人工审批与工单派发；",
        "执行：水面机器人接收指令执行清理，回传 ACK 回执与作业数据；",
        "数据价值：热力图、派单调度、量化报表与溯源分析沉淀治理资产。",
    ])
    m.para(
        "与市面单机清理设备相比，本软件的差异在于系统级闭环：识别对象针对"
        "中国养殖区特色垃圾（EPS 泡沫浮球碎片、废旧渔具、饵料袋），"
        "打捞执行端可替换、可离线，软件侧独立形成事件理解、规划、工具调用、"
        "策略守卫、审批、派单、审计与回放的完整能力。"
    )
    m.h2("2.2  功能清单")
    m.table(
        ["子系统", "主要功能"],
        [
            ["边缘感知软件", "视频取流、垃圾检测、时序校验误报抑制、事件上报"],
            ["数据平台后端", "事件接入、派单引擎、工单状态机、设备管理、报表统计、权限与审计"],
            ["智能体内核", "事件研判、决策规划、工具调用、策略守卫、人工审批、记忆与复盘"],
            ["知识智能体", "多模态知识资产登记、动态本体构建、跨文档多跳检索、证据链"],
            ["Web 前端", "治理大屏、事件/工单/设备/报表管理、AI 助手、知识域与审批工作台"],
            ["消息链路", "MQTT 设备接入、ACK 超时追踪、WebSocket 实时推送"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.h2("2.3  技术架构")
    m.para("软件采用分层架构，主要技术选型如下：")
    m.table(
        ["层次", "技术", "用途"],
        [
            ["后端服务", "Python 3.11 / FastAPI", "异步接口服务、OpenAPI 文档"],
            ["数据存储", "PostgreSQL + PostGIS / Redis", "业务与空间数据、缓存与事件队列"],
            ["消息总线", "EMQX（MQTT）", "移动网络友好的设备接入"],
            ["对象存储", "MinIO", "告警帧与作业影像存储"],
            ["流媒体", "go2rtc", "RTSP 视频转 WebRTC/FLV 低延迟播放"],
            ["前端", "Vue 3 / Vite / Pinia", "单页应用与实时状态管理"],
            ["可视化", "ECharts / Leaflet / Three.js", "图表、地图与机械臂三维仿真"],
            ["边缘检测", "OpenCV 传统视觉（主链路）与开放词汇零样本（对照）", "漂浮垃圾检测"],
            ["容器化", "Docker Compose", "一键部署全部服务"],
        ],
        widths_cm=[2.8, 6.7, 6.0],
    )
    m.page_break()


def build_env(m: Manual) -> None:
    m.h1("3  运行环境")
    m.h2("3.1  硬件环境")
    m.table(
        ["节点", "最低配置", "说明"],
        [
            ["平台服务器", "8 核 CPU / 16 GB 内存 / 200 GB 磁盘", "运行后端、数据库、消息与应用服务"],
            ["边缘计算盒", "4 核 CPU / 8 GB 内存", "岸基摄像头旁部署，运行边缘感知软件"],
            ["客户端", "2 核 CPU / 4 GB 内存，1920×1080 显示器", "Chrome / Edge 浏览器访问"],
        ],
        widths_cm=[2.8, 6.2, 6.5]
    )
    m.h2("3.2  软件环境")
    m.table(
        ["类别", "要求"],
        [
            ["操作系统", "Linux（服务端，推荐 Ubuntu 22.04）；边缘盒支持 Linux/Windows"],
            ["容器环境", "Docker 24+ 与 Docker Compose v2"],
            ["数据库", "PostgreSQL 14+（含 PostGIS 扩展）、Redis 7"],
            ["消息中间件", "EMQX 5.x"],
            ["浏览器", "Chrome 100+ / Edge 100+（推荐 1920×1080 分辨率）"],
        ],
        widths_cm=[3.0, 12.5]
    )
    m.page_break()


def build_deploy(m: Manual) -> None:
    m.h1("4  部署与初始化")
    m.steps([
        "准备服务器并安装 Docker 与 Docker Compose；",
        "复制 .env.example 为 .env，按现场填写数据库、消息队列、对象存储等连接参数；",
        "执行 docker compose up -d 启动全部服务（后端、前端、数据库、Redis、EMQX、MinIO、流媒体）；",
        "执行初始化脚本创建演示账号与基础数据；",
        "浏览器访问平台地址，使用管理员账号登录，进入「设备管理」完成摄像头与执行设备的登记；",
        "在边缘盒部署边缘感知软件，配置点位与上报地址，启动后事件自动上报至平台。",
    ])
    m.para(
        "部署完成后，系统提供四类预置角色：admin（全部权限）、operator（写操作）、"
        "approver（只读与智能体审批）、viewer（只读）。权限由服务端签名令牌承载，"
        "所有写操作均记录审计日志。"
    )
    m.page_break()


def build_operations(m: Manual) -> None:
    m.h1("5  功能操作说明")
    m.para(
        "本章按页面逐一说明各功能模块的操作方法。截图取自实际运行的 Web 前端。"
    )

    # 5.1 登录
    m.h2("5.1  用户登录")
    m.para(
        "打开平台地址进入登录页。输入账号与密码完成登录；系统按角色签发"
        "服务端签名令牌，并跳转至对应权限的默认页面。连续输错将触发限速保护。"
    )
    m.image(UI / "1920x1080-login.png", "图 5-1  登录页面")
    m.page_break()

    # 5.2 大屏
    m.h2("5.2  治理大屏")
    m.para(
        "治理大屏是系统的主视图，实时汇聚关键治理指标：今日事件数、待处理工单、"
        "清理量统计、垃圾类别分布、事件热力地图与实时告警流。数据通过 WebSocket "
        "实时推送，页面无需手动刷新。"
    )
    m.image(UI / "1920x1080-dashboard.png", "图 5-2  治理大屏（指标、热力地图与实时事件）")
    m.bullets([
        "顶部统计卡片：今日事件、待派单、进行中工单、累计清理量；",
        "中部热力地图：按网格聚合事件密度，点击网格可查看明细；",
        "右侧实时事件流：新事件上报后秒级出现，可一键跳转详情。",
    ])
    m.page_break()

    # 5.3 事件
    m.h2("5.3  事件管理")
    m.para(
        "事件页面管理边缘端上报的全部垃圾事件。支持按类别、时间段、状态、"
        "点位筛选；每条事件包含类别、位置、时间、置信度与证据图。"
        "对同一位置短时间内的重复事件，系统自动防抖合并，避免重复派单。"
    )
    m.image(UI / "1920x1080-events.png", "图 5-3  事件管理页面")
    m.steps([
        "在筛选栏选择类别（泡沫/塑胶/渔具/其他）与时间范围；",
        "点击事件行查看详情与证据图；",
        "确认事件有效后点击「派单」，选择执行设备并提交；",
        "系统生成工单并进入工单流转。",
    ])
    m.page_break()

    # 5.4 工单
    m.h2("5.4  工单管理")
    m.para(
        "工单页面跟踪清理任务的完整生命周期：待确认 → 已下发 → 执行中 → "
        "已完成 / 已取消。设备收到指令后回传 ACK 回执，超时未确认的工单"
        "自动换设备重派；执行完成后回传作业数据与影像。"
    )
    m.image(UI / "1920x1080-tasks.png", "图 5-4  工单管理页面")
    m.bullets([
        "状态机流转全程留痕，任何状态变更均记录操作人与时间；",
        "支持人工补派、取消与备注；",
        "工单详情页可查看 ACK 回执时间线与执行结果影像。",
    ])
    m.page_break()

    # 5.5 设备
    m.h2("5.5  设备管理")
    m.para(
        "设备页面管理三类设备：岸基摄像头、无人机与水面机器人。"
        "可查看设备在线状态、最近心跳、绑定点位与负责区域；"
        "支持设备登记、编辑、启停与协议配置。"
    )
    m.image(UI / "1920x1080-devices.png", "图 5-5  设备管理页面")
    m.steps([
        "点击「新增设备」，选择设备类型并填写名称、点位坐标与通信参数；",
        "保存后设备进入离线状态，边缘程序或机载程序上线后自动转为在线；",
        "对异常设备可执行停用操作，停用后不再参与派单。",
    ])
    m.page_break()

    # 5.6 报表
    m.h2("5.6  统计报表")
    m.para(
        "报表页面提供治理成效的量化统计：按日/周/月的事件趋势、清理量趋势、"
        "类别构成、点位排名与设备作业量。报表支持导出，作为治理台账留档。"
    )
    m.image(UI / "1920x1080-reports.png", "图 5-6  统计报表页面")
    m.bullets([
        "趋势图支持时间粒度切换（日/周/月）；",
        "类别构成饼图反映四类垃圾占比变化；",
        "导出结果与页面数据一致，可作为考核依据。",
    ])
    m.page_break()

    # 5.7 AI 助手
    m.h2("5.7  AI 助手")
    m.para(
        "AI 助手是面向值班人员的自然语言问答入口，可查询事件、工单、设备与"
        "统计数据，并触发常用操作。助手由大模型与规则兜底共同驱动，"
        "对高风险操作（如派单）会先请求人工确认。"
    )
    m.image(UI / "1920x1080-assistant.png", "图 5-7  AI 助手对话页面")
    m.steps([
        "在输入框用自然语言提问，例如“今天泡沫类事件有多少”；",
        "助手返回结构化结果并附数据来源；",
        "对涉及写操作的请求，页面弹出确认框，人工确认后执行。",
    ])
    m.page_break()

    # 5.8 智能体
    m.h2("5.8  智能体工作台")
    m.para(
        "智能体工作台展示智能体的决策运行轨迹：每次运行的规划步骤、工具调用、"
        "审批节点与记忆更新全程留痕。审批人员可在此对智能体的高风险决策"
        "进行批准或驳回，所有决定记录在案，形成可审计的证据链。"
    )
    m.image(UI / "1920x1080-agents.png", "图 5-8  智能体工作台（运行轨迹与审批）")
    m.bullets([
        "运行列表：按时间与状态筛选智能体运行记录；",
        "轨迹视图：逐步展示规划、工具调用与结果；",
        "审批视图：approver 角色可批准或驳回待审批决策。",
    ])
    m.page_break()

    # 5.9 知识域
    m.h2("5.9  知识域工作台")
    m.para(
        "知识域工作台管理系统的多模态知识资产：政策文件、监测报告、台账表格、"
        "事件与遥测数据登记入库后形成版本不可变的知识资产；系统支持半自动"
        "本体构建与跨文档多跳检索，为治理决策提供可溯源的证据支撑。"
    )
    m.image(UI / "1920x1080-knowledge.png", "图 5-9  知识域工作台")
    m.steps([
        "在资产页上传或登记文档/表格/图片，系统计算内容哈希并生成版本；",
        "在本体页审核系统抽取的本体候选，发布本体版本；",
        "在检索页进行跨文档检索，结果附带原文定位与证据链。",
    ])
    m.page_break()

    # 5.10 通知
    m.h2("5.10  消息通知中心")
    m.para(
        "通知中心汇聚系统告警与业务消息：设备离线、事件激增、工单超时、"
        "审批待办等。支持移动端自适应布局，值班人员可在手机上即时收到提醒。"
    )
    m.image(UI / "390x844-notifications.png", "图 5-10  通知中心（移动端自适应布局）", width_cm=8.0)
    m.page_break()

    # 5.11 检测效果
    m.h2("5.11  边缘检测效果说明")
    m.para(
        "边缘感知软件在岸基摄像头的水面监控视角下对漂浮垃圾进行检测识别。"
        "以下为水面实测画面的检测结果：识别框叠加在视频帧上，并标注垃圾类别"
        "与置信度。检测结果按置信度由高到低排列，图中仅保留达到置信度阈值"
        "且目标尺寸足以辨识的有效框。"
    )
    m.para(
        "检测结果并非直接上报事件，而是先进入时序校验环节：同一网格区域内"
        "需在设定时间窗内连续命中方可确认为正式事件，单帧命中仅作为候选"
        "记录。该机制用于抑制水面波光、反光与漂浮物阴影造成的瞬时误报，"
        "因此事件列表中的确认事件数量明显少于原始检测框数量。"
    )
    m.image(VP / "water-bottle-detected.jpg", "图 5-11  水面漂浮塑料瓶与塑料袋检测效果", width_cm=14.5)
    m.image(VP / "water-plasticbag-detected.jpg", "图 5-12  水面塑料废弃物检测效果", width_cm=14.5)
    m.image(VP / "water-container-detected.jpg", "图 5-13  水面塑料容器检测效果", width_cm=14.5)
    m.caption_note(
        "注：以上检测画面为岸基摄像头水面监控视角的实拍帧，"
        "用于说明边缘感知软件的检测与标注能力。"
    )
    m.page_break()


def build_faq(m: Manual) -> None:
    m.h1("6  常见问题与处理")
    m.table(
        ["现象", "可能原因", "处理方法"],
        [
            ["登录后页面空白", "账号无对应角色权限", "联系管理员确认角色分配"],
            ["大屏数据不更新", "WebSocket 连接中断", "检查网络后刷新页面；仍异常则查看后端日志"],
            ["事件持续无上报", "边缘盒离线或时序校验未命中", "在设备页检查边缘盒心跳；核对摄像头取流地址"],
            ["工单长时间待确认", "执行设备未回 ACK", "等待系统超时自动重派，或人工补派至其他设备"],
            ["检测误报较多", "点位反光或阈值不适配", "在边缘配置中调整时序校验与置信度阈值"],
        ],
        widths_cm=[3.6, 5.4, 6.5]
    )
    m.page_break()


def build_appendix(m: Manual) -> None:
    m.h1("7  附录：接口与数据约定")
    m.para("软件对外提供 REST API（/api/v1 前缀）与 WebSocket 实时通道，主要约定如下：")
    m.table(
        ["类别", "约定"],
        [
            ["认证", "登录签发 JWT 令牌，后续请求携带 Authorization: Bearer 头"],
            ["响应信封", "统一 {code, message, data} 结构，附 trace_id 便于追踪"],
            ["事件上报", "边缘端经 MQTT 上报，QoS1 幂等去重"],
            ["工单指令", "平台经 MQTT 下发，设备回传 ACK 回执与执行结果"],
            ["实时推送", "WebSocket 推送事件、工单状态与设备上下线消息"],
        ],
        widths_cm=[3.0, 12.5]
    )
    m.para(
        "本说明书随软件版本迭代更新。如与系统实际界面存在差异，以软件实际运行版本为准。"
    )


# ---------------------------------------------------------------------------
# 拆分登记第 2 篇：海洋治理智能体决策与审批软件 —— 操作手册
# 视角：智能体配置 / 审批流管理 / 运维手册（平台其余部分只作背景）
# ---------------------------------------------------------------------------


def build_agent_cover(m: Manual) -> None:
    for _ in range(5):
        m.doc.add_paragraph()
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(AGENT_FULL_NAME), size=24, color=NAVY, bold=True)
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(f"（简称：{AGENT_SHORT_NAME}）"), size=16, color=OCEAN)
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(f"{VERSION}"), size=20, color=NAVY, bold=True)
    for _ in range(2):
        m.doc.add_paragraph()
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run("软 件 说 明 书"), size=22, color=DARK, bold=True)
    for _ in range(6):
        m.doc.add_paragraph()
    for line in ("文档类别：操作手册", "著作权人：福州理工学院", "编写日期：2026 年 10 月"):
        p = m.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cjk(p.add_run(line), size=12, color=GRAY)
    m.page_break()


def build_agent_toc(m: Manual) -> None:
    m.h1("目  录")
    toc = [
        "1  引言",
        "　1.1  编写目的",
        "　1.2  软件背景",
        "　1.3  术语与缩略语",
        "2  软件概述",
        "　2.1  软件定位与决策闭环",
        "　2.2  功能清单",
        "　2.3  技术架构",
        "3  运行环境",
        "　3.1  硬件环境",
        "　3.2  软件环境",
        "4  部署与配置",
        "　4.1  服务部署",
        "　4.2  大模型后端接入",
        "　4.3  审批角色与权限配置",
        "5  事件研判",
        "　5.1  事件接入",
        "　5.2  研判触发",
        "　5.3  研判结论查看",
        "6  多角色智能体运行",
        "　6.1  角色说明",
        "　6.2  运行列表",
        "　6.3  运行详情与步骤追踪",
        "7  人工审批门禁",
        "　7.1  待审批队列",
        "　7.2  批准与拒绝",
        "　7.3  策略拒绝与研判门禁",
        "8  派发引擎与设备 ACK 闭环",
        "　8.1  建单与合并规则",
        "　8.2  command_id 幂等",
        "　8.3  ACK 状态追踪",
        "9  工具调用编排",
        "　9.1  工具清单",
        "　9.2  读工具与写工具",
        "　9.3  工具调用链与审批阈值",
        "10  经验沉淀与复用",
        "11  运行持久化与断点续跑",
        "12  运维与审计",
        "13  附录：接口与数据约定",
    ]
    p = m.doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.6
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    for el in (fld_begin, instr, fld_sep):
        run._element.append(el)
    ph = p.add_run("")
    set_cjk(ph, size=9, color=RGBColor(0x80, 0x80, 0x80))
    end_run = p.add_run()
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    end_run._element.append(fld_end)
    for line in toc:
        tp = m.doc.add_paragraph()
        tp.paragraph_format.line_spacing = 1.5
        set_cjk(tp.add_run(line), size=10)
    m.page_break()


def build_agent_intro(m: Manual) -> None:
    m.h1("1  引言")
    m.h2("1.1  编写目的")
    m.para(
        "本说明书是「探海灵眸海洋治理智能体决策与审批软件[简称:Oceanus Agent] V1.0」"
        "的操作手册，面向系统管理员、值班研判人员与审批人员，说明软件的运行环境、"
        "部署配置方法，以及事件研判、多角色智能体运行、人工审批门禁、派发与设备回执闭环、"
        "工具调用编排、经验沉淀与运行维护等功能模块的操作方法。"
    )
    m.para(
        "本软件是海洋环境治理平台的决策支柱：它不负责图像识别，也不直接驱动执行机构，"
        "而是把「发现垃圾之后该怎么办」这段决策过程做成可解释、可审批、可审计、"
        "可复用的软件能力。"
    )
    m.h2("1.2  软件背景")
    m.para(
        "近海养殖区的海漂垃圾治理中，决策环节长期依赖人工经验：发现垃圾后派哪一台设备、"
        "是否值得出动、证据不足的单子如何处理，既缺少可复现的规则，也难以留下可追溯的凭据。"
        "人工判断一旦出错，往往表现为「无谓出动」或「该清的没清」，事后无从复盘。"
    )
    m.para(
        "本软件把这段决策交给一个确定性的智能体内核：规则策略先给出可验证的基线建议，"
        "达到风险阈值的写操作必须经人工审批放行，执行结果与设备回执全程留痕，"
        "一次运行的终态还会被复盘为可复用的经验，供后续同类事件引用。"
        "由此形成「机器建议—人审批—系统执行—经验沉淀」的治理决策闭环。"
    )
    m.h2("1.3  术语与缩略语")
    m.table(
        ["术语", "说明"],
        [
            ["运行（Run）", "一次智能体决策执行，含计划加载、步骤推进、审批与终态收敛"],
            ["角色（Role）", "运行计划中的智能体分工：事件研判 Agent 与调度执行 Agent"],
            ["工具（Tool）", "智能体可调用的原子能力，带输入输出契约与风险级别"],
            ["风险级别", "只读 / 写入 / 设备指令 / 敏感；达到阈值即需人工审批"],
            ["策略门禁", "确定性规则守卫，校验角色权限、黑名单与是否需审批"],
            ["policy_denied", "策略拒绝或研判门禁拦截的错误码；被拒时不建单、事件保持原状"],
            ["人工审批", "approver 或 admin 角色对待审批决策作出批准或拒绝"],
            ["经验（Lesson）", "由 run 终态按确定性规则提炼、可跨 run 复用的处置结论"],
            ["ACK 回执", "执行设备收到指令后的确认应答，以 command_id 为幂等键"],
            ["断点续跑", "运行状态持久化后，中断的 run 可从中断点恢复推进"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.page_break()


def build_agent_overview(m: Manual) -> None:
    m.h1("2  软件概述")
    m.h2("2.1  软件定位与决策闭环")
    m.para(
        "本软件是一套面向海洋环境治理的智能体决策与审批软件，围绕四个环节构成闭环："
    )
    m.bullets([
        "机器建议：研判 Agent 检索治理政策与处置口径，结合事件证据给出研判结论与处置建议；"
        "调度执行 Agent 按候选设备池生成确定性派单方案。",
        "人审批：凡风险级别达到阈值的写操作（如创建工单）一律挂起，"
        "由 approver 或 admin 角色批准后方可继续；拒绝即终止，不产生任何副作用。",
        "系统执行：批准的决策由派发引擎落地为真实工单，经消息链路下发至执行设备，"
        "并以 ACK 回执确认设备确实收到指令。",
        "经验沉淀：每次运行到达终态后，按确定性规则从真实结果中提炼经验条目，"
        "同类事件再次触发时按条件检索并引用，让规则模式也具备可复现的进化能力。",
    ])
    m.para(
        "与直接把决策交给大模型的做法相比，本软件的差异在于把「确定性」放在第一位："
        "规则策略先给出可验证的基线决策，大模型只做增强；模型后端未配置时，"
        "规则模式照常完整工作。任何一次决策的输入、输出、依据、审批人与耗时都逐步留痕，"
        "可逐条复核。"
    )
    m.h2("2.2  功能清单")
    m.table(
        ["子系统", "主要功能"],
        [
            ["智能体运行时内核", "计划加载、步骤推进、期望校验、失败重规划、终态收敛与运行状态记录"],
            ["策略门禁", "角色权限校验、风险阈值判定、工具黑名单、计划级聚合预检"],
            ["工具层", "工具注册与版本管理、输入输出 Schema 校验、幂等结果缓存、超时控制、审计回调"],
            ["多角色协同", "研判 Agent 与调度执行 Agent 两段式计划，角色标记写入运行状态"],
            ["人工审批", "待审批队列、批准与拒绝、审批超时终止、批准后断点续跑"],
            ["派发与设备回执", "建单与近邻合并、command_id 幂等、ACK 状态追踪与超时重派"],
            ["经验沉淀", "五类经验的确定性提炼、条件检索、命中计数与置信度递增"],
            ["持久化与续跑", "运行、步骤、审批、记忆的持久化存储与中断恢复"],
            ["模型适配", "OpenAI 兼容多后端适配层，支持规则模式与模型增强两种运行模式"],
        ],
        widths_cm=[3.6, 11.9]
    )
    m.h2("2.3  技术架构")
    m.para("软件采用分层架构，主要技术选型如下：")
    m.table(
        ["层次", "技术", "用途"],
        [
            ["后端服务", "Python 3.10 / FastAPI", "异步接口服务、智能体内核宿主"],
            ["决策内核", "自研 agents 服务包", "运行时、规划、策略门禁、工具层、记忆与经验"],
            ["数据存储", "PostgreSQL / Redis", "运行与审批持久化、事件流缓存"],
            ["消息总线", "EMQX（MQTT）", "工单指令下发与设备 ACK 回执"],
            ["模型接入", "OpenAI 兼容 HTTP 接口", "可选的大模型增强规划后端"],
            ["容器化", "Docker Compose", "一键部署全部服务"],
        ],
        widths_cm=[2.8, 6.7, 6.0],
    )
    m.page_break()


def build_agent_env(m: Manual) -> None:
    m.h1("3  运行环境")
    m.h2("3.1  硬件环境")
    m.table(
        ["节点", "最低配置", "说明"],
        [
            ["平台服务器", "8 核 CPU / 16 GB 内存 / 200 GB 磁盘", "运行智能体内核、数据库与消息服务"],
            ["模型推理节点", "可选，独立 GPU 服务器或外部模型服务", "启用模型增强模式时需要"],
            ["客户端", "2 核 CPU / 4 GB 内存，1920×1080 显示器", "Chrome / Edge 浏览器访问智能体控制台"],
        ],
        widths_cm=[3.0, 6.0, 6.5]
    )
    m.h2("3.2  软件环境")
    m.table(
        ["类别", "要求"],
        [
            ["操作系统", "Linux（服务端，推荐 Ubuntu 22.04）"],
            ["容器环境", "Docker 24+ 与 Docker Compose v2"],
            ["运行时", "Python 3.10+（FastAPI 服务）"],
            ["数据库", "PostgreSQL 14+；Redis 7（事件流与缓存）"],
            ["消息中间件", "EMQX 5.x（MQTT）"],
            ["浏览器", "Chrome 100+ / Edge 100+（推荐 1920×1080 分辨率）"],
        ],
        widths_cm=[3.0, 12.5]
    )
    m.page_break()


def build_agent_deploy(m: Manual) -> None:
    m.h1("4  部署与配置")
    m.h2("4.1  服务部署")
    m.steps([
        "准备服务器并安装 Docker 与 Docker Compose；",
        "复制 .env.example 为 .env，填写数据库、消息队列与模型服务连接参数；",
        "执行 docker compose up -d 启动后端、数据库、Redis、EMQX 等服务；",
        "执行初始化脚本创建预置账号与基础数据；",
        "浏览器访问平台地址，使用管理员账号登录，进入「智能体控制台」确认工具目录与运行环境已就绪。",
    ])
    m.para(
        "智能体控制台在启动后即完成工具注册：注册表内置事件读取、设备候选筛选、"
        "派单方案生成、政策检索、研判结论生成与工单创建六类工具，并展示每个工具的版本、"
        "风险级别、幂等标志、超时上限与允许角色。"
    )
    m.h2("4.2  大模型后端接入")
    m.para(
        "软件支持两种规划模式：规则模式与模型增强模式。规则模式是默认模式，"
        "由内置的确定性规则计划驱动，不依赖任何外部服务即可完整工作；"
        "模型增强模式在规则基线之上引入大模型对计划做补充建议。"
    )
    m.table(
        ["配置项", "说明"],
        [
            ["模型服务地址", "OpenAI 兼容接口的 Base URL"],
            ["模型名称", "调用的模型标识"],
            ["接口密钥", "访问模型服务所需的密钥，经环境变量注入，不写入代码与日志"],
            ["启用开关", "未配置地址或名称时自动回落规则模式，运行记录标注为规则模式"],
        ],
        widths_cm=[3.6, 11.9]
    )
    m.para(
        "模型适配层对多后端统一封装：请求构造、响应解析、异常与超时均收敛为同一组结构化结果，"
        "模型不可用时不影响决策主链路的可用性。"
    )
    m.h2("4.3  审批角色与权限配置")
    m.para("软件预置四类角色，权限边界如下：")
    m.table(
        ["角色", "权限范围"],
        [
            ["admin", "全部权限，含审批决定与运行管理"],
            ["operator", "本辖区业务操作，可发起智能体运行"],
            ["approver", "仅用于人工审批：查看待审批队列并作出批准或拒绝"],
            ["viewer", "只读，可查看运行轨迹与审批留痕"],
        ],
        widths_cm=[3.0, 12.5]
    )
    m.para(
        "审批决定权限由服务端守卫单独校验：仅 admin 或 approver 角色可对待审批决策作出决定，"
        "其余角色的请求被拒绝。每个工具另带允许角色白名单，角色不在白名单内时调用被策略门禁拒绝。"
    )
    m.page_break()


def build_agent_assess(m: Manual) -> None:
    m.h1("5  事件研判")
    m.h2("5.1  事件接入")
    m.para(
        "边缘感知程序识别到水面漂浮垃圾后，将事件经消息链路接入平台，落库为待处置事件，"
        "初始状态为新建。事件记录包含类别、坐标、时间、置信度与证据图地址，"
        "这些字段构成后续研判的证据基础。事件本身不直接产生工单，是否派单由决策环节决定。"
    )
    m.h2("5.2  研判触发")
    m.para(
        "研判以一次智能体运行为载体触发。在智能体控制台选择事件并启动运行，"
        "选择多角色计划时，运行按两段式计划推进：第一段由事件研判 Agent 检索政策依据并给出研判结论，"
        "第二段由调度执行 Agent 完成派单。也可以在智能助手对话页用自然语言描述诉求，"
        "由助手转成结构化请求后触发运行。"
    )
    m.image(UI / "1920x1080-assistant.png", "图 5-1  智能助手对话入口（自然语言触发事件查询与研判）")
    m.steps([
        "在智能助手输入框描述诉求，例如查询某时间范围内的漂浮垃圾事件；",
        "助手返回结构化结果并附事件编号、类别与处置状态；",
        "对需要处置的事件，进一步发起智能体运行进入研判与派单流程。",
    ])
    m.page_break()
    m.h2("5.3  研判结论查看")
    m.para(
        "研判 Agent 的政策检索工具会从知识库中检索本辖区治理政策与处置口径，"
        "形成可引用的依据条目；研判结论工具再综合事件证据与政策依据，"
        "输出风险级别、建议处置动作、判定依据列表与置信度。"
    )
    m.table(
        ["研判输出", "含义"],
        [
            ["risk_level", "风险级别：normal 表示可正常处置，high 表示需人工复核"],
            ["recommended_action", "建议动作：dispatch（派单）、merge_first（优先合并）、manual_review（转人工）"],
            ["basis", "判定依据列表，逐条列出证据与政策命中情况"],
            ["confidence", "识别置信度，低于自动派单下限时不下自动派单结论"],
        ],
        widths_cm=[3.8, 11.7]
    )
    m.para(
        "研判不是形式环节，它带一道真实门禁：当事件缺少证据图，或识别置信度低于自动派单下限时，"
        "研判结论为转人工复核，运行随即安全终止，事件保持新建状态、不产生工单。"
        "这使「不该自动派单的单子」被拦在决策环节之外。"
    )
    m.page_break()


def build_agent_run(m: Manual) -> None:
    m.h1("6  多角色智能体运行")
    m.h2("6.1  角色说明")
    m.para(
        "本篇软件的多角色协同由两个角色构成，角色是计划项的元数据，"
        "由内核记入运行状态，不改变步骤表结构："
    )
    m.table(
        ["角色", "承担的工具步骤", "职责"],
        [
            ["事件研判 Agent", "政策检索、研判结论生成", "检索治理依据并给出研判结论与处置建议"],
            ["调度执行 Agent", "事件读取、设备候选筛选、派单方案生成、工单创建", "按候选设备池生成方案并落地工单"],
        ],
        widths_cm=[3.4, 6.4, 5.7]
    )
    m.para(
        "两个角色共用同一套运行时内核：计划加载、逐步执行、期望校验、失败重规划与终态收敛。"
        "运行计划分为单角色与多角色两种变体，单角色计划仅由调度执行 Agent 的四个步骤构成，"
        "多角色计划在前面追加研判 Agent 的两个步骤。"
    )
    m.h2("6.2  运行列表")
    m.para(
        "智能体控制台的运行列表按创建时间倒序展示全部运行记录，"
        "支持按状态筛选，并可查看当前生效的策略版本与运行模式。"
    )
    m.image(FIGS / "agent-console-overview.png",
            "图 6-1  智能体运行控制台（运行列表、审批队列、工具目录与评测摘要）")
    m.bullets([
        "列表列：运行编号、事件、计划模式、状态、当前步骤与创建时间；",
        "顶部指标：活跃运行数、累计运行数、待审批数、已建工单数与运行时长；",
        "模式标识：规则模式与模型增强模式分列显示，并展示当前策略版本。",
    ])
    m.page_break()
    m.h2("6.3  运行详情与步骤追踪")
    m.para(
        "进入运行详情可查看该次运行的完整轨迹。每个步骤按执行顺序记录：步骤序号、"
        "所属角色、调用的工具与版本、输入摘要、输出摘要、耗时、幂等命中标志与错误码。"
        "工具每次尝试都单独落一条步骤记录，因此重试过程同样可追溯。"
    )
    m.table(
        ["轨迹要素", "说明"],
        [
            ["步骤号", "自增序号，与运行内步骤顺序一一对应"],
            ["角色", "该步骤由哪个智能体角色承担"],
            ["工具与版本", "调用的工具名及其版本号，便于跨版本复核"],
            ["输入/输出摘要", "参数键摘要与输出摘要，原始敏感载荷不留存"],
            ["耗时与幂等", "单次调用耗时；命中幂等缓存时标注为复用结果"],
            ["错误码", "结构化错误码，取值限定在冻结清单内"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.image(FIGS / "agent-run-steps.png",
            "图 6-2  一次成功运行的完整步骤轨迹（多角色计划，含审批放行、派单与建单）")
    m.para(
        "运行终态包括成功、取消与各类结构化错误。内核为每个计划步骤预设期望条件"
        "（如事件可派单、候选设备数不少于一台、方案给出机器人标识、工单标识非空），"
        "期望不满足即按预设错误码终止或触发一次重规划，避免带病继续执行。"
    )
    m.page_break()


def build_agent_approval(m: Manual) -> None:
    m.h1("7  人工审批门禁")
    m.h2("7.1  待审批队列")
    m.para(
        "凡风险级别达到审批阈值的工具调用，内核不直接执行，而是挂起该步骤并生成一条待审批记录，"
        "运行状态转为等待审批。审批人员从智能体控制台的审批队列进入处理，"
        "队列展示运行编号、工具、风险级别、申请人、申请时间与等待时长。"
    )
    m.image(FIGS / "agent-approval-queue.png",
            "图 7-1  审批队列（approver 角色待决定入口；图示 5 条待决定记录）", width_cm=13.5)
    m.para(
        "挂起期间运行保持等待状态，不消耗后续步骤。审批记录本身是独立实体，"
        "带唯一标识与状态字段，可在审批留痕中单独查询。"
    )
    m.h2("7.2  批准与拒绝")
    m.para("审批人员对待审批决策作出决定，两种结果的处理路径完全不同：")
    m.table(
        ["决定", "系统行为"],
        [
            ["批准", "该步骤解除挂起并立即执行，运行从中断点继续推进直至终态"],
            ["拒绝", "运行以审批拒绝错误码终止，被挂起的写操作不执行，不产生工单"],
            ["超时未决定", "按审批超时错误码终止运行，同样不产生任何副作用"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.para(
        "审批决定必须由 admin 或 approver 角色作出，服务端在写入决定前再次校验角色，"
        "并记录决定人、决定时间与决定理由。批准后的续跑沿用运行中断点的状态快照，"
        "已完成的步骤不会重复执行。"
    )
    m.h2("7.3  策略拒绝与研判门禁")
    m.para(
        "除人工拒绝外，软件还有两道自动门禁，三者都表现为「不建单」，但成因不同，"
        "在轨迹里以不同错误码区分："
    )
    m.table(
        ["门禁", "触发条件", "错误码与后果"],
        [
            ["策略拒绝", "调用角色不在工具允许角色白名单内，或工具被列入策略黑名单",
             "policy_denied；该步骤不执行，运行终止，不建单"],
            ["研判门禁", "事件缺少证据图，或识别置信度低于自动派单下限，研判结论为转人工复核",
             "policy_denied；运行安全终止，事件保持新建状态，不建单"],
            ["审批拒绝", "审批人员对写操作作出拒绝决定", "approval_rejected；写操作不执行，不建单"],
        ],
        widths_cm=[2.8, 6.9, 5.8]
    )
    m.para(
        "以多角色计划为例，研判 Agent 的结论步骤对建议动作设定期望：只有派单或优先合并才继续，"
        "转人工复核即安全终止。因此评审人员在轨迹中能直接看到「这一次为什么没建单」"
        "——是策略不允许、证据不足，还是审批未通过。"
    )
    m.image(FIGS / "agent-policy-denied.png",
            "图 7-2  研判门禁终止的运行轨迹（研判结论为转人工复核，运行安全终止、不建单）")
    m.page_break()


def build_agent_dispatch(m: Manual) -> None:
    m.h1("8  派发引擎与设备 ACK 闭环")
    m.h2("8.1  建单与合并规则")
    m.para(
        "派单方案由确定性规则生成：先读取事件状态与类别，再筛选在线、电量与仓容均合格的候选设备，"
        "最后按同类别顺路加权与距离综合选择执行设备。方案输出机器人标识、距离与选择理由，"
        "理由随轨迹留痕，便于复核为什么选了这一台。"
    )
    m.para(
        "工单创建步骤会先检查合并窗口：若事件近邻已存在同类活跃工单，则并入既有工单而非新建，"
        "减少重复出勤。合并与新建两种结果都会在输出中标注动作类型与是否新建。"
    )
    m.image(UI / "1920x1080-tasks.png", "图 8-1  工单看板（派单结果与状态流转）")
    m.h2("8.2  command_id 幂等")
    m.para(
        "工单下发指令以 command_id 为幂等键，取值规则为「cmd_」加任务标识。"
        "回执账本以 command_id 为准：首次收到回执时建立一条规范记录，"
        "同一 command_id 的后续重复回执只累计次数并标记为重复，不重复建账。"
        "由此保证设备因网络抖动重复上报时，平台侧账本始终唯一。"
    )
    m.h2("8.3  ACK 状态追踪")
    m.para(
        "指令经消息链路下发后，平台等待执行设备回传确认应答，主题为设备指令确认通道。"
        "回执解析优先使用冻结信封字段，任务标识既可取自顶层兼容字段，"
        "也可由 command_id 反推，兼容不同固件版本的上报格式。"
    )
    m.bullets([
        "已确认：设备回执到达且账本记录为首次，工单进入执行中；",
        "重复回执：同一 command_id 再次到达，只累计次数，不改变工单状态；",
        "确认超时：超过等待时限仍未收到回执，平台触发超时处理，换设备重新派发。",
    ])
    m.page_break()


def build_agent_tools(m: Manual) -> None:
    m.h1("9  工具调用编排")
    m.h2("9.1  工具清单")
    m.para(
        "软件内置六类决策工具，全部带版本号、输入输出契约、风险级别、幂等标志、"
        "超时上限与允许角色。工具目录可在智能体控制台直接查看。"
    )
    m.image(FIGS / "agent-tool-catalog.png",
            "图 9-1  工具目录（工具、版本、风险、幂等、超时与允许角色）", width_cm=15.0)
    m.table(
        ["工具", "版本", "风险", "幂等", "超时", "允许角色"],
        [
            ["event.get", "1.0.0", "只读", "否", "1.00s", "operator / admin"],
            ["device.query_available", "1.0.0", "只读", "否", "1.00s", "operator / admin"],
            ["dispatch.plan", "1.0.0", "只读", "否", "1.00s", "operator / admin"],
            ["policy.lookup", "1.0.0", "只读", "否", "1.00s", "operator / admin"],
            ["analysis.assess", "1.0.0", "只读", "否", "1.00s", "operator / admin"],
            ["task.create_or_merge", "1.0.0", "写入", "否", "1.00s", "operator / admin"],
        ],
        widths_cm=[4.4, 1.7, 1.6, 1.3, 1.6, 3.9]
    )
    m.h2("9.2  读工具与写工具")
    m.para(
        "六个工具按风险级别分为两类：事件读取、设备候选筛选、派单方案生成、政策检索、"
        "研判结论生成五者为只读工具，只读取业务快照、不改变任何状态；"
        "工单创建或合并为写入工具，是本软件中唯一会改变业务数据、"
        "因而唯一需要人工审批放行的工具。"
    )
    m.para(
        "只读工具的输入输出均为请求快照，不启用跨请求缓存，保证同一时刻读取到的结果可复现；"
        "写入工具关闭幂等缓存，改由工单侧的合并窗口与 command_id 幂等键保证不重复建单。"
    )
    m.h2("9.3  工具调用链与审批阈值")
    m.para("每次工具调用的执行顺序固定，任一环节不通过即返回结构化错误码，不进入下一环节：")
    m.steps([
        "参数 Schema 校验：输入不满足契约时返回输入不合法错误码；",
        "角色与策略守卫：校验角色白名单与黑名单，并按风险级别判定是否需人工审批；",
        "幂等检查：幂等工具且命中成功结果缓存时直接复用，不再执行；",
        "超时控制与执行：调用工具处理器，记录单次尝试耗时；",
        "输出 Schema 校验：输出不满足契约时返回输出不合法错误码；",
        "幂等结果缓存与审计留痕：写入成功结果缓存，并记录输入输出摘要哈希与耗时。",
    ])
    m.para(
        "审批阈值由运行配置决定：默认对写入级别及以上（写入、设备指令、敏感）挂起审批；"
        "可放宽为仅对设备指令与敏感级别审批。阈值随策略版本一并留痕，"
        "使同一份轨迹在不同策略下的判定差异可被解释。"
    )
    m.page_break()


def build_agent_lessons(m: Manual) -> None:
    m.h1("10  经验沉淀与复用")
    m.para(
        "经验机制让确定性规则模式也具备可进化的闭环：每次运行到达终态后，"
        "内核按可复现的规则从真实结果中提炼经验条目，同类事件再次触发时按条件检索并引用。"
        "经验的提炼只看 run 的真实终态，不看模型输出，因此同样的运行永远得到同样的结论，"
        "可离线复现。"
    )
    m.table(
        ["经验种类", "提炼条件", "处置建议", "初始置信度"],
        [
            ["合并优先", "近邻已有同类活跃工单", "优先并入既有工单而非新建，减少重复出勤", "0.85"],
            ["重规划可恢复", "首次工具调用失败后经重规划恢复", "首次调用失败时允许一次重规划", "0.60"],
            ["重点类别优先", "该类别属政策重点治理类别", "优先派单并优先选择同类别顺路设备", "0.80"],
            ["资源不足待命", "候选设备全部不合格导致无法派单", "先补池或等待充电清仓，不立即重试", "0.75"],
            ["证据不足转人工", "同类事件曾因证据不足被研判拦下", "缺证据图或置信度不达标时转人工复核", "0.90"],
        ],
        widths_cm=[2.6, 4.6, 5.7, 2.6]
    )
    m.para(
        "经验条目的置信度不是固定常数：初始值由该种类结论的证据强度决定，"
        "之后随命中次数单调上调并设有上限，规则模式的经验始终作为启发式结论存在。"
        "每条经验带适用条件谓词，检索时按事件类别与上下文条件真实过滤，不满足条件即不引用。"
    )
    m.para(
        "被引用的经验会在本次运行的轨迹中留痕，可查到「这一次参考了哪几条经验、"
        "置信度是多少」。经验与运行记忆共用同一套存储与脱敏纪律，"
        "进程运行期间累积，重启后清零。"
    )
    m.page_break()


def build_agent_persistence(m: Manual) -> None:
    m.h1("11  运行持久化与断点续跑")
    m.para(
        "运行、步骤、审批与记忆四类对象均有独立的持久化仓储。默认使用内存仓储，"
        "在未接入数据库时亦可完整演示与联测；配置开启后切换为数据库仓储，"
        "运行状态跨进程重启保留。仓储初始化失败时自动回落内存实现并告警，"
        "不影响决策主链路的可用性。"
    )
    m.table(
        ["对象", "持久化内容"],
        [
            ["运行", "运行标识、事件、角色、状态、策略版本、运行模式、创建与更新时刻"],
            ["步骤", "步骤号、角色、工具与版本、输入输出摘要、耗时、幂等标志、错误码"],
            ["审批", "审批标识、关联运行与步骤、工具、风险级别、状态、决定人与决定理由"],
            ["记忆", "运行级工作记忆与跨运行经验条目，含作用域、种类与置信度"],
        ],
        widths_cm=[2.8, 12.7]
    )
    m.para(
        "断点续跑依赖运行状态快照：审批挂起或运行中断后，从中断点恢复时"
        "已完成步骤的状态与输出直接复用，未完成步骤按原计划继续推进。"
        "续跑不重新执行已成功步骤，因此不会重复建单或重复调用只读工具。"
    )
    m.para(
        "运行状态中额外记录每个步骤的角色归属，使恢复后的轨迹仍能还原"
        "哪一步由哪个智能体角色完成，多角色运行在中断续跑后依然可读。"
    )
    m.page_break()


def build_agent_ops(m: Manual) -> None:
    m.h1("12  运维与审计")
    m.para(
        "本软件的运维重点是运行可观测与决定可追溯。控制台提供运行列表、"
        "步骤轨迹、审批留痕与工具目录四类视图，配合运行日志可覆盖一次决策的全过程。"
    )
    m.h2("12.1  审计留痕")
    m.table(
        ["留痕项", "内容"],
        [
            ["运行轨迹", "每次运行的全部步骤及其输入输出摘要、耗时与错误码"],
            ["工具审计", "工具调用成功时记录工具名、版本、角色、输入输出摘要哈希与耗时"],
            ["审批留痕", "审批决定人、决定时间、决定结果与理由"],
            ["策略版本", "每次运行判定所依据的策略版本号，随运行记录保存"],
            ["脱敏纪律", "敏感载荷只保留键名摘要，不落原始内容"],
        ],
        widths_cm=[3.0, 12.5]
    )
    m.h2("12.2  常见问题与处理")
    m.table(
        ["现象", "可能原因", "处理方法"],
        [
            ["运行一直停在等待审批", "写操作挂起且尚未有人处理", "由 approver 或 admin 角色在审批队列作出决定"],
            ["运行被终止且未建单", "策略拒绝、研判门禁或审批拒绝", "在运行轨迹中查看错误码，据此区分成因"],
            ["研判结论为转人工复核", "事件缺证据图或置信度低于下限", "补齐证据或转人工核实后重新发起运行"],
            ["派单失败无候选设备", "设备离线、电量或仓容不合格", "在设备页恢复设备在线状态，或等待清仓与充电"],
            ["工单长时间未确认", "执行设备未回传 ACK 回执", "等待超时自动换设备重派，或人工干预重派"],
            ["模型增强模式不可用", "模型服务地址或名称未配置", "补齐模型连接参数；未配置时规则模式照常可用"],
        ],
        widths_cm=[3.4, 5.2, 6.9]
    )
    m.page_break()


def build_agent_appendix(m: Manual) -> None:
    m.h1("13  附录：接口与数据约定")
    m.para("软件对外提供 REST API 与消息链路，主要约定如下：")
    m.table(
        ["类别", "约定"],
        [
            ["认证", "登录签发令牌，后续请求携带 Authorization 请求头"],
            ["运行接口", "创建运行、查询运行、查询步骤轨迹、取消运行"],
            ["审批接口", "查询待审批队列、批准或拒绝；决定权限限定 admin 与 approver"],
            ["指令下发", "经 MQTT 下发工单指令，command_id 取值 cmd_ 加任务标识"],
            ["回执上报", "设备经 MQTT 上报确认应答，平台以 command_id 建账并去重"],
            ["错误码", "结构化错误码固定为 12 个取值，轨迹与终态只允许出现冻结值"],
        ],
        widths_cm=[3.0, 12.5]
    )
    m.para(
        "本说明书随软件版本迭代更新。如与系统实际界面存在差异，以软件实际运行版本为准。"
    )


# ===========================================================================
# 拆分登记第 4 篇：水面垃圾打捞机械臂控制软件（机器人本体嵌入式控制）
# ===========================================================================
def build_arm_cover(m: Manual) -> None:
    for _ in range(5):
        m.doc.add_paragraph()
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(ARM_FULL_NAME), size=26, color=NAVY, bold=True)
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(f"（简称：{ARM_SHORT_NAME}）"), size=16, color=OCEAN)
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(VERSION), size=20, color=NAVY, bold=True)
    for _ in range(2):
        m.doc.add_paragraph()
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run("软 件 说 明 书"), size=22, color=DARK, bold=True)
    for _ in range(6):
        m.doc.add_paragraph()
    for line in ("文档类别：操作手册",
                 "著作权人：福州理工学院",
                 "运行位置：水面打捞机器人本体工控机",
                 "编写日期：2026 年 10 月"):
        p = m.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cjk(p.add_run(line), size=12, color=GRAY)
    m.page_break()


def build_arm_toc(m: Manual) -> None:
    m.h1("目  录")
    toc = [
        "1  引言",
        "　1.1  编写目的",
        "　1.2  软件背景与定位",
        "　1.3  术语与缩略语",
        "2  软件概述",
        "　2.1  在治理闭环中的位置",
        "　2.2  功能清单",
        "　2.3  技术架构",
        "3  运行环境",
        "　3.1  硬件环境",
        "　3.2  软件环境",
        "4  部署与硬件连接",
        "　4.1  工控机与串口准备",
        "　4.2  控制台界面",
        "　4.3  本体配置说明",
        "　4.4  启动与自检",
        "5  MQTT 指令与 ACK 链路",
        "　5.1  主题约定",
        "　5.2  指令幂等与过期拒绝",
        "　5.3  超时重试与断链保护",
        "6  抓取动作编排",
        "　6.1  识别—定位—抓取—投放序列",
        "　6.2  动作参数调整",
        "7  ROS 运动学驱动",
        "　7.1  关节空间控制",
        "　7.2  关节限位与机械爪协同",
        "8  幻尔总线舵机协议",
        "　8.1  串口总线与厂商协议",
        "　8.2  动作序列示教工具",
        "9  仿真与真机双模",
        "10  手眼标定与视觉引导",
        "11  安全与故障排查",
        "12  附录：接口与数据约定",
    ]
    p = m.doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.6
    run = p.add_run()
    for tag, attr, val in (
        ("w:fldChar", "w:fldCharType", "begin"),
        ("w:instrText", None, 'TOC \\o "1-2" \\h \\z \\u'),
        ("w:fldChar", "w:fldCharType", "separate"),
    ):
        el = OxmlElement(tag)
        if attr:
            el.set(qn(attr), val)
        else:
            el.set(qn("xml:space"), "preserve")
            el.text = val
        run._element.append(el)
    ph = p.add_run("")
    set_cjk(ph, size=9, color=RGBColor(0x80, 0x80, 0x80))
    end_run = p.add_run()
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    end_run._element.append(fld_end)
    for line in toc:
        tp = m.doc.add_paragraph()
        tp.paragraph_format.line_spacing = 1.5
        set_cjk(tp.add_run(line), size=10)
    m.page_break()


def build_arm_intro(m: Manual) -> None:
    m.h1("1  引言")
    m.h2("1.1  编写目的")
    m.para(
        "本说明书是「探海灵眸水面垃圾打捞机械臂控制软件[简称:Oceanus Arm] V1.0」"
        "的操作手册，面向机器人本体操作员、现场部署人员与机械臂调试人员，"
        "说明软件的运行环境、部署接线方式、配置项含义、指令链路约定、"
        "动作编排与标定流程，以及常见故障的排查方法。"
    )
    m.h2("1.2  软件背景与定位")
    m.para(
        "海漂垃圾治理的完整链路是「岸基感知—平台决策—机器人执行—数据回传」，"
        "其中最后一步的物理动作必须在机器人本体上完成。本软件即部署于水面打捞"
        "机器人本体工控机的执行端控制软件：它不承担识别与决策，只做一件事 —— "
        "把云端下发的处置指令安全地翻译成机械臂的关节运动与串口舵机动作，"
        "并把执行结果以 ACK 与遥测的形式回传给平台。"
    )
    m.para(
        "软件与平台之间只经 MQTT 指令/ACK 解耦，不共享数据库、不直接调用平台接口。"
        "这一边界使执行端可替换：更换机械臂品牌只需在本体侧切换驱动后端，"
        "平台与报文契约零改动。"
    )
    m.h2("1.3  术语与缩略语")
    m.table(
        ["术语", "说明"],
        [
            ["桥接（Bridge）", "本软件的核心：接收平台指令、驱动机械臂、回传 ACK 与遥测"],
            ["指令（Command）", "平台下发的一条动作请求，带全局唯一 command_id"],
            ["ACK", "执行端对指令的确认应答，含 accepted 标志与拒绝原因"],
            ["幂等去重", "同一 command_id 重复到达时只执行一次，重发返回既有 ACK"],
            ["驱动后端（backend）", "机械臂驱动的实现选择：仿真、HTTP、ROS、总线舵机"],
            ["示教", "人工拖动或逐步发送方式记录一组舵机位置，形成可回放的动作序列"],
            ["关节空间", "以各关节角度（弧度）描述机械臂姿态"],
            ["手眼标定", "求取相机坐标系到机械臂坐标系的变换，用于视觉引导定位"],
            ["LWT", "MQTT 遗嘱消息，设备异常掉线时由 Broker 代发离线状态"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.page_break()


def build_arm_overview(m: Manual) -> None:
    m.h1("2  软件概述")
    m.h2("2.1  在治理闭环中的位置")
    m.para(
        "本软件位于治理闭环的「执行」环节。上游是平台派发的打捞工单，"
        "下游是机械臂的物理动作。软件内部的职责划分为三层："
    )
    m.bullets([
        "指令层：MQTT 收发、指令解析与校验、幂等去重、ACK 与进度回传；",
        "编排层：把一次打捞工单展开为「识别—定位—抓取—投放」的动作序列；",
        "驱动层：把动作序列落到具体硬件 —— 仿真器、HTTP 端点、ROS 控制栈或串口舵机。",
    ])
    m.para(
        "分层的好处是硬件可替换。同一份指令报文，驱动后端可在配置文件里改成 "
        "simulated / http / ros_arm_control / hiwonder_bus_servo 四者之一，"
        "而指令层与编排层代码不变。"
    )
    m.h2("2.2  功能清单")
    m.table(
        ["模块", "主要功能"],
        [
            ["指令桥接", "主题订阅、报文校验、command_id 幂等、过期指令拒绝、ACK 发布"],
            ["动作编排", "打捞序列展开、进度上报、投放与重量统计、复核结果回传"],
            ["ROS 运动学驱动", "复用厂商 ros_control 控制栈，关节空间轨迹下发，关节角回读"],
            ["总线舵机驱动", "厂商串口协议适配、舵机 ID 配置、动作序列回放、逐舵机遥测"],
            ["商城/仿真驱动", "无硬件自检：确定性返回打捞结果，供全链路演练"],
            ["示教工具", "逐步记录舵机位置并导出动作序列文件，供驱动加载"],
            ["手眼标定", "标定板采图、内参求解、像素—平面映射，视觉引导定位"],
            ["双模回退", "真机断电或依赖缺失时自动降级，全流程仍可仿真运行"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.h2("2.3  技术架构")
    m.para("软件采用分层架构，主要技术选型如下：")
    m.table(
        ["层次", "技术", "用途"],
        [
            ["运行平台", "工控机（x86_64 / ARM64）", "随机器人本体部署"],
            ["运行时", "Python 3.10", "桥接服务主进程"],
            ["通信", "paho-mqtt / EMQX 5", "平台指令接入与 ACK 回传"],
            ["机械臂控制", "ROS 2 Humble / ros_control", "关节空间轨迹与关节角回读"],
            ["串口舵机", "pyserial", "幻尔总线舵机厂商协议（半双工串口）"],
            ["配置", "YAML", "device_id、驱动后端、串口、关节与限位"],
            ["视觉标定", "OpenCV", "棋盘格标定与像素—平面映射"],
        ],
        widths_cm=[2.8, 6.4, 6.3],
    )
    m.page_break()


def build_arm_env(m: Manual) -> None:
    m.h1("3  运行环境")
    m.h2("3.1  硬件环境")
    m.table(
        ["部件", "要求", "说明"],
        [
            ["本体工控机", "4 核 CPU / 8 GB 内存 / 32 GB 存储",
             "随机器人本体，运行本软件；树莓派 4B 及以上或同等 x86 工控机"],
            ["机械臂", "6 自由度机型（joint1..joint5 + r_joint）或幻尔总线舵机臂",
             "ROS 控制栈机型与幻尔串口机型均受支持"],
            ["总线舵机", "幻尔 Hiwonder 总线舵机，ID 1~4（可按需扩展）",
             "半双工串口 /dev/ttyAMA0，波特率 1000000"],
            ["摄像头", "标定用 USB 摄像头或机械臂原装相机", "手眼标定与视觉引导定位"],
            ["标定板", "棋盘格，默认 9×6 内角点，方格边长 0.03 m", "标定时置于工作平面"],
        ],
        widths_cm=[2.6, 6.6, 6.3]
    )
    m.h2("3.2  软件环境")
    m.table(
        ["类别", "要求"],
        [
            ["操作系统", "Linux（Ubuntu 22.04 推荐；幻尔机型随机型附带 Raspberry Pi OS）"],
            ["Python", "3.10 及以上"],
            ["ROS", "ROS 2 Humble（走 ROS 驱动后端时必需；仿真模式可不装）"],
            ["消息中间件", "EMQX 5.x（MQTT）"],
            ["Python 依赖", "paho-mqtt、pyserial、PyYAML、OpenCV（标定与视觉引导）"],
            ["厂商 SDK", "幻尔总线舵机 SDK（走串口驱动后端时必需）"],
        ],
        widths_cm=[3.0, 12.5]
    )
    m.page_break()


def build_arm_deploy(m: Manual) -> None:
    m.h1("4  部署与硬件连接")
    m.h2("4.1  工控机与串口准备")
    m.steps([
        "在工控机上安装 Python 3.10 及以上版本，并安装 requirements.txt 中的依赖；",
        "连接机械臂供电与通信线缆。走 ROS 后端时确认工控机与机械臂在同一 ROS 域；"
        "走串口后端时把舵机总线接到 /dev/ttyAMA0；",
        "执行 sudo systemctl stop armpi_fpv_bringup 停掉厂商常驻节点 —— "
        "串口为半双工独占总线，厂商节点在跑会抢占，直连必然失败；",
        "确认串口权限：将运行账户加入 dialout 组，否则打开串口会报 Permission denied；",
        "确认机械臂四周无人、无遮挡，急停按钮可触及。",
    ])
    m.para(
        "★ 优先选择 ROS 后端。厂商的 hiwonder_servo_manager 节点已持有串口，"
        "直连方式与厂商图形界面互斥，只能二选一；ROS 后端复用厂商的 ros_control "
        "action，可与厂商程序共存，且拿到的是有物理意义的关节角（弧度）。"
    )
    m.h2("4.2  控制台界面")
    m.para(
        "控制台是本体侧的可视面板，用于确认执行端配置是否就绪。面板顶部显示"
        "接入方式与可达状态：当跳转地址配置为 nx:// 协议时，标签显示为"
        "「nx 协议」，表示点击后将由本机 NoMachine 客户端唤起远程桌面。"
        "面板中部列出四种可替换的执行后端，当前生效的一个以高亮标出，"
        "并注明当前工单号与目标坐标；面板底部为「舵机遥测」区，"
        "逐舵机显示电压、温度与位置。"
    )
    m.image(ARM_SHOT / "arm-console-top.png",
            "图 4-1  机械臂执行端控制台（接入方式与可替换的执行后端）", width_cm=12.2)
    m.image(ARM_SHOT / "arm-console-head.png",
            "图 4-2  跳转目标已配置态（面板转为可达状态，标签显示 nx 协议）",
            width_cm=15.5)
    m.para(
        "面板底部的「舵机遥测」区逐舵机显示电压、温度与位置。这三项读数由机械臂"
        "驱动回读自舵机本身，而不是平台侧自报，因此可以作为「真机确实执行了」的"
        "证据。任一舵机读取失败只影响该行，不会让整个面板变空。"
    )
    m.image(ARM_SHOT / "arm-console-servos.png",
            "图 4-3  舵机遥测区（逐舵机回读的电压 / 温度 / 位置）", width_cm=12.2)
    # ★ 图注**不得**点明「哪些行被排除」。初版写成「『登录账号』等凭据栏未纳入
    #   图示范围」，等于向任何读者宣告此处原本有凭据 —— 排除本身是妥当的，
    #   宣布排除反而把注意力引过去。公开登记文件里应当既不显示、也不提及。
    m.caption_note(
        "注：图 4-1~4-3 取自软件实际运行界面；软件名与跳转地址为现场配置值。"
    )
    m.page_break()
    m.h2("4.3  本体配置说明")
    m.para(
        "本体行为全部由 edge/arm_bridge/config.yaml 决定。关键配置项如下，"
        "修改后需重启桥接服务生效。"
    )
    m.table(
        ["配置项", "含义与取值"],
        [
            ["site_id / device_id", "点位与设备标识；device_id 决定 MQTT 主题前缀"],
            ["mqtt.host / port", "MQTT Broker 地址与端口"],
            ["mqtt.username / password", "设备接入凭据；部署时须替换默认值"],
            ["mqtt.use_lwt", "是否启用遗嘱消息，异常掉线时由 Broker 代发离线状态"],
            ["driver.backend", "驱动后端：simulated / http / ros_arm_control / hiwonder_bus_servo"],
            ["vendors.<name>.kind", "厂商驱动类型，与 backend 名称对应"],
            ["serial_port / baudrate", "串口设备与波特率（总线舵机默认 /dev/ttyAMA0 @ 1000000）"],
            ["servo_ids", "参与动作的舵机编号列表"],
            ["home_positions", "各舵机回零位置（0~1000 脉宽量程）"],
            ["pick_sequence", "抓取动作序列：每步含 duration 与 positions"],
            ["pick_sequence_file", "改用外部示教文件时的路径（与内联序列二选一）"],
            ["arm_controller / gripper_controller", "ROS 控制栈的机械臂与机械爪控制器名"],
            ["home_rad / pick_rad", "ROS 后端的回零与抓取关节角（弧度）"],
        ],
        widths_cm=[5.0, 10.5]
    )
    m.caption_note(
        "★ pick_rad 是默认值，真机首跑前必须示教确认 —— 直接沿用回零位当抓取位会抓空。"
        "pick_sequence 与 pick_sequence_file 同时配置会被拒绝，避免加载来源歧义。"
    )
    m.h2("4.4  启动与自检")
    m.steps([
        "确认 config.yaml 中的 device_id 与驱动后端；",
        "执行 python -m edge.arm_bridge.main 启动桥接服务；",
        "服务上线后向 robot/<device_id>/status 发布在线状态，平台据此判断设备可达；",
        "在控制台面板确认跳转目标与执行后端；",
        "无真机时先把 backend 设为 simulated 跑通全链路，再切换真机后端。",
    ])
    m.page_break()


def build_arm_mqtt(m: Manual) -> None:
    m.h1("5  MQTT 指令与 ACK 链路")
    m.h2("5.1  主题约定")
    m.para(
        "桥接服务只订阅两个主题、发布三个主题，全部以 device_id 为前缀，"
        "避免多台设备共用 Broker 时相互串扰。所有报文为 JSON，QoS 1。"
    )
    m.table(
        ["主题", "方向", "用途"],
        [
            ["robot/{device_id}/task", "订阅", "平台下发的打捞工单"],
            ["robot/{device_id}/cmd", "订阅", "平台下发的控制指令（含急停）"],
            ["robot/{device_id}/cmd/ack", "发布", "指令确认应答，含 accepted 与拒绝原因"],
            ["robot/{device_id}/task/progress", "发布", "作业进度与完成结果"],
            ["robot/{device_id}/telemetry", "发布", "设备遥测：状态、位置、舵机回读"],
            ["marine/{site_id}/{device_id}/status", "发布", "遗嘱主题，异常掉线时由 Broker 代发"],
        ],
        widths_cm=[5.4, 1.6, 8.5]
    )
    m.h2("5.2  指令幂等与过期拒绝")
    m.para(
        "移动网络下平台重发指令是常态，因此执行端必须自己保证「同一条指令只执行一次」。"
        "桥接层以 command_id 为键记录已发布的 ACK：重复到达的指令不再驱动硬件，"
        "直接重发既有 ACK，并记一条 duplicate_command 事件。此外，报文校验不过、"
        "设备号不匹配、目标缺失、动作未知、指令已过期的情形一律拒绝，"
        "并在 ACK 中给出可读的拒绝原因，便于平台侧定位。"
    )
    m.h2("5.3  超时重试与断链保护")
    m.para(
        "设备异常掉电时，Broker 会依据遗嘱消息代发离线状态，平台无需等指令超时"
        "即可感知设备不可达。执行端侧，指令处理过程中的任何驱动异常都会转为 "
        "pick_failed 事件与拒绝 ACK，不会让桥接进程崩溃；掉线重连后自动重新订阅"
        "全部主题，无需人工干预。"
    )
    m.page_break()


def build_arm_pick(m: Manual) -> None:
    m.h1("6  抓取动作编排")
    m.h2("6.1  识别—定位—抓取—投放序列")
    m.para(
        "一次打捞工单在本体内被展开为四步动作序列。平台只下发目标坐标与优先级，"
        "具体动作由本体编排，这样更换机械臂机型时平台侧无需改动。"
    )
    m.table(
        ["步骤", "动作", "本体侧行为"],
        [
            ["1  识别", "接收平台工单", "校验报文，解析目标坐标与优先级"],
            ["2  定位", "对准目标", "下发轨迹把末端移向目标上方；标定后可按像素反算平面坐标"],
            ["3  抓取", "下探并收拢", "下探至抓取姿态，机械爪收拢；抓取姿态须经示教确认"],
            ["4  投放", "回零并计数", "抬臂回零、张开机械爪，累计打捞重量并回传复核结果"],
        ],
        widths_cm=[2.6, 3.4, 9.5]
    )
    m.h2("6.2  动作参数调整")
    m.para(
        "动作参数集中在 config.yaml 中调整，无需改代码：每步的 duration 控制该步"
        "耗时（越大越慢越稳），positions 给出该步各舵机的目标位置。"
        "调参的一般顺序是先慢后快：先用较长 duration 确认轨迹无碰撞，"
        "再逐步压缩到现场可接受的节拍。机械爪在 ROS 后端的机型上由独立的 "
        "gripper_controller 驱动，与机械臂本体的 arm_controller 分开，"
        "因此夹持力与开合时机可独立调整。"
    )
    m.page_break()


def build_arm_ros(m: Manual) -> None:
    m.h1("7  ROS 运动学驱动")
    m.h2("7.1  关节空间控制")
    m.para(
        "ROS 后端复用厂商的 ros_control 控制栈，通过 action 下发关节空间轨迹。"
        "每次下发携带关节名列表与目标角度（弧度），由控制器完成插补，"
        "本体只负责给出目标位姿，不自行积分。回零位取厂商实测标定值，"
        "实机标定为 [0°, 30°, -78°, -100.8°, 0°, -102°]，"
        "折算弧度 [0.0, 0.5236, -1.3614, -1.7593, 0.0, -1.7802]。"
    )
    m.para(
        "关节角通过订阅 joint_states 回读，映射为逐舵机读数后进入遥测上报。"
        "这一路数据来自机械臂驱动本身而非平台自报，因此可以作为"
        "「真机确实执行了」的证据。"
    )
    m.h2("7.2  关节限位与机械爪协同")
    m.para(
        "轨迹下发前做限位检查，超限的目标不会下发到控制器。机械爪在厂商机型上"
        "挂在独立的 gripper_controller 下，抓取流程为「下探到位 → 收拢 → "
        "张开放料」。未连接 ROS 环境时，驱动会给出可读的错误而不是崩溃，"
        "便于在无真机的开发机上调试上层逻辑。"
    )
    m.page_break()


def build_arm_hiwonder(m: Manual) -> None:
    m.h1("8  幻尔总线舵机协议")
    m.h2("8.1  串口总线与厂商协议")
    m.para(
        "幻尔总线舵机走半双工串口，同一时刻只能有一个主控在总线上，因此"
        "直连方式与厂商图形界面互斥。驱动封装了厂商 SDK 的读写：舵机位置使用 "
        "0~1000 的脉宽量程而非角度，电压以毫伏为单位回报（舵机侧约 11000，"
        "控制板约 7400），温度以摄氏度回报。这些单位口径与厂商 SDK 一致，"
        "控制台面板按同一口径展示，避免出现「看起来是角度其实是脉宽」的误读。"
    )
    m.para(
        "状态查询会逐舵机回报读数。若某个舵机读取失败，仅该舵机缺数，"
        "不影响整条状态报文 —— 掉一个舵机不该让整个面板变空。"
    )
    m.h2("8.2  动作序列示教工具")
    m.para(
        "抓取姿态不能凭空设定，必须示教。工具 tools/teach_hiwonder_sequence.py "
        "按舵机逐个发送位置并记录，最终输出可直接被驱动加载的动作序列文件。"
        "驱动同时兼容厂商示教文件的两种格式（扁平位置文件与带 steps 包装的文件），"
        "因此既可以用本工具示教，也可以直接用厂商工具示教后导入。"
    )
    m.para("示教流程如下：")
    m.steps([
        "确认厂商常驻节点已停止，串口未被占用；",
        "指定串口设备、波特率与参与示教的舵机编号，启动示教工具；",
        "逐个舵机试位，确认无碰撞后记录该位姿；",
        "依次完成下探位、抓取位、投放位，导出动作序列文件；",
        "在 config.yaml 中把 pick_sequence_file 指向该文件，或把序列内联到 pick_sequence；",
        "重启桥接服务，用仿真后端先验证序列时长与顺序，再切真机。",
    ])
    m.page_break()


def build_arm_dual(m: Manual) -> None:
    m.h1("9  仿真与真机双模")
    m.para(
        "软件支持四种执行后端，可在 config.yaml 的 driver.backend 一项内切换，"
        "平台与报文契约零改动。这使「无真机也能完整演示」成为可能："
        "断电的机械臂、不存在的串口、未安装的 ROS，都不会让链路中断。"
    )
    m.table(
        ["后端", "类型", "适用场景"],
        [
            ["simulated", "仿真", "确定性自检；返回固定打捞结果，供全链路演练"],
            ["http", "仿真/真机", "对接通用 HTTP 机械臂 SDK，指令转发到 HTTP 端点"],
            ["ros_arm_control", "真机（推荐）", "复用厂商 ros_control，可与厂商程序共存"],
            ["hiwonder_bus_servo", "真机", "直连串口总线舵机，与厂商图形界面互斥"],
        ],
        widths_cm=[4.2, 2.6, 8.7]
    )
    m.para(
        "切换后端只需改一个字段。开发与联调阶段建议全程用 simulated 跑通指令、"
        "ACK、进度与遥测四条链路，再切真机后端，这样硬件问题与逻辑问题不会"
        "混在一起排查。"
    )
    m.h2("9.1  离线自检")
    m.para(
        "本体的逻辑正确性可以完全离线验证。edge/arm_bridge 下的三组单元测试"
        "覆盖指令校验、幂等去重、过期拒绝、厂商协议格式、ROS 关节映射与"
        "急停后状态回落等行为，不依赖真机、串口或 ROS。实际执行结果如下："
    )
    m.mono_block([
        "$ python -m pytest edge/arm_bridge/ -q",
        "",
        "..........................................                       [100%]",
        "42 passed in 1.14s",
    ], "图 9-1  本体逻辑离线自检：42 项单元测试全部通过")
    m.caption_note(
        "注：以上为实际执行结果。测试覆盖指令幂等、过期拒绝、厂商协议格式、"
        "ROS 关节映射与急停状态回落等关键行为，可在无真机的开发机上复现。"
    )
    m.page_break()


def build_arm_calib(m: Manual) -> None:
    m.h1("10  手眼标定与视觉引导")
    m.para(
        "平台下发的目标坐标是经纬度，而机械臂需要的是机械坐标系下的位置。"
        "两者之间由手眼标定建立映射：标定相机内参并求取像素坐标到工作平面"
        "坐标的对应关系，再由平面坐标换算出机械臂可达的抓取位。"
    )
    m.para("标定流程如下：")
    m.steps([
        "把棋盘格标定板平放在机械臂工作平面内，确保相机完整可见；",
        "在与抓取高度一致的距离上，从不同角度拍摄若干张标定板图像；",
        "执行标定脚本，指定图像目录、棋盘格规格（默认 9×6 内角点）与方格实际边长（默认 0.03 m）；",
        "脚本输出标定报告，含重投影误差与像素—平面映射参数；",
        "用标定结果做点对点验证：放置已知平面坐标的标记物，比对反算结果与实测值；",
        "验证通过后把映射参数写入本体配置，供视觉引导定位使用。",
    ])
    m.mono_block([
        "$ python ml/scripts/calibrate_camera.py chessboard \\",
        "      --images ./calib_shots --pattern 9x6 --square-size 0.03 \\",
        "      --output ./calib_report.json --evidence-level E1",
    ], "图 10-1  手眼标定命令（chessboard 子命令）")
    m.para(
        "标定报告带证据等级：E1 为可离线复现的标定，E2 为受控实验条件下采集，"
        "E3 要求真实采集来源说明（须显式给出 --real-source）。现场使用 E2/E3 "
        "结果，开发阶段用 E1 验证流程。标定精度会随相机安装位置变化而失效，"
        "因此拆装相机后必须重新标定。"
    )
    m.page_break()


def build_arm_safety(m: Manual) -> None:
    m.h1("11  安全与故障排查")
    m.h2("11.1  急停")
    m.para(
        "急停指令经 robot/{device_id}/cmd 下发，动作名为 emergency_stop。"
        "桥接层收到后立即调用驱动的急停接口，使机械臂停止当前轨迹，"
        "随后状态查询会报告急停后的运行模式，便于平台确认设备确实已停下。"
        "急停是最高优先级的指令，不参与幂等去重以外的任何排队。"
    )
    m.para(
        "物理急停按钮与软件急停相互独立，两者都应在现场可用。"
        "恢复运行须先排除致停原因，再重新下发回零动作。"
    )
    m.h2("11.2  掉线行为")
    m.para(
        "MQTT 连接启用遗嘱消息：本体异常掉电时，由 Broker 代发离线状态到 "
        "marine/{site_id}/{device_id}/status，平台无需等待指令超时即可判定"
        "设备不可达。本体侧掉线重连后自动重新订阅全部主题；掉线期间未执行的"
        "指令不会在重连后被补跑，避免机械臂在无人看守时突然动作。"
    )
    m.h2("11.3  常见故障排查")
    m.table(
        ["现象", "可能原因", "处理方法"],
        [
            ["串口打不开或报占用", "厂商常驻节点仍持有总线",
             "sudo systemctl stop armpi_fpv_bringup 后重试"],
            ["串口报 Permission denied", "运行账户不在 dialout 组", "把账户加入 dialout 组后重新登录"],
            ["指令收到但不动", "驱动后端仍为 simulated", "把 driver.backend 改为真机后端并重启服务"],
            ["ACK 正常但抓空", "抓取姿态未示教，沿用回零位",
             "用示教工具记录抓取位并写入 pick_sequence"],
            ["动作中途碰撞", "duration 过短或中间位姿缺失",
             "加大该步 duration，或补一个中间过渡位姿"],
            ["平台显示设备离线", "本体掉电或网络中断", "检查本体供电与网络；遗嘱消息会给出离线状态"],
            ["ROS 后端报找不到控制器", "ROS 域不匹配或控制器未启动", "确认与机械臂同一 ROS 域，并核对控制器名"],
            ["标定反算偏差大", "相机拆装后未重标，或标定板与抓取面不同高", "按第 10 章重新标定，标定板与抓取面等高"],
        ],
        widths_cm=[3.4, 5.6, 6.5]
    )
    m.page_break()


def build_arm_appendix(m: Manual) -> None:
    m.h1("12  附录：接口与数据约定")
    m.para("本软件与平台的报文约定如下，全部为 JSON，经 MQTT QoS 1 传输。")
    m.table(
        ["报文", "方向", "主要字段"],
        [
            ["工单 task", "平台 → 本体", "task_id、target{lng,lat}、priority、action"],
            ["指令 cmd", "平台 → 本体", "command_id、action（含 emergency_stop）、target、expire_at"],
            ["ACK", "本体 → 平台", "command_id、accepted、reason（拒绝时）、task_id"],
            ["进度 progress", "本体 → 平台", "task_id、status、review_result、collected_weight"],
            ["遥测 telemetry", "本体 → 平台", "device_id、status、location、battery、servo_telemetry"],
            ["在线状态", "本体 → 平台", "上线发布 status=online；掉线由 Broker 依遗嘱代发"],
        ],
        widths_cm=[3.0, 3.0, 9.5]
    )
    m.h2("12.1  字段口径")
    m.bullets([
        "command_id 全局唯一，是幂等去重的唯一依据；平台重发须沿用同一 command_id；",
        "target 为 {lng, lat} 经纬度对，本体侧经标定映射换算为机械坐标；",
        "servo_telemetry 的 position 为 0~1000 脉宽量程，不是角度；电压单位为毫伏；",
        "collected_weight 为该次作业累计打捞重量，单位为千克；",
        "review_result 为投放后的复核结论，取值 confirmed / recheck。",
    ])
    m.para(
        "本说明书随软件版本迭代更新。如与软件实际运行结果存在差异，"
        "以软件实际运行版本为准。"
    )


# ---------------------------------------------------------------------------
# 拆分登记第 1 篇：海漂垃圾边缘智能感知软件 —— 部署与运维手册
# 视角：边缘端安装 / 配置 / 取流 / 检测 / 时序校验 / 上报 / 仿真 / 排障
# 本篇只写感知链路，云端平台仅作为报文接收方出现在背景里。
# ---------------------------------------------------------------------------


def build_edge_cover(m: Manual) -> None:
    for _ in range(5):
        m.doc.add_paragraph()
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(EDGE_FULL_NAME), size=24, color=NAVY, bold=True)
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(f"（简称：{EDGE_SHORT_NAME}）"), size=16, color=OCEAN)
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(f"{VERSION}"), size=20, color=NAVY, bold=True)
    for _ in range(2):
        m.doc.add_paragraph()
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run("软 件 说 明 书"), size=22, color=DARK, bold=True)
    for _ in range(6):
        m.doc.add_paragraph()
    for line in ("文档类别：操作手册", "著作权人：福州理工学院", "编写日期：2026 年 10 月"):
        p = m.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cjk(p.add_run(line), size=12, color=GRAY)
    m.page_break()


def build_edge_toc(m: Manual) -> None:
    m.h1("目  录")
    toc = [
        "1  引言",
        "　1.1  编写目的",
        "　1.2  软件背景",
        "　1.3  术语与缩略语",
        "2  软件概述",
        "　2.1  软件定位与云端关系",
        "　2.2  功能清单",
        "　2.3  技术架构",
        "3  运行环境",
        "　3.1  硬件环境",
        "　3.2  软件环境",
        "4  安装与部署",
        "　4.1  边缘盒准备",
        "　4.2  依赖与启动",
        "　4.3  配置文件说明",
        "5  多路视频取流与帧调度",
        "　5.1  视频源类型",
        "　5.2  取流与重连",
        "　5.3  抽帧与帧率控制",
        "6  海漂垃圾目标检测",
        "　6.1  检测类别",
        "　6.2  检测流程",
        "　6.3  检测效果",
        "7  开放词汇零样本检测",
        "　7.1  通道定位",
        "　7.2  提示词与标签映射",
        "　7.3  现场加词操作",
        "8  时序校验误报抑制",
        "　8.1  抑制原理",
        "　8.2  关联三重门限",
        "　8.3  参数调优建议",
        "9  事件上报、离线缓存与恢复补传",
        "　9.1  事件报文结构",
        "　9.2  MQTT 主题约定",
        "　9.3  上报节流",
        "　9.4  断网缓存与恢复补传",
        "10  设备仿真与故障注入",
        "　10.1  仿真场景",
        "　10.2  仿真参数",
        "　10.3  设备孪生与故障注入",
        "11  运维与故障排查",
        "　11.1  运行观测",
        "　11.2  常见问题与处理",
        "12  附录：配置与主题约定",
    ]
    p = m.doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.6
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    for el in (fld_begin, instr, fld_sep):
        run._element.append(el)
    ph = p.add_run("")
    set_cjk(ph, size=9, color=RGBColor(0x80, 0x80, 0x80))
    end_run = p.add_run()
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    end_run._element.append(fld_end)
    for line in toc:
        tp = m.doc.add_paragraph()
        tp.paragraph_format.line_spacing = 1.5
        set_cjk(tp.add_run(line), size=10)
    m.page_break()


def build_edge_intro(m: Manual) -> None:
    m.h1("1  引言")
    m.h2("1.1  编写目的")
    m.para(
        "本说明书是「探海灵眸海漂垃圾边缘智能感知软件[简称:Oceanus Edge] V1.0」"
        "的操作手册，面向边缘盒运维人员与现场部署人员，说明软件的运行环境、"
        "安装部署方法，以及多路视频取流、海漂垃圾检测、开放词汇零样本识别、"
        "时序校验误报抑制、事件上报与离线缓存、设备仿真与故障注入等功能的操作方法。"
    )
    m.para(
        "本软件是海漂垃圾治理体系的感知源头：它不负责事件研判与派单决策，"
        "也不直接驱动打捞设备，而是把摄像头画面变成结构化的垃圾事件，"
        "经消息链路交给云端平台处置；摄像头与网络不可用时，软件可独立运行并"
        "在本地缓存事件，待链路恢复后按序补传。"
    )
    m.h2("1.2  软件背景")
    m.para(
        "近海养殖区海漂垃圾治理长期依赖人工巡查：巡查频次有限、发现不及时，"
        "水面反光与浪花造成的瞬时误报又会让值班人员疲于甄别。"
        "把识别放在云端还会带来两个现实问题：视频持续回传占用带宽，"
        "渔港 4G 信号不稳时整条感知链路随之中断。"
    )
    m.para(
        "本软件把识别前移到岸基摄像头旁的边缘计算盒，在本地完成取流、检测与"
        "时序校验，只把确认后的事件报文上报出去；同时用一套时序校验机制压制"
        "水面波光造成的瞬时误报，让上报事件量从原始检测框的数百条数量级"
        "收敛到可人工处置的规模。由此在低带宽、弱网络的现场条件下，"
        "仍能提供持续稳定的垃圾感知数据。"
    )
    m.h2("1.3  术语与缩略语")
    m.table(
        ["术语", "说明"],
        [
            ["边缘盒", "部署在摄像头旁的计算单元，独立完成检测与上报"],
            ["RTSP", "实时流传输协议，岸基摄像头的标准取流协议"],
            ["抽帧", "按固定间隔取样推理，降低边缘盒算力占用"],
            ["原始检测", "单帧检测器输出的候选目标框，可能包含瞬时误报"],
            ["确认事件", "经时序校验确认、可对外上报的垃圾记录"],
            ["时序校验", "边缘端误报抑制机制：连续多帧持续命中方可确认"],
            ["跟踪单元", "时序校验中被跟踪的一个候选目标，而非单个像素格"],
            ["四类别", "foam（泡沫）、plastic（塑胶）、fishing_gear（渔具）、other（其他）"],
            ["开放词汇检测", "零样本识别通道，现场给出提示词即可检出该类，无需重新训练"],
            ["MQTT", "面向弱网与移动网络的消息协议，用于事件上报与设备接入"],
            ["离线缓存", "断网期间事件进本地队列，恢复后按原顺序补传"],
            ["设备孪生", "无真实设备时用软件模型复刻设备命令与遥测行为的仿真体"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.page_break()


def build_edge_overview(m: Manual) -> None:
    m.h1("2  软件概述")
    m.h2("2.1  软件定位与云端关系")
    m.para(
        "本软件是一套部署在近岸边缘计算盒的海漂垃圾智能感知前端，"
        "扮演「感知源头」这一角色，与云端治理平台之间以消息链路解耦："
    )
    m.bullets([
        "本地闭环：取流、检测、时序校验、上报节流全部在边缘盒内完成，"
        "不依赖云端算力；",
        "单向解耦：只向云端发布事件报文，事件可被任意 MQTT 消费方接收，"
        "不绑定特定平台实现；",
        "弱网可用：断网期间事件进本地缓存队列，链路恢复后按原顺序补传；",
        "无摄像头可用：内置视频/事件仿真器与设备孪生，没有真实摄像头时"
        "也能驱动全链路联调与故障演练。",
    ])
    m.para(
        "与把识别放在云端相比，本软件的差异在于把计算放在数据产生的地方："
        "视频帧不出边缘盒，只上传确认后的结构化事件，带宽占用显著降低；"
        "同时因为检测与校验在同一进程内完成，误报抑制的时序窗口可以做得"
        "更短、更贴合帧率，而无需等待云端回传。"
    )
    m.h2("2.2  功能清单")
    m.table(
        ["功能模块", "主要功能"],
        [
            ["取流与调度", "RTSP / 视频文件 / 本地摄像头 / 合成海面四类视频源，抽帧与日志节流"],
            ["海漂垃圾检测", "OpenCV 背景差分与颜色纹理双通道，四类别判定与伪置信度打分"],
            ["开放词汇检测", "YOLO-World 零样本通道，提示词加词、标签映射与回落可观测"],
            ["时序校验", "候选目标跟踪、连续命中确认、关联三重门限与冷却去重"],
            ["事件上报", "结构化事件报文、MQTT 发布、上报节流与最大目标数限制"],
            ["离线缓存", "断网环形队列缓存、满了丢最旧、恢复后按批补传"],
            ["设备仿真", "多设备事件仿真、场景切换、重复投递与断网注入"],
            ["设备孪生", "命令闭环、ACK 幂等、遥测上报、故障注入与确定性报告"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.h2("2.3  技术架构")
    m.para("软件采用单进程分层结构，主要技术选型如下：")
    m.table(
        ["层次", "技术", "用途"],
        [
            ["运行时", "Python 3.10", "边缘程序主进程与仿真工具"],
            ["图像处理", "OpenCV / NumPy", "取流、背景差分、形态学与颜色判定"],
            ["开放词汇模型", "Ultralytics YOLO-World（可选）", "零样本开放词汇检测通道"],
            ["语义映射", "标签映射表", "提示词原文与四类契约类别之间的显式映射"],
            ["消息链路", "paho-mqtt / EMQX 5", "事件上报、设备命令与遥测通道"],
            ["配置", "YAML", "单文件承载检测、时序、上报与设备参数"],
            ["设备仿真", "自研 device_sim 包", "设备孪生、协议编解码与故障注入"],
        ],
        widths_cm=[2.8, 6.7, 6.0],
    )
    m.page_break()


def build_edge_env(m: Manual) -> None:
    m.h1("3  运行环境")
    m.h2("3.1  硬件环境")
    m.table(
        ["节点", "最低配置", "说明"],
        [
            ["边缘计算盒", "8 核 CPU / 16 GB 内存 / 64 GB 存储", "部署在摄像头旁，运行感知主程序"],
            ["计算加速", "NVIDIA Jetson 系列，或 x86_64 工控机（可配独立 GPU）", "开放词汇通道需要时可启用，主通道不依赖 GPU"],
            ["摄像头", "支持 RTSP 输出的网络摄像机", "每个点位一路，可按点位并行部署多台边缘盒"],
            ["网络", "到 MQTT Broker 的可达网络（渔港 4G 亦可）", "断网时自动缓存，恢复后补传"],
        ],
        widths_cm=[3.0, 6.0, 6.5]
    )
    m.h2("3.2  软件环境")
    m.table(
        ["类别", "要求"],
        [
            ["操作系统", "Ubuntu 22.04（Jetson 用对应 JetPack 版本）；x86_64 工控机用普通发行版"],
            ["运行时", "Python 3.10"],
            ["图像依赖", "opencv-python-headless、numpy"],
            ["消息依赖", "paho-mqtt"],
            ["配置依赖", "PyYAML"],
            ["开放词汇（可选）", "ultralytics、torch、transformers，仅在启用零样本通道时需要"],
            ["消息中间件", "EMQX 5.x（MQTT），可与云端平台共用或就近独立部署"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.para(
        "开放词汇通道的全部依赖为可选安装：未安装时主程序照常以 OpenCV 通道运行，"
        "零样本相关能力返回明确的不可用提示，不影响主告警链路。"
    )
    m.page_break()


def build_edge_deploy(m: Manual) -> None:
    m.h1("4  安装与部署")
    m.h2("4.1  边缘盒准备")
    m.steps([
        "在边缘盒安装 Ubuntu 22.04（或对应 JetPack）并接入与摄像头同一网段的网络；",
        "部署 edge/ 目录到边缘盒本地路径，确认目录内含 main.py、config.yaml、"
        "detector/、simulator/ 与 device_sim/；",
        "若使用开放词汇通道，把 YOLO-World 权重文件放到仓库根目录，"
        "并安装可选的模型依赖。",
    ])
    m.h2("4.2  依赖与启动")
    m.para("主通道只需图像、消息与配置三类依赖，安装后即可运行：")
    m.bullets([
        "安装依赖：pip install opencv-python-headless numpy paho-mqtt pyyaml；",
        "无摄像头自检：python main.py --source synthetic --dry-run --max-frames 200；",
        "视频文件回放：python main.py --source file --file samples/shore.mp4 --dry-run；",
        "真实摄像头上报：python main.py --source rtsp。",
    ])
    m.para(
        "自检模式用内置合成海面跑固定帧数、只打印报文不连 Broker，"
        "用于在不依赖摄像头与网络的前提下验证「检测—时序—报文」是否连通。"
    )
    m.h2("4.3  配置文件说明")
    m.para(
        "全部现场参数集中在 config.yaml，按站点、消息、检测、时序、上报、缓存与"
        "设备七个段落组织。修改后在下次启动时生效，无需改动代码。"
    )
    m.table(
        ["配置段", "关键项", "说明"],
        [
            ["site_id", "站点标识", "用于构造 MQTT 主题前缀"],
            ["mqtt", "host / port / username / password", "Broker 地址与认证；开启遗嘱消息后平台可判离线"],
            ["detector", "backend", "检测通道：cv（主通道）或 world（零样本对照）"],
            ["temporal", "window_frames / min_hits", "时序窗口长度与最少命中次数"],
            ["reporting", "cooldown_seconds / min_interval_seconds", "上报冷却与最小间隔"],
            ["buffer", "max_size / flush_batch", "离线缓存上限与恢复后每批补传条数"],
            ["source", "type / rtsp / file / camera", "视频源类型与地址"],
            ["device", "device_id / device_type / lng / lat", "设备身份与点位坐标，须与平台登记一致"],
            ["roi", "多边形顶点", "只在指定区域内检测，排除天空与岸边建筑"],
        ],
        widths_cm=[2.6, 4.9, 8.0]
    )
    m.para(
        "roi 为空表示全画面检测；填写相对宽高的多边形顶点（0~1）后，"
        "只在多边形内检测，用于排除固定缆绳、天空与岸边建筑等恒定误报源。"
    )
    m.page_break()


def build_edge_capture(m: Manual) -> None:
    m.h1("5  多路视频取流与帧调度")
    m.h2("5.1  视频源类型")
    m.para(
        "软件支持四类视频源，通过 source.type 或命令行 --source 选择，"
        "不同来源共用同一套检测、校验与上报代码："
    )
    m.table(
        ["类型", "取值", "用途"],
        [
            ["RTSP 摄像头", "rtsp", "现网部署，岸基网络摄像机实时取流"],
            ["视频文件", "file", "离线回放录制的码头片段，用于算法调试"],
            ["本地摄像头", "camera", "接入 USB 摄像头做台面验证"],
            ["合成海面", "synthetic", "内置生成海面帧序列，无摄像头时端到端自检"],
        ],
        widths_cm=[3.4, 2.4, 9.7]
    )
    m.h2("5.2  取流与重连")
    m.para(
        "RTSP 与本地摄像头经统一的取帧接口读取；任一来源读帧失败即视为该帧缺失，"
        "主循环按取流重连间隔重新打开视频源，而不是退出进程。"
        "这样短暂的网络抖动不会中断整条感知链路。"
    )
    m.bullets([
        "取流重连间隔由 source.reconnect_interval 控制，现网默认 5 秒；",
        "每读取若干帧打印一次进度日志，间隔由 source.log_every 控制；",
        "多路视频按点位部署：每个摄像头对应一台边缘盒及其独立配置。",
    ])
    m.h2("5.3  抽帧与帧率控制")
    m.para(
        "边缘盒算力有限，不要求对每一帧都做推理。时序校验的 decimation 参数规定"
        "每 N 帧推理一次，中间帧只做取流与解码；其余环节按推理帧推进。"
        "抽帧在保留目标持续性的同时把算力占用压到可控范围。"
    )
    m.para(
        "合成海面帧率、视频文件回放速度与真实摄像头一致地进入同一主循环，"
        "因此同一套时序参数在自检、回放与现网三种环境下行为一致。"
    )
    m.page_break()


def build_edge_detect(m: Manual) -> None:
    m.h1("6  海漂垃圾目标检测")
    m.h2("6.1  检测类别")
    m.para(
        "检测输出固定为四个契约类别，类别顺序与平台侧、训练配置逐项一致，"
        "不允许出现第五类；开放词汇通道的自由文本在进入契约前被映射回这四类。"
    )
    m.table(
        ["类别", "中文名", "典型目标"],
        [
            ["foam", "泡沫类", "EPS 泡沫浮球及其碎片，白亮、团状，当地治理优先级最高"],
            ["plastic", "塑胶类", "塑胶浮球、塑料瓶与塑料袋，带明显彩度"],
            ["fishing_gear", "渔具类", "废旧渔网、湿缆绳与饵料包装，偏暗、细长"],
            ["other", "其他", "木板、藻团、鞋等生活杂物，兜底类别"],
        ],
        widths_cm=[2.8, 2.4, 10.3]
    )
    m.h2("6.2  检测流程")
    m.para(
        "主通道采用背景差分与颜色纹理双通道的传统视觉方案，不依赖标注数据集"
        "与模型训练，可直接在边缘设备部署："
    )
    m.steps([
        "背景建模：用历史帧建立背景模型，抓取新出现或正在移动的目标；",
        "白色通道：单独抓白亮、几乎不带颜色的泡沫类目标，避免泡沫随浪停在"
        "镜头前不动时被背景模型学成背景；",
        "暗色通道：单独抓比海面明显偏暗的废旧渔网与湿缆绳，避免被背景模型"
        "当成阴影剔除；",
        "形态学与候选过滤：开运算吃掉波光噪点，闭运算填补泡沫内部空洞，"
        "再按面积、凸包填充度与长宽比过滤浪花与水痕；",
        "四类判定：按泡沫、渔具、塑胶、其他的顺序命中优先级规则；",
        "置信度打分：以可解释的伪置信度综合匹配度、反光惩罚与面积适中度。",
    ])
    m.para(
        "原始检测允许存在一定误报，其作用只是「指出候选」，真正的确认由下游"
        "时序校验完成。这一分工使检测器可以保持简单可解释，而把稳定性交给"
        "时序环节。"
    )
    m.h2("6.3  检测效果")
    m.para(
        "下图为岸基摄像头水面监控视角下的实测画面：识别框叠加在视频帧上，"
        "并标注垃圾类别与置信度。检测结果按置信度由高到低排列，"
        "图中仅保留达到阈值且尺寸足以辨识的有效框。"
    )
    m.image(VP / "water-container-detected.jpg", "图 6-1  水面塑胶容器检测效果", width_cm=14.0)
    m.image(VP / "foam-pellets-4k-detected.jpg", "图 6-2  泡沫颗粒检测效果", width_cm=14.0)
    m.image(VP / "fishing-net-4k-detected.jpg", "图 6-3  废旧渔网检测效果", width_cm=14.0)
    m.caption_note(
        "注：以上画面为岸基摄像头水面监控视角的实拍帧，"
        "用于说明检测通道的标注能力。"
    )
    m.page_break()


def build_edge_world(m: Manual) -> None:
    m.h1("7  开放词汇零样本检测")
    m.h2("7.1  通道定位")
    m.para(
        "开放词汇通道基于 YOLO-World 零样本模型，用于能力演示与对照评测，"
        "默认不进主告警链路。它的价值在于：现场说一个新词，"
        "系统立刻能检出这一类，不需要重新采集、标注与训练。"
    )
    m.para(
        "两个检测通道的输出契约完全一致，因此时序校验、上报节流与 MQTT 报文的"
        "代码一行都不用改；但两通道的置信度尺度不同，时序门限必须各用各的。"
        "把主通道的门限套到开放词汇通道上，该通道的检测会在时序环节被全部丢弃，"
        "而现象只是「这个通道没有结果」，排查方向容易被带偏。"
    )
    m.table(
        ["配置项", "主通道 cv", "零样本通道 world"],
        [
            ["模型侧打分门限", "不适用", "0.02（零样本分数尺度较低）"],
            ["交给时序的门限", "0.45", "0.02（与模型门限同尺度）"],
            ["权重", "无", "yolov8s-worldv2.pt（按仓库根解析）"],
            ["静默下载", "不适用", "默认关闭，避免现场启动卡在联网重试"],
        ],
        widths_cm=[3.6, 4.0, 7.9]
    )
    m.h2("7.2  提示词与标签映射")
    m.para(
        "开放词汇模型的输出类别是提示词原文，而契约只有四类，"
        "所以自由文本必须在进入契约之前经映射表映射回四类。"
        "映射采用显式表，不做模糊匹配：未命中的词回落 other，"
        "同时输出映射类型，便于统计回落数量、发现「静默失效」。"
    )
    m.table(
        ["提示词示例", "映射类别", "映射类型"],
        [
            ["plastic bottle / plastic bag", "plastic", "精确命中"],
            ["foam debris / styrofoam", "foam", "精确命中"],
            ["fishing net / rope", "fishing_gear", "精确命中"],
            ["discarded shoe / seaweed", "other", "精确命中"],
            ["表外任意新词", "other", "回落（计入 fallback_other）"],
        ],
        widths_cm=[6.4, 3.2, 5.9]
    )
    m.h2("7.3  现场加词操作")
    m.para(
        "现场需要临时识别某个新词时，无需改动配置文件，用命令行参数追加提示词即可，"
        "可重复传入多个："
    )
    m.steps([
        "切换检测通道：--backend world；",
        "追加提示词：--world-prompt \"foam buoy\" --world-prompt \"plastic bag\"；",
        "如需观察检测框，附加 --show 弹出显示窗口；",
        "提示词未命中映射表时会回落 other，并在输出中提示未归宿的提示词清单。",
    ])
    m.para(
        "该通道的姿态是「零样本、可现场加词」，对外只说明其能力，"
        "不承诺精度指标；精度验收以主通道为准。"
    )
    m.page_break()


def build_edge_temporal(m: Manual) -> None:
    m.h1("8  时序校验误报抑制")
    m.h2("8.1  抑制原理")
    m.para(
        "时序校验是降误报的第一道闸，其核心判断是一句常识：浪花是瞬态的，"
        "垃圾是持续的。滑动窗口内只有连续多帧在同一目标上命中，"
        "候选才会被升级为确认事件；单帧命中只作为候选记录，不上报。"
    )
    m.para(
        "与把校验寄托在单帧置信度阈值上的做法相比，时序校验利用的是时间维度"
        "的持续性：水面波光、反光与水花在连续帧之间不能稳定复现，"
        "而真实垃圾会在多帧内保持位置与类别一致。同一点位上，"
        "原始检测框数量常在每帧数十条，确认事件量则收敛到个位数量级。"
    )
    m.h2("8.2  关联三重门限")
    m.para(
        "时序校验跟踪的是目标而不是像素格。一个新的检测框只有同时满足"
        "「类别相同 + 中心位移达标 + 框重叠度达标」三个条件，"
        "才会被认作某个已有目标的延续；否则视为新目标。"
    )
    m.table(
        ["参数", "默认值", "含义与调优方向"],
        [
            ["window_frames", "15", "滑动窗口长度（推理帧）；调大更稳，确认更慢"],
            ["min_hits", "3", "窗口内最少命中次数；调大更保守，可能漏报慢速目标"],
            ["grid_size", "64", "空间聚合格网边长（像素），避免同一垃圾被算成多个目标"],
            ["min_confidence", "0.45", "进入窗口的最低置信度（主通道）"],
            ["decimation", "4", "每 N 帧推理一次，直接决定窗口对应的真实时长"],
            ["match_distance", "60.0", "中心位移上限（像素），约画面宽度 3%"],
            ["min_iou", "0.25", "最小框重叠度，允许抖动、拒绝「碰巧靠近」"],
            ["max_misses", "5", "连续丢失多少帧后淘汰，容忍短暂遮挡"],
        ],
        widths_cm=[3.4, 1.9, 10.2]
    )
    m.para(
        "参数之间互为约束：max_misses 偏小会使被浪遮挡的目标被淘汰、"
        "同一片垃圾重复上报；偏大则噪声目标迟迟不退出、白占跟踪槽位。"
        "match_distance 与 min_iou 必须同时生效，只放宽其中之一会引入"
        "「远处两个无关目标被合并」的错误。"
    )
    m.h2("8.3  参数调优建议")
    m.bullets([
        "误报偏多时：先增大 min_hits，再考虑收紧 min_confidence；",
        "漏报偏多时：先减小 min_hits 或放宽 max_misses，再检查相机曝光与 roi；",
        "目标移动较快时：适当增大 match_distance，避免漂移出关联范围；",
        "调整后必须用固定种子的回归场景复跑，确认改动的方向与幅度符合预期。",
    ])
    m.page_break()


def build_edge_report(m: Manual) -> None:
    m.h1("9  事件上报、离线缓存与恢复补传")
    m.h2("9.1  事件报文结构")
    m.para(
        "确认事件被组织成固定结构的事件报文后上报。报文内同时携带设备身份、"
        "点位坐标、检测明细与聚合结果，使云端无需回查即可落库与派单。"
    )
    m.table(
        ["字段", "说明"],
        [
            ["event_id", "事件标识，由设备标识与事件序号拼成，全局唯一"],
            ["device_id / device_type", "上报设备标识与类型"],
            ["timestamp", "UTC 时间戳"],
            ["location", "点位经纬度"],
            ["detections", "检测明细列表，含类别、置信度与像素框"],
            ["aggregate", "聚合结果：主类别、目标数与最高置信度"],
            ["evidence_url", "证据图地址（可选）"],
            ["model_version", "产生该事件的检测版本"],
            ["seq", "设备级单调递增序号，平台据此幂等去重"],
        ],
        widths_cm=[3.6, 11.9]
    )
    m.h2("9.2  MQTT 主题约定")
    m.para("事件与状态经两级主题上报，站点与设备标识都体现在主题里：")
    m.table(
        ["主题", "方向", "用途"],
        [
            ["marine/{site_id}/{device_id}/event", "上报", "确认事件报文"],
            ["marine/{site_id}/{device_id}/status", "上报", "设备上下线状态，含遗嘱消息"],
            ["marine/{site_id}/{device_id}/telemetry", "上报", "仿真遥测（设备仿真场景）"],
        ],
        widths_cm=[7.4, 1.8, 6.3]
    )
    m.image(UI / "1920x1080-events.png",
            "图 9-1  云端事件列表（佐证上报链路：边缘端上报的事件在此落库展示）", width_cm=15.5)
    m.h2("9.3  上报节流")
    m.para(
        "时序校验确认后并非立即每条都上报。同一目标在冷却期内不重复上报，"
        "任意两次上报之间也保留最小间隔，单条报文最多携带设定数量的目标，"
        "避免同一片垃圾被反复派单。"
    )
    m.table(
        ["参数", "默认值", "说明"],
        [
            ["cooldown_seconds", "90", "同一目标的上报冷却时长"],
            ["min_interval_seconds", "2", "任意两次上报之间的最小间隔"],
            ["max_detections", "20", "单条报文最多携带的目标数"],
        ],
        widths_cm=[4.2, 2.2, 9.1]
    )
    m.h2("9.4  断网缓存与恢复补传")
    m.para(
        "渔港 4G 信号不稳，断网时不能丢事件、也不能阻塞新事件。"
        "软件用本地上限队列缓存待发报文：队列满时丢弃最旧的一条，"
        "保证新事件始终能入队；链路恢复后按原顺序分批补传，"
        "沿用原始序号，平台侧按设备与序号幂等去重。"
    )
    m.table(
        ["参数", "默认值", "说明"],
        [
            ["max_size", "1000", "本地队列上限，满了丢最旧"],
            ["flush_batch", "20", "恢复后每批补传条数"],
            ["flush_interval", "1.0", "批间隔（秒）"],
        ],
        widths_cm=[3.4, 2.2, 9.9]
    )
    m.page_break()


def build_edge_simulator(m: Manual) -> None:
    m.h1("10  设备仿真与故障注入")
    m.h2("10.1  仿真场景")
    m.para(
        "没有真实摄像头或真实打捞设备时，仿真工具可以复刻边缘盒的完整行为，"
        "驱动平台演示与联调。仿真器自己生成符合契约的检测框与事件报文，"
        "与真实程序共用同一套 MQTT 主题、时序校验与上报节流参数，"
        "因此平台侧无法区分报文来自仿真器还是真实摄像头。"
    )
    m.table(
        ["场景", "取值", "用途"],
        [
            ["演示", "demo", "缩短冷却、加快事件节奏，用于现场演示"],
            ["压测", "stress", "放宽确认门槛、加快上报，用于压派单引擎"],
            ["回归", "regression", "固定随机种子，结果可复现，用于回归比对"],
        ],
        widths_cm=[2.6, 2.4, 10.5]
    )
    m.h2("10.2  仿真参数")
    m.table(
        ["参数", "默认值", "说明"],
        [
            ["--scenario", "demo", "运行场景：demo / stress / regression"],
            ["--interval", "0.125", "抽帧间隔秒数，0.125 相当于 8fps"],
            ["--event-interval", "读配置", "同一目标的最小上报间隔，演示时用于加快节奏"],
            ["--loop", "关闭", "循环运行不退出"],
            ["--duration", "0", "运行时长（秒），0 表示不限"],
            ["--seed", "无", "随机种子，固定后结果可复现"],
            ["--devices", "全部", "只模拟指定设备，逗号分隔"],
            ["--dup-rate", "0.0", "重复投递比例 0~1，用于验证平台幂等判重"],
            ["--net-drop-every", "0", "每 N 轮模拟一次断网，用于验证离线补传"],
            ["--dry-run", "关闭", "只打印报文，不连接 Broker"],
        ],
        widths_cm=[3.8, 2.2, 9.5]
    )
    m.para(
        "内置点位覆盖码头、渔港、养殖区、航道与回收点等典型场景，"
        "各点位带独立的垃圾类别构成与事件速率；无人机点位在巡飞范围内"
        "随机落点，用于验证广域巡查数据。"
    )
    m.image(UI / "1920x1080-devices.png",
            "图 10-1  云端设备列表（仿真点位与真实点位在同一处登记与查看）", width_cm=15.5)
    m.h2("10.3  设备孪生与故障注入")
    m.para(
        "设备孪生独立于事件仿真器，复刻打捞设备的命令闭环、遥测上报与故障行为，"
        "用于在假时钟与内存通道下做确定性演练。"
    )
    m.table(
        ["主题", "方向", "用途"],
        [
            ["robot/{device_id}/cmd", "下发", "通用命令（暂停、返航、急停、回执确认）"],
            ["robot/{device_id}/task", "下发", "派单任务"],
            ["robot/{device_id}/cmd/ack", "上报", "命令回执，平台按命令标识幂等去重"],
            ["robot/{device_id}/telemetry", "上报", "周期性遥测"],
        ],
        widths_cm=[5.6, 1.8, 8.1]
    )
    m.para(
        "孪生支持六类命令动作与六种运行模式：紧急停止命令在处理批次中插队最先执行，"
        "执行后进入急停模式、其余待处理命令被拒绝；恢复命令回到停止前的模式。"
        "同一命令标识的重复回执只生效一次，乱序与超时回执被平台侧识别并计入统计。"
    )
    m.table(
        ["故障码", "含义"],
        [
            ["battery_critical", "电量低于阈值，自动返航充电并自动恢复"],
            ["bin_full", "仓容将满，自动返航卸仓并自动恢复"],
            ["gps_lost", "定位丢失，注入后需显式清除"],
            ["communication_lost", "通信中断，出站报文进入本地队列、重连后补传"],
            ["emergency_stop", "急停，优先级最高"],
            ["ack_timeout / duplicate_ack / out_of_order_ack", "回执超时、重复与乱序，供平台幂等校验"],
        ],
        widths_cm=[5.6, 9.9]
    )
    m.para(
        "多故障并存时，遥测只上报一个主故障，优先级从高到低依次为急停、通信中断、"
        "电量临界、仓容将满、定位丢失、回执类故障。故障场景以固定种子驱动，"
        "同一场景重复执行得到逐字节一致的结构化报告，可离线复现。"
    )
    m.page_break()


def build_edge_ops(m: Manual) -> None:
    m.h1("11  运维与故障排查")
    m.h2("11.1  运行观测")
    m.para(
        "边缘程序在运行中按固定间隔打印进度，并维护一组计数器，"
        "覆盖从取流到上报的每个环节。发生异常时先看计数器在哪一段停止增长，"
        "即可快速定位是取流、检测、时序校验还是上报环节的问题。"
    )
    m.table(
        ["计数器", "含义"],
        [
            ["frames", "已读取的帧数"],
            ["raw", "原始检测框数量"],
            ["confirmed", "时序校验确认的事件数"],
            ["published", "已成功发布的报文数"],
            ["buffered", "已进入离线缓存的报文数"],
            ["throttled", "被上报节流丢弃的重复上报数"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.para(
        "缓存队列长度持续增长说明链路没有恢复或权限配置有误；"
        "原始检测框数量正常而确认事件为零，通常是时序门限设置过严，"
        "或相机画面缺少足够清晰的目标。"
    )
    m.h2("11.2  常见问题与处理")
    m.table(
        ["现象", "可能原因", "处理方法"],
        [
            ["程序启动无输出、长时间无反应", "开放词汇权重缺失触发联网重试", "确认权重已放到仓库根目录；默认静默下载已关闭"],
            ["原始检测框很多但无事件上报", "时序门限过严或帧率不匹配", "核对 window_frames / min_hits 与抽帧间隔，适当放宽"],
            ["同一片垃圾反复上报", "max_misses 偏小，目标被短暂遮挡后重复确认", "适当增大 max_misses 或延长上报冷却"],
            ["平台收不到事件", "Broker 地址或认证错误、设备未登记", "核对 mqtt 段与 device 段，确认设备已与平台登记一致"],
            ["断网恢复后事件缺失", "本地队列达到上限、最旧事件被丢弃", "提高 buffer.max_size，或排查长时间断网原因"],
            ["零样本通道没有任何结果", "误用了主通道的时序门限", "确认该通道使用自身的低尺度门限，而非主通道门限"],
            ["画面固定区域持续误报", "岸边建筑、缆绳或反光进入检测区", "配置 roi 多边形，把该区域排除在检测范围外"],
        ],
        widths_cm=[3.6, 5.0, 6.9]
    )
    m.page_break()


def build_edge_appendix(m: Manual) -> None:
    m.h1("12  附录：配置与主题约定")
    m.para("软件的关键参数集中在单一配置文件，主要约定如下：")
    m.table(
        ["配置段", "约定"],
        [
            ["site_id", "站点标识，参与构造全部 MQTT 主题"],
            ["mqtt", "Broker 地址、端口、认证与遗嘱消息开关"],
            ["detector", "检测通道选择与两通道各自的参数"],
            ["temporal", "时序窗口、命中次数、关联三重门限与抽帧间隔"],
            ["reporting", "上报冷却、最小间隔与单报文最大目标数"],
            ["buffer", "离线缓存上限、批量补传条数与批间隔"],
            ["source", "视频源类型与各来源的地址"],
            ["device", "设备身份与点位坐标，须与平台登记一致"],
        ],
        widths_cm=[3.0, 12.5]
    )
    m.para("消息主题约定如下：")
    m.table(
        ["主题", "方向", "用途"],
        [
            ["marine/{site_id}/{device_id}/event", "上报", "确认事件报文"],
            ["marine/{site_id}/{device_id}/status", "上报", "设备上下线状态"],
            ["marine/{site_id}/{device_id}/telemetry", "上报", "仿真遥测"],
            ["robot/{device_id}/cmd", "下发", "打捞设备通用命令"],
            ["robot/{device_id}/task", "下发", "打捞设备派单任务"],
            ["robot/{device_id}/cmd/ack", "上报", "打捞设备命令回执"],
            ["robot/{device_id}/telemetry", "上报", "打捞设备遥测"],
        ],
        widths_cm=[6.4, 1.8, 7.3]
    )
    m.para(
        "本说明书随软件版本迭代更新。如与系统实际运行版本存在差异，以软件实际运行版本为准。"
    )


# ══════════════════════════════════════════════════════════════════════════
# 拆分登记第 3 篇：探海灵眸海域治理三维数字沙盘软件（Oceanus SandBox）
# ══════════════════════════════════════════════════════════════════════════
# 与主软著共用 Manual 排版类；正文另起一套 build_sandbox_* 函数链。
# 说明书视角：三维态势呈现与仿真推演操作手册 —— 沙盘是唯一主角，
# 平台其余部分（事件中心、工单看板等）只作为联动的背景出现。
# 截图来源：artifacts/ui-responsive/ 下 1920x1080-sandbox-*.png 与
# 2560x1440-sandbox-dashboard.png（2026-10-14 由
# scripts/shoot_sandbox_copyright.mjs 在本地演示栈对真实前后端实拍）。


def build_sandbox_cover(m: Manual) -> None:
    for _ in range(5):
        m.doc.add_paragraph()
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(SANDBOX_FULL_NAME), size=24, color=NAVY, bold=True)
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(f"（简称：{SANDBOX_SHORT_NAME}）"), size=16, color=OCEAN)
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run(f"{VERSION}"), size=20, color=NAVY, bold=True)
    for _ in range(2):
        m.doc.add_paragraph()
    p = m.doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_cjk(p.add_run("软 件 说 明 书"), size=22, color=DARK, bold=True)
    for _ in range(6):
        m.doc.add_paragraph()
    for line in ("文档类别：操作手册", "著作权人：福州理工学院", "编写日期：2026 年 10 月"):
        p = m.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        set_cjk(p.add_run(line), size=12, color=GRAY)
    m.page_break()


def build_sandbox_toc(m: Manual) -> None:
    m.h1("目  录")
    toc = [
        "1  引言",
        "　1.1  编写目的",
        "　1.2  软件背景",
        "　1.3  术语与缩略语",
        "2  软件概述",
        "　2.1  软件定位",
        "　2.2  功能清单",
        "　2.3  技术架构",
        "3  运行环境",
        "　3.1  硬件环境",
        "　3.2  软件环境",
        "4  部署与访问",
        "　4.1  构建与部署",
        "　4.2  访问与登录",
        "　4.3  大屏模式进入",
        "5  三维海域地形",
        "　5.1  地形建模",
        "　5.2  水陆判定规则",
        "　5.3  视角漫游操作",
        "6  载具三维调度",
        "　6.1  双载具模型",
        "　6.2  状态颜色语义",
        "　6.3  点选与操作卡",
        "7  作业航线与轨迹回放",
        "　7.1  航线与作业目标点",
        "　7.2  已走轨迹",
        "　7.3  轨迹回放",
        "8  图层与事件联动",
        "　8.1  海漂垃圾分布图层",
        "　8.2  海域设施图层",
        "　8.3  事件点联动",
        "9  仿真推演沙盒",
        "　9.1  启动与推演控制",
        "　9.2  推演过程与闭环",
        "　9.3  闭环完成与复核",
        "10  大屏展示模式",
        "　10.1  大屏适配",
        "　10.2  全屏与快捷导航",
        "11  常见问题与处理",
        "12  附录：图层配色与数据约定",
    ]
    p = m.doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.6
    run = p.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = 'TOC \\o "1-2" \\h \\z \\u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    for el in (fld_begin, instr, fld_sep):
        run._element.append(el)
    ph = p.add_run("")
    set_cjk(ph, size=9, color=RGBColor(0x80, 0x80, 0x80))
    end_run = p.add_run()
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    end_run._element.append(fld_end)
    for line in toc:
        tp = m.doc.add_paragraph()
        tp.paragraph_format.line_spacing = 1.5
        set_cjk(tp.add_run(line), size=10)
    m.page_break()


def build_sandbox_intro(m: Manual) -> None:
    m.h1("1  引言")
    m.h2("1.1  编写目的")
    m.para(
        "本说明书是「探海灵眸海域治理三维数字沙盘软件[简称:Oceanus SandBox] V1.0」"
        "的操作手册，面向海域治理指挥人员、值班人员与决策汇报人员，"
        "说明软件的功能构成、运行环境、部署方式以及三维沙盘各功能模块的操作方法。"
    )
    m.h2("1.2  软件背景")
    m.para(
        "海域治理涉及海漂垃圾清理、养殖区巡查、渔船与机械装备调度等多类业务，"
        "传统管理方式依赖二维表格与平面地图，难以直观呈现海域空间关系与作业态势。"
        "本软件以真实海岸线数据为基础构建三维数字沙盘，把海域地形、"
        "作业载具、作业航线、垃圾分布与告警事件统一呈现在一幅三维态势图上，"
        "并内置仿真推演沙盒，供指挥与汇报场景在不触碰真机的情况下演练完整作业流程。"
    )
    m.h2("1.3  术语与缩略语")
    m.table(
        ["术语", "说明"],
        [
            ["三维数字沙盘", "以真实海岸线数据构建的三维场景，统一承载海域地形与作业要素"],
            ["水陆判定", "依据地形高度采样判断坐标位于水面或陆地，用于载具与要素的落位"],
            ["载具", "沙盘中的作业装备，含打捞机器人船体与履带式滩涂清除车两类"],
            ["作业目标点", "活跃工单的目的地坐标，在沙盘上以目标浮标呈现"],
            ["已走轨迹", "载具实际航行经过的路径，以带状轨迹呈现并可供回放"],
            ["仿真推演", "在沙盘中模拟一次完整作业闭环的功能，不向真机下发指令"],
            ["事件点", "边缘感知上报的垃圾告警记录在沙盘上的标记"],
            ["WebGL", "浏览器三维渲染接口，本软件的三维场景由 WebGL2 加速渲染"],
        ],
        widths_cm=[3.4, 12.1]
    )
    m.page_break()


def build_sandbox_overview(m: Manual) -> None:
    m.h1("2  软件概述")
    m.h2("2.1  软件定位")
    m.para(
        "本软件是面向海域治理场景的三维数字沙盘软件：以真实海岸线数据构建三维地形，"
        "把作业载具、作业航线与轨迹、海漂垃圾分布、海域设施与告警事件统一呈现在"
        "一幅三维态势图上，并提供不依赖真机的仿真推演沙盒，"
        "为指挥决策与汇报展示提供沉浸式的海域态势一张图。"
    )
    m.para(
        "本软件作为浏览器端软件独立部署（B/S 架构客户端），通过接口接入平台态势数据，"
        "可与事件中心、工单看板等模块联动跳转；其本体不承担检测识别与调度的后台计算，"
        "专注于三维态势的呈现与交互。"
    )
    m.h2("2.2  功能清单")
    m.table(
        ["功能模块", "主要能力"],
        [
            ["三维海域地形", "真实海岸线建模、水陆分层着色、海面波动、视角漫游"],
            ["载具三维调度", "打捞机器人 / 履带式滩涂清除车双载具呈现、状态语义、点选详情"],
            ["作业航线与轨迹", "剩余航线与目标浮标、已走轨迹带、跳转工单仿真、轨迹回放"],
            ["海漂垃圾分布图层", "海浮 / 沙滩垃圾点位、四类配色、光柱指示、点选查询"],
            ["海域设施图层", "渔排养殖区、礁体、岸线设施标记"],
            ["事件点联动", "事件标记呈现、点选查看、跳转事件中心"],
            ["仿真推演沙盒", "完整作业闭环推演、倍速控制、单步执行、运行日志"],
            ["大屏展示", "大屏分辨率适配、沙盘全屏、快捷导航"],
        ],
        widths_cm=[3.8, 11.7]
    )
    m.h2("2.3  技术架构")
    m.para(
        "本软件采用 Vue 3 前端框架与 Three.js 三维引擎构建，"
        "以 Vite 完成工程构建，产物为静态资源，由 Nginx 独立托管；"
        "态势数据经 REST 接口与 WebSocket 实时通道接入。三维场景的"
        "地形建模、载具调度、航线渲染、图层组织与拾取交互按管理器拆分，"
        "后处理管线使用 HDR 泛光（UnrealBloom）与多重采样抗锯齿，"
        "并对渲染倍率做自适应调节以兼顾画质与帧率。"
    )
    m.page_break()


def build_sandbox_env(m: Manual) -> None:
    m.h1("3  运行环境")
    m.h2("3.1  硬件环境")
    m.table(
        ["项", "要求"],
        [
            ["计算平台", "x86_64 工作站 / 大屏展示终端"],
            ["图形能力", "支持 WebGL2 的显卡（建议独立显卡或集成显卡硬件加速开启）"],
            ["显示分辨率", "1920×1080 及以上（支持 2560×1440 等大屏分辨率自适应）"],
            ["网络", "可访问平台服务端（REST / WebSocket）"],
        ],
        widths_cm=[3.2, 12.3]
    )
    m.h2("3.2  软件环境")
    m.table(
        ["项", "要求"],
        [
            ["操作系统", "Windows 10/11 或 Ubuntu 22.04（浏览器运行，不依赖本机运行时）"],
            ["浏览器", "Chrome / Edge 等基于 Chromium 的浏览器（需支持 WebGL2）"],
            ["前端技术栈", "Vue 3 / Three.js / Vite"],
            ["静态托管", "Nginx（前端容器与后端容器分离部署）"],
        ],
        widths_cm=[3.2, 12.3]
    )
    m.caption_note(
        "注：三维场景加载对显卡驱动有一定要求；若浏览器提示 WebGL 不可用，"
        "请在浏览器设置中开启硬件加速后重试。"
    )
    m.page_break()


def build_sandbox_deploy(m: Manual) -> None:
    m.h1("4  部署与访问")
    m.h2("4.1  构建与部署")
    m.para(
        "本软件为纯前端工程：在工程目录执行构建命令生成静态产物后，"
        "将产物部署至 Nginx 站点目录即可（与后端容器分离，可独立发布）。"
        "接口地址等环境参数在构建配置中注入。"
    )
    m.mono_block([
        "# 构建（工程根目录）",
        "npm install",
        "npm run build          # 产物输出到 dist/",
        "",
        "# 部署：将 dist/ 目录内容拷贝至 Nginx 站点根目录，重载后即生效",
    ], "构建与部署命令（示意）")
    m.h2("4.2  访问与登录")
    m.steps([
        "在浏览器地址栏输入沙盘部署地址，进入系统登录页；",
        "输入账号与密码登录（账号由平台管理员分配，含管理员、操作员等角色）；",
        "登录后从顶部导航进入「监测大屏」，三维沙盘位于大屏中部「3D 海域态势」区域。",
    ])
    m.image(UI / "1920x1080-sandbox-dashboard.png",
            "图 4-1  登录后进入的监测大屏（中部为 3D 海域态势沙盘）")
    m.h2("4.3  大屏模式进入")
    m.para(
        "沙盘内提供「全屏查看」按钮：点击后沙盘脱离页面布局铺满整个屏幕，"
        "适合在大屏展示终端上以沉浸方式呈现海域态势；"
        "按浏览器全屏约定（Esc 或按钮）可随时退出全屏。"
    )
    m.page_break()


def build_sandbox_terrain(m: Manual) -> None:
    m.h1("5  三维海域地形")
    m.h2("5.1  地形建模")
    m.para(
        "沙盘地形基于真实海岸线数据生成：载入县域海陆边界后，"
        "在 256 × 256 的网格上做高度位移，并按高程与离岸距离分层着色，"
        "呈现沙滩、植被、山体等地貌层次；海面以半透明着色器绘制，"
        "带缓慢起伏与近岸浪花效果，远景辅以天空渐变与雾效。"
    )
    m.para(
        "山体阴影采用预烘焙策略：场景静止时不重复计算阴影，"
        "仅在取景发生变化时按需重烤，以在低功耗设备上保持流畅帧率；"
        "渲染分辨率亦按实时帧率自适应调节。"
    )
    m.image(UI / "1920x1080-sandbox-hero.png", "图 5-1  三维海域沙盘全景（全屏查看）")
    m.h2("5.2  水陆判定规则")
    m.para(
        "沙盘对每个坐标点做地形高度采样，据此刻分水面与陆地："
        "打捞机器人的落位与航行始终在水面，履带式滩涂清除车则沿岸线内侧的滩涂带作业；"
        "垃圾分布、事件标记等要素的呈现同样遵循水陆约束——"
        "海浮垃圾只出现在近岸水面，沙滩垃圾则沿岸线内侧的低平地带分布。"
    )
    m.h2("5.3  视角漫游操作")
    m.table(
        ["操作", "说明"],
        [
            ["自由视角", "鼠标左键拖动旋转、滚轮缩放、右键拖动平移，任意观察角度"],
            ["俯视", "一键切换正俯视视角，适合查看全域分布与点位关系"],
            ["跟随首船", "相机跟随作业载具移动，近距离观察航行与作业过程"],
            ["回到默认视角", "一键恢复初始取景"],
            ["罗盘 / 比例尺", "左上角罗盘指示方位，右下角比例尺随视距实时换算"],
            ["缩放百分比", "右侧缩放条显示当前镜头缩放比例，可点按放大 / 缩小"],
        ],
        widths_cm=[3.6, 11.9]
    )
    m.page_break()


def build_sandbox_vessels(m: Manual) -> None:
    m.h1("6  载具三维调度")
    m.h2("6.1  双载具模型")
    m.para(
        "沙盘承载两类作业载具：打捞机器人船体（双体船型，航行时带尾流）"
        "与履带式滩涂清除车（贴滩涂地带作业）。载具以真实设备编号命名呈现，"
        "模型位置随作业遥测实时更新，处于航行状态时沿航线平稳移动并随波起伏。"
    )
    m.image(UI / "1920x1080-sandbox-vessel.png", "图 6-1  打捞机器人（点选后弹出操作卡）")
    m.image(UI / "1920x1080-sandbox-tracked.png", "图 6-2  履带式滩涂清除车（点选后弹出操作卡）")
    m.h2("6.2  状态颜色语义")
    m.para(
        "每台载具在沙盘上带名称标签，并按下图例语义着色，"
        "使全域载具的作业状态一眼可辨："
    )
    m.table(
        ["状态", "颜色语义", "含义"],
        [
            ["航行中", "青绿色", "载具正前往作业目标点"],
            ["作业中", "橙色", "载具正在目标点执行清理作业"],
            ["已派单", "紫色", "工单已派发、等待载具确认"],
            ["离线", "灰色", "载具不在线"],
        ],
        widths_cm=[3.0, 3.6, 8.9]
    )
    m.h2("6.3  点选与操作卡")
    m.para(
        "沙盘采用两段式交互：点击载具先弹出操作卡（不立即跳转），"
        "在卡片上确认后才执行跳转，避免在密集点位中误触。"
    )
    m.steps([
        "将鼠标悬停在载具上，出现悬停信息卡；",
        "点击载具，弹出操作卡，显示载具名称、在线状态与电量、载具类型；",
        "若该载具绑定了工单，卡片显示「对应工单」编号；",
        "点击「查看对应工单 / 查看相关工单」进入工单看板；点击卡片右上角 × 取消选中。",
    ])
    m.page_break()


def build_sandbox_routes(m: Manual) -> None:
    m.h1("7  作业航线与轨迹回放")
    m.h2("7.1  航线与作业目标点")
    m.para(
        "当工单进入派发、航行或作业状态时，沙盘自动为对应载具绘制航线："
        "载具当前位置至作业目标点之间以脉冲圆点标示剩余航线，"
        "目标点以浮标标记并带双重脉冲环，醒目指示作业目的地。"
        "点击目标浮标可弹出「作业目标点」操作卡，显示关联工单编号，"
        "点击「进入工单仿真」即可跳转到该工单的执行仿真页（见第 9 章）。"
    )
    m.image(UI / "1920x1080-sandbox-route.png", "图 7-1  作业目标点操作卡（关联工单跳转入口）")
    m.h2("7.2  已走轨迹")
    m.para(
        "载具航行过程中，沙盘实时累积其实际航迹并以带状轨迹绘制，"
        "与剩余航线（脉冲圆点）在同一处图例下呈现，"
        "指挥人员可据此核对「计划航线」与「实际航迹」的偏差。"
    )
    m.h2("7.3  轨迹回放")
    m.para(
        "在工单执行仿真页的「地图」视图中，可对作业轨迹做回放查看："
        "地图上以图例区分「已走轨迹」与「剩余航线」，标注目标点与载具实时位置，"
        "并显示本单总航程；配合右侧执行档案中的生命周期时间链"
        "（创建—派单—机器人确认—开始作业—完成），可完整复核一次作业的时空过程。"
    )
    m.image(UI / "1920x1080-sandbox-sim-map.png", "图 7-2  作业轨迹回放视图（已走轨迹与剩余航线）")
    m.page_break()


def build_sandbox_layers(m: Manual) -> None:
    m.h1("8  图层与事件联动")
    m.h2("8.1  海漂垃圾分布图层")
    m.para(
        "沙盘以「发光点 + 向天空射出的光柱」呈现垃圾分布："
        "海浮垃圾点位位于近岸与海湾水面，随水流缓慢漂移并随浪面起伏；"
        "沙滩垃圾沿岸线低平地带分布，静态微闪。"
        "两类点位均按四类垃圾配色（泡沫、塑料、渔具、其他），"
        "远看是一根根从海面射向天空的信号线，使垃圾聚集区在全局视角下也清晰可见。"
    )
    m.image(UI / "1920x1080-sandbox-debris.png", "图 8-1  海漂垃圾分布图层（点选后弹出类别卡）")
    m.steps([
        "垃圾点位以确定性方式生成，刷新页面位置不跳变，便于对照核查；",
        "点击任一垃圾点位，弹出操作卡显示「海浮垃圾 / 沙滩垃圾」与所属类别；",
        "点击「查看相关事件」按类别筛选进入事件中心，查看对应告警记录。",
    ])
    m.h2("8.2  海域设施图层")
    m.para(
        "沙盘对海域内的固定设施分层呈现：渔排养殖区、礁体与岸线设施"
        "以专用图层绘制于地形之上，与动态要素（载具、垃圾、事件）分离管理，"
        "避免固定设施在动态图层频繁刷新时重复绘制。"
    )
    m.h2("8.3  事件点联动")
    m.para(
        "边缘感知上报的告警事件在沙盘上以事件点标记呈现，"
        "颜色与垃圾类别配色一致；点击事件点弹出操作卡，"
        "显示事件类别与识别目标数量，并可跳转事件中心查看详情与处置记录，"
        "实现「沙盘点位」与「业务台账」的双向联动。"
    )
    m.image(UI / "1920x1080-sandbox-event.png", "图 8-2  事件点操作卡（跳转事件详情入口）")
    m.page_break()


def build_sandbox_simulation(m: Manual) -> None:
    m.h1("9  仿真推演沙盒")
    m.h2("9.1  启动与推演控制")
    m.para(
        "仿真推演沙盒用于在不触碰真机的前提下完整演练一次作业闭环："
        "打开仿真页后页面只加载当前状态、不自动开跑，"
        "由操作者点击「▶ 启动」后开始推演；推演过程提供倍速（1x / 2x / 4x）、"
        "单步执行、暂停 / 继续与停止等控制，便于逐相位观察与讲解。"
    )
    m.image(UI / "1920x1080-sandbox-simulation.png",
            "图 9-1  仿真推演页运行态（作业中，倍速与单步控制条）")
    m.steps([
        "在工单看板选择活跃工单，或在沙盘点击作业目标点经「进入工单仿真」进入；",
        "页面加载后点击「▶ 启动」，推演开始；",
        "按需切换 1x / 2x / 4x 倍速，或使用「单步」逐相位推进；",
        "随时「停止」推演，或在完成后「刷新」重新加载状态复核。",
    ])
    m.h2("9.2  推演过程与闭环")
    m.para(
        "推演严格沿正式状态机推进：机器人确认（ACK）→ 前往目标点 → 执行清理作业"
        "→ 返航 → 闭环完成。推演过程中，载具在沙盘上沿航线移动、"
        "仓容与电量随作业变化，地图视图实时绘制已走轨迹，"
        "右侧执行档案同步刷新生命周期时间链与运行日志。"
    )
    m.para(
        "推演不依赖真机、也无需连接消息代理：设备侧报文由仿真执行器在进程内"
        "按时间直接注入正式消息处理链路，因此仿真中的状态迁移、ACK 审计账本、"
        "轨迹记录与页面推送与真实执行完全一致，而不会向任何真实机器人下发指令。"
    )
    m.h2("9.3  闭环完成与复核")
    m.para(
        "推演完成后，页面状态显示「闭环完成」，执行档案中记录打捞重量、"
        "最终结果与各阶段时间戳，运行日志保留本次推演的机器人报文数量，"
        "可整体作为一次作业演练的复核材料。"
    )
    m.image(UI / "1920x1080-sandbox-sim-done.png", "图 9-2  推演闭环完成（执行档案与运行日志）")
    m.page_break()


def build_sandbox_bigscreen(m: Manual) -> None:
    m.h1("10  大屏展示模式")
    m.h2("10.1  大屏适配")
    m.para(
        "监测大屏按大屏终端分辨率自适应布局：顶部为治理指标卡，"
        "中部左侧为现场视频、中央为三维海域态势沙盘、右侧为实时告警流，"
        "底部为事件趋势、类别分布与机器人状态面板。"
        "在 1920×1080 与 2560×1440 等分辨率下均保持完整分区与清晰可读。"
    )
    m.image(UI / "2560x1440-sandbox-dashboard.png", "图 10-1  监测大屏（2560×1440 分辨率适配）")
    m.h2("10.2  全屏与快捷导航")
    m.bullets([
        "沙盘「全屏查看」：将三维沙盘铺满整屏，用于大屏值守与汇报演示；",
        "顶栏导航直达：监测大屏、事件中心、工单看板等页面一键切换；",
        "数字键快捷导航：键盘数字键 1-9 可直接切换到对应导航页，便于演示巡场；",
        "实时状态提示：顶栏显示实时连接状态，沙盘数据在网络恢复后自动回补。",
    ])
    m.page_break()


def build_sandbox_faq(m: Manual) -> None:
    m.h1("11  常见问题与处理")
    m.table(
        ["现象", "可能原因", "处理方法"],
        [
            ["页面提示 WebGL 不可用 / 场景黑屏", "浏览器未开启硬件加速", "在浏览器设置中开启「使用硬件加速」后重启浏览器"],
            ["沙盘首次加载较慢", "地形数据与三维资源首次加载", "等待进度提示完成；再次访问将走缓存加快"],
            ["大屏文字偏小", "分辨率与缩放比例不匹配", "使用浏览器全屏（F11）或沙盘「全屏查看」"],
            ["沙盘数据不更新", "实时连接中断", "查看顶栏「实时已连接」状态，刷新页面重试"],
            ["点选载具无响应", "点在其他图层要素上", "调整视角后再点选；载具过小时先放大一级"],
        ],
        widths_cm=[4.2, 4.6, 6.7]
    )
    m.page_break()


def build_sandbox_appendix(m: Manual) -> None:
    m.h1("12  附录：图层配色与数据约定")
    m.para("沙盘图层与状态配色约定如下（与图例一致）：")
    m.table(
        ["要素", "配色", "说明"],
        [
            ["航行中载具", "青绿 #18A999", "正在前往作业目标点"],
            ["作业中载具", "橙 #FF9500", "正在目标点执行清理"],
            ["已派单载具", "紫 #7A5AF8", "等待机器人确认"],
            ["离线载具", "灰 #7A8798", "不在线"],
            ["事件点", "红 #FF3B30", "告警事件标记"],
            ["泡沫垃圾", "橙 #FF9500", "foam 类点位与光柱"],
            ["塑料垃圾", "蓝 #007AFF", "plastic 类点位与光柱"],
            ["渔具垃圾", "红 #FF3B30", "fishing_gear 类点位与光柱"],
            ["其他垃圾", "灰 #8E8E93", "other 类点位与光柱"],
        ],
        widths_cm=[3.4, 3.6, 8.5]
    )
    m.para("沙盘对外数据约定：")
    m.table(
        ["类别", "约定"],
        [
            ["态势数据", "经 REST 接口获取机器人、事件、工单与热力数据"],
            ["实时通道", "WebSocket 订阅状态变更，断线自动重连"],
            ["工单联动", "沙盘操作卡按工单编号跳转工单看板 / 执行仿真页"],
            ["仿真控制", "推演启动、倍速、暂停继续、单步与停止均经工单仿真接口"],
        ],
        widths_cm=[3.0, 12.5]
    )
    m.para(
        "本说明书随软件版本迭代更新。如与系统实际运行版本存在差异，以软件实际运行版本为准。"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成软著软件说明书")
    parser.add_argument(
        "--out", default=r"C:\Users\Liii\Desktop\Oceanus软著材料", help="输出目录"
    )
    parser.add_argument(
        "--variant",
        choices=("main", "agent", "arm", "edge", "sandbox"),
        default="main",
        help="main=主软著（整体覆盖）；agent=拆分登记第 2 篇（决策与审批）；"
             "arm=拆分登记第 4 篇（机械臂控制）；edge=拆分登记第 1 篇（边缘智能感知）；"
             "sandbox=拆分登记第 3 篇（三维数字沙盘）",
    )
    args = parser.parse_args()
    select_variant(args.variant)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    m = Manual()
    if args.variant == "edge":
        build_edge_cover(m)
        build_edge_toc(m)
        build_edge_intro(m)
        build_edge_overview(m)
        build_edge_env(m)
        build_edge_deploy(m)
        build_edge_capture(m)
        build_edge_detect(m)
        build_edge_world(m)
        build_edge_temporal(m)
        build_edge_report(m)
        build_edge_simulator(m)
        build_edge_ops(m)
        build_edge_appendix(m)
        full_name = EDGE_FULL_NAME
    elif args.variant == "arm":
        build_arm_cover(m)
        build_arm_toc(m)
        build_arm_intro(m)
        build_arm_overview(m)
        build_arm_env(m)
        build_arm_deploy(m)
        build_arm_mqtt(m)
        build_arm_pick(m)
        build_arm_ros(m)
        build_arm_hiwonder(m)
        build_arm_dual(m)
        build_arm_calib(m)
        build_arm_safety(m)
        build_arm_appendix(m)
        full_name = ARM_FULL_NAME
    elif args.variant == "agent":
        build_agent_cover(m)
        build_agent_toc(m)
        build_agent_intro(m)
        build_agent_overview(m)
        build_agent_env(m)
        build_agent_deploy(m)
        build_agent_assess(m)
        build_agent_run(m)
        build_agent_approval(m)
        build_agent_dispatch(m)
        build_agent_tools(m)
        build_agent_lessons(m)
        build_agent_persistence(m)
        build_agent_ops(m)
        build_agent_appendix(m)
        full_name = AGENT_FULL_NAME
    elif args.variant == "sandbox":
        build_sandbox_cover(m)
        build_sandbox_toc(m)
        build_sandbox_intro(m)
        build_sandbox_overview(m)
        build_sandbox_env(m)
        build_sandbox_deploy(m)
        build_sandbox_terrain(m)
        build_sandbox_vessels(m)
        build_sandbox_routes(m)
        build_sandbox_layers(m)
        build_sandbox_simulation(m)
        build_sandbox_bigscreen(m)
        build_sandbox_faq(m)
        build_sandbox_appendix(m)
        full_name = SANDBOX_FULL_NAME
    else:
        build_cover(m)
        build_toc(m)
        build_intro(m)
        build_overview(m)
        build_env(m)
        build_deploy(m)
        build_operations(m)
        build_faq(m)
        build_appendix(m)
        full_name = SOFTWARE_FULL_NAME

    doc = m.build()
    path = out_dir / f"软件说明书_{full_name}{VERSION}.docx"
    doc.save(path)
    print(f"已生成: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
