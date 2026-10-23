#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板上逆运动学解算常驻子进程（runtime: **python3.6**）。

为什么单独拆成一只进程 —— 这是上真机时实测定出来的、不是设计偏好：

* 厂商 ROS 工作空间（`rospy` / `hiwonder_servo_msgs` / `cv_bridge`）**只装在
  python2.7** 下（ROS melodic）；py3.6 有 cv2/numpy 但没有 rospy。
* 厂商 `kinematics` 的 `.so` 在生产环境的 py2.7 `dist-packages` 里那份是
  **py3 编译的错误拷贝**：`ImportError: undefined symbol: _Py_FalseStruct`；
  装在同一台机器的 **py3.6** 下那份才是能用的（实测
  `setPitchRanges((0,0.17,0.30),-65,-180,0)` → `{'servo3':393,'servo4':756,
  'servo5':592,'servo6':500}`）。

于是板上按「每个解释器只做它能做的事」分工：ROS 发布/回读归 py2.7 代理
（`board_agent.py`），IK 解算归这只 py3.6 进程。父进程用管道喂坐标、收脉宽。

协议：stdin 每行一个 JSON 请求，stdout 每行一个 JSON 响应（按键 `id` 对应）。
偏移量 ``d`` 与俯仰角扫描沿用厂商默认口径（`ik_transform.ArmIK.setPitchRanges`）。
"""

import json
import os
import sys


def _plain(value):
    """把 numpy 标量降级成内置类型 —— 否则 json.dumps 会抛 TypeError。"""
    try:
        return {k: _plain(v) for k, v in value.items()}
    except AttributeError:
        pass
    if isinstance(value, float):
        return float(value)
    if isinstance(value, int):
        return int(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def main():
    from kinematics import ik_transform

    ik = ik_transform.ArmIK()
    out = sys.stdout

    out.write(json.dumps({"id": None, "ok": True, "op": "ready",
                          "pid": os.getpid()}) + "\n")
    out.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            if req.get("op") == "ping":
                resp = {"ok": True, "pid": os.getpid()}
            else:
                result = ik.setPitchRanges(
                    (float(req["x"]), float(req["y"]), float(req["z"])),
                    float(req["pitch"]),
                    float(req["alpha1"]),
                    float(req["alpha2"]),
                    float(req.get("d", 0.01)),
                )
                if not result:
                    resp = {"ok": False, "error": "unreachable"}
                else:
                    theta, servos, alpha = result
                    resp = {"ok": True, "servos": _plain(servos),
                            "theta": _plain(theta), "alpha": float(alpha)}
        except Exception as exc:  # noqa: BLE001 - 单条请求失败不能拖垮常驻进程
            resp = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
        resp["id"] = rid
        out.write(json.dumps(resp) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
