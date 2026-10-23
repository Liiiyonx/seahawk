#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探海灵眸 Oceanus —— 公开漂浮垃圾基准感知评测（YOLO-World / YOLO11 通道）。

与 ``evaluate_opencv.py`` 的分工
--------------------------------
* ``evaluate_opencv.py`` 评测 **OpenCV 传统视觉**通道（需要连续帧建背景模型）。
* 本脚本评测**神经网络检测通道**，跑在**静态图独立测试集**上：
    - ``--channel world``  ：YOLO-World 开放词汇零样本（``edge/detector/world_detector.py``）
    - ``--channel yolo11`` ：YOLO11 有监督微调权重

★ 本脚本直接调用产品里那条 ``WorldDetector``，不是另写一份推理 ——
  「评测的模型」与「演示现场加词的模型」是同一个类、同一份权重。

纪律（与 WP-06 一致，不得放宽）
--------------------------------
1. 只认数据集清单（``--manifest-dir``），不扫目录。
2. 清单 ``status != ready`` / 空数据 / 图片缺失 → ``not_evaluated``，**绝不生成虚假精度**。
3. 每个数字都带 ``evidence_level`` 与 ``claim_boundary``；公开第三方数据集**不得**
   表述为「连江现场验证」或「本项目设备实测精度」。
4. 记录权重文件 SHA256、标注文件 SHA256、清单哈希与命令，保证可复现。

退出码：0=完成（含 not_evaluated）；1=运行时错误；2=配置/清单错误；3=依赖缺失。

用法
----
    python ml/scripts/evaluate_public_litter.py \
        --manifest-dir ml/datasets/manifests_public --split test \
        --channel world --output artifacts/metrics/public_floatwaste_world_test.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

THIS = Path(__file__).resolve()
ML = THIS.parent.parent
ROOT = ML.parent
SCRIPTS = THIS.parent
for p in (str(SCRIPTS), str(ROOT / "edge" / "detector")):
    if p not in sys.path:
        sys.path.insert(0, p)

from evaluate_opencv import (  # noqa: E402  —— 复用冻结的清单校验与 IoU
    ALLOWED_EVIDENCE,
    EVALUATED,
    NOT_EVALUATED,
    box_iou,
    resolve_evidence,
    validate_manifest,
)

IMG_SUFFIX = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
IOU_THRESHOLDS = [round(0.5 + 0.05 * i, 2) for i in range(10)]  # 0.50 … 0.95
CONTRACT4_NAMES = ("foam", "plastic", "fishing_gear", "other")


class DependencyError(Exception):
    pass


class ConfigError(Exception):
    pass


# ----------------------------------------------------------------------
# 指标（纯逻辑，无第三方依赖）
# ----------------------------------------------------------------------
def _match_image(gt: list[dict], det: list[dict], iou_thr: float) -> tuple[list[int], list[int]]:
    """单图贪心匹配（置信度降序），返回 (dets 的命中标记, gts 的占用标记)。"""
    gt_used = [False] * len(gt)
    det_hit = [False] * len(det)
    for i in sorted(range(len(det)), key=lambda k: -det[k]["confidence"]):
        best_j, best_iou = -1, iou_thr
        for j, g in enumerate(gt):
            if gt_used[j]:
                continue
            iou = box_iou(det[i]["bbox"], g["bbox"])
            if iou >= best_iou:
                best_iou, best_j = iou, j
        if best_j >= 0:
            gt_used[best_j] = True
            det_hit[i] = True
    return det_hit, gt_used


