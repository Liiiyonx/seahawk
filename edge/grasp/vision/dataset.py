"""YOLO 格式数据集组织：采集帧 → 标注 → 留出集划分。

目录约定（``data.root`` 之下）::

    data/
      raw/<session>/frame_0001.jpg     采集的原始帧（按采集会话分组）
      labels/<session>/frame_0001.txt  与帧同名的 YOLO 标注
      built/                           组装好的训练集（ultralytics 直接吃）
        images/train/*.jpg
        images/val/*.jpg
        labels/train/*.txt
        labels/val/*.txt
        data.yaml

标注行格式与 YOLO 一致：``cls_id cx cy w h``，归一化到 0..1。
类别索引由 ``vision.classes`` 决定 —— **顺序即语义**，改顺序必须重训。
"""

from __future__ import annotations

import logging
import random
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("oceanus.grasp.dataset")


class DatasetError(RuntimeError):
    """数据集不完整或标注格式非法。"""


@dataclass
class Box:
    """一个归一化标注框。"""

    cls: str
    cx: float
    cy: float
    w: float
    h: float
    conf: float = 1.0

    def to_line(self, class_index: dict[str, int]) -> str:
        if self.cls not in class_index:
            raise DatasetError(f"未知类别 {self.cls!r}；已注册 {sorted(class_index)}")
        return (f"{class_index[self.cls]} {self.cx:.6f} {self.cy:.6f} "
                f"{self.w:.6f} {self.h:.6f}")


