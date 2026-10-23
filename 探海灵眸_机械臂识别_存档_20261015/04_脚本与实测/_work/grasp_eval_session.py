"""在指定采集会话（有真值）上整集评估某个尺寸的模型：AP50 / P / R。

用途：量「演示场景域」的识别水平 —— synthetic_demo 就是作业台 mock 的仿真海面
（深色水面 + 低饱和灰袋 + 高饱和彩色浮标），也就是计划书里机械臂那段要跑的画面。
★ 注意：这些帧**本身是合成渲染**，所以数字口径是「合成域内精度」，不是真实海面精度。

也顺带报「被类名门控挡掉的浮标框数」，验证抗浮标三层防线的推理层是否生效。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import cv2
import numpy as np

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
sys.path.insert(0, str(EDGE))

from grasp.config import load_config                      # noqa: E402
from grasp.vision.detector import Detector               # noqa: E402

DATA = EDGE / "grasp" / "data"


def load_gt(label_path: pathlib.Path, w: int, h: int):
    """返回 {cls_idx: [xyxy...]}。"""
    out: dict[int, list[tuple[float, float, float, float]]] = {}
    if not label_path.exists():
        return out
    for line in label_path.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        ci = int(float(p[0]))
        cx, cy, bw, bh = (float(v) for v in p[1:5])
        out.setdefault(ci, []).append(((cx - bw / 2) * w, (cy - bh / 2) * h,
                                       (cx + bw / 2) * w, (cy + bh / 2) * h))
    return out


def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="20261015_004150_synthetic_demo")
    ap.add_argument("--sizes", default="416,640,768")
    ap.add_argument("--model-dir", default=None, help="直接指定模型目录（覆盖按尺寸取 _work/onnx_export）")
    args = ap.parse_args()

    cfg = load_config()
    frames = sorted((DATA / "raw" / args.session).glob("frame_*.jpg"))
    if not frames:
        raise SystemExit(f"会话无帧：{args.session}")
    print(f"会话 {args.session} · {len(frames)} 帧\n")

    for size in (int(s) for s in args.sizes.split(",")):
        det = Detector(cfg, mock=False)
        det.input_size = size
        det.model_dir = (pathlib.Path(args.model_dir) if args.model_dir
                         else pathlib.Path(__file__).resolve().parent / "onnx_export" / f"n{size}")
        if det.load() != "onnx":
            print(f"imgsz={size}: 模型不可用，跳过")
            continue

        old = det.conf_threshold
        det.conf_threshold = 0.05
        n_gt_bag = 0
        buoy_preds = 0
        matched: list[tuple[float, bool]] = []
        for f in frames:
            img = cv2.imread(str(f))
            if img is None:
                continue
            h, w = img.shape[:2]
            gt = load_gt(DATA / "labels" / args.session / f.with_suffix(".txt").name, w, h)
            g_bag = gt.get(0, [])
            n_gt_bag += len(g_bag)
            preds = det.infer(img)
            buoy_preds += sum(1 for d in preds if d.cls == "buoy")
            bag_preds = sorted((d for d in preds if d.cls == "plastic_bag"), key=lambda d: -d.conf)
            used = [False] * len(g_bag)
            for d in bag_preds:
                bi, bv = -1, 0.0
                for i, g in enumerate(g_bag):
                    if used[i]:
                        continue
                    v = iou((d.x1, d.y1, d.x2, d.y2), g)
                    if v > bv:
                        bv, bi = v, i
                hit = bv >= 0.5
                if hit:
                    used[bi] = True
                matched.append((d.conf, hit))
        det.conf_threshold = old

        matched.sort(key=lambda x: -x[0])
        if not matched or n_gt_bag == 0:
            print(f"imgsz={size}: 无候选/无真值")
            continue
        tp_arr = np.array([1.0 if t else 0.0 for _, t in matched])
        ctp = np.cumsum(tp_arr)
        cfp = np.cumsum(1.0 - tp_arr)
        prec = ctp / np.maximum(ctp + cfp, 1e-9)
        rec = ctp / n_gt_bag
        mrec = np.concatenate(([0.0], rec, [1.0]))
        mpre = np.concatenate(([1.0], prec, [0.0]))
        for i in range(len(mpre) - 2, -1, -1):
            mpre[i] = max(mpre[i], mpre[i + 1])
        idx = np.where(mrec[1:] != mrec[:-1])[0]
        ap50 = float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))

        def at(thr: float):
            tp = sum(1 for c, t in matched if c >= thr and t)
            fp = sum(1 for c, t in matched if c >= thr and not t)
            return tp / max(tp + fp, 1), tp / n_gt_bag

        p50, r50 = at(0.5)
        p30, r30 = at(0.3)
        hits_per_frame = sum(1 for f in frames
                             for d in [det.infer(cv2.imread(str(f)))]
                             if any(x.cls == "plastic_bag" and x.conf >= 0.5 for x in d))
        print(f"imgsz={size:4d} · 真值袋 {n_gt_bag} · 候选 {len(matched)} · 浮标框 {buoy_preds}")
        print(f"           AP50 {ap50:.4f} · conf0.5 P {p50:.3f} R {r50:.3f}"
              f" · conf0.3 P {p30:.3f} R {r30:.3f}"
              f" · 帧级命中(conf>=0.5) {hits_per_frame}/{len(frames)}")


if __name__ == "__main__":
    main()
