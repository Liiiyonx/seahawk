"""树莓派上的训练作业台（web 层）。

页面职责（对应实施计划书 §4.1）：工单上下文 / 实时画面 / 数据采集 /
标注台 / 训练任务 / 部署验证，外加手动点动与标定引导。

**页面跑在树莓派上、不在平台里**：浏览器直连 ``http://<IP>:8090``，
采集、训练、部署、作业控制全部在 Pi 本地闭环；平台只做入口与看板，
MQTT 契约一行不用改（平台侧把环境变量配成 ``http://{ip}:8090`` 即可）。

启动：

    # 真机（先 source 厂商工作空间）
    source ~/armpi_fpv/devel/setup.bash && python3 -m grasp.web.server

    # 开发机（无 ROS，合成画面 + 模拟舵机跑通 UI）
    python -m grasp.web.server --mock

训练进度用**轮询**（``/api/train/status``）而不是 SSE：轮询实现更短、
断线自恢复、也不占长连接；演示场景下 0.5s 粒度完全够用。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
GRASP_DIR = HERE.parent
EDGE_DIR = GRASP_DIR.parent
for path in (str(EDGE_DIR), str(GRASP_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from grasp.arm_io import ArmIo, ArmIoError                      # noqa: E402
from grasp.calibration import (                                 # noqa: E402
    Calibration,
    capture_at_observation,
    config_plane_z,
    demo_calibration,
    describe_place,
    load_calibration,
    save_calibration,
)
from grasp.config import load_config                            # noqa: E402
from grasp.grasp_loop import GraspLoop                          # noqa: E402
from grasp.vision.dataset import Box, Dataset, DatasetError     # noqa: E402
from grasp.vision.deploy import DeployError, ModelStore         # noqa: E402
from grasp.vision.detector import Detector                      # noqa: E402
from grasp.vision.evaluate import evaluate, passes              # noqa: E402
from grasp.vision.train import TIERS, TrainingError, train, training_available  # noqa: E402

logger = logging.getLogger("oceanus.grasp.web")


# ======================================================================
# 运行时状态
# ======================================================================
@dataclass
class Job:
    """一个后台任务（采集 / 训练 / 标定 / 抓取）的进度快照。"""

    kind: str = ""
    running: bool = False
    stage: str = "idle"
    detail: dict[str, Any] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "running": self.running,
            "stage": self.stage,
            "detail": dict(self.detail),
            "log": list(self.log[-40:]),
            "result": self.result,
            "error": self.error,
            "elapsed": round(time.time() - self.started_at, 1) if self.started_at else 0.0,
        }


class TaskListener:
    """只读订阅平台派单，供页面显示工单上下文（不改平台契约）。"""

    def __init__(self, cfg: dict[str, Any]) -> None:
        mqtt = cfg.get("mqtt", {}) or {}
        self.enabled = bool(mqtt.get("enabled", True))
        # 与 arm_bridge/main.py 共用同一组环境变量：作业台在树莓派上跑时 broker
        # 在平台那侧（不是 localhost），现场由 systemd 注入。两边共用一个变量名，
        # 避免「桥接层连 A、作业台连 B」这种最难查的配置漂移。
        self.host = os.environ.get("OCEANUS_MQTT_HOST") or str(mqtt.get("host", "localhost"))
        self.port = int(os.environ.get("OCEANUS_MQTT_PORT") or mqtt.get("port", 1883))
        self.username = os.environ.get("OCEANUS_MQTT_USER") or str(mqtt.get("username", "robot_device"))
        self.password = os.environ.get("OCEANUS_MQTT_PASSWORD") or str(mqtt.get("password", "CHANGE_ME"))
        self.client_id = str(mqtt.get("client_id", "oceanus_grasp_web"))
        self.device_id = str(cfg.get("device_id", "RBT-ARM-01"))
        self.site_id = str(cfg.get("site_id", "lianjiang"))
        self.context: dict[str, Any] = {"status": "未连接"}
        self._client: Any = None

    @property
    def topic(self) -> str:
        return f"robot/{self.device_id}/task"

    def start(self) -> None:
        if not self.enabled:
            self.context = {"status": "已禁用（配置 mqtt.enabled=false）"}
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.context = {"status": "未安装 paho-mqtt，无法订阅派单"}
            return

        def _on_connect(client: Any, _userdata: Any, _flags: Any, rc: int) -> None:
            if rc == 0:
                client.subscribe(self.topic, qos=1)
                self.context = {"status": f"已订阅 {self.topic}"}
            else:
                self.context = {"status": f"MQTT 连接失败 rc={rc}"}

        def _on_message(_client: Any, _userdata: Any, msg: Any) -> None:
            import json

            try:
                payload = json.loads(msg.payload.decode("utf-8"))
            except ValueError:
                payload = {"raw": msg.payload.decode("utf-8", "ignore")}
            params = payload.get("params") or {}
            self.context = {
                "status": "已收到派单",
                "task_id": params.get("task_id"),
                "target": params.get("target"),
                "priority": params.get("priority"),
                "command_id": payload.get("command_id"),
                "received_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

        try:
            client = mqtt.Client(client_id=self.client_id)
            if self.username:
                client.username_pw_set(self.username, self.password)
            client.on_connect = _on_connect
            client.on_message = _on_message
            client.connect_async(self.host, self.port, 30)
            client.loop_start()
            self._client = client
        except Exception as exc:  # noqa: BLE001
            self.context = {"status": f"MQTT 启动失败：{exc}"}
            logger.warning("MQTT 订阅启动失败: %s", exc)

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass


class AppState:
    """进程内共享态（单进程服务，一个实例足够）。"""

    def __init__(self, cfg: dict[str, Any], mock: bool) -> None:
        self.cfg = cfg
        self.mock = mock
        self.io = ArmIo(cfg, mock=mock)
        self.detector = Detector(cfg, mock=mock)
        # 水面/台面高度：文件名里有就用文件里的（现场量的），否则用 config 的
        self.plane_z_default = config_plane_z(cfg)
        self.cal: Calibration = load_calibration(plane_z=self.plane_z_default)
        # mock 模式没有真机标定 —— 用演示映射，让状态接口与闭环口径一致
        self.cal_is_demo = False
        if mock and not self.cal.ready:
            self.cal = demo_calibration(
                plane_z=self.plane_z_default if self.plane_z_default is not None
                else self.cal.plane_z
            )
            self.cal_is_demo = True
        self.dataset = Dataset.from_config(cfg)
        self.store = ModelStore.from_config(cfg)
        self.loop = GraspLoop(self.io, self.detector, self.cal, cfg)
        self.listener = TaskListener(cfg)

        self.job = Job()
        self.capture_session: str = ""
        self.dets: list[Any] = []
        self.dets_ts: float = 0.0
        self._lock = threading.RLock()
        self._infer_thread: threading.Thread | None = None
        self._worker: threading.Thread | None = None
        self._stop_infer = threading.Event()

    # ------------------------------------------------------------------
    def start(self) -> None:
        self.io.start()
        backend = self.detector.load()
        logger.info("作业台启动：mock=%s 检测后端=%s 标定=%s",
                    self.mock, backend, self.cal.ready)
        self.listener.start()
        self._stop_infer.clear()
        self._infer_thread = threading.Thread(target=self._infer_loop, daemon=True)
        self._infer_thread.start()

    def stop(self) -> None:
        self._stop_infer.set()
        self.listener.stop()
        self.io.stop()

    def _infer_loop(self) -> None:
        """后台推理：4fps 产出检测框，供 MJPEG 叠加与状态上报。

        为什么不放在 MJPEG 循环里逐帧推理：Pi 上单帧推理几十到几百毫秒，
        会把推流帧率拖到个位数。分离后画面流畅、检测框略微滞后即可。
        """
        while not self._stop_infer.is_set():
            try:
                frame = self.io.latest_frame()
                dets = self.detector.infer(frame) if frame is not None else []
                with self._lock:
                    self.dets = dets
                    self.dets_ts = time.time()
            except Exception:  # noqa: BLE001
                logger.exception("推理循环异常")
            time.sleep(0.25)

    def latest_dets(self) -> list[Any]:
        with self._lock:
            return list(self.dets)

    # ------------------------------------------------------------------
    def start_job(self, kind: str, target: Any, *args: Any, **kwargs: Any) -> Job:
        """启动一个后台任务；已有任务在跑时拒绝（409 由调用方抛）。"""
        with self._lock:
            if self.job.running:
                raise RuntimeError(f"已有任务在运行：{self.job.kind}")
            self.job = Job(kind=kind, running=True, stage="starting", started_at=time.time())
            job_ref = self.job

        def _runner() -> None:
            try:
                target(job_ref, *args, **kwargs)
                job_ref.stage = "done"
            except Exception as exc:  # noqa: BLE001
                job_ref.error = str(exc)
                job_ref.stage = "error"
                logger.exception("后台任务 %s 失败", kind)
            finally:
                job_ref.running = False

        self._worker = threading.Thread(target=_runner, daemon=True)
        self._worker.start()
        return self.job


STATE: AppState | None = None


def _state() -> AppState:
    if STATE is None:
        raise HTTPException(status_code=503, detail="服务未初始化")
    return STATE


# ======================================================================
# 放置点（旁边的料槽）
# ======================================================================
def _current_pose(st: AppState) -> dict[int, int]:
    """把当前舵机位置读成一组 ``{舵机ID: 脉宽}``，用作示教放置位姿。

    优先取回读 ``position``（机械臂**实际**在哪），取不到才退回 ``goal``
    （我们刚下发的目标）—— 示教要记录的是"摆在哪里"，不是"命令它去哪"。
    """
    tele = st.io.servo_telemetry() or {}
    pose: dict[int, int] = {}
    for sid in (st.io.gripper_servo, st.io.wrist_servo, *st.io.ik_servos):
        row = tele.get(str(sid)) or {}
        value = row.get("position")
        if value is None:
            value = row.get("goal")
        if value is not None:
            pose[int(sid)] = int(value)
    return pose


def _persist_calibration(st: AppState) -> bool:
    """把标定文件落盘（放置点、水面高度都记在里面）。

    ★ 演示标定（mock）与未就绪的标定**不落盘** —— 与「保存标定」同一条纪律：
      不能让一个「看起来合法」的 calibration.json 被拷到真机上当真值用。
      此时只存在内存里（mock 联调够用），响应里 ``persisted=false``。
    """
    if st.cal_is_demo or not st.cal.ready:
        return False
    try:
        save_calibration(st.cal)
    except OSError:
        logger.exception("标定文件落盘失败")
        return False
    return True


# ======================================================================
# 后台任务体
# ======================================================================
def _job_capture(job: Job, frames: int, tag: str, augment: bool) -> None:
    st = _state()
    session = st.dataset.new_session(tag or "capture")
    st.capture_session = session
    job.detail["session"] = session
    job.detail["target_frames"] = frames
    # 采集姿态增广：机械臂在 3–4 个观测姿态间轮换，视角多样性比连拍有用
    poses = [(0.0, 0.17, 0.30), (-0.05, 0.15, 0.26), (0.05, 0.15, 0.26), (0.0, 0.13, 0.24)]
    saved = 0
    i = 0
    while saved < frames:
        if not job.running:
            break
        if augment and i % max(1, frames // len(poses)) == 0:
            px, py, pz = poses[(i // max(1, frames // len(poses))) % len(poses)]
            st.io.move_to(px, py, pz)
            time.sleep(0.8)
        frame = st.io.latest_frame()
        if frame is not None:
            import cv2

            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ok:
                st.dataset.add_frame(session, buf.tobytes())
                saved += 1
                job.detail["saved"] = saved
        i += 1
        time.sleep(0.12)
    job.log.append(f"采集完成：{saved} 帧 → {session}")
    job.result = {"session": session, "frames": saved}


def _job_calibrate(job: Job, grid: list[tuple[float, float]]) -> None:
    st = _state()

    def _on_step(idx: int, world: tuple[float, float], pixel: Any) -> None:
        job.detail["step"] = idx
        job.detail["world"] = [round(world[0], 4), round(world[1], 4)]
        job.detail["pixel"] = [round(pixel[0], 1), round(pixel[1], 1)] if pixel else None
        job.log.append(f"第 {idx}/{len(grid)} 点：" +
                       (f"像素 {pixel[0]:.0f},{pixel[1]:.0f}" if pixel else "未检测到目标，跳过"))

    cal = capture_at_observation(st.io, st.detector, grid,
                                marker_class=st.detector.target_class,
                                plane_z=st.cal.plane_z, on_step=_on_step)
    st.cal = cal
    st.loop.cal = cal
    path = save_calibration(cal)
    job.log.append(f"标定完成：{len(cal.pairs)} 点，RMSE={cal.rmse:.4f}m → {path}")
    job.result = {"points": len(cal.pairs), "rmse": cal.rmse, "path": str(path)}


def _job_grasp(job: Job, task_id: str) -> None:
    st = _state()

    def _on_phase(phase: str, info: dict[str, Any]) -> None:
        job.stage = phase
        job.detail.update(info)
        job.log.append(f"{phase} {info or ''}")

    # 用临时的 on_phase 复跑同一个 GraspLoop：一份实现、两处入口
    loop = GraspLoop(st.io, st.detector, st.cal, st.cfg, on_phase=_on_phase)
    outcome = loop.run(task_id=task_id)
    job.result = outcome.to_dict()
    if not outcome.ok:
        job.log.append(f"未成功：{outcome.message}")
    elif outcome.placed:
        job.log.append(f"抓取成功并放入料槽（第 {outcome.attempts} 次尝试）")
    else:
        job.log.append(f"抓取成功但未放入料槽：{outcome.message}")
    job.stage = "done" if outcome.ok else "error"
    if not outcome.ok:
        job.error = outcome.message


def _job_train(job: Job, tier: str, session: str = "") -> None:
    st = _state()

    def _on_progress(stage: str, info: dict[str, Any]) -> None:
        job.stage = stage
        job.detail.update({k: v for k, v in info.items() if k != "result"})
        if stage == "epoch":
            job.log.append(
                f"epoch {info.get('epoch')}/{info.get('total_epochs')} "
                f"loss={info.get('loss'):.4f} mAP50={info.get('map50'):.4f}"
            )
        elif stage in ("export", "done", "eval"):
            job.log.append(f"{stage}: {info}")

    stats = st.dataset.build(session=session or None)
    job.log.append(f"数据集组装：train={stats['train']} val={stats['val']} "
                   f"类别分布={stats['per_class']}"
                   f"（会话={session or '全部'}）")
    result = train(st.cfg, tier, dataset_yaml=stats["data_yaml"], progress_cb=_on_progress)
    job.result = result
    job.log.append(f"训练产物：{result.get('model_path')}")
    # ★ 必须重载检测器：免训练校准会把新阈值/ROI 写进 tuning.json，但 Detector 是
    #   长驻对象，不 load() 就仍在用旧值 —— 会出现「校准跑完了、界面也显示新数字、
    #   实际推理还是旧阈值」这种最难发现的假成功。其它档重载也无副作用（active
    #   模型没变，只是把 tuning 再叠加一次）。
    st.detector.load()
    job.log.append(f"已重载检测后端：conf={st.detector.conf_threshold} "
                   f"iou={st.detector.iou_threshold} roi={st.detector.roi}")


# ======================================================================
# 请求模型
# ======================================================================
class JogBody(BaseModel):
    servo_id: int = Field(ge=0, le=32)
    position: int = Field(ge=0, le=1000)
    duration_ms: int = Field(default=600, ge=50, le=10000)


class GripperBody(BaseModel):
    action: str


class PlaceBody(BaseModel):
    """放置点（臂座旁边的料槽）的三种用法 —— 三者互斥，按 clear > coord > pose 处理。

    * ``coord=[x, y]``：直接给工作平面坐标（m，标定坐标系）；
    * ``pose="here"``：把**当前舵机姿态**记为放置位姿（示教：先手动点动到位再点保存）；
    * ``clear=True``：清掉放置点（清掉后抓取闭环会拒绝开工）。
    """

    coord: list[float] | None = None
    pose: str | None = None
    clear: bool = False


class GraspBody(BaseModel):
    task_id: str = ""


class CaptureBody(BaseModel):
    frames: int = Field(default=200, ge=10, le=2000)
    tag: str = ""
    augment: bool = True


class LabelBody(BaseModel):
    session: str
    name: str
    boxes: list[dict[str, Any]] = Field(default_factory=list)


class TrainBody(BaseModel):
    tier: str = "local"
    #: 只用这个采集会话组装训练集；空 = 全部会话。
    #  ★ 场景特化时必须指定：否则会把历史会话（比如早期那批合成演示帧）一起
    #    拉进来稀释，训练/扫出来的阈值就不是当前场景的了。
    session: str = ""


class DeployBody(BaseModel):
    note: str = ""
    min_map50: float = Field(default=0.5, ge=0.0, le=1.0)


class RollbackBody(BaseModel):
    version: str = ""


class CalibrateBody(BaseModel):
    grid_size: int = Field(default=3, ge=2, le=5)
    span: float = Field(default=0.10, gt=0.0, le=0.4)


class PlaneZBody(BaseModel):
    """水面/台面高度（绝对 z，m；原点 = 臂座安装面）。

    标定只解出像素↔(x, y)，**z 是独立的一件事**：船上甲板高于水面，水面 z 是
    负值（甲板高出水面 8cm → -0.08）。填错这一步，爪子要么压不到袋子、要么撞下去。
    """

    plane_z: float = Field(ge=-0.5, le=0.5)


class TuningBody(BaseModel):
    """场景微调调参（写 models/active/tuning.json；缺省字段保持原值）。"""

    conf_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    iou_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    #: 归一化 ROI ``[x, y, w, h]``；只保留中心落在其中的检出
    roi: list[float] | None = None
    clear_roi: bool = False


# ======================================================================
# 画面叠加
# ======================================================================
def _no_signal_frame(w: int = 640, h: int = 480) -> Any:
    """无相机信号时的占位帧。

    ★ 为什么必须有：``/stream`` 是 multipart 流，若一个字节都不产出，
      ``<img src="/stream">`` 会**永远处于加载中** —— 浏览器的 load 事件
      因此永不触发，整个页面卡在 loading（现场 ROS 没起来时就是这样）。
      先送一帧占位，既解除挂起，又给现场一句明确的排障提示。
      文字用固定浅色画在深色底上（不随主题反转）。
    """
    import cv2
    import numpy as np

    img = np.full((h, w, 3), 28, dtype=np.uint8)
    for x in range(-h, w, 44):
        cv2.line(img, (x, 0), (x + h, h), (44, 44, 44), 2)
    cv2.putText(img, "NO CAMERA SIGNAL", (96, h // 2 - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (240, 240, 240), 2, cv2.LINE_AA)
    cv2.putText(img, "check ROS / usb_cam on the Pi", (128, h // 2 + 34),
                cv2.FONT_HERSHEY_SIMPLEX, 0.62, (150, 190, 210), 1, cv2.LINE_AA)
    return img


def _draw(frame: Any, dets: list[Any], target_class: str) -> Any:
    """在画面上画检测框：目标类高亮、其他类（浮标）灰色忽略框。"""
    import cv2

    for det in dets:
        is_target = det.cls == target_class
        color = (0, 200, 120) if is_target else (150, 150, 150)
        x1, y1, x2, y2 = (int(det.x1), int(det.y1), int(det.x2), int(det.y2))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        # ★ 叠加文字一律用 ASCII：cv2 的 Hershey 字体不带中文字形，写中文只会
        #   渲染成一串方块（实测「忽略」→「????」）。类别名本身即英文，故写 ignored。
        tag = f"{det.cls} {det.conf:.2f}" + ("" if is_target else " ignored")
        # 固定浅色文字 + 深色底衬：画面是深色水面，用固定色保证可读
        cv2.putText(frame, tag, (x1 + 2, max(14, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        if is_target:
            gu, gv = det.grasp_point
            cv2.drawMarker(frame, (int(gu), int(gv)), color, cv2.MARKER_CROSS, 16, 2)
    return frame


# ======================================================================
# 应用
# ======================================================================
def create_app(cfg: dict[str, Any], mock: bool) -> FastAPI:
    global STATE
    STATE = AppState(cfg, mock)
    app_state = STATE

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> Any:
        # 新版 FastAPI 已移除 add_event_handler，改用 lifespan 托管启停。
        # 行为与旧写法一致：启动起相机/推理/MQTT，退出时逐项收尸。
        app_state.start()
        try:
            yield
        finally:
            app_state.stop()

    app = FastAPI(title="Oceanus 机械臂训练作业台", version="0.1.0", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def index() -> Any:
        page = HERE / "static" / "index.html"
        if not page.exists():
            raise HTTPException(status_code=500, detail="index.html 缺失")
        return HTMLResponse(page.read_text(encoding="utf-8"))

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        st = _state()
        target = st.detector.target_class

        async def gen() -> Any:
            import cv2

            placeholder_sent = False
            while True:
                frame = st.io.latest_frame()
                if frame is None:
                    # 无相机：先送一帧占位解除 <img> 的加载挂起，之后每 0.3s 重试
                    if not placeholder_sent:
                        ok, buf = cv2.imencode(
                            ".jpg", _no_signal_frame(),
                            [int(cv2.IMWRITE_JPEG_QUALITY), 72],
                        )
                        if ok:
                            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                                   + buf.tobytes() + b"\r\n")
                            placeholder_sent = True
                    await asyncio.sleep(0.3)
                    continue
                placeholder_sent = False
                frame = _draw(frame, st.latest_dets(), target)
                ok, buf = cv2.imencode(".jpg", frame,
                                       [int(cv2.IMWRITE_JPEG_QUALITY), 72])
                if ok:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                           + buf.tobytes() + b"\r\n")
                await asyncio.sleep(0.06)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    # ---------------- 状态 ----------------
    @app.get("/api/status")
    def status() -> dict[str, Any]:
        st = _state()
        return {
            "mock": st.mock,
            # ROS 未通时非空：页面据此显示排障提示（服务本身照常可用）
            "ros_error": st.io.ros_error,
            "detector": st.detector.info(),
            "calibration": {
                "ready": bool(st.cal.ready),
                "demo": bool(st.cal_is_demo),
                "points": len(st.cal.pairs),
                "rmse": st.cal.rmse,
                "plane_z": st.cal.plane_z,
            },
            # 放置点（料槽）：抓取闭环的硬前置，"放哪儿"要和"抓哪儿"一样可见
            "place": st.loop.place_info(),
            "servos": st.io.servo_telemetry(),
            "detections": [d.to_dict() for d in st.latest_dets()],
            "dets_age": round(time.time() - st.dets_ts, 2) if st.dets_ts else None,
            "phase": st.loop.phase,
            "job": st.job.to_dict(),
            "task": st.listener.context,
            "tiers": sorted(TIERS),
            "training_available": training_available(),
            "frames": len(st.dataset.list_frames()),
            "labeled": len(st.dataset.labeled_frames()),
            "current_model": st.store.current(),
        }

    @app.get("/api/task")
    def task_context() -> dict[str, Any]:
        return _state().listener.context

    @app.get("/api/telemetry")
    def telemetry() -> dict[str, Any]:
        return _state().io.servo_telemetry()

    # ---------------- 手动点动 ----------------
    @app.post("/api/jog")
    def jog(body: JogBody) -> dict[str, Any]:
        st = _state()
        try:
            st.io.set_servo(body.servo_id, body.position, body.duration_ms)
        except ArmIoError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"ok": True, "servo_id": body.servo_id, "position": body.position}

    @app.post("/api/home")
    def home() -> dict[str, Any]:
        st = _state()
        try:
            ok = st.io.home()
        except ArmIoError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"ok": bool(ok)}

    @app.post("/api/gripper")
    def gripper(body: GripperBody) -> dict[str, Any]:
        st = _state()
        try:
            if body.action == "open":
                st.io.gripper_open()
                return {"ok": True, "action": "open"}
            if body.action == "close":
                pulse = st.io.gripper_close_adaptive()
                return {"ok": True, "action": "close", "pulse": pulse}
        except ArmIoError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail="action 必须是 open / close")

    # ---------------- 放置点（旁边的料槽） ----------------
    @app.post("/api/place")
    def place_set(body: PlaceBody) -> dict[str, Any]:
        """示教 / 手填 / 清除料槽放置点。写进 calibration.json（与设备绑定）。"""
        st = _state()
        if body.clear:
            st.cal.place = None
            saved = _persist_calibration(st)
            return {"ok": True, "place": describe_place(None), "persisted": saved}

        if body.coord is not None:
            if len(body.coord) < 2:
                raise HTTPException(status_code=400, detail="coord 需要 [x, y] 两个数（m）")
            place = {"coord": [float(body.coord[0]), float(body.coord[1])],
                     "source": "console"}
        elif body.pose == "here":
            pose = _current_pose(st)
            if not pose:
                raise HTTPException(
                    status_code=400,
                    detail="读不到舵机位置，无法记录当前姿态：确认真机 ROS 已接入"
                           "（mock 模式下读到的是最近一次下发值）",
                )
            place = {"pose": pose, "source": "taught"}
        else:
            raise HTTPException(status_code=400, detail="需要 coord / pose='here' / clear 之一")

        place["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        st.cal.place = place
        saved = _persist_calibration(st)
        return {"ok": True, "place": describe_place(place), "persisted": saved}

    # ---------------- 抓取作业 ----------------
    @app.post("/api/grasp/start")
    def grasp_start(body: GraspBody) -> dict[str, Any]:
        st = _state()
        # 没有放置点就别开工：夹起来了没地方放，比不抓更糟（同闭环内的前置判断）
        if not st.loop.place_info()["ready"]:
            raise HTTPException(
                status_code=400,
                detail="未配置料槽放置点：先在「放置点（料槽）」示教一次"
                       "（手动点动到槽口上方 → 「用当前姿态作放置点」），"
                       "或填 config.yaml 的 agent.place.coord",
            )
        try:
            st.start_job("grasp", _job_grasp, body.task_id or st.listener.context.get("task_id", ""))
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "job": st.job.to_dict()}

    @app.post("/api/grasp/stop")
    def grasp_stop() -> dict[str, Any]:
        st = _state()
        st.loop.request_stop()
        return {"ok": True}

    # ---------------- 采集 ----------------
    @app.post("/api/capture/start")
    def capture_start(body: CaptureBody) -> dict[str, Any]:
        st = _state()
        try:
            st.start_job("capture", _job_capture, body.frames, body.tag, body.augment)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "job": st.job.to_dict()}

    @app.get("/api/frames")
    def frames(session: str = "") -> dict[str, Any]:
        st = _state()
        items: list[dict[str, Any]] = []
        for frame in st.dataset.list_frames(session or None):
            rel = frame.relative_to(st.dataset.raw_dir)
            parts = rel.parts
            sess = parts[0] if len(parts) > 1 else session
            boxes = st.dataset.read_label(frame)
            items.append({
                "session": sess,
                "name": frame.name,
                "url": f"/api/frames/{sess}/{frame.name}",
                "labels": [{"cls": b.cls, "cx": b.cx, "cy": b.cy, "w": b.w, "h": b.h}
                           for b in boxes],
            })
        return {"count": len(items), "frames": items[-60:]}

    @app.get("/api/frames/{session}/{name}")
    def frame_image(session: str, name: str) -> Any:
        st = _state()
        path = (st.dataset.raw_dir / session / name).resolve()
        if not str(path).startswith(str(st.dataset.raw_dir.resolve())) or not path.exists():
            raise HTTPException(status_code=404, detail="帧不存在")
        return FileResponse(path, media_type="image/jpeg")

    @app.post("/api/frames/prelabel")
    def prelabel(body: LabelBody) -> dict[str, Any]:
        """用当前模型给一帧预标注，交给页面画框修正。"""
        st = _state()
        frame_path = st.dataset.raw_dir / body.session / body.name
        if not frame_path.exists():
            raise HTTPException(status_code=404, detail="帧不存在")
        import cv2

        img = cv2.imread(str(frame_path))
        if img is None:
            raise HTTPException(status_code=400, detail="帧不可读")
        h, w = img.shape[:2]
        boxes: list[dict[str, Any]] = []
        for det in st.detector.infer(img):
            boxes.append({
                "cls": det.cls,
                "cx": ((det.x1 + det.x2) / 2) / w,
                "cy": ((det.y1 + det.y2) / 2) / h,
                "w": (det.x2 - det.x1) / w,
                "h": (det.y2 - det.y1) / h,
                "conf": round(det.conf, 3),
            })
        return {"boxes": boxes, "width": w, "height": h}

    @app.post("/api/label")
    def save_label(body: LabelBody) -> dict[str, Any]:
        st = _state()
        frame_path = st.dataset.raw_dir / body.session / body.name
        if not frame_path.exists():
            raise HTTPException(status_code=404, detail="帧不存在")
        try:
            boxes = [Box(str(b["cls"]), float(b["cx"]), float(b["cy"]),
                         float(b["w"]), float(b["h"]),
                         float(b.get("conf", 1.0))) for b in body.boxes]
            path = st.dataset.write_label(frame_path, boxes)
        except (DatasetError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"标注非法：{exc}") from exc
        return {"ok": True, "path": str(path), "count": len(boxes)}

    # ---------------- 标定 ----------------
    @app.post("/api/calibrate/start")
    def calibrate_start(body: CalibrateBody) -> dict[str, Any]:
        st = _state()
        half = body.span
        n = body.grid_size
        grid: list[tuple[float, float]] = []
        for iy in range(n):
            for ix in range(n):
                grid.append((
                    -half + 2 * half * (ix / max(1, n - 1)),
                    -half + 2 * half * (iy / max(1, n - 1)),
                ))
        try:
            st.start_job("calibrate", _job_calibrate, grid)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "grid": grid, "job": st.job.to_dict()}

    @app.post("/api/calibrate/save")
    def calibrate_save() -> dict[str, Any]:
        st = _state()
        if not st.cal.ready:
            raise HTTPException(status_code=400, detail="标定未就绪，无法保存")
        # ★ mock 模式下的 st.cal 是演示映射（demo_calibration），ready 只是为了
        #   让离线联调不被前置检查挡住。把它落盘会留下一个「看起来合法」的
        #   calibration.json（RMSE 正好 0、3 个假点对），而真机侧 precheck /
        #   supervisor 只看 ready，就会当成真标定用 —— 这正是"假装成功"。
        if st.cal_is_demo:
            raise HTTPException(
                status_code=409,
                detail="当前是 mock 演示标定（非真机标定），拒绝落盘："
                       "请上真机、跑完 9 点标定后再保存",
            )
        path = save_calibration(st.cal)
        return {"ok": True, "path": str(path)}

    @app.post("/api/calibrate/plane_z")
    def calibrate_plane_z(body: PlaneZBody) -> dict[str, Any]:
        """设置水面/台面高度（z）。标定只管 (x, y)，z 是独立的一件事。

        船上甲板高于水面，这个值是**负数**；不填准，爪子要么压不到袋子、
        要么直接撞下去。写入 calibration.json（演示标定不落盘，同其它接口）。
        """
        st = _state()
        st.cal.plane_z = float(body.plane_z)
        st.loop.cal.plane_z = float(body.plane_z)
        persisted = _persist_calibration(st)
        return {"ok": True, "plane_z": st.cal.plane_z, "persisted": persisted}

    # ---------------- 场景微调（tuning.json） ----------------
    @app.get("/api/tuning")
    def get_tuning() -> dict[str, Any]:
        st = _state()
        det = st.detector
        path = det.model_dir / "tuning.json"
        raw: dict[str, Any] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
        return {
            "path": str(path),
            "exists": path.exists(),
            # 这三个是「当前生效值」（可能来自 tuning.json，也可能来自 config.yaml）
            "conf_threshold": det.conf_threshold,
            "iou_threshold": det.iou_threshold,
            "roi": list(det.roi) if det.roi else None,
            "sweep": raw.get("sweep"),
            "chosen_by": raw.get("chosen_by"),
        }

    @app.post("/api/tuning")
    def set_tuning(body: TuningBody) -> dict[str, Any]:
        """手动写 tuning.json 并立刻生效（固定演示场景的 ROI / 阈值微调）。"""
        st = _state()
        det = st.detector
        path = det.model_dir / "tuning.json"
        raw: dict[str, Any] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
        if body.conf_threshold is not None:
            raw["conf_threshold"] = float(body.conf_threshold)
        if body.iou_threshold is not None:
            raw["iou_threshold"] = float(body.iou_threshold)
        if body.clear_roi:
            raw.pop("roi", None)
        elif body.roi is not None:
            roi = [float(x) for x in body.roi]
            if len(roi) != 4:
                raise HTTPException(
                    status_code=400, detail="roi 必须是 4 个数：x y w h（归一化 0~1）")
            if not all(0.0 <= v <= 1.0 for v in roi):
                raise HTTPException(status_code=400, detail="roi 的每个值都要落在 0~1")
            raw["roi"] = roi
        raw["chosen_by"] = "manual_console"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        det.load()          # 立刻生效：load() 会重读 tuning.json
        return {"ok": True, "path": str(path),
                "conf_threshold": det.conf_threshold,
                "iou_threshold": det.iou_threshold,
                "roi": list(det.roi) if det.roi else None}

    # ---------------- 训练与部署 ----------------
    @app.post("/api/train")
    def train_start(body: TrainBody) -> dict[str, Any]:
        st = _state()
        if body.tier not in TIERS:
            raise HTTPException(status_code=400, detail=f"未知档位，可选 {sorted(TIERS)}")
        if not training_available() and body.tier != "calibrate":
            raise HTTPException(
                status_code=503,
                detail="训练档需要 ultralytics；请改选 calibrate 档或用局域网协同档",
            )
        try:
            st.start_job("train", _job_train, body.tier, body.session)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, "tier": body.tier, "session": body.session, "job": st.job.to_dict()}

    @app.get("/api/train/status")
    def train_status() -> dict[str, Any]:
        return _state().job.to_dict()

    @app.post("/api/evaluate")
    def do_evaluate() -> dict[str, Any]:
        st = _state()
        try:
            metrics = evaluate(st.cfg)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        ok, reason = passes(metrics, 0.5)
        return {"ok": ok, "reason": reason, "metrics": metrics}

    @app.post("/api/deploy")
    def do_deploy(body: DeployBody) -> dict[str, Any]:
        st = _state()
        model_dir = st.detector.model_dir
        candidates = [model_dir / n for n in ("best.onnx", "best.ncnn.param", "best.pt")]
        model_path = next((p for p in candidates if p.exists()), None)
        if model_path is None:
            raise HTTPException(
                status_code=409,
                detail="active 目录没有可部署的模型。请先训练（产物在 runs/ 下，"
                       "用 /api/deploy-from 指定路径，或把模型拷进 active 后重试）",
            )
        # 部署门禁：先用 active 里的模型算指标
        metrics: dict[str, Any] = {}
        try:
            metrics = evaluate(st.cfg, model_path=model_path)
            ok, reason = passes(metrics, body.min_map50)
        except Exception as exc:  # noqa: BLE001
            logger.warning("部署前评估失败，跳过门禁：%s", exc)
            ok, reason = True, f"评估不可用（{exc}），跳过门禁"
        if not ok:
            raise HTTPException(status_code=409, detail=f"未通过部署门禁：{reason}")
        try:
            meta = st.store.deploy(model_path, metrics=metrics, note=body.note)
        except DeployError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        st.detector.load()
        return {"ok": True, "gate": reason, "version": meta}

    @app.post("/api/deploy-from")
    def deploy_from(body: dict[str, Any]) -> dict[str, Any]:
        """把训练产物（runs/.../best.onnx）登记为新版本并切换 active。"""
        st = _state()
        path = str(body.get("model_path", "")).strip()
        if not path:
            raise HTTPException(status_code=400, detail="缺少 model_path")
        src = Path(path)
        if not src.exists():
            raise HTTPException(status_code=404, detail=f"模型不存在: {src}")
        metrics: dict[str, Any] = {}
        min_map50 = float(body.get("min_map50", 0.5))
        try:
            metrics = evaluate(st.cfg, model_path=src)
            ok, reason = passes(metrics, min_map50)
        except Exception as exc:  # noqa: BLE001
            ok, reason = True, f"评估不可用（{exc}），跳过门禁"
        if not ok:
            raise HTTPException(status_code=409, detail=f"未通过部署门禁：{reason}")
        try:
            meta = st.store.deploy(src, metrics=metrics, note=str(body.get("note", "")))
        except DeployError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        st.detector.load()
        return {"ok": True, "gate": reason, "version": meta}

    @app.get("/api/versions")
    def versions() -> dict[str, Any]:
        st = _state()
        return {"current": st.store.current(), "versions": st.store.versions()}

    @app.post("/api/rollback")
    def rollback(body: RollbackBody) -> dict[str, Any]:
        st = _state()
        try:
            meta = st.store.activate(body.version) if body.version else st.store.rollback()
        except DeployError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        st.detector.load()
        return {"ok": True, "version": meta}

    return app


# ======================================================================
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Oceanus 机械臂训练作业台")
    ap.add_argument("--config", default=None, help="配置文件路径（默认 edge/grasp/config.yaml）")
    ap.add_argument("--mock", action="store_true", help="不接 ROS，用合成画面跑通 UI")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config(args.config)
    mock = args.mock or bool((cfg.get("web") or {}).get("mock"))
    host = args.host or str((cfg.get("web") or {}).get("host", "0.0.0.0"))
    port = args.port or int((cfg.get("web") or {}).get("port", 8090))

    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("需要 fastapi + uvicorn：pip install -r edge/grasp/requirements.txt") from exc

    app = create_app(cfg, mock)
    logger.info("作业台启动：http://%s:%s （mock=%s）", host, port, mock)
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
