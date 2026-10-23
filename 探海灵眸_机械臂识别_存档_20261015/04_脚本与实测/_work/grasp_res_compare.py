"""分辨率对比实测：同一个 best.pt 导出成 416 / 640 / 768 三个 ONNX，
走**部署同一条 cv2.dnn 推理路径**（Detector，只改 input_size + model_dir），
在下面三组素材上分别量一遍：

  A. SC-FloatWaste 独立测试集（400 张真实漂浮物照，有真值）→ AP50 / P / R
  B. 机械臂受控拾取实拍视频（720×1280，抽 30 帧，无真值）→ 检出率 / 置信度 / 误框数
  C. 水面塑料袋检测实拍照片（5120×2880，无真值）→ 能否检出那个袋子

★ 中文路径 cv2 静默失败 → 视频/照片先拷到英文临时目录。
★ 不写任何「合成检测」：mock=false，模型缺失直接报错退出。
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

from grasp.config import load_config                      # noqa: E402
from grasp.vision.detector import Detector               # noqa: E402

WORK = pathlib.Path(__file__).resolve().parent
EXPORT = WORK / "onnx_export"
TMP = WORK / "tmp"
OUT = WORK / "shots" / "res_compare"
TMP.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

SIZES = (416, 640, 768)
DATA = EDGE / "grasp" / "data"
TEST_IMG = DATA / "public_plastic" / "images" / "test"
TEST_LBL = DATA / "public_plastic" / "labels" / "test"

SRC_DIR = pathlib.Path(r"c:\Users\Liii\Desktop\seahawk\_backup_selection_20261010\04_检测效果图")
SRC_VIDEO = SRC_DIR / "03_机械臂受控拾取实拍.mp4"
SRC_PHOTO = SRC_DIR / "04_水面塑料袋检测实拍.jpg"


# ----------------------------------------------------------------------
def to_ascii(src: pathlib.Path, tag: str) -> pathlib.Path | None:
    if not src.exists():
        print("  源文件不存在：", src)
        return None
    dst = TMP / f"{tag}{src.suffix.lower()}"
    if not dst.exists():
        shutil.copy2(src, dst)
    return dst


def load_gt(label_path: pathlib.Path, w: int, h: int) -> list[tuple[float, float, float, float]]:
    if not label_path.exists():
        return []
    out = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5 or int(float(parts[0])) != 0:
            continue
        cx, cy, bw, bh = (float(v) for v in parts[1:5])
        out.append(((cx - bw / 2) * w, (cy - bh / 2) * h, (cx + bw / 2) * w, (cy + bh / 2) * h))
    return out


def iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def build_detector(cfg: dict, size: int) -> Detector:
    model_dir = EXPORT / f"n{size}"
    onnx = model_dir / "best.onnx"
    if not onnx.exists():
        raise SystemExit(f"缺少 {onnx}，请先跑 grasp_export_sizes.py")
    det = Detector(cfg, mock=False)
    det.input_size = size                 # 覆盖配置里的部署尺寸
    det.model_dir = model_dir             # 指向该尺寸的导出目录（无 tuning.json → ROI=None）
    det.load()
    if det.backend != "onnx":
        raise SystemExit(f"imgsz={size} 后端不是 onnx，而是 {det.backend}")
    return det


# ----------------------------------------------------------------------
def eval_test(det: Detector, low_conf: float = 0.05) -> dict:
    """整集评估：把 conf 压到 low_conf 收集全部候选，再统一算 AP50 与工作点 P/R。"""
    images = sorted(TEST_IMG.glob("*.*"))
    old = det.conf_threshold
    det.conf_threshold = low_conf
    n_gt = 0
    matched: list[tuple[float, bool]] = []
    try:
        for path in images:
            frame = cv2.imread(str(path))
            if frame is None:
                continue
            h, w = frame.shape[:2]
            gt = load_gt(TEST_LBL / (path.stem + ".txt"), w, h)
            n_gt += len(gt)
            preds = [d for d in det.infer(frame) if d.cls == det.target_class]
            preds.sort(key=lambda d: -d.conf)
            used = [False] * len(gt)
            for d in preds:
                best_i, best_iou = -1, 0.0
                for i, g in enumerate(gt):
                    if used[i]:
                        continue
                    v = iou((d.x1, d.y1, d.x2, d.y2), g)
                    if v > best_iou:
                        best_iou, best_i = v, i
                hit = best_iou >= 0.5
                if hit:
                    used[best_i] = True
                matched.append((d.conf, hit))
    finally:
        det.conf_threshold = old

    matched.sort(key=lambda x: -x[0])
    if not matched or n_gt == 0:
        return {"n_img": len(images), "n_gt": n_gt, "n_pred": len(matched), "ap50": 0.0,
                "p50": 0.0, "r50": 0.0, "p30": 0.0, "r30": 0.0}
    arr_tp = np.array([1.0 if t else 0.0 for _, t in matched])
    ctp = np.cumsum(arr_tp)
    cfp = np.cumsum(1.0 - arr_tp)
    prec = ctp / np.maximum(ctp + cfp, 1e-9)
    rec = ctp / n_gt
    mrec = np.concatenate(([0.0], rec, [1.0]))
    mpre = np.concatenate(([1.0], prec, [0.0]))
    for i in range(len(mpre) - 2, -1, -1):
        mpre[i] = max(mpre[i], mpre[i + 1])
    idx = np.where(mrec[1:] != mrec[:-1])[0]
    ap50 = float(np.sum((mrec[idx + 1] - mrec[idx]) * mpre[idx + 1]))

    def at(thr: float) -> tuple[float, float]:
        tp = sum(1 for c, t in matched if c >= thr and t)
        fp = sum(1 for c, t in matched if c >= thr and not t)
        return (tp / max(tp + fp, 1), tp / n_gt)

    p50, r50 = at(0.50)
    p30, r30 = at(0.30)
    return {"n_img": len(images), "n_gt": n_gt, "n_pred": len(matched), "ap50": ap50,
            "p50": p50, "r50": r50, "p30": p30, "r30": r30}


def eval_video(det: Detector, vid: pathlib.Path, sample: int = 30) -> dict:
    cap = cv2.VideoCapture(str(vid))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    idxs = [int(i) for i in np.linspace(0, max(0, n - 1), sample)]
    confs, centers, hit, extra, tiles = [], [], 0, 0, []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, f = cap.read()
        if not ok:
            continue
        dets = det.infer(f)
        tgts = [d for d in dets if d.cls == det.target_class
                and d.conf >= det.conf_threshold and det._in_roi(d, f)]
        extra += len(dets) - len(tgts)     # 阈值上但非目标类的框（误框线索）
        if tgts:
            hit += 1
            best = max(tgts, key=lambda d: d.conf)
            confs.append(best.conf)
            centers.append(best.center)
            if len(tiles) < 6:
                vis = f.copy()
                for d in dets:
                    col = (60, 60, 235) if d.cls == det.target_class else (150, 150, 150)
                    cv2.rectangle(vis, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), col, 2)
                    cv2.putText(vis, f"{d.cls} {d.conf:.2f}", (int(d.x1), max(12, int(d.y1) - 5)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                tiles.append(vis)
    cap.release()
    jit = None
    if len(centers) >= 2:
        jit = (statistics.pstdev([c[0] for c in centers]), statistics.pstdev([c[1] for c in centers]))
    return {"n": len(idxs), "hit": hit, "confs": confs, "jitter": jit, "extra": extra, "tiles": tiles}


def eval_photo(det: Detector, img: pathlib.Path) -> dict:
    frame = cv2.imread(str(img))
    if frame is None:
        return {"ok": False}
    dets = det.infer(frame)
    tgts = [d for d in dets if d.cls == det.target_class and d.conf >= det.conf_threshold]
    vis = frame.copy()
    for d in dets:
        col = (60, 60, 235) if d.cls == det.target_class else (150, 150, 150)
        cv2.rectangle(vis, (int(d.x1), int(d.y1)), (int(d.x2), int(d.y2)), col, 3)
        cv2.putText(vis, f"{d.cls} {d.conf:.2f}", (int(d.x1), max(20, int(d.y1) - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2, cv2.LINE_AA)
    return {"ok": True, "n_all": len(dets), "n_tgt": len(tgts),
            "confs": [round(d.conf, 3) for d in dets], "vis": vis,
            "wh": (frame.shape[1], frame.shape[0])}


# ----------------------------------------------------------------------
def main() -> None:
    cfg = load_config()
    vid = to_ascii(SRC_VIDEO, "arm_video")
    photo = to_ascii(SRC_PHOTO, "water_photo")

    rows = []
    for size in SIZES:
        print(f"\n{'=' * 84}\nimgsz = {size}\n{'=' * 84}", flush=True)
        det = build_detector(cfg, size)
        print(f"  后端 {det.backend} · 模型 {det.model_path} · conf {det.conf_threshold} · "
              f"ROI {det.roi}", flush=True)

        test = eval_test(det)
        print(f"  [A 测试集] {test['n_img']} 张 / 真值 {test['n_gt']} 个 / 候选 {test['n_pred']} 个")
        print(f"            AP50 {test['ap50']:.4f} · conf0.5 P {test['p50']:.3f} R {test['r50']:.3f}"
              f" · conf0.3 P {test['p30']:.3f} R {test['r30']:.3f}", flush=True)

        v = eval_video(det, vid) if vid else {"n": 0, "hit": 0, "confs": [], "jitter": None, "extra": 0, "tiles": []}
        if v["n"]:
            confs = v["confs"]
            cs = (f"最高 {max(confs):.3f} 中位 {statistics.median(confs):.3f} 最低 {min(confs):.3f}"
                  if confs else "无")
            jt = (f"x σ={v['jitter'][0]:.1f} y σ={v['jitter'][1]:.1f}px" if v["jitter"] else "命中太少")
            print(f"  [B 实拍视频] 抽 {v['n']} 帧 → 目标类检出 {v['hit']} 帧（{100*v['hit']/v['n']:.0f}%）· "
                  f"非目标框 {v['extra']} 个")
            print(f"              置信度 {cs} · 框中心抖动 {jt}", flush=True)
            if v["tiles"]:
                cols = 3
                tw, th = 300, 533
                r = (len(v["tiles"]) + cols - 1) // cols
                sheet = np.full((r * th, cols * tw, 3), 24, np.uint8)
                for i, t in enumerate(v["tiles"]):
                    rr, cc = divmod(i, cols)
                    sheet[rr * th:(rr + 1) * th, cc * tw:(cc + 1) * tw] = cv2.resize(t, (tw, th))
                p = OUT / f"video_n{size}.jpg"
                cv2.imwrite(str(p), sheet)
                print(f"              视频拼图：{p}", flush=True)

        p = eval_photo(det, photo) if photo else {"ok": False}
        if p["ok"]:
            print(f"  [C 水面照] {p['wh'][0]}×{p['wh'][1]} · 全部检出 {p['n_all']} · 目标类 {p['n_tgt']} · "
                  f"conf {p['confs']}")
            if p["vis"] is not None:
                sp = OUT / f"water_n{size}.jpg"
                small = cv2.resize(p["vis"], (1280, 720))
                cv2.imwrite(str(sp), small)
                print(f"              照片缩略图：{sp}", flush=True)

        rows.append({"size": size, **{k: test[k] for k in ("ap50", "p50", "r50", "p30", "r30")},
                     "v_hit": v["hit"], "v_n": v["n"], "v_extra": v["extra"],
                     "photo_all": p.get("n_all", -1), "photo_tgt": p.get("n_tgt", -1)})

    print(f"\n{'=' * 84}\n对比总表\n{'=' * 84}")
    print(f"{'imgsz':>6} {'AP50':>7} {'P@.5':>7} {'R@.5':>7} {'P@.3':>7} {'R@.3':>7} "
          f"{'视频命中':>10} {'非目标框':>9} {'水面照全部':>11} {'水面照目标':>11}")
    for r in rows:
        print(f"{r['size']:>6} {r['ap50']:>7.4f} {r['p50']:>7.3f} {r['r50']:>7.3f} "
              f"{r['p30']:>7.3f} {r['r30']:>7.3f} {r['v_hit']:>4}/{r['v_n']:<5} "
              f"{r['v_extra']:>9} {r['photo_all']:>11} {r['photo_tgt']:>11}")


if __name__ == "__main__":
    main()
