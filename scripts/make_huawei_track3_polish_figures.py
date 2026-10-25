#!/usr/bin/env python3
"""Generate the four supplementary figures for the 2026-10-25 national-award
polish of Huawei ICT track-3 materials (artifacts/doc-figures/).

Facts pinned to acceptance records (no invented numbers):
- fig-m2-knowledge-pipeline : knowledge-domain lifecycle (R-KN-01/02, R-LLM-01/02, R-MA-01)
- fig-m2-call-graph         : agent -> skills -> MCP -> api -> db (R-NX-04, R-NX-09)
- fig-m2-dual-drive         : retrieval-reasoning dual-drive flow (R-KN-05/06)
- fig-huawei-fullstack      : hosted-platform + ModelArts topology (R-NX-05/08, R-MA-01)

Reuses the box-fit machinery from make_huawei_ict_doc_figures.py so no text
can overflow its box.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from make_huawei_ict_doc_figures import (  # noqa: E402
    BLUE, LIGHT, EDGE, ORANGE, GREEN, PURPLE, RED, GRAY,
    WARNINGS, arrow, elbow_arrow, est_width_pt, make_box,
)

OUT = ROOT / "artifacts" / "doc-figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False


def _zone(ax, x, y, w, h, title, color):
    import matplotlib.patches as mpatches
    ax.add_patch(mpatches.FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.012",
        fc="#ffffff", ec=color, lw=1.6, linestyle=(0, (6, 3))))
    ax.text(x + 0.012, y + h - 0.022, title, ha="left", va="center",
            fontsize=10.5, weight="bold", color=color)


def fig_knowledge_pipeline() -> None:
    W, H = 7.6, 4.4
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    box = make_box(W, H)

    box(ax, 0.020, 0.66, 0.21, 0.24, "六类资产登记",
        ["document·table·image", "event·telemetry·dataset",
         "不可变版本·内容哈希", "standard_codes 对齐"], fs=7.2, tfs=9.5)
    box(ax, 0.250, 0.66, 0.20, 0.24, "候选抽取（双通道）",
        ["规则：词频+共现（可解释）", "LLM 主通道：JSON schema",
         "实体/关系类型限定词表", "引文必摘原文·失败回退规则"],
        fc="#fdf3e3", ec=ORANGE, fs=7.2, tfs=9.5)
    box(ax, 0.470, 0.66, 0.145, 0.24, "人工审核",
        ["候选默认 proposed", "approver 逐条审核", "发布校验"], fs=7.2, tfs=9.5)
    box(ax, 0.635, 0.66, 0.145, 0.24, "本体版本发布",
        ["版本链可继承父版本", "发布→旧版退役", "检索用最新已发布版"], fs=7.2, tfs=9.5)
    box(ax, 0.800, 0.66, 0.175, 0.24, "持续更新（R-KN-03）",
        ["增量抽取 1.615ms", "全量重抽 4.387ms", "节省 63.19%"], fc="#e8f4ec", ec=GREEN, fs=7.2, tfs=9.5)

    for x1, x2 in ((0.230, 0.250), (0.450, 0.470), (0.615, 0.635), (0.780, 0.800)):
        arrow(ax, (x1, 0.78), (x2, 0.78), lw=1.6)

    box(ax, 0.025, 0.34, 0.28, 0.22, "跨文档多跳检索",
        ["有本体：mode=ontology_graph", "返回 path / hop / citations",
         "无本体：明确回退 keyword", "不冒充图谱检索"], fs=7.8, tfs=10)
    box(ax, 0.345, 0.34, 0.28, 0.22, "决策证据链固化",
        ["按顺序固化证据", "资产版本 + 节点 + 关系 + 跳数",
         "hop=0/1/2 三档实例（R-KN-05）", "可按当时口径回放"], fs=7.8, tfs=10)
    box(ax, 0.665, 0.34, 0.31, 0.22, "检索-生成问答（R-KN-06）",
        ["先多跳检索，模型只依据证据作答", "回答内嵌 [c:n] 引用徽章",
         "证据不足 → insufficient_evidence 拒答", "模型失败 → 降级证据列表"],
        fc="#f0ecfa", ec=PURPLE, fs=7.8, tfs=10)

    arrow(ax, (0.30, 0.66), (0.18, 0.56), lw=1.6)
    arrow(ax, (0.16, 0.34), (0.345, 0.45), lw=1.6)
    arrow(ax, (0.625, 0.45), (0.665, 0.45), lw=1.6)

    box(ax, 0.025, 0.075, 0.45, 0.20, "评测口径（如实，含负结果）",
        ["真实公开政务语料：LLM 18 关系全带类型与引用（R-LLM-02）",
         "合成语料术语：规则 11/20 · DeepSeek 9/20",
         "GLM-5.3（昇腾池）13/20 反超（R-LLM-01 / R-MA-01）",
         "弱项如实报告：合成语料关系两通道各 1/7"], fs=7.2, tfs=9.5)
    box(ax, 0.505, 0.075, 0.47, 0.20, "对外暴露",
        ["MCP 工具面 21 只读 + 11 写入（显式开关）",
         "5 个 Skill 工作流模板（跨行业可复用）",
         "Nexent 编排调用（R-NX-04 / 09），",
         "本地与华为托管平台双端验收"], fc="#e8f4ec", ec=GREEN, fs=7.2, tfs=9.5)
    arrow(ax, (0.18, 0.34), (0.18, 0.277), lw=1.6)
    arrow(ax, (0.73, 0.34), (0.73, 0.277), color=GREEN, lw=1.6)

    fig.tight_layout(pad=0.4)
    fig.savefig(OUT / "fig-m2-knowledge-pipeline.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_call_graph() -> None:
    W, H = 7.6, 4.6
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    box = make_box(W, H)

    box(ax, 0.30, 0.845, 0.40, 0.115, "用户问题（示例：疑似漏油事件处置依据）", [], fs=8.5, tfs=10)
    box(ax, 0.22, 0.60, 0.56, 0.185, "Nexent Agent：seasight_governance_decision_agent",
        ["发布版本 4 v0.2.0-seasight-governance-llm（RELEASED）",
         "模型：DeepSeek deepseek-v4-pro · SSE 流式 · 失败回退规则规划器"],
        fc="#dbe7f7", ec=BLUE, fs=8.2, tfs=10.5)
    arrow(ax, (0.5, 0.845), (0.5, 0.785), lw=1.8)

    skills = [
        (0.025, "policy-evidence-qa", "政策证据问答"),
        (0.219, "marine-event-assessment", "事件研判"),
        (0.413, "cross-document-decision", "跨文档多跳决策"),
        (0.607, "dispatch-work-order-", "工单编排"),
        (0.801, "decision-trace-audit", "决策轨迹审计"),
    ]
    for x, name, cn in skills:
        box(ax, x, 0.415, 0.174, 0.115, cn,
            [name.replace("-", ""), "read_skill_md 载入"], fc="#f0ecfa", ec=PURPLE, fs=6.8, tfs=8.2)
        arrow(ax, (x + 0.087, 0.415), (0.5, 0.60 - 0.006), color=PURPLE, lw=1.2)
    ax.text(0.5, 0.395, "Skill 工作流模板 ×5（触发条件 / 工具顺序 / 停止条件 / 输出要求；绑定 5 个，示例问题实际加载 4 个）",
            ha="center", fontsize=7.6, color=PURPLE)

    box(ax, 0.10, 0.235, 0.80, 0.115, "Oceanus Domain Cognition MCP（21 只读 + 11 写入显式开关）",
        ["Bearer 入站鉴权 fail-closed · 出站最小权限只读账号自动刷新 · 业务失败→工具错误，不伪装成功"],
        fc="#fdf3e3", ec=ORANGE, fs=8.2, tfs=10.5)
    arrow(ax, (0.5, 0.372), (0.5, 0.352), lw=1.8, label="MCP 协议（stdio / Streamable HTTP）", lfs=8)

    groups = [
        (0.025, "资产·本体·检索", "7 工具"),
        (0.219, "决策", "2 工具"),
        (0.413, "业务（事件/工单/看板）", "6 工具"),
        (0.607, "Agent 审计", "6 工具"),
        (0.801, "写入（显式开关）", "11 工具"),
    ]
    for x, name, cnt in groups:
        box(ax, x, 0.10, 0.174, 0.095, name, (cnt,), fs=7.0, tfs=8.4)
        arrow(ax, (x + 0.087, 0.235), (x + 0.087, 0.197), lw=1.2)

    box(ax, 0.025, 0.015, 0.95, 0.058,
        "Oceanus /api/v1（角色 / 辖区 / 审批 / 幂等 / 审计） → PostgreSQL（资产 / 本体 / 决策 / 事件 / 任务）",
        [], fc="#e8f4ec", ec=GREEN, fs=8.0, tfs=8.8)
    arrow(ax, (0.5, 0.10), (0.5, 0.075), lw=1.6, color=GREEN)

    ax.text(0.985, 0.885, "实测（R-NX-09）：一次运行 HTTP 200 · 8 步 · 31 次工具调用 · 13 个唯一工具 · 2,777 字回答",
            ha="right", fontsize=7.6, color=GRAY)
    ax.text(0.985, 0.845, "调用关系由平台 API 真实返回（R-NX-04）：GET /api/agent/call_relationship/1",
            ha="right", fontsize=7.6, color=GRAY)

    fig.tight_layout(pad=0.4)
    fig.savefig(OUT / "fig-m2-call-graph.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_dual_drive() -> None:
    W, H = 7.6, 4.2
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    box = make_box(W, H)

    box(ax, 0.40, 0.885, 0.20, 0.09, "用户问题", [], fs=8.5, tfs=10)
    arrow(ax, (0.5, 0.885), (0.5, 0.845), lw=1.8)
    box(ax, 0.33, 0.745, 0.34, 0.095, "Skill 选择（触发条件匹配）", ["read_skill_md 载入工作流"], fs=8, tfs=9.5)
    arrow(ax, (0.5, 0.745), (0.5, 0.705), lw=1.8)
    arrow(ax, (0.5, 0.705), (0.27, 0.705), lw=1.4)
    arrow(ax, (0.5, 0.705), (0.73, 0.705), lw=1.4)

    box(ax, 0.025, 0.505, 0.44, 0.195, "检索驱动（确定性，可引用）",
        ["knowledge_search 资产打分检索", "资产/本体/决策/事件/工单列举",
         "返回资产版本、片段与引用"], fs=8, tfs=10)
    box(ax, 0.535, 0.505, 0.44, 0.195, "推理驱动（本体引导）",
        ["已发布本体：多跳检索", "mode / path / hop / citations",
         "无可用本体：明确回退，不冒充图谱"], fc="#fdf3e3", ec=ORANGE, fs=8, tfs=10)
    arrow(ax, (0.27, 0.505), (0.42, 0.425), lw=1.6)
    arrow(ax, (0.73, 0.505), (0.58, 0.425), lw=1.6)

    import matplotlib.patches as mpatches
    ax.add_patch(mpatches.FancyBboxPatch((0.375, 0.30), 0.25, 0.115,
                 boxstyle="round,pad=0.002,rounding_size=0.01",
                 fc="#fdeaea", ec=RED, lw=1.5))
    ax.text(0.5, 0.395, "证据是否充分？", ha="center", va="center", fontsize=9.5, weight="bold", color="#8a3a34")
    ax.text(0.5, 0.345, "（模型只依据检索证据判断）", ha="center", va="center", fontsize=7.4, color=GRAY)

    box(ax, 0.025, 0.075, 0.44, 0.185, "是 → 决策固化与生成",
        ["决策按顺序固化证据链：资产版本+节点+关系+跳数",
         "生成回答内嵌 [c:n] 引用（R-KN-06）",
         "前端引用徽章可点击定位证据卡"], fc="#e8f4ec", ec=GREEN, fs=7.8, tfs=9.5)
    box(ax, 0.535, 0.075, 0.44, 0.185, "否 → 明示拒答",
        ["insufficient_evidence = true",
         "列出证据缺口（如漏油：应急预案/上报流程/",
         "围油拦阻/监测取证四类），不编造政策依据",
         "与 R-NX-08/09 托管平台与本地的拒答同一设计"], fc="#fdeaea", ec=RED, fs=7.8, tfs=9.5)
    arrow(ax, (0.44, 0.355), (0.25, 0.262), color=GREEN, lw=1.6, label="充分", lfs=8)
    arrow(ax, (0.56, 0.355), (0.75, 0.262), color=RED, lw=1.6, label="不足", lfs=8)

    ax.text(0.5, 0.018, "设计要点：推理必须落在可检索到的资产版本上——模型可以判断“证据不足”，但不允许在无引用前提下生成政策依据。",
            ha="center", fontsize=7.8, color="#173a66", style="italic")

    fig.tight_layout(pad=0.4)
    fig.savefig(OUT / "fig-m2-dual-drive.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_huawei_fullstack() -> None:
    W, H = 7.8, 4.9
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    box = make_box(W, H)

    _zone(ax, 0.015, 0.16, 0.545, 0.80, "华为云 cn-southwest-2 · VPC environment-seasight-vpc-verify（Skill 必需私网环境）", BLUE)

    box(ax, 0.035, 0.60, 0.50, 0.185, "AgentArts 托管智能体 seasight-governance-agent-vpc2",
        ["managed runtime（R-NX-08 验收智能体）· 绑定 5 Skills",
         "入站：Managed Agents WebSocket 官方协议 + API Key",
         "供应商：deepseek-provider-vpc → https://192.168.0.230:8080/v1"],
        fc="#dbe7f7", ec=BLUE, fs=7.6, tfs=9.8)
    box(ax, 0.035, 0.385, 0.24, 0.155, "ECS ecs-6b91 模型中转",
        ["socat TLS :8080（自签证书）", "relay :18080 模型名重写", "deepseek-v4.1-flash→deepseek-chat", "安全组限 192.168.0.0/16"],
        fc="#fdf3e3", ec=ORANGE, fs=6.9, tfs=8.8)
    box(ax, 0.305, 0.385, 0.23, 0.155, "DeepSeek 官方 API",
        ["真实 Key 仅存中转 ECS", "公网出口由 ECS 承担", "智能体不自持凭据"], fs=7.0, tfs=8.8)
    arrow(ax, (0.275, 0.462), (0.305, 0.462), lw=1.6, label=None)
    arrow(ax, (0.16, 0.60), (0.16, 0.545), lw=1.6)
    ax.text(0.155, 0.568, "VPC 内出站", ha="right", fontsize=7.2, color=BLUE)

    box(ax, 0.035, 0.205, 0.50, 0.155, "平台内 MCP 工具面（R-NX-10，2026-10-25 验证通过）",
        ["新版单智能体绑定 Oceanus Domain Cognition MCP（21 只读工具）",
         "运行时 Pod → 隧道 → ECS MCP → Oceanus /api/v1 全链路",
         "event_list + knowledge_search 共 6 次真实调用全部成功",
         "平台调用链与 ECS 服务端日志逐条对应（07_证据包/R-NX-10）"],
        fc="#e8f4ec", ec=GREEN, fs=7.0, tfs=8.8)
    elbow_arrow(ax, [(0.28, 0.60), (0.28, 0.575)], color=GREEN, lw=1.3)

    _zone(ax, 0.585, 0.16, 0.40, 0.80, "项目侧 · Oceanus（本地部署，另一验收端）", GREEN)

    box(ax, 0.605, 0.66, 0.36, 0.125, "本地 Nexent v2.6.1（官方源码部署）",
        ["R-NX-09：完整 Skill 问答 · 21 工具", "MCP stdio / Streamable HTTP"], fc="#e8f4ec", ec=GREEN, fs=7.4, tfs=9.5)
    box(ax, 0.605, 0.495, 0.36, 0.13, "Oceanus 后端 /api/v1 + MCP 服务",
        ["角色 / 辖区 / 审批 / 幂等 / 审计", "知识域 LLM 通道（KNOWLEDGE_LLM_*）"], fs=7.4, tfs=9.5)
    arrow(ax, (0.785, 0.66), (0.785, 0.627), color=GREEN, lw=1.6)

    box(ax, 0.605, 0.30, 0.36, 0.155, "ModelArts Studio MaaS（昇腾资源池）",
        ["知识域 LLM 通道真实推理评测（R-MA-01）", "GLM-5.3：术语 13/20 反超规则 11/20",
         "问答双景复现：接地双引用 + 漏油拒答", "真实政务文本 34 关系全带类型与引用"],
        fc="#f0ecfa", ec=PURPLE, fs=7.0, tfs=9.2)
    arrow(ax, (0.785, 0.495), (0.785, 0.457), color=PURPLE, lw=1.6, label="OpenAI 兼容端点", lfs=7.2)

    box(ax, 0.605, 0.195, 0.36, 0.085, "全程留证（可复核）",
        ["R-NX-05 / 06 / 07 / 08-PROBE", "→ R-NX-08-COMPLETED"], fs=7.0, tfs=8.4)

    box(ax, 0.015, 0.025, 0.97, 0.10, "验收数字（全部有登记产物，可逐条复核）",
        ["托管平台问答（R-NX-08）：9 分钟 · 1,933 帧 · 2,254 字回答 · 证据不足如实拒答（知识资产未加载时全部 not_evaluated）",
         "本地问答（R-NX-09）：HTTP 200 · 8 步 · 31 次工具调用 · 13 唯一工具 · 2,777 字 ｜  昇腾推理（R-MA-01）：GLM-5.3 真实评测"],
        fc=LIGHT, ec=EDGE, fs=7.2, tfs=8.8)

    fig.tight_layout(pad=0.4)
    fig.savefig(OUT / "fig-huawei-fullstack.png", dpi=200, bbox_inches="tight")
    plt.close(fig)




def fig_retrieval_eval() -> None:
    """R-KN-07 三系统检索对照（hit@1 / hit@5 双面板，2026-10-26 id 更正后冻结快照）."""
    import numpy as np

    cats = ["标题型", "实体型", "本体二跳"]
    systems = ["现有检索(词法+本体图)", "两阶段(BGE-M3+精排)", "RRF混合(v3已上生产)"]
    hit1 = {"baseline": [51.9, 60.0, 80.0], "twostage": [48.1, 37.0, 57.5], "hybrid": [81.5, 51.0, 78.3]}
    hit5 = {"baseline": [85.2, 93.0, 98.3], "twostage": [48.1, 45.0, 72.5], "hybrid": [100.0, 86.0, 98.3]}
    colors = {"baseline": "#9AA6B2", "twostage": "#E8B04B", "hybrid": "#2F6FED"}

    fig, axes = plt.subplots(1, 2, figsize=(8.8, 3.5))
    for ax, data, title in ((axes[0], hit1, "hit@1"), (axes[1], hit5, "hit@5")):
        x = np.arange(len(cats))
        w = 0.26
        for i, sys_key in enumerate(("baseline", "twostage", "hybrid")):
            vals = data[sys_key]
            bars = ax.bar(x + (i - 1) * w, vals, w, label=systems[i],
                          color=colors[sys_key], edgecolor="white", linewidth=0.6)
            for b, v in zip(bars, vals):
                ax.text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:g}",
                        ha="center", va="bottom", fontsize=6.8, color="#333")
        ax.set_xticks(x)
        ax.set_xticklabels(cats, fontsize=8)
        ax.set_title(title, fontsize=9.5, color="#173a66")
        ax.set_ylim(0, 112)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(labelsize=7.5)
        ax.grid(axis="y", linestyle="--", alpha=0.25)
    axes[0].set_ylabel("命中率 (%)", fontsize=8)
    axes[0].legend(fontsize=6.5, loc="upper left", frameon=False)
    fig.suptitle("R-KN-07 检索评测: 306 题 / 27 资产语料, 三系统对照 (id 更正后冻结快照)",
                 fontsize=9.5, color="#173a66", y=0.99)
    fig.text(0.5, -0.05,
             "发现: 无全能配置——BM25 称霸标题型(hit@1 90.1%), 图扩展称霸实体(93.0%)/多跳(98.3%); RRF 混合标题型 hit@1 81.5%(+57% 相对)且多跳不损失; 稠密+精排全题型显著最差 (诚实登记)",
             ha="center", fontsize=6.8, color="#666")
    fig.tight_layout(pad=0.6)
    fig.savefig(OUT / "fig-m2-retrieval-eval.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

if __name__ == "__main__":
    fig_knowledge_pipeline()
    fig_call_graph()
    fig_dual_drive()
    fig_huawei_fullstack()
    fig_retrieval_eval()
    if WARNINGS:
        print("LAYOUT WARNINGS:")
        for w in WARNINGS:
            print("  -", w)
    else:
        print("layout: all boxes fit, no warnings")
    print(f"OK -> {OUT}")