def _voc_ap(recalls: list[float], precisions: list[float]) -> float:
    """全点插值 AP（VOC2010+ / COCO 风格单调包络积分）。"""
    if not recalls:
        return 0.0
    mrec = [0.0] + recalls + [1.0]
    mpre = [0.0] + precisions + [0.0]
    for i in range(len(mpre) - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    ap = 0.0
    for i in range(1, len(mrec)):
        if mrec[i] != mrec[i - 1]:
            ap += (mrec[i] - mrec[i - 1]) * mpre[i]
    return ap


def ap_for_class(
    gt_by_img: dict[str, list[dict]], det_by_img: dict[str, list[dict]], cls: str, iou_thr: float
) -> tuple[float, int, int, list[tuple[float, int, int]]]:
    """返回 (AP, n_gt, n_det, PR 曲线点[(conf, tp, fp)])。

    ★ 逐图先做匹配，再按全局置信度排序累计 —— 检测框用 (图像, 原始下标) 标识，
      不用对象相等性去找下标（那在框重复时会错配）。
    """
    hits: dict[tuple[str, int], bool] = {}
    flat: list[tuple[float, str, int]] = []
    n_det = 0
    for img, ds in det_by_img.items():
        idxs = [k for k, d in enumerate(ds) if d["class"] == cls]
        sub = [ds[k] for k in idxs]
        if sub:
            h, _ = _match_image(
                [g for g in gt_by_img.get(img, []) if g["class"] == cls], sub, iou_thr)
            for pos, k in enumerate(idxs):
                hits[(img, k)] = h[pos]
                flat.append((ds[k]["confidence"], img, k))
            n_det += len(sub)
    flat.sort(key=lambda t: -t[0])
    n_gt = sum(1 for v in gt_by_img.values() for g in v if g["class"] == cls)

    tp = fp = 0
    recalls: list[float] = []
    precisions: list[float] = []
    points: list[tuple[float, int, int]] = []
    for conf, img, k in flat:
        if hits.get((img, k)):
            tp += 1
        else:
            fp += 1
        points.append((conf, tp, fp))
        if n_gt > 0:
            recalls.append(tp / n_gt)
            precisions.append(tp / (tp + fp))
    ap = _voc_ap(recalls, precisions) if n_gt > 0 else 0.0
    return ap, n_gt, n_det, points


def best_f1(points: list[tuple[float, int, int]], n_gt: int) -> dict[str, Any]:
    """在 PR 曲线上取 F1 最大的工作点。"""
    if n_gt <= 0 or not points:
        return {"status": NOT_EVALUATED, "reason": "无真值或无检测，分母为零"}
    best = None
    for conf, tp, fp in points:
        if tp == 0:
            continue
        p = tp / (tp + fp)
        r = tp / n_gt
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        if best is None or f1 > best["f1"]:
            best = {"confidence_threshold": round(conf, 4), "precision": round(p, 4),
                    "recall": round(r, 4), "f1": round(f1, 4), "tp": tp, "fp": fp,
                    "fn": n_gt - tp}
    if best is None:
        return {"status": NOT_EVALUATED, "reason": "无有效工作点"}
    best["status"] = EVALUATED
    return best


def metrics_at_conf(points: list[tuple[float, int, int]], n_gt: int, conf: float) -> dict[str, Any]:
    """指定门限下的 P/R/F1（取 <= conf 的最后一个累计点）。"""
    if n_gt <= 0:
        return {"status": NOT_EVALUATED, "reason": "无真值，分母为零"}
    tp = fp = 0
    for c, t, f in points:
        if c < conf:
            break
        tp, fp = t, f
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / n_gt
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return {"status": EVALUATED, "confidence_threshold": conf,
            "precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4),
            "tp": tp, "fp": fp, "fn": n_gt - tp}


# ----------------------------------------------------------------------
# 数据加载
# ----------------------------------------------------------------------
def sha256_file(p: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def load_yaml(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise DependencyError("缺少 pyyaml") from exc
    import io as _io
    return yaml.safe_load(_io.open(path, encoding="utf-8"))


def load_manifest(manifest_dir: Path, split: str) -> dict:
    if not manifest_dir.exists():
        raise ConfigError("清单目录不存在：%s" % manifest_dir)
    cands = [p for p in sorted(manifest_dir.glob("*.y*ml")) if not p.name.startswith("template")]
    found: dict[str, tuple[dict, Path]] = {}
    for p in cands:
        data = validate_manifest(load_yaml(p), p.name)
        mt = data["manifest_type"]
        if mt in found:
            raise ConfigError("清单目录存在重复的 %s 类型：%s" % (mt, p.name))
        found[mt] = (data, p)
    if split not in found:
        raise ConfigError("缺少 %s 分集清单（可用: %s）" % (split, sorted(found)))
    data, path = found[split]
    data["_path"] = str(path)
    return data


def yolo_labels_for(img: Path, images_root: Path, labels_root: Path) -> Path:
    rel = img.relative_to(images_root)
    return labels_root / rel.with_suffix(".txt")


def read_yolo(txt: Path, w: int, h: int, names: list[str]) -> list[dict]:
    out: list[dict] = []
    if not txt.exists():
        return out
    for line in txt.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        try:
            cid = int(float(parts[0]))
            cx, cy, bw, bh = (float(v) for v in parts[1:])
        except ValueError:
            continue
        if not (0 <= cid < len(names)):
            continue
        out.append({
            "class": names[cid],
            "bbox": [(cx - bw / 2) * w, (cy - bh / 2) * h,
                     (cx + bw / 2) * w, (cy + bh / 2) * h],
        })
    return out


def region_of(img: Path) -> str:
    """文件名约定 ``<region>__<stem>.<ext>``（见 scripts/fetch_public_floatwaste.py）。"""
    stem = img.stem
    return stem.split("__", 1)[0] if "__" in stem else "unknown"


# ----------------------------------------------------------------------
# 通道适配
# ----------------------------------------------------------------------
def load_channel(args: argparse.Namespace):
    """返回 (name, detect_fn, meta)。detect_fn(np.ndarray) -> [{class, confidence, bbox}]"""
    if args.channel == "world":
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
        except ImportError as exc:
            raise DependencyError("world 通道需要 numpy/cv2") from exc
        from world_detector import DEFAULT_WORLD_CONFIG, WorldDetector, resolve_weights_path

        prompts = args.prompts or list(DEFAULT_WORLD_CONFIG["prompt_classes"])
        cfg = dict(DEFAULT_WORLD_CONFIG)
        cfg.update({
            "weights": args.weights or DEFAULT_WORLD_CONFIG["weights"],
            "device": args.device,
            "imgsz": args.imgsz,
            "conf": args.conf,
            "max_det": args.max_det,
            "prompt_classes": prompts,
            "allow_weights_download": False,
        })
        det = WorldDetector(cfg, roi=None)
        if not det.available:
            raise DependencyError("WorldDetector 不可用：%s" % det.last_error)
        wpath = resolve_weights_path(cfg["weights"])
        meta = {
            "channel": "world",
            "kind": "open_vocabulary_zero_shot",
            "model": "YOLO-World",
            "weights": str(wpath),
            "weights_sha256": sha256_file(wpath),
            "prompts": prompts,
            "imgsz": args.imgsz,
            "conf_floor": args.conf,
            "device": args.device,
            "note": "零样本开放词汇：提示词即类别，未在目标数据集上训练。",
        }
        return "world", det.detect, meta

    if args.channel == "yolo11":
        if not args.weights:
            raise ConfigError("yolo11 通道必须给 --weights")
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise DependencyError("yolo11 通道需要 ultralytics") from exc
        wpath = Path(args.weights)
        if not wpath.is_absolute():
            wpath = (ROOT / wpath).resolve()
        if not wpath.exists():
            raise ConfigError("权重不存在：%s" % wpath)
        model = YOLO(str(wpath))
        names = [model.names[i] for i in sorted(model.names)]

        def detect(frame):
            r = model.predict(frame, conf=args.conf, iou=args.iou_nms, imgsz=args.imgsz,
                              max_det=args.max_det, device=args.device, verbose=False)[0]
            out = []
            if r.boxes is None:
                return out
            for bbox, conf, cid in zip(r.boxes.xyxy.detach().cpu().tolist(),
                                       r.boxes.conf.detach().cpu().tolist(),
                                       r.boxes.cls.detach().cpu().int().tolist()):
                out.append({"class": names[int(cid)], "confidence": float(conf),
                            "bbox": [float(v) for v in bbox]})
            return out

        meta = {"channel": "yolo11", "kind": "supervised_finetuned",
                "model": "YOLO11", "weights": str(wpath),
                "weights_sha256": sha256_file(wpath), "names": names,
                "imgsz": args.imgsz, "conf_floor": args.conf, "device": args.device}
        return "yolo11", detect, meta

    raise ConfigError("未知通道：%s" % args.channel)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="公开漂浮垃圾基准感知评测")
    ap.add_argument("--manifest-dir", default=str(ML / "datasets" / "manifests_public"))
    ap.add_argument("--split", default="test")
    ap.add_argument("--channel", default="world", choices=["world", "yolo11"])
    ap.add_argument("--weights", default=None)
    ap.add_argument("--output", required=True)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.001,
                    help="模型侧打分下限；AP 需要完整 PR 曲线，故取极低值")
    ap.add_argument("--iou-nms", type=float, default=0.45)
    ap.add_argument("--max-det", type=int, default=100)
    ap.add_argument("--device", default="0")
    ap.add_argument("--prompts", action="append", default=None)
    ap.add_argument("--label-space", default="litter", choices=["litter", "contract4"])
    ap.add_argument("--max-images", type=int, default=0)
    ap.add_argument("--tag", default="")
    args = ap.parse_args(argv)

    command = "python ml/scripts/evaluate_public_litter.py " + " ".join(sys.argv[1:])
    manifest_dir = Path(args.manifest_dir)
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "status": NOT_EVALUATED,
        "not_evaluated_reasons": [],
        "command": command.strip(),
        "date": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "label_space": args.label_space,
        "iou_thresholds": IOU_THRESHOLDS,
        "metrics": {},
    }

    try:
        manifest = load_manifest(manifest_dir, args.split)
    except (ConfigError, DependencyError) as exc:
        report["not_evaluated_reasons"].append(str(exc))
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        print("[not_evaluated] %s" % exc)
        return 2 if isinstance(exc, ConfigError) else 3

    ev = resolve_evidence(manifest.get("data_type"), manifest.get("status"),
                          manifest.get("evidence_level"))
    report["dataset"] = {
        "manifest_dir": str(manifest_dir), "manifest_path": manifest.get("_path"),
        "manifest_name": manifest.get("name"), "split": args.split,
        "status": manifest.get("status"), "data_type": manifest.get("data_type"),
        "evidence_level": ev, "isolation": manifest.get("isolation"),
        "source": manifest.get("source"), "description": manifest.get("description"),
    }

    if manifest.get("status") != "ready":
        report["not_evaluated_reasons"].append(
            "清单 status=%r，未就绪（planned/sealed 不得评测）" % manifest.get("status"))
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        print("[not_evaluated] 清单未就绪")
        return 0

    loc = manifest.get("location") or {}
    images_root = (ROOT / loc["images"]).resolve() if loc.get("images") else None
    labels_sub = "labels" if args.label_space == "litter" else "labels_contract4"
    labels_root = (ROOT / (loc.get("labels") or "")).resolve() if loc.get("labels") else None
    if labels_root is not None and labels_sub != "labels":
        labels_root = labels_root.parent / labels_sub

    if not images_root or not images_root.exists():
        report["not_evaluated_reasons"].append("图片目录不存在：%s" % images_root)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        print("[not_evaluated] 图片目录不存在")
        return 0

    imgs = sorted(p for p in images_root.rglob("*")
                  if p.is_file() and p.suffix.lower() in IMG_SUFFIX)
    if args.max_images:
        imgs = imgs[:args.max_images]
    if not imgs:
        report["not_evaluated_reasons"].append("独立测试集为空（images=%d）" % len(imgs))
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        print("[not_evaluated] 空数据集")
        return 0

    report["dataset"]["sample_size"] = len(imgs)
    report["dataset"]["images_root"] = str(images_root)
    report["dataset"]["labels_root"] = str(labels_root)

    try:
        ch_name, detect, ch_meta = load_channel(args)
    except (DependencyError, ConfigError) as exc:
        report["not_evaluated_reasons"].append(str(exc))
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        print("[not_evaluated] %s" % exc)
        return 3 if isinstance(exc, DependencyError) else 2

    report["channel"] = ch_meta

    import cv2
    import numpy as np

    gt_by_img: dict[str, list[dict]] = {}
    det_by_img: dict[str, list[dict]] = {}
    regions: dict[str, str] = {}
    n_gt = 0
    missing_imgs: list[str] = []
    t0 = datetime.now()
    for i, img in enumerate(imgs, 1):
        frame = cv2.imread(str(img), cv2.IMREAD_COLOR)
        if frame is None:
            missing_imgs.append(str(img))
            continue
        key = img.stem
        regions[key] = region_of(img)
        h, w = frame.shape[:2]
        names = CONTRACT4_NAMES if args.label_space == "contract4" else ["litter"]
        gt_by_img[key] = read_yolo(
            yolo_labels_for(img, images_root, labels_root), w, h, list(names))
        n_gt += len(gt_by_img[key])
        dets = detect(frame)
        if args.label_space == "litter":
            # 单类任务：开放词汇通道输出的四个契约类在这里全部并入
            # 「漂浮垃圾」这一类再与真值匹配 —— 评测的是「有没有找到垃圾」，
            # 不是「分对了没有」。
            for d in dets:
                d["class"] = "litter"
        det_by_img[key] = dets
        if i % 25 == 0 or i == len(imgs):
            print("  推理 %d/%d  真值框=%d 耗时=%.0fs"
                  % (i, len(imgs), n_gt, (datetime.now() - t0).total_seconds()))

    if missing_imgs:
        report["not_evaluated_reasons"].append(
            "有 %d 张图无法解码，已跳过：%s" % (len(missing_imgs), missing_imgs[:5]))

    n_det = sum(len(v) for v in det_by_img.values())
    report["denominators"] = {
        "images": len(gt_by_img), "gt_boxes": n_gt, "detections": n_det,
        "images_missing": len(missing_imgs),
    }
    if n_gt == 0:
        report["not_evaluated_reasons"].append("真值框数为 0，分母为零 → 不产出精度")
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        print("[not_evaluated] 真值为 0")
        return 0

    classes = ["litter"] if args.label_space == "litter" else list(CONTRACT4_NAMES)
    per_class: dict[str, Any] = {}
    for cls in classes:
        ap_by_iou = {}
        pts50 = None
        for t in IOU_THRESHOLDS:
            a, g, d, pts = ap_for_class(gt_by_img, det_by_img, cls, t)
            if t == 0.5:
                pts50 = pts
            if g == 0 or d == 0:
                continue
            ap_by_iou[t] = round(a, 4)
        gt_c = sum(1 for v in gt_by_img.values() for g in v if g["class"] == cls)
        dt_c = sum(1 for v in det_by_img.values() for d in v if d["class"] == cls)
        if not ap_by_iou:
            per_class[cls] = {"status": NOT_EVALUATED,
                              "reason": "该类无真值或无检测，分母为零",
                              "gt_boxes": gt_c, "detections": dt_c}
            continue
        per_class[cls] = {
            "status": EVALUATED,
            "gt_boxes": gt_c, "detections": dt_c,
            "mAP50": ap_by_iou.get(0.5),
            "mAP50_95": round(sum(ap_by_iou.values()) / len(ap_by_iou), 4),
            "ap_by_iou": {str(k): v for k, v in ap_by_iou.items()},
            "best_f1": best_f1(pts50 or [], gt_c),
            "at_conf_0.25": metrics_at_conf(pts50 or [], gt_c, 0.25),
            "at_conf_0.10": metrics_at_conf(pts50 or [], gt_c, 0.10),
            "at_conf_0.05": metrics_at_conf(pts50 or [], gt_c, 0.05),
        }

    # 分区域（跨域泛化证据）：region 取自文件名前缀
    def _subset(keys: set[str]) -> tuple[dict, dict, int]:
        g = {k: v for k, v in gt_by_img.items() if k in keys}
        d = {k: v for k, v in det_by_img.items() if k in keys}
        return g, d, sum(len(v) for v in g.values())

    by_region: dict[str, Any] = {}
    for r in sorted(set(regions.values())):
        keys = {k for k, v in regions.items() if v == r}
        g, d, ng = _subset(keys)
        entry: dict[str, Any] = {"images": len(g), "gt_boxes": ng,
                                 "detections": sum(len(v) for v in d.values())}
        for cls in classes:
            a50, gc, dc, pts = ap_for_class(g, d, cls, 0.5)
            if gc == 0 or dc == 0:
                entry[cls] = {"status": NOT_EVALUATED, "gt_boxes": gc, "detections": dc}
            else:
                entry[cls] = {"status": EVALUATED, "mAP50": round(a50, 4),
                              "gt_boxes": gc, "detections": dc,
                              "best_f1": best_f1(pts, gc)}
        by_region[r] = entry

    valid = [m for m in per_class.values() if m.get("status") == EVALUATED]
    report["metrics"] = {
        "per_class": per_class,
        "by_region": by_region,
        "headline": {
            "mAP50": round(sum(m["mAP50"] for m in valid) / len(valid), 4) if valid else None,
            "mAP50_95": round(sum(m["mAP50_95"] for m in valid) / len(valid), 4) if valid else None,
        },
    }
    report["status"] = EVALUATED if valid else NOT_EVALUATED
    report["elapsed_seconds"] = round((datetime.now() - t0).total_seconds(), 1)
    report["claim_boundary"] = (
        "本结果是**第三方公开数据集**（SC-FloatWaste，非连江海域、非本项目设备）上的"
        "独立测试集精度。只能表述为『在公开漂浮垃圾基准上的独立评测精度』；"
        "不得表述为『连江现场验证』『真实海域验证』或『本项目设备实测精度』。"
        "开放词汇通道为零样本，未使用本测试集训练或调参。"
    )
    if args.tag:
        report["tag"] = args.tag

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    print("\n== 结果 ==")
    print("  status=%s  样本=%d  真值框=%d  检测=%d"
          % (report["status"], len(gt_by_img), n_gt, n_det))
    for cls, m in per_class.items():
        if m.get("status") == EVALUATED:
            print("  %-14s mAP50=%.4f  mAP50-95=%.4f  bestF1=%s"
                  % (cls, m["mAP50"], m["mAP50_95"], m["best_f1"].get("f1")))
        else:
            print("  %-14s not_evaluated (%s)" % (cls, m.get("reason")))
    print("  → %s" % args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
