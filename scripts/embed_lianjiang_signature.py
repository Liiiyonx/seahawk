# -*- coding: utf-8 -*-
r"""处理手写签名照片 → 透明底电子签 PNG → 嵌入《情况说明》并重出 PDF。

用法：python scripts\embed_lianjiang_signature.py
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
from docx import Document
from docx.shared import Pt
from PIL import Image, ImageFilter

SRC = Path(r"c:\Users\Liii\.trae-cn\attachments\6ac9d744f7615d7951be5ad4\cebbdfb8-ffba-4a07-b324-b67785e09f13_2eb4e266-bb9a-4d01-8380-6950b67c4dd9_122e4f1b6d40cf4e782284634705b029.jpg")
OUT_PNG = Path(r"C:\Users\Liii\Desktop\连江县创新创业大赛\证明材料\电子签名_李涌翔.png")
DOCX = Path(r"C:\Users\Liii\Desktop\连江县创新创业大赛\证明材料\情况说明_未设经营实体无出资_李涌翔.docx")


def fill_closed_holes(img: Image.Image, low_thr: int = 100, max_area: int = 120) -> Image.Image:
    """BFS 填「封闭小孔」：与图像边界不连通的低值小区域（面积 < max_area）填实。
    字内大留白（面积大）与所有外部边缘过渡区不受影响——零副作用。"""
    a = np.asarray(img, dtype=np.uint8)
    low = a < low_thr
    h, w = low.shape
    visited = np.zeros((h, w), bool)
    dq: deque = deque()
    for x in range(w):  # 种子：四边界低值像素（外部背景）
        for y in (0, h - 1):
            if low[y, x] and not visited[y, x]:
                visited[y, x] = True
                dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if low[y, x] and not visited[y, x]:
                visited[y, x] = True
                dq.append((y, x))
    while dq:  # 4连通泛洪标记外部
        y, x = dq.popleft()
        if y > 0 and low[y-1, x] and not visited[y-1, x]:
            visited[y-1, x] = True; dq.append((y-1, x))
        if y < h-1 and low[y+1, x] and not visited[y+1, x]:
            visited[y+1, x] = True; dq.append((y+1, x))
        if x > 0 and low[y, x-1] and not visited[y, x-1]:
            visited[y, x-1] = True; dq.append((y, x-1))
        if x < w-1 and low[y, x+1] and not visited[y, x+1]:
            visited[y, x+1] = True; dq.append((y, x+1))
    hole = np.zeros((h, w), bool)  # 剩余低值连通块 → 按面积筛选
    for y in range(h):
        for x in range(w):
            if low[y, x] and not visited[y, x]:
                comp = []
                dq.append((y, x)); visited[y, x] = True
                while dq:
                    cy, cx = dq.popleft()
                    comp.append((cy, cx))
                    for ny, nx in ((cy-1, cx), (cy+1, cx), (cy, cx-1), (cy, cx+1)):
                        if 0 <= ny < h and 0 <= nx < w and low[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True; dq.append((ny, nx))
                if len(comp) < max_area:
                    for cy, cx in comp:
                        hole[cy, cx] = True
    hole_d = np.asarray(Image.fromarray(hole.astype(np.uint8) * 255, "L")
                        .filter(ImageFilter.MaxFilter(3)), dtype=float)  # 扩1px贴边
    return Image.fromarray(np.maximum(a.astype(float), hole_d).astype(np.uint8), "L")


def extract_signature() -> None:
    im = Image.open(SRC).convert("L")
    # 局部背景估计（大核中值）：用「背景亮度 - 像素亮度」提取墨迹，
    # 自动消除纸张光影渐变。实测纸张噪声 diff≤6，细笔画中心 diff≥15
    bg = im.filter(ImageFilter.MedianFilter(size=51))
    arr = np.asarray(im, dtype=float)
    bg_arr = np.asarray(bg, dtype=float)
    diff = np.clip(bg_arr - arr, 0.0, None)
    # 陡峭映射（10..25）：噪声(<10)全排除，细笔画快速饱和为实心黑
    alpha = np.clip((diff - 10.0) / 15.0 * 255.0, 0.0, 255.0)
    a_img = Image.fromarray(alpha.astype(np.uint8), "L")

    # 密度过滤：清 502 个孤立散点（照片墨点/边缘伪影），笔画区密度远高于阈值
    density = np.asarray(a_img.filter(ImageFilter.BoxBlur(41)), dtype=float)
    a_img = Image.fromarray((alpha * (density >= 6)).astype(np.uint8), "L")

    # BFS 精准填封闭小孔（零副作用），再 3px 闭(填针孔)→开(去毛刺)
    a_img = fill_closed_holes(a_img)
    a_img = a_img.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    a_img = a_img.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    a2 = np.asarray(a_img, dtype=float)

    ys, xs = np.where(a2 > 40)
    assert len(xs), "未找到墨迹"
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    print(f"    定位: x {x0}-{x1}, y {y0}-{y1}")

    pad = 26
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(im.width - 1, x1 + pad), min(im.height - 1, y1 + pad)

    alpha_c = a2[y0:y1 + 1, x0:x1 + 1]
    rgba = np.zeros((*alpha_c.shape, 4), dtype=np.uint8)
    rgba[..., 3] = alpha_c.astype(np.uint8)
    out = Image.fromarray(rgba, "RGBA")

    # 控制尺寸（宽 ≤ 1000）
    if out.width > 1000:
        ratio = 1000 / out.width
        out = out.resize((1000, int(out.height * ratio)), Image.LANCZOS)
    out.save(OUT_PNG)
    print("[OK] 签名抠图:", OUT_PNG.name, out.size)

    # 预览（白底黑字：全幅 + 右侧局部放大）
    fa = np.asarray(out)[..., 3].astype(float) / 255.0
    h, w = fa.shape
    full = Image.fromarray((np.ones((h, w, 3)) * 255.0 * (1 - fa[..., None])).astype(np.uint8))
    sub = full.crop((int(w * 0.38), 0, w, h))
    sub = sub.resize((int(sub.width * 1.5), int(sub.height * 1.5)), Image.LANCZOS)
    gap = 14
    W = max(full.width, sub.width) + 2 * gap
    H = full.height + sub.height + 3 * gap
    sheet = Image.new("RGB", (W, H), (180, 180, 180))
    sheet.paste(full, ((W - full.width) // 2, gap))
    sheet.paste(sub, ((W - sub.width) // 2, full.height + 2 * gap))
    sheet.save(r"C:\Users\Liii\AppData\Local\Temp\sig_preview_final.png")
    print("preview saved:", sheet.size)


def embed_into_docx() -> None:
    doc = Document(DOCX)
    target = None
    for p in doc.paragraphs:
        if p.text.strip().startswith("申报人（签字）"):
            target = p
            break
    assert target is not None, "未找到签字行"

    runs = target.runs
    assert runs, "签字行为空"
    runs[0].text = "申报人（签字）："
    for r in list(runs[1:]):
        r._element.getparent().remove(r._element)

    run = target.add_run()
    run.add_picture(str(OUT_PNG), height=Pt(40))
    doc.save(DOCX)
    print("[OK] 已嵌入签名:", DOCX.name)


def main() -> None:
    extract_signature()
    embed_into_docx()


if __name__ == "__main__":
    main()