@dataclass
class Dataset:
    """数据集管理（会话采集 + 标注读写 + 组装）。"""

    root: Path
    classes: list[str]
    capture_frames: int = 200
    val_ratio: float = 0.2
    sessions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.class_index = {name: i for i, name in enumerate(self.classes)}

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> "Dataset":
        data = cfg.get("data", {}) or {}
        vision = cfg.get("vision", {}) or {}
        base = Path(str(data.get("root", "data")))
        if not base.is_absolute():
            base = Path(__file__).resolve().parent.parent / base
        return cls(
            root=base,
            classes=list(vision.get("classes") or ["plastic_bag", "buoy"]),
            capture_frames=int(data.get("capture_frames", 200)),
            val_ratio=float(data.get("val_ratio", 0.2)),
        )

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------
    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def labels_dir(self) -> Path:
        return self.root / "labels"

    @property
    def built_dir(self) -> Path:
        return self.root / "built"

    # ------------------------------------------------------------------
    # 采集
    # ------------------------------------------------------------------
    def new_session(self, tag: str = "") -> str:
        """开一个采集会话，返回会话名。"""
        name = f"{datetime.now():%Y%m%d_%H%M%S}" + (f"_{tag}" if tag else "")
        (self.raw_dir / name).mkdir(parents=True, exist_ok=True)
        (self.labels_dir / name).mkdir(parents=True, exist_ok=True)
        self.sessions.append(name)
        return name

    def add_frame(self, session: str, jpeg: bytes) -> Path:
        """把一帧 JPEG 落盘，返回帧路径。"""
        if not jpeg:
            raise DatasetError("空帧，拒绝落盘")
        folder = self.raw_dir / session
        folder.mkdir(parents=True, exist_ok=True)
        n = len(list(folder.glob("frame_*.jpg"))) + 1
        path = folder / f"frame_{n:04d}.jpg"
        path.write_bytes(jpeg)
        return path

    def list_frames(self, session: str | None = None) -> list[Path]:
        base = self.raw_dir / session if session else self.raw_dir
        return sorted(base.rglob("frame_*.jpg"))

    @staticmethod
    def frame_label_path(frame: Path, raw_dir: Path, labels_dir: Path) -> Path:
        """帧路径 → 对应标注路径（保持会话子目录结构）。"""
        rel = frame.relative_to(raw_dir)
        return (labels_dir / rel).with_suffix(".txt")

    # ------------------------------------------------------------------
    # 标注
    # ------------------------------------------------------------------
    def write_label(self, frame: Path, boxes: list[Box | dict[str, Any]]) -> Path:
        label_path = self.frame_label_path(frame, self.raw_dir, self.labels_dir)
        label_path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        for box in boxes:
            if isinstance(box, dict):
                box = Box(str(box["cls"]), float(box["cx"]), float(box["cy"]),
                          float(box["w"]), float(box["h"]), float(box.get("conf", 1.0)))
            lines.append(box.to_line(self.class_index))
        label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return label_path

    def read_label(self, frame: Path) -> list[Box]:
        label_path = self.frame_label_path(frame, self.raw_dir, self.labels_dir)
        if not label_path.exists():
            return []
        boxes: list[Box] = []
        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            idx = int(parts[0])
            name = self.classes[idx] if 0 <= idx < len(self.classes) else f"cls{idx}"
            boxes.append(Box(name, float(parts[1]), float(parts[2]),
                             float(parts[3]), float(parts[4])))
        return boxes

    def labeled_frames(self, session: str | None = None) -> list[Path]:
        """只返回有非空标注的帧 —— 组装训练集时用这个，避免把空标注当负样本。"""
        return [f for f in self.list_frames(session) if self.read_label(f)]

    def built_stem(self, frame: Path) -> str:
        """组装训练集时的文件主名：用「会话名_原名」消歧。

        ★ 各会话的帧名都叫 ``frame_0001.jpg``…；多会话一起组装时若按原名平铺，
          后一个会话的同名帧会**静默覆盖**前一个（实测 282 帧缩水到 153 帧，
          且不报任何错）。带上会话名后同名即不再同名。
        """
        try:
            rel = frame.relative_to(self.raw_dir)
        except ValueError:
            return frame.stem
        return f"{rel.parent.name}_{rel.stem}" if rel.parent.name else frame.stem

    # ------------------------------------------------------------------
    # 组装
    # ------------------------------------------------------------------
    def build(self, session: str | None = None, seed: int = 42) -> dict[str, Any]:
        """组装 ultralytics 可用的数据集目录，返回统计信息。"""
        frames = self.labeled_frames(session)
        if len(frames) < 5:
            raise DatasetError(f"有标注的帧太少（{len(frames)}），至少需要 5 帧才能组装")

        if self.built_dir.exists():
            shutil.rmtree(self.built_dir)
        for sub in ("images/train", "images/val", "labels/train", "labels/val"):
            (self.built_dir / sub).mkdir(parents=True, exist_ok=True)

        shuffled = list(frames)
        random.Random(seed).shuffle(shuffled)
        n_val = max(1, int(round(len(shuffled) * self.val_ratio)))
        val_set, train_set = set(shuffled[:n_val]), set(shuffled[n_val:])

        counts: dict[str, int] = {name: 0 for name in self.classes}
        for frame in shuffled:
            split = "val" if frame in val_set else "train"
            stem = self.built_stem(frame)
            shutil.copy2(frame, self.built_dir / "images" / split / f"{stem}{frame.suffix}")
            label = self.frame_label_path(frame, self.raw_dir, self.labels_dir)
            shutil.copy2(label, self.built_dir / "labels" / split / f"{stem}.txt")
            for box in self.read_label(frame):
                counts[box.cls] = counts.get(box.cls, 0) + 1

        yaml_path = self.built_dir / "data.yaml"
        names = "\n".join(f"  {i}: {name}" for i, name in enumerate(self.classes))
        yaml_path.write_text(
            f"# 由 edge/grasp/vision/dataset.py 生成，请勿手工编辑\n"
            f"path: {self.built_dir.as_posix()}\n"
            f"train: images/train\n"
            f"val: images/val\n"
            f"names:\n{names}\n",
            encoding="utf-8",
        )
        stats = {
            "train": len(train_set),
            "val": len(val_set),
            "total": len(shuffled),
            "per_class": counts,
            "data_yaml": str(yaml_path),
        }
        logger.info("数据集组装完成：train=%d val=%d 类别分布=%s",
                    stats["train"], stats["val"], counts)
        return stats
