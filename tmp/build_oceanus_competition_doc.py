# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import math
import os
import re
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path(r"C:\Users\Liii\Desktop\seahawk")
OUT = ROOT / "output" / "pdf"
BUILD = ROOT / "tmp" / "oceanus-competition-build"
DEVICE_SOURCE = ROOT / "tmp" / "plan_review_20261020" / "device_images"
ASSETS = Path(
    r"C:\Users\Liii\Desktop\2026年海峡大学生人工智能创意大赛\提交材料\assets"
)
UI = ROOT / "artifacts" / "ui-responsive"
CONSOLE = ROOT / "artifacts" / "agent-console"
ARM = ROOT / "artifacts" / "arm-console"
DETECT = Path(
    r"C:\Users\Liii\Desktop\2026年海峡大学生人工智能创意大赛"
    r"\计算与信息科学学院（智能科学与技术）-探海灵眸-李涌翔-校级选拔材料"
    r"\辅助材料\04_检测效果图"
)

DOCX_PATH = OUT / "探海灵眸Oceanus_系统设计报告_参赛优化版.docx"
PDF_PATH = OUT / "探海灵眸Oceanus_系统设计报告_参赛优化版.pdf"

NAVY = "103B4A"
TEAL = "0C7C86"
TEAL_DARK = "075D66"
CYAN = "E8F5F5"
PALE = "F5F8F9"
PALE_BLUE = "EAF3F7"
PALE_ORANGE = "FFF4E7"
PALE_RED = "FBEDEF"
ORANGE = "D87A16"
RED = "C34B54"
GREEN = "1D7B63"
INK = "18313B"
MID = "5B7079"
LIGHT = "D8E3E7"
WHITE = "FFFFFF"
CONTENT_WIDTH_CM = 16.6

FONT_CN = "Microsoft YaHei"
FONT_EN = "Aptos"


def ensure_dirs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)


def px(value: float) -> int:
    return int(round(value))


def to_grayscale(path: Path) -> Path:
    target = BUILD / f"{path.stem}_grayscale.png"
    with Image.open(path) as source:
        image = ImageOps.grayscale(source.convert("RGB"))
        image = ImageEnhance.Contrast(image).enhance(1.03)
        image.save(target, optimize=True)
    return target


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path(r"C:\Windows\Fonts\msyhbd.ttc") if bold else Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def make_cover_image() -> Path:
    source = DETECT / "03_水面多目标检测.jpg"
    target = BUILD / "cover_detection.jpg"
    im = Image.open(source).convert("RGB")
    w, h = im.size
    target_ratio = 16 / 8.2
    if w / h > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        im = im.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = int((h - new_h) * 0.34)
        im = im.crop((0, top, w, top + new_h))
    im = im.resize((1800, round(1800 / target_ratio)), Image.Resampling.LANCZOS)
    im.save(target, quality=93, optimize=True)
    return target


def make_innovation_image() -> Path:
    path = BUILD / "innovation_engine.png"
    W, H = 1800, 920
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    title_font = load_font(42, True)
    h_font = load_font(28, True)
    body_font = load_font(22)
    small_font = load_font(19)

    def rounded(box, fill, outline, radius=26, width=3):
        d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

    def text_center(xy, text, font, fill):
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text((xy[0] - tw / 2, xy[1] - th / 2), text, font=font, fill=fill)

    d.text((70, 54), "一个治理内核，四条能力链闭环", font=title_font, fill="#103B4A")
    d.text(
        (70, 112),
        "把识别、决策、执行与核算放进同一条可审计证据链",
        font=body_font,
        fill="#5B7079",
    )

    center = (900, 485)
    d.ellipse((710, 295, 1090, 675), fill="#0C7C86", outline="#075D66", width=5)
    text_center((900, 445), "治理智能体", h_font, "white")
    text_center((900, 490), "Oceanus Core", small_font, "#DDF5F4")
    text_center((900, 535), "Run · Policy · Tool", body_font, "white")
    text_center((900, 572), "Approval · Replay · Eval", body_font, "white")

    cards = [
        ((70, 265, 630, 450), "01  感知证据化", "检测结果带帧、时序、坐标与置信度", "#EAF3F7", "#0C7C86"),
        ((1170, 265, 1730, 450), "02  决策可审计", "每个 Run/Step/工具输入输出全程留痕", "#F2EDFC", "#6D45B8"),
        ((70, 535, 630, 720), "03  执行受控", "写操作策略守卫，高风险强制人工审批", "#FFF4E7", "#D87A16"),
        ((1170, 535, 1730, 720), "04  结果可核算", "前后影像、重量、复核与报表可回查", "#EAF7F1", "#1D7B63"),
    ]
    for box, heading, body, fill, outline in cards:
        rounded(box, fill, outline)
        d.text((box[0] + 26, box[1] + 25), heading, font=h_font, fill=outline)
        d.text((box[0] + 26, box[1] + 82), body, font=body_font, fill="#304A54")

    for start, end in [
        ((630, 355), (710, 405)),
        ((1170, 355), (1090, 405)),
        ((630, 625), (710, 575)),
        ((1170, 625), (1090, 575)),
    ]:
        d.line((start, end), fill="#78949E", width=5)

    d.rounded_rectangle((420, 790, 1380, 860), radius=18, fill="#F5F8F9", outline="#D8E3E7", width=2)
    text_center(
        (900, 825),
        "模型可以替换，执行器可以更换；治理契约与证据链保持稳定。",
        body_font,
        "#304A54",
    )
    im.save(path)
    return path


