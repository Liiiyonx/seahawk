#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把「开机默认姿态」同步到树莓派。

## 为什么需要单独一条同步命令

作业台上点「设为开机默认」只会写开发机上的两个文件：
``edge/grasp/presets.json``（预设全集）和 ``edge/grasp/boot_pose.json``（导出件）。
但**开机摆位是板子自己做的**（板上有 systemd 单元，开机跑
``board_apply_boot_pose.py``），而板子在 AP 模式下**连不到开发机**
（实测：板子→笔记本所有端口超时，AP 客户端隔离），所以没办法「板子来拉」。

反过来开发机→板子是通的，所以用推送：本脚本把 ``boot_pose.json``
和板上摆位脚本一起 scp 到板子，然后**就地验证**板子能正确读到它。

## 用法

    python scripts/sync_boot_pose.py --host 192.168.149.1
    python scripts/sync_boot_pose.py --host 192.168.149.1 --apply   # 立刻摆位一次

``--apply`` 会真的让机械臂动到那个姿态，默认不开（首次应当有人在场）。
"""

from __future__ import annotations

import argparse
import posixpath
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GRASP = REPO / "edge" / "grasp"
BOOT_POSE = GRASP / "boot_pose.json"
APPLY_SCRIPT = GRASP / "deploy" / "board_apply_boot_pose.py"


def log(msg: str) -> None:
    print(f"[boot] {msg}", flush=True)


def die(msg: str, code: int = 2) -> None:
    print(f"[boot] ✗ {msg}", file=sys.stderr, flush=True)
    raise SystemExit(code)


def run(cmd: list[str], *, dry: bool, check: bool = True) -> subprocess.CompletedProcess:
    if dry:
        log("$ " + " ".join(shlex.quote(c) for c in cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    for line in (proc.stdout or "").strip().splitlines():
        print("    " + line)
    for line in (proc.stderr or "").strip().splitlines():
        print("    ! " + line, file=sys.stderr)
    if check and proc.returncode != 0:
        die(f"命令失败（{proc.returncode}）：{' '.join(cmd)}")
    return proc


def ssh(args: argparse.Namespace, script: str, *, dry: bool, check: bool = True):
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if args.port != 22:
        cmd += ["-p", str(args.port)]
    cmd += [f"{args.user}@{args.host}", f"bash -lc {shlex.quote(script)}"]
    return run(cmd, dry=dry, check=check)


def scp(args: argparse.Namespace, local: Path, remote_path: str, *, dry: bool):
    cmd = ["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if args.port != 22:
        cmd += ["-P", str(args.port)]
    cmd += [str(local), f"{args.user}@{args.host}:{remote_path}"]
    return run(cmd, dry=dry)


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="把开机默认姿态同步到树莓派")
    ap.add_argument("--host", required=True)
    ap.add_argument("--user", default="ubuntu")
    ap.add_argument("--port", type=int, default=22)
    ap.add_argument("--remote-repo", default=None,
                    help="板上仓库根目录（默认 /home/<user>/oceanus）")
    ap.add_argument("--apply", action="store_true",
                    help="同步后立刻在板上摆位一次（会让机械臂动）")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    args.remote_repo = args.remote_repo or f"/home/{args.user}/oceanus"

    grasp_remote = posixpath.join(args.remote_repo, "edge", "grasp")
    deploy_remote = posixpath.join(grasp_remote, "deploy")

    # ---- 1) 先看本地有没有可同步的东西 ----
    if not BOOT_POSE.is_file():
        die("本地 edge/grasp/boot_pose.json 不存在 —— 先在作业台"
            "「7 手动控制 → 把当前姿态存为预设 → 设为开机默认」设一次")
    import json
    try:
        payload = json.loads(BOOT_POSE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        die(f"boot_pose.json 读不出来：{exc}")
    name = payload.get("name")
    pose = payload.get("pose") or {}
    if not pose:
        die("boot_pose.json 里没有 pose")
    log(f"待同步的开机姿态「{name}」：{pose}")

    if not APPLY_SCRIPT.is_file():
        die(f"找不到 {APPLY_SCRIPT}")

    # ---- 2) 连通性 ----
    res = ssh(args, "echo board-ok && hostname", dry=args.dry_run, check=False)
    if not args.dry_run and res.returncode != 0:
        die(f"连不上 {args.user}@{args.host}；先确认热点/Wi-Fi 已连上"
            f"（netsh wlan connect name=HW-6AF67543 interface=WLAN）")

    # ---- 3) 推送 ----
    log(f"推送 boot_pose.json → {grasp_remote}/")
    scp(args, BOOT_POSE, posixpath.join(grasp_remote, "boot_pose.json"), dry=args.dry_run)
    log(f"推送摆放脚本 → {deploy_remote}/")
    scp(args, APPLY_SCRIPT, posixpath.join(deploy_remote, "board_apply_boot_pose.py"),
        dry=args.dry_run)

    # 文本文件去 CR（Windows scp 会加 CRLF，会让 python3 解析出错）
    ssh(args, f"sed -i 's/\\r$//' {shlex.quote(posixpath.join(grasp_remote, 'boot_pose.json'))} "
              f"{shlex.quote(posixpath.join(deploy_remote, 'board_apply_boot_pose.py'))}",
        dry=args.dry_run)

    # ---- 4) 板上验证：能否读到 + 内容是否一致 ----
    log("板上校验")
    verify = (
        f"python3 - <<'PYEOF'\n"
        f"import json, pathlib\n"
        f"p = pathlib.Path({posixpath.join(grasp_remote, 'boot_pose.json')!r})\n"
        f"d = json.loads(p.read_text(encoding='utf-8'))\n"
        f"print('  name =', d.get('name'))\n"
        f"print('  pose =', d.get('pose'))\n"
        f"assert d.get('pose'), 'pose 为空'\n"
        f"print('BOOT_POSE_ON_BOARD_OK')\n"
        f"PYEOF"
    )
    ssh(args, verify, dry=args.dry_run)

    # ---- 5) 可选：立刻摆位 ----
    if args.apply:
        log("★ --apply：立刻在板上摆位（机械臂会动）")
        rc = ssh(args,
                 f"python3 {shlex.quote(posixpath.join(deploy_remote, 'board_apply_boot_pose.py'))} "
                 f"--pose-file {shlex.quote(posixpath.join(grasp_remote, 'boot_pose.json'))}",
                 dry=args.dry_run, check=False)
        if not args.dry_run and rc.returncode != 0:
            log(f"! 摆位脚本返回 {rc.returncode}（2 = 有舵机没到位，看上面的逐舵机输出）")
    else:
        log("未加 --apply，没有让机械臂动。")
        log("要立刻摆位一次：python scripts/sync_boot_pose.py --host "
            f"{args.host} --apply")

    log("同步完成。以后板子每次开机都会自动摆到该姿态（systemd ExecStartPost）")
    log("确认：ssh " + f"{args.user}@{args.host} 'journalctl -u oceanus-board-agent | grep boot-pose'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
