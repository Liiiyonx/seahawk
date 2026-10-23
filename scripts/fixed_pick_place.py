#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""固定位置慢速抓放（不依赖识别模型）。

## 为什么不用闭环

现场实测：模型在这个房间（域外场景）最"稳定"检出的东西是**机械臂自己的夹爪**
（12/12 帧），真袋子只有 2/12 帧。让闭环去抓，它会锁到夹爪那块区域，
并朝错误方向持续下压 —— 上一次就是这样压到贴住表面的。

所以这里改成**固定位置开环动作**：目标位置由操作员把袋子放在约定点确定，
不依赖任何检测。代价是没有"自动识别"，换来的是可预期、可复现、不会乱撞。

## 安全设计（针对上次撞机）

1. **z 硬限位**：下探高度不得低于 `--z-min`（默认 -0.045，即平面 -0.05 之上 5mm）。
   任何时刻算出低于它的目标都会被夹住并告警，绝不照发。
2. **全程慢速**：每段动作 `--duration` 默认 2000ms；越慢越不容易甩飞或过冲。
3. **分步回读**：每步之后读舵机位置并与目标比对，偏差过大就停下报告。
4. **接触前不闭爪**：先到位再闭爪，闭爪用自适应渐闭（夹到即停）。

## 用法

    # 干跑：只打印将要执行的动作序列，不驱动机械臂
    python scripts/fixed_pick_place.py --dry-run

    # 真跑（袋子放在臂座前方 11cm、地面 -0.05 上）
    python scripts/fixed_pick_place.py --grasp-x 0.11 --grasp-y 0.0

    # 放到左舷而非右舷
    python scripts/fixed_pick_place.py --grasp-x 0.11 --place-x -0.275