def make_state_machine_image() -> Path:
    path = BUILD / "state_machine_v2.png"
    W, H = 1800, 860
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    font_title = load_font(40, True)
    font_h = load_font(25, True)
    font_s = load_font(21)
    font_l = load_font(20)

    d.text((72, 48), "治理智能体 Run 状态机", font=font_title, fill="#103B4A")
    d.text(
        (72, 102),
        "正常路径、人工审批、重规划与安全终止统一进入可回放轨迹",
        font=font_s,
        fill="#5B7079",
    )

    def box(cx, cy, text, fill, outline, width=300, height=78):
        d.rounded_rectangle(
            (cx - width // 2, cy - height // 2, cx + width // 2, cy + height // 2),
            radius=16,
            fill=fill,
            outline=outline,
            width=3,
        )
        bbox = d.textbbox((0, 0), text, font=font_h)
        d.text(
            (cx - (bbox[2] - bbox[0]) / 2, cy - (bbox[3] - bbox[1]) / 2 - 2),
            text,
            font=font_h,
            fill=outline,
        )

    def arrow(points, color="#78949E", width=4, label=None, label_pos=None):
        d.line(points, fill=color, width=width, joint="curve")
        x1, y1 = points[-2]
        x2, y2 = points[-1]
        ang = math.atan2(y2 - y1, x2 - x1)
        size = 12
        p1 = (x2 - size * math.cos(ang - 0.55), y2 - size * math.sin(ang - 0.55))
        p2 = (x2 - size * math.cos(ang + 0.55), y2 - size * math.sin(ang + 0.55))
        d.polygon([(x2, y2), p1, p2], fill=color)
        if label and label_pos:
            bbox = d.textbbox((0, 0), label, font=font_s)
            d.rectangle(
                (
                    label_pos[0] - 6,
                    label_pos[1] - 3,
                    label_pos[0] + bbox[2] + 6,
                    label_pos[1] + bbox[3] + 4,
                ),
                fill="white",
            )
            d.text(label_pos, label, font=font_s, fill=color)

    # Main path
    coords = [
        (150, 300),
        (425, 300),
        (700, 300),
        (975, 300),
        (1250, 300),
        (1525, 300),
    ]
    labels = ["created", "planning", "policy", "executing", "observing", "verifying"]
    fills = ["#F2F5F6", "#EAF3F7", "#FFF4E7", "#F2EDFC", "#F2EDFC", "#F2EDFC"]
    outlines = ["#5B7079", "#0C7C86", "#D87A16", "#6D45B8", "#6D45B8", "#6D45B8"]
    for (cx, cy), label, fill, outline in zip(coords, labels, fills, outlines):
        box(cx, cy, label, fill, outline, width=210, height=70)
    for i in range(len(coords) - 1):
        arrow(
            [
                (coords[i][0] + 108, coords[i][1]),
                (coords[i + 1][0] - 108, coords[i + 1][1]),
            ]
        )

    # Success and approval branch
    box(1600, 430, "succeeded", "#EAF7F1", "#1D7B63", width=210, height=70)
    arrow([(1540, 335), (1578, 385)], color="#1D7B63")
    box(975, 475, "waiting_approval", "#FFF4E7", "#D87A16", width=250, height=70)
    arrow([(760, 335), (890, 440)], color="#D87A16", label="write", label_pos=(788, 365))
    arrow([(975, 440), (1130, 330)], color="#D87A16", label="approved", label_pos=(1035, 373))

    # Replan loop
    box(1250, 625, "replan / verify", "#F5F8F9", "#5B7079", width=250, height=70)
    arrow([(1250, 335), (1250, 590)], color="#78949E", label="not yet done", label_pos=(1262, 485))
    arrow([(1125, 625), (425, 625), (425, 335)], color="#D87A16", label="new step, old trace kept", label_pos=(705, 595))

    # Terminal failure
    box(975, 750, "failed / cancelled / expired", "#FBEDEF", "#C34B54", width=430, height=78)
    d.line((150, 690, 1525, 690), fill="#E5B7BB", width=3)
    d.line((150, 676, 150, 690), fill="#C34B54", width=3)
    d.line((1525, 676, 1525, 690), fill="#C34B54", width=3)
    d.text(
        (180, 697),
        "任一状态发生超时、拒绝、冲突、取消或策略终止",
        font=font_s,
        fill="#8D3B43",
    )
    arrow([(975, 690), (975, 708)], color="#C34B54", width=4)
    d.text(
        (72, 795),
        "结构化终止原因：no_robot_available · tool_timeout · policy_denied · approval_rejected · task_conflict · max_steps_exceeded",
        font=font_l,
        fill="#5B7079",
    )
    im.save(path)
    return path


def make_evidence_strip() -> Path:
    path = BUILD / "evidence_strip.png"
    W, H = 1800, 340
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    h = load_font(24, True)
    b = load_font(19)
    metrics = [
        ("27 / 27", "固定评测场景断言通过", "#0C7C86"),
        ("129 / 129", "真实 HTTP + DB 集成验收", "#1D7B63"),
        ("98.9%", "工具选择正确率（88 / 89）", "#6D45B8"),
        ("100%", "轨迹回放与审批交接", "#D87A16"),
    ]
    card_w = 405
    gap = 20
    x = 30
    for value, label, color in metrics:
        d.rounded_rectangle((x, 40, x + card_w, 280), radius=20, fill="#F7FAFA", outline="#D8E3E7", width=2)
        d.rectangle((x, 40, x + 8, 280), fill=color)
        d.text((x + 28, 78), value, font=load_font(46, True), fill=color)
        d.text((x + 28, 153), label, font=h, fill="#18313B")
        d.text((x + 28, 203), "证据口径见第 19-20 页", font=b, fill="#5B7079")
        x += card_w + gap
    im.save(path)
    return path


def make_robot_boundary_image() -> Path:
    path = BUILD / "robot_boundary.png"
    W, H = 1800, 700
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    title = load_font(40, True)
    h = load_font(25, True)
    b = load_font(20)
    s = load_font(17)
    d.text((64, 42), "机械臂执行端：已打通链路，尚未宣称自动抓取成功", font=title, fill="#103B4A")
    d.text(
        (64, 98),
        "把“动作链路”“识别准确”“抓放成功”拆开报告，避免把联调信号误写成现场能力",
        font=b,
        fill="#5B7079",
    )

    def panel(x, y, w, hh, head, status, color, fill, items):
        d.rounded_rectangle((x, y, x + w, y + hh), radius=20, fill=fill, outline=color, width=3)
        d.text((x + 26, y + 24), head, font=h, fill=color)
        d.rounded_rectangle((x + w - 158, y + 20, x + w - 20, y + 58), radius=14, fill=color)
        bbox = d.textbbox((0, 0), status, font=s)
        d.text(
            (x + w - 89 - (bbox[2] - bbox[0]) / 2, y + 27),
            status,
            font=s,
            fill="white",
        )
        yy = y + 88
        for item in items:
            d.ellipse((x + 28, yy + 7, x + 40, yy + 19), fill=color)
            d.text((x + 54, yy), item, font=b, fill="#304A54")
            yy += 48

    panel(
        64,
        165,
        790,
        440,
        "已验证：控制与执行链路",
        "E2 受控联调",
        "#1D7B63",
        "#EAF7F1",
        [
            "ROS + 6 路总线舵机回读、IK 解算、TCP 自检通过",
            "笔记本到板端真实运动控制可用",
            "开机姿态 systemd 服务与 7 标签页控制台可用",
            "9 点标定工具就绪；机械臂代码测试 91 项通过",
        ],
    )
    panel(
        946,
        165,
        790,
        440,
        "仍需补齐：视觉抓取闭环",
        "未宣称成功",
        "#C34B54",
        "#FBEDEF",
        [
            "室内白袋与浅色地面可分性不足，12/12 帧误锁夹爪",
            "固定位置慢速动作序列已走完，但夹爪空手",
            "当前标定是单点平移近似，需重做仿射拟合",
            "板端疑似欠压重启，需更换 5V/3A 以上电源",
        ],
    )
    im.save(path)
    return path


def make_roadmap_image() -> Path:
    path = BUILD / "roadmap_v2.png"
    W, H = 1800, 560
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    title = load_font(40, True)
    h = load_font(24, True)
    b = load_font(18)
    d.text((64, 38), "价值落地路径：先证明闭环，再复制，再联网", font=title, fill="#103B4A")
    d.text((64, 92), "每个阶段都设置可验收的退出条件，避免“演示结束即项目结束”", font=b, fill="#5B7079")
    stages = [
        ("0-3 个月", "单点闭环", "1 个养殖区 / 2-3 个点位\n补足现场标定与抓取验证", "#0C7C86", "#EAF3F7"),
        ("3-6 个月", "县域复制", "多设备派单 / 证据报表\n形成可复制的运营手册", "#1D7B63", "#EAF7F1"),
        ("6-12 个月", "区域协同", "跨点位联动 / 国产算力迁移\n建立统一考核口径", "#D87A16", "#FFF4E7"),
        ("12 个月+", "标准输出", "开放接口 / 设备生态\n沉淀近岸治理数据规范", "#6D45B8", "#F2EDFC"),
    ]
    x0 = 45
    card_w = 410
    gap = 23
    for idx, (period, title_s, body_s, color, fill) in enumerate(stages):
        x = x0 + idx * (card_w + gap)
        d.rounded_rectangle((x, 165, x + card_w, 455), radius=22, fill=fill, outline=color, width=3)
        d.rectangle((x, 165, x + card_w, 218), fill=color)
        d.text((x + 24, 174), period, font=h, fill="white")
        d.text((x + 24, 248), title_s, font=h, fill=color)
        d.multiline_text((x + 24, 305), body_s, font=b, fill="#304A54", spacing=10)
        if idx < len(stages) - 1:
            d.line((x + card_w + 2, 310, x + card_w + gap - 2, 310), fill="#78949E", width=4)
            d.polygon(
                [
                    (x + card_w + gap - 4, 310),
                    (x + card_w + gap - 18, 302),
                    (x + card_w + gap - 18, 318),
                ],
                fill="#78949E",
            )
    im.save(path)
    return path


def make_er_diagram_image() -> Path:
    path = BUILD / "er_diagram_clean.png"
    W, H = 1800, 1120
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    head_font = load_font(28, True)
    field_font = load_font(22)
    strong_font = load_font(22, True)
    edge_font = load_font(19, True)

    def entity(x, y, w, h, title, color, fields):
        d.rounded_rectangle((x, y, x + w, y + h), radius=18, fill="#FFFFFF", outline=color, width=3)
        d.rounded_rectangle((x, y, x + w, y + 62), radius=18, fill=color, outline=color, width=3)
        d.rectangle((x, y + 44, x + w, y + 62), fill=color)
        bbox = d.textbbox((0, 0), title, font=head_font)
        d.text((x + (w - (bbox[2] - bbox[0])) / 2, y + 13), title, font=head_font, fill="white")
        yy = y + 80
        for field, strong in fields:
            d.text((x + 24, yy), field, font=strong_font if strong else field_font, fill="#18313B")
            yy += 29

    def arrow(x1, y1, x2, y2, label):
        d.line((x1, y1, x2, y2), fill="#78949E", width=4)
        d.polygon(((x2, y2), (x2 - 15, y2 - 9), (x2 - 15, y2 + 9)), fill="#78949E")
        mid = ((x1 + x2) // 2, (y1 + y2) // 2)
        bbox = d.textbbox((0, 0), label, font=edge_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        d.rounded_rectangle(
            (mid[0] - tw / 2 - 10, mid[1] - th / 2 - 6, mid[0] + tw / 2 + 10, mid[1] + th / 2 + 8),
            radius=8,
            fill="white",
            outline="#D8E3E7",
            width=2,
        )
        d.text((mid[0] - tw / 2, mid[1] - th / 2 - 1), label, font=edge_font, fill="#5B7079")

    entity(
        40, 40, 500, 430, "t_event", "#0C7C86",
        [
            ("id BIGSERIAL PK", True),
            ("event_id TEXT UNIQUE", False),
            ("device_id TEXT", False),
            ("seq BIGINT", False),
            ("category TEXT", False),
            ("confidence FLOAT", False),
            ("bbox JSONB", False),
            ("location GEOMETRY", False),
            ("captured_at TIMESTAMPTZ", False),
            ("UNIQUE(device_id, seq)", True),
        ],
    )
    entity(
        650, 40, 500, 360, "t_task", "#1D7B63",
        [
            ("task_id TEXT UNIQUE", True),
            ("event_id TEXT FK", False),
            ("assignee_id TEXT", False),
            ("priority INT", False),
            ("status TEXT", False),
            ("target_point GEOMETRY", False),
            ("dispatch_score FLOAT", False),
            ("reject_reason TEXT", False),
        ],
    )
    entity(
        1260, 40, 500, 300, "t_evidence", "#D87A16",
        [
            ("id BIGSERIAL PK", True),
            ("task_id TEXT FK", False),
            ("kind TEXT", False),
            ("object_key TEXT", False),
            ("weight_kg FLOAT", False),
            ("reviewed_by TEXT", False),
        ],
    )
    entity(
        40, 650, 500, 320, "t_agent_run", "#6D45B8",
        [
            ("run_id TEXT PK", True),
            ("trigger_type TEXT", False),
            ("objective TEXT", False),
            ("status TEXT", False),
            ("policy_version TEXT", False),
            ("termination_reason TEXT", False),
            ("trace_id TEXT", False),
        ],
    )
    entity(
        650, 640, 500, 390, "t_agent_step", "#6D45B8",
        [
            ("step_id TEXT PK", True),
            ("run_id TEXT FK", False),
            ("step_no INT", False),
            ("step_type TEXT", False),
            ("tool_name TEXT", False),
            ("input_hash TEXT", False),
            ("output_hash TEXT", False),
            ("status TEXT", False),
            ("UNIQUE(run_id, step_no)", True),
        ],
    )
    entity(
        1260, 650, 500, 320, "t_agent_approval", "#C34B54",
        [
            ("approval_id TEXT PK", True),
            ("run_id TEXT FK", False),
            ("requested_action TEXT", False),
            ("risk_level TEXT", False),
            ("decision TEXT", False),
            ("decided_by TEXT", False),
            ("decided_at TIMESTAMPTZ", False),
        ],
    )

    arrow(540, 245, 650, 245, "1 : N")
    arrow(1150, 245, 1260, 245, "1 : N")
    arrow(540, 805, 650, 805, "1 : N")
    arrow(1150, 805, 1260, 805, "1 : N")
    im.save(path)
    return path


def make_ascend_path_image() -> Path:
    path = BUILD / "ascend_path_clean.png"
    W, H = 1800, 720
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    heading_font = load_font(30, True)
    card_font = load_font(25, True)
    body_font = load_font(21)
    note_font = load_font(21)

    def card(x, y, w, h, title, body, color, fill, dashed=False):
        d.rounded_rectangle((x, y, x + w, y + h), radius=16, fill=fill, outline=color, width=3)
        if dashed:
            for xx in range(x + 18, x + w - 10, 28):
                d.line((xx, y, min(xx + 14, x + w), y), fill=fill, width=5)
                d.line((xx, y + h, min(xx + 14, x + w), y + h), fill=fill, width=5)
        bbox = d.textbbox((0, 0), title, font=card_font)
        d.text((x + (w - (bbox[2] - bbox[0])) / 2, y + 18), title, font=card_font, fill=color)
        bbox = d.textbbox((0, 0), body, font=body_font)
        d.text((x + (w - (bbox[2] - bbox[0])) / 2, y + 62), body, font=body_font, fill="#304A54")

    d.text((64, 42), "已实测 E2 / 软件集成", font=heading_font, fill="#0C7C86")
    d.text((1126, 42), "方案级 / 未做硬件实测", font=heading_font, fill="#D87A16")
    d.rounded_rectangle((54, 98, 1050, 454), radius=22, fill="#F7FBFA", outline="#BFDAD8", width=2)
    d.rounded_rectangle((1098, 98, 1746, 454), radius=22, fill="#FFFBF5", outline="#F0C88E", width=2)

    card(88, 152, 450, 112, "ONNX 导出", "batch=1 / opset=17 / 图简化", "#0C7C86", "#EAF3F7")
    card(566, 152, 450, 112, "provider 探测", "TensorRT / CUDA / CPU", "#0C7C86", "#EAF3F7")
    card(88, 296, 450, 112, "HTTP 推理服务", "/infer/detect / /infer/health", "#1D7B63", "#EAF7F1")
    card(566, 296, 450, 112, "云平台智能体", "ModelArts / AgentArts", "#1D7B63", "#EAF7F1")

    card(1128, 150, 188, 142, "ATC 转换", "ONNX -> OM", "#D87A16", "#FFF4E7", dashed=True)
    card(1330, 150, 188, 142, "CANN 执行", "ExecutionProvider", "#D87A16", "#FFF4E7", dashed=True)
    card(1532, 150, 188, 142, "版本管理", "算子 / 模型一致", "#D87A16", "#FFF4E7", dashed=True)
    d.text((1128, 326), "目标：不改业务协议，仅替换推理后端", font=note_font, fill="#5B7079")
    d.text((88, 528), "边界口径：右侧为迁移方案，不等同于已完成昇腾硬件实测。", font=note_font, fill="#5B7079")
    im.save(path)
    return path


def make_detection_pair_image() -> Path:
    path = BUILD / "detection_pair.png"
    left = Image.open(DETECT / "03_水面多目标检测.jpg").convert("RGB")
    right = Image.open(DETECT / "05_岸滩泡沫塑料检测.jpg").convert("RGB")
    W, H = 1800, 780
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    label_font = load_font(27, True)
    d.text((48, 26), "水面多目标检测", font=label_font, fill="#103B4A")
    d.text((934, 26), "岸滩泡沫塑料检测", font=label_font, fill="#103B4A")
    left_fit = ImageOps.fit(left, (840, 660), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    right_fit = ImageOps.fit(right, (840, 660), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
    im.paste(left_fit, (48, 80))
    im.paste(right_fit, (912, 80))
    d.rectangle((48, 80, 888, 740), outline="#D8E3E7", width=3)
    d.rectangle((912, 80, 1752, 740), outline="#D8E3E7", width=3)
    im.save(path)
    return path


def make_temporal_funnel_image() -> Path:
    path = BUILD / "temporal_funnel_v2.png"
    W, H = 1500, 760
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    font_title = load_font(40, True)
    font_sub = load_font(25)
    font_header = load_font(22, True)
    font_label = load_font(30, True)
    font_count = load_font(30, True)
    font_metric = load_font(26)
    font_note = load_font(21)
    font_badge = load_font(26, True)
    font_step = load_font(18, True)

    def text_left(x, center_y, text, font, fill):
        box = d.textbbox((0, 0), text, font=font)
        h = box[3] - box[1]
        d.text((x, center_y - h / 2 - box[1]), text, font=font, fill=fill)

    def text_right(x, center_y, text, font, fill):
        box = d.textbbox((0, 0), text, font=font)
        w = box[2] - box[0]
        h = box[3] - box[1]
        d.text((x - w, center_y - h / 2 - box[1]), text, font=font, fill=fill)

    d.text((60, 26), "时序先验误报抑制链路", font=font_title, fill="#103B4A")
    d.text(
        (60, 84),
        "合成海面测试数据 · 原始检测 1000 → 可信事件 240",
        font=font_sub,
        fill="#5B7079",
    )
    d.rounded_rectangle((1175, 34, 1440, 86), radius=26, fill="#0C7C86")
    text_right(1410, 60, "链路过滤率 76%", font_badge, "white")
    d.line((60, 124, 1440, 124), fill="#D8E3E7", width=2)

    text_left(110, 152, "处理环节", font_header, "#5B7079")
    text_left(350, 152, "候选规模", font_header, "#5B7079")
    text_right(1095, 152, "检测数", font_header, "#5B7079")
    text_left(1185, 152, "相对上一环节", font_header, "#5B7079")

    stages = [
        ("原始多帧检测", 1000, "基线 1000", "#C34B54", "#FBEDEF"),
        ("抽帧后候选", 400, "减少 600 · 60%", "#D87A16", "#FFF4E7"),
        ("目标跟踪关联", 320, "减少 80 · 20%", "#D87A16", "#FFF4E7"),
        ("连续命中 ≥N 帧", 260, "减少 60 · 19%", "#0C7C86", "#E8F5F5"),
        ("冷却窗口过滤", 240, "减少 20 · 8%", "#0C7C86", "#E8F5F5"),
        ("可信事件", 240, "保留 240 · 24%", "#1D7B63", "#EAF7F1"),
    ]
    bar_left = 350
    bar_max = 700
    row_y = [204, 297, 390, 483, 576, 669]
    bar_h = 52
    for index, ((label, count, change, accent, fill), cy) in enumerate(
        zip(stages, row_y), start=1
    ):
        d.ellipse((70, cy - 17, 104, cy + 17), fill=accent)
        step = str(index).zfill(2)
        sb = d.textbbox((0, 0), step, font=font_step)
        sw, sh = sb[2] - sb[0], sb[3] - sb[1]
        d.text(
            (87 - sw / 2, cy - sh / 2 - sb[1]),
            step,
            font=font_step,
            fill="white",
        )
        text_left(110, cy, label, font_label, "#18313B")

        bar_w = max(124, round(bar_max * count / 1000))
        d.rounded_rectangle(
            (bar_left, cy - bar_h // 2, bar_left + bar_w, cy + bar_h // 2),
            radius=12,
            fill=fill,
            outline=accent,
            width=3,
        )
        text_right(1095, cy, str(count), font_count, accent)
        text_left(1185, cy, change, font_metric, "#304A54")

    d.line((60, 703, 1440, 703), fill="#E6ECEF", width=2)
    d.text(
        (60, 724),
        "口径：相对上一环节计算；76% 为链路过滤率，不代表识别精度或召回率。",
        font=font_note,
        fill="#5B7079",
    )
    im.save(path)
    return path


def make_assets() -> dict[str, Path]:
    return {
        "innovation": make_innovation_image(),
        "state": make_state_machine_image(),
        "evidence": make_evidence_strip(),
        "robot": make_robot_boundary_image(),
        "roadmap": make_roadmap_image(),
        "er": make_er_diagram_image(),
        "ascend": make_ascend_path_image(),
        "detection_pair": make_detection_pair_image(),
        "temporal": make_temporal_funnel_image(),
    }


def grayscale_hex(fill: str) -> str:
    value = fill.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(channel * 2 for channel in value)
    if len(value) != 6:
        return WHITE
    try:
        red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return WHITE
    gray = round(0.299 * red + 0.587 * green + 0.114 * blue)
    return f"{gray:02X}{gray:02X}{gray:02X}"


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill.lstrip("#").upper())


def set_cell_border(
    cell,
    *,
    top: str | None = None,
    bottom: str | None = None,
    left: str | None = None,
    right: str | None = None,
    size: int = 6,
) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_borders = tc_pr.first_child_found_in("w:tcBorders")
    if tc_borders is None:
        tc_borders = OxmlElement("w:tcBorders")
        tc_pr.append(tc_borders)
    for edge, color in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        if not color:
            continue
        tag = "w:" + edge
        element = tc_borders.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            tc_borders.append(element)
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), str(size))
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), color)


def set_cell_margins(cell, top=90, bottom=90, left=120, right=120) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for name, value in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
        tag = "w:" + name
        element = tc_mar.find(qn(tag))
        if element is None:
            element = OxmlElement(tag)
            tc_mar.append(element)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")


def set_repeat_table_header(row) -> None:
    tr = row._tr
    tr_pr = tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_row_height(row, cm: float) -> None:
    tr = row._tr
    tr_pr = tr.get_or_add_trPr()
    tr_height = OxmlElement("w:trHeight")
    tr_height.set(qn("w:val"), str(int(cm * 567)))
    tr_height.set(qn("w:hRule"), "atLeast")
    tr_pr.append(tr_height)


def set_table_width(table, width_cm: float) -> None:
    width_cm = min(width_cm, CONTENT_WIDTH_CM)
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    tbl_w = tbl_pr.first_child_found_in("w:tblW")
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(int(width_cm * 567)))
    tbl_w.set(qn("w:type"), "dxa")


