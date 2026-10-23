#!/usr/bin/env python3
"""泳池域「部署推理路径」验证（薄壳：算法实际在 ``grasp/vision/sweep.py``）。

## 为什么还要单独测一遍

``vision/evaluate.py`` 走 ultralytics 自带的 ONNX 推理（它有自己的 letterbox 与后处理）；
现场跑的是 ``Detector``（``cv2.dnn`` + 自写 letterbox/解码/按类 NMS）。**两者不是
一回事** —— ultralytics 上的高分不能证明部署链路也对（类别索引错位、letterbox 偏移、
输出维度反了、类别无关 NMS 吞框，都只会在部署链路上暴露）。实测过：同一次预测在两条
链路上的召回差 0.13。

本工具就测部署链路本身，并按「机械臂误抓代价高」的口径把**精确率**摊开看：不仅报
塑料袋类的 P/R/F1，还把误检分成「落在其他类物体上」与「落在纯背景上」。

算法与阈值档位已收敛到 ``grasp/vision/sweep.py``（与作业台的扫描端点共用同一份实现），
本文件只负责参数解析与打印，保持输出格式与历史一致。

用法::

    python edge/grasp/tools/verify_pool_model.py                  # 测 models/active 里那份
    python edge/grasp/tools/verify_pool_model.py --limit 60 --json-out _work/pool_verify.json

口径：数据集是**当前组装好的**留出集（``data/built``）；结论只说明部署链路在这批帧上
工作正常，**不是现场精度**。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRASP_DIR = HERE.parent
for _p in (str(GRASP_DIR), str(GRASP_DIR.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from grasp.config import load_config                 # noqa: E402
from grasp.vision.detector import DetectorError      # noqa: E402
from grasp.vision.sweep import run_deployment_sweep  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="泳池域部署推理路径验证（cv2.dnn + Detector）")
    ap.add_argument("--config", default=None)
    ap.add_argument("--model", default=None, help="指定 .onnx；默认用 models/active")
    ap.add_argument("--split", default="val", help="测哪个划分（默认 val 留出集）")
    ap.add_argument("--limit", type=int, default=0, help="只测前 N 张（0=全部）")
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    try:
        r = run_deployment_sweep(cfg, split=args.split, limit=args.limit, iou=args.iou,
                                 model_path=args.model)
    except DetectorError as exc:
        print(f"[错误] {exc}")
        return 2

    print(f"[模型] backend={r['backend']} input={r['input_size']} classes={r['classes']}")
    print(f"[数据] {r['split']} 集 {r['images']} 张 | {r['target_class']} 真值 "
          f"{r['gt_target']} 框 | 其他类真值 {r['gt_other']} 框 | "
          f"纯背景帧 {r['background_frames']} 张")

    print("\n[部署链路] 阈值扫描（只看塑料袋类；机械臂场景看 P 优先）")
    print("  conf |   TP |   FP |   FN |    P   |    R   |   F1  | 命中帧")
    for row in r["scan"]:
        print(f"  {row['conf']:.2f} | {row['tp']:>4} | {row['fp']:>4} | {row['fn']:>4} | "
              f"{row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} | "
              f"{row['hit_frames']}/{r['images']}")

    best = r["best_f1"]
    print(f"\n  F1 最优: conf={best['conf']:.2f} P={best['precision']:.3f} "
          f"R={best['recall']:.3f} F1={best['f1']:.3f}"
          f"（其中误检落在彩色浮标 {best['fp_other']}、纯背景 {best['fp_background']}）")

    cur = r["current"]
    print(f"  当前配置 conf={r['current_conf']:.2f}：P={cur['precision']:.3f} "
          f"R={cur['recall']:.3f}（tp={cur['tp']} fp={cur['fp']} fn={cur['fn']}）")
    print(f"\n  判定：{r['verdict']}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(r, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
        print(f"[写出] {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
