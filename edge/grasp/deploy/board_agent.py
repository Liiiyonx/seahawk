#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""板上执行代理（runtime: **python2.7 + ROS melodic**）。

用途：把「机械臂执行端」以一条 JSON-over-TCP 长连接暴露给开发机上的作业台
（`edge/grasp/web/server.py`）。开发机（Windows）没有 ROS、也碰不到舵机总线，
但作业台要能看实时画面、点动舵机、开合夹爪、回待命位、读真实遥测 —— 这中间
就隔着这条代理。

三条硬约束沿用 `edge/grasp/arm_io.py`（都由厂商源码实测得出），本代理同样遵守：

1. **不抢串口**。厂商 `hiwonder_servo_manager` 持有舵机总线，本代理只往
   `/servo_controllers/port_id_1/multi_id_pos_dur` 发控制消息，只读厂商已发布的
   `/servo_controllers/port_id_1/servo_states`。
2. **不抢摄像头**。只订阅 `usb_cam` 已发布的图像话题，不打开 `/dev/video*`。
3. **不 import 厂商 `bus_servo_control`**（它 import 时注册 SIGINT handler 并
   `rospy.signal_shutdown()`，会劫持服务进程的退出信号）。

为什么是 python2.7 而不是 python3：厂商 ROS 工作空间只装在 py2.7 下（实测
py3.6 无 rospy）。IK 反过来只在 py3.6 下可用（py2.7 那份 `kinematics` `.so` 是
py3 编译的错误拷贝）。因此 IK 交给 `ik_worker.py` 这只 py3.6 常驻子进程，
本代理用管道喂坐标、收脉宽 —— 详见 `ik_worker.py` 的说明。

启动（板上）：

    source /opt/ros/melodic/setup.bash
    source $HOME/armpi_fpv/devel/setup.bash
    export ROS_HOSTNAME=ubuntu ROS_MASTER_URI=http://ubuntu:11311
    python2 board_agent.py --port 8093 --params /home/ubuntu/oceanus_board/board_params.json

自检（开发机）：

    python scripts/deploy_board_agent.py --host 192.168.149.1
