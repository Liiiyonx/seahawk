#!/usr/bin/env python3
"""Build the Huawei ICT track-3 design document DOCX.

Uses the shared DOCX renderer (``build_plan_docx.py``) with a cover/header
tuned for the track-3 submission instead of the proposal booklet.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_plan_docx  # noqa: E402


def main() -> None:
    source = ROOT / "docs" / "competitions" / "huawei-ict-track3-design-doc.md"
    output = ROOT / "项目文档" / "华为ICT赛道三_开发设计文档.docx"

    metadata, blocks = build_plan_docx.parse_markdown(source.read_text(encoding="utf-8"))
    h1_count = sum(1 for block in blocks if block.kind == "heading" and block.level == 1)
    cover_meta_rows = [
        ("版本", metadata.get("版本", "1.0")),
        ("编制日期", metadata.get("编制日期", "2026-09-29")),
        ("参赛赛道", "华为 ICT 大赛 创新赛道三"),
        ("文档定位", "初赛/决赛评测要求的开发设计文档"),
        ("证据口径", "E0-E4 内部纪律；感知精度 not_evaluated"),
        ("章节数量", f"{h1_count} 个一级章节"),
    ]

    result = build_plan_docx.build_docx(
        source,
        output,
        header_text="\t探海灵眸 SeaSight  |  华为 ICT 赛道三 · 开发设计文档",
        cover_title="探海灵眸 SeaSight 可进化决策智能体开发设计文档",
        cover_subtitle="华为 ICT 大赛 创新赛道三",
        cover_statement="政务-县域海洋环境治理 · 领域资产认知智能体",
        cover_meta_rows=cover_meta_rows,
        cover_boundary=(
            "本文档严格区分代码/测试、合成验证、本地平台侧验收与华为托管平台验收；"
            "所有对外数字必须回到证据台账。"
        ),
        core_title="探海灵眸 SeaSight 可进化决策智能体开发设计文档",
        core_subject="华为 ICT 大赛 创新赛道三初赛/决赛评测材料",
        core_author="SeaSight 项目组",
        core_comments="严格区分 E0-E4 证据；平台侧验收不等于海域验证或感知精度。",
    )
    print(result)


if __name__ == "__main__":
    main()
