"""检测跑一遍：用**已部署的 ONNX 后端**（作业台真机同一条推理路径）跑一遍。

覆盖两组图：
  A. SC-FloatWaste 独立测试集（真实漂浮物照片，单类 plastic_bag）—— 对真值算 P/R
  B. built/val 合成帧（模拟机械臂第一人称俯视场景，含塑料袋 + 彩色浮标）

输出：逐图检出明细 + 汇总 + 标注框拼图。
"""
from __future__ import annotations

import pathlib
import sys

import cv2
import numpy as np

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
sys.path.insert(0, str(EDGE))

from grasp.config import load_config                     # noqa: E402
from grasp.vision.detector import Detector                # noqa: E402

DATA = EDGE / "grasp" / "data"
OUT = pathlib.Path(__file__).resolve().parent / "shots" / "detect_run"
OUT.mkdir(parents=True, exist_ok=True)


def load_gt(label_path: pathlib.Path, w: int, h: int) -> list[tuple[float, float, float, float]]:
    """读 YOLO 格式真值，只取 class 0 = plastic_bag。"""
    if not label_path.exists():
        return []
    out = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5 or int(float(parts[0])) != 0:
            continue
        cx, cy, bw, bh = (float(v) for v in parts[1:5])
        out.append(((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h))
    return out


def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def run_group(name: str, slug: str, images: list[pathlib.Path], labels_dir: pathlib.Path,
              det: Detector, cols: int = 4) -> dict:
    print(f"\n{'=' * 78}\n{name}  （{len(images)} 张）\n{'=' * 78}")
    tp = fp = fn = 0
    tiles = []
    for path in images:
        frame = cv2.imread(str(path))
        if frame is None:
            print(f"  {path.name}: 读取失败")
            continue
        h, w = frame.shape[:2]
        gt = load_gt(labels_dir / (path.stem + ".txt"), w, h) if labels_dir else []

        dets = det.infer(frame)                 # 全部检出
        tgts = det.targets(frame)               # 进入抓取候选的（目标类 + 阈值门控）

        # 逐图 TP/FP/FN（conf>=阈值 且 IoU>=0.5 记为命中）
        pred = [d for d in dets if d.cls == det.target_class and d.conf >= det.conf_threshold]
        used = set()
        for p in pred:
            hit = False
            for gi, g in enumerate(gt):
                if gi in used:
                    continue
                if iou((p.x1, p.y1, p.x2, p.y2), g) >= 0.5:
                    used.add(gi)
                    hit = True
                    break
            if hit:
                tp += 1
            else:
                fp += 1
        fn += len(gt) - len(used)

        for d in dets:
            u, v = d.grasp_point
            print(f"  {path.name:14s} {d.cls:12s} conf={d.conf:.3f} "
                  f"bbox=({d.x1:5.0f},{d.y1:5.0f},{d.x2:5.0f},{d.y2:5.0f}) 抓取点=({u:5.0f},{v:5.0f})")
        if not dets:
            print(f"  {path.name:14s} （无检出）")
        print(f"  {'':14s} 真值 {len(gt)} 个 → 候选 {len(tgts)} 个 / 阈值上检出 {len(pred)} 个")

        vis = frame.copy()
        for g in gt:                            # 真值：绿色细框
            cv2.rectangle(vis, (int(g[0]), int(g[1])), (int(g[2]), int(g[3])), (60, 200, 90), 2)
        for d in dets:                          # 检出：塑料袋红框 + 抓取点十字
            col = (60, 60, 235) if d.cls == det.target_class else (150, 150, 150)
            cv2.rectangle(vis, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), col, 2)
            cv2.putText(vis, f"{d.cls} {d.conf:.2f}", (int(d.x1), max(12, int(d.y1) - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1)
            if d.cls == det.target_class and d.conf >= det.conf_threshold:
                u, v = (int(x) for x in d.grasp_point)
                cv2.drawMarker(vis, (u, v), (60, 60, 235), cv2.MARKER_CROSS, 16, 2)
        tiles.append(vis)

    rows = (len(tiles) + cols - 1) // cols
    tw, th = 320, 240
    sheet = np.full((rows * th, cols * tw, 3), 24, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = cv2.resize(t, (tw, th))
    out_png = OUT / f"{slug}.png"
    ok = cv2.imwrite(str(out_png), sheet)
    if not ok:
        raise SystemExit(f"拼图写入失败: {out_png}")

    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    print(f"\n  汇总：TP {tp}  FP {fp}  FN {fn}  →  P {prec:.3f}  R {rec:.3f}"
          f"（conf>={det.conf_threshold}、IoU>=0.5）")
    print(f"  拼图：{out_png}")
    return {"tp": tp, "fp": fp, "fn": fn, "p": prec, "r": rec, "png": str(out_png)}


def full_eval(det: Detector, images: list[pathlib.Path], labels_dir: pathlib.Path,
              low_conf: float = 0.05) -> dict:
    """整集评估：把 conf 阈值临时压到 low_conf 收集全部候选，再统一算 AP50 / P / R。

    在 inference 层压低阈值、在统计层再切阈值 —— 只跑一遍推理，就能同时拿到
    AP50 与「conf=0.5/0.6」两个工作点的 P/R。
    """
    old = det.conf_threshold
    det.conf_threshold = low_conf
    n_gt = 0
    matched: list[tuple[float, bool]] = []
    try:
        for path in images:
            frame = cv2.imread(str(path))
            if frame is None:
                continue
            h, w = frame.shape[:2]
            gt = load_gt(labels_dir / (path.stem + ".txt"), w, h)
            n_gt += len(gt)
            preds = [d for d in det.infer(frame) if d.cls == det.target_class]
            preds.sort(key=lambda d: -d.conf)
            used = [False] * len(gt)
            for d in preds:
                best_i, best_iou = -1, 0.0
                for i, g in enumerate(gt):
                    if used[i]:
                        continue
                    v = iou((d.x1, d.y1, d.x2, d.y2), g)
                    if v > best_iou:
                        best_iou, best_i = v, i
                hit = best_iou >= 0.5
                if hit:
                    used[best_i] = True
                matched.append((d.conf, hit))
    finally:
        det.conf_threshold = old

    matched.sort(key=lambda x: -x[0])
    if not matched or n_gt == 0:
        return {"n_img": len(images), "n_gt": n_gt, "n_pred": len(matched), "ap50": 0.0}

    tps = np.array([1.0 if t else 0.0 for _, t in matched])
    ctp = np.cumsum(tps)
    cfp = np.cumsum(1.0 - tps)
    prec = ctp / np.maximum(ctp + cfp, 1e-9)
    rec = ctp / n_gt
    mrec = np.concatenate(([0.0], rec, [1.0]))
    mpre = np.concatenate(([1.0], prec, [0.0]))
    for i in range(len(mpre) - 2, -1, -1):          # 全点插值：右侧最大精度包络
        mpre[i] = max(mpre[i], mpre[i + 1])
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    ap50 = float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))

    def at(thr: float) -> tuple[float, float]:
        tp = sum(1 for c, t in matched if c >= thr and t)
        fp = sum(1 for c, t in matched if c >= thr and not t)
        return (tp / max(tp + fp, 1), tp / n_gt)

    return {"n_img": len(images), "n_gt": n_gt, "n_pred": len(matched), "ap50": ap50,
            "p50_r50": at(0.50), "p60_r60": at(0.60)}


def main() -> None:
    cfg = load_config()
    det = Detector(cfg, mock=False)         # 真机模式：必须走真实模型，不许合成检测
    backend = det.load()
    print("检测后端：", backend)
    print("模型路径：", det.model_path)
    print("类别口径：", det.classes, " 目标类：", det.target_class)
    print("输入边长：", det.input_size, " conf 阈值：", det.conf_threshold,
          " IoU：", det.iou_threshold, " ROI：", det.roi)
    if backend == "none":
        raise SystemExit("没找到模型，无法检测")

    real = sorted((DATA / "public_plastic" / "images" / "test").glob("*.*"))
    step = max(1, len(real) // 12)
    sample = real[::step][:12]
    r1 = run_group("A · SC-FloatWaste 独立测试集（真实照片）", "A_real_photos", sample,
                   DATA / "public_plastic" / "labels" / "test", det)

    synth = sorted((DATA / "built" / "images" / "val").glob("*.jpg"))[:8]
    r2 = run_group("B · 合成帧（机械臂第一人称演示场景）", "B_synthetic", synth,
                   DATA / "built" / "labels" / "val", det)

    print(f"\n{'=' * 78}\n总览\n{'=' * 78}")
    for tag, r in (("真实照片", r1), ("合成帧", r2)):
        print(f"  {tag}: TP {r['tp']} FP {r['fp']} FN {r['fn']}  P {r['p']:.3f}  R {r['r']:.3f}")

    print(f"\n{'=' * 78}\nC · 独立测试集整集评估（{len(real)} 张，走部署 ONNX 后端）\n{'=' * 78}")
    ev = full_eval(det, real, DATA / "public_plastic" / "labels" / "test")
    print(f"  图像 {ev['n_img']} 张 · 真值 {ev['n_gt']} 个 · 候选(conf>=0.05) {ev['n_pred']} 个")
    print(f"  AP50 = {ev['ap50']:.4f}")
    p50, r50 = ev["p50_r50"]
    p60, r60 = ev["p60_r60"]
    print(f"  conf=0.50 → P {p50:.3f}  R {r50:.3f}")
    print(f"  conf=0.60 → P {p60:.3f}  R {r60:.3f}")


if __name__ == "__main__":
    main()
