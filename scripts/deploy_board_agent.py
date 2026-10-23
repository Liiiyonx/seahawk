"""把板上执行代理部署到树莓派，并从开发机做（默认只读的）验证。

★ 安全边界（与 `scripts/deploy_bridge_to_pi.py` 同一条纪律）：
  本脚本默认**只做只读验证** —— ping / status / telemetry / frame，不下发任何
  运动指令。要动臂必须显式加 `--allow-motion`，而且那一步应该有人在现场盯着：
  首次部署就自动驱动机械臂是不负责任的。

为什么需要这层代理（而不是让作业台直接接 ROS）：
  · 作业台（FastAPI）跑在开发机上，机械臂挂在树莓派的 ROS/舵机总线上；
  · 开发机（Windows）没有 ROS、也碰不到那根总线；
  · 板上 ROS 只在 **python2.7** 下可用（py3.6 没有 rospy），而厂商 IK 反过来
    只在 **py3.6** 下可用（py2.7 那份 kinematics `.so` 是 py3 编译的错误拷贝，
    `undefined symbol: _Py_FalseStruct`）。
  因此板上拆成两只进程：`board_agent.py`（py2.7，ROS 下发/回读/取帧）
  + `ik_worker.py`（py3.6，逆运动学），本脚本负责把两者与参数一起送上去。

用法：
    # 只读验证（安全默认）
    python scripts/deploy_board_agent.py --host 192.168.149.1

    # 现场有人盯着时，验证真实动作
    python scripts/deploy_board_agent.py --host 192.168.149.1 --allow-motion --swing
    python scripts/deploy_board_agent.py --host 192.168.149.1 --allow-motion --gripper open
    python scripts/deploy_board_agent.py --host 192.168.149.1 --allow-motion --home
"""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDGE = os.path.join(REPO, "edge")
for _p in (EDGE, os.path.join(EDGE, "grasp")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CONFIG_LOCAL = os.path.join(EDGE, "grasp", "config.yaml")

#: 需要上板的文件：(仓库内路径, 板上相对路径)
UPLOADS = [
    (os.path.join(EDGE, "grasp", "deploy", "board_agent.py"), "board_agent.py"),
    (os.path.join(EDGE, "grasp", "deploy", "ik_worker.py"), "ik_worker.py"),
]

#: `board_params.json` 白名单 —— 只送代理真正用的字段，避免把 usb_camera /
#: remote / plane_z 这类本机口径混到板上（那是"看起来在用、其实没用"的隐患）。
PARAM_KEYS = [
    "servo_topic", "servo_states_topic", "camera_topic",
    "gripper_servo", "wrist_servo", "ik_servos",
    "gripper_open", "gripper_close", "gripper_step", "gripper_step_wait",
    "wrist_center", "default_duration_ms", "home",
]


def load_arm_config() -> dict:
    import yaml

    with open(CONFIG_LOCAL, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    arm = cfg.get("arm") or {}
    if not arm:
        raise SystemExit("config.yaml 里没有 arm 段：%s" % CONFIG_LOCAL)
    return arm


def build_params(arm: dict) -> dict:
    return {k: arm[k] for k in PARAM_KEYS if k in arm}


def main() -> int:
    ap = argparse.ArgumentParser(description="部署并验证板上机械臂执行代理")
    ap.add_argument("--host", default="192.168.149.1")
    ap.add_argument("--user", default="ubuntu")
    ap.add_argument("--password", default=None, help="留空读环境变量 PI_PASSWORD")
    ap.add_argument("--remote-dir", default="/home/ubuntu/oceanus_board")
    ap.add_argument("--port", type=int, default=8093)
    ap.add_argument("--allow-motion", action="store_true",
                    help="★ 允许下发运动指令（默认只读验证）")
    ap.add_argument("--swing", action="store_true",
                    help="舵机 6 摆动 620→380→500（需 --allow-motion）")
    ap.add_argument("--gripper", choices=["open", "close"], default=None,
                    help="夹爪开/合一次（需 --allow-motion）")
    ap.add_argument("--home", action="store_true",
                    help="回待命位（需 --allow-motion）")
    ap.add_argument("--frame-out", default=None, help="把验证到的一帧存成 jpg")
    ap.add_argument("--skip-deploy", action="store_true", help="只做验证，不上传/不重启")
    args = ap.parse_args()

    password = args.password or os.environ.get("PI_PASSWORD", "hiwonder")
    if args.allow_motion:
        print("★ --allow-motion 已开启：接下来的指令会真实驱动机械臂，"
              "请确认现场有人盯着。", file=sys.stderr)

    arm = load_arm_config()
    params = build_params(arm)
    print("板上参数（取自 edge/grasp/config.yaml 的 arm 段）：")
    print(json.dumps(params, ensure_ascii=False, indent=2))

    if not args.skip_deploy:
        rc = deploy(args, password, params)
        if rc != 0:
            return rc

    return verify(args, arm)


def deploy(args, password: str, params: dict) -> int:
    try:
        import paramiko
    except ImportError:
        print("需要 paramiko：pip install paramiko", file=sys.stderr)
        return 2

    missing = [src for src, _ in UPLOADS if not os.path.isfile(src)]
    if missing:
        print("本地缺少文件：%s" % missing, file=sys.stderr)
        return 2

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        cli.connect(args.host, username=args.user, password=password,
                    timeout=25, banner_timeout=25, auth_timeout=25)
    except Exception as exc:  # noqa: BLE001
        print("连接失败 %s@%s：%s" % (args.user, args.host, exc), file=sys.stderr)
        print("排查：① 电脑是否连上树莓派热点 ② 树莓派是否还开着", file=sys.stderr)
        return 1

    def run(cmd: str, timeout: int = 60) -> str:
        _, so, se = cli.exec_command(cmd, timeout=timeout)
        so.channel.settimeout(timeout)
        try:
            out = so.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            return "(read timeout: %s)" % type(exc).__name__
        err = se.read().decode("utf-8", "replace")
        return (out or "") + (("\n[stderr] " + err) if err.strip() else "")

    try:
        # ── 1. 上传 ──
        print("\n1) 上传代理文件 → %s" % args.remote_dir)
        run("mkdir -p %s" % args.remote_dir).strip()
        sftp = cli.open_sftp()
        for src, rel in UPLOADS:
            remote = posixpath.join(args.remote_dir, rel)
            sftp.put(src, remote)
            print("   %s" % rel)
        params_remote = posixpath.join(args.remote_dir, "board_params.json")
        with sftp.open(params_remote, "w") as fh:
            fh.write(json.dumps(params, ensure_ascii=False, indent=2))
        print("   board_params.json")
        sftp.close()

        # ── 2. 重启代理 ──
        print("\n2) 重启板上代理（python2.7 + ROS）")
        log_remote = "/tmp/oceanus_board_agent.log"
        pid_remote = "/tmp/oceanus_board_agent.pid"
        # ★ 用 pidfile / 端口定位旧进程，**不用 `pkill -f board_agent.py`**：
        #   exec_command 的 wrapper 命令行本身就含这个串，pkill 会把执行它的
        #   shell 一起杀掉 —— 表现为「重启步骤一句回显都没有」（已踩过）。
        kill_cmd = (
            "if [ -f %s ]; then kill $(cat %s) >/dev/null 2>&1; fi; sleep 0.6; "
            "if (exec 3<>/dev/tcp/127.0.0.1/%d) 2>/dev/null; then "
            "echo PORT_STILL_OPEN; else echo PORT_FREE; fi"
            % (pid_remote, pid_remote, args.port)
        )
        print("   " + run(kill_cmd, timeout=30).strip())

        # ★ 整个后台任务组一起重定向到日志（`( … ) > LOG 2>&1 < /dev/null &`）：
        #   只在 python 命令上重定向时，后台子壳仍持有 exec_command 的 stdout 管道，
        #   对端读不到 EOF → 表现为「本步骤读超时、一句回显都没有」（已踩过）。
        start_cmd = (
            "( cd {dir} && export ROS_HOSTNAME=ubuntu "
            "ROS_MASTER_URI=http://ubuntu:11311 "
            "&& source /opt/ros/melodic/setup.bash "
            "&& source $HOME/armpi_fpv/devel/setup.bash "
            "&& exec nohup python2 -u board_agent.py --port {port} "
            "--params board_params.json --pidfile {pid} "
            ") > {log} 2>&1 < /dev/null & echo LAUNCHED; sleep 3; "
            "echo '--- pidfile ---'; cat {pid} 2>/dev/null || echo NO_PIDFILE; "
            "echo '--- log tail ---'; tail -25 {log}"
        ).format(dir=args.remote_dir, port=args.port, log=log_remote, pid=pid_remote)
        print("   " + run("bash -c %s" % _quote(start_cmd), timeout=90).strip()[-2500:])

        # ── 3. 端口就绪 ──
        print("\n3) 端口就绪检查")
        print("   " + run(
            "for i in $(seq 1 12); do "
            "(exec 3<>/dev/tcp/127.0.0.1/%d) 2>/dev/null && "
            "{ echo PORT_%d_OPEN; break; } || sleep 0.5; done" % (args.port, args.port),
            timeout=30).strip())
    finally:
        cli.close()
    return 0


def _quote(text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


def verify(args, arm: dict) -> int:
    from grasp.arm_io import ArmIoError, ArmIoRemote

    cfg = {"arm": dict(arm)}
    cfg["arm"]["remote"] = {"enabled": True, "host": args.host, "port": args.port,
                            "timeout": 30.0}
    io = ArmIoRemote(cfg)
    print("\n4) 只读验证（开发机 → 板上代理 %s:%s）" % (args.host, args.port))
    try:
        io.start()
    except ArmIoError as exc:
        print("   ✗ 链路失败：%s" % exc, file=sys.stderr)
        return 1
    if io.ros_error:
        print("   ✗ 板上代理自报异常：%s" % io.ros_error, file=sys.stderr)
        return 1
    print("   ✓ ping 通")

    # 给取帧线程一点时间拿到第一帧
    deadline = time.time() + 8.0
    while time.time() < deadline and io.latest_frame() is None:
        time.sleep(0.2)
    frame = io.latest_frame()
    if frame is None:
        print("   ✗ 拿不到画面（板上相机话题没数据？）", file=sys.stderr)
    else:
        h, w = frame.shape[:2]
        print("   ✓ 实时画面 %d×%d（帧龄 %.2fs）" % (w, h, io.frame_age()))
        if args.frame_out:
            import cv2
            cv2.imwrite(args.frame_out, frame)
            print("     已存：%s" % args.frame_out)

    tele = io.servo_telemetry() or {}
    if not tele:
        print("   ⚠ 遥测为空 —— 舵机状态话题没数据？")
    else:
        print("   ✓ 舵机回读 %d 个：" % len(tele))
        for sid, row in sorted(tele.items(), key=lambda kv: int(kv[0])):
            print("     #%-3s vin=%8s mV  position=%4s  goal=%4s  error=%s"
                  % (sid, row.get("vin"), row.get("position"),
                     row.get("goal"), row.get("error")))

    # ── 可选：真实动作（必须显式 --allow-motion）──
    if args.swing or args.gripper or args.home:
        if not args.allow_motion:
            print("\n   （给了动作开关但没加 --allow-motion，故不下发任何运动指令）",
                  file=sys.stderr)
    if args.allow_motion:
        _motion(io, args)

    io.stop()
    return 0


def _motion(io, args) -> None:
    print("\n5) 真实动作（★ 臂在动，请盯着）")
    if args.swing:
        print("   舵机 6 摆动：620 → 380 → 500")
        for pulse in (620, 380, 500):
            io.set_servo(6, pulse, 2000)
            time.sleep(2.4)
        print("   ✓ 摆动完成")
    if args.gripper == "open":
        io.gripper_open()
        print("   ✓ 夹爪张开（脉宽 %d）" % io.gripper_open_pulse)
    elif args.gripper == "close":
        pulse = io.gripper_close_adaptive()
        print("   ✓ 夹爪渐闭至脉宽 %d（停滞判据由板端回读决定）" % pulse)
    if args.home:
        ok = io.home()
        print("   %s 回待命位（IK reachable=%s）" % ("✓" if ok else "✗", ok))

    dead = time.time() + 2.0
    while time.time() < dead:
        time.sleep(0.4)
    tele = io.servo_telemetry() or {}
    print("   动作后遥测：")
    for sid, row in sorted(tele.items(), key=lambda kv: int(kv[0])):
        print("     #%-3s position=%4s  goal=%4s" % (sid, row.get("position"),
                                                      row.get("goal")))


if __name__ == "__main__":
    sys.exit(main())
