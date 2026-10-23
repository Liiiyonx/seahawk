"""在「演示场景域」数据集上微调 YOLO11s（2 类：塑料袋 + 浮标负类），导出 ONNX@640。

为什么从当前 active 的 best.pt 续训而不是从零：
  * 它已经学过「塑料袋」的纹理特征（SC-FloatWaste 那套），骨干+颈部值得保留；
  * 类别数 1→2 会让 ultralytics 重建检测头，但特征层照旧复用。

产出去 D 盘（英文路径），不落仓库，避免把大权重混进 git。
"""
from __future__ import annotations

import pathlib
import shutil
import sys

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
sys.path.insert(0, str(EDGE))

# 续训基座：优先 active 目录里的 .pt（现场再训练口径）；没有就退回盘上那份训练产出的 .pt
_BASE_CANDIDATES = (
    EDGE / "grasp" / "models" / "active" / "best.pt",
    pathlib.Path(r"D:\seahawk-work\runs\plastic_color_v4\weights\best.pt"),
)
BASE_PT = next((p for p in _BASE_CANDIDATES if p.exists()), _BASE_CANDIDATES[0])
DATA_YAML = EDGE / "grasp" / "data" / "built" / "data.yaml"
OUT_ROOT = pathlib.Path(r"D:\seahawk-work\runs")
NAME = "grasp_domain_2cls"
IMGSZ = 640
EPOCHS = 60
BATCH = 12


def main() -> None:
    if not BASE_PT.exists():
        raise SystemExit(f"缺少续训基座权重：{BASE_PT}")
    if not DATA_YAML.exists():
        raise SystemExit(f"缺少数据集描述：{DATA_YAML} —— 先跑 _work/grasp_build_domain.py")
    from ultralytics import YOLO

    model = YOLO(str(BASE_PT))
    results = model.train(
        data=str(DATA_YAML),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        project=str(OUT_ROOT),
        name=NAME,
        exist_ok=True,
        seed=0,
        device="0",
        workers=2,
        verbose=True,
    )
    save_dir = pathlib.Path(str(getattr(results, "save_dir", "") or ""))
    best_pt = save_dir / "weights" / "best.pt"
    print(f"\nbest.pt: {best_pt}  exists={best_pt.exists()}")

    onnx = pathlib.Path(model.export(format="onnx", imgsz=IMGSZ, opset=12,
                                     simplify=True, dynamic=False, half=False, device="cpu"))
    print(f"onnx: {onnx}  exists={onnx.exists()}")

    # 归拢到固定目录，方便下一步部署脚本引用
    stage = OUT_ROOT / NAME / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    if best_pt.exists():
        shutil.copy2(best_pt, stage / "best.pt")
    if onnx.exists():
        shutil.copy2(onnx, stage / "best.onnx")
    print(f"已归拢：{stage}")


if __name__ == "__main__":
    main()
