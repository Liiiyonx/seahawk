"""组装「演示场景域」训练集：只取两个成体系、标注可信的会话。

纳入：
  * 20261015_004150_synthetic_demo  仿真海面（作业台 mock 的画面，计划书里机械臂那段要跑的就是它）
  * 20261015_144012_real_demo       真实水面漂浮物照片（补真实纹理）

排除（**故意不纳入训练**，理由写进注释免得后人踩）：
  * 20261015_183936_arm_bench_real  第三人称台面视频抽帧，**草稿标注自带误框**（大量框落在蓝色臂座），
                                    当训练真值会把误框教给模型；它留给人工在标注台逐帧复核后再用。
  * 20261015_184214_synthetic_fpv   只有 1 帧带框，且是合成图；量太少，单独作管线夹具。

类别口径：2 类（0=plastic_bag，1=buoy）。buoy 是**显式负类**——彩色浮标标成 buoy 后，
推理层按 target_class 门控直接挡在候选之外（抗彩色干扰的第一道防线）。

输出：data/built/（覆盖，属派生产物，可重建）
"""
from __future__ import annotations

import pathlib
import random
import shutil
import sys

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
sys.path.insert(0, str(EDGE))

from grasp.config import load_config            # noqa: E402
from grasp.vision.dataset import Dataset        # noqa: E402

INCLUDE_SESSIONS = ("20261015_004150_synthetic_demo", "20261015_144012_real_demo")
VAL_RATIO = 0.2
SEED = 42


def main() -> None:
    cfg = load_config()
    ds = Dataset.from_config(cfg)

    frames = []
    for sess in INCLUDE_SESSIONS:
        got = ds.labeled_frames(sess)
        if not got:
            raise SystemExit(f"会话无有效标注帧：{sess}")
        frames.extend(got)
        print(f"  {sess}: 有效标注帧 {len(got)}")

    # 清理并重建 built
    if ds.built_dir.exists():
        shutil.rmtree(ds.built_dir)
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (ds.built_dir / sub).mkdir(parents=True, exist_ok=True)

    shuffled = list(frames)
    random.Random(SEED).shuffle(shuffled)
    n_val = max(1, int(round(len(shuffled) * VAL_RATIO)))
    val_set = set(shuffled[:n_val])

    counts = {name: 0 for name in ds.classes}
    n_dup = 0
    seen: set[str] = set()
    for frame in shuffled:
        split = "val" if frame in val_set else "train"
        # ★ 两个会话的帧名都叫 frame_0001.jpg…，直接按原名拷进同一个平铺目录会**互相覆盖**，
        #   282 帧会缩水到 153 帧。用「会话短标签_原名」消歧。
        tag = "syn" if "synthetic" in frame.parent.name else "real"
        new_stem = f"{tag}_{frame.stem}"
        if new_stem in seen:
            n_dup += 1
            continue
        seen.add(new_stem)
        shutil.copy2(frame, ds.built_dir / "images" / split / f"{new_stem}{frame.suffix}")
        label = ds.frame_label_path(frame, ds.raw_dir, ds.labels_dir)
        shutil.copy2(label, ds.built_dir / "labels" / split / f"{new_stem}.txt")
        for box in ds.read_label(frame):
            counts[box.cls] = counts.get(box.cls, 0) + 1

    names = "\n".join(f"  {i}: {name}" for i, name in enumerate(ds.classes))
    (ds.built_dir / "data.yaml").write_text(
        "# 由 _work/grasp_build_domain.py 生成（演示场景域）\n"
        f"path: {ds.built_dir.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        f"names:\n{names}\n",
        encoding="utf-8",
    )

    print(f"\n组装完成：train {len(shuffled) - n_val} · val {n_val} · 合计 {len(shuffled)}"
          f"（重名跳过 {n_dup}）")
    n_img = len(list((ds.built_dir / "images" / "train").glob("*"))) + \
        len(list((ds.built_dir / "images" / "val").glob("*")))
    print(f"实落盘图片 {n_img} 张（应与合计一致）")
    print(f"类别分布：{counts}")
    print(f"data.yaml：{ds.built_dir / 'data.yaml'}")


if __name__ == "__main__":
    main()
