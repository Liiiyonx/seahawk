#!/usr/bin/env python3
"""板子启动后把机械臂摆到「开机默认姿态」。

## 为什么要有这一步

`run_board_stack.sh` 只负责把 ROS 栈和 board_agent 拉起来，**不会动机械臂**：
舵机上电后停在断电前的位置，每次开机姿态都不一样。要「以后开机都这个位置」，
就必须在启动后主动下发一次目标脉宽。

## 姿态从哪来

`presets.json` 的 `boot_default` 字段（由作业台「设开机默认」写入）。
板上没有作业台（Python 3.6 跑不了那套代码），所以作业台把开机姿态另外
**导出**成 `boot_pose.json`（与 config.yaml 同目录），再由同步脚本推到板上。
本脚本只读 `boot_pose.json`，不去解析作业台那份文件 —— 两边职责分开。

## 到位校验（重要）

下发之后**回读实际位置**并比较目标：超出容差就告警，而不是当作成功。
原因：总线舵机在「跟不动」的区间会不到位但也不报错，操作员却以为到位了。
某些姿态（例如接近行程端点）本来就顶得住，这种时候需要明确说出来。

## ★ 语法限制：必须兼容 Python 3.6

板子是 Ubuntu 18.04 + Python 3.6.9。所以本文件里**不能**出现：
  * ``from __future__ import annotations``（需要 3.7+，否则 SyntaxError）
  * ``str | None`` / ``dict[str, int]`` 这类 PEP 585/604 内联写法（3.9/3.10+）
  * 海象运算符、``match`` 等更新语法

这跟 ``arm_io.py`` / ``web/server.py`` 的情况不同：那些**只在开发机跑**，
用新语法没问题；而本脚本**只在板上跑**。写之前先想清「这段代码在哪台机器上执行」——
我就在这里踩过一次：用了 ``from __future__ import annotations``，
板上直接 ``SyntaxError: future feature annotations is not defined``。
"""
import argparse
import json
import socket
import sys
import time
from pathlib import Path

#: 默认与 config.yaml 同目录（repo/edge/grasp/boot_pose.json）。
#: 用 __file__ 定位而不是硬编码绝对路径：板上仓库可能不在 /home/ubuntu/oceanus。
DEFAULT_POSE_FILE = (Path(__file__).resolve().parent.parent / "boot_pose.json")
DEFAULT_PORT = 8093
#: 到位容差（脉宽）。实测正常跟随误差 ≤6，取 15 留出机械间隙余量。
TOLERANCE = 15


# ★ 注解一律用「字符串形式」或干脆不标：
#   py3.6 下 `tuple[str, dict[int, int]] | None` 在**函数定义时**就会
#   TypeError: 'type' object is not subscriptable（内联泛型是 3.9+）。
#   写成字符串则不会被求值，既保留可读性又能在 3.6 跑。
def log(msg):
    # type: (str) -> None
    print("[boot-pose] %s" % msg, flush=True)


def load_pose(path):
    # type: (Path) -> "tuple[str, dict[int, int]] | None"
    """读 boot_pose.json；没有/损坏时返回 None（开机摆位失败不该挡住启动）。"""
    if not path.is_file():
        log("没有 %s —— 跳过开机摆位（这是正常的：还没设过开机默认姿态）" % path)
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log("! %s 读不出来，跳过：%s" % (path, exc))
        return None
    pose = raw.get("pose")
    if not isinstance(pose, dict) or not pose:
        log("! %s 里没有有效 pose，跳过" % path)
        return None
    try:
        clean = {int(k): int(v) for k, v in pose.items()}
    except (TypeError, ValueError) as exc:
        log("! pose 格式不对，跳过：%s" % exc)
        return None
    return str(raw.get("name") or "boot"), clean


class Agent:
    def __init__(self, host, port, timeout=20.0):
        # type: (str, int, float) -> None
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.f = self.sock.makefile("rwb")

    def call(self, req):
        # type: (dict) -> dict
        self.f.write((json.dumps(req) + "\n").encode())
        self.f.flush()
        line = self.f.readline()
        if not line:
            raise RuntimeError("board_agent 断开连接")
        return json.loads(line.decode())

    def close(self):
        # type: () -> None
        try:
            self.sock.close()
        except OSError:
            pass


def main(argv=None):
    # type: ("list[str] | None") -> int
    ap = argparse.ArgumentParser(description="把机械臂摆到开机默认姿态")
    ap.add_argument("--pose-file", default=str(DEFAULT_POSE_FILE))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--duration-ms", type=int, default=1500)
    ap.add_argument("--settle", type=float, default=2.5, help="下发后等待到位的时间（秒）")
    ap.add_argument("--tolerance", type=int, default=TOLERANCE)
    args = ap.parse_args(argv)

    loaded = load_pose(Path(args.pose_file))
    if loaded is None:
        return 0                      # 没设开机姿态不算失败
    name, pose = loaded
    log("开机默认姿态「%s」：%s" % (name, pose))

    # 等 board_agent 就绪（它在 ROS 栈之后才起来，可能还没监听）
    deadline = time.time() + 90
    agent = None
    while time.time() < deadline:
        try:
            agent = Agent(args.host, args.port)
            st = agent.call({"op": "status"})
            if st.get("ros_error"):
                log("! ROS 链路有问题：%s" % st["ros_error"])
            break
        except Exception:                                    # noqa: BLE001
            agent = None
            time.sleep(3)
    if agent is None:
        log("! board_agent 90s 内没就绪，无法摆位")
        return 1

    try:
        pairs = sorted(pose.items())
        r = agent.call({"op": "set_servos", "pairs": pairs,
                        "duration_ms": args.duration_ms})
        if not r.get("ok"):
            log("! 下发失败：%s" % r.get("error"))
            return 1
        log("已下发 %d 个舵机，等待 %ss 到位…" % (len(pairs), args.settle))
        time.sleep(args.settle)

        tel = agent.call({"op": "telemetry"}).get("servos") or {}
        bad = []                       # type: list
        for sid, target in pairs:
            row = tel.get(str(sid)) or {}
            got = row.get("position")
            if got is None:
                bad.append("id%s 无回读" % sid)
                continue
            delta = int(got) - int(target)
            mark = "OK" if abs(delta) <= args.tolerance else "偏差大"
            log("  id%s: 目标 %s 实测 %s 差 %+d  %s" % (sid, target, got, delta, mark))
            if abs(delta) > args.tolerance:
                bad.append("id%s 目标%s 实测%s 差%+d" % (sid, target, got, delta))
        if bad:
            # ★ 不静默通过：这种偏差在现场意味着"舵机顶住了 / 该关节带不动"，
            #   继续用它做抓取会瞄错地方，必须让人看到。
            log("! 有舵机没到目标位置：" + "；".join(bad))
            log("! 可能原因：该姿态接近行程端点（机构顶住）、负载过大、或舵机供电不足")
            return 2
        log("开机摆位完成：全部舵机到位 OK")
        return 0
    finally:
        agent.close()


if __name__ == "__main__":
    raise SystemExit(main())
