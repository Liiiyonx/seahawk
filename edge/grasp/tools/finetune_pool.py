#!/usr/bin/env python3
"""「泳池微调」一键脚本：在泳池域数据上微调塑料袋检测模型，产出可部署的 ONNX。

一条命令走完：**组装数据集 → 训练 → 留出集评估 → 导出 ONNX → （可选）原子部署**。

## 两种用法，同一个脚本

* **合成泳池域**（无真机、无泳池时的管线验证）
  ``python edge/grasp/tools/gen_pool_dataset.py --count 600 --tag pool_synth --build``
  ``python edge/grasp/tools/finetune_pool.py --session <上面那个会话名> --epochs 80``
* **现场泳池**（真机 + 泳池到位后，按《探海灵眸_充气泳池采集规程》采完帧并标注）
  ``python edge/grasp/tools/finetune_pool.py --session <采集会话> --epochs 80 --deploy``

## 为什么分辨率必须 640

``config.yaml`` 的 ``vision.input_size`` 是 640，``Detector`` 按它做 letterbox、
导出的 ONNX 输入边长必须一致，否则 ``cv2.dnn`` 直接报维度不匹配。
本脚本默认训练与导出都用 640，**两者一致**；要改就同时改 config。

## 证据等级（必读）

合成帧训出的模型只在合成分布内有效，证据等级上限 **E1/E2**，
对外只能表述为「管线验证 / 演示模型」，**不得写成现场精度**。
现场泳池属受控环境，按 ``quasi_real`` / E2 记；真机真实场景才够 E3。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRASP_DIR = HERE.parent
EDGE_DIR = GRASP_DIR.parent
for path in (str(EDGE_DIR), str(GRASP_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

REPO_ROOT = EDGE_DIR.parent


def _default_base() -> str:
    """续训起点：优先仓库根的 yolo11s.pt（本机无外网，必须预置），退回 ultralytics 默认。"""
    cand = REPO_ROOT / "yolo11s.pt"
    return str(cand) if cand.exists() else "yolo11s.pt"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="泳池域塑料袋检测模型微调（train→eval→export→deploy）")
    ap.add_argument("--config", default=None, help="配置文件（默认 edge/grasp/config.yaml）")
    ap.add_argument("--session", action="append", default=None,
                    help="只组装该采集会话（可重复传入多个）；省略=全部有标注的帧")
    ap.add_argument("--group-split", action="store_true",
                    help="按采集单元（会话）整组切 train/val，不逐帧洗牌 —— "
                         "现场视频流采集必须开，否则相邻帧泄漏进 val")
    ap.add_argument("--no-build", action="store_true", help="不重新组装，直接用现有 data/built")
    ap.add_argument("--dataset-yaml", default=None,
                    help="直接用这份 YOLO data.yaml 训练（如 TACO 底料集），跳过组装")
    ap.add_argument("--mix-dataset-yaml", action="append", default=None,
                    help="把另一份 YOLO data.yaml 的图像混进训练（replay，如 TACO 真实照片"
                         "底料）；可重复。混采能避免「只拿合成域微调」把底料的真实域"
                         "能力灾难性遗忘掉。要求追加集类名是主集的子集")
    ap.add_argument("--onnx", default=None,
                    help="跳过训练与导出，直接用这份 ONNX 跑「评估→门禁→部署」")
    ap.add_argument("--base", default=None, help="续训起点权重；默认仓库根 yolo11s.pt")
    ap.add_argument("--imgsz", type=int, default=640, help="训练与导出分辨率（默认 640）")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--device", default="0", help="'0'=首块 GPU，'cpu'=CPU")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--project", default=None, help="训练输出根目录（默认 edge/grasp/runs）")
    ap.add_argument("--name", default="pool", help="本次训练目录名")
    ap.add_argument("--deploy", action="store_true", help="评估过门禁后原子部署")
    ap.add_argument("--force", action="store_true", help="门禁未过也强行部署（用于演示兜底）")
    ap.add_argument("--min-map50", type=float, default=0.60, help="部署门禁 mAP50")
    ap.add_argument("--min-recall", type=float, default=0.0, help="部署门禁召回下限")
    ap.add_argument("--min-precision", type=float, default=0.85,
                    help="部署门禁精确率下限（机械臂误抓代价高，精确率是主指标）")
    ap.add_argument("--note", default="", help="版本备注（写进模型版本元数据）")
    ap.add_argument("--summary", default=None, help="把本次运行摘要写到该 JSON 路径")
    args = ap.parse_args(argv)

    from grasp.config import load_config
    from grasp.vision.dataset import Dataset
    from grasp.vision.deploy import ModelStore
    from grasp.vision.evaluate import evaluate, passes
    from grasp.vision.mix import MixError, mix_datasets

    cfg = load_config(args.config)
    dataset = Dataset.from_config(cfg)
    base = args.base or _default_base()

    # ---------- 1) 组装数据集 ----------
    if args.dataset_yaml:
        yaml_path = Path(args.dataset_yaml)
        if not yaml_path.exists():
            print(f"[错误] --dataset-yaml 指向的文件不存在: {yaml_path}")
            return 2
        stats = {"external_yaml": True, "data_yaml": str(yaml_path)}
    elif args.no_build:
        yaml_path = dataset.built_dir / "data.yaml"
        if not yaml_path.exists():
            print(f"[错误] 未找到已组装数据集: {yaml_path}（去掉 --no-build 重新组装）")
            return 2
        stats = {"reused": True, "data_yaml": str(yaml_path)}
    else:
        sessions = args.session
        if sessions is not None and len(sessions) == 1:
            sessions = sessions[0]
        stats = dataset.build(session=sessions, group_splits=args.group_split)
    yaml_path = Path(stats["data_yaml"])
    if args.mix_dataset_yaml:
        # 混采实现已搬到 grasp/vision/mix.py：CLI 与控制台共用同一份，避免两处漂移。
        # 失败是 MixError（不是 SystemExit）—— 作业台那边只捕 Exception，用 SystemExit
        # 会让后台任务停在 starting 且不报错。
        try:
            mixed = mix_datasets(yaml_path, [Path(p) for p in args.mix_dataset_yaml],
                                 dataset.root / "built_mixed")
        except MixError as exc:
            print(f"[错误] 混采不可行：{exc}")
            return 2
        yaml_path = Path(mixed["data_yaml"])
        print(f"[混采] train={mixed['train']} val={mixed['val']} "
              f"来源={mixed['sources']} → {yaml_path}")
    brief = {k: v for k, v in stats.items() if k != "data_yaml"}
    print("[数据集] %s  %s" % (yaml_path, json.dumps(brief, ensure_ascii=False)))

    # ---------- 2) 训练 + 3) 导出 ONNX ----------
    if args.onnx:
        # 复用已有产物：只跑「评估 → 门禁 → 部署」，不重训。
        # 用途：训练已完成但评估/部署那一步失败时（如评估脚本在多变类上崩了），
        # 不必把十几分钟的训练重跑一遍。
        onnx_path = Path(args.onnx)
        if not onnx_path.exists():
            print(f"[错误] --onnx 指向的文件不存在: {onnx_path}")
            return 5
        best_pt = None
        print(f"[跳过训练] 直接用已有 ONNX：{onnx_path}")
    else:
        try:
            from ultralytics import YOLO
        except ImportError:
            print("[错误] 缺少 ultralytics：pip install ultralytics")
            return 3

        project = Path(args.project) if args.project else (GRASP_DIR / "runs")
        print(f"[训练] base={base} imgsz={args.imgsz} epochs={args.epochs} "
              f"batch={args.batch} device={args.device}")
        model = YOLO(base)
        model.train(data=str(yaml_path), epochs=args.epochs, imgsz=args.imgsz,
                    batch=args.batch, workers=args.workers, device=args.device,
                    seed=args.seed, project=str(project), name=args.name,
                    exist_ok=True, verbose=True)

        best_pt = project / args.name / "weights" / "best.pt"
        if not best_pt.exists():
            print(f"[错误] 训练结束但未找到 best.pt: {best_pt}")
            return 4

        print(f"[导出] ONNX imgsz={args.imgsz}")
        exported = YOLO(str(best_pt)).export(format="onnx", imgsz=args.imgsz,
                                             half=False, dynamic=False)
        onnx_path = Path(str(exported))
        if not onnx_path.exists():
            print(f"[错误] ONNX 导出失败: {exported}")
            return 5

    # ---------- 4) 留出集评估（部署门禁依据） ----------
    metrics = evaluate(cfg, model_path=onnx_path, dataset_yaml=yaml_path)
    print(f"[评估] mAP50={metrics['map50']} mAP50-95={metrics['map50_95']} "
          f"P={metrics['precision']} R={metrics['recall']} ({metrics['split']} 划分)")
    if args.mix_dataset_yaml:
        print("[评估] ⚠ 上面的数字是**混采 val（两域合并）**，不能当泳池域指标读；"
              "泳池域与真实照片域必须分别测（verify_pool_model.py + TACO data.yaml）。")

    ok, reason = passes(metrics, args.min_map50, args.min_recall, args.min_precision)
    print(f"[门禁] {'通过' if ok else '未过'} — {reason}")

    out = {
        "session": args.session,
        "base": base,
        "imgsz": args.imgsz,
        "epochs": args.epochs,
        "best_pt": str(best_pt) if best_pt else None,
        "onnx": str(onnx_path),
        "metrics": metrics,
        "gate": {"passed": ok, "reason": reason, "min_map50": args.min_map50,
                 "min_recall": args.min_recall, "min_precision": args.min_precision},
        "dataset": stats if isinstance(stats, dict) else {},
        "evidence_level": "E1(synthetic)",
        "note": args.note,
    }

    # ---------- 5) 原子部署 ----------
    if args.deploy:
        if not ok and not args.force:
            print("[部署] 已中止：门禁未过（如确需兜底，显式加 --force）")
        else:
            store = ModelStore.from_config(cfg)
            meta = store.deploy(onnx_path, metrics=metrics,
                                note=args.note or f"泳池域微调 {args.session or 'all'}")
            out["deployed"] = meta
            print(f"[部署] 版本 {meta['version']} → active（回滚：作业台"
                  f"「4 · 部署与回滚」，或 ModelStore.rollback()）")

    if args.summary:
        sp = Path(args.summary)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[摘要] 已写入 {sp}")
    print(json.dumps({k: v for k, v in out.items() if k not in ("dataset",)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
