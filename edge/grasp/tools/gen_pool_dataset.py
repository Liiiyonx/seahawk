#!/usr/bin/env python3
"""合成「充气泳池」域数据集生成工具：产出一批「帧 + 精确真值」的 YOLO 数据集。

## 为什么单独做「泳池域」

真机在室内房间抓取失败的根因是**感知域外**：现网模型（v20261015_190359）是在
「合成海面 + 真实水面」域上微调的，进了室内后把臂体、线缆当成了塑料袋
（conf 0.85，全场最高，且随臂同步移动 → 视觉伺服永远收敛不了）。

实际演示场景是**充气泳池水面拾取白色半透明塑料袋**。泳池水面的视觉特征与
「海面域」差得很远：水色是明亮青蓝、有池底透射斑纹、池壁是彩色充气圈、
水面有折光网纹。所以需要一批近似该域的训练帧。

## 边界（务必先读）

与 ``gen_synthetic_dataset.py`` 同一口径：这些帧是**合成渲染**，证据等级上限
**E1/E2**；它们在泳池域内的指标**不代表现场精度**，也不能替代现场采集。
真机 + 泳池到位后必须按《探海灵眸_充气泳池采集规程》采集真实帧再微调一次。

## 视觉配方（目标是覆盖真实泳池的视觉多样性，而不是画得好看）

* 水色：明亮青蓝，亮度/色相/曝光随机；池底透射低频斑纹
* 水面：折光网纹（caustics）+ 波纹亮度调制 + 镜面高光条 + 少量低饱和亮斑
  —— 后两者**不标注**，它们是「低饱和亮团」的真实误检来源，必须让模型学会区分
* 池壁：画面边缘的彩色充气圈（多色、充气分段棱、管状高光），内侧带水面倒影
* 塑料袋（标注 ``plastic_bag``）：白色/半透明，四种形态（皱团 / 长条薄膜 /
  扁平贴水 / 揉搓团），半透明混合（水色透过来）、褶皱明暗、边缘细高光
* 负样本（**不标注**，只为让模型学会「这些不是袋子」，直击现场失败点）：
  臂体/夹持器外壳（深灰哑光 + 金属高光）、线缆（深色蜿蜒曲线）、手（肤色团块）
  —— 三者只出现在画面**边缘带**，与中央目标区互不重叠，保证真值框只对应可见
  目标、不引入脏标注
* 彩色浮标（标注 ``buoy``）：泳池彩色玩具/浮圈，作为显式负类来源，维持与部署
  模型一致的两类头

用法::

    python edge/grasp/tools/gen_pool_dataset.py --count 400 --tag pool_synth --build
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRASP_DIR = HERE.parent
EDGE_DIR = GRASP_DIR.parent
for path in (str(EDGE_DIR), str(GRASP_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from grasp.config import load_config  # noqa: E402
from grasp.vision.dataset import Box, Dataset  # noqa: E402

BAG_CLASS = "plastic_bag"
BUOY_CLASS = "buoy"

FRAME_W, FRAME_H = 640, 480
MARGIN = 10                 # 目标必须离画面边缘至少这么多像素
BORDER_FRAC = 0.17          # 负样本（臂/手/线缆）只允许在这么宽的边缘带内
CENTER_INSET = 0.20         # 目标（袋/浮标）只允许在中央这块区域内
                            # 两个区间互补 ⇒ 负样本与目标物理上不重叠

#: 充气圈配色池（BGR）—— 蓝 / 白 / 粉 / 黄 / 绿，覆盖市面常见泳池
POOL_RING_COLORS = [
    (238, 130, 62), (212, 208, 200), (168, 92, 228), (96, 198, 242), (124, 214, 152),
]

#: 浮标配色池（BGR，高饱和）
BUOY_COLORS = [
    (0, 0, 235), (235, 80, 0), (0, 205, 255), (0, 180, 0), (200, 0, 200), (30, 30, 240),
]

#: 塑料形态池：(名称, 顶点数区间, 半径抖动, 宽高比区间)
BAG_FORMS = [
    ("crumpled", (10, 15), (0.10, 0.16), (1.3, 2.2)),
    ("film", (8, 12), (0.08, 0.12), (2.6, 4.4)),
    ("flat", (12, 17), (0.06, 0.10), (1.8, 3.0)),
    ("wadded", (6, 9), (0.18, 0.26), (1.0, 1.7)),
]


# ----------------------------------------------------------------------
# 水面
# ----------------------------------------------------------------------
def _pool_water(rng: np.random.Generator) -> np.ndarray:
    """明亮青蓝的池水：色相/曝光随机 + 池底透射 + 折光网纹 + 高光。"""
    ys, xs = np.mgrid[0:FRAME_H, 0:FRAME_W].astype(np.float32)

    # 基础水色：B 高 / G 中高 / R 低（青蓝），整体亮度随机
    lum = rng.uniform(138.0, 202.0)
    b_k = lum * rng.uniform(0.96, 1.14)
    g_k = lum * rng.uniform(0.78, 0.98)
    r_k = lum * rng.uniform(0.42, 0.66)
    img = np.empty((FRAME_H, FRAME_W, 3), dtype=np.float32)
    img[..., 0] = b_k
    img[..., 1] = g_k
    img[..., 2] = r_k

    # 纵向亮度趋势（远亮近暗，或反之），模拟池深变化
    g = np.linspace(rng.uniform(0.98, 1.10), rng.uniform(0.82, 0.96), FRAME_H)
    img *= g.reshape(-1, 1, 1)

    # 池底透射：大尺度低频斑纹（池底印花/深浅），只在低频上加，不制造纹理噪点
    low = rng.normal(0.0, 20.0, (FRAME_H, FRAME_W)).astype(np.float32)
    low = cv2.GaussianBlur(low, (0, 0), rng.uniform(22.0, 40.0))
    img += low[..., None]

    # 折光网纹（caustics）：先做低频域扭曲，再叠两组正弦。
    # ★ 纯正弦会形成规整点阵 —— 那是真实泳池里不存在的强纹理捷径，模型会学它
    #   而不是学袋子。先用低频噪声把坐标场揉皱，正弦的周期就被打散成大小不一的
    #   折光格子，接近真实水面的网状亮线。
    lx1 = rng.uniform(46.0, 120.0)
    ly1 = rng.uniform(38.0, 96.0)
    lx2 = rng.uniform(52.0, 132.0)
    ly2 = rng.uniform(42.0, 104.0)
    warp = cv2.GaussianBlur(rng.normal(0.0, 1.0, (FRAME_H, FRAME_W)).astype(np.float32),
                            (0, 0), rng.uniform(24.0, 46.0))
    warp *= rng.uniform(10.0, 28.0)
    xw = xs + warp
    yw = ys + np.roll(warp, 13, axis=1)
    c1 = np.sin(2 * np.pi * (xw / lx1 + yw / ly1) + rng.uniform(0, 6.28))
    c2 = np.sin(2 * np.pi * (xw / lx2 - yw / ly2) + rng.uniform(0, 6.28))
    net = (c1 + c2) * 0.5
    bright = np.clip((net - rng.uniform(0.32, 0.58)) / 0.55, 0.0, 1.0)
    # 不同通道给不同强度 → 折光稍偏暖/偏冷，避免模型退化到"单通道阈值"
    img[..., 0] += bright * rng.uniform(14.0, 34.0)
    img[..., 1] += bright * rng.uniform(16.0, 38.0)
    img[..., 2] += bright * rng.uniform(10.0, 28.0)

    # 波纹亮度调制：让水面不平（局部明暗带）
    lam = rng.uniform(44.0, 116.0)
    ang = rng.uniform(0.0, np.pi)
    proj = xs * np.cos(ang) + ys * np.sin(ang)
    rip = np.sin(2 * np.pi * proj / lam + rng.uniform(0, 6.28))
    img += (rip * rng.uniform(4.0, 13.0))[..., None]

    # 镜面高光条（水平软亮带）
    for _ in range(int(rng.integers(0, 4))):
        y = int(rng.integers(0, FRAME_H))
        sig = rng.uniform(2.0, 9.0)
        amp = rng.uniform(16.0, 58.0)
        band = np.exp(-((np.arange(FRAME_H) - y) ** 2) / (2 * sig * sig))
        img += (band * amp).reshape(-1, 1, 1)

    # 少量低饱和亮斑（水面镜面反射团）—— 真实的「像袋子」误检来源，不标注
    for _ in range(int(rng.integers(0, 3))):
        cx, cy = int(rng.integers(BORDER_FRAC * FRAME_W, (1 - BORDER_FRAC) * FRAME_W)), \
            int(rng.integers(BORDER_FRAC * FRAME_H, (1 - BORDER_FRAC) * FRAME_H))
        ax, ay = int(rng.integers(14, 42)), int(rng.integers(8, 22))
        blob = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
        cv2.ellipse(blob, (cx, cy), (ax, ay), float(rng.uniform(-30, 30)), 0, 360, 1.0, -1)
        blob = cv2.GaussianBlur(blob, (0, 0), rng.uniform(3.0, 9.0))
        img += (blob * rng.uniform(18.0, 46.0))[..., None]

    return img


# ----------------------------------------------------------------------
# 池壁（充气圈）
# ----------------------------------------------------------------------
def _draw_band(img: np.ndarray, side: str, rng: np.random.Generator) -> None:
    """在画面某一边画一段充气圈（带管状明暗 + 分段棱 + 高光 + 内侧倒影）。"""
    along = np.arange(FRAME_W if side in ("top", "bottom") else FRAME_H, dtype=np.float32)
    span = FRAME_H if side in ("top", "bottom") else FRAME_W
    seg = rng.uniform(72.0, 138.0)
    wave = np.sin(2 * np.pi * along / seg + rng.uniform(0, 6.28)) * rng.uniform(3.0, 12.0)
    t = rng.uniform(0.09, 0.19) * span
    inner = t + wave

    if side in ("top", "bottom"):
        d = np.arange(FRAME_H, dtype=np.float32).reshape(-1, 1) * np.ones((1, FRAME_W))
        if side == "bottom":
            d = (FRAME_H - 1) - d
        inner2d = inner.reshape(1, -1)
    else:
        d = np.ones((FRAME_H, 1)) * np.arange(FRAME_W, dtype=np.float32).reshape(1, -1)
        if side == "right":
            d = (FRAME_W - 1) - d
        inner2d = inner.reshape(-1, 1)

    mask = (d < inner2d).astype(np.float32)
    soft = cv2.GaussianBlur(mask, (0, 0), 1.4)

    # 管状明暗：带内「两边暗、中间亮」，读起来像充气管
    prof = np.clip(d / np.maximum(inner2d, 1.0), 0.0, 1.0)
    tube = 0.74 + 0.44 * np.sin(np.pi * prof)

    color = np.array(POOL_RING_COLORS[int(rng.integers(0, len(POOL_RING_COLORS)))], dtype=np.float32)
    color = color * rng.uniform(0.88, 1.10)
    layer = color.reshape(1, 1, 3) * tube[..., None]

    a = (soft * rng.uniform(0.90, 0.99))[..., None]
    img *= (1.0 - a)
    img += layer * a

    # 分段充气棱（暗缝）+ 高光脊线，都裁在带内
    rib = ((along % seg) < 2.2).astype(np.float32)
    rib2d = rib.reshape(1, -1) if side in ("top", "bottom") else rib.reshape(-1, 1)
    img -= (rib2d * soft * rng.uniform(18.0, 42.0))[..., None]

    ridge = np.exp(-((prof - rng.uniform(0.28, 0.42)) ** 2) / (2 * 0.05 ** 2)) * soft
    img += (ridge * rng.uniform(24.0, 62.0))[..., None]

    # 内侧倒影：带彩色随距离衰减的软渐变（近似水面倒映充气圈）
    refl = np.clip((d - inner2d) / np.maximum(inner2d, 1.0) * 1.25, 0.0, 1.0)
    refl = (1.0 - refl) * np.clip((d - inner2d) >= 0, 0, 1)
    refl = cv2.GaussianBlur(refl.astype(np.float32), (0, 0), 4.0)
    img += (refl * rng.uniform(10.0, 26.0))[..., None] * color.reshape(1, 1, 3) / 255.0


def _pool_ring(rng: np.random.Generator, img: np.ndarray) -> None:
    """画池壁：默认远端（上边）必有，近端/左右随机（俯视机位下常见远景壁）。"""
    sides = ["top"]
    if rng.random() < 0.45:
        sides.append("bottom")
    if rng.random() < 0.35:
        sides.append("left")
    if rng.random() < 0.35:
        sides.append("right")
    for side in sides:
        _draw_band(img, side, rng)


# ----------------------------------------------------------------------
# 负样本（臂 / 手 / 线缆）—— 全部落在边缘带，且不写标注
# ----------------------------------------------------------------------
def _edge_anchor(side: str, rng: np.random.Generator, half: int) -> tuple[int, int]:
    """在指定边缘带内取一个落点，返回 (cx, cy)。

    落点偏外但不完全贴边：俯视机位下臂体/手是从画面外沿伸进来的。
    具体占位尺寸由各绘制函数自己算并把**真实**外接矩形登记进 ``rects``，
    这样目标避让用的是实际占位，不会因为用保守方框而过度挤压目标分布。
    """
    band = int(BORDER_FRAC * (FRAME_H if side in ("top", "bottom") else FRAME_W))
    reach = band + rng.uniform(2.0, 18.0)
    if side in ("top", "bottom"):
        cy = int(reach * 0.55) if side == "top" else int(FRAME_H - reach * 0.55)
        cx = int(rng.integers(half + MARGIN, FRAME_W - half - MARGIN))
    else:
        cx = int(reach * 0.55) if side == "left" else int(FRAME_W - reach * 0.55)
        cy = int(rng.integers(half + MARGIN, FRAME_H - half - MARGIN))
    return cx, cy


def _draw_arm(rng: np.random.Generator, img: np.ndarray, rects: list[tuple[int, int, int, int]]) -> None:
    """臂体/夹持器外壳入画：深灰哑光 + 金属高光条 + 从臂体甩出的线缆。"""
    side = str(rng.choice(["bottom", "bottom", "left", "right", "top"]))
    half = int(rng.integers(46, 96))
    cx, cy = _edge_anchor(side, rng, half)

    w = int(rng.integers(half, half * 2))
    h = int(rng.integers(max(34, half // 2), half + 34))
    k = int(rng.integers(10, 22))
    rx1, ry1 = cx - w // 2 - k, cy - h // 2 - k
    rx2, ry2 = cx + w // 2 + k, cy + h // 2 + k

    # 主体：深灰哑光圆角块（先画矩形再对角补圆，避免引 cv2 圆角 API）
    base = rng.uniform(38.0, 74.0)
    layer = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.float32)
    cv2.rectangle(layer, (cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2),
                  (base * 1.02, base, base * 0.96), -1)
    for dx in (-1, 1):
        for dy in (-1, 1):
            cv2.circle(layer, (cx + dx * w // 2, cy + dy * h // 2), k,
                       (base * 1.02, base, base * 0.96), -1)

    m = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
    cv2.rectangle(m, (cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2), 1.0, -1)
    m = cv2.GaussianBlur(m, (0, 0), 1.6)

    img *= (1.0 - m[..., None])
    img += layer * m[..., None]

    # 金属高光条（臂体外壳上的长条反光）
    gl = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
    gx1 = cx - w // 2 + int(w * rng.uniform(0.12, 0.28))
    gx2 = cx + w // 2 - int(w * rng.uniform(0.12, 0.28))
    gy = cy + int(h * rng.uniform(-0.28, 0.10))
    cv2.line(gl, (gx1, gy), (gx2, gy), 1.0, max(2, h // 14))
    gl = cv2.GaussianBlur(gl, (0, 0), 2.0) * m
    img += (gl * rng.uniform(60.0, 120.0))[..., None]

    # 线缆：从臂体边缘甩出的一条深色蜿蜒曲线（含细高光）。
    # 随机游走限制在锚点附近的小方框里 —— 线缆是细长物体，若任其漫游到画面
    # 中央，它就会从目标下方穿过，真值框里混入非目标像素（脏标注）。收在
    # 锚点附近既符合"线缆贴着臂体"的物理事实，也保证目标避让框够准。
    walk = 78
    for _ in range(int(rng.integers(1, 3))):
        p = (int(cx + rng.uniform(-w / 2, w / 2)), int(cy + rng.uniform(-h / 2, h / 2)))
        pts = [p]
        for _step in range(int(rng.integers(3, 6))):
            p2 = (int(np.clip(p[0] + rng.uniform(-walk, walk), 0, FRAME_W - 1)),
                  int(np.clip(p[1] + rng.uniform(-walk, walk), 0, FRAME_H - 1)))
            pts.append(p2)
            p = p2
        rx1, ry1 = min(rx1, min(q[0] for q in pts)), min(ry1, min(q[1] for q in pts))
        rx2, ry2 = max(rx2, max(q[0] for q in pts)), max(ry2, max(q[1] for q in pts))
        cl = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
        cv2.polylines(cl, [np.array(pts, dtype=np.int32)], False, 1.0,
                      int(rng.integers(3, 7)), cv2.LINE_AA)
        cl = cv2.GaussianBlur(cl, (0, 0), 0.9)
        dark = rng.uniform(22.0, 52.0)
        img -= (cl * dark)[..., None]
        img += (cv2.GaussianBlur(cl, (0, 0), 2.4) * rng.uniform(10.0, 30.0))[..., None]

    rects.append((int(rx1), int(ry1), int(rx2), int(ry2)))


def _draw_hand(rng: np.random.Generator, img: np.ndarray, rects: list[tuple[int, int, int, int]]) -> None:
    """手入画：肤色团块 + 指节凸起（不标注）。"""
    side = str(rng.choice(["top", "bottom", "left", "right"]))
    half = int(rng.integers(34, 62))
    cx, cy = _edge_anchor(side, rng, half)

    skin = np.array([rng.uniform(110.0, 150.0), rng.uniform(150.0, 185.0),
                     rng.uniform(190.0, 225.0)], dtype=np.float32)   # BGR 偏暖
    layer = np.zeros((FRAME_H, FRAME_W, 3), dtype=np.float32)
    m = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
    ax = int(rng.integers(half, half * 2))
    ay = int(rng.integers(half, int(half * 1.6)))
    ang = float(rng.uniform(0, 360))
    cv2.ellipse(m, (cx, cy), (ax, ay), ang, 0, 360, 1.0, -1)
    for _ in range(int(rng.integers(2, 5))):        # 指节/指头凸起
        fx = int(cx + rng.uniform(-ax, ax))
        fy = int(cy + rng.uniform(-ay, ay))
        cv2.circle(m, (fx, fy), int(rng.integers(8, half // 2 + 4)), 1.0, -1)
    m = cv2.GaussianBlur(m, (0, 0), 2.4)

    layer[:] = skin
    # 手指遮挡造成的手背阴影
    shadow = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
    cv2.ellipse(shadow, (cx + int(ax * 0.35), cy + int(ay * 0.35)),
                (int(ax * 0.8), int(ay * 0.8)), ang, 0, 360, 1.0, -1)
    shadow = cv2.GaussianBlur(shadow, (0, 0), 3.0) * m
    layer *= (1.0 - shadow * 0.35)[..., None]

    img *= (1.0 - m[..., None])
    img += layer * m[..., None]

    pad = int(half // 2 + 8)          # 覆盖指头凸起 + 模糊外扩
    rects.append((cx - ax - pad, cy - ay - pad, cx + ax + pad, cy + ay + pad))


def _draw_negatives(rng: np.random.Generator, img: np.ndarray) -> list[tuple[int, int, int, int]]:
    rects: list[tuple[int, int, int, int]] = []
    if rng.random() < 0.80:          # 臂体/线缆：现场失败的主因，出现率给高
        _draw_arm(rng, img, rects)
    if rng.random() < 0.30:
        _draw_hand(rng, img, rects)
    return rects


# ----------------------------------------------------------------------
# 目标
# ----------------------------------------------------------------------
def _center_anchor(rng: np.random.Generator, w: int, h: int) -> tuple[int, int]:
    x_lo = int(CENTER_INSET * FRAME_W) + w // 2 + MARGIN
    x_hi = int((1 - CENTER_INSET) * FRAME_W) - w // 2 - MARGIN
    y_lo = int(CENTER_INSET * FRAME_H) + h // 2 + MARGIN
    y_hi = int((1 - CENTER_INSET) * FRAME_H) - h // 2 - MARGIN
    cx = int(rng.integers(min(x_lo, x_hi), max(x_lo + 1, x_hi)))
    cy = int(rng.integers(min(y_lo, y_hi), max(y_lo + 1, y_hi)))
    return cx, cy


def _overlaps(box: tuple[int, int, int, int], rects: list[tuple[int, int, int, int]]) -> bool:
    x1, y1, x2, y2 = box
    for rx1, ry1, rx2, ry2 in rects:
        if x1 < rx2 and rx1 < x2 and y1 < ry2 and ry1 < y2:
            return True
    return False


def _draw_bag(rng: np.random.Generator, img: np.ndarray,
              rects: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    """白色/半透明塑料袋：半透明混合 + 褶皱明暗 + 边缘细高光 + 镜面小亮点。"""
    name, n_rng, jit_rng, aspect_rng = BAG_FORMS[int(rng.integers(0, len(BAG_FORMS)))]
    aspect = rng.uniform(*aspect_rng)
    w = int(rng.integers(76, 232))
    h = int(max(26, w / aspect))
    w = min(w, FRAME_W - 2 * MARGIN)
    h = min(h, FRAME_H - 2 * MARGIN)

    span = 1 - 2 * CENTER_INSET
    max_w = span * FRAME_W - 2 * MARGIN
    max_h = span * FRAME_H - 2 * MARGIN
    if w > max_w:                 # 中央区放不下就等比缩到能放下
        scale = max_w / w
        w, h = int(w * scale), max(22, int(h * scale))
    if h > max_h:
        scale = max_h / h
        w, h = max(30, int(w * scale)), int(h * scale)

    n = int(rng.integers(*n_rng))
    jit = rng.uniform(*jit_rng)
    angle = float(rng.uniform(-35, 35))
    ca, sa = np.cos(np.radians(angle)), np.sin(np.radians(angle))

    for _ in range(30):           # 与负样本矩形冲突就重挑位置（保证真值框纯净）
        cx, cy = _center_anchor(rng, w, h)
        pts = []
        for i in range(n):
            t = 2 * np.pi * i / n
            rr = 1.0 + rng.uniform(-jit, jit)
            x = np.cos(t) * (w / 2) * rr
            y = np.sin(t) * (h / 2) * rr
            pts.append([cx + x * ca - y * sa, cy + x * sa + y * ca])
        poly = np.array(pts, dtype=np.int32)
        x1, y1 = int(poly[:, 0].min()), int(poly[:, 1].min())
        x2, y2 = int(poly[:, 0].max()), int(poly[:, 1].max())
        box = (x1, y1, x2, y2)
        if not _overlaps(box, rects):
            break
    else:
        return None

    poly = np.clip(poly, [MARGIN, MARGIN], [FRAME_W - 1 - MARGIN, FRAME_H - 1 - MARGIN])
    x1, y1 = int(poly[:, 0].min()), int(poly[:, 1].min())
    x2, y2 = int(poly[:, 0].max()), int(poly[:, 1].max())

    mask = np.zeros((FRAME_H, FRAME_W), dtype=np.uint8)
    cv2.fillPoly(mask, [poly.reshape(-1, 1, 2)], 255)
    soft = cv2.GaussianBlur(mask.astype(np.float32) / 255.0, (0, 0), 1.3)

    # 半透明混合：白/冷白，透明度随机 → 水色从下面透过来
    v = rng.uniform(206.0, 252.0)
    tint = np.array([v * rng.uniform(0.97, 1.0), v, v * rng.uniform(0.95, 0.99)],
                    dtype=np.float32)
    alpha = (soft * rng.uniform(0.46, 0.86))[..., None]
    img *= (1.0 - alpha)
    img += tint.reshape(1, 1, 3) * alpha

    # 褶皱：低频明暗 + 若干条折痕（暗线紧邻亮线）
    noise = rng.normal(0.0, 1.0, (FRAME_H, FRAME_W)).astype(np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), rng.uniform(6.0, 17.0))
    noise /= (np.abs(noise).max() + 1e-6)
    img += (noise * rng.uniform(16.0, 44.0) * soft)[..., None]

    for _ in range(int(rng.integers(1, 4))):
        fold = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
        fx = int(rng.integers(x1, max(x1 + 1, x2)))
        cv2.line(fold, (x1, fx), (x2, int(np.clip(fx + rng.uniform(-14, 14), y1, y2))),
                 1.0, int(rng.integers(1, 4)), cv2.LINE_AA)
        fold = cv2.GaussianBlur(fold, (0, 0), 2.0) * soft
        img -= (fold * rng.uniform(18.0, 40.0))[..., None]
        img += (np.roll(fold, 3, axis=1) * rng.uniform(12.0, 28.0))[..., None]

    # 边缘细高光（袋膜边缘的掠射亮边）
    k = np.ones((5, 5), np.uint8)
    edge = (cv2.dilate(mask, k).astype(np.float32) - cv2.erode(mask, k).astype(np.float32)) / 255.0
    edge = cv2.GaussianBlur(edge, (0, 0), 1.0) * soft
    img += (edge * rng.uniform(22.0, 56.0))[..., None]

    # 镜面小亮点
    for _ in range(int(rng.integers(0, 3))):
        gx = int(rng.integers(x1, max(x1 + 1, x2)))
        gy = int(rng.integers(y1, max(y1 + 1, y2)))
        if mask[min(gy, FRAME_H - 1), min(gx, FRAME_W - 1)] == 0:
            continue
        gl = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
        cv2.ellipse(gl, (gx, gy), (int(rng.integers(3, 11)), int(rng.integers(2, 6))),
                    float(rng.uniform(0, 180)), 0, 360, 1.0, -1)
        img += (cv2.GaussianBlur(gl, (0, 0), 2.0) * rng.uniform(30.0, 80.0))[..., None]

    return x1, y1, x2, y2


def _draw_buoy(rng: np.random.Generator, img: np.ndarray) -> tuple[int, int, int, int]:
    """彩色浮圈/泳池玩具（标注 buoy 负类）：圆环 + 白边 + 高光。"""
    r = int(rng.integers(14, 34))
    cx, cy = _center_anchor(rng, 2 * r, 2 * r)
    color = np.array(BUOY_COLORS[int(rng.integers(0, len(BUOY_COLORS)))], dtype=np.float32)
    m = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
    if rng.random() < 0.5:                       # 实心浮球
        cv2.circle(m, (cx, cy), r, 1.0, -1)
    else:                                        # 空心浮圈
        cv2.circle(m, (cx, cy), r, 1.0, max(3, r // 3))
    m = cv2.GaussianBlur(m, (0, 0), 1.0)
    img *= (1.0 - m[..., None])
    img += color.reshape(1, 1, 3) * m[..., None]

    ring = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
    cv2.circle(ring, (cx, cy), r, 1.0, 2)
    img += (cv2.GaussianBlur(ring, (0, 0), 1.2) * 200.0)[..., None]
    hl = np.zeros((FRAME_H, FRAME_W), dtype=np.float32)
    cv2.circle(hl, (cx - r // 3, cy - r // 3), max(2, r // 4), 1.0, -1)
    img += (cv2.GaussianBlur(hl, (0, 0), 1.4) * 220.0)[..., None]
    return cx - r, cy - r, cx + r, cy + r


# ----------------------------------------------------------------------
# 组装
# ----------------------------------------------------------------------
def synth_frame(rng: np.random.Generator) -> tuple[np.ndarray, list[tuple[str, tuple[int, int, int, int]]]]:
    """生成一帧与它的真值框列表 [(class, (x1,y1,x2,y2))]。"""
    img = _pool_water(rng)
    _pool_ring(rng, img)                     # 池壁（含内侧倒影）
    rects = _draw_negatives(rng, img)        # 臂/手/线缆：边缘带、不标注

    boxes: list[tuple[str, tuple[int, int, int, int]]] = []
    for _ in range(int(rng.integers(0, 3))):
        boxes.append((BUOY_CLASS, _draw_buoy(rng, img)))
    for _ in range(int(rng.integers(1, 3))):
        box = _draw_bag(rng, img, rects)
        if box:
            boxes.append((BAG_CLASS, box))

    # 收尾：整体曝光 + 传感器噪声 + 轻微雾化（水汽/离焦）
    img *= rng.uniform(0.90, 1.08)
    img += rng.normal(0.0, 3.4, img.shape)
    if rng.random() < 0.35:
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.6, 1.5))
    return np.clip(img, 0, 255).astype(np.uint8), boxes


def _to_yolo(cls: str, xyxy: tuple[int, int, int, int]) -> Box:
    x1, y1, x2, y2 = xyxy
    w = (x2 - x1) / FRAME_W
    h = (y2 - y1) / FRAME_H
    cx = ((x1 + x2) / 2) / FRAME_W
    cy = ((y1 + y2) / 2) / FRAME_H
    return Box(cls, cx, cy, w, h, 1.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成合成「充气泳池」域塑料袋/浮标数据集")
    ap.add_argument("--config", default=None, help="配置文件（默认 edge/grasp/config.yaml）")
    ap.add_argument("--count", type=int, default=400, help="生成帧数")
    ap.add_argument("--tag", default="pool_synth", help="采集会话标签")
    ap.add_argument("--seed", type=int, default=20261018)
    ap.add_argument("--build", action="store_true", help="生成后立即组装 train/val")
    ap.add_argument("--session", default=None, help="--build 时只组装该会话（默认本次生成的）")
    ap.add_argument("--preview", default=None, help="额外导出一张九宫格预览图到该路径")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    dataset = Dataset.from_config(cfg)
    rng = np.random.default_rng(args.seed)

    session = dataset.new_session(args.tag)
    n_bag = n_buoy = 0
    preview_parts: list[np.ndarray] = []
    for i in range(args.count):
        frame, boxes = synth_frame(rng)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok:
            continue
        path = dataset.add_frame(session, buf.tobytes())
        dataset.write_label(path, [_to_yolo(c, b) for c, b in boxes])
        n_bag += sum(1 for c, _ in boxes if c == BAG_CLASS)
        n_buoy += sum(1 for c, _ in boxes if c == BUOY_CLASS)
        if args.preview and len(preview_parts) < 9 and i % max(1, args.count // 9) == 0:
            vis = frame.copy()
            for c, (x1, y1, x2, y2) in boxes:
                col = (0, 255, 0) if c == BAG_CLASS else (0, 165, 255)
                cv2.rectangle(vis, (x1, y1), (x2, y2), col, 2)
            preview_parts.append(cv2.resize(vis, (FRAME_W // 2, FRAME_H // 2)))

    print(f"[生成] 会话={session} 帧={args.count} "
          f"袋框={n_bag} 浮标框={n_buoy} → {dataset.raw_dir / session}")

    if args.preview and preview_parts:
        rows = []
        while preview_parts:
            row = preview_parts[:3]
            preview_parts = preview_parts[3:]
            if len(row) < 3:
                row += [np.zeros_like(row[0])] * (3 - len(row))
            rows.append(np.hstack(row))
        cv2.imwrite(args.preview, np.vstack(rows))
        print(f"[预览] 已导出 {args.preview}")

    if args.build:
        stats = dataset.build(session=args.session or session)
        print(f"[组装] {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
