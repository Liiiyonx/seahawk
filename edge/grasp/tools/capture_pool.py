#!/usr/bin/env python3
"""泳池现场「一键采集」脚手架：按组采集第一人称帧，并留下整组切分所需的元数据。

## 它解决什么

现场采集最容易出的三个问题，本脚本从机制上绕开：

1. **分组乱** —— 袋子换个位置/形态就该另起一组。这里**每组一个 Dataset 会话**
   （目录），组边界天然写在磁盘上；``finetune_pool.py --group-split`` 就能按组
   整组切 train/val，不会把同一袋同一位置的相邻帧拆到两侧（那是泄漏）。
2. **条件没记录** —— 采完只剩一堆图，说不清覆盖了哪些干扰。这里把每组的条件
   与帧数写进 ``data/capture/<批次>.json``，清单里的 ``confounders`` 直接照抄。
3. **忘了规程要求** —— 组标签里带 ``arm`` / ``hand`` / ``empty`` 等关键词时，
   脚本会打印对应规程提示（如「臂体入画」是现场被误检 conf 0.85 的头号来源），
   开工前就能照着拍。

## 用法

::

    # 真机（远程板端；config 里 arm.remote.enabled: true）
    python edge/grasp/tools/capture_pool.py --tag pool01 \\
        --groups "center/crumpled,edge/flat,glare/film,arm_in_frame,hand_in_frame,empty" \\
        --frames-per-group 40 --settle 6

    # 无真机演练（合成画面，只验链路）
    python edge/grasp/tools/capture_pool.py --mock --tag dryrun \\
        --groups "a,b" --frames-per-group 8 --settle 0

## 采完的下一步

1. 作业台「2 · 标注台」标注：袋子标 ``plastic_bag``；**负样本整张不标**；
   池边彩色物体标 ``buoy`` 作显式负类
2. ``python edge/grasp/tools/finetune_pool.py --session <会话1> --session <会话2> \\
   --group-split --deploy``
3. 另起一次采集做独立 test 集（换水/换灯/换袋），全程不参与训练与调参
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GRASP = HERE.parent
EDGE = GRASP.parent
for _p in (str(EDGE), str(GRASP)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

EXPECTED_SIZE = (640, 480)

#: 组标签关键词 → (维度, 规程提示)。点检关键词即可自动带出该组的采集要求。
KEYWORDS: dict[str, tuple[str, str]] = {
    "center": ("位置", "袋子放池心"),
    "edge": ("位置", "袋子靠池边"),
    "near": ("位置", "袋子贴近画面下缘"),
    "far": ("位置", "袋子靠近画面上缘"),
    "crumpled": ("形态", "袋子揉成团"),
    "flat": ("形态", "袋子铺开、贴水"),
    "film": ("形态", "长条薄膜状（易与水面高光混淆）"),
    "wet": ("形态", "袋面被水膜覆盖"),
    "multi": ("数量", "同框放 2~3 个袋子（少量即可）"),
    "dark": ("光照", "整体调暗"),
    "glare": ("光照", "人为制造水面高光/强反光（必须拍，模型要能分清反光和白袋）"),
    "side": ("光照", "侧光"),
    "arm": ("负样本", "★让夹爪/腕部/线缆入画 —— 现场被误检 conf 0.85 的头号来源"),
    "hand": ("负样本", "手把袋子放进水里的过程（手入画）"),
    "empty": ("负样本", "空池：只有水与深色底衬（多角度、多光照）"),
    "ripple": ("负样本", "水面波纹/泡沫"),
    "debris": ("负样本", "水面漂浮碎屑/落叶/瓶盖"),
    "wall": ("负样本", "池壁/池沿/地面/水管入水口"),
}


def _conditions_of(label: str) -> dict[str, str]:
    """把组标签里的关键词解析成 {维度: 提示}。"""
    out: dict[str, str] = {}
    for key, (dim, hint) in KEYWORDS.items():
        if key in label.lower():
            out[dim] = hint
    return out


def _is_negative_group(conds: dict[str, str]) -> bool:
    """整组只命中「负样本」维度 ⇒ 纯负样本组（采集后要标成背景）。

    纯负样本组按规程「整张不标」；不额外标背景的话，组装训练集时会被当成
    「尚未标注」静默丢掉 —— 见 dataset.BACKGROUND_MARKER 的说明。
    """
    return bool(conds) and set(conds) == {"负样本"}


def _print_hints(groups: list[str]) -> None:
    print("\n组标签关键词表（点检式提示，写进组名即可自动带出）：")
    for key, (dim, hint) in KEYWORDS.items():
        print(f"  {key:<10} [{dim}] {hint}")
    print()


def _settle_seconds(seconds: float) -> None:
    """人类可读的倒计时：现场要摆袋子，必须看得见还剩几秒。"""
    remain = float(seconds)
    while remain > 0:
        print(f"    准备 {remain:>4.1f}s …（摆好袋子 / 调好光照）", end="\r", flush=True)
        time.sleep(min(0.5, remain))
        remain -= 0.5
    if seconds > 0:
        print(" " * 60, end="\r")


def _observe_pose(cfg: dict[str, Any]) -> tuple[tuple[float, float, float], float] | None:
    """按闭环同一口径算出「低头观测位」；标定未就绪时返回 None。

    与 GraspLoop.run() 的观测位**完全同一公式**（servo_fallback + 平面高度 +
    接近高度 + 伺服抬高，pitch=grasp_pitch），保证「采集机位 = 现场识别机位」。
    """
    from grasp.calibration import load_calibration

    cal = load_calibration()
    if not getattr(cal, "ready", False):
        return None
    agent = cfg.get("agent", {}) or {}
    fb = agent.get("servo_fallback") or [0.0, 0.10]
    box = agent.get("servo_box") or {}
    bx = box.get("x") or [-0.30, 0.30]
    by = box.get("y") or [-0.05, 0.30]
    ox = min(max(float(fb[0]), float(bx[0])), float(bx[1]))
    oy = min(max(float(fb[1]), float(by[0])), float(by[1]))
    oz = float(cal.plane_z) + float(agent.get("approach_height", 0.08)) \
        + float(agent.get("servo_lift", 0.15))
    return (ox, oy, oz), float(agent.get("grasp_pitch", -175))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="泳池现场一键采集（按组，留整组切分元数据）")
    ap.add_argument("--config", default=None)
    ap.add_argument("--tag", default="pool", help="批次标签（决定会话名前缀）")
    ap.add_argument("--groups", required=True,
                    help="逗号分隔的组标签，如 'center/crumpled,edge/flat,arm_in_frame'")
    ap.add_argument("--frames-per-group", type=int, default=40)
    ap.add_argument("--interval", type=float, default=0.12, help="取帧间隔（s）")
    ap.add_argument("--settle", type=float, default=6.0, help="每组开始前的准备倒计时（s）")
    ap.add_argument("--quality", type=int, default=95, help="JPEG 质量（规程要求尽量不重损）")
    ap.add_argument("--frame-timeout", type=float, default=10.0, help="单组取帧无图超时（s）")
    ap.add_argument("--mock", action="store_true", help="合成画面演练（不碰真机）")
    ap.add_argument("--observe", action="store_true",
                    help="每组开始前把臂摆到低头观测位（需标定就绪）")
    ap.add_argument("--list-hints", action="store_true", help="只打印关键词提示表后退出")
    args = ap.parse_args(argv)

    if args.list_hints:
        _print_hints([""])
        return 0

    import cv2  # noqa: E402  (延迟导入：--list-hints 不需要它)

    from grasp.arm_io import build_arm_io
    from grasp.config import load_config
    from grasp.vision.dataset import Dataset

    cfg = load_config(args.config)
    dataset = Dataset.from_config(cfg)
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    if not groups:
        print("[错误] --groups 为空")
        return 2

    io = build_arm_io(cfg, mock=args.mock)
    print(f"[链路] mock={args.mock} remote={bool((cfg.get('arm') or {}).get('remote', {}).get('enabled'))}")

    pose = _observe_pose(cfg) if args.observe else None
    if args.observe and pose is None:
        print("[观测位] 标定未就绪，跳过摆位（先跑作业台「5 · 9 点标定」）")
    if pose is not None:
        _, pitch = pose
        pr = (cfg.get("arm", {}) or {}).get("home", {}).get("pitch_range") or [-180, 0]
        print(f"[观测位] 低头 pitch={pitch:g} → 每组开始前自动摆位")

    batch = f"{datetime.now():%Y%m%d_%H%M%S}_{args.tag}"
    record: dict[str, Any] = {
        "batch": args.tag,
        "batch_id": batch,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "device": {
            "site_id": cfg.get("site_id"),
            "device_id": cfg.get("device_id"),
            "mock": bool(args.mock),
            "remote": bool(((cfg.get("arm") or {}).get("remote") or {}).get("enabled")),
        },
        "frames_per_group": args.frames_per_group,
        "quality": args.quality,
        "groups": [],
    }

    print(f"\n[采集] 批次={batch} 组数={len(groups)} 每组={args.frames_per_group} 帧")
    _print_hints(groups)

    total_saved = 0
    for gi, label in enumerate(groups, start=1):
        conds = _conditions_of(label)
        print(f"\n=== 第 {gi}/{len(groups)} 组：{label} ===")
        for dim, hint in conds.items():
            print(f"  [{dim}] {hint}")
        if not conds:
            print("  （未命中关键词，按自定义组处理）")

        if pose is not None:
            ox, oy, oz = pose
            pr = ((cfg.get("arm", {}) or {}).get("home") or {}).get("pitch_range") or [-180, 0]
            reached = io.move_to(ox, oy, oz, pitch=pose[1],
                                 pitch_range=(float(pr[0]), float(pr[1])))
            print(f"  [观测位] move_to({ox:+.2f},{oy:+.2f},{oz:.3f}) → "
                  f"{'ok' if reached else '不可达'}")
            time.sleep(0.6)

        _settle_seconds(args.settle)

        session = dataset.new_session(f"{args.tag}_{gi:02d}_{label.replace('/', '-')}")
        saved = 0
        warned_size = False
        deadline = time.time() + max(args.frame_timeout, args.frames_per_group * args.interval * 4)
        while saved < args.frames_per_group:
            if time.time() > deadline:
                print(f"  [中止] 本组在 {args.frame_timeout:g}s 超时内只采到 {saved} 帧"
                      f"（相机无图？检查链路 / 单进程占用）")
                break
            frame = io.latest_frame()
            if frame is None:
                time.sleep(args.interval)
                continue
            h, w = frame.shape[:2]
            if not warned_size and (w, h) != EXPECTED_SIZE:
                print(f"  [警告] 帧尺寸 {w}×{h} ≠ 规程要求的 {EXPECTED_SIZE[0]}×{EXPECTED_SIZE[1]}"
                      f"（部署输入是 640×480，缩放会改变域）")
                warned_size = True
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), args.quality])
            if not ok:
                continue
            dataset.add_frame(session, buf.tobytes())
            saved += 1
            if saved % 10 == 0:
                print(f"  采集中 {saved}/{args.frames_per_group}", end="\r", flush=True)
            time.sleep(args.interval)
        total_saved += saved
        is_bg = _is_negative_group(conds)
        if is_bg and saved:
            dataset.mark_background(session, note=f"纯负样本组 {label}")
            print(f"  已标记为背景负样本（组装时作为空标签背景帧进入训练，"
                  f"标注台不必再标）")
        print(f"  完成 {saved}/{args.frames_per_group} 帧 → 会话 {session}")
        record["groups"].append({
            "index": gi,
            "label": label,
            "conditions": conds,
            "session": session,
            "frames": saved,
            "background": is_bg,
            "raw_dir": str((dataset.raw_dir / session).relative_to(dataset.root)),
        })

    record["total_frames"] = total_saved
    cap_dir = dataset.root / "capture"
    cap_dir.mkdir(parents=True, exist_ok=True)
    meta_path = cap_dir / f"{batch}.json"
    meta_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[完成] 共 {total_saved} 帧，{len(groups)} 组")
    print(f"[元数据] {meta_path}")
    n_bg = sum(1 for g in record["groups"] if g["background"])
    if n_bg:
        print(f"[背景] {n_bg}/{len(groups)} 组是纯负样本组，已自动标记为背景 "
              f"（组装时以空标签背景帧进入训练）")
    print("[下一步] 1) 作业台「2 · 标注台」标注：袋子标 plastic_bag，"
          "背景组整张不标（已自动标记，不必再动）")
    print("         2) finetune_pool.py --session <会话…> --group-split --deploy")
    print("         3) 另起一次采集做独立 test 集，训练调参全程不碰")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
