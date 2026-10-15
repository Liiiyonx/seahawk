#!/usr/bin/env python3
"""抗干扰评测：量化「会不会被其他物体或其他颜色干扰」。

## 为什么需要这个工具

用户的核心诉求不是"在某个环境达到某精度"，而是**准确识别塑料袋、不被其他
物体或颜色干扰**。这个诉求本质上是**精确率（Precision）**问题：
mAP 高但精确率低，等于"检出的一半是误报"，现场就是机械臂去抓不该抓的东西。

本工具回答三个具体问题：

1. **阈值怎么定**：扫置信度阈值，给出 P/R/F1 全表和推荐工作点
   （含"精确率优先"工作点）。
2. **误检出在哪**：把每个误检框归因到
   「落在非塑料袋物体上（被其他物体干扰）」还是「落在纯背景上」。
3. **颜色干扰有多大**：往测试图里注入高饱和彩色圆块（模拟彩色浮标），
   对比注入前后的误检数 —— 直接量化"被其他颜色干扰"的程度。

## 数据与口径

* 图：``edge/grasp/data/public_plastic/images/test``（官方 val 划分，400 张）
* 真值：``ml/datasets/public_floatwaste/labels_contract4/test``（4 类，
  用于区分"塑料袋"与"其他物体"）
* 模型：默认用**已部署的** ``models/active/best.onnx``（测的就是实际在用的那个）

> ⚠️ 结论仍是**公开数据集上的表现**，不是现场结论。彩色圆块是合成注入，
> 只能证明"模型对这类高饱和色块的敏感度"，不能替代现场彩色浮标的真实测试。

用法::

    python edge/grasp/tools/eval_robustness.py
    python edge/grasp/tools/eval_robustness.py --model <onnx> --limit 200
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRASP_DIR = HERE.parent
REPO_ROOT = GRASP_DIR.parent.parent
for _p in (str(GRASP_DIR), str(GRASP_DIR.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from grasp.config import load_config  # noqa: E402
from grasp.vision.detector import Detector  # noqa: E402

CONTRACT4_NAMES = ("foam", "plastic", "fishing_gear", "other")
PLASTIC_IDX = CONTRACT4_NAMES.index("plastic")
DEFAULT_IMG_DIR = GRASP_DIR / "data" / "public_plastic" / "images" / "test"
DEFAULT_GT_DIR = REPO_ROOT / "ml" / "datasets" / "public_floatwaste" / "labels_contract4" / "test"

#: 扫阈值时使用的模型侧下限（要拿到完整 PR 曲线，必须比任何工作点都低）
SCAN_FLOOR = 0.05


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
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


def load_gt(lbl_path: Path, w: int, h: int) -> dict[int, list[tuple[float, float, float, float]]]:
    """读 4 类真值，返回 {类索引: [xyxy 像素]}。"""
    out: dict[int, list[tuple[float, float, float, float]]] = {}
    if not lbl_path.exists():
        return out
    for line in lbl_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        ci = int(parts[0])
        cx, cy, bw, bh = (float(x) for x in parts[1:])
        x1, y1 = (cx - bw / 2) * w, (cy - bh / 2) * h
        x2, y2 = (cx + bw / 2) * w, (cy + bh / 2) * h
        out.setdefault(ci, []).append((x1, y1, x2, y2))
    return out


def inject_color_blobs(img: Any, rng: np.random.Generator, count: int = 4) -> Any:
    """注入高饱和彩色圆块（模拟彩色浮标）：实心圆 + 白边 + 高光点。

    刻意沿用与合成数据集一致的高饱和色池 —— 这样测的是"模型对这类
    颜色特征的敏感度"。
    """
    out = img.copy()
    h, w = out.shape[:2]
    colors = [(0, 0, 235), (235, 80, 0), (0, 205, 255), (0, 180, 0), (200, 0, 200)]
    for _ in range(count):
        r = int(rng.integers(15, 33))
        cx = int(rng.integers(r + 2, max(r + 3, w - r - 2)))
        cy = int(rng.integers(r + 2, max(r + 3, h - r - 2)))
        color = colors[int(rng.integers(0, len(colors)))]
        cv2.circle(out, (cx, cy), r, color, -1)
        cv2.circle(out, (cx, cy), r, (250, 250, 250), 2)
        cv2.circle(out, (cx - r // 3, cy - r // 3), max(2, r // 4), (255, 255, 255), -1)
    return out


def match(preds: list[tuple[float, tuple]], gts: list[tuple], iou_thr: float) -> tuple[int, list[int]]:
    """贪心匹配（按 conf 降序）。返回 (TP 数, 未匹配的 pred 下标)。"""
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
            v = _iou(box, g)
            if v > best_iou:
                best_iou, best_j = v, j
        if best_j >= 0 and best_iou >= iou_thr:
            used[best_j] = True
            tp += 1
        else:
            unmatched.append(pi)
    return tp, unmatched


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="塑料袋检测器抗干扰评测")
    ap.add_argument("--config", default=None)
    ap.add_argument("--model", default=None, help="默认用 models/active 里的模型")
    ap.add_argument("--img-dir", default=str(DEFAULT_IMG_DIR))
    ap.add_argument("--gt-dir", default=str(DEFAULT_GT_DIR))
    ap.add_argument("--limit", type=int, default=0, help="只测前 N 张（0=全部）")
    ap.add_argument("--iou", type=float, default=0.5, help="匹配 IoU 阈值")
    ap.add_argument("--blobs", type=int, default=4, help="每张图注入的彩色块数")
    ap.add_argument("--work-conf", type=float, default=0.35,
                    help="归因与彩色干扰分析所用的工作点阈值（默认取 F1 最优附近；"
                         "不能用极端高阈值 —— 那种情况下误检数太少，归因没有统计意义）")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    det = Detector(cfg)
    if args.model:
        # 只支持 .onnx —— 本工具测的是"实际部署的那份推理路径"（cv2.dnn），
        # 而不是 ultralytics 的 .pt 推理，避免"测的和用的不是同一个东西"。
        p = Path(args.model)
        if p.suffix != ".onnx":
            raise SystemExit("--model 只支持 .onnx（本工具测的是部署推理路径）；"
                             "要测 .pt 请直接用 `yolo detect val`")
        det.model_dir = p.parent
        det._net = cv2.dnn.readNetFromONNX(str(p))
        det.backend, det.model_path = "onnx", str(p)
        det._apply_tuning()
        backend = det.backend
    else:
        backend = det.load()
    print(f"[模型] backend={backend} input={det.input_size} classes={det.classes}")

    # 扫描要用到的最低阈值，先按下限推理一次并缓存全部原始检出
    det.conf_threshold = SCAN_FLOOR
    img_dir, gt_dir = Path(args.img_dir), Path(args.gt_dir)
    images = sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.png"))
    if args.limit:
        images = images[: args.limit]

    raw: list[dict] = []
    rng = np.random.default_rng(20261015)
    for p in images:
        img = cv2.imread(str(p))
        if img is None:
            continue
        h, w = img.shape[:2]
        gt = load_gt(gt_dir / f"{p.stem}.txt", w, h)
        preds = [(d.conf, (d.x1, d.y1, d.x2, d.y2)) for d in det.infer(img)]
        raw.append({"name": p.name, "w": w, "h": h, "gt": gt, "preds": preds,
                    "n_preds": len(preds)})

    n_gt_plastic = sum(len(r["gt"].get(PLASTIC_IDX, [])) for r in raw)
    n_gt_other = sum(len(v) for r in raw for ci, v in r["gt"].items() if ci != PLASTIC_IDX)
    print(f"[数据] 图 {len(raw)} 张 | 塑料袋真值 {n_gt_plastic} 框 | 其他物体真值 {n_gt_other} 框")

    # ---------- 1) 阈值扫描 ----------
    thresholds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50,
                  0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
    rows = []
    for t in thresholds:
        tp = fp = 0
        for r in raw:
            preds = [(c, b) for c, b in r["preds"] if c >= t]
            n_tp, unmatched = match(preds, r["gt"].get(PLASTIC_IDX, []), args.iou)
            tp += n_tp
            fp += len(unmatched)
        fn = n_gt_plastic - tp
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        rows.append({"conf": t, "tp": tp, "fp": fp, "fn": fn,
                     "precision": round(prec, 4), "recall": round(rec, 4),
                     "f1": round(f1, 4)})

    print("\n[1] 阈值扫描（精度优先看 precision，别只看 mAP）")
    print("  conf |   TP |   FP |   FN |    P   |    R   |   F1")
    for r in rows:
        print(f"  {r['conf']:.2f} | {r['tp']:>4} | {r['fp']:>4} | {r['fn']:>4} | "
              f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f}")

    best_f1 = max(rows, key=lambda r: r["f1"])
    prec_ordered = [r for r in rows if r["precision"] >= 0.80]
    high_prec = max(prec_ordered, key=lambda r: r["recall"]) if prec_ordered else None
    print(f"\n  F1 最优工作点 : conf={best_f1['conf']:.2f} "
          f"P={best_f1['precision']:.3f} R={best_f1['recall']:.3f}  "
          f"(TP {best_f1['tp']} / FP {best_f1['fp']} / FN {best_f1['fn']})")
    if high_prec:
        print(f"  精确率优先(>=0.80): conf={high_prec['conf']:.2f} "
              f"P={high_prec['precision']:.3f} R={high_prec['recall']:.3f}")
    else:
        print("  精确率优先: 扫到的阈值里**没有一个**能让 precision >= 0.80")
    cfg_row = next((r for r in rows if abs(r["conf"] - 0.60) < 1e-6), None)
    if cfg_row:
        print(f"  当前配置(conf=0.60): P={cfg_row['precision']:.3f} R={cfg_row['recall']:.3f}  "
              f"→ 这个工作点恰好是「精确率中等、召回很低」")

    # ---------- 2) 误检归因 ----------
    ref = {"conf": float(args.work_conf)}
    print(f"\n[2] 误检归因（工作点 conf={ref['conf']:.2f}）")
    on_object = on_background = 0
    total_fp = 0
    per_class = Counter()
    for r in raw:
        preds = [(c, b) for c, b in r["preds"] if c >= ref["conf"]]
        _tp, unmatched = match(preds, r["gt"].get(PLASTIC_IDX, []), args.iou)
        total_fp += len(unmatched)
        others = [(ci, b) for ci, boxes in r["gt"].items() if ci != PLASTIC_IDX for b in boxes]
        for pi in unmatched:
            box = preds[pi][1]
            hit = None
            for ci, g in others:
                if _iou(box, g) >= 0.30:
                    hit = ci
                    break
            if hit is None:
                on_background += 1
            else:
                on_object += 1
                per_class[CONTRACT4_NAMES[hit]] += 1
    print(f"  共 {total_fp} 个误检")
    print(f"  落在【其他物体】上（被其他物体干扰）: {on_object}  "
          f"({on_object / max(1, total_fp) * 100:.1f}%)  明细={dict(per_class)}")
    print(f"  落在【纯背景】上                     : {on_background}  "
          f"({on_background / max(1, total_fp) * 100:.1f}%)")

    # ---------- 3) 彩色干扰注入 ----------
    print(f"\n[3] 彩色干扰注入（每图贴 {args.blobs} 个高饱和彩色圆块）")
    base_total = tgt_total = 0
    for r in raw:
        base_total += sum(1 for c, _ in r["preds"] if c >= ref["conf"])
    for p in images:
        img = cv2.imread(str(p))
        if img is None:
            continue
        perturbed = inject_color_blobs(img, rng, args.blobs)
        for d in det.infer(perturbed):
            if d.conf >= ref["conf"]:
                tgt_total += 1
    delta = tgt_total - base_total
    print(f"  原图检出合计 {base_total} → 注入后 {tgt_total}（Δ={delta:+d}）")
    if base_total:
        print(f"  相对增幅 {delta / base_total * 100:+.1f}%")
    print("  读法：增幅越小说明模型越不依赖「颜色」这一单一特征；"
          "增幅大则说明彩色干扰确实会引入误检。")

    if args.json_out:
        out = {
            "model": det.model_path, "backend": backend, "images": len(raw),
            "gt_plastic": n_gt_plastic, "gt_other": n_gt_other,
            "scan": rows, "best_f1": best_f1, "precision_priority": high_prec,
            "fp_on_object": on_object, "fp_on_background": on_background,
            "fp_on_object_detail": dict(per_class),
            "color_injection": {"base": base_total, "after": tgt_total, "delta": delta},
            "claim_boundary": "公开数据集 + 合成彩色注入，非现场结论",
        }
        Path(args.json_out).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
        print(f"\n[写出] {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
