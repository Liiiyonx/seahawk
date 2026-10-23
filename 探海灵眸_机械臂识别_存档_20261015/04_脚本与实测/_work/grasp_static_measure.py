"""在仓库里现有的「机械臂受控拾取实拍」视频/照片上，实测当前部署模型的识别情况。

这是目前我能拿到的、最接近你演示场景的真实素材（受控拾取实拍 + 水面塑料袋检测实拍）。
注意：这两份素材没有标注真值，所以只能量「检出率 / 置信度 / 框位置稳定性」，
**不能算 precision/recall** —— 报告里会明确区分。

★ 中文路径 cv2 会静默失败，所以先把源文件拷到英文临时目录再处理。
"""
from __future__ import annotations

import pathlib
import shutil
import statistics
import sys

import cv2
import numpy as np

EDGE = pathlib.Path(__file__).resolve().parents[1] / "edge"
sys.path.insert(0, str(EDGE))

from grasp.config import load_config                    # noqa: E402
from grasp.vision.detector import Detector              # noqa: E402

TMP = pathlib.Path(__file__).resolve().parent / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
OUT = pathlib.Path(__file__).resolve().parent / "shots" / "static_measure"
OUT.mkdir(parents=True, exist_ok=True)

SRC_VIDEO = pathlib.Path(r"c:\Users\Liii\Desktop\seahawk\_backup_selection_20261010"
                         r"\04_检测效果图\03_机械臂受控拾取实拍.mp4")
SRC_IMG = pathlib.Path(r"c:\Users\Liii\Desktop\seahawk\_backup_selection_20261010"
                       r"\04_检测效果图\04_水面塑料袋检测实拍.jpg")


def to_ascii(src: pathlib.Path) -> pathlib.Path | None:
    if not src.exists():
        print("源文件不存在：", src)
        return None
    dst = TMP / ("src" + src.suffix.lower())
    shutil.copy2(src, dst)
    return dst


def draw(frame, dets, target, conf_thr):
    vis = frame.copy()
    for d in dets:
        is_t = d.cls == target
        col = (60, 60, 235) if is_t else (150, 150, 150)
        cv2.rectangle(vis, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), col, 2)
        cv2.putText(vis, f"{d.cls} {d.conf:.2f}", (int(d.x1), max(12, int(d.y1) - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return vis


def grid(tiles, cols=4, tw=380, th=285):
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.full((rows * th, cols * tw, 3), 24, np.uint8)
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = cv2.resize(t, (tw, th))
    return sheet


def main() -> None:
    cfg = load_config()
    det = Detector(cfg, mock=False)
    backend = det.load()
    print(f"后端 {backend} · 目标类 {det.target_class} · conf {det.conf_threshold} · "
          f"input {det.input_size} · ROI {det.roi}", flush=True)
    if backend == "none":
        raise SystemExit("没有模型")

    # ---------------- 单张照片 ----------------
    img_path = to_ascii(SRC_IMG)
    if img_path:
        img = cv2.imread(str(img_path))
        if img is None:
            print("照片读不出来：", img_path)
        else:
            h, w = img.shape[:2]
            dets = det.infer(img)
            tgts = det.targets(img)
            print(f"\n[照片] {w}×{h} · 全部检出 {len(dets)} · 进入抓取候选 {len(tgts)}", flush=True)
            for d in dets:
                print(f"   {d.cls:12s} conf={d.conf:.3f} "
                      f"box=({d.x1:.0f},{d.y1:.0f},{d.x2:.0f},{d.y2:.0f}) "
                      f"尺寸 {d.width:.0f}×{d.height:.0f}", flush=True)
            cv2.imwrite(str(OUT / "photo_water.jpg"), draw(img, dets, det.target_class,
                                                           det.conf_threshold))

    # ---------------- 视频抽帧 ----------------
    vid_path = to_ascii(SRC_VIDEO)
    if not vid_path:
        return
    cap = cv2.VideoCapture(str(vid_path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"\n[视频] {n} 帧 · {fps:.1f} fps · {w}×{h} · "
          f"时长约 {n / fps:.1f}s" if fps else f"\n[视频] {n} 帧 · {w}×{h}", flush=True)

    sample = 30
    idxs = [int(i) for i in np.linspace(0, max(0, n - 1), sample)]
    tiles, centers, confs, hit = [], [], [], 0
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = cap.read()
        if not ok:
            continue
        dets = det.infer(f)
        tgts = det.targets(f)
        if tgts:
            hit += 1
            best = max(tgts, key=lambda d: d.conf)
            centers.append(best.center)
            confs.append(best.conf)
        print(f"  帧 {i:5d}: 检出 {len(dets)}（目标类 {len(tgts)}）"
              + ("" if not tgts else
                 "  " + " | ".join(f"{d.conf:.2f}@{int(d.center[0])},{int(d.center[1])}"
                                   f" {d.width:.0f}×{d.height:.0f}" for d in tgts)), flush=True)
        if len(tiles) < 12 and tgts:
            tiles.append(draw(f, dets, det.target_class, det.conf_threshold))
    cap.release()

    total = len(idxs)
    print(f"\n[视频汇总] 抽 {total} 帧 → 检出目标类 {hit} 帧 "
          f"（{100.0 * hit / total:.0f}%）", flush=True)
    if confs:
        print(f"  置信度：最高 {max(confs):.3f} · 中位 {statistics.median(confs):.3f} · "
              f"最低 {min(confs):.3f}", flush=True)
    if len(centers) >= 2:
        sx = statistics.pstdev([c[0] for c in centers])
        sy = statistics.pstdev([c[1] for c in centers])
        print(f"  框中心抖动：x σ={sx:.1f}px · y σ={sy:.1f}px "
              f"（画面 {w}×{h}，静态目标应该很小）", flush=True)
    else:
        print("  命中帧太少，无法算抖动", flush=True)

    if tiles:
        cv2.imwrite(str(OUT / "video_frames.jpg"), grid(tiles))
        print(f"  抽帧拼图：{OUT / 'video_frames.jpg'}（只放有检出的帧）", flush=True)
    else:
        print("  ⚠️ 一帧都没检出目标类 —— 没有任何帧可拼图", flush=True)


if __name__ == "__main__":
    main()
