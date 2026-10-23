"""姿态预设：把「一组舵机脉宽」命名存下来，一键切回。

## 为什么单独存一份文件，而不是塞进 calibration.json

`calibration.json` 里已经放了标定矩阵与料槽放置点，那两样都是**设备的物理事实**
（换机器/重标定就失效）。姿态预设是**操作习惯**：比如「相机朝下」「抓取预备」
「给我看看爪子」，跟标定没有关系，也不该因为重跑一次 9 点标定就被清掉。
所以单独落一个 ``presets.json``。

## 数据形状

::

    {
      "version": 1,
      "boot_default": "初始位",
      "presets": {
        "相机朝下": {"1": 200, "2": 500, "3": 205, "4": 511, "5": 491, "6": 500},
        "初始位":   {"1": 200, "2": 500, "3": 393, "4": 756, "5": 592, "6": 500}
      }
    }

``boot_default`` 是**开机默认姿态**的名字：板子启动脚本会在执行端就绪后，
把这个预设的脉宽下发一次，让机械臂每次都停到同一个位置。
它不是必填项；名字指向的预设被删掉时，启动脚本会跳过并告警，而不是报错退出
（开机位置没设好，不该让整个执行端起不来）。

键是**舵机 ID 的字符串**（JSON 的键只能是字符串，用 int 会在读写之间来回丢类型），
值是 0..1000 的脉宽 —— 与厂商口径一致（``RawIdPosDur.position`` 是 uint16 0..1000）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("oceanus.grasp.presets")

HERE = Path(__file__).resolve().parent
DEFAULT_PRESETS_PATH = HERE / "presets.json"

#: 名称长度上限：界面上是按钮文字，太长会把布局撑坏
MAX_NAME_LEN = 18
#: 最多存多少个 —— 防手滑脚本刷爆文件
MAX_PRESETS = 40
#: 脉宽合法区间（厂商口径，与 arm_io 的校验保持一致）
PULSE_MIN, PULSE_MAX = 0, 1000

_NAME_BAD = re.compile(r"[\x00-\x1f\x7f]")


class PresetError(ValueError):
    """预设名或脉宽非法。"""


def normalize_name(name: Any) -> str:
    """校验并规整预设名。

    为什么要在服务端做：界面上是按钮，名字会参与 DOM 与 JSON 两处，
    一个带控制字符或前导空格的名字在现场会表现成「按钮点了没反应」。
    """
    if not isinstance(name, str):
        raise PresetError("预设名必须是字符串")
    clean = name.strip()
    if not clean:
        raise PresetError("预设名不能为空")
    if _NAME_BAD.search(clean):
        raise PresetError("预设名不能含控制字符")
    if len(clean) > MAX_NAME_LEN:
        raise PresetError(f"预设名最长 {MAX_NAME_LEN} 个字符，当前 {len(clean)}")
    return clean


def normalize_pose(pose: Any) -> dict[str, int]:
    """把 ``{舵机ID: 脉宽}`` 规整成 ``{ "1": 200, ... }``，非法直接报错。"""
    if not isinstance(pose, dict) or not pose:
        raise PresetError("姿态必须是非空的 {舵机ID: 脉宽}")
    out: dict[str, int] = {}
    for key, value in pose.items():
        try:
            sid = int(key)
        except (TypeError, ValueError) as exc:
            raise PresetError(f"舵机 ID 必须是整数，收到 {key!r}") from exc
        if not 1 <= sid <= 32:
            raise PresetError(f"舵机 ID 超出范围 1..32：{sid}")
        try:
            pulse = int(value)
        except (TypeError, ValueError) as exc:
            raise PresetError(f"舵机 {sid} 的脉宽必须是整数，收到 {value!r}") from exc
        if not PULSE_MIN <= pulse <= PULSE_MAX:
            raise PresetError(f"舵机 {sid} 脉宽须在 {PULSE_MIN}..{PULSE_MAX}，收到 {pulse}")
        out[str(sid)] = pulse
    return out


class PresetStore:
    """``presets.json`` 的读写。读失败不抛异常 —— 现场一个坏文件不该让作业台起不来。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PRESETS_PATH

    # ------------------------------------------------------------------
    def _load_raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "presets": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("预设文件不可读，按空处理 %s: %s", self.path, exc)
            return {"version": 1, "presets": {}}
        return raw if isinstance(raw, dict) else {"version": 1, "presets": {}}

    def load(self) -> dict[str, dict[str, int]]:
        presets = self._load_raw().get("presets")
        if not isinstance(presets, dict):
            return {}
        out: dict[str, dict[str, int]] = {}
        for name, pose in presets.items():
            try:
                out[normalize_name(name)] = normalize_pose(pose)
            except PresetError as exc:
                # 单条坏数据只丢这一条，不牵连整个文件
                logger.warning("跳过非法预设 %r: %s", name, exc)
        return out

    def boot_default(self) -> str | None:
        """开机默认姿态的名字；没设或指向不存在的预设时返回 None。

        指向不存在的预设时**只告警不报错**：开机位置没配好，不该让整个
        执行端起不来（那会连带把作业台也弄瘫）。
        """
        name = self._load_raw().get("boot_default")
        if not isinstance(name, str) or not name.strip():
            return None
        clean = name.strip()
        if clean not in self.load():
            logger.warning("boot_default 指向不存在的预设 %r，已忽略", clean)
            return None
        return clean

    def boot_pose(self) -> dict[str, int] | None:
        """开机默认姿态的脉宽表；没设时返回 None。"""
        name = self.boot_default()
        return None if name is None else self.load()[name]

    def save_all(self, presets: dict[str, dict[str, int]],
                 boot_default: str | None = None) -> None:
        """原子写：先写临时文件再 replace。断电时不会留下半个 JSON。

        ``boot_default`` 保持原样传入（None = 明确清掉）。为了不因为某次
        只改预设的写入而意外丢掉开机默认，调用方应统一用 ``write()``。
        """
        payload = {"version": 1, "boot_default": boot_default, "presets": presets}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def write(self, presets: dict[str, dict[str, int]],
              boot_default: str | None | "ellipsis" = ...) -> None:
        """写回预设；``boot_default`` 不传 = 保留文件里现有的值。"""
        if boot_default is ...:
            boot_default = self.boot_default()
        self.save_all(presets, boot_default)

    # ------------------------------------------------------------------
    def put(self, name: Any, pose: Any) -> dict[str, Any]:
        clean_name = normalize_name(name)
        clean_pose = normalize_pose(pose)
        presets = self.load()
        existed = clean_name in presets
        if not existed and len(presets) >= MAX_PRESETS:
            raise PresetError(f"预设数量已达上限 {MAX_PRESETS}，先删几个")
        presets[clean_name] = clean_pose
        self.write(presets)                     # 保留现有 boot_default
        return {"name": clean_name, "pose": clean_pose, "overwritten": existed,
                "count": len(presets), "boot_default": self.boot_default()}

    def delete(self, name: Any) -> dict[str, Any]:
        clean_name = normalize_name(name)
        presets = self.load()
        if clean_name not in presets:
            raise PresetError(f"没有这个预设：{clean_name}")
        del presets[clean_name]
        # 删掉的正好是开机默认 → 一并清掉，否则启动脚本会一直告警
        boot = self.boot_default()
        self.write(presets, None if boot == clean_name else boot)
        # ★ 必须重新导出：否则 boot_pose.json 里还留着**已被删掉**的姿态，
        #   板子下次开机照样按它摆位 —— 现场表现是「删了怎么还生效」。
        export = self.export_boot_pose()
        return {"name": clean_name, "count": len(presets),
                "boot_default": self.boot_default(), "export": export}

    def set_boot_default(self, name: Any) -> dict[str, Any]:
        """把某个预设设为开机默认姿态（板子每次启动会下发它）。"""
        clean_name = normalize_name(name)
        presets = self.load()
        if clean_name not in presets:
            raise PresetError(f"没有这个预设：{clean_name}")
        self.write(presets, clean_name)
        export = self.export_boot_pose()
        return {"name": clean_name, "pose": presets[clean_name],
                "boot_default": clean_name, "count": len(presets), "export": export}

    def clear_boot_default(self) -> dict[str, Any]:
        self.write(self.load(), None)
        export = self.export_boot_pose()
        return {"boot_default": None, "count": len(self.load()), "export": export}

    def export_boot_pose(self) -> dict[str, Any]:
        """把开机默认姿态导出成 ``boot_pose.json``，供板子在启动时读取。

        为什么要导出而不是让板上直接读 ``presets.json``：
          1. ``presets.json`` 是**操作习惯**的集合（可能有几十条），
             板子只需要开机那一条，给它一个只含必要字段的小文件更清楚；
          2. 两份文件职责分离：作业台改预设不会波及板的启动逻辑。

        导出失败**不抛异常**：作业台不能因为一个附带产物写不出去就用不了。
        但结果里会带 ``ok``/``error``，界面要如实显示 —— 否则操作员以为
        「已设开机默认」而板子上根本没生效。
        """
        path = self.path.parent / "boot_pose.json"
        name = self.boot_default()
        try:
            if name is None:
                if path.exists():
                    path.unlink()
                return {"ok": True, "path": str(path), "name": None,
                        "cleared": True}
            pose = self.load()[name]
            payload = {
                "version": 1,
                "name": name,
                "pose": pose,
                "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, path)
            return {"ok": True, "path": str(path), "name": name,
                    "cleared": False, "pose": pose}
        except OSError as exc:
            logger.warning("导出 boot_pose.json 失败：%s", exc)
            return {"ok": False, "path": str(path), "name": name, "error": str(exc)}

    def describe(self) -> dict[str, Any]:
        presets = self.load()
        return {
            "path": str(self.path),
            "count": len(presets),
            "boot_default": self.boot_default(),
            "items": [{"name": n, "pose": p} for n, p in sorted(presets.items())],
            "saved_at": (time.strftime("%Y-%m-%d %H:%M:%S",
                                       time.localtime(self.path.stat().st_mtime))
                         if self.path.exists() else None),
        }
