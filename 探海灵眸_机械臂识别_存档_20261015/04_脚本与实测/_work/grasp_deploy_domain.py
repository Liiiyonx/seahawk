"""把域内微调出来的 2 类模型评估 → 原子部署，并把两套口径的数字写进版本元数据。

两套评估口径必须分开报，别混：
  A. 演示场景域（synthetic_demo 160 帧，**合成渲染**）—— demo 要跑的正是这个画面
  B. 公开基准（SC-FloatWaste test 400 张真实漂浮物照）—— 看有没有把通用能力练废

评估时**临时**把类别口径改成 2 类（plastic_bag + buoy），因为新模型输出两类；
部署完成后 config.yaml 也要同步改成这个口径，否则索引错位。
"""
from __future__ import annotations

import pathlib
import sys

import cv2
import numpy as np

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
sys.path.insert(0, str(EDGE))

from grasp.config import load_config                       # noqa: E402
from grasp.vision.detector import Detector                 # noqa: E402
from grasp.vision.deploy import ModelStore                 # noqa: E402

NEW_ONNX = pathlib.Path(r"D:\seahawk-work\runs\grasp_domain_2cls\stage\best.onnx")
DATA = EDGE / "grasp" / "data"
NOTE = "域内微调：演示场景域(仿真海面+真实水面) 2 类，塑料袋+浮标负类，@640"


def load_gt(label_path: pathlib.Path, w: int, h: int):
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


def evaluate(tag: str, det: Detector, images: list[pathlib.Path], labels_root: pathlib.Path) -> dict:
    old = det.conf_threshold
    det.conf_threshold = 0.05
    n_gt = 0
    frame_hit = 0
    matched: list[tuple[float, bool]] = []
    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        gt = load_gt(labels_root / f"{img_path.stem}.txt", w, h).get(0, [])
        n_gt += len(gt)
        preds = sorted((d for d in det.infer(img) if d.cls == det.target_class),
                       key=lambda d: -d.conf)
        if any(d.conf >= 0.5 for d in preds):
            frame_hit += 1
        used = [False] * len(gt)
        for d in preds:
            bi, bv = -1, 0.0
            for i, g in enumerate(gt):
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
    if not matched or n_gt == 0:
        return {"tag": tag, "ap50": 0.0, "p50": 0.0, "r50": 0.0, "p30": 0.0, "r30": 0.0,
                "frame_hit": frame_hit, "n_img": len(images), "n_gt": n_gt}
    arr = np.array([1.0 if t else 0.0 for _, t in matched])
    ctp, cfp = np.cumsum(arr), np.cumsum(1.0 - arr)
    prec, rec = ctp / np.maximum(ctp + cfp, 1e-9), ctp / n_gt
    mrec = np.concatenate(([0.0], rec, [1.0]))
    mpre = np.concatenate(([1.0], prec, [0.0]))
    for i in range(len(mpre) - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    ap50 = float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))

    def at(thr):
        tp = sum(1 for c, t in matched if c >= thr and t)
        fp = sum(1 for c, t in matched if c >= thr and not t)
        return tp / max(tp + fp, 1), tp / n_gt

    p50, r50 = at(0.5)
    p30, r30 = at(0.3)
    return {"tag": tag, "ap50": ap50, "p50": p50, "r50": r50, "p30": p30, "r30": r30,
            "frame_hit": frame_hit, "n_img": len(images), "n_gt": n_gt}


def main() -> None:
    if not NEW_ONNX.exists():
        raise SystemExit(f"新模型不存在：{NEW_ONNX} —— 先跑 _work/grasp_train_domain.py")

    cfg = load_config()
    # ★ 临时覆盖：新模型输出 2 类，评估必须按 2 类口径解码，否则第 2 类会被叫成 cls1
    cfg.setdefault("vision", {})["model_classes"] = ["plastic_bag", "buoy"]
    cfg["vision"]["input_size"] = 640

    det = Detector(cfg, mock=False)
    det.model_dir = NEW_ONNX.parent
    det.input_size = 640
    if det.load() != "onnx":
        raise SystemExit("新模型 onnx 加载失败")

    demo_imgs = sorted((DATA / "raw" / "20261015_004150_synthetic_demo").glob("frame_*.jpg"))
    m_demo = evaluate("演示场景域(合成)", det, demo_imgs, DATA / "labels" / "20261015_004150_synthetic_demo")
    pub_imgs = sorted((DATA / "public_plastic" / "images" / "test").glob("*.*"))
    m_pub = evaluate("公开基准(真实)", det, pub_imgs, DATA / "public_plastic" / "labels" / "test")

    for m in (m_demo, m_pub):
        print(f"[{m['tag']}] {m['n_img']} 张 / 真值 {m['n_gt']} · AP50 {m['ap50']:.4f} · "
              f"conf0.5 P {m['p50']:.3f} R {m['r50']:.3f} · conf0.3 P {m['p30']:.3f} R {m['r30']:.3f} · "
              f"帧级命中 {m['frame_hit']}/{m['n_img']}", flush=True)

    store = ModelStore.from_config(cfg)
    meta = store.deploy(NEW_ONNX, metrics={
        "imgsz": 640, "classes": ["plastic_bag", "buoy"], "base": "plastic_color_v4/best.pt",
        "demo_scene_synthetic": {k: (round(v, 4) if isinstance(v, float) else v)
                                 for k, v in m_demo.items()},
        "public_benchmark_real": {k: (round(v, 4) if isinstance(v, float) else v)
                                  for k, v in m_pub.items()},
        "note": "演示场景域为合成渲染帧；公开基准为真实漂浮物照片。两者不可混算。",
    }, note=NOTE)
    print(f"\n已部署版本：{meta['version']} · 文件 {meta['files']}")
    print(f"　源：{meta['source']}")


if __name__ == "__main__":
    main()
