"""One-off patch: material-1 docx (提交包/01_开发设计文档.docx) — R-NX-10 update.

Applies in-place text edits (scoring table, MCP paragraph, fullstack table,
honest boundary, closing paragraph, figure caption) and swaps the embedded
fig-huawei-fullstack.png (matched by pixel size 1475x997) with the regenerated
R-NX-10 version. Backup is written next to the target before saving.
"""
import copy
import shutil
import sys
from pathlib import Path

import docx
from PIL import Image

TARGET = Path(r"C:\Users\Liii\Desktop\华为ICT大赛\提交包\01_开发设计文档.docx")
BACKUP = TARGET.with_suffix(".docx.bak-rnx10")
NEW_FIG = Path(r"C:\Users\Liii\Desktop\seahawk\artifacts\doc-figures\fig-huawei-fullstack.png")
NEW_FIG_SIZE = (1475, 997)

REPLACEMENTS = [
    # (old_substring, new_substring) applied to every paragraph/cell text run-wise
    (
        "本地官方源码部署完整 LLM Skill 问答（一次运行 8 步、31 次工具调用）；华为 AgentArts 托管平台内完整 Skill 问答已跑通（9 分钟 1933 帧、真实模型、证据不足如实拒答）",
        "本地官方源码部署完整 LLM Skill 问答（一次运行 8 步、31 次工具调用）；华为 AgentArts 托管平台内完整 Skill 问答已跑通（9 分钟 1933 帧、真实模型、证据不足如实拒答）；平台内 MCP 工具面真实调用验证通过（event_list + knowledge_search 共 6 次调用、平台调用链与 ECS 服务端日志逐条对应）",
    ),
    (
        "登记号 R-NX-09 / R-NX-08",
        "登记号 R-NX-09 / R-NX-08 / R-NX-10",
    ),
    (
        "本体抽取具备 LLM 主通道并在真实公开政务文本上完成双通道对照评测（登记号 R-LLM-01/02）。",
        "本体抽取具备 LLM 主通道并在真实公开政务文本上完成双通道对照评测（登记号 R-LLM-01/02）。2026-10-25 进一步完成托管平台内 MCP 工具面真实调用验证（登记号 R-NX-10）：两次问答共 6 次 MCP 调用全部成功——event_list 首查遇后端 500 后智能体自动去过滤重试拿到 17 条事件，knowledge_search 返回 200；平台调试抽屉调用链与 ECS 服务端 MCP 日志逐条对应，构成“托管平台内智能体真实调用外部工具面”的端到端证据。",
    ),
    (
        "感知识别精度为 not_evaluated（未评测）；本项目使用的真实公开数据（政务公开文件、NOAA NCEI 公开监测数据）不等于真实脱敏行业内部数据；演示数据不参与任何精度宣称；托管平台本次验收运行中 MCP 知识域工具不可用（网关 Target 指向丢失的旧 ECS），智能体改用文件检索并如实报告——工具面恢复为后续待办。",
        "感知识别精度为 not_evaluated（未评测）；本项目使用的真实公开数据（政务公开文件、NOAA NCEI 公开监测数据）不等于真实脱敏行业内部数据；演示数据不参与任何精度宣称；托管平台验收分两次独立登记——R-NX-08（完整 Skill 问答，当次 MCP 工具不可用为如实登记的历史中间态）与 R-NX-10（MCP 工具面真实调用验证，预览调试通道、event_list 一次 500 后重试成功、写入类工具未启用），两次不混写、不越级宣称。",
    ),
    (
        "已在本地 Nexent 与华为 AgentArts 托管平台双端完成完整 LLM Skill 问答验收（托管平台一次运行 9 分钟、1933 帧、证据不足如实拒答），并在真实",
        "已在本地 Nexent 与华为 AgentArts 托管平台双端完成完整 LLM Skill 问答验收（托管平台一次运行 9 分钟、1933 帧、证据不足如实拒答），并完成平台内 MCP 工具面真实调用验证（R-NX-10：6 次调用、服务端日志逐条对应），并在真实",
    ),
    (
        "图 8 华为云全栈部署与验收拓扑：AgentArts 托管智能体（VPC 私网）→ ECS TLS 模型中转 → DeepSeek API；知识域 LLM 通道 → ModelArts MaaS（昇腾池）（R-NX-08 / R-MA-01）",
        "图 8 华为云全栈部署与验收拓扑：AgentArts 托管智能体（VPC 私网）→ ECS TLS 模型中转 → DeepSeek API；知识域 LLM 通道 → ModelArts MaaS（昇腾池）；平台内 MCP 工具面已打通（R-NX-08 / R-NX-10 / R-MA-01）",
    ),
]