def set_row_cant_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    tr_pr.append(cant_split)


def set_table_fixed_layout(table) -> None:
    tbl_pr = table._tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)


def set_col_widths(table, widths_cm: list[float]) -> None:
    total = sum(widths_cm)
    scale = min(1.0, CONTENT_WIDTH_CM / total) if total else 1.0
    scaled_widths = [width * scale for width in widths_cm]
    for row in table.rows:
        for cell, width in zip(row.cells, scaled_widths):
            cell.width = Cm(width)
    for col, width in zip(table.columns, scaled_widths):
        col.width = Cm(width)


def remove_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = OxmlElement("w:" + edge)
        tag.set(qn("w:val"), "nil")
        borders.append(tag)
    tbl_pr.append(borders)


def add_paragraph_border(paragraph, position="bottom", color=LIGHT, size=6) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    edge = OxmlElement("w:" + position)
    edge.set(qn("w:val"), "single")
    edge.set(qn("w:sz"), str(size))
    edge.set(qn("w:space"), "4")
    edge.set(qn("w:color"), color)
    p_bdr.append(edge)


def add_page_number(paragraph, *, set_alignment: bool = True) -> None:
    if set_alignment:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("第 ")
    run.font.name = FONT_CN
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor.from_string(MID)
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = " PAGE "
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char1)
    run._r.append(instr_text)
    run._r.append(fld_char2)
    run2 = paragraph.add_run(" 页")
    run2.font.name = FONT_CN
    run2.font.size = Pt(8.5)
    run2.font.color.rgb = RGBColor.from_string(MID)


def set_page_number_start(section, start: int) -> None:
    sect_pr = section._sectPr
    pg_num_type = sect_pr.find(qn("w:pgNumType"))
    if pg_num_type is None:
        pg_num_type = OxmlElement("w:pgNumType")
        sect_pr.append(pg_num_type)
    pg_num_type.set(qn("w:start"), str(start))


def set_keep_with_next(paragraph, keep_together: bool = True) -> None:
    p = paragraph.paragraph_format
    p.keep_with_next = True
    p.keep_together = keep_together


def set_cell_text(
    cell,
    text: str,
    *,
    size=10,
    bold=False,
    color=INK,
    align=WD_ALIGN_PARAGRAPH.LEFT,
    font=FONT_CN,
    line=1.15,
) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = line
    run = p.add_run(text)
    run.bold = bold
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def add_rich_cell(
    cell,
    parts: list[tuple[str, dict]],
    *,
    align=WD_ALIGN_PARAGRAPH.LEFT,
) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.1
    for text, opts in parts:
        run = p.add_run(text)
        run.font.name = opts.get("font", FONT_CN)
        run._element.rPr.rFonts.set(qn("w:eastAsia"), opts.get("font", FONT_CN))
        run.font.size = Pt(opts.get("size", 10))
        run.bold = opts.get("bold", False)
        run.italic = opts.get("italic", False)
        run.font.color.rgb = RGBColor.from_string(opts.get("color", INK))


def style_document(doc: Document) -> None:
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = FONT_CN
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(6)

    title = styles["Title"]
    title.font.name = FONT_CN
    title._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    title.font.size = Pt(26)
    title.font.bold = True
    title.font.color.rgb = RGBColor.from_string(NAVY)
    title_p_pr = title._element.find(qn("w:pPr"))
    if title_p_pr is not None:
        for border in list(title_p_pr.findall(qn("w:pBdr"))):
            title_p_pr.remove(border)

    for name in ["Heading 1", "Heading 2", "Heading 3"]:
        style = styles[name]
        style.font.name = FONT_CN
        style._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
        style.font.color.rgb = RGBColor.from_string(NAVY)
        style.font.bold = True
        style.paragraph_format.keep_with_next = True
    styles["Heading 1"].font.size = Pt(20)
    styles["Heading 2"].font.size = Pt(14)
    styles["Heading 3"].font.size = Pt(11.5)


def configure_sections(doc: Document) -> None:
    cover = doc.sections[0]
    cover.page_width = Cm(21)
    cover.page_height = Cm(29.7)
    cover.top_margin = Cm(2.2)
    cover.bottom_margin = Cm(1.4)
    cover.left_margin = Cm(0)
    cover.right_margin = Cm(0)
    cover.header_distance = Cm(0.5)
    cover.footer_distance = Cm(0.7)
    cover.different_first_page_header_footer = False
    cover.header.is_linked_to_previous = False
    cover.footer.is_linked_to_previous = False
    for paragraph in list(cover.header.paragraphs):
        paragraph.text = ""
    for paragraph in list(cover.footer.paragraphs):
        paragraph.text = ""

    body = doc.add_section(WD_SECTION.NEW_PAGE)
    body.page_width = Cm(21)
    body.page_height = Cm(29.7)
    body.top_margin = Cm(1.75)
    body.bottom_margin = Cm(1.55)
    body.left_margin = Cm(2.2)
    body.right_margin = Cm(2.2)
    body.header_distance = Cm(0.65)
    body.footer_distance = Cm(0.65)
    body.different_first_page_header_footer = False
    set_page_number_start(body, 1)

    body.header.is_linked_to_previous = False
    body.footer.is_linked_to_previous = False
    header = body.header
    hp = header.paragraphs[0]
    hp.text = ""
    hp.paragraph_format.tab_stops.add_tab_stop(Cm(CONTENT_WIDTH_CM), alignment=2)
    left = hp.add_run("探海灵眸 Oceanus")
    left.bold = True
    left.font.name = FONT_CN
    left.font.size = Pt(8.5)
    left.font.color.rgb = RGBColor.from_string(NAVY)
    # The Header style already provides a center tab stop; the second tab
    # reaches the explicit right-aligned stop without moving the title left.
    hp.add_run("\t\t")
    right = hp.add_run("系统设计报告")
    right.font.name = FONT_CN
    right.font.size = Pt(8.5)
    right.font.color.rgb = RGBColor.from_string(MID)
    add_paragraph_border(hp, "bottom", LIGHT, 5)

    footer = body.footer
    for paragraph in list(footer.paragraphs):
        footer._element.remove(paragraph._element)
    footer_table = footer.add_table(rows=1, cols=3, width=Cm(CONTENT_WIDTH_CM))
    footer_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    footer_table.autofit = False
    remove_table_borders(footer_table)
    set_table_width(footer_table, CONTENT_WIDTH_CM)
    set_col_widths(footer_table, [CONTENT_WIDTH_CM / 3] * 3)
    set_row_height(footer_table.rows[0], 0.42)
    left_cell, center_cell, right_cell = footer_table.rows[0].cells
    for cell in footer_table.rows[0].cells:
        set_cell_margins(cell, 0, 0, 0, 0)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    left_cell.text = ""
    center_cell.text = ""
    right_cell.text = ""
    center_p = center_cell.paragraphs[0]
    center_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    center_p.paragraph_format.space_before = Pt(0)
    center_p.paragraph_format.space_after = Pt(0)
    center_run = center_p.add_run("2026 年海峡大学生人工智能创意大赛")
    center_run.font.name = FONT_CN
    center_run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    center_run.font.size = Pt(8.5)
    center_run.font.color.rgb = RGBColor.from_string(MID)
    right_p = right_cell.paragraphs[0]
    right_p.paragraph_format.space_before = Pt(0)
    right_p.paragraph_format.space_after = Pt(0)
    add_page_number(right_p)


