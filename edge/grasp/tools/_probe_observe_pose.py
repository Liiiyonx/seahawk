# -*- coding: utf-8 -*-
"""只动臂拍照：扫一串候选「观测位姿」，用画面确认哪个真能俯视工作平面。

背景：厂商 IK 在较高处解不出竖直朝下（alpha 会被退到接近水平），而
`arm.home`（pitch -65）实测是**前视**，看不到地面工作平面 —— 这正是标定/闭环
第一道会踩的坑。alpha 的口径靠读源码推断容易翻车，所以这里直接用画面验证。

会做的事：逐个 move_to 候选位姿 → 抓一帧 → 存盘；最后拼一张带标签的对比图，
并把机械臂送回 home。所有 z ≥ 0.20 m，不会碰到平面上的袋子。
"""
import sys
import time

sys.path.insert(0, r"c:\Users\Liii\Desktop\seahawk\edge")
sys.path.insert(0, r"c:\Users\Liii\Desktop\seahawk\edge\grasp")

from grasp.arm_io import ArmIoRemote  # noqa: E402
from grasp.config import load_config  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

OUT_DIR = r"c:\Users\Liii\Desktop\seahawk\_work\shots"

# 候选：先固定 (x, y) 扫俯仰角，再看高度。标签一律英文（cv2 画不了中文）。
CANDIDATES = [
    ("A_x0_y17_z22_p175", 0.0, 0.17, 0.22, -175),
    ("B_x0_y17_z22_p150", 0.0, 0.17, 0.22, -150),
    ("C_x0_y17_z22_p110", 0.0, 0.17, 0.22, -110),
    ("D_x0_y17_z22_p090", 0.0, 0.17, 0.22, -90),
    ("E_x0_y17_z25_p175", 0.0, 0.17, 0.25, -175),
    ("F_x0_y17_z25_p130", 0.0, 0.17, 0.25, -130),
    ("G_x0_y12_z22_p175", 0.0, 0.12, 0.22, -175),
    ("H_x0_y22_z22_p175", 0.0, 0.22, 0.22, -175),
    ("I_x0_y17_z20_p175", 0.0, 0.17, 0.20, -175),
]


def main():
    cfg = load_config()
    cfg["arm"]["remote"] = {"enabled": True, "host": "192.168.149.1", "port": 8093,
                            "timeout": 30.0}
    io = ArmIoRemote(cfg)
    io.start()
    if io.ros_error:
        print("链路失败：%s" % io.ros_error)
        return 1

    shots = []
    for name, x, y, z, pitch in CANDIDATES:
        ok = io.move_to(x, y, z, pitch=pitch, pitch_range=(-180.0, 0.0))
        time.sleep(1.4)
        frame = io.latest_frame()
        tele = io.servo_telemetry() or {}
        servos = " ".join("%s=%s" % (k, v.get("position")) for k, v in sorted(tele.items()))
        print("%-20s reach=%-5s servos=%s" % (name, ok, servos))
        if frame is None:
            continue
        path = "%s\\obs_%s.jpg" % (OUT_DIR, name)
        cv2.imwrite(path, frame)
        shots.append((name, frame))

    # 拼对比图：3 列，每格缩到 320x240，左上角写标签
    cols = 3
    rows = (len(shots) + cols - 1) // cols
    tile_w, tile_h = 320, 240
    sheet = np.full((rows * (tile_h + 22), cols * tile_w, 3), 30, dtype=np.uint8)
    for idx, (name, frame) in enumerate(shots):
        r, c = divmod(idx, cols)
        small = cv2.resize(frame, (tile_w, tile_h))
        y0 = r * (tile_h + 22) + 22
        sheet[y0:y0 + tile_h, c * tile_w:(c + 1) * tile_w] = small
        cv2.putText(sheet, name, (c * tile_w + 4, y0 - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)
    sheet_path = "%s\\obs_contact.jpg" % OUT_DIR
    cv2.imwrite(sheet_path, sheet)
    print("对比图：%s" % sheet_path)

    io.home()
    print("已回 home")
    io.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
