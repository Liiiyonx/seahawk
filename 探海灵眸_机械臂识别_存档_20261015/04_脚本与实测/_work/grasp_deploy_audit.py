"""补测三颗「写操作」按钮：评估 / 部署 / 回滚（逐条即时打印，避免再盲等）。

安全说明：models/ 与 runs/ 都在 .gitignore 里，部署只会把同一份 best.onnx
再登记成一个新版本；测完用 rollback 回到原版本，并删掉新建的版本目录。
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8090"
VERSIONS_DIR = pathlib.Path(r"c:\Users\Liii\Desktop\seahawk\edge\grasp\models\versions")


def call(method: str, path: str, body: dict | None = None, timeout: float = 180.0):
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
                return resp.status, raw[:200]
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except ValueError:
            return exc.code, b""
    except Exception as exc:                       # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def line(label: str, status: int, payload) -> None:
    extra = ""
    if isinstance(payload, dict):
        if "reason" in payload:
            extra = f"reason={payload['reason']} metrics.map50={payload.get('metrics', {}).get('map50')}"
        elif "gate" in payload:
            extra = f"gate={payload['gate']} version={(payload.get('version') or {}).get('version')}"
        elif "detail" in payload:
            extra = f"detail={payload['detail']}"
        elif "version" in payload:
            extra = f"version={payload.get('version')}"
        else:
            extra = json.dumps(payload, ensure_ascii=False)[:110]
    else:
        extra = str(payload)[:110]
    mark = "通  " if 200 <= status < 300 else ("拒绝" if 400 <= status < 500 else "异常")
    print(f"[{mark}] {label:<34} HTTP {status:<4} {extra}", flush=True)


def main() -> None:
    before = sorted(p.name for p in VERSIONS_DIR.iterdir() if p.is_dir())
    print("审计前版本目录：", before, flush=True)

    s, b = call("POST", "/api/evaluate")
    line("评估当前模型", s, b)

    s, b = call("POST", "/api/deploy", {"min_map50": 0.5, "note": "审计"})
    line("部署当前模型（页面默认门禁 0.5）", s, b)
    new_ver = (b.get("version") or {}).get("version") if isinstance(b, dict) else None

    if new_ver is None:
        print("  → 默认门禁被拦下（说明门禁生效）。改用宽松门禁 0.05 复测部署链路…", flush=True)
        s, b = call("POST", "/api/deploy", {"min_map50": 0.05, "note": "审计"})
        line("部署当前模型（门禁 0.05）", s, b)
        new_ver = (b.get("version") or {}).get("version") if isinstance(b, dict) else None

    s, b = call("POST", "/api/rollback", {"version": ""})
    line("回滚上一版", s, b)

    time.sleep(1)
    s, b = call("GET", "/api/versions")
    print("  /api/versions current =", (b or {}).get("current") if isinstance(b, dict) else b, flush=True)
    after = sorted(p.name for p in VERSIONS_DIR.iterdir() if p.is_dir())
    print("审计后版本目录：", after, flush=True)
    added = [x for x in after if x not in before]
    print("新增版本目录：", added, flush=True)


if __name__ == "__main__":
    main()