def add_cover(doc: Document) -> None:
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(0)
    spacer.paragraph_format.line_spacing = 1
    spacer.add_run("").font.size = Pt(88)

    label = doc.add_paragraph()
    label.paragraph_format.left_indent = Cm(2.05)
    label.paragraph_format.space_after = Pt(8)
    lr = label.add_run("2026 年海峡大学生人工智能创意大赛  /  参赛作品")
    lr.bold = True
    lr.font.name = FONT_CN
    lr.font.size = Pt(10.5)
    lr.font.color.rgb = RGBColor.from_string(TEAL)

    title = doc.add_paragraph()
    title.style = doc.styles["Title"]
    title.paragraph_format.left_indent = Cm(2.05)
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(0)
    tr = title.add_run("探海灵眸 Oceanus")
    tr.bold = True
    tr.font.name = FONT_CN
    tr.font.size = Pt(31)
    tr.font.color.rgb = RGBColor.from_string(NAVY)

    subtitle = doc.add_paragraph()
    subtitle.paragraph_format.left_indent = Cm(2.05)
    subtitle.paragraph_format.space_before = Pt(4)
    subtitle.paragraph_format.space_after = Pt(12)
    sr = subtitle.add_run("面向近岸养殖区漂浮垃圾的可审计治理智能体")
    sr.font.name = FONT_CN
    sr.font.size = Pt(15)
    sr.font.color.rgb = RGBColor.from_string(MID)

    line = doc.add_paragraph()
    line.paragraph_format.left_indent = Cm(2.05)
    line.paragraph_format.right_indent = Cm(2.05)
    line.paragraph_format.space_after = Pt(14)
    add_paragraph_border(line, "bottom", TEAL, 10)

    doc_type = doc.add_paragraph()
    doc_type.paragraph_format.left_indent = Cm(2.05)
    doc_type.paragraph_format.space_after = Pt(6)
    dr = doc_type.add_run("系统设计报告")
    dr.bold = True
    dr.font.name = FONT_CN
    dr.font.size = Pt(15)
    dr.font.color.rgb = RGBColor.from_string(NAVY)

    definition = doc.add_paragraph()
    definition.paragraph_format.left_indent = Cm(2.05)
    definition.paragraph_format.right_indent = Cm(2.05)
    definition.paragraph_format.space_after = Pt(10)
    definition.add_run("看得见 · 想得清 · 管得住 · 查得到").font.size = Pt(11)
    for run in definition.runs:
        run.font.name = FONT_CN
        run.font.color.rgb = RGBColor.from_string(TEAL_DARK)

    report_meta = doc.add_paragraph()
    report_meta.paragraph_format.left_indent = Cm(2.05)
    report_meta.paragraph_format.right_indent = Cm(2.05)
    report_meta.paragraph_format.space_before = Pt(6)
    report_meta.paragraph_format.space_after = Pt(0)
    meta_run = report_meta.add_run(
        "报告日期：2026 年 10 月    文档版本：参赛优化版    最高证据等级：E2"
    )
    meta_run.font.name = FONT_CN
    meta_run.font.size = Pt(9)
    meta_run.font.color.rgb = RGBColor.from_string(INK)

    footer = doc.add_paragraph()
    footer.paragraph_format.left_indent = Cm(2.05)
    footer.paragraph_format.right_indent = Cm(2.05)
    footer.paragraph_format.space_before = Pt(18)
    fr = footer.add_run("OCEANUS PROJECT  ·  2026")
    fr.bold = True
    fr.font.name = FONT_EN
    fr.font.size = Pt(8)
    fr.font.color.rgb = RGBColor.from_string(INK)


def new_page() -> None:
    # Keep the body as one continuous report; only the appendix starts afresh.
    return


def section_header(number: str, title_text: str, kicker: str = "") -> None:
    p = doc.add_paragraph()
    if number == "25":
        p.paragraph_format.page_break_before = True
    p.paragraph_format.space_before = Pt(2 if number == "01" else 16)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(number + "  " + (kicker or "系统设计报告"))
    r.bold = True
    r.font.name = FONT_CN
    r.font.size = Pt(8.3)
    r.font.color.rgb = RGBColor.from_string(TEAL)

    h = doc.add_heading(level=1)
    h.paragraph_format.space_before = Pt(0)
    h.paragraph_format.space_after = Pt(8)
    h.paragraph_format.keep_with_next = True
    run = h.add_run(title_text)
    run.font.name = FONT_CN
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    run.font.size = Pt(16.5)
    run.font.color.rgb = RGBColor.from_string(NAVY)
    add_paragraph_border(h, "bottom", TEAL, 6)


def body(text: str, *, bold_lead: str | None = None, size=10.2, color=INK, space_after=5) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.5
    p.paragraph_format.first_line_indent = Cm(0.74)
    if bold_lead:
        r = p.add_run(bold_lead)
        r.bold = True
        r.font.name = FONT_CN
        r.font.size = Pt(size)
        r.font.color.rgb = RGBColor.from_string(TEAL_DARK)
    r = p.add_run(text)
    r.font.name = FONT_CN
    r._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    r.font.size = Pt(size)
    r.font.color.rgb = RGBColor.from_string(color)


def bullet(text: str, *, size=9.8, color=INK, level=0) -> None:
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.left_indent = Cm(0.55 + level * 0.45)
    p.paragraph_format.first_line_indent = Cm(-0.25)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.35
    run = p.add_run(text)
    run.font.name = FONT_CN
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)


def add_caption(text: str, *, source: str = "") -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(7)
    r = p.add_run(text)
    r.italic = True
    r.font.name = FONT_CN
    r.font.size = Pt(8.2)
    r.font.color.rgb = RGBColor.from_string(INK)
    if source:
        s = p.add_run("  " + source)
        s.font.name = FONT_CN
        s.font.size = Pt(8.2)
        s.font.color.rgb = RGBColor.from_string(INK)


def add_figure(path: Path, width_cm: float, caption: str, source: str = "") -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(5)
    p.paragraph_format.space_after = Pt(9)
    p.paragraph_format.keep_together = True
    p.add_run().add_picture(
        str(path),
        width=Cm(min(width_cm, CONTENT_WIDTH_CM - 0.8)),
    )
    p.add_run().add_break(WD_BREAK.LINE)
    caption_run = p.add_run(caption)
    caption_run.italic = True
    caption_run.font.name = FONT_CN
    caption_run.font.size = Pt(8.2)
    caption_run.font.color.rgb = RGBColor.from_string(INK)
    if source:
        source_run = p.add_run("  " + source)
        source_run.font.name = FONT_CN
        source_run.font.size = Pt(8.2)
        source_run.font.color.rgb = RGBColor.from_string(INK)


def add_callout(
    title_text: str,
    text: str,
    *,
    fill=PALE_BLUE,
    accent=TEAL,
    trailing_spacer: bool = True,
) -> None:
    accent_width = 0.22
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    remove_table_borders(table)
    set_table_width(table, CONTENT_WIDTH_CM)
    set_table_fixed_layout(table)
    set_col_widths(table, [accent_width, CONTENT_WIDTH_CM - accent_width])
    set_row_cant_split(table.rows[0])

    accent_cell, body_cell = table.rows[0].cells
    set_cell_shading(accent_cell, accent)
    set_cell_shading(body_cell, fill)
    set_cell_margins(accent_cell, 0, 0, 0, 0)
    set_cell_margins(body_cell, 120, 120, 160, 160)
    accent_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    body_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    set_cell_text(accent_cell, "", size=2)
    add_rich_cell(
        body_cell,
        [
            (title_text + "  ", {"bold": True, "color": accent, "size": 9.5}),
            (text, {"color": INK, "size": 9.5}),
        ],
    )
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(8 if trailing_spacer else 4)
    spacer.paragraph_format.line_spacing = 1
    spacer.add_run("").font.size = Pt(1)


def add_metric_cards(metrics: list[tuple[str, str, str, str]], widths=None) -> None:
    if not metrics:
        return
    if widths is None:
        widths = [CONTENT_WIDTH_CM / len(metrics)] * len(metrics)
    table = doc.add_table(rows=1, cols=len(metrics))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    remove_table_borders(table)
    set_table_width(table, sum(widths))
    set_table_fixed_layout(table)
    set_col_widths(table, widths)
    set_row_cant_split(table.rows[0])

    for cell, (value, label, color, fill) in zip(table.rows[0].cells, metrics):
        set_cell_shading(cell, fill)
        set_cell_border(cell, top=color, size=18)
        set_cell_margins(cell, 160, 160, 140, 140)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        cell.text = ""
        value_p = cell.paragraphs[0]
        value_p.paragraph_format.space_before = Pt(0)
        value_p.paragraph_format.space_after = Pt(2)
        value_run = value_p.add_run(value)
        value_run.bold = True
        value_run.font.name = FONT_CN
        value_run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
        value_run.font.size = Pt(18)
        value_run.font.color.rgb = RGBColor.from_string(color)
        label_p = cell.add_paragraph()
        label_p.paragraph_format.space_before = Pt(0)
        label_p.paragraph_format.space_after = Pt(0)
        label_run = label_p.add_run(label)
        label_run.font.name = FONT_CN
        label_run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT_CN)
        label_run.font.size = Pt(8.5)
        label_run.font.color.rgb = RGBColor.from_string(MID)

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(5)
    spacer.paragraph_format.line_spacing = 1
    spacer.add_run("").font.size = Pt(1)


def add_table(
    headers: list[str],
    rows: list[list[str]],
    widths: list[float],
    *,
    header_fill=NAVY,
    font_size=8.8,
    row_fills: list[str] | None = None,
    first_col_bold=False,
) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_table_width(table, sum(widths))
    set_table_fixed_layout(table)
    set_col_widths(table, widths)
    # Neutral table borders
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = OxmlElement("w:" + edge)
        tag.set(qn("w:val"), "single")
        tag.set(qn("w:sz"), "4")
        tag.set(qn("w:color"), LIGHT)
        borders.append(tag)
    tbl_pr.append(borders)

    hdr = table.rows[0]
    set_repeat_table_header(hdr)
    set_row_cant_split(hdr)
    for cell, h in zip(hdr.cells, headers):
        set_cell_shading(cell, header_fill)
        set_cell_margins(cell, 110, 110, 100, 100)
        set_cell_text(cell, h, size=8.8, bold=True, color=WHITE)

    for r_idx, row_data in enumerate(rows):
        row = table.add_row()
        set_row_height(row, 0.6)
        set_row_cant_split(row)
        fill = row_fills[r_idx] if row_fills and r_idx < len(row_fills) else WHITE
        for c_idx, (cell, value) in enumerate(zip(row.cells, row_data)):
            set_cell_shading(cell, fill)
            set_cell_margins(cell, 90, 90, 100, 100)
            set_cell_text(
                cell,
                value,
                size=font_size,
                bold=(first_col_bold and c_idx == 0),
                color=INK if c_idx > 0 else NAVY,
            )
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def add_pill_row(items: list[tuple[str, str]]) -> None:
    if not items:
        return
    width = CONTENT_WIDTH_CM / len(items)
    table = doc.add_table(rows=1, cols=len(items))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    remove_table_borders(table)
    set_table_width(table, CONTENT_WIDTH_CM)
    set_table_fixed_layout(table)
    set_col_widths(table, [width] * len(items))
    set_row_cant_split(table.rows[0])

    for cell, (label, color) in zip(table.rows[0].cells, items):
        set_cell_shading(cell, PALE)
        set_cell_border(cell, top=color, size=14)
        set_cell_margins(cell, 110, 110, 100, 100)
        set_cell_text(
            cell,
            label,
            size=8.5,
            bold=True,
            color=color,
            align=WD_ALIGN_PARAGRAPH.CENTER,
            line=1.15,
        )

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(7)
    spacer.paragraph_format.line_spacing = 1
    spacer.add_run("").font.size = Pt(1)


