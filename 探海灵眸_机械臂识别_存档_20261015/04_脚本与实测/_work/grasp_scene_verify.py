"""验证三项新功能：手动调参(tuning.json) / 一键场景校准 / 登记训练产物。

注意：会真跑一次 calibrate 档（会写 models/active/tuning.json）——跑完本脚本
会提示把该文件删掉以恢复基线。
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8090"
TUNING = pathlib.Path(r"c:\Users\Liii\Desktop\seahawk\edge\grasp\models\active\tuning.json")


def call(method: str, path: str, body: dict | None = None, timeout: float = 120.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except ValueError:
                return resp.status, raw[:150]
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except ValueError:
            return exc.code, b""
    except Exception as exc:                              # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def live() -> dict:
    _, s = call("GET", "/api/status")
    d = (s or {}).get("detector", {}) if isinstance(s, dict) else {}
    return {"conf": d.get("conf_threshold"), "iou": d.get("iou_threshold"), "roi": d.get("roi")}


def show(label: str, status: int, payload) -> None:
    body = json.dumps(payload, ensure_ascii=False)[:150] if isinstance(payload, dict) else str(payload)[:150]
    print(f"[{status}] {label}\n      {body}", flush=True)


def main() -> None:
    print("== 1) 初始状态 ==", flush=True)
    show("GET /api/tuning", *call("GET", "/api/tuning"))
    print("   /api/status.detector:", live(), flush=True)

    print("\n== 2) 手动设 conf=0.35 + ROI(0.2,0.3,0.4,0.4) → 应立刻生效 ==", flush=True)
    show("POST /api/tuning", *call("POST", "/api/tuning",
                                   {"conf_threshold": 0.35, "roi": [0.2, 0.3, 0.4, 0.4]}))
    print("   /api/status.detector:", live(), flush=True)
    print("   tuning.json:", TUNING.read_text(encoding="utf-8").replace("\n", " ")
          if TUNING.exists() else "MISSING", flush=True)

    print("\n== 3) 取消 ROI → 应真的清掉（Detector 长驻，会叠加）==", flush=True)
    show("POST /api/tuning clear_roi", *call("POST", "/api/tuning", {"clear_roi": True}))
    print("   /api/status.detector:", live(), flush=True)

    print("\n== 4) 非法 ROI 应被拒 ==", flush=True)
    show("roi 只有 2 个值", *call("POST", "/api/tuning", {"roi": [0.1, 0.2]}))
    show("roi 越界", *call("POST", "/api/tuning", {"roi": [0.1, 0.2, 0.5, 2.0]}))

    print("\n== 5) 一键场景校准（真跑 calibrate 档，限定真实照片那次会话）==", flush=True)
    SESSION = "20261015_144012_real_demo"
    show("POST /api/train tier=calibrate",
         *call("POST", "/api/train", {"tier": "calibrate", "session": SESSION}))
    for _ in range(240):
        time.sleep(1)
        _, st = call("GET", "/api/status")
        job = (st or {}).get("job") or {}
        if not job.get("running"):
            print(f"   job 结束：kind={job.get('kind')} stage={job.get('stage')} "
                  f"error={job.get('error')}", flush=True)
            print("   log:", json.dumps(job.get("log"), ensure_ascii=False)[:400], flush=True)
            break

    print("\n== 6) 校准结果应体现在 /api/tuning（含 sweep + ROI）==", flush=True)
    _, t = call("GET", "/api/tuning")
    if isinstance(t, dict):
        print(f"   conf={t.get('conf_threshold')} iou={t.get('iou_threshold')} "
              f"roi={t.get('roi')} chosen_by={t.get('chosen_by')}", flush=True)
        print("   sweep:", json.dumps(t.get("sweep"), ensure_ascii=False)[:400], flush=True)
    else:
        print("   ", t, flush=True)
    print("   /api/status.detector:", live(), flush=True)

    print("\n== 7) 登记训练产物（未接界面前是死接口）==", flush=True)
    show("缺 model_path", *call("POST", "/api/deploy-from", {}))
    show("路径不存在", *call("POST", "/api/deploy-from", {"model_path": "no/such/model.onnx"}))


if __name__ == "__main__":
    main()
