"""把 AI 生成的机械臂第一人称图落成一个采集会话，当**管线夹具**（不是效果证据）。

为什么这么做：仓库里没有任何「手腕第一人称」真实帧，FPV 域是空的 —— 这个会话
只用来把「采集 → 标注 → 组装 → 训练 → 部署」整条链路走通，证明 FPV 域的接入方式可行。

★ 三条硬规矩写死在代码里，别改：
  1. 裁掉生成器右下角「AI生成」水印（固定角落，会变成训练捷径特征，也会泄露来源）；
  2. 缩到 640×480 —— 与树莓派 usb_cam 输出同口径，避免"训练用高清、部署用低清"的域错配；
  3. 会话名带 `synthetic_fpv`，标注目录与真实会话分开，**绝不与真实数据混合统计精度**。

★ 中文路径 cv2 静默失败 → 源图在 _work/ai_fpv（英文路径）。
"""
from __future__ import annotations

import pathlib
import sys

import cv2

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
sys.path.insert(0, str(EDGE))

from grasp.config import load_config                       # noqa: E402
from grasp.vision.dataset import Box, Dataset              # noqa: E402
from grasp.vision.detector import Detector                 # noqa: E402

WORK = pathlib.Path(__file__).resolve().parent
SRC = WORK / "ai_fpv"
OUT = WORK / "shots" / "fpv_session"
OUT.mkdir(parents=True, exist_ok=True)

CROP_RIGHT = 0.13       # 裁掉右 13%
CROP_BOTTOM = 0.10      # 裁掉下 10%
CAM_W, CAM_H = 640, 480  # 与 usb_cam 同口径
DRAFT_CONF = 0.35


def main() -> None:
    files = sorted(SRC.glob("fpv_*.jpg")) + sorted(SRC.glob("fpv_*.png"))
    if not files:
        raise SystemExit(f"没找到 AI 生成图：{SRC}")

    cfg = load_config()
    det = Detector(cfg, mock=False)
    det.input_size = 640
    det.model_dir = WORK / "onnx_export" / "n640"
    if det.load() != "onnx":
        raise SystemExit("草稿标注需要 onnx 后端")

    ds = Dataset.from_config(cfg)
    session = ds.new_session("synthetic_fpv")
    print(f"会话：{session}", flush=True)

    tiles = []
    for path in files:
        img = cv2.imread(str(path))
        if img is None:
            print("  读取失败：", path.name)
            continue
        h, w = img.shape[:2]
        img = img[0:int(h * (1 - CROP_BOTTOM)), 0:int(w * (1 - CROP_RIGHT))]   # 去水印
        img = cv2.resize(img, (CAM_W, CAM_H))                                  # 对齐相机口径
        okj, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not okj:
            continue
        frame_path = ds.add_frame(session, buf.tobytes())
        dets = [d for d in det.infer(img)
                if d.cls == det.target_class and d.conf >= DRAFT_CONF]
        boxes = [Box(d.cls, ((d.x1 + d.x2) / 2) / CAM_W, ((d.y1 + d.y2) / 2) / CAM_H,
                     (d.x2 - d.x1) / CAM_W, (d.y2 - d.y1) / CAM_H, conf=round(d.conf, 3))
                 for d in dets]
        ds.write_label(frame_path, boxes)
        print(f"  {path.name}: 草稿框 {len(boxes)} 个"
              + ("" if not boxes else
                 "  " + " ".join(f"{b.conf:.2f}" for b in boxes)), flush=True)

        vis = img.copy()
        for d in dets:
            cv2.rectangle(vis, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), (60, 60, 235), 2)
            cv2.putText(vis, f"{d.cls} {d.conf:.2f}", (int(d.x1), max(14, int(d.y1) - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(vis)

    if tiles:
        import numpy as np
        cols, tw, th = 3, 320, 240
        rows = (len(tiles) + cols - 1) // cols
        sheet = np.full((rows * th, cols * tw, 3), 24, np.uint8)
        for i, t in enumerate(tiles):
            r, c = divmod(i, cols)
            sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = cv2.resize(t, (tw, th))
        p = OUT / "fpv_draft.jpg"
        cv2.imwrite(str(p), sheet)
        print(f"\n草稿拼图：{p}", flush=True)

    n_box = sum(len(ds.read_label(p)) for p in ds.list_frames(session))
    print(f"落盘 {len(list(ds.list_frames(session)))} 帧 · 草稿框共 {n_box} 个")
    print(f"会话目录：{ds.raw_dir / session}")
    print("\n⚠️ 本会话 100% 合成图，只作管线夹具；任何精度数字都必须标注「合成」。", flush=True)


if __name__ == "__main__":
    main()