def make_anonymous_ui_screenshot() -> Path:
    source = UI / "1920x1080-sandbox-sim-done.png"
    target = BUILD / "sandbox_sim_done_anonymous.png"
    im = Image.open(source).convert("RGB")
    draw = ImageDraw.Draw(im)

    header_fill = im.getpixel((1400, 10))
    panel_fill = im.getpixel((20, 450))
    label_font = load_font(15)
    mark_font = load_font(16)

    role_box = (1502, 12, 1652, 59)
    draw.rounded_rectangle(role_box, radius=10, fill=header_fill)
    role_text = "演示账号"
    role_bbox = draw.textbbox((0, 0), role_text, font=label_font)
    role_w = role_bbox[2] - role_bbox[0]
    role_h = role_bbox[3] - role_bbox[1]
    draw.text(
        (
            role_box[0] + (role_box[2] - role_box[0] - role_w) / 2,
            role_box[1] + (role_box[3] - role_box[1] - role_h) / 2 - 1,
        ),
        role_text,
        font=label_font,
        fill="#5B7079",
    )

    # Remove local device credentials, coordinates and private network details.
    for top, bottom in ((445, 476), (533, 563), (577, 608), (617, 650)):
        draw.rectangle((136, top, 1465, bottom), fill=panel_fill)
        draw.text((160, top + 7), "已脱敏", font=mark_font, fill="#5B7079")

    im.save(target, quality=95, optimize=True)
    return target


