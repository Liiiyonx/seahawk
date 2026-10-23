"""把作业台演示数据从「合成色块图」换成**真实照片**。

为什么：built 数据集来自 data/raw/20261015_004150_synthetic_demo（抽象色块合成图），
部署模型是在真实照片上训的 —— 域差太大，标注台的「预标注」与实时检测在那些帧上
一个框都出不来，演示时是空屏。

做法：用项目自己的 Dataset API 建一个真实照片会话（保证 frame_XXXX.jpg 命名约定），
再从该会话重建 built。原始合成会话**保留在盘上不动**，需要回退时重新 build 即可。
"""
from __future__ import annotations

import pathlib
import sys

import cv2
import yaml

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
sys.path.insert(0, str(EDGE))

from grasp.config import load_config                     # noqa: E402
from grasp.vision.dataset import Box, Dataset            # noqa: E402

GRASP = EDGE / "grasp"
SRC = GRASP / "data" / "public_plastic_color"            # 真实照片 + 注入彩色干扰物（未标注）
SRC_IMAGES = SRC / "images" / "val"
SRC_LABELS = SRC / "labels" / "val"
SYNTH_SESSION = "20261015_004150_synthetic_demo"
TAG = "real_demo"


def source_names() -> dict[int, str]:
    y = yaml.safe_load((SRC / "data.yaml").read_text(encoding="utf-8"))
    return {int(k): str(v) for k, v in (y.get("names") or {}).items()}


def read_src_label(path: pathlib.Path, names: dict[int, str]) -> list[Box]:
    if not path.exists():
        return []
    boxes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 5:
            continue
        idx = int(float(parts[0]))
        boxes.append(Box(names.get(idx, f"cls{idx}"),
                         float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])))
    return boxes


def main() -> None:
    cfg = load_config()
    ds = Dataset.from_config(cfg)
    names = source_names()
    print("源类别口径（public_plastic_color）：", names)
    print("数据集类别口径（vision.classes）：", ds.classes)

    imgs = sorted(p for p in SRC_IMAGES.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    print(f"源图 {len(imgs)} 张")

    session = ds.new_session(TAG)
    print("新会话：", session)

    kept_labels = 0
    for src in imgs:
        img = cv2.imread(str(src))
        if img is None:
            print("  读图失败，跳过：", src.name)
            continue
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        if not ok:
            print("  编码失败，跳过：", src.name)
            continue
        frame = ds.add_frame(session, buf.tobytes())
        boxes = read_src_label(SRC_LABELS / (src.stem + ".txt"), names)
        ds.write_label(frame, boxes)
        if boxes:
            kept_labels += 1

    stats = ds.build(session=session)
    print(f"\n已写入 {len(list((ds.raw_dir / session).glob('frame_*.jpg')))} 帧，"
          f"其中 {kept_labels} 帧带真值框")
    print("built 重建结果：", stats)
    print(f"\n回退方法：把 build(session={session!r}) 换成 "
          f"build(session={SYNTH_SESSION!r}) 重新执行即可（合成会话仍在盘上）")


if __name__ == "__main__":
    main()
