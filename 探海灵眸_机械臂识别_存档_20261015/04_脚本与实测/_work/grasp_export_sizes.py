"""按不同输入边长重导 ONNX（416 基线 / 640 / 768），供分辨率对比实测。

为什么可以重导：训练用的 best.pt 在盘上（D:\\seahawk-work\\runs\\plastic_color_v4\\weights\\best.pt），
且 args.yaml 显示**训练 imgsz=768** —— 当年部署却导出了 416，属于白丢分辨率。
本脚本把 .pt 拷进每个尺寸各自的英文临时目录后再导出，避免 ultralytics
把 best.onnx 写回权重目录、覆盖掉 416 基线导出。

★ 中文路径坑：源在 D 盘英文路径，输出也在 _work 英文路径，全程无中文。
"""
from __future__ import annotations

import pathlib
import shutil
import sys

SRC_PT = pathlib.Path(r"D:\seahawk-work\runs\plastic_color_v4\weights\best.pt")
ROOT = pathlib.Path(__file__).resolve().parent / "onnx_export"

SIZES = (416, 640, 768)


def main() -> None:
    if not SRC_PT.exists():
        raise SystemExit(f"源 .pt 不存在：{SRC_PT}")
    from ultralytics import YOLO

    for n in SIZES:
        out_dir = ROOT / f"n{n}"
        out_dir.mkdir(parents=True, exist_ok=True)
        pt = out_dir / "best.pt"
        if not pt.exists():
            shutil.copy2(SRC_PT, pt)
        model = YOLO(str(pt))
        onnx = out_dir / "best.onnx"
        if onnx.exists():
            print(f"[{n}] 已存在，跳过：{onnx}", flush=True)
            continue
        try:
            produced = model.export(format="onnx", imgsz=n, opset=12,
                                    simplify=True, dynamic=False, half=False,
                                    device="cpu")
        except Exception as exc:                                   # noqa: BLE001
            print(f"[{n}] simplify=True 导出失败（{exc}），退回 simplify=False", flush=True)
            produced = model.export(format="onnx", imgsz=n, opset=12,
                                    simplify=False, dynamic=False, half=False,
                                    device="cpu")
        produced = pathlib.Path(str(produced))
        if produced.resolve() != onnx.resolve():
            shutil.move(str(produced), str(onnx))
        print(f"[{n}] 导出完成：{onnx} （{onnx.stat().st_size} bytes）", flush=True)

    print("\n全部导出结果：")
    for n in SIZES:
        p = ROOT / f"n{n}" / "best.onnx"
        print(f"  imgsz={n:4d} -> {p}  exists={p.exists()}", flush=True)
    return None


if __name__ == "__main__":
    sys.exit(main())