"""

from __future__ import print_function

import argparse
import base64
import json
import os
import select
import socket
import subprocess
import sys
import threading
import time
import traceback

import SocketServer

import rospy
from hiwonder_servo_msgs.msg import MultiRawIdPosDur, RawIdPosDur, ServoStateList
from sensor_msgs.msg import Image

#: 默认参数 —— 与 `edge/grasp/config.yaml` 的 `arm` 段同口径。
#: 部署脚本会从 config.yaml 生成 `board_params.json` 覆盖它们，避免两边漂移。
DEFAULTS = {
    "servo_topic": "/servo_controllers/port_id_1/multi_id_pos_dur",
    "servo_states_topic": "/servo_controllers/port_id_1/servo_states",
    "camera_topic": "/usb_cam/image_raw",
    "gripper_servo": 1,
    "wrist_servo": 2,
    "ik_servos": [3, 4, 5, 6],
    "gripper_open": 200,
    "gripper_close": 450,
    "gripper_step": 20,
    "gripper_step_wait": 0.12,
    "wrist_center": 500,
    "default_duration_ms": 800,
    "home": {"coord": [0.0, 0.17, 0.30], "pitch": -65, "pitch_range": [-180, 0]},
}

AGENT_VERSION = "2026.10.16"


def log(msg):
    # py2：json 读进来的话题名是 unicode，而本文件的中文字面量是 utf-8 str；
    # 「str 格式化 + unicode 参数」会触发 ascii 解码（现场踩过：日志里一句中文
    # 配一个 unicode 话题名，代理直接起不来）。统一编码成 utf-8 str 再打印。
    if isinstance(msg, unicode):
        msg = msg.encode("utf-8")
    print("[board_agent] %s" % msg)
    sys.stdout.flush()


def to_bytes(value):
    """把 json 读进来的 unicode 递归降回 utf-8 ``str``（py2 下两者混用会炸）。"""
    if isinstance(value, unicode):
        return value.encode("utf-8")
    if isinstance(value, dict):
        return dict((to_bytes(k), to_bytes(v)) for k, v in value.items())
    if isinstance(value, list):
        return [to_bytes(item) for item in value]
    return value


# ======================================================================
# 执行代理
# ======================================================================
class BoardAgent(object):
    def __init__(self, params, ik_timeout=3.0):
        self.cfg = dict(DEFAULTS)
        self.cfg.update(to_bytes(params or {}))
        if not isinstance(self.cfg.get("home"), dict):
            self.cfg["home"] = dict(DEFAULTS["home"])

        self.ik_timeout = float(ik_timeout)
        self.start_time = time.time()
        self.ros_error = None
        self.ik_error = None
        self._lock = threading.RLock()
        self._ik_lock = threading.RLock()
        self._states = {}
        self._last_pulses = {}
        self._frame = None
        self._frame_ts = 0.0
        self._frame_count = 0
        self._bridge = None
        self._pub = None
        self._ik = None

        self._start_ros()
        self._start_ik()

    # ------------------------------------------------------------------
    # ROS 接入（失败只记录，不退出 —— 让开发机那边能看到排障原因）
    # ------------------------------------------------------------------
    def _start_ros(self):
        try:
            rospy.init_node("oceanus_board_agent", anonymous=False, disable_signals=True)
            self._pub = rospy.Publisher(
                self.cfg["servo_topic"], MultiRawIdPosDur, queue_size=1
            )
            rospy.Subscriber(
                self.cfg["servo_states_topic"], ServoStateList,
                self._on_states, queue_size=1,
            )
            rospy.Subscriber(
                self.cfg["camera_topic"], Image, self._on_image, queue_size=1
            )
        except Exception as exc:  # noqa: BLE001
            self.ros_error = "%s: %s" % (type(exc).__name__, exc)
            log("ROS 接入失败（代理仍会起来，status 里会给出原因）：%s" % self.ros_error)
            return
        log("ROS 已接入：servo=%s states=%s camera=%s"
            % (self.cfg["servo_topic"], self.cfg["servo_states_topic"],
               self.cfg["camera_topic"]))

    def _on_states(self, msg):
        with self._lock:
            for st in getattr(msg, "servo_states", []) or []:
                self._states[str(st.id)] = {
                    "vin": round(float(st.voltage), 2),   # mV，与作业台页面换算口径一致
                    "position": int(st.position),
                    "goal": int(st.goal),
                    "error": int(st.error),
                }

    def _on_image(self, msg):
        if self._bridge is None:
            try:
                import cv_bridge
                self._bridge = cv_bridge.CvBridge()
            except ImportError as exc:
                self.ros_error = "cv_bridge 不可用：%s" % exc
                return
        try:
            frame = self._bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as exc:  # noqa: BLE001
            self.ros_error = "图像转换失败：%s" % exc
            return
        with self._lock:
            # copy：cv_bridge 结果的生命周期跟随 msg，存引用会让下一帧覆盖它
            self._frame = frame.copy()
            self._frame_ts = time.time()
            self._frame_count += 1

    # ------------------------------------------------------------------
    # IK 子进程（py3.6）
    # ------------------------------------------------------------------
    def _start_ik(self):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ik_worker.py")
        if not os.path.isfile(script):
            self.ik_error = "ik_worker.py 不在同目录：%s" % script
            log(self.ik_error)
            return
        try:
            errlog = open("/tmp/oceanus_ik_worker.log", "ab")
            self._ik = subprocess.Popen(
                ["python3", "-u", script],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errlog,
                cwd=os.path.dirname(script),
            )
        except Exception as exc:  # noqa: BLE001
            self.ik_error = "IK 子进程启动失败：%s" % exc
            log(self.ik_error)
            return
        # 读掉就绪行（子进程 import kinematics 后自报 ready）
        if not self._readable(self.ik_timeout):
            self.ik_error = "IK 子进程 %ss 内没就绪：看 /tmp/oceanus_ik_worker.log" % self.ik_timeout
            log(self.ik_error)
            return
        ready = self._ik.stdout.readline()
        try:
            payload = json.loads(ready)
        except ValueError:
            payload = {}
        if not payload.get("ok"):
            self.ik_error = "IK 子进程自检失败：%r" % ready
            log(self.ik_error)
            return
        log("IK 子进程就绪（py3.6，pid=%s）" % payload.get("pid"))

    def _readable(self, timeout):
        ready, _, _ = select.select([self._ik.stdout], [], [], float(timeout))
        return bool(ready)

    def ik_call(self, req):
        if self._ik is None:
            raise RuntimeError("IK 不可用：%s" % self.ik_error)
        if self._ik.poll() is not None:
            self.ik_error = "IK 子进程已退出（rc=%s）" % self._ik.returncode
            raise RuntimeError("IK 不可用：%s" % self.ik_error)
        with self._ik_lock:
            self._ik.stdin.write(json.dumps(req) + "\n")
            self._ik.stdin.flush()
            if not self._readable(self.ik_timeout):
                raise RuntimeError("IK 解算超时（%ss）" % self.ik_timeout)
            line = self._ik.stdout.readline()
        try:
            return json.loads(line)
        except ValueError:
            raise RuntimeError("IK 子进程返回不可解析：%r" % line)

    # ------------------------------------------------------------------
    # 舵机下发
    # ------------------------------------------------------------------
    def _publish_servos(self, duration_ms, pairs):
        clean = []
        for sid, pos in pairs:
            sid, pos = int(sid), int(pos)
            if not 0 <= pos <= 1000:
                raise ValueError("舵机脉宽必须在 0..1000 之间，收到 %s:%s" % (sid, pos))
            clean.append((sid, pos))
        if not clean:
            raise ValueError("没有要下发的舵机")
        if self.ros_error:
            raise RuntimeError("ROS 链路不可用：%s" % self.ros_error)
        if self._pub is None:
            raise RuntimeError("舵机发布器未就绪")
        dur = int(duration_ms or self.cfg["default_duration_ms"])
        msg = MultiRawIdPosDur()
        msg.id_pos_dur_list = [
            RawIdPosDur(sid, pos, dur) for sid, pos in clean
        ]
        self._pub.publish(msg)
        with self._lock:
            for sid, pos in clean:
                self._last_pulses[sid] = pos

    def _duration(self, req):
        value = req.get("duration_ms")
        return int(value) if value else int(self.cfg["default_duration_ms"])

    # ------------------------------------------------------------------
    # 画面
    # ------------------------------------------------------------------
    def op_frame(self, req):
        import cv2

        with self._lock:
            frame = None if self._frame is None else self._frame.copy()
            ts = self._frame_ts
        if frame is None:
            return {"ok": False, "error": "还没有画面：相机话题没数据 / 未 source 厂商工作空间"}
        max_w = int(req.get("max_width") or 640)
        h, w = frame.shape[:2]
        if max_w and w > max_w:
            scale = float(max_w) / float(w)
            frame = cv2.resize(frame, (max_w, int(round(h * scale))))
        ok, buf = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(req.get("quality") or 70)]
        )
        if not ok:
            return {"ok": False, "error": "JPEG 编码失败"}
        return {
            "ok": True,
            "jpeg_b64": base64.b64encode(buf.tostring()).decode("ascii"),
            "w": int(frame.shape[1]),
            "h": int(frame.shape[0]),
            "age": round(time.time() - ts, 3) if ts else None,
            "count": self._frame_count,
        }

    # ------------------------------------------------------------------
    # 遥测
    # ------------------------------------------------------------------
    def op_telemetry(self, req):
        with self._lock:
            return {"ok": True, "servos": {k: dict(v) for k, v in self._states.items()}}

    def op_status(self, req):
        with self._lock:
            frame_age = 0.0 if not self._frame_ts else round(time.time() - self._frame_ts, 3)
            shape = None
            if self._frame is not None:
                shape = [int(self._frame.shape[1]), int(self._frame.shape[0])]
            states = len(self._states)
        return {
            "ok": True,
            "agent_version": AGENT_VERSION,
            "host": socket.gethostname(),
            "ros_error": self.ros_error,
            "ik_error": self.ik_error,
            "ik_ready": self._ik is not None and self._ik.poll() is None,
            "camera_topic": self.cfg["camera_topic"],
            "frame": {"shape": shape, "age": frame_age, "count": self._frame_count},
            "servo_state_count": states,
            "uptime_s": round(time.time() - self.start_time, 1),
        }

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------
    def op_set_servos(self, req):
        pairs = [(int(a), int(b)) for a, b in (req.get("pairs") or [])]
        self._publish_servos(self._duration(req), pairs)
        return {"ok": True, "pairs": pairs}

    def op_set_servo(self, req):
        pairs = [(int(req["servo_id"]), int(req["position"]))]
        self._publish_servos(self._duration(req), pairs)
        return {"ok": True, "pairs": pairs}

    def op_move_to(self, req):
        if self.ik_error:
            raise RuntimeError("IK 不可用：%s" % self.ik_error)
        home = self.cfg["home"]
        pitch = req.get("pitch")
        pitch = float(home["pitch"]) if pitch is None else float(pitch)
        rng = req.get("pitch_range") or home["pitch_range"]
        extra = [(int(a), int(b)) for a, b in (req.get("extra_pairs") or [])]

        resp = self.ik_call({
            "op": "solve",
            "x": float(req["x"]), "y": float(req["y"]), "z": float(req["z"]),
            "pitch": pitch,
            "alpha1": float(rng[0]), "alpha2": float(rng[1]),
            "d": float(req.get("d", 0.01)),
        })
        if not resp.get("ok"):
            # 目标不可达：由调用方决定换目标还是重试（与 arm_io.move_to 同语义）
            return {"ok": True, "reachable": False, "servos": {}}

        servos = resp.get("servos") or {}
        pairs = list(extra)
        for sid in self.cfg["ik_servos"]:
            key = "servo%d" % int(sid)
            if key in servos:
                pairs.append((int(sid), int(servos[key])))
        self._publish_servos(self._duration(req), pairs)
        return {"ok": True, "reachable": True, "servos": servos,
                "alpha": resp.get("alpha"), "pairs": pairs}

    def op_home(self, req):
        home = self.cfg["home"]
        coord = home["coord"]
        return self.op_move_to({
            "x": coord[0], "y": coord[1], "z": coord[2],
            "pitch": home["pitch"], "pitch_range": home["pitch_range"],
            "duration_ms": int(req.get("duration_ms") or 1500),
            "extra_pairs": [[int(self.cfg["wrist_servo"]), int(self.cfg["wrist_center"])]],
        })

    def op_gripper_open(self, req):
        sid = int(self.cfg["gripper_servo"])
        pulse = int(req.get("pulse") or self.cfg["gripper_open"])
        self._publish_servos(self._duration(req), [(sid, pulse)])
        return {"ok": True, "pulse": pulse}

    def op_gripper_close(self, req):
        """渐进闭合 + 回读停滞判据（自适应夹取）。

        ★ 闭合方向由脉宽决定，不能写死加减号 —— 厂商口径是**脉宽越大越闭**
          （`warehouse/in.py` 夹住 450 / 松开 75）。`open < close` 时每步要**加**。
        ★ 回读来自厂商 `servo_states`（板上 7Hz），读不到就按步数走完，
          不会误判成「夹到了」。
        """
        sid = int(self.cfg["gripper_servo"])
        start = int(req.get("open_pulse") or self.cfg["gripper_open"])
        target = int(req.get("close_pulse") or self.cfg["gripper_close"])
        step = abs(int(req.get("step") or self.cfg["gripper_step"]))
        step = step if target >= start else -step
        wait = req.get("step_wait")
        wait = float(self.cfg["gripper_step_wait"]) if wait is None else float(wait)
        threshold = int(req.get("stall_threshold") or 8)
        max_steps = int(req.get("max_steps") or 24)

        pos = start
        stall = 0
        prev = None
        stalled = False
        for _ in range(max_steps):
            pos += step
            if (step > 0 and pos > target) or (step < 0 and pos < target):
                pos = target
            self._publish_servos(int(wait * 1000), [(sid, pos)])
            time.sleep(wait)
            with self._lock:
                row = self._states.get(str(sid)) or {}
            read = row.get("position")
            if read is not None and prev is not None:
                if abs(int(read) - int(prev)) <= threshold:
                    stall += 1
                    if stall >= 2:
                        stalled = True
                        break
                else:
                    stall = 0
            prev = read
            if pos == target:
                break
        return {"ok": True, "pulse": pos, "stalled": stalled}

    # ------------------------------------------------------------------
    def handle(self, req):
        op = req.get("op")
        table = {
            "ping": lambda r: {"ok": True, "pong": True, "agent_version": AGENT_VERSION},
            "status": self.op_status,
            "telemetry": self.op_telemetry,
            "frame": self.op_frame,
            "set_servos": self.op_set_servos,
            "set_servo": self.op_set_servo,
            "move_to": self.op_move_to,
            "home": self.op_home,
            "gripper_open": self.op_gripper_open,
            "gripper_close": self.op_gripper_close,
        }
        handler = table.get(op)
        if handler is None:
            raise ValueError("未知 op：%r" % op)
        return handler(req)


# ======================================================================
# TCP 服务（换行分隔 JSON；多连接并发，画面轮询不会被点动阻塞）
# ======================================================================
class RequestHandler(SocketServer.StreamRequestHandler):
    def handle(self):
        agent = self.server.agent
        while True:
            line = self.rfile.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            rid = None
            try:
                req = json.loads(line)
                rid = req.get("id")
                payload = agent.handle(req)
                if not isinstance(payload, dict):
                    payload = {"ok": True, "result": payload}
            except Exception as exc:  # noqa: BLE001
                payload = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
                traceback.print_exc()
            payload["id"] = rid
            try:
                self.wfile.write(json.dumps(payload) + "\n")
            except Exception:  # noqa: BLE001 - 对端断开
                break


class ThreadedServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Oceanus 板上机械臂执行代理")
    ap.add_argument("--params", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "board_params.json"))
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8093)
    ap.add_argument("--ik-timeout", type=float, default=3.0)
    ap.add_argument("--pidfile", default=None,
                    help="把自身 pid 写到这里（便于重启时精确 kill；"
                         "用 `pkill -f board_agent.py` 会连执行它的 shell 一起杀）")
    args = ap.parse_args(argv)

    params = {}
    if args.params and os.path.isfile(args.params):
        with open(args.params) as fh:
            params = json.load(fh)
        log("已加载参数：%s" % args.params)
    else:
        log("未找到 %s，用内置默认值（与 config.yaml 同口径）" % args.params)

    agent = BoardAgent(params, ik_timeout=args.ik_timeout)
    server = ThreadedServer((args.host, args.port), RequestHandler)
    server.agent = agent
    log("监听 %s:%s（协议：换行分隔 JSON）" % (args.host, args.port))
    if args.pidfile:
        try:
            with open(args.pidfile, "w") as fh:
                fh.write(str(os.getpid()))
        except IOError as exc:
            log("pidfile 写入失败（不影响运行）：%s" % exc)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("收到中断，退出")
    finally:
        if args.pidfile and os.path.isfile(args.pidfile):
            try:
                os.remove(args.pidfile)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
