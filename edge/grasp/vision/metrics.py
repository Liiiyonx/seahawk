"""检测评测的共用数学口径：IoU / 贪心匹配 / 阈值扫描行。

## 为什么要集中到一处

同一批预测，在两条推理链上的 P/R 会不一样：

* ``vision/evaluate.py`` 走 **ultralytics 自带推理**（它有自己的 letterbox 与后处理）；
* 现场真正跑的是 ``Detector``（``cv2.dnn`` + 自写 letterbox/解码/NMS）。

所以「测的」与「用的」必须各有一份证据 —— 但**匹配口径必须共用**。原先这套算法在
``tools/eval_robustness.py`` 与 ``tools/verify_pool_model.py`` 里各写了一份（后者还
多写了个只用于「误检落在哪」的 ``_iou_at_least``）。两套实现算出两个数时，谁也说不清
谁对；现在只留这一份。

本模块是纯数学，**不 import cv2**：没有 cv2 的机器也能单测它。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

#: 扫阈值时使用的模型侧下限（要拿到完整 PR 曲线，必须比任何工作点都低）
SCAN_FLOOR = 0.05

#: 部署链路扫描的默认阈值档位（与 tools 历史的档位一致，便于逐字比对输出）
DEPLOY_THRESHOLDS: tuple[float, ...] = (0.05, 0.15, 0.25, 0.30, 0.35, 0.40,
                                       0.50, 0.60, 0.70, 0.80, 0.90)

#: 判「误检落在其他类物体上」而非纯背景时的 IoU 门限
FP_ATTRIBUTION_IOU = 0.30

Box = tuple[float, float, float, float]


def iou(a: Box, b: Box) -> float:
    """两个 xyxy 框的交并比。"""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def iou_at_least(a: Box, b: Box, thr: float) -> bool:
    """``iou(a, b) >= thr``，但省掉除法后的比较（判归属时只看是与否）。"""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return False
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return union > 0 and inter / union >= thr


def match(preds: Sequence[tuple[float, Box]], gts: Sequence[Box],
          iou_thr: float) -> tuple[int, list[int]]:
    """贪心匹配（pred 按 conf 降序）。返回 ``(TP 数, 未匹配的 pred 下标)``。

    贪心而不是最优指派：与 ultralytics 的评测口径一致，且 TP 记法在
    「一个 gt 被多个 pred 争」时不会重复计数（``used`` 保证一对一）。
    """
    order = sorted(range(len(preds)), key=lambda i: -preds[i][0])
    used = [False] * len(gts)
    tp = 0
    unmatched: list[int] = []
    for pi in order:
        box = preds[pi][1]
        best_j, best_iou = -1, 0.0
        for j, g in enumerate(gts):
            if used[j]:
                continue
            v = iou(box, g)
            if v > best_iou:
                best_iou, best_j = v, j
        if best_j >= 0 and best_iou >= iou_thr:
            used[best_j] = True
            tp += 1
        else:
            unmatched.append(pi)
    return tp, unmatched


def load_yolo_gt(path: Path, w: int, h: int) -> dict[int, list[Box]]:
    """读 YOLO txt 真值 → ``{类索引: [xyxy 像素框]}``；非法行跳过。"""
    out: dict[int, list[Box]] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        ci = int(parts[0])
        cx, cy, bw, bh = (float(x) for x in parts[1:])
        out.setdefault(ci, []).append(((cx - bw / 2) * w, (cy - bh / 2) * h,
                                       (cx + bw / 2) * w, (cy + bh / 2) * h))
    return out


def scan_rows(raw: Iterable[dict[str, Any]], *, thresholds: Sequence[float],
              iou: float = 0.5, target_idx: int = 0,
              split_fp_by_other: bool = False) -> list[dict[str, Any]]:
    """对已缓存的原始检出做阈值扫描，返回每档 ``conf`` 的完整指标行。

    ``raw`` 每项形如 ``{"gt": {类索引: [xyxy]}, "preds": [(conf, box), ...]}``，
    其中 ``preds`` 由调用方**按需先过滤好类**（各工具的口径不同，不该在这里替它决定）。

    ``split_fp_by_other=True`` 时把误检再分成「落在其他类物体上」与「落在纯背景上」——
    机械臂场景里这两类的处置完全不同（被彩色浮标干扰 vs 背景反光误检）。
    """
    rows: list[dict[str, Any]] = []
    raw = list(raw)
    n_gt = sum(len(r["gt"].get(target_idx, [])) for r in raw)
    for t in thresholds:
        tp = fp_other = fp_bg = 0
        hit_frames = 0
        for r in raw:
            preds = [(c, b) for c, b in r["preds"] if c >= t]
            n_tp, unmatched = match(preds, r["gt"].get(target_idx, []), iou)
            tp += n_tp
            if preds and n_tp:
                hit_frames += 1
            if not split_fp_by_other:
                fp_bg += len(unmatched)
                continue
            others = [(ci, b) for ci, boxes in r["gt"].items() if ci != target_idx
                      for b in boxes]
            for pi in unmatched:
                box = preds[pi][1]
                if any(iou_at_least(box, g, FP_ATTRIBUTION_IOU) for _ci, g in others):
                    fp_other += 1
                else:
                    fp_bg += 1
        fp = fp_other + fp_bg
        fn = n_gt - tp
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        rows.append({"conf": float(t), "tp": tp, "fp": fp, "fp_other": fp_other,
                     "fp_background": fp_bg, "fn": fn, "precision": round(prec, 4),
                     "recall": round(rec, 4), "f1": round(f1, 4),
                     "hit_frames": hit_frames})
    return rows
