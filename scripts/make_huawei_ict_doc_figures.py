#!/usr/bin/env python3
"""Generate the architecture / runtime / evolution figures for the optimized
Huawei ICT design document (artifacts/doc-figures/).

Layout guarantees (no text outside boxes, by construction):
- every box measures its inner area in POINTS and lays the title/lines out
  top-down with real font metrics (no magic axis constants);
- lines wider than the box are auto-shrunk (floor 6.5pt) to fit;
- if the vertical content still exceeds the box, fonts shrink proportionally
  and a WARNING is printed so the text must be shortened.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "artifacts" / "doc-figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

BLUE = "#1f5fbf"
LIGHT = "#eef3fb"
EDGE = "#9db6d9"
ORANGE = "#e8871e"
GREEN = "#2e8b57"
PURPLE = "#6d5bb8"
RED = "#c0564f"
GRAY = "#6b7280"

WARNINGS: list[str] = []


def est_width_pt(text: str, fs: float) -> float:
    """Estimated rendered width: CJK/fullwidth chars ≈ 1.0×fs, ASCII ≈ 0.55×fs."""
    return sum(fs if ord(c) > 0x2E80 else fs * 0.55 for c in text)


def make_box(fig_w_in: float, fig_h_in: float):
    """Box renderer bound to one figure's physical size (pt↔axis conversion)."""
    pt2ax_h = 1.0 / (fig_h_in * 72)

    def box(ax, x, y, w, h, title, lines=(), fc=LIGHT, ec=EDGE, fs=9.5, tfs=12,
            hpad_pt=7.0, vpad_pt=5.0, min_fs=6.5):
        ax.add_patch(FancyBboxPatch((x, y), w, h,
                                    boxstyle="round,pad=0.002,rounding_size=0.01",
                                    fc=fc, ec=ec, lw=1.5))
        inner_w = w * fig_w_in * 72 - 2 * hpad_pt
        inner_h = h * fig_h_in * 72 - 2 * vpad_pt

        def fit(text: str, size: float) -> float:
            while size > min_fs and est_width_pt(text, size) > inner_w:
                size -= 0.25
            if est_width_pt(text, size) > inner_w:
                WARNINGS.append(f"box '{title[:14]}…' 行仍超宽: {text[:20]}")
            return size

        t_size = fit(title, tfs)
        l_sizes = [fit(ln, fs) for ln in lines]
        content_h = t_size + (3 + sum(s + 2.5 for s in l_sizes) if lines else 0)
        if content_h > inner_h:
            scale = max(0.62, inner_h / content_h)
            t_size *= scale
            l_sizes = [s * scale for s in l_sizes]
            content_h = t_size + (3 * scale + sum(s + 2.5 * scale for s in l_sizes) if lines else 0)
            if content_h > inner_h:
                WARNINGS.append(f"box '{title[:14]}…' 纵向仍超界（需精简文字）")

        top = y + h - vpad_pt * pt2ax_h
        cur = top - (t_size / 2) * pt2ax_h
        ax.text(x + w / 2, cur, title, ha="center", va="center",
                fontsize=t_size, weight="bold", color="#173a66")
        cur -= (t_size / 2 + 3) * pt2ax_h
        for line, s in zip(lines, l_sizes):
            cur -= (s / 2) * pt2ax_h
            ax.text(x + w / 2, cur, line, ha="center", va="center",
                    fontsize=s, color="#333333")
            cur -= (s / 2 + 2.5) * pt2ax_h

    return box


def arrow(ax, p1, p2, color=BLUE, style="-", lw=1.8, label=None, lfs=9, loff=(0, 0.014)):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=16,
                                 color=color, lw=lw, linestyle=style, shrinkA=2, shrinkB=2))
    if label:
        mx, my = (p1[0] + p2[0]) / 2 + loff[0], (p1[1] + p2[1]) / 2 + loff[1]
        ax.text(mx, my, label, ha="center", va="center", fontsize=lfs, color=color)


