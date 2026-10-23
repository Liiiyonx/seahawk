"""用 ultralytics 自己的 val 口径，对**同一个部署 ONNX**测 AP50 —— 与自研 cv2.dnn 口径对齐。"""
from __future__ import annotations

import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
import logging

logging.disable(logging.CRITICAL)

from ultralytics import YOLO

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
GRASP = EDGE / "grasp"
YAML = GRASP / "data" / "public_plastic" / "data.yaml"

TARGETS = [
    ("部署 ONNX @416", GRASP / "models" / "active" / "best.onnx"),
    ("版本 v20261015_113323 ONNX @416", GRASP / "models" / "versions" / "v20261015_113323" / "best.onnx"),
]


def main() -> None:
    for tag, model in TARGETS:
        if not model.exists():
            print(f"{tag}: 文件不存在 {model}", flush=True)
            continue
        print(f"\n=== {tag} ===\n{model}", flush=True)
        try:
            m = YOLO(str(model), task="detect")
            r = m.val(data=str(YAML), split="test", imgsz=416, verbose=False,
                      plots=False, save_json=False, device="cpu")
        except Exception as exc:  # noqa: BLE001
            print(f"  val 失败: {type(exc).__name__}: {exc}", flush=True)
            continue
        b = r.box
        print("  mAP50=%.4f  mAP50-95=%.4f  P=%.4f  R=%.4f" %
              (b.map50, b.map, b.mp, b.mr), flush=True)


if __name__ == "__main__":
    main()
