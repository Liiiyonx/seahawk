#!/usr/bin/env python3
"""Build the Huawei ICT track-3 attachment guide DOCX (submission material 3).

Renders docs/competitions/huawei-ict-track3-attachment-guide.md with the shared
DOCX renderer so material 3 ships as Word (uniform with materials 1/2) instead
of raw Markdown.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_plan_docx  # noqa: E402


def main() -> None:
    source = ROOT / "docs" / "competitions" / "huawei-ict-track3-attachment-guide.md"
    output = ROOT / "项目文档" / "华为ICT赛道三_附送文件说明.docx"

    metadata, blocks = build_plan_docx.parse_markdown(source.read_text(encoding="utf-8"))
    h1_count = sum(1 for b in blocks if b.kind == "heading" and b.level == 1)

    result = build_plan_docx.build_docx(
        source,
        output,
        header_text="\t探海灵眸 Oceanus  |  华为 ICT 赛道三 · 随附文件说明",
        cover_title="探海灵眸 Oceanus 赛道三随附文件说明",
        cover_subtitle="华为 ICT 大赛 创新赛道三",
        cover_statement="材料 3 · 随附文件逐项说明与登记号对照",
        cover_meta_rows=[
            ("版本", metadata.get("版本", "1.2")),
            ("编制日期", metadata.get("编制日期", "2026-10-25")),
            ("参赛赛道", "华为 ICT 大赛 创新赛道三"),
            ("文档定位", "与开发设计文档、智能体设计说明同步提交的随附文件说明（材料 3）"),
            ("证据口径", "全部随附文件按登记号治理，证据等级与适用边界逐项标注"),
            ("章节数量", f"{h1_count} 个一级章节"),
        ],
        cover_boundary=(
            "本文档与 01_开发设计文档.docx、02_智能体设计说明.docx 同包提交；"
            "演示级证据不表述为真实行业效果。"
        ),
        core_title="探海灵眸 Oceanus 赛道三随附文件说明",
        core_subject="华为 ICT 大赛 创新赛道三初赛评测材料（材料 3）",
        core_author="Oceanus 项目组",
        core_comments="随附文件按登记号对照；证据等级 E0-E4 逐项标注。",
        toc_with_pages=False,
    )
    print(result)


if __name__ == "__main__":
    main()
