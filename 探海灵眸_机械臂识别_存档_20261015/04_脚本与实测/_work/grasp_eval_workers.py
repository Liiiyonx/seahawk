"""确认 evaluate() 卡死的根因：ultralytics val 默认 workers>0 → Windows spawn 多进程。

在脚本里调用时，spawn 会重新导入主模块；若主模块没有 `if __name__ == "__main__"`
守卫，子进程会重入同样的代码 → 永久等待/递归。服务进程里调用则是另一种表现形式。

这里加守卫 + workers=0 对照跑一次。
"""
from __future__ import annotations

import pathlib
import sys
import time

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"

if __name__ == "__main__":
    warnings = __import__("warnings")
    warnings.filterwarnings("ignore")
    from ultralytics import YOLO

    model = EDGE / "grasp" / "models" / "active" / "best.onnx"
    yaml_path = EDGE / "grasp" / "data" / "built" / "data.yaml"

    for workers in (0,):
        t0 = time.time()
        yolo = YOLO(str(model), task="detect")
        res = yolo.val(data=str(yaml_path), split="val", imgsz=416,
                       verbose=False, plots=False, workers=workers)
        print(f"workers={workers} → map50={res.box.map50:.4f} "
              f"耗时 {time.time() - t0:.1f}s", flush=True)
