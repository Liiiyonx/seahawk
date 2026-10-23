"""收尾验证：
  1) 定位 AP50 口径差 —— 同模型同数据，只改 NMS IoU / conf 取值，看自研口径能否逼近 ultralytics。
     已知参照：ultralytics val on 同一 ONNX @416 → mAP50 0.3676。
  2) 换数据后复验 —— 新 built/val（真实照片）现在应能被真实检出，不再是空屏。
"""
from __future__ import annotations

import pathlib
import sys

WORK = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
EDGE = WORK.parent / "edge"
sys.path.insert(0, str(EDGE))

from grasp.config import load_config                      # noqa: E402
from grasp.vision.detector import Detector               # noqa: E402
from grasp_detect_run import DATA, full_eval, run_group  # noqa: E402


def ap_sweep() -> None:
    test_imgs = sorted((DATA / "public_plastic" / "images" / "test").glob("*.*"))
    labels = DATA / "public_plastic" / "labels" / "test"
    cfg = load_config()
    print("== 1) AP50 口径差定位（ultralytics 参照 = 0.3676）==")
    for iou, low in ((0.45, 0.05), (0.70, 0.05), (0.70, 0.001), (0.90, 0.05)):
        det = Detector(cfg, mock=False)
        det.load()
        det.iou_threshold = iou
        ev = full_eval(det, test_imgs, labels, low_conf=low)
        p50, r50 = ev["p50_r50"]
        print(f"  NMS IoU={iou:<4} conf下限={low:<5} → AP50={ev['ap50']:.4f}  "
              f"conf0.50 P={p50:.3f} R={r50:.3f}  候选={ev['n_pred']}")


def verify_new_data() -> None:
    val_imgs = sorted((DATA / "built" / "images" / "val").glob("*.*"))
    labels = DATA / "built" / "labels" / "val"
    cfg = load_config()
    det = Detector(cfg, mock=False)
    det.load()
    print(f"\n== 2) 换数据后复验：built/val（真实照片，{len(val_imgs)} 张）==")
    run_group("B · built/val（真实照片）", "B_real_demo", val_imgs, labels, det)


if __name__ == "__main__":
    ap_sweep()
    verify_new_data()
