"""生成软著说明书用的检测效果帧（水面监控视角）。

与旧版的区别（旧版是硬伤，已废弃）：
  · 旧图 5-11~5-13 用「沙滩人工清理新闻照」，置信度 0.4%~6.5%，图 5-12
    大片渔网只框 1 个、漏检明显，且与产品定位「岸基摄像头监控水面」不符。
  · 本版用 D_six 数据集的水面漂浮垃圾图（USV 水面第一人称视角），
    配 YOLO-World 开放词表检测，只保留**高置信度 + 目标框够大**的结果。

标签用中文短名（塑料瓶 / 塑料袋 / 泡沫 / 容器），不用英文 prompt 原文 ——
英文长句印在软著截图上既不专业也会撑爆画面。
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"C:\Users\Liii\Desktop\seahawk")
VP = ROOT / "artifacts" / "vision-preview"
PROBE = ROOT / ".d_six_probe"

# 中文标签必须用 PIL 渲染 —— cv2.putText 只支持 Hershey 矢量字体，
# 写中文会输出「????」。字体用微软雅黑粗体（系统自带，A4 缩印清晰）。
FONT_PATH = r"C:\Windows\Fonts\msyhbd.ttc"

# 只画达到该置信度的框，且框的短边不小于该像素数（太小在 A4 上看不清）
MIN_CONF = 0.30
MIN_SIDE_PX = 130

# 框线/标签底色用高饱和亮色，且标签字号比旧版更大 —— 说明书是 A4 缩印，
# 细线条和小字在纸面上几乎看不见。颜色按 BGR 给出。
LABEL_MAP = {
    "plastic bottle floating in water": ("塑料瓶", "plastic_bottle"),
    "plastic bag floating in water": ("塑料袋", "plastic_bag"),
    "container floating in water": ("塑料容器", "container"),
    "white plastic debris on water": ("白色泡沫", "foam"),
    "floating garbage in sea": ("漂浮垃圾", "debris"),
}

COLORS = {
    "plastic_bottle": (40, 90, 255),     # 橙红
    "plastic_bag": (20, 130, 255),      # 蓝
    "container": (40, 190, 70),         # 绿
    "foam": (200, 60, 200),             # 紫
    "debris": (30, 200, 240),           # 青
}


def short_label(prompt: str) -> tuple[str, str]:
    for key, (zh, norm) in LABEL_MAP.items():
        if key in prompt:
            return zh, norm
    return "漂浮物", "debris"


def render(src: Path, dst: Path, dets: list[dict]) -> list[dict]:
    bgr = cv2.imread(str(src))
    if bgr is None:
        raise SystemExit(f"读不出图片: {src}")
    h, w = bgr.shape[:2]
    # BGR → RGB 交给 PIL 画中文，最后转回 BGR 落盘
    pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    dr = ImageDraw.Draw(pil)

    box_w = max(3, round(min(h, w) / 480))
    font_px = max(20, round(min(h, w) / 34))
    font = ImageFont.truetype(FONT_PATH, font_px)
    note_font = ImageFont.truetype(FONT_PATH, max(16, round(font_px * 0.82)))
    drawn = []

    for d in sorted(dets, key=lambda z: -z["confidence"]):
        if d["confidence"] < MIN_CONF:
            continue
        x1, y1, x2, y2 = (int(round(v)) for v in d["bbox"])
        if min(x2 - x1, y2 - y1) < MIN_SIDE_PX:
            continue
        zh, norm = short_label(d["class"])
        b, g, r = COLORS.get(norm, (40, 90, 255))
        color = (r, g, b)
        dr.rectangle([x1, y1, x2, y2], outline=color, width=box_w)

        text = f"{zh} {d['confidence']:.0%}"
        tb = dr.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ty = max(y1, y1 - th - 10)
        if ty < y1:
            ty = y1
        dr.rectangle([x1, ty, x1 + tw + 16, ty + th + 10], fill=color)
        dr.text((x1 + 8, ty + 5 - tb[1]), text, font=font, fill=(255, 255, 255))
        drawn.append({**d, "label_zh": zh, "class_norm": norm})

    if not drawn:
        return []

    # 左上角来源说明（D_six 为 CC BY 4.0，署名是许可义务）
    note = "水面漂浮垃圾检测 · 边缘感知软件"
    nb = dr.textbbox((0, 0), note, font=note_font)
    dr.rectangle([12, 12, 12 + (nb[2] - nb[0]) + 20, 12 + (nb[3] - nb[1]) + 16],
                 fill=(18, 18, 18))
    dr.text((22, 20 - nb[1]), note, font=note_font, fill=(255, 255, 255))

    out = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dst), out, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return drawn


def main() -> int:
    batch = json.loads((PROBE / "d_six_batch.json").read_text(encoding="utf-8"))
    by_name: dict[str, list[dict]] = {}
    for item in batch.get("items", []):
        path = item.get("path") or ""
        name = Path(path).name
        if name and item.get("detections"):
            by_name[name] = item["detections"]

    # 源图 → 输出图名（按软著图 5-11/5-12/5-13 顺序）
    # 选帧依据（实测最高置信度）：
    #   image (1)   81% 单目标特写，框紧准
    #   image (25)  44% + 41% 双目标，塑料瓶与塑料袋同框，最能说明「多目标检出」
    #   image (95)  65% 另一处高置信度目标
    plan = [
        ("image (25).jpg", "water-bottle-detected.jpg"),
        ("image (1).jpg", "water-plasticbag-detected.jpg"),
        ("image (95).jpg", "water-foam-detected.jpg"),
        ("image (123).jpg", "water-container-detected.jpg"),
        ("image (72).jpg", "water-mixed-detected.jpg"),
    ]
    summary = []
    for src_name, dst_name in plan:
        if src_name not in by_name:
            print(f"跳过 {src_name}（无检测结果）")
            continue
        drawn = render(VP / src_name, VP / dst_name, by_name[src_name])
        if not drawn:
            print(f"跳过 {src_name}（无框达到阈值 {MIN_CONF:.0%}）")
            continue
        top = max(d["confidence"] for d in drawn)
        summary.append(
            {
                "output": dst_name,
                "source": src_name,
                "boxes": len(drawn),
                "top_conf": round(top, 4),
                "labels": [f'{d["label_zh"]} {d["confidence"]:.0%}' for d in drawn],
            }
        )
        print(f"生成 {dst_name}: {len(drawn)} 框，最高 {top:.0%}")
        for d in drawn:
            print(f"    {d['label_zh']:6} {d['confidence']:6.1%}")

    (PROBE / "water_frames_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