def elbow_arrow(ax, points, color=PURPLE, lw=1.6, label=None, lfs=9, label_at=None):
    for i in range(len(points) - 2):
        ax.plot([points[i][0], points[i + 1][0]], [points[i][1], points[i + 1][1]],
                color=color, lw=lw, linestyle=(0, (5, 3)), solid_capstyle="round")
    arrow(ax, points[-2], points[-1], color=color, style=(0, (5, 3)), lw=lw)
    if label and label_at:
        ax.text(label_at[0], label_at[1], label, ha="center", va="center",
                fontsize=lfs, color=color)


def fig_architecture() -> None:
    W, H = 7.2, 5.1
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    box = make_box(W, H)

    box(ax, 0.05, 0.71, 0.90, 0.17, "编排层 · ModelEngine Nexent Agent",
        ["DeepSeek 大模型 · Skill 工作流 ×5 · 规划-推理-停止条件",
         "（政策问答 / 事件研判 / 跨文档决策 / 工单编排 / 轨迹审计）"],
        fc="#dbe7f7", ec=BLUE, fs=9, tfs=12)
    box(ax, 0.05, 0.50, 0.90, 0.14, "MCP 工具面 · Oceanus Domain Cognition MCP",
        ["21 只读工具（资产/本体/检索/决策/业务/审计） + 11 写入（显式开关）",
         "Bearer 鉴权 fail-closed · 业务失败 → 工具错误返回"],
        fc="#fdf3e3", ec=ORANGE, fs=9, tfs=11)
    box(ax, 0.05, 0.25, 0.44, 0.19, "认知层 · Oceanus 知识域",
        ["六类资产版本化（内容哈希）",
         "半自动本体：抽取 → 审核 → 发布",
         "多跳检索（路径/跳数）→ 证据链"],
        fs=8.5, tfs=10.5)
    box(ax, 0.51, 0.25, 0.44, 0.19, "执行层 · Oceanus 业务系统",
        ["角色权限（签名令牌） · 辖区过滤",
         "策略守卫 · 多角色审批 · 幂等",
         "审计回放 · 派单 → 末端可插拔"],
        fs=8.5, tfs=10.5)
    box(ax, 0.05, 0.06, 0.60, 0.12, "数据层",
        ["PostgreSQL+PostGIS · Redis 7 · MinIO"],
        fs=8.5, tfs=10.5)
    box(ax, 0.69, 0.06, 0.26, 0.12, "执行末端",
        ["MQTT 接入 · 可插拔", "打捞机器人 · 机械臂"],
        fc="#e8f4ec", ec=GREEN, fs=8.5, tfs=10.5)

    arrow(ax, (0.27, 0.71), (0.27, 0.645), label="MCP 协议", loff=(-0.068, 0), lfs=8.5)
    arrow(ax, (0.73, 0.71), (0.73, 0.645), label="MCP 协议", loff=(0.068, 0), lfs=8.5)
    arrow(ax, (0.27, 0.50), (0.27, 0.445), label="只读检索 / 证据", loff=(-0.085, 0), lfs=8.5)
    arrow(ax, (0.73, 0.50), (0.73, 0.445), label="写入 / 业务事实", loff=(0.085, 0), lfs=8.5)
    arrow(ax, (0.35, 0.25), (0.35, 0.185))
    arrow(ax, (0.80, 0.25), (0.80, 0.185), color=GREEN, label="MQTT 派单/回执", lfs=8.5,
          loff=(-0.108, 0.012))

    ax.text(0.5, 0.030, "关键分工：Nexent 负责编排与推理，Oceanus 后端负责权限与事实——工具返回后端真实数据。",
            ha="center", fontsize=8.3, color="#173a66", style="italic")
    ax.text(0.5, 0.007, "数据来源：真实公开政务语料（8 份，R-OD-02）· NOAA NCEI 行业监测数据（22,530 条，R-OD-03）· 演示资产（标注“演示”）",
            ha="center", fontsize=7.6, color=GRAY)
    fig.tight_layout(pad=0.4)
    fig.savefig(OUT / "fig-architecture.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_runtime() -> None:
    W, H = 7.2, 4.7
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    box = make_box(W, H)

    steps = [
        ("事件/问题", "研判·规划请求"),
        ("任务规划", "模型规划·失败回退"),
        ("MCP 工具调用", "检索·证据·业务"),
        ("策略守卫", "敏感工具·越权·预算"),
        ("多角色人工审批", "申请→管理员决策"),
        ("执行与审计", "派单闭环·轨迹回放"),
    ]
    w, h, y = 0.148, 0.26, 0.56
    fills = [LIGHT, "#fdf3e3", LIGHT, "#fdeaea", "#e8f4ec", LIGHT]
    edges = [EDGE, ORANGE, EDGE, RED, GREEN, EDGE]
    for i, (title, sub) in enumerate(steps):
        x = 0.025 + i * (w + 0.012)
        box(ax, x, y, w, h, title, (sub,), fc=fills[i], ec=edges[i], fs=8, tfs=9.5)
        if i < len(steps) - 1:
            arrow(ax, (x + w, y + h / 2), (x + w + 0.012, y + h / 2), lw=2.0)

    gx = 0.025 + 3 * (w + 0.012) + w / 2
    px = 0.025 + (w + 0.012) + w / 2
    elbow_arrow(ax, [(gx, y + h), (gx, 0.92), (px, 0.92), (px, y + h + 0.005)],
                color=RED, label="拦截 / 退回（0 次执行）", label_at=(0.5, 0.945), lfs=8.5)

    evo = [
        (0.10, 0.22, "经验库（经验进化）",
         ["终态复盘提炼结构化经验", "同类事件规划期自动引用", "贝叶斯置信度封顶 0.95"]),
        (0.395, 0.22, "本体版本链（知识进化）",
         ["新版本 → 抽取 → 审核 → 发布", "增量较全量重抽省 63.19%"]),
        (0.69, 0.22, "策略版本化（策略进化）",
         ["证据链固化策略版本", "按当时口径回放"]),
    ]
    for x, bw, title, lines in evo:
        box(ax, x, 0.06, bw, 0.20, title, tuple(lines), fc="#f0ecfa", ec=PURPLE, fs=8, tfs=9.5)

    arrow(ax, (0.21, 0.26), (0.21, y - 0.005), color=PURPLE, style=(0, (5, 3)),
          label="同类事件引用", lfs=8.2, loff=(-0.075, 0.06))
    arrow(ax, (0.505, 0.26), (0.505, y - 0.005), color=PURPLE, style=(0, (5, 3)),
          label="新版本发布", lfs=8.2, loff=(0.075, 0.06))
    arrow(ax, (0.80, 0.26), (gx + w / 2 + 0.02, y - 0.005), color=PURPLE, style=(0, (5, 3)),
          label="策略演进", lfs=8.2, loff=(0.09, 0.10))

    ex = 0.025 + 5 * (w + 0.012) + w / 2
    elbow_arrow(ax, [(ex, y), (ex, 0.385), (0.325, 0.385), (0.24, 0.26)],
                color=PURPLE, label="终态复盘", label_at=(0.63, 0.41), lfs=8.2)

    ax.text(0.5, 0.012, "紫色虚线 = 三条进化回路：经验进化 · 知识进化 · 策略进化（对应赛题“可进化决策智能体”）",
            ha="center", fontsize=8.5, color=PURPLE, style="italic")
    fig.tight_layout(pad=0.4)
    fig.savefig(OUT / "fig-runtime-evolution.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig_architecture()
    fig_runtime()
    if WARNINGS:
        print("LAYOUT WARNINGS:")
        for w in WARNINGS:
            print("  -", w)
    else:
        print("layout: all boxes fit, no warnings")
    print(f"OK -> {OUT}")
