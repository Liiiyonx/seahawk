#!/usr/bin/env python3
"""Build the Huawei ICT track-3 agent design DOCX (submission material 2).

Uses the shared DOCX renderer (``build_plan_docx.py``) with a cover/header
tuned for the "Nexent platform agent design" submission instead of the
development design document.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_plan_docx  # noqa: E402


def main() -> None:
    source = ROOT / "docs" / "competitions" / "huawei-ict-track3-agent-design.md"
    output = ROOT / "项目文档" / "华为ICT赛道三_Nexent智能体设计说明.docx"

    metadata, blocks = build_plan_docx.parse_markdown(source.read_text(encoding="utf-8"))
    h1_count = sum(1 for block in blocks if block.kind == "heading" and block.level == 1)
    cover_meta_rows = [
        ("版本", metadata.get("版本", "1.0")),
        ("编制日期", metadata.get("编制日期", "2026-09-30")),
        ("参赛赛道", "华为 ICT 大赛 创新赛道三"),
        ("文档定位", "初赛/决赛评测要求的智能体整体设计说明（材料 2）"),
        ("证据口径", "本地官方源码部署已验收；托管平台 R-NX-07 blocked"),
        ("章节数量", f"{h1_count} 个一级章节"),
    ]

    result = build_plan_docx.build_docx(
        source,
        output,
        header_text="\t探海灵眸 Oceanus  |  华为 ICT 赛道三 · Nexent 智能体设计说明",
        cover_title="探海灵眸 Oceanus Nexent 智能体整体设计说明",
        cover_subtitle="华为 ICT 大赛 创新赛道三",
        cover_statement="领域资产认知智能体 · MCP 工具面 + Skill 分层编排",
        cover_meta_rows=cover_meta_rows,
        cover_boundary=(
            "本地官方源码部署已跑通完整 Skill 问答；华为 AgentArts 托管平台内完整"
            "问答仍为 blocked，两者不可混写。"
        ),
        core_title="探海灵眸 Oceanus Nexent 智能体整体设计说明",
        core_subject="华为 ICT 大赛 创新赛道三初赛/决赛评测材料（材料 2）",
        core_author="Oceanus 项目组",
        core_comments="严格区分本地 Nexent 验收与华为托管平台验收；感知精度 not_evaluated。",
    )
    print(result)


if __name__ == "__main__":
    main()
