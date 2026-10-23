"""部署推理链路的阈值扫描：用现场真正跑的那条路（``cv2.dnn`` + ``Detector``）测留出集。

## 为什么要单独一条链路

``vision/evaluate.py`` 走的是 **ultralytics 自带的 ONNX 推理**（它有自己的 letterbox
与后处理）；现场跑的是 ``Detector``：``cv2.dnn`` + 自写 letterbox + 自解
``(1, 4+nc, N)`` 头 + 按类 NMS。**两者的前后处理不是一回事** —— ultralytics 上
0.99 的 mAP50 不能证明 ``cv2.dnn`` 那条路也对。实测过一个反例：同一次预测在两条
链路上的召回差了 0.13（0.776 vs 0.908，原因是按类 NMS 的修复）。

所以「评估」与「部署链路扫描」是**两份证据**，界面上必须分别标名，不能互相替代。

## 两条硬纪律

1. **永远新建 ``Detector``，绝不复用作业台那个长驻实例**。扫描要把
   ``conf_threshold`` 压到 ``SCAN_FLOOR`` 才能拿到完整 PR 曲线；复用长驻对象会让
   实时画面叠加与抓取闭环按 0.05 阈值乱抓，异常时还会把错误阈值永久留在对象上
   —— 正是仓库最忌讳的「按钮看着成功、实际留下一个静默错误状态」。
2. **只认 onnx/ncnn 后端**。扫描测的就是部署链路；退化成 mock/ultralytics/none
   产出的表「看起来是部署链路结论、其实是另一条路」，宁可硬失败并说明原因。
   （与 ``tools/precheck.py`` 同一条纪律：即使 ``--mock`` 也按**真模型**检查。）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Sequence

from . import metrics
from .dataset import Dataset
from .detector import Detector, DetectorError

logger = logging.getLogger("oceanus.grasp.sweep")

ProgressCb = Callable[[int, int, dict[str, Any]], None]


def load_deployment_detector(cfg: dict[str, Any],
                             model_path: str | Path | None = None) -> Detector:
    """新建一个走部署链路的检测器（见模块头部纪律 1 与 2）。"""
    import cv2

    det = Detector(cfg, mock=False)
    if model_path:
        p = Path(model_path)
        if p.suffix != ".onnx":
            raise DetectorError(
                f"部署链路扫描只支持 .onnx（要测的就是 cv2.dnn 那条路），收到 {p.suffix!r}"
            )
        if not p.exists():
            raise DetectorError(f"模型不存在: {p}")
        det.model_dir = p.parent
        try:
            det._net = cv2.dnn.readNetFromONNX(str(p))
        except Exception as exc:  # noqa: BLE001
            raise DetectorError(f"ONNX 加载失败 {p}: {exc}") from exc
        det.backend, det.model_path = "onnx", str(p)
        det._apply_tuning()
    else:
        det.load()

    if det.backend not in ("onnx", "ncnn"):
        raise DetectorError(
            f"检测后端是 {det.backend!r} —— 扫描测的就是现场真正跑的那条推理链"
            "（cv2.dnn / ncnn）；用 mock / ultralytics / 无模型算出来的表不是部署结论。"
            "请先在「4 部署与回滚」部署一份 best.onnx，或用 --model 指定。"
        )
    return det


def collect_raw(det: Detector, img_dir: Path, lbl_dir: Path,
                limit: int = 0, progress_cb: Callable[[int, int], None] | None = None
                ) -> list[dict[str, Any]]:
    """把留出集的原始检出缓存下来（每张图推理一次，后续扫阈值不再重复前向）。

    ★ 提供 ``progress_cb`` 的理由：整个扫描的墙钟时间**几乎全花在这一步**
    （每张图一次 cv2.dnn 前向），而后面 11 档阈值只做匹配、瞬间跑完。不报这一步
    的进度，界面就会在最长的那段里一直显示"没动过"，看起来像卡住。
    """
    import cv2

    images = sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.png"))
    if limit:
        images = images[:limit]
    total = len(images)
    raw: list[dict[str, Any]] = []
    for i, p in enumerate(images, 1):
        img = cv2.imread(str(p))
        if img is None:
            if progress_cb:
                progress_cb(i, total)
            continue
        h, w = img.shape[:2]
        raw.append({
            "name": p.name,
            "gt": metrics.load_yolo_gt(lbl_dir / f"{p.stem}.txt", w, h),
            "preds": [(d.conf, (d.x1, d.y1, d.x2, d.y2), d.cls) for d in det.infer(img)],
        })
        if progress_cb:
            progress_cb(i, total)
    return raw


def run_deployment_sweep(cfg: dict[str, Any], *, split: str = "val", limit: int = 0,
                         iou: float = 0.5, model_path: str | Path | None = None,
                         thresholds: Sequence[float] | None = None,
                         min_precision: float | None = None,
                         min_recall: float | None = None,
                         progress_cb: ProgressCb | None = None,
                         collect_cb: Callable[[int, int], None] | None = None
                         ) -> dict[str, Any]:
    """在 ``data/built/images/<split>`` 上扫阈值，返回扫描表与判定。

    ``min_precision`` / ``min_recall`` 为 ``None`` 时用工具的历史口径
    ``P>=0.90 且 R>=0.80``（CLI 输出因此保持原样）；控制台传操作员自己的门禁值，
    后端不写死数字。

    ``progress_cb`` 报每档阈值的完成情况；``collect_cb`` 报取图/前向进度
    （那一步才是耗时大头）。
    """
    dataset = Dataset.from_config(cfg)
    img_dir = dataset.built_dir / "images" / split
    lbl_dir = dataset.built_dir / "labels" / split
    if not img_dir.exists() or not any(img_dir.iterdir()):
        raise DetectorError(f"找不到 {split} 图像：{img_dir}（先在训练任务里组装数据集）")

    det = load_deployment_detector(cfg, model_path)
    cfg_conf = float(det.conf_threshold)      # ★ 先存配置阈值：下面会把它压到下限
    det.conf_threshold = metrics.SCAN_FLOOR
    raw = collect_raw(det, img_dir, lbl_dir, limit, collect_cb)
    if not raw:
        raise DetectorError(f"{img_dir} 下没有可读图像")

    target_idx = det.classes.index(det.target_class) if det.target_class in det.classes else 0
    ths = tuple(thresholds) if thresholds else metrics.DEPLOY_THRESHOLDS
    # 只把目标类的检出送进匹配：非目标类（如 buoy 负类）本来就不该进入抓取候选，
    # 但「它被检出了」这件事由类别门控处理，不该混进塑料袋的精确率分子分母。
    filtered = [{"gt": r["gt"],
                 "preds": [(c, b) for c, b, cls in r["preds"] if cls == det.target_class]}
                for r in raw]

    rows: list[dict[str, Any]] = []
    for i, t in enumerate(ths, 1):
        row = metrics.scan_rows(filtered, thresholds=[float(t)], iou=iou,
                                target_idx=target_idx, split_fp_by_other=True)[0]
        rows.append(row)
        if progress_cb:
            progress_cb(i, len(ths), row)

    n_gt_target = sum(len(r["gt"].get(target_idx, [])) for r in raw)
    n_gt_other = sum(len(v) for r in raw for ci, v in r["gt"].items() if ci != target_idx)
    n_bg_frames = sum(1 for r in raw if not any(r["gt"].values()))
    best = max(rows, key=lambda r: r["f1"])
    cur = min(rows, key=lambda r: abs(r["conf"] - cfg_conf))
    mp = 0.90 if min_precision is None else float(min_precision)
    mr = 0.80 if min_recall is None else float(min_recall)
    ok = cur["precision"] >= mp and cur["recall"] >= mr
    verdict = (f"通过（P≥{mp:.2f} 且 R≥{mr:.2f}）" if ok
               else f"不达标（P≥{mp:.2f} 且 R≥{mr:.2f}）")

    result = {
        "model": det.model_path, "backend": det.backend, "split": split,
        "input_size": det.input_size, "classes": list(det.classes),
        "target_class": det.target_class,
        "images": len(raw), "gt_target": n_gt_target, "gt_other": n_gt_other,
        "background_frames": n_bg_frames, "scan": rows, "best_f1": best,
        "current_conf": cfg_conf, "current": cur, "passed": ok, "verdict": verdict,
        "gate": {"min_precision": mp, "min_recall": mr},
        "claim_boundary": ("测的是部署推理链路（cv2.dnn + Detector）；"
                           "数据集是当前组装好的留出集，不代表现场精度"),
    }
    logger.info("部署链路扫描完成：%d 档，当前 conf=%.2f → P=%.3f R=%.3f（%s）",
                len(rows), cfg_conf, cur["precision"], cur["recall"], verdict)
    return result
