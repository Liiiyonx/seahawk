"""全自动抓取闭环（六态状态机）。

## 与厂商 demo 的本质区别

厂商的 ``face_detect`` / ``warehouse`` 是「预设初始位姿 + 固定关节序列回放」：
每个脉宽都是录制值。本模块里**每一个动作都由感知输出经 IK 现算**：

    YOLO 检出 → 像素↔世界坐标换算 → ArmIK 解算 → 总线舵机下发

没有一段录制序列，换目标位置、换袋子大小都照样工作。

## 六态

    ① 持续检测 → ② 目标锁定（滤浮标）→ ③ 视觉伺服逼近
      → ④ 精准夹取 → ⑤ 抓取验证 → ⑥ 放置入槽 →（循环回 ①）

⑥ 的落点是**臂座旁边的料槽**（side_hopper，见 ``agent.place``）：抓取点每帧
由视觉现算，放置点是固定工位，示教/配置一次即可（``coord`` 走 IK，``pose``
回放示教位姿）。**没有放置点就直接报错**，不会把袋子丢在原地假装完成。

失败任一步就回 ① 重试，超过 ``max_retry`` 则上报异常。

## 抗浮标三层防线在代码里的落点

* 训练层 —— 浮标作 ``buoy`` 显式负类（在 ``vision/dataset`` + 训练侧）
* 推理层 —— 仅 ``plastic_bag`` 且过阈值才成候选（``Detector.targets``）
* 决策层 —— 本模块 ``_lock_target()`` 里的 HSV 饱和度辅助校验 + 轨迹邻域锁定

本模块被两个入口复用（一份实现、两处调用）：

* ``vision_driver.OceanusVisionArmDriver``（桥接进程，随平台派单执行）
* ``web/server.py``（作业台进程，页面「开始作业」按钮）
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .calibration import describe_place

logger = logging.getLogger("oceanus.grasp.loop")

#: 状态机相位名（页面与日志共用同一套词，避免两处漂移）
PHASES = ("idle", "detecting", "locking", "servoing", "grasping",
          "verifying", "placing", "done", "error")

PhaseCb = Callable[[str, dict[str, Any]], None]


@dataclass
class GraspOutcome:
    """一次抓取的结果。"""

    ok: bool
    phase: str
    attempts: int = 0
    detected: int = 0
    grip_pulse: int | None = None
    target_gone: bool = False
    grip_stalled: bool = False
    #: 是否真的放进了料槽。★ 与 ``ok`` 分开：夹住了但放置点不可达时
    #: ``ok=True / placed=False`` —— 这两种结果的处置方式完全不同
    #: （前者可以继续下一单，后者要人工去把臂上的袋子取下来）。
    placed: bool = False
    message: str = ""
    log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "phase": self.phase,
            "attempts": self.attempts,
            "detected": self.detected,
            "grip_pulse": self.grip_pulse,
            "target_gone": self.target_gone,
            "grip_stalled": self.grip_stalled,
            "placed": self.placed,
            "message": self.message,
        }


class GraspLoopError(RuntimeError):
    """闭环前置条件不满足（无标定 / 无模型）。"""


class GraspLoop:
    """视觉闭环抓取（无预设动作）。"""

    def __init__(
        self,
        io: Any,
        detector: Any,
        calibration: Any,
        cfg: dict[str, Any],
        *,
        on_phase: PhaseCb | None = None,
    ) -> None:
        agent = cfg.get("agent", {}) or {}
        arm = cfg.get("arm", {}) or {}
        self.io = io
        self.detector = detector
        self.cal = calibration
        self.on_phase = on_phase

        self.frame_period_s = float(agent.get("frame_period_ms", 250)) / 1000.0
        self.max_retry = int(agent.get("max_retry", 3))
        self.depth_offset = float(agent.get("grasp_depth_offset", 0.005))
        self.work_radius = float(agent.get("work_radius", 0.20))
        self.approach_height = float(agent.get("approach_height", 0.08))
        self.lock_min_hits = int(agent.get("lock_min_hits", 3))
        self.grip_stall_threshold = int(agent.get("grip_stall_threshold", 8))

        # ---------- 抓取姿态 ----------
        # ★ 俯仰角口径按厂商源码核对：ROS 版 IK（armpi_fpv_kinematics）里
        #   「夹持器与水平面夹角」取值区间是 [-180, 0]，桌面/水面抓取用
        #   **-175**（warehouse/in.py、object_sorting/sorting.py 的
        #   grasps.grasp_pos.rotation.r）。原先沿用待命位 -65°，在真机上
        #   爪子是斜的、不是朝下压住目标。
        self.grasp_pitch = float(agent.get("grasp_pitch", -175))
        home = arm.get("home") or {}
        pr = home.get("pitch_range") or [-180, 0]
        self.pitch_range = (float(pr[0]), float(pr[1]))

        # ---------- 放置点（旁边的料槽）----------
        # 几何口径同样取自厂商：warehouse/in.py 的货架位 x=±0.275、y=0、
        # 底层 z=0.02、底层俯仰角 -130（R1/L1）。臂座两侧的料槽就是同一类
        # 「侧向固定工位」，所以默认值直接沿用这一组。
        place = agent.get("place") or {}
        #: 槽口上方接近高度（**绝对 z**）——不能用"水面 + 偏移"：水面在甲板
        #: 以下时那个算法会把臂送到槽口下面去。
        self.place_approach_z = float(place.get("approach_z", 0.12))
        #: 槽内落料高度（**绝对 z**，m）。0.02 与厂商货架底层同口径。
        self.place_drop_z = float(place.get("drop_z", 0.02))
        self.place_retreat_z = float(place.get("retreat_z", 0.20))
        self.place_pitch = float(place.get("pitch", -130))
        self.place_settle_s = float(place.get("settle_s", 0.5))
        self.place_move_ms = int(place.get("coord_move_ms", 900))
        self.place_drop_ms = int(place.get("drop_move_ms", 700))
        #: 配置文件里的兜底放置点（示教值存在 calibration.json 时会盖过它）
        self.config_place: dict[str, Any] | None = None
        if isinstance(place.get("coord"), (list, tuple)) and len(place.get("coord")) >= 2:
            self.config_place = {"coord": [float(place["coord"][0]), float(place["coord"][1])],
                                 "source": "config"}
        elif isinstance(place.get("pose"), dict) and place.get("pose"):
            self.config_place = {"pose": {int(k): int(v) for k, v in place["pose"].items()},
                                 "source": "config"}

        # ★ 夹爪脉宽口径按厂商源码核对：**越大越闭**（in.py 夹住 450 / 松开 75）
        self.gripper_open_pulse = int(arm.get("gripper_open", 200))
        self.gripper_close_pulse = int(arm.get("gripper_close", 450))

        self._phase = "idle"
        self._stop = False
        self._detect_rounds = max(8, int(6.0 / max(self.frame_period_s, 0.05)))
        self._servo_iters = 6
        self._converge_px = 12.0          # 像素收敛阈值
        self._converge_m = 0.006          # 世界坐标收敛阈值（m）

        # mock 模式下没有真机标定 —— 造一个演示映射，让整条闭环可离线跑通
        if getattr(io, "mock", False) and not getattr(calibration, "ready", False):
            self._install_demo_calibration()

    # ------------------------------------------------------------------
    def request_stop(self) -> None:
        self._stop = True

    @property
    def phase(self) -> str:
        return self._phase

    def _set_phase(self, phase: str, **info: Any) -> None:
        self._phase = phase
        if self.on_phase is not None:
            try:
                self.on_phase(phase, info)
            except Exception:  # noqa: BLE001
                logger.exception("on_phase 回调异常")

    def _install_demo_calibration(self) -> None:
        """mock 专用：装载演示标定映射，让闭环可离线跑通。"""
        from .calibration import demo_calibration

        self.cal = demo_calibration(plane_z=self.depth_offset)
        logger.info("mock 模式：已装载演示标定映射（非真标定）")

    # ------------------------------------------------------------------
    # 放置点（旁边的料槽）
    # ------------------------------------------------------------------
    def _resolve_place(self) -> dict[str, Any]:
        """取当前生效的放置点：示教值（calibration.json）> config 兜底 > 无。

        示教值优先的原因：它是操作员在**这台机器**上摆出来的；config 里的
        坐标是纸面推算，换一台机器/重标定就未必还对。
        """
        desc = describe_place(getattr(self.cal, "place", None))
        if desc["ready"]:
            return desc
        if self.config_place:
            return describe_place(self.config_place)
        return {"kind": "none", "target": None, "ready": False,
                "source": "none", "saved_at": None}

    def place_info(self) -> dict[str, Any]:
        """放置点的只读描述（状态接口与自检共用）。"""
        return self._resolve_place()

    # ------------------------------------------------------------------
    def run(self, task_id: str = "", max_retry: int | None = None) -> GraspOutcome:
        """跑完整闭环，直到抓成功或重试超限。"""
        self._stop = False
        limit = int(max_retry or self.max_retry)
        log: list[dict[str, Any]] = []

        if not getattr(self.cal, "ready", False):
            self._set_phase("error", message="未标定")
            return GraspOutcome(ok=False, phase="error",
                                message="未完成 9 点标定，无法换算抓取坐标")
        if not getattr(self.detector, "info", lambda: {})().get("ready", False):
            self._set_phase("error", message="未部署模型")
            return GraspOutcome(ok=False, phase="error",
                                message="active 目录无可用模型（best.onnx/.pt），请先训练并部署")
        if not self._resolve_place()["ready"]:
            # 没有放置点就不开工：夹起来了却没地方放，比不抓更糟
            self._set_phase("error", message="未配置料槽放置点")
            return GraspOutcome(
                ok=False, phase="error",
                message="未配置料槽放置点：请在作业台「放置点（料槽）」示教一次，"
                        "或填 config.yaml 的 agent.place.coord / agent.place.pose",
            )

        for attempt in range(1, limit + 1):
            if self._stop:
                break
            entry: dict[str, Any] = {"attempt": attempt}

            lock = self._detect_and_lock(task_id, log)
            if lock is None:
                entry["result"] = "no_target"
                log.append(entry)
                continue
            entry["lock"] = lock.to_dict()

            if not self._servo_approach(lock, log):
                entry["result"] = "servo_failed"
                log.append(entry)
                continue

            grip_pulse = self._grasp(lock, log)
            target_gone, grip_stalled = self._verify(lock, grip_pulse, log)
            entry.update({"grip_pulse": grip_pulse, "target_gone": target_gone,
                          "grip_stalled": grip_stalled})

            if not (target_gone and grip_stalled):
                # 双证据不齐 → 视为不确定，回检测重试（并放下已夹物，避免叠压）
                self.io.gripper_open()
                entry["result"] = "verify_failed"
                log.append(entry)
                continue

            placed = self._place(log)
            entry["result"] = "ok" if placed else "placed_failed"
            entry["placed"] = placed
            log.append(entry)
            self._set_phase("done", attempt=attempt, placed=placed)
            message = (f"抓取成功并放入料槽（第 {attempt} 次尝试）" if placed
                       else f"抓取成功但未放入料槽（第 {attempt} 次尝试）")
            return GraspOutcome(ok=True, phase="done", attempts=attempt,
                                detected=len(log), grip_pulse=grip_pulse,
                                target_gone=True, grip_stalled=True, placed=placed,
                                message=message, log=log)

        message = "已停止" if self._stop else f"重试 {limit} 次仍未成功"
        self._set_phase("error", message=message)
        return GraspOutcome(ok=False, phase="error", attempts=limit,
                            detected=len(log), message=message, log=log)

    # ------------------------------------------------------------------
    # ①② 检测与锁定
    # ------------------------------------------------------------------
    def _detect_and_lock(self, task_id: str, log: list[dict[str, Any]]) -> Any:
        self._set_phase("detecting", task_id=task_id)
        hits: dict[int, int] = {}
        best: Any = None
        for _ in range(self._detect_rounds):
            if self._stop:
                return None
            frame = self.io.latest_frame()
            cands = self._candidates(frame)
            if cands:
                self._set_phase("locking", count=len(cands))
                top = max(cands, key=lambda d: d.width * d.height)
                key = self._track_key(top)
                hits[key] = hits.get(key, 0) + 1
                if hits[key] >= self.lock_min_hits:
                    best = top
                    break
            time.sleep(self.frame_period_s)
        return best

    def _candidates(self, frame: Any) -> list[Any]:
        """决策层过滤：目标类候选 + HSV 辅助校验。

        HSV 只作**辅证**，不作主判据 —— 水面反光会破坏颜色稳定性，
        主判据始终是模型类别与置信度。这里只剔除「模型说是袋、但颜色
        几乎不可能是袋」的离群点（例如高饱和的彩色浮标被误判成袋）。
        """
        if frame is None:
            return []
        targets = self.detector.targets(frame)
        kept: list[Any] = []
        for det in targets:
            if self._color_plausible(frame, det):
                kept.append(det)
        return kept

    def _color_plausible(self, frame: Any, det: Any) -> bool:
        try:
            import cv2
            import numpy as np
        except ImportError:
            return True
        u, v = det.center
        x1, y1 = int(max(0, det.x1)), int(max(0, det.y1))
        x2, y2 = int(min(frame.shape[1], det.x2)), int(min(frame.shape[0], det.y2))
        if x2 <= x1 or y2 <= y1:
            return True
        patch = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        sat = float(np.mean(hsv[:, :, 1]))
        # 塑料袋低饱和（白/半透明），浮标高饱和。阈值放宽到 120，
        # 只当"明显不可能"时才否决，避免误杀脏污的袋子。
        return sat <= 120.0

    @staticmethod
    def _track_key(det: Any) -> int:
        """粗糙的轨迹键：按检测框中心量化到 40px 网格。

        目的是去抖 —— 同一位置连续命中若干帧才算锁定，避免单帧误检
        就触发抓取。真正复杂的 SORT 跟踪不必要：场景里只有少数目标。
        """
        u, v = det.center
        return int(u // 40) * 1000 + int(v // 40)

    # ------------------------------------------------------------------
    # ③ 视觉伺服逼近
    # ------------------------------------------------------------------
    def _servo_approach(self, lock: Any, log: list[dict[str, Any]]) -> bool:
        self._set_phase("servoing")
        try:
            wx, wy, _ = self.cal.pixel_to_world(*lock.grasp_point)
        except Exception as exc:  # noqa: BLE001
            logger.warning("坐标换算失败: %s", exc)
            return False

        if self._radius(wx, wy) > self.work_radius:
            logger.info("目标超出工作半径 %.3f > %.3f，跳过", self._radius(wx, wy), self.work_radius)
            return False

        # 先抬到接近高度，避免横向扫过时撞到水面/目标
        if not self.io.move_to(wx, wy, self.cal.plane_z + self.approach_height,
                               pitch=self.grasp_pitch, pitch_range=self.pitch_range):
            return False
        time.sleep(max(0.4, self.frame_period_s * 2))

        prev_px: tuple[float, float] | None = None
        prev_world: tuple[float, float] | None = None
        for _ in range(self._servo_iters):
            if self._stop:
                return False
            frame = self.io.latest_frame()
            det = self._nearest_target(frame, lock)
            if det is None:
                return False          # 跟丢，回检测
            px = det.grasp_point
            wx, wy, _ = self.cal.pixel_to_world(*px)
            if self._radius(wx, wy) > self.work_radius:
                return False
            # 往前走一小步（保留接近高度），再重检测 —— 边走边修正
            if not self.io.move_to(wx, wy, self.cal.plane_z + self.approach_height,
                                   pitch=self.grasp_pitch, pitch_range=self.pitch_range):
                return False
            time.sleep(self.frame_period_s)
            if prev_px is not None and prev_world is not None:
                dpx = abs(px[0] - prev_px[0]) + abs(px[1] - prev_px[1])
                dw = abs(wx - prev_world[0]) + abs(wy - prev_world[1])
                if dpx <= self._converge_px and dw <= self._converge_m:
                    log.append({"servo_converged": True, "residual_px": round(dpx, 1)})
                    return True
            prev_px, prev_world = px, (wx, wy)
        # 迭代到上限仍未收敛：用最后一次的位置继续（闭环会再验证）
        log.append({"servo_converged": False, "iters": self._servo_iters})
        return True

    def _nearest_target(self, frame: Any, lock: Any) -> Any:
        """在当前帧里找离锁定位置最近的目标（邻近跟踪）。"""
        if frame is None:
            return None
        cands = self._candidates(frame)
        if not cands:
            return None
        lu, lv = lock.center
        return min(cands, key=lambda d: (d.center[0] - lu) ** 2 + (d.center[1] - lv) ** 2)

    @staticmethod
    def _radius(x: float, y: float) -> float:
        return (x * x + y * y) ** 0.5

    # ------------------------------------------------------------------
    # ④ 精准夹取
    # ------------------------------------------------------------------
    def _grasp(self, lock: Any, log: list[dict[str, Any]]) -> int:
        self._set_phase("grasping")
        wx, wy, _ = self.cal.pixel_to_world(*lock.grasp_point)
        z = self.cal.plane_z + self.depth_offset
        self.io.gripper_open()
        time.sleep(0.2)
        # 下探到抓取高度（IK 现算，非录制位）
        if not self.io.move_to(wx, wy, z, pitch=self.grasp_pitch,
                               pitch_range=self.pitch_range, duration_ms=700):
            logger.warning("下探不可达，按当前位置夹取")
        time.sleep(0.5)
        # 自适应渐闭：夹到东西就停，不靠固定脉宽
        pulse = self.io.gripper_close_adaptive(self.grip_stall_threshold)
        time.sleep(0.3)
        # 抬起（同样由 IK 现算）
        self.io.move_to(wx, wy, self.cal.plane_z + self.approach_height,
                        pitch=self.grasp_pitch, pitch_range=self.pitch_range,
                        duration_ms=700)
        log.append({"grasp_point_world": [round(wx, 4), round(wy, 4)], "grip_pulse": pulse})
        return int(pulse)

    # ------------------------------------------------------------------
    # ⑤ 抓取验证（双证据）
    # ------------------------------------------------------------------
    def _verify(self, lock: Any, grip_pulse: int, log: list[dict[str, Any]]) -> tuple[bool, bool]:
        self._set_phase("verifying")
        time.sleep(self.frame_period_s)
        frame = self.io.latest_frame()
        # 证据一：原位置目标消失
        lu, lv = lock.center
        cands = self._candidates(frame)
        target_gone = all(((d.center[0] - lu) ** 2 + (d.center[1] - lv) ** 2) ** 0.5 > 60
                          for d in cands)
        # 证据二：夹爪未闭到底（位置停滞）→ 说明夹住了东西
        #   ★ 方向无关判据：只看「离全闭位还差多少」。夹爪脉宽越大越闭
        #     （厂商 in.py：夹住 450 / 松开 75），所以"停在半途"就是夹到了东西。
        grip_stalled = abs(int(grip_pulse) - self.gripper_close_pulse) > self.grip_stall_threshold
        log.append({"target_gone": target_gone, "grip_stalled": grip_stalled})
        return target_gone, grip_stalled

    # ------------------------------------------------------------------
    # ⑥ 放置入槽（臂座旁边的料槽 side_hopper）
    # ------------------------------------------------------------------
    def _place(self, log: list[dict[str, Any]]) -> bool:
        """把夹住的袋子放进旁边的料槽，返回**是否真的放进去了**。

        与抓取的区别：抓取点每帧由视觉现算，放置点是固定工位 —— 所以这里
        不重新检测目标，只是把臂移到示教/配置好的槽口位置，松爪，落料。
        动作序列（coord 模式，高度一律用**绝对 z**）：

            抬到槽口上方（``place.approach_z``）
              → 下探进槽（``place.drop_z``）→ 松爪 → 停顿落料 → 抬离
              → 回待命位

        几何口径抄自厂商 `warehouse/in.py` 的侧向货架：x=±0.275、y=0、
        底层 z=0.02、俯仰角 -130（``place.pitch``）。臂座旁的料槽属于同一类
        「侧向固定工位」，所以默认值直接沿用。

        ``pose`` 模式（示教位姿）直接回放该组舵机脉宽，再走同样的松爪/落料/回位。
        两种模式下**只要动作没真正到位就返回 False** —— 上层据此区分
        「抓到了」与「抓到了且放进槽了」。
        """
        self._set_phase("placing")
        place = self._resolve_place()
        kind, target, source = place["kind"], place["target"], place["source"]
        if not place["ready"]:
            log.append({"placed": False, "reason": "no_place_point"})
            return False

        reached = True
        evidence: dict[str, Any] = {"place_kind": kind, "place_source": source}

        if kind == "coord":
            px, py = float(target[0]), float(target[1])
            up = self.io.move_to(px, py, self.place_approach_z,
                                 pitch=self.place_pitch, pitch_range=self.pitch_range,
                                 duration_ms=self.place_move_ms)
            time.sleep(max(0.3, self.frame_period_s))
            down = self.io.move_to(px, py, self.place_drop_z,
                                   pitch=self.place_pitch, pitch_range=self.pitch_range,
                                   duration_ms=self.place_drop_ms)
            reached = bool(up and down)
            evidence["place_coord"] = [round(px, 4), round(py, 4)]
            evidence["place_z"] = round(self.place_drop_z, 4)
            evidence["place_pitch"] = self.place_pitch
            if not reached:
                logger.warning("料槽放置点不可达 (%s, %s, z=%s)：就地松爪并如实上报",
                               px, py, self.place_drop_z)
        else:
            pairs = sorted((int(k), int(v)) for k, v in dict(target).items())
            evidence["place_pulses"] = pairs
            try:
                self.io.set_servos(self.place_drop_ms, pairs)
            except Exception as exc:  # noqa: BLE001 —— 链路问题不该吞掉
                logger.warning("示教放置位姿下发失败：%s", exc)
                reached = False
            time.sleep(max(0.3, self.frame_period_s))

        time.sleep(0.4)
        self.io.gripper_open()
        # 停顿：让袋子真的落进槽里再抬臂，否则会挂在夹爪上被带走
        time.sleep(max(0.0, self.place_settle_s))
        if kind == "coord":
            self.io.move_to(px, py, self.place_retreat_z,
                            pitch=self.place_pitch, pitch_range=self.pitch_range,
                            duration_ms=self.place_drop_ms)
        self.io.home()

        evidence["placed"] = bool(reached)
        log.append(evidence)
        return bool(reached)