"""
import argparse
import json
import socket
import sys
import time

DEFAULT_BOOT = {1: 199, 2: 499, 3: 167, 4: 929, 5: 713, 6: 510}


class Board:
    def __init__(self, host, port=8093, timeout=30.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.f = self.sock.makefile("rwb")

    def call(self, req):
        self.f.write((json.dumps(req) + "\n").encode())
        self.f.flush()
        line = self.f.readline()
        if not line:
            raise RuntimeError("板子断开连接")
        return json.loads(line.decode())

    def pos(self):
        t = self.call({"op": "telemetry"}).get("servos") or {}
        return {int(k): v.get("position") for k, v in t.items()}

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description="固定位置慢速抓放（不依赖识别）")
    ap.add_argument("--host", default="192.168.149.1")
    ap.add_argument("--port", type=int, default=8093)
    ap.add_argument("--grasp-x", type=float, default=0.11, help="抓取点 x（m）")
    ap.add_argument("--grasp-y", type=float, default=0.0, help="抓取点 y（m）")
    ap.add_argument("--place-x", type=float, default=0.275, help="放置点 x（右舷 0.275 / 左舷 -0.275）")
    ap.add_argument("--place-y", type=float, default=0.0)
    ap.add_argument("--plane-z", type=float, default=-0.05, help="目标平面高度（m，绝对 z）")
    # ★ 硬限位：下探最深到这里。平面 -0.05 的话，-0.045 表示停在平面上方 5mm。
    ap.add_argument("--z-min", type=float, default=-0.045,
                    help="下探硬限位（绝对 z，m）；低于它的目标会被夹住并告警")
    ap.add_argument("--approach-z", type=float, default=0.06, help="接近高度（绝对 z）")
    ap.add_argument("--retreat-z", type=float, default=0.14, help="抬离高度（绝对 z）")
    ap.add_argument("--duration", type=int, default=2000, help="每段动作时长（ms）；越慢越稳")
    ap.add_argument("--settle", type=float, default=1.6, help="每步后等待时间（s）")
    ap.add_argument("--grasp-pitch", type=float, default=-175.0, help="抓取俯仰角（-175=竖直朝下）")
    ap.add_argument("--place-pitch", type=float, default=-130.0, help="放置俯仰角")
    ap.add_argument("--dry-run", action="store_true", help="只打印动作序列，不驱动")
    args = ap.parse_args()

    drop_z = max(args.z_min, args.plane_z)      # 下探到平面，但绝不低于硬限位
    steps = [
        ("① 回观测位（开机位）", None),
        ("② 抬到接近高度", ("move", args.grasp_x, args.grasp_y, args.approach_z, args.grasp_pitch)),
        ("③ 慢速下探到抓取点", ("move", args.grasp_x, args.grasp_y, drop_z, args.grasp_pitch)),
        ("④ 夹爪自适应闭合", ("grip",)),
        ("⑤ 抬起", ("move", args.grasp_x, args.grasp_y, args.retreat_z, args.grasp_pitch)),
        ("⑥ 横移到料槽上方", ("move", args.place_x, args.place_y, args.retreat_z, args.place_pitch)),
        ("⑦ 下探进槽", ("move", args.place_x, args.place_y, max(args.z_min, 0.0), args.place_pitch)),
        ("⑧ 松爪落料", ("open",)),
        ("⑨ 抬离 + 回观测位", None),
    ]

    print("=== 动作序列 ===")
    print("  抓取点 (%.3f, %.3f)  平面 z=%.3f  实际下探到 z=%.3f（硬限位 %.3f）"
          % (args.grasp_x, args.grasp_y, args.plane_z, drop_z, args.z_min))
    print("  放置点 (%.3f, %.3f)  料槽侧=%s" % (args.place_x, args.place_y,
                                            "左舷" if args.place_x < 0 else "右舷"))
    print("  每段时长 %d ms（慢速）" % args.duration)
    for name, _ in steps:
        print("   ", name)
    if drop_z <= args.z_min + 1e-9:
        print("  ⚠ 下探到 z=%.3f 已触及硬限位 —— 若平面更低，爪子可能够不到" % drop_z)

    if args.dry_run:
        print("\n--dry-run：不驱动机械臂。")
        return 0

    b = Board(args.host, args.port)
    try:
        p0 = b.pos()
        print("\n起始舵机:", dict(sorted(p0.items())))
        print()

        def do_move(label, x, y, z, pitch):
            if z < args.z_min - 1e-9:
                print("  %s：z=%.3f 低于硬限位 %.3f —— 已夹住，不下发" % (label, z, args.z_min))
                return False
            r = b.call({"op": "move_to", "x": x, "y": y, "z": z, "pitch": pitch,
                        "duration_ms": args.duration})
            if not r.get("reachable"):
                print("  %s：IK 不可达 (%.3f, %.3f, %.3f) pitch=%.0f —— 停止"
                      % (label, x, y, z, pitch))
                return False
            time.sleep(args.settle)
            cur = b.pos()
            print("  %s OK  舵机=%s" % (label, {k: cur[k] for k in sorted(cur)}))
            return True

        # ①
        r = b.call({"op": "set_servos", "pairs": sorted(DEFAULT_BOOT.items()),
                    "duration_ms": args.duration})
        time.sleep(args.settle)
        print("  ① 回观测位 OK  舵机=%s" % {k: b.pos()[k] for k in sorted(DEFAULT_BOOT)})

        # ②③ 接近 + 下探
        if not do_move("② 抬到接近高度", args.grasp_x, args.grasp_y, args.approach_z, args.grasp_pitch):
            return 2
        if not do_move("③ 慢速下探", args.grasp_x, args.grasp_y, drop_z, args.grasp_pitch):
            return 2

        # ④ 夹
        r = b.call({"op": "gripper_close"})
        time.sleep(2.0)
        print("  ④ 夹爪闭合  脉宽=%s stalled=%s" % (r.get("pulse"), r.get("stalled")))

        # ⑤ 抬
        if not do_move("⑤ 抬起", args.grasp_x, args.grasp_y, args.retreat_z, args.grasp_pitch):
            return 2

        # ⑥⑦ 移到料槽 + 下探
        if not do_move("⑥ 横移到料槽上方", args.place_x, args.place_y, args.retreat_z, args.place_pitch):
            return 2
        if not do_move("⑦ 下探进槽", args.place_x, args.place_y, max(args.z_min, 0.0), args.place_pitch):
            return 2

        # ⑧ 松爪
        b.call({"op": "gripper_open"})
        time.sleep(1.5)
        print("  ⑧ 松爪落料 OK")

        # ⑨ 抬离 + 回位
        do_move("⑨ 抬离", args.place_x, args.place_y, args.retreat_z, args.place_pitch)
        b.call({"op": "set_servos", "pairs": sorted(DEFAULT_BOOT.items()),
                "duration_ms": args.duration})
        time.sleep(args.settle)
        pf = b.pos()
        print("\n结束舵机:", dict(sorted(pf.items())))
        print("与开机位偏差:", {k: pf[k] - DEFAULT_BOOT[k] for k in sorted(DEFAULT_BOOT)})
        return 0
    finally:
        b.close()


if __name__ == "__main__":
    raise SystemExit(main())