def build_doc() -> None:
    global doc, pending_page_break
    ensure_dirs()
    assets = make_assets()
    anonymous_ui = make_anonymous_ui_screenshot()
    pending_page_break = False

    doc = Document()
    style_document(doc)
    doc.core_properties.title = "Oceanus - System Design Document"
    doc.core_properties.subject = "2026 Strait University Student AI Creativity Competition Entry"
    doc.core_properties.author = ""
    doc.core_properties.last_modified_by = ""
    doc.core_properties.keywords = "Oceanus, Auditable AI Agent, Marine Litter"
    doc.core_properties.comments = ""
    add_cover(doc)
    configure_sections(doc)

    # Page 2: Executive summary and score map
    new_page()
    section_header("01", "从视觉识别到可交付治理闭环", "执行摘要")
    body(
        "探海灵眸 Oceanus 面向近岸养殖区、港口与景区水域的漂浮垃圾治理场景，"
        "把视觉检测、事件验证、空间派单、受控执行、人工审批与证据核算串成一条可审计闭环。"
        "每次发现都保留原始证据、决策依据、审批人和核验结果，使事件能够从告警进入任务与处置流程。",
        size=10.6,
    )
    add_callout(
        "作品定位",
        "一个以证据为中心、以策略与审批约束写操作、可在不同模型和设备上迁移的近岸垃圾治理智能体。",
        fill=CYAN,
        accent=TEAL,
    )
    add_metric_cards(
        [
            ("27/27", "固定评测场景断言通过", TEAL, PALE_BLUE),
            ("129/129", "真实 HTTP + DB 集成验收", GREEN, "EAF7F1"),
            ("0", "策略违规执行（评测口径）", "6D45B8", "F2EDFC"),
            ("E2", "当前最高集成证据等级", ORANGE, PALE_ORANGE),
        ]
    )
    body("能力与证据概览", bold_lead="", size=9.5, color=TEAL_DARK)
    add_table(
        ["能力维度", "需要回答的问题", "对应实现与证据"],
        [
            ["治理闭环", "过程能否解释、复核和重放？", "Run / Step / Tool / Policy / Approval / Replay / Eval 七类记录；写操作强制审批。"],
            ["技术解耦", "模型、算力与设备能否替换？", "ONNX 导出、多 provider 探测、HTTP 推理服务与 Ascend 迁移路径。"],
            ["链路完整", "发现到处置是否连续？", "事件→时序→派单→执行→证据→报表全链路；平台与机械臂均有可演示接口。"],
            ["使用场景", "哪些角色会持续使用？", "养殖户、乡镇、巡查队与监管四方角色；按点位订阅并提供运营服务。"],
            ["公共价值", "对治理工作的直接作用是什么？", "降低临水巡检风险、减少无效出勤，并沉淀可复核的治理数据。"],
        ],
        [3.0, 5.4, 9.15],
        font_size=8.5,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE],
        first_col_bold=True,
    )
    # Page 3: Real problem
    new_page()
    section_header("02", "治理难点：发现之后缺少可执行的处置链路", "问题定义")
    body(
        "近岸漂浮垃圾具有来源分散、随潮汐漂移、出现时间不固定、处置责任跨角色等特点。"
        "单点摄像头能提供告警，却不能天然形成可派发、可审批、可核算的治理工单；"
        "而只做机器人或只做模型，也无法回答管理端最关心的“为何派、派给谁、完成没有、凭什么认定完成”。",
    )
    add_pill_row(
        [
            ("发现：画面有垃圾", TEAL),
            ("确认：是不是误报", TEAL),
            ("派单：谁去最合适", ORANGE),
            ("执行：动作是否安全", "6D45B8"),
            ("核算：结果如何留证", GREEN),
        ]
    )
    add_table(
        ["治理断点", "现实表现", "Oceanus 的接口化回应"],
        [
            ["误报进入业务", "浪花、反光、飞鸟被当成垃圾；人工反复看视频。", "目标跟踪 + 连续命中 + 冷却窗口，先形成“可信事件”再触发业务。"],
            ["工单缺少理由", "派单靠电话和群消息，优先级与设备状态割裂。", "PostGIS 邻近检索叠加在线、电量、仓容和同类顺路权重。"],
            ["写操作难追责", "自动建单、下发设备、修改状态缺统一审批边界。", "工具声明权限与风险；write/high-risk 默认进入人工审批。"],
            ["完成口径不统一", "口头说清理完成，前后影像和重量分散在聊天记录。", "证据表约束闭环；无证据的“完成”不进入治理核算。"],
            ["模型无法迁移", "换了模型或设备，业务逻辑要重写。", "推理服务、模型适配器、MQTT 执行端均以契约隔离。"],
        ],
        [3.2, 7.1, 7.25],
        font_size=8.6,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE],
        first_col_bold=True,
    )
    add_callout(
        "设计判断",
        "把 AI 的角色从“单次识别器”提升为“受策略约束的治理执行者”，让自动化只发生在可审计、可回滚、可人工接管的边界内。",
        fill=PALE_ORANGE,
        accent=ORANGE,
    )
    body(
        "目标用户与任务：养殖户关心“何时清、清了多少”；乡镇巡查队关心“先处理哪里”；"
        "监管与考核人员关心“证据是否完整”；一线操作员关心“设备是否听指令、异常能否停得住”。"
        "四类角色共同构成产品的真实使用链路。",
        size=9.2,
    )

    # Page 4: Value proposition and scope
    new_page()
    section_header("03", "方案定位：可替换的模型，稳定不变的治理契约", "方案总览")
    add_figure(assets["innovation"], 17.2, "图 1  四条能力链围绕同一治理内核闭环", "自绘")
    body(
        "Oceanus 把系统分为感知、事件、决策、执行、核算五层。模型、设备和页面都可以替换，"
        "但事件证据、策略规则、审批记录、工具调用和结果核算保持同一套契约。"
        "这使作品既能作为 Web 平台运行，也能接入水面机器人、机械臂或无人机，而不被单一硬件绑死。",
        size=9.6,
    )
    add_table(
        ["层", "职责", "当前实现", "价值"],
        [
            ["感知", "从图像形成可解释检测结果", "OpenCV / ONNX Runtime / 独立 HTTP 推理服务", "模型可替换，CPU/GPU provider 可探测"],
            ["事件", "去重、时序验证、空间派单", "FastAPI + Redis Streams + PostGIS", "先验证再触发，减少误报驱动出勤"],
            ["决策", "规划、策略守卫、审批、重规划", "治理智能体内核", "自动化有边界，失败可解释"],
            ["执行", "任务下发、ACK、进度、遥测", "MQTT/EMQX + 可插拔驱动", "平台与设备解耦"],
            ["核算", "证据归档、报表、热力图", "MinIO + PostgreSQL + Vue 3", "结果可复核、可交付"],
        ],
        [1.1, 4.4, 7.4, 4.65],
        font_size=8.3,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE],
    )
    add_callout(
        "产品边界",
        "当前文档描述的是“软件平台 + 受控执行端”的系统设计。自动视觉抓取尚未宣称完成，真实海域规模化验证也尚未开展；这两项被明确列为下一阶段里程碑。",
        fill=PALE_RED,
        accent=RED,
    )

    # Page 5: Core innovations
    new_page()
    section_header("04", "四项核心机制：把模型能力纳入可控运行边界", "技术创新")
    body(
        "Oceanus 将模型的不确定性纳入可验证、可审批、可回放和可度量的运行机制。"
        "四项机制分别约束执行轨迹、工具权限、业务状态与模型迁移边界。",
    )
    innovation_rows = [
        [
            "01  可审计治理智能体",
            "Run 记录目标与终止原因；Step 保留计划、工具、观察、验证与重规划轨迹；工具输入输出哈希固化。",
            "从“结果对不对”升级为“过程能否解释、能否复核、能否再跑一次”。",
        ],
        [
            "02  风险感知的工具契约",
            "每个工具声明 permission、risk_level、timeout、idempotency_key、audit_event 与错误码。",
            "越权调用被策略守卫拦截；写入与高风险设备指令进入人工审批。",
        ],
        [
            "03  事件—空间—证据三层收敛",
            "时序验证解决误报，PostGIS 解决就近派单，证据表解决结果核算；异常均结构化返回。",
            "AI 输出不再直接驱动业务写入，而是经过证据门槛和业务状态机。",
        ],
        [
            "04  模型与执行器解耦",
            "OpenAI 兼容适配器、ONNX 多 provider、MQTT 可插拔执行端与统一任务契约。",
            "同一治理内核可迁移到云、边缘机、Ascend 或不同机器人。",
        ],
    ]
    add_table(
        ["核心机制", "实现方式", "工程作用"],
        innovation_rows,
        [4.0, 8.4, 5.15],
        font_size=8.6,
        row_fills=[PALE_BLUE, "F2EDFC", PALE_ORANGE, "EAF7F1"],
        first_col_bold=True,
    )
    add_callout(
        "模型与规则的分工",
        "模型可用时负责生成计划；模型不可用时规则模式仍能完成核心派单闭环。"
        "模型输出只作为计划输入，业务写入仍需经过策略守卫、状态机与必要的人工审批。",
        fill=CYAN,
        accent=TEAL,
    )
    bullet("事实、推断、人工确认在记忆中分源存储；禁止把模型推断写成事实。", size=9.1)
    bullet("重规划产生新的 step_no，历史步骤不被覆盖；回放用于核对轨迹而非重新编故事。", size=9.1)
    bullet("所有失败有结构化错误码，支持从 UI 直接定位到策略、审批或工具环节。", size=9.1)

    # Page 6: End-to-end architecture
    new_page()
    section_header("05", "端到端架构：从一帧图像到一份可核实治理记录", "系统架构")
    add_figure(assets["state"], 17.25, "图 2  治理 Run 状态机：正常、审批、重规划与安全终止", "自绘")
    body(
        "一次完整运行从事件接入开始。系统先对 `event_id` 或 `(device_id, seq)` 做幂等去重，"
        "再通过目标跟踪、连续命中和冷却窗口确认事件。确认后，智能体读取事件与设备状态，"
        "生成派单计划；若涉及写操作，先经过策略守卫与人工审批，再调用 MQTT 工具下发任务。"
        "设备回传 ACK、进度、遥测和证据后，系统进入观察与验证阶段，最终成功或结构化失败。",
        size=9.3,
    )
    add_table(
        ["关键对象", "作用", "不可省略的约束"],
        [
            ["Event", "一次候选发现及其帧、类别、坐标、时间", "幂等键唯一；时间与创建时间分离；缺坐标不参与空间派单"],
            ["Task", "可派发、可执行、可追踪的业务工单", "状态机守卫；目标点与设备绑定；失败原因结构化"],
            ["Run / Step", "智能体一次治理过程及其历史轨迹", "步骤只追加不覆盖；终止原因必填；轨迹可回放"],
            ["Approval", "对写操作或高风险动作的人工决策", "请求人、决策人、理由、时间完整保存"],
            ["Evidence", "前后影像、重量、复核记录", "完成必须关联证据；估算值不得冒充实测"],
        ],
        [2.6, 7.7, 7.25],
        font_size=8.3,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE],
    )
    add_callout(
        "架构原则",
        "依赖单向、契约先行、失败姿态明确、证据内建。感知层不直接触发派单，设备不直接写数据库，报表层不反向修改业务状态。",
        fill=PALE_BLUE,
        accent=TEAL,
    )

    # Page 7: Auditable agent runtime
    new_page()
    section_header("06", "治理智能体：不放手的自动化，可控地完成", "核心机制")
    add_figure(ASSETS / "arch_layered.png", 16.6, "图 3  五层闭环与治理内核在系统中的位置", "系统架构")
    body(
        "运行时把一次治理拆成可观察的步骤：计划、策略检查、工具调用、观察、验证、重规划与终止。"
        "每一步都记录步骤类型、输入输出哈希、状态、耗时和错误码。"
        "审批是一个正式状态，不是弹窗提醒：等待审批期间不执行写工具，超时、拒绝和通过分别产生可追踪结果。",
        size=9.1,
    )
    add_table(
        ["运行组件", "解决的问题", "实现要点"],
        [
            ["Planner", "下一步做什么", "规则模式可独立运行；模型模式只生成受 Schema 约束的计划"],
            ["Policy", "这一步允许做吗", "按角色、权限、风险与服务状态拦截；违规不进入执行"],
            ["Tool Executor", "如何安全执行", "超时、重试上限、幂等键、输入输出 Schema 校验与审计"],
            ["Observer / Verifier", "做完之后真的成立吗", "读取真实状态，不把“已下发”误判为“已完成”"],
            ["Replay / Eval", "以后能否复核与回归", "固定场景、期望轨迹、失败样本和版本化评测记忆"],
        ],
        [3.0, 5.0, 9.55],
        font_size=8.35,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE],
    )
    # Page 8: Perception benchmark
    new_page()
    section_header("07", "感知能力：用独立公开基准说话，也不越过证据边界", "感知与验证")
    body(
        "项目采用 YOLO11 微调模型作为有监督基线，并保留 YOLO-World 零样本路径用于快速扩展类别。"
        "评测在第三方公开数据集 SC-FloatWaste 上完成，包含 400 张图像、1,490 个标注框和三个区域。"
        "这组结果用于证明模型训练与导出链路有效，不等同于连江海域现场精度，也不等同于项目设备实测精度。",
        size=9.4,
    )
    add_table(
        ["评测对象", "mAP@0.5", "mAP@0.5:0.95", "最佳 F1", "Precision", "Recall"],
        [
            ["YOLO11 微调", "0.5135", "0.3444", "0.5376", "0.5665", "0.5114"],
            ["YOLO-World 零样本", "0.1432", "0.0930", "0.2702", "—", "—"],
        ],
        [3.4, 2.6, 3.0, 2.6, 2.75, 2.4],
        font_size=8.8,
        row_fills=[PALE_BLUE, PALE],
        first_col_bold=True,
    )
    add_callout(
        "区域差异",
        "YOLO11 在 Indonesia / NSW / Hobart 的 mAP@0.5 分别为 0.7229 / 0.3341 / 0.4029。差异说明跨水域域偏移真实存在，模型不能凭一次基准测试宣称“通用准确”。",
        fill=PALE_ORANGE,
        accent=ORANGE,
    )
    add_figure(
        assets["detection_pair"],
        16.8,
        "图 4  水面与岸滩检测界面示例（展示输出形态，不作为现场精度证据）",
        "公开数据/项目截图",
    )
    body(
        "工程侧通过 ONNX 导出、输入尺寸固定、批次为 1 与图简化降低边缘部署成本；"
        "推理服务在 `/infer/health` 中返回实际 provider 与降级状态，调用方必须检查 `mode`，避免模型缺失时静默误判。",
        size=8.8,
        color=MID,
        space_after=0,
    )

    # Page 9: Temporal and spatial
    new_page()
    section_header("08", "从检测到可信事件：先降噪，再派单", "业务闭环")
    add_figure(
        assets["temporal"],
        17.25,
        "图 5  时序先验误报抑制链路",
        "合成海面测试数据；76% 为链路过滤率，不等于识别精度",
    )
    body(
        "单帧置信度无法直接代表业务真实性。系统在候选框进入业务前加入三层收敛："
        "抽帧与跟踪关联减少重复目标，连续命中提升时序稳定性，冷却窗口避免同一事件反复建单。"
        "该链路的输出是“可信事件”，不是“绝对事实”；最终仍需现场执行与证据回传完成闭环。",
        size=8.9,
    )
    add_table(
        ["派单因子", "为什么纳入", "落地方式"],
        [
            ["空间距离", "最近设备通常响应更快", "PostGIS KNN 邻近检索"],
            ["设备在线 / 电量 / 仓容", "不可用设备不应进入候选", "设备表状态过滤与门槛约束"],
            ["同类任务顺路", "减少重复往返", "同类类别活跃任务加权"],
            ["优先级与截止时间", "公共风险需要排序", "任务优先级与超时处理"],
            ["派单理由", "便于人工复核与追责", "dispatch_score / reject_reason 持久化"],
        ],
        [4.0, 6.4, 7.15],
        font_size=8.45,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE],
    )
    add_callout(
        "异常路径同样是产品的一部分",
        "无设备可用、ACK 超时、工具超时、审批拒绝、模型不可用和无效循环都进入固定评测场景；系统必须给出结构化原因，而不是卡在“运行中”。",
        fill=PALE_BLUE,
        accent=TEAL,
    )

    # Page 10: Human in the loop
    new_page()
    section_header("09", "人在回路：让审批成为状态，而不是礼貌提示", "安全设计")
    add_figure(ASSETS / "tool_risk_matrix.png", 16.8, "图 6  工具权限 × 风险矩阵", "工具注册契约")
    body(
        "智能体只允许调用注册表中存在的工具。读工具可在策略允许下自动执行；"
        "创建/合并工单等写工具需要角色权限；设备下发属于高风险写操作，默认必须人工审批。"
        "审批人看到的是具体动作、参数摘要、风险级别与关联 Run，而不是一段模糊的自然语言。",
        size=9.0,
    )
    add_table(
        ["角色", "可以看到", "可以决定", "系统保留的审计信息"],
        [
            ["操作员", "事件、证据帧、可用设备与计划摘要", "低风险操作；发起审批", "查看/操作时间、Run、角色"],
            ["复核员", "前序步骤、策略结果、异常原因", "审批通过或拒绝", "决策理由、决策人、参数哈希"],
            ["管理员", "全量运行轨迹与工具目录", "工具配置、策略修订", "版本、变更前状态、生效时间"],
            ["系统", "设备状态、工具结果、验证条件", "执行策略守卫与超时终止", "结构化错误码、步骤号、终止原因"],
        ],
        [2.4, 5.2, 4.7, 5.25],
        font_size=8.3,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE],
    )
    add_callout(
        "安全底线",
        "等待审批期间不执行写工具；审批被拒绝时 Run 终止且不下发设备；同一幂等键不会因重试产生重复工单。",
        fill=PALE_RED,
        accent=RED,
    )
    body(
        "这种设计把“人类监督”从演示时的口头承诺，变成状态机、权限表、数据库记录和固定评测场景，"
        "更适合需要责任边界的公共服务场景。",
        size=9.1,
    )

    # Page 11: Platform demo
    new_page()
    section_header("10", "可交互平台：同一套数据贯通监测与派单", "产品演示")
    add_figure(
        UI / "1920x1080-sandbox-tracked.png",
        16.2,
        "图 7  监测大屏：现场视频、三维态势、实时告警、工单与机器人状态",
        "项目截图",
    )
    body(
        "大屏不是静态看板：地图点位、告警、设备状态、工单与事件来自统一业务数据。"
        "用户可以进入事件中心查看检测证据，进入工单板了解派单结果，再进入智能体控制台核对每个决策步骤。",
        size=9.1,
    )
    add_metric_cards(
        [
            ("6 类", "核心导航与业务流程", TEAL, PALE_BLUE),
            ("Web", "桌面与移动自适应", GREEN, "EAF7F1"),
            ("可回放", "Run / Step 轨迹", ORANGE, PALE_ORANGE),
        ]
    )
    add_pill_row(
        [
            ("大屏：发现", TEAL),
            ("事件：确认", TEAL),
            ("工单：派发", ORANGE),
            ("控制台：审计", "6D45B8"),
            ("报表：核算", GREEN),
        ]
    )
    body(
        "演示流程可在无真实摄像头时注入模拟事件，也可切换到受控执行端模拟任务下发、ACK、进度和完成；"
        "异常注入用于展示策略拒绝、审批拒绝、设备故障与模型不可用时的行为。",
        size=8.9,
        color=MID,
        space_after=0,
    )

    # Page 12: Agent console audit
    new_page()
    section_header("11", "可审计控制台：任务过程与决策依据可视化", "交互验证")
    add_figure(
        CONSOLE / "run-steps-viewport.png",
        16.2,
        "图 8  Run 轨迹回放：策略、审批、工具调用、观察、验证与终止逐步骤展开",
        "项目截图",
    )
    body(
        "以一次正常派单为例，控制台显示 13 个步骤：计划、策略守卫、审批请求、事件读取、设备查询、"
        "空间派单、工单创建、观察、验证和正常终止。每一步均可看到摘要与状态；"
        "失败运行则直接显示错误码与失败位置。",
        size=9.0,
    )
    add_table(
        ["演示问题", "控制台给出的回答"],
        [
            ["为什么派给这台机器人？", "展示候选、距离、同类任务加权和最终 dispatch 计划。"],
            ["这次写操作谁批准了？", "审批请求、请求人、决策人、理由和时间均可在 Run 中追溯。"],
            ["工具返回后系统怎么判断？", "观察步骤读取真实返回，验证步骤逐条核对计划期望。"],
            ["失败后能不能重试又不重复建单？", "幂等键与工具级去重保证重放不产生重复业务写入。"],
        ],
        [5.0, 12.55],
        font_size=8.8,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE],
    )
    add_callout(
        "运行状态投影",
        "同一界面同时服务日常操作、任务跟踪与事后审计，数据直接读取运行时状态。",
        fill=CYAN,
        accent=TEAL,
    )

    # Page 13: Data structures and interfaces
    new_page()
    section_header("12", "接口与数据结构：先把契约讲清，再谈自动化", "工程实现")
    add_figure(assets["er"], 16.4, "图 9  核心数据关系：事件、任务、证据与智能体轨迹", "PostgreSQL + PostGIS")
    body(
        "接口层用 Schema 冻结跨模块契约。事件入口采用双重幂等键；推理服务公开 provider、模型版本与降级状态；"
        "MQTT 使用 task / ack / progress / telemetry / evidence 五类主题。"
        "数据库把业务表与智能体表分开，既保证治理轨迹独立，也允许业务系统单独演进。",
        size=8.4,
    )
    add_table(
        ["契约", "关键字段 / 主题", "设计意图"],
        [
            ["POST /api/v1/events", "event_id, device_id, seq, category, confidence, bbox, location, captured_at", "事件可重复提交但不重复入账；设备重传是正常现象"],
            ["GET /agents/runs/{id}/steps", "step_no, step_type, tool_name, input_hash, output_hash, status, error_code", "运行轨迹只追加不覆盖，可精确回放"],
            ["POST /approvals/{id}/decide", "requested_action, risk_level, decision, reason, decided_by", "把人工决策变成正式状态与审计事件"],
            ["MQTT task/assign", "task_id, target, priority, deadline", "平台与执行端通过统一任务契约解耦"],
            ["Evidence", "kind, object_key, weight_kg, reviewed_by", "闭环与核算只认证据，不用估算值冒充实测"],
        ],
        [4.0, 8.1, 5.45],
        font_size=7.6,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE],
    )
    add_callout(
        "工程取舍",
        "只保留关键契约：幂等、状态机、权限、审批、证据与降级；实现细节由源码与验收报告承载。",
        fill=PALE_BLUE,
        accent=TEAL,
        trailing_spacer=False,
    )

    # Page 14: Robot execution
    new_page()
    section_header("13", "机械臂执行端：先把“跑通”与“抓准”分开", "软硬件集成")
    add_figure(assets["robot"], 17.0, "图 10  机械臂执行端证据边界", "联调存档 2026-10-17")
    body(
        "执行端以 ArmPiFPV 为载体，板端运行 ROS 与总线舵机控制，桌面端通过 HTTP/MQTT 桥接下发任务。"
        "系统已实现六路舵机回读、逆运动学解算、TCP 自检、开机姿态服务与七标签页手动控制台；"
        "机械臂相关代码测试 91 项通过，说明控制与执行链路已具备可复现的软件基础；自动视觉抓取仍未完成。",
        size=8.9,
    )
    add_figure(
        anonymous_ui,
        16.2,
        "图 11  平台中的执行端仿真与执行档案：任务、遥测、证据等级和生命周期",
        "项目截图；仿真执行，非真实海试",
    )
    add_callout(
        "必须保留的诚实披露",
        "自动视觉识别抓取尚未打通：室内浅色场景中模型 12/12 帧误锁夹爪；固定位置抓放动作序列无碰撞但夹爪空手。下一阶段先补仿射标定、稳定供电和场景特化数据，再宣称自动抓取。",
        fill=PALE_RED,
        accent=RED,
        trailing_spacer=False,
    )

    # Page 15: Surface and aerial execution platform layouts
    new_page()
    section_header("14", "执行端结构布局：水面与空中载体共用同一任务契约", "结构方案")
    body(
        "以下设计图说明双浮筒无人船与六旋翼无人机的部件关系、载荷位置和维护入口。"
        "三型载体共用任务下发、遥测回传、审批与证据契约，差异由 device driver 隔离；"
        "图中部件均为结构方案，不代表样机或性能证据。",
        size=8.4,
        space_after=0,
    )
    add_figure(
        DEVICE_SOURCE / "boat.png",
        13.8,
        "图 12  双浮筒无人船：机械臂、料斗与主要部件布局",
        "结构布局方案；非现场样机",
    )
    add_figure(
        DEVICE_SOURCE / "drone.png",
        13.8,
        "图 13  六旋翼无人机：巡检、抓取与机载收纳布局",
        "结构布局方案；非现场样机",
    )
    # Page 16: Ground platform layout and structural evidence boundary
    new_page()
    section_header("15", "地面执行端：履带底盘与拾取载荷的结构关系", "结构方案")
    add_figure(
        DEVICE_SOURCE / "car.png",
        14.7,
        "图 14  履带无人车：沙地通行与机械臂拾取布局",
        "结构布局方案；非现场样机",
    )
    add_table(
        ["结构单元", "方案中的部件", "当前可确认的事实与待验证项"],
        [
            ["通行结构", "履带、驱动轮、承重轮、导向轮、横向履齿", "面向岸滩松软地面与跨障设计；实际坡度、附着、续航和通过性仍需样机测试。"],
            ["拾取载荷", "旋转底座、机械臂、腕部摄像头、夹爪", "运动链与手动控制链路可作为后续集成基础；自动视觉抓取尚未打通。"],
            ["收纳结构", "垃圾料斗、上甲板、电池舱检修盖", "料斗容积、满载重心变化与行驶稳定性尚未完成称重和现场验证。"],
            ["控制边界", "电源、通信、传感器与设备驱动接口", "仅按任务、遥测、审批和证据契约对接；配电保护与故障降级待联调。"],
        ],
        [2.5, 6.0, 9.05],
        font_size=7.9,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE],
    )
    body(
        "说明书结构不替代样机验收。下一步需依次完成空载行驶、载荷称重、机械臂运动链复测、仿射标定与连续受控抓取，"
        "并将每一轮的故障、能耗与成功率写入证据台账。",
        size=8.4,
        color=TEAL_DARK,
        space_after=0,
    )

    # Page 17: Deployment and hardware/software platform
    new_page()
    section_header("16", "部署形态：单机可起，边缘可插，云边协同可扩展", "平台整合")
    add_figure(ASSETS / "deployment.png", 16.5, "图 15  Docker Compose 部署拓扑", "当前单机部署形态")
    body(
        "平台以 Docker Compose 组织前端、后端、AI 服务、PostgreSQL/PostGIS、Redis、EMQX 与 MinIO，"
        "可在单机环境一键启动，适合演示、试点与低成本部署。边缘侧通过 MQTT/HTTP 接入摄像头、水面机器人、"
        "无人机或机械臂，设备不直接访问数据库，执行指令必须经过任务状态机与权限边界。",
        size=9.0,
    )
    add_table(
        ["平台层次", "技术组成", "当前状态", "扩展方式"],
        [
            ["展示层", "Vue 3 + Vite + 地图可视化 + 响应式布局", "E2 可运行", "新增移动端/小程序视图"],
            ["服务层", "FastAPI + JWT + RBAC + Schema 校验", "E2 可运行", "拆分微服务或接入统一网关"],
            ["AI 层", "OpenCV + ONNX Runtime + 多 provider 探测", "E1/E2", "替换模型、接入 Ascend/CANN"],
            ["数据层", "PostgreSQL/PostGIS + Redis Streams + MinIO", "E2 可运行", "托管数据库、对象存储扩容"],
            ["执行层", "EMQX/MQTT + 可插拔 driver + ROS 机械臂", "E2 受控联调", "海面机器人、无人机、无人船"],
        ],
        [2.6, 7.0, 4.0, 3.95],
        font_size=8.3,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE],
    )
    add_callout(
        "平台价值",
        "把“算法验证”变成可部署的软件资产：一次接入，可在不同水域、不同设备与不同模型之间复用；部署成本随试点规模渐进增加。",
        fill=CYAN,
        accent=TEAL,
        trailing_spacer=False,
    )

    # Page 18: Ascend path
    new_page()
    section_header("17", "国产算力与开放工具链：把迁移点前置到架构里", "Ascend 路径")
    add_figure(assets["ascend"], 16.5, "图 16  已实测链路与待验证的昇腾迁移路径", "E2 软件集成；昇腾部分为方案设计，未做硬件实测")
    body(
        "作品当前完成的是 ONNX 导出、输入尺寸固定、多 provider 探测和独立 HTTP 推理服务化。"
        "这为国产算力迁移留下了明确改造点：将 ONNX 通过 ATC 转为 OM，接入 CANN Execution Provider，"
        "在 ModelArts / AgentArts 上部署服务。模型适配器保持 OpenAI 兼容协议，业务层不需要理解底层芯片。",
        size=8.9,
    )
    add_table(
        ["能力", "当前证据", "下一步", "验收口径"],
        [
            ["模型导出", "ONNX 导出与 `--verify` 自检", "固定算子集与版本矩阵", "同一输入输出在 CPU/目标芯片一致"],
            ["推理服务", "HTTP /infer/detect、/infer/health", "增加 Ascend provider 健康检查", "provider、模型版本、降级原因可观测"],
            ["云端智能体", "ModelArts / AgentArts 部署设计", "工具调用与审批链路联调", "Run 轨迹、超时与审批记录完整"],
            ["工具生态", "MCP 协议与 5 个 Skills 接入", "统一注册、版本与权限策略", "越权工具被拒绝且产生审计事件"],
        ],
        [2.8, 6.2, 4.5, 4.05],
        font_size=8.2,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE],
    )
    add_callout(
        "昇腾验证边界",
        "当前仅完成 ONNX 导出与多 provider 适配设计，尚无昇腾硬件推理实测；迁移完成前按方案级验证记录。",
        fill=PALE_ORANGE,
        accent=ORANGE,
    )

    # Page 19: Evaluation evidence
    new_page()
    section_header("18", "验证证据：27 个场景、129 项集成检查，指标不混用", "测试与验收")
    add_figure(ASSETS / "eval_results.png", 16.6, "图 17  治理智能体固定评测：场景通过、业务成功与待优化指标并列", "E1；无网络、无真实模型、无真实设备")
    body(
        "固定评测包含正常派单、无设备、策略拒绝、审批拒绝、审批超时、工具超时、最大步数、无效循环、"
        "重规划恢复、模型不可用、幂等重放、持久化重启、模型 Schema 错误、并发冲突、角色交接、设备故障注入等场景。"
        "27 个场景断言全部通过，但这不是“业务成功率 100%”：其中包含预期失败路径。",
        size=8.8,
    )
    add_metric_cards(
        [
            ("62.96%", "业务成功场景占比", TEAL, PALE_BLUE),
            ("33.33%", "可恢复异常恢复率", ORANGE, PALE_ORANGE),
            ("7.41%", "无效循环占比", RED, PALE_RED),
        ]
    )
    body(
        "业务成功、策略违规、轨迹回放、重启恢复、审批交接和工具正确率使用不同分母，不能合并成一个“总准确率”。"
        "真实 HTTP + PostgreSQL 验收的 129 项检查全部通过；它验证了鉴权、持久化、审批、幂等与只读回放，"
        "但使用合成 HTTP 事件，没有真实摄像头、海域、用户或硬件数据。",
        size=8.8,
        color=MID,
    )
    add_callout(
        "证据边界",
        "E1 = 软件/仿真测试；E2 = 真实组件集成受控实验；E3 = 真实海域/设备/用户现场验证。"
        "当前最高证据等级为 E2；尚未进入生产部署或商业验证阶段。",
        fill=PALE_BLUE,
        accent=TEAL,
    )

    # Page 18: Evidence integrity
    new_page()
    section_header("19", "证据台账：每一项能力都能回到文件、版本与口径", "证据链")
    add_figure(assets["evidence"], 17.2, "图 18  四项核心验证结果", "对应 artifacts 目录中的机器可读报告")
    add_table(
        ["证据项", "关键结果", "能证明什么", "不能证明什么"],
        [
            ["agent_evals/latest_v2.json", "27/27 场景断言；89 次工具选择中 88 次正确；0 次策略违规", "智能体状态机、策略、审批、回放与异常路径", "真实模型在开放环境的稳定性"],
            ["agent-real-state-acceptance/latest.json", "129/129 检查；真实 HTTP + 鉴权 + PostgreSQL + 审批 + 重启只读回放", "组件集成与持久化契约", "真实摄像头、海区、用户或生产流量"],
            ["YOLO11 public benchmark", "mAP@0.5 = 0.5135；mAP@0.5:0.95 = 0.3444", "训练/评估流程与模型基本有效性", "连江现场或本设备精度"],
            ["机械臂联调存档", "6 舵机回读、IK、TCP、开机姿态、91 项测试通过", "控制与执行链路可在受控环境运行", "自动视觉抓取成功或海面作业能力"],
            ["UI / Agent Console", "大屏、工单、控制台、Run 步骤与审批界面可操作", "产品形态与操作流程已实现", "外观截图本身不能替代现场效果"],
        ],
        [4.1, 5.5, 4.5, 3.45],
        font_size=7.7,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE],
    )
    add_callout(
        "可复核性",
        "关键结果由 JSON/Markdown 报告与对应代码版本生成；正文中的百分比、分母和环境限制均可回溯。",
        fill=CYAN,
        accent=TEAL,
    )
    body(
        "复核顺序：先确认报告版本与生成时间，再核对分母与环境限制，最后检查结论是否越过证据等级。"
        "任何单项百分比都不单独作为“系统准确率”。",
        size=8.8,
        color=MID,
    )
    add_pill_row(
        [
            ("01  版本与时间", TEAL),
            ("02  分母与环境", ORANGE),
            ("03  证据等级", GREEN),
        ]
    )

    # Page 19: Source and modules
    new_page()
    section_header("20", "源码组织：五层代码边界与关键入口", "代码导航")
    body(
        "仓库按“业务平台 + 智能体内核 + 感知服务 + 边缘执行 + 前端展示 + 部署与验证”组织。"
        "关键模块、接口入口与测试记录分目录存放，可按功能直接定位。",
        size=9.1,
    )
    add_table(
        ["目录", "主要内容", "关键入口 / 证据"],
        [
            ["backend/app/api", "事件、设备、任务、审批、报表 API", "`api/v1/events.py`, `agents.py`"],
            ["backend/app/services/agents", "运行时、规划器、策略、工具、持久化、回放", "`runtime.py`, `policy.py`, `tools.py`"],
            ["backend/app/services/detection", "时序验证、跟踪、冷却窗口", "`detection/temporal.py`"],
            ["backend/app/services/dispatch", "PostGIS 邻近派单与业务打分", "`dispatch/spatial.py`"],
            ["backend/app/services/task", "任务状态机与非法迁移守卫", "`task/state_machine.py`"],
            ["ml", "检测器、训练/评估、ONNX 导出", "`detectors/`, `scripts/export_onnx.py`"],
            ["edge/grasp", "机械臂控制、标定、桥接、仿真与测试", "`grasp/deploy/`, `scripts/calib_point.py`"],
            ["frontend", "Vue 3 监测大屏、工单、控制台、报表", "`src/views/`, `src/components/`"],
            ["deploy", "Docker Compose、环境配置、生产编排", "`docker-compose.yml`, `deploy/`"],
            ["artifacts", "评测、验收、截图、联调报告", "`agent_evals/`, `agent-real-state-acceptance/`"],
        ],
        [4.2, 7.4, 5.95],
        font_size=7.9,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE, PALE, WHITE, PALE, WHITE, PALE],
    )
    add_callout(
        "代码阅读顺序",
        "先看 `runtime.py` 与 `tools.py` 理解治理内核，再看 `temporal.py` 与 `spatial.py` 理解业务闭环，最后用 artifacts 中的机器可读报告核对文档数字。",
        fill=PALE_BLUE,
        accent=TEAL,
    )

    # Page 20: Market and business value
    new_page()
    section_header("21", "方案价值：从一次性项目到可复制基础设施", "市场与用户")
    body(
        "目标市场不是泛化的“环保 AI”，而是具有明确责任主体、固定巡查半径和持续处置需求的近岸水域。"
        "优先切入养殖区、乡镇河道/岸滩、景区水域与港区，再向区域联网和标准化输出扩展。",
        size=9.1,
    )
    add_table(
        ["场景", "主要痛点", "首期可交付价值", "付费/运营逻辑"],
        [
            ["近岸养殖区", "漂浮物发现晚、人工巡塘成本高、责任分散", "监测 + 派单 + 执行记录 + 日报", "按点位订阅 + 边缘设备 + 运营服务"],
            ["乡镇岸滩/河道", "巡查范围广、误报多、考核缺证据", "时序降噪 + 工单 + 前后影像", "按乡镇/水域包年，叠加运维"],
            ["景区水域", "形象风险高、响应窗口短", "重点点位监测 + 快速派单 + 事件回放", "活动保障 + 年度运维"],
            ["港区/码头", "设备多、任务复杂、数据分散", "多设备接入 + 证据报表 + 权限审计", "平台授权 + 行业集成"],
        ],
        [3.4, 5.2, 5.3, 3.65],
        font_size=8.2,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE],
    )
    add_metric_cards(
        [
            ("4 类", "首批目标用户角色", TEAL, PALE_BLUE),
            ("3 层", "软件 / 边缘 / 运营收入", GREEN, "EAF7F1"),
            ("可复制", "点位 → 县域 → 区域", ORANGE, PALE_ORANGE),
        ]
    )
    body(
        "商业上不依赖一次性定制：平台负责统一的事件、智能体、证据与报表；边缘设备负责就地感知与执行；"
        "本地服务商负责安装、标定和运维。单点试运行后，复制成本主要来自设备与现场服务，而不是重写软件。",
        size=8.9,
    )
    add_callout(
        "商业验证边界",
        "当前尚无真实订单、回款或规模客户，商业验证尚未完成。现阶段可确认的能力来自治理契约、可审计运行轨迹与软硬件解耦。",
        fill=PALE_ORANGE,
        accent=ORANGE,
    )

    # Page 21: Social value and roadmap
    new_page()
    section_header("22", "社会价值与落地路径：先完成一个点位闭环", "价值实现")
    add_figure(assets["roadmap"], 17.1, "图 19  分阶段落地路径与退出条件", "自绘")
    body(
        "社会价值来自三个可验证方向：减少人工临水巡检暴露、减少无效出勤、把治理结果沉淀为可追溯的公共数据。"
        "对养殖户，重点是降低污染风险与巡塘负担；对乡镇，重点是把“有人发现”变成“有人负责、有人核实”；"
        "对监管，重点是统一口径而不是再增加一套孤立的报表。",
        size=9.1,
    )
    add_table(
        ["阶段", "核心目标", "必达验收", "停止条件"],
        [
            ["0-3 个月", "单点闭环", "真实点位连续运行；事件→工单→证据链路可用；机械臂抓取完成受控验证", "无现场准入或供电/标定无法稳定则暂停扩展"],
            ["3-6 个月", "县域复制", "2-3 个点位、多设备派单、运营手册与周报", "故障率或人工接管率超过约定阈值则回退单点"],
            ["6-12 个月", "区域协同", "跨点位数据共享、国产算力迁移、统一考核口径", "隐私、数据安全或运维成本不可接受则不联网"],
            ["12 个月+", "标准输出", "开放接口、设备生态与行业数据规范", "未形成可复制的运营与责任边界则不宣称规模化"],
        ],
        [2.5, 3.8, 7.3, 3.95],
        font_size=8.0,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE],
    )
    add_callout(
        "社会价值的可量化方向",
        "后续试点统一记录：无效出勤减少比例、单事件平均闭环时长、证据完整率、人工接管率、单位清理重量与设备可用率。没有基线和审计口径的“社会效益”不进入正式结论。",
        fill=CYAN,
        accent=TEAL,
    )

    # Page 22: Differentiation
    new_page()
    section_header("23", "差异化：不与通用模型比参数，而与治理系统比闭环", "竞争分析")
    body(
        "漂浮垃圾识别已有成熟模型，机器人控制也有成熟方案。Oceanus 的差异化不在单点指标绝对领先，"
        "而在于把感知、派单、审批、执行、证据和核算组合成一个可复用的治理系统，并明确每一层的可替换边界。",
        size=9.2,
    )
    add_table(
        ["方案形态", "能发现", "能派单", "能受控执行", "能审计/回放", "主要短板"],
        [
            ["人工巡查 + 微信群", "依赖人眼", "人工协调", "人工操作", "聊天记录分散", "覆盖有限、责任链不清"],
            ["通用视觉告警", "通常较强", "较弱", "通常无", "告警日志有限", "误报直接进入业务，缺少闭环"],
            ["通用机器人平台", "取决于外设", "可能有", "较强", "偏设备日志", "业务证据与治理口径弱"],
            ["Oceanus", "公开基准 + 时序收敛", "PostGIS + 多因子", "策略/审批/状态机", "Run/Step + 前后证据", "现场验证与自动抓取仍待补齐"],
        ],
        [3.8, 3.0, 2.7, 2.9, 2.8, 3.35],
        font_size=8.0,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE_BLUE],
    )
    add_callout(
        "系统组合",
        "系统通过事件证据化、决策可审计、执行受控和结果可核算形成连续治理链路，模型与设备均可在契约边界内替换。",
        fill=PALE_BLUE,
        accent=TEAL,
    )
    body("三个关键差异点", bold_lead="", size=9.2, color=TEAL_DARK)
    bullet("与普通告警系统的区别：每条事件进入任务、审批、执行和证据闭环，不停留在画面告警。", size=9.0)
    bullet("与通用智能体平台的区别：策略守卫、工具权限、幂等、回放和评测属于运行内核，而非外挂模块。", size=9.0)
    bullet("持续使用基础：模型和设备可替换，治理契约、任务记录与证据数据能够持续积累。", size=9.0)

    # Page 23: Risks and next milestones
    new_page()
    section_header("24", "风险收敛与下一步：每条限制都对应一个可验收动作", "路线与风险")
    body(
        "当前主要风险集中在现场感知、机械臂抓取、供电稳定、国产算力迁移和真实用户验证五个方面。"
        "每项风险均设置下一动作和可验收的完成标准。",
        size=9.0,
    )
    add_table(
        ["风险", "当前事实", "下一动作", "完成标准"],
        [
            ["现场域偏移", "公开基准三个区域差异明显；尚无连江现场数据", "采集 1 个养殖区连续两周图像，建立本地验证集", "形成按区域、光照、潮汐分层的本地报告"],
            ["自动抓取未完成", "室内 12/12 帧误锁夹爪；夹爪空手", "深色背景 + 4 点仿射标定 + 现场特化数据", "连续 20 次受控抓取，分别报告抓取与入仓成功"],
            ["板端供电不稳", "多次重启，疑似欠压", "更换 5V/3A 电源与粗线，增加电压监测", "连续 2 小时执行无重启，故障可告警"],
            ["昇腾未实测", "目前完成 ONNX 与多 provider 设计", "ATC 转 OM、CANN provider、目标硬件联调", "同一输入输出一致，时延与稳定性达标"],
            ["真实运营未验证", "无订单、无现场用户、无规模数据", "1 个乡镇/养殖区试点，签验收指标", "闭环时长、证据完整率与接管率达到约定阈值"],
        ],
        [3.0, 5.1, 5.2, 4.25],
        font_size=7.85,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE],
    )
    add_callout(
        "下一步 90 天",
        "完成一个真实点位的最小闭环：本地数据验证、事件→工单→证据全链路、机械臂受控抓取、一次断电/断网恢复演练。"
        "验收以现场记录、设备日志和可回放证据为准。",
        fill=CYAN,
        accent=TEAL,
    )
    body("5 分钟演示流程", bold_lead="", size=9.2, color=TEAL_DARK)
    add_table(
        ["时间", "演示动作", "操作内容", "屏幕上可核对的证据"],
        [
            ["0:00-0:45", "事件入站", "注入一张水面垃圾图或模拟事件", "事件号、时空信息、置信度与去重结果"],
            ["0:45-1:45", "验证与派单", "展示连续命中、冷却窗口与候选设备评分", "为何派、派给谁、优先级依据"],
            ["1:45-3:15", "审批与执行", "切换角色触发写操作审批，再下发仿真任务", "审批人/理由、状态机、ACK、进度与遥测"],
            ["3:15-5:00", "故障与回放", "注入模型不可用或工具超时，打开证据台账与轨迹回放", "安全终止、错误码、回放一致与证据边界"],
        ],
        [2.3, 3.2, 6.2, 5.85],
        font_size=7.7,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE],
    )

    # Page 24: Evidence index / closing
    new_page()
    section_header("25", "证据索引：实现、测试与联调记录", "附录")
    body(
        "实现、测试与联调记录可按下列路径查阅；路径相对于项目根目录。",
        size=9.0,
    )
    add_table(
        ["证据类别", "项目内位置", "用途"],
        [
            ["系统设计与源码", "`backend/`, `ml/`, `edge/`, `frontend/`, `deploy/`", "架构、模块、接口、数据结构、部署与执行端实现"],
            ["智能体评测", "`artifacts/agent_evals/latest_v2.json`", "27 个固定场景、指标定义、分母与环境限制"],
            ["集成验收", "`artifacts/agent-real-state-acceptance/latest.json`", "129 项 HTTP + DB + 审批 + 幂等 + 回放检查"],
            ["机械臂联调", "`项目文档/探海灵眸_机械臂_联调存档_20261017.md`", "已验证链路、未完成抓取、供电/标定缺陷与复现步骤"],
            ["平台截图", "`artifacts/ui-responsive/`, `artifacts/agent-console/`", "大屏、工单、控制台、Run 步骤与审批界面"],
            ["检测示例", "项目辅助材料 `04_检测效果图/`", "水面与岸滩多目标检测输出形态"],
        ],
        [3.2, 8.6, 5.75],
        font_size=8.2,
        first_col_bold=True,
        row_fills=[WHITE, PALE, WHITE, PALE, WHITE, PALE],
    )
    add_callout(
        "结论",
        "Oceanus 通过统一治理契约连接感知、决策、执行与核算。下一步需要在一个真实点位完成可重复、可审计、可核算的闭环。",
        fill=PALE_BLUE,
        accent=TEAL,
    )
    body("作品关键词", bold_lead="", size=9.0, color=TEAL_DARK)
    add_pill_row(
        [
            ("可审计", TEAL),
            ("人在回路", ORANGE),
            ("证据优先", GREEN),
            ("软硬解耦", "6D45B8"),
            ("可复制", TEAL_DARK),
        ]
    )
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(18)
    r = p.add_run("探海灵眸 Oceanus")
    r.bold = True
    r.font.name = FONT_EN
    r.font.size = Pt(17)
    r.font.color.rgb = RGBColor.from_string(NAVY)
    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run("看得见 · 想得清 · 管得住 · 查得到")
    r2.font.name = FONT_CN
    r2.font.size = Pt(10)
    r2.font.color.rgb = RGBColor.from_string(MID)

    # Remove accidental empty end paragraph if any
    doc.save(DOCX_PATH)
    print(f"DOCX={DOCX_PATH}")


if __name__ == "__main__":
    build_doc()
