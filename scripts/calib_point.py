#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""9 点标定的**逐点采集**工具（一次采一个已知世界坐标点）。

## 为什么不用页面上的自动流程

页面上的 `/api/calibrate/start` 会在每个网格点等待固定时长（默认 1.6s）然后取
**当前帧**的检测框中心。如果操作员没来得及把目标挪到下一点，它会连着采到
**同一个像素位置**，最后拟合出一个 RMSE≈0 的**退化标定** —— 文件看起来合法，
抓取时却会去错地方。这是最危险的一种"假装成功"。

本工具改成：**每次只采一个点**，由操作员逐点确认后再采下一个。
世界坐标由调用方给出（已知），像素坐标由该姿态下的检测框中心给出。

## 观测姿态

采集前把机械臂摆到**观测姿态**再取帧 —— 姿态一变，像素↔世界的对应关系就变了，
所以整轮标定必须始终在同一个姿态下采。

观测姿态默认取**开机位**（`edge/grasp/boot_pose.json`，由作业台「设为开机默认」
写入）。为什么不用厂商默认待命位：在这台设备上，默认待命位
（`id3=390`、`pitch=-65`）的相机对着椅子/衣柜，**看不到地面工作区**；
操作员实际设的开机位（`id3≈167`）才是俯视工作区的姿态。这一点实测确认过。

    --pose boot    用开机位（默认）
    --pose home    用厂商默认待命位
    --pose hold    什么都不动，就用当前位置（操作员自己摆好了）

## 用法

    # 采一点（世界坐标 x y，单位 m；原点 = 臂座安装面在地面的投影）
    python scripts/calib_point.py --xy 0.11 0.00
    python scripts/calib_point.py --xy 0.00 0.11

    # 看已采的点 / 清掉重来
    python scripts/calib_point.py --status
    python scripts/calib_point.py --reset

    # 采完后拟合、校验、落盘
    python scripts/calib_point.py --fit --plane-z -0.05
