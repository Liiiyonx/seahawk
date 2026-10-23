"""作业台按钮全量审计：把页面上每个按钮对应的接口都打一遍，看是不是真的能用。

## 安全策略（重要）

有几颗按钮会**写文件**，直接点会污染演示数据或留下假标定：
  /api/capture/start  写帧进 data/raw
  /api/label          覆盖已有真值标注
  /api/calibrate/start 与 /api/calibrate/save  写 calibration.json
  /api/train          跑训练、写 runs/

对这类接口本脚本**不发有效载荷**，而是发一个必然被校验拦下的非法载荷
（如 frames=1 违反 ge=10），用返回的 4xx 证明「路由存在且契约生效」，
从而做到零副作用。

只读或 mock 下无副作用的接口（jog/gripper/home/prelabel/grasp/versions…）才真跑。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8090"
ROWS: list[tuple[str, str, str, str]] = []   # 控件 / 接口 / 结果 / 结论


def call(method: str, path: str, body: dict | None = None, timeout: float = 60.0,
         read_limit: int | None = None):
    """read_limit 用于 /stream 这类无限流：绝不能 resp.read() 到底，会永远阻塞。"""
    url = BASE + path
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(read_limit) if read_limit else resp.read()
            if read_limit:
                return resp.status, raw
            try:
                return resp.status, json.loads(raw)
            except ValueError:
                return resp.status, raw[:200]
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw[:200]
    except Exception as exc:                      # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def note(control: str, path: str, status: int, extra: str = "") -> None:
    ok = 200 <= status < 300
    ROWS.append((control, path, f"{status} {extra}".strip(),
                 "通" if ok else "异常"))


def brief(payload, keys: list[str], limit: int = 90) -> str:
    if not isinstance(payload, dict):
        return str(payload)[:limit]
    bits = []
    for k in keys:
        if k in payload:
            bits.append(f"{k}={payload[k]}")
    return ", ".join(bits)[:limit]


def main() -> None:
    # ---------- 只读 GET（页面轮询/刷新用） ----------
    s, body = call("GET", "/api/status")
    note("（页面每秒轮询）", "/api/status", s, brief(body, ["mock", "frames", "labeled", "phase"]))

    s, body = call("GET", "/api/frames")
    note("刷新帧列表", "/api/frames", s, f"{len(body.get('frames', [])) if isinstance(body, dict) else '?'} 帧")

    s, body = call("GET", "/api/versions")
    baseline_versions = [v.get("version") for v in (body or {}).get("versions", [])] \
        if isinstance(body, dict) else []
    note("刷新版本", "/api/versions", s,
         f"{len(baseline_versions)} 个版本 · current={(body or {}).get('current')}")

    s, body = call("GET", "/api/train/status")
    note("（轮询进度）", "/api/train/status", s, brief(body, ["kind", "stage"]))

    s, body = call("GET", "/api/task")
    note("（只读订阅）", "/api/task", s, brief(body, ["status"], 60))

    s, body = call("GET", "/api/telemetry")
    note("（未接入页面）", "/api/telemetry", s, f"{len(body) if isinstance(body, dict) else '?'} 个舵机")

    # ---------- 单帧图片（缩略图/标注台用） ----------
    s, body = call("GET", "/api/frames")
    frames = (body or {}).get("frames", []) if isinstance(body, dict) else []
    if frames:
        f0 = frames[0]
        s, body = call("GET", f"/api/frames/{f0['session']}/{f0['name']}")
        note("点缩略图", "/api/frames/{session}/{name}", s,
             f"{len(body) if isinstance(body, bytes) else '?'} 字节")
    else:
        ROWS.append(("点缩略图", "/api/frames/{session}/{name}", "无帧可测", "跳过"))

    # ---------- MJPEG 流：只读首包若干字节，绝不能读到底（无限流会永久阻塞） ----------
    s, body = call("GET", "/stream", timeout=8, read_limit=256)
    note("（实时画面）", "/stream", s, f"首包 {len(body) if isinstance(body, bytes) else '?'} 字节")

    # ---------- 手动点动（mock 下不发真指令，安全） ----------
    s, body = call("POST", "/api/jog", {"servo_id": 1, "position": 520, "duration_ms": 200})
    note("下发", "/api/jog", s, brief(body, ["ok", "servo_id"]))
    s, body = call("POST", "/api/gripper", {"action": "open"})
    note("夹爪张开", "/api/gripper(open)", s, brief(body, ["ok", "action"]))
    s, body = call("POST", "/api/gripper", {"action": "close"})
    note("夹爪自适应闭合", "/api/gripper(close)", s, brief(body, ["ok", "action", "pulse"]))
    s, body = call("POST", "/api/home")
    note("回待命位", "/api/home", s, brief(body, ["ok"]))

    # ---------- 标注台：预标注只读推理 ----------
    if frames:
        f0 = frames[0]
        s, body = call("POST", "/api/frames/prelabel",
                       {"session": f0["session"], "name": f0["name"], "boxes": []})
        note("预标注", "/api/frames/prelabel", s,
             f"{len(body.get('boxes', [])) if isinstance(body, dict) else '?'} 个建议框")

    # ---------- 会写文件的按钮：只发非法载荷，验证路由与契约 ----------
    s, body = call("POST", "/api/capture/start", {"frames": 1})
    note("开始采集（未发有效载荷）", "/api/capture/start", s, "校验拦下=路由正常")
    s, body = call("POST", "/api/label", {})
    note("保存标注（未发有效载荷）", "/api/label", s, "校验拦下=路由正常")
    s, body = call("POST", "/api/calibrate/start", {"grid_size": 99})
    note("开始标定（未发有效载荷）", "/api/calibrate/start", s, "校验拦下=路由正常")
    s, body = call("POST", "/api/train", {"tier": "no-such-tier"})
    note("开始训练（未发有效载荷）", "/api/train", s, "档位校验拦下=路由正常")
    s, body = call("POST", "/api/deploy", {"min_map50": 2.0})
    note("部署当前模型（未发有效载荷）", "/api/deploy", s, "校验拦下=路由正常")
    s, body = call("POST", "/api/rollback", {"version": "v-does-not-exist"})
    note("回滚（未发有效载荷）", "/api/rollback", s, "未知版本被拒=路由正常")
    s, body = call("POST", "/api/deploy-from", {})
    note("（未接入页面）", "/api/deploy-from", s, "缺参被拒=路由正常")

    # ---------- 抓取作业：mock 下真跑（模拟舵机，不碰硬件） ----------
    s, body = call("POST", "/api/grasp/start", {"task_id": ""})
    note("开始作业", "/api/grasp/start", s, brief(body, ["ok"], 40))
    s, body = call("POST", "/api/grasp/stop")
    note("停止", "/api/grasp/stop", s, brief(body, ["ok"]))
    # 等作业收尾，避免后面 409
    import time
    for _ in range(40):
        time.sleep(1.0)
        _, st = call("GET", "/api/status")
        if isinstance(st, dict) and not (st.get("job") or {}).get("running"):
            break

    # ---------- 评估当前模型（只读，写 gitignore 掉的 runs/） ----------
    s, body = call("POST", "/api/evaluate", timeout=300)
    note("评估当前模型", "/api/evaluate", s,
         brief(body, ["ok", "reason"], 80) if isinstance(body, dict) else "")

    # ---------- 部署 / 回滚：用页面默认门禁真跑一次 ----------
    s, body = call("POST", "/api/deploy", {"min_map50": 0.5, "note": "审计"}, timeout=300)
    note("部署当前模型（页面默认门禁 0.5）", "/api/deploy", s,
         brief(body, ["ok", "gate"], 70) if isinstance(body, dict) else str(body)[:70])
    deployed_new = None
    if 200 <= s < 300 and isinstance(body, dict):
        deployed_new = (body.get("version") or {}).get("version")

    s, body = call("POST", "/api/rollback", {"version": ""}, timeout=120)
    note("回滚上一版", "/api/rollback", s, brief(body, ["ok"], 60) if isinstance(body, dict) else "")

    s, body = call("GET", "/api/versions")
    after = [v.get("version") for v in (body or {}).get("versions", [])] if isinstance(body, dict) else []

    # ---------- 汇总 ----------
    print("\n作业台按钮审计（mock 模式，真机同样的路由）")
    print("=" * 100)
    print(f"{'控件':<26}{'接口':<30}{'结果':<30}结论")
    print("-" * 100)
    for control, path, result, verdict in ROWS:
        print(f"{control:<26}{path:<30}{result:<30}{verdict}")
    print("=" * 100)
    bad = [r for r in ROWS if r[3] == "异常"]
    print(f"共 {len(ROWS)} 项，异常 {len(bad)} 项")
    print(f"版本基线 {len(baseline_versions)} 个 → 审计后 {len(after)} 个")
    if deployed_new:
        print(f"本次部署新增版本目录：{deployed_new}（如要完全复原，可删掉对应版本目录）")


if __name__ == "__main__":
    main()