TABLE_ROW_AFTER = (
    "VPC / 安全组 / EIP",
    [
        "MCP 工具面（平台内）",
        "运行时→隧道→ECS MCP→Oceanus 后端全链路；event_list + knowledge_search 共 6 次调用成功；服务端日志逐条对应",
        "07_证据包/R-NX-10_COMPLETED.yaml + evidence/hosted-qa-2026-10-25/",
    ],
)


def iter_paragraphs(document):
    for p in document.paragraphs:
        yield p
    for t in document.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    yield p
                for nested in cell.tables:
                    for nrow in nested.rows:
                        for ncell in nrow.cells:
                            for np in ncell.paragraphs:
                                yield np


def replace_in_paragraph(par, old, new):
    full = par.text
    if old not in full:
        return False
    # single-run fast path
    for run in par.runs:
        if old in run.text:
            run.text = run.text.replace(old, new)
            return True
    # cross-run: rebuild text into first run, clear the rest
    joined = full.replace(old, new)
    runs = par.runs
    if not runs:
        return False
    runs[0].text = joined
    for r in runs[1:]:
        r.text = ""
    return True


def main():
    shutil.copy2(TARGET, BACKUP)
    document = docx.Document(str(TARGET))
    applied = {old: 0 for old, _ in REPLACEMENTS}

    for par in iter_paragraphs(document):
        for old, new in REPLACEMENTS:
            if applied[old] == 0 and replace_in_paragraph(par, old, new):
                applied[old] += 1

    missing = [old[:40] for old, n in applied.items() if n == 0]
    if missing:
        print("WARN unmatched replacements:", missing)

    # insert fullstack table row after the VPC row
    inserted = False
    for t in document.tables:
        for i, row in enumerate(t.rows):
            row_text = "".join(c.text for c in row.cells)
            if TABLE_ROW_AFTER[0] in row_text and "安全组" in row_text:
                new_row = copy.deepcopy(row._tr)
                # clear copied cell text
                for tc in new_row.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
                    tc.text = ""
                t._tbl.insert(list(t._tbl).index(row._tr) + 1, new_row)
                from docx.table import _Cell
                tr_cells = [_Cell(tc, t) for tc in new_row.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tc")]
                for cell, text in zip(tr_cells, TABLE_ROW_AFTER[1]):
                    p = cell.paragraphs[0]
                    run = p.add_run(text)
                    from docx.shared import Pt
                    run.font.size = Pt(9)
                inserted = True
                break
        if inserted:
            break
    print("fullstack row inserted:", inserted)

    # swap embedded fullstack figure by pixel-size match
    swapped = 0
    fig_bytes = NEW_FIG.read_bytes()
    for rel_id, rel in list(document.part.rels.items()):
        if "image" not in rel.reltype:
            continue
        part = rel.target_part
        blob = part.blob
        if not blob:
            continue
        try:
            import io as _io
            im = Image.open(_io.BytesIO(blob))
            if im.size == NEW_FIG_SIZE:
                part._blob = fig_bytes
                swapped += 1
        except Exception:
            continue
    print("images swapped:", swapped)

    document.save(str(TARGET))
    print("saved:", TARGET, "(backup:", BACKUP.name + ")")
    if missing or not inserted or swapped == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