"""
import argparse
import base64
import json
import socket
import sys
import time
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent
GRASP = REPO / "edge" / "grasp"
CALIB_PATH = GRASP / "calibration.json"
BOOT_POSE_PATH = GRASP / "boot_pose.json"
sys.path.insert(0, str(REPO / "edge"))

from grasp.config import load_config                      # noqa: E402
from grasp.vision.detector import Detector                # noqa: E402


class BoardLink:
    def __init__(self, host, port=8093, timeout=20.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.f = self.sock.makefile("rwb")

    def call(self, req):
        self.f.write((json.dumps(req) + "\n").encode())
        self.f.flush()
        line = self.f.readline()
        if not line:
            raise RuntimeError("板子断开连接")
        return json.loads(line.decode())

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def grab(self, width=640, quality=92, tries=8):
        for _ in range(tries):
            r = self.call({"op": "frame", "max_width": width, "quality": quality})
            if r.get("ok"):
                img = cv2.imdecode(
                    np.frombuffer(base64.b64decode(r["jpeg_b64"]), dtype=np.uint8),
                    cv2.IMREAD_COLOR)
                if img is not None:
                    return img
            time.sleep(0.3)
        return None


def load_pairs():
    if not CALIB_PATH.is_file():
        return [], None
    try:
        raw = json.loads(CALIB_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], None
    return list(raw.get("pairs") or []), raw.get("plane_z")


def save_pairs(pairs, plane_z, matrix=None, rmse=None):
    payload = {
        "plane_z": plane_z,
        "pairs": pairs,
        "matrix": matrix,
        "rmse": rmse,
        "place": None,
    }
    CALIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALIB_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    return CALIB_PATH


def fit_pairs(pairs):
    """最小二乘拟合仿射映射；返回 (matrix, rmse, 每点残差)。"""
    a = np.array([[p["pixel"][0], p["pixel"][1], 1.0] for p in pairs])
    b = np.array([[p["world"][0], p["world"][1]] for p in pairs])
    sol, *_ = np.linalg.lstsq(a, b, rcond=None)
    resid = a @ sol - b
    per = np.sqrt((resid ** 2).sum(axis=1))
    rmse = float(np.sqrt((resid ** 2).sum(axis=1).mean()))
    return sol.tolist(), rmse, per


def apply_observation_pose(link, mode):
    """把机械臂摆到观测姿态。返回人类可读的姿态说明。"""
    if mode == "hold":
        return "保持当前位置（--pose hold）"
    if mode == "home":
        r = link.call({"op": "home", "duration_ms": 1500})
        if not r.get("ok"):
            raise RuntimeError("回默认待命位失败：%s" % r.get("error"))
        time.sleep(2.5)
        return "厂商默认待命位 (0, 0.17, 0.30) pitch=-65"
    # boot（默认）：用操作员设的开机位
    if not BOOT_POSE_PATH.is_file():
        raise RuntimeError(
            "找不到 %s —— 先在作业台把工作姿态设为开机默认，"
            "或改用 --pose home / --pose hold" % BOOT_POSE_PATH)
    raw = json.loads(BOOT_POSE_PATH.read_text(encoding="utf-8"))
    pose = {int(k): int(v) for k, v in (raw.get("pose") or {}).items()}
    if not pose:
        raise RuntimeError("%s 里没有有效 pose" % BOOT_POSE_PATH)
    r = link.call({"op": "set_servos", "pairs": sorted(pose.items()),
                   "duration_ms": 1500})
    if not r.get("ok"):
        raise RuntimeError("摆到开机位失败：%s" % r.get("error"))
    time.sleep(2.5)
    return "开机位「%s」%s" % (raw.get("name"), pose)


def main():
    ap = argparse.ArgumentParser(description="逐点采集 9 点标定")
    ap.add_argument("--host", default="192.168.149.1")
    ap.add_argument("--port", type=int, default=8093)
    ap.add_argument("--xy", nargs=2, type=float, metavar=("X", "Y"),
                    help="该点的世界坐标（m）")
    ap.add_argument("--status", action="store_true", help="显示已采的点")
    ap.add_argument("--reset", action="store_true", help="清空已采的点")
    ap.add_argument("--fit", action="store_true", help="拟合、校验并落盘")
    ap.add_argument("--plane-z", type=float, default=None, help="目标平面高度（m）")
    ap.add_argument("--pose", choices=("boot", "home", "hold"), default="boot",
                    help="观测姿态：boot=开机位（默认）/ home=厂商默认待命位 / hold=不动")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    pairs, existing_z = load_pairs()

    if args.status:
        print("标定文件:", CALIB_PATH, "存在" if CALIB_PATH.is_file() else "不存在")
        print("已采点数:", len(pairs))
        for i, p in enumerate(pairs, 1):
            print("  %d) 世界 (%.3f, %.3f)  <-  像素 (%.1f, %.1f)"
                  % (i, p["world"][0], p["world"][1], p["pixel"][0], p["pixel"][1]))
        if CALIB_PATH.is_file():
            raw = json.loads(CALIB_PATH.read_text(encoding="utf-8"))
            print("plane_z =", raw.get("plane_z"), " rmse =", raw.get("rmse"))
        return 0

    if args.reset:
        if CALIB_PATH.is_file():
            CALIB_PATH.unlink()
        print("已清空", CALIB_PATH)
        return 0

    if args.fit:
        if len(pairs) < 3:
            print("点不够：仿射标定至少 3 个（建议 4 个以上），当前 %d" % len(pairs))
            return 2
        matrix, rmse, per = fit_pairs(pairs)
        plane_z = args.plane_z if args.plane_z is not None else (existing_z or 0.02)
        print("拟合结果：")
        for i, (p, r) in enumerate(zip(pairs, per), 1):
            print("  %d) 世界 (%.3f, %.3f)  像素 (%.1f, %.1f)  残差 %.1f px"
                  % (i, p["world"][0], p["world"][1],
                     p["pixel"][0], p["pixel"][1], r))
        print("  RMSE = %.1f px   plane_z = %s" % (rmse, plane_z))
        # 退化检测：残差全为 0 或点几乎共线 → 标定不可用
        pix = np.array([p["pixel"] for p in pairs])
        if len(pairs) >= 3:
            area = 0.5 * abs(np.cross(pix[1] - pix[0], pix[2] - pix[0]))
            spread_x = pix[:, 0].ptp()
            spread_y = pix[:, 1].ptp()
            print("  像素分布：跨度 x=%.0f y=%.0f，首三角面积=%.0f"
                  % (spread_x, spread_y, area))
            if area < 200:
                print("  ✗ 像素点几乎共线/过于集中 —— 标定不可用，请把网点分开得更远")
                return 3
            if spread_x < 40 or spread_y < 40:
                print("  ✗ 像素跨度太小（<40px）—— 极可能是采到了同一个位置，标定不可用")
                return 3
        path = save_pairs(pairs, plane_z, matrix, rmse)
        print("已写入", path)
        print("★ 记得重启作业台/桥接层让新标定生效")
        return 0

    if not args.xy:
        ap.print_help()
        return 2

    # ---- 采集一个点 ----
    cfg = load_config(args.config)
    det = Detector(cfg, mock=False)
    backend = det.load()
    if backend == "none":
        print("✗ 模型没加载成功，无法检测目标")
        return 2
    marker = det.target_class

    link = BoardLink(args.host, args.port)
    try:
        # 摆到观测姿态（默认开机位 —— 实测只有它能看到地面工作区）
        try:
            pose_desc = apply_observation_pose(link, args.pose)
        except Exception as exc:                              # noqa: BLE001
            print("✗ 摆观测姿态失败：%s" % exc)
            return 2
        print("观测姿态：%s" % pose_desc)
        img = link.grab()
        if img is None:
            print("✗ 取帧失败")
            return 2
        dets = [d for d in det.infer(img) if d.cls == marker]
        if not dets:
            print("✗ 这一帧没检出 %s（目标要放在当前视野内）" % marker)
            return 4
        best = max(dets, key=lambda d: d.conf)
        px = [round(float(best.center[0]), 1), round(float(best.center[1]), 1)]
        print("检出 %s：conf=%.3f 像素=(%.1f, %.1f)  本帧另检出 %d 个同类"
              % (marker, best.conf, px[0], px[1], len(dets) - 1))
        # 多检出时要人能核对：把带框的图存下来（否则可能采错目标）
        if len(dets) > 1:
            vis = img.copy()
            for i, d in enumerate(sorted(dets, key=lambda x: -x.conf)):
                color = (0, 0, 255) if d is best else (0, 200, 0)
                cv2.rectangle(vis, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), color, 2)
                cv2.putText(vis, "#%d %.2f" % (i + 1, d.conf),
                            (int(d.x1), max(14, int(d.y1) - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
            art = REPO / "artifacts"
            art.mkdir(exist_ok=True)
            out = art / ("calib_%s_%s.jpg" % (len(pairs) + 1, args.xy[0]))
            cv2.imwrite(str(out), vis)
            print("  ⚠ 有多个同类检出，已存带框图供核对：%s" % out)

        world = [round(float(args.xy[0]), 4), round(float(args.xy[1]), 4)]
        pairs.append({"pixel": px, "world": world})
        plane_z = args.plane_z if args.plane_z is not None else (existing_z or 0.02)
        save_pairs(pairs, plane_z)
        print("已记录第 %d 点：世界 (%.3f, %.3f) ← 像素 (%.1f, %.1f)"
              % (len(pairs), world[0], world[1], px[0], px[1]))
        return 0
    finally:
        link.close()


if __name__ == "__main__":
    raise SystemExit(main())
