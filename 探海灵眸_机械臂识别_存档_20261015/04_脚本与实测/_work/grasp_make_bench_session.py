"""把「机械臂受控拾取实拍」视频抽帧，落成一个演示采集会话，并用部署模型写**草稿标注**。

定位要说清楚（写进报告，别混）：
  * 这段视频是**第三人称台面视角**（拍的是机械臂整机 + 台面），不是手腕第一人称；
  * 因此它不能当「FPV 识别精度」的证据，只当**域内真实素材**与标注管线跑通的载体；
  * 草稿标注 = 模型自动出的框，**含误框**（实测大量框落在蓝色臂座/包装袋上），
    训练前必须在标注台逐帧人工过一遍，不得静默当真值。

★ 中文路径 cv2 静默失败 → 源视频先拷英文临时目录。
★ 用 imgsz=640 的导出模型出草稿（分辨率实测里它 AP50 最好）。
"""
from __future__ import annotations

import pathlib
import shutil
import sys

import cv2

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
sys.path.insert(0, str(EDGE))

from grasp.config import load_config                       # noqa: E402
from grasp.vision.dataset import Box, Dataset              # noqa: E402
from grasp.vision.detector import Detector                 # noqa: E402

WORK = pathlib.Path(__file__).resolve().parent
TMP = WORK / "tmp"
TMP.mkdir(parents=True, exist_ok=True)

SRC_VIDEO = pathlib.Path(r"c:\Users\Liii\Desktop\seahawk\_backup_selection_20261010"
                         r"\04_检测效果图\03_机械臂受控拾取实拍.mp4")
N_FRAMES = 40
DRAFT_CONF = 0.40          # 草稿阈值：比部署工作点(0.50)略松，给人工多留候选


def main() -> None:
    if not SRC_VIDEO.exists():
        raise SystemExit(f"源视频不存在：{SRC_VIDEO}")
    vid = TMP / "arm_bench.mp4"
    if not vid.exists():
        shutil.copy2(SRC_VIDEO, vid)

    cfg = load_config()
    det = Detector(cfg, mock=False)
    det.input_size = 640
    det.model_dir = WORK / "onnx_export" / "n640"
    backend = det.load()
    if backend != "onnx":
        raise SystemExit(f"草稿标注需要 onnx 后端，实得 {backend}")
    print(f"草稿标注模型：{det.model_path} · imgsz {det.input_size} · 阈值 {DRAFT_CONF}", flush=True)

    ds = Dataset.from_config(cfg)
    session = ds.new_session("arm_bench_real")
    print(f"会话：{session}", flush=True)

    cap = cv2.VideoCapture(str(vid))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idxs = [int(i) for i in range(0, n, max(1, n // N_FRAMES))][:N_FRAMES]
    written = with_box = 0
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, frame = cap.read()
        if not ok:
            continue
        okj, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if not okj:
            continue
        path = ds.add_frame(session, buf.tobytes())
        written += 1
        dets = [d for d in det.infer(frame)
                if d.cls == det.target_class and d.conf >= DRAFT_CONF]
        h, w = frame.shape[:2]
        boxes = [Box(d.cls, ((d.x1 + d.x2) / 2) / w, ((d.y1 + d.y2) / 2) / h,
                     (d.x2 - d.x1) / w, (d.y2 - d.y1) / h, conf=round(d.conf, 3))
                 for d in dets]
        ds.write_label(path, boxes)
        if boxes:
            with_box += 1
    cap.release()

    n_lbl = len(list((ds.labels_dir / session).glob("*.txt")))
    n_box = sum(len(ds.read_label(p)) for p in ds.list_frames(session))
    print(f"\n落盘 {written} 帧 · 有草稿框的帧 {with_box} 帧 · 标注文件 {n_lbl} 个 · 草稿框共 {n_box} 个")
    print(f"会话目录：{ds.raw_dir / session}")
    print(f"标注目录：{ds.labels_dir / session}")
    print("\n⚠️ 草稿标注含误框（蓝色臂座/包装袋等），训练前必须人工逐帧复核。", flush=True)


if __name__ == "__main__":
    main()
