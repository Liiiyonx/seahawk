"""定位 /api/evaluate 卡在哪：挂个 60s 的栈转储，卡住就把调用栈打出来。"""
from __future__ import annotations

import faulthandler
import pathlib
import sys
import time

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
sys.path.insert(0, str(EDGE))

faulthandler.dump_traceback_later(60, exit=True)

from grasp.config import load_config            # noqa: E402
from grasp.vision.evaluate import evaluate      # noqa: E402

cfg = load_config()
print("开始评估（最多等 60s，卡住会打印调用栈）…", flush=True)
t0 = time.time()
metrics = evaluate(cfg)
print(f"评估完成，耗时 {time.time() - t0:.1f}s: {metrics}", flush=True)
