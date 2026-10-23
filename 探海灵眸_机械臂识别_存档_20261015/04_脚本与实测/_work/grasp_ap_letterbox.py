"""换 letterbox 口径跑同一个模型，看 AP50 差在哪。

部署路径 vision/detector.py 的 _blob() 把图贴到画布**左上角**（代码里明确注释
「不居中」）；而 ultralytics 训练/导出用的是**居中** letterbox。这里用同一份
ONNX、同一批独立测试集，只换 letterbox 口径，比较 AP50。
"""
from __future__ import annotations

import pathlib
import sys

import cv2

WORK = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(WORK))
EDGE = WORK.parent / "edge"
sys.path.insert(0, str(EDGE))

from grasp.config import load_config                      # noqa: E402
from grasp.vision.detector import Detection, Detector    # noqa: E402
from grasp_detect_run import DATA, full_eval, load_gt    # noqa: E402


class CenteredDetector(Detector):
    """居中 letterbox（与训练口径一致），**先减 padding、后缩放再裁剪**。

    注意：父类 _decode 是「先 /scale 再 clip 到原图边界」，这个顺序只对左上
    letterbox 成立。居中口径必须先减 pad 再缩放，否则未减 pad 的坐标（最大可到
    input_size/scale，远大于原图边）会先被裁掉，减 pad 后就整体偏了。
    """

    _pad = (0, 0)

    def _blob(self, frame):
        h, w = frame.shape[:2]
        scale = min(self.input_size / w, self.input_size / h)
        nw, nh = int(round(w * scale)), int(round(h * scale))
        resized = cv2.resize(frame, (nw, nh))
        top = (self.input_size - nh) // 2
        left = (self.input_size - nw) // 2
        canvas = cv2.copyMakeBorder(
            resized, top, self.input_size - nh - top, left, self.input_size - nw - left,
            cv2.BORDER_CONSTANT, value=(114, 114, 114),
        )
        self._pad = (left, top)
        blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0,
                                     (self.input_size, self.input_size), swapRB=True, crop=False)
        return blob, scale

    def _decode(self, out, frame, scale):
        import numpy as np

        pred = np.squeeze(out, axis=0)
        if pred.shape[0] < pred.shape[1]:
            pred = pred.T
        boxes_xywh = pred[:, :4]
        scores = pred[:, 4:]
        cls_ids = scores.argmax(axis=1)
        confs = scores.max(axis=1)
        keep = confs >= self.conf_threshold
        boxes_xywh, cls_ids, confs = boxes_xywh[keep], cls_ids[keep], confs[keep]
        if len(boxes_xywh) == 0:
            return []

        xyxy = np.empty_like(boxes_xywh)
        xyxy[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
        xyxy[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
        xyxy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
        xyxy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2

        px, py = self._pad
        xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - px) / scale     # 先减 pad，再缩放
        xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - py) / scale

        h, w = frame.shape[:2]
        xyxy[:, [0, 2]] = xyxy[:, [0, 2]].clip(0, w - 1)      # 此时才裁剪
        xyxy[:, [1, 3]] = xyxy[:, [1, 3]].clip(0, h - 1)

        idx = cv2.dnn.NMSBoxes(xyxy.tolist(), confs.tolist(),
                               self.conf_threshold, self.iou_threshold)
        dets: list[Detection] = []
        for i in (idx.flatten() if hasattr(idx, "flatten") else list(idx)):
            ci = int(cls_ids[i])
            name = self.classes[ci] if ci < len(self.classes) else f"cls{ci}"
            x1, y1, x2, y2 = xyxy[i]
            dets.append(Detection(name, float(confs[i]),
                                  float(x1), float(y1), float(x2), float(y2)))
        return dets


def check_classes(labels_dir: pathlib.Path) -> None:
    seen: dict[int, int] = {}
    for p in labels_dir.glob("*.txt"):
        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts:
                seen[int(float(parts[0]))] = seen.get(int(float(parts[0])), 0) + 1
    print("测试集标注里出现的类别索引 → 框数：", dict(sorted(seen.items())))


def main() -> None:
    cfg = load_config()
    test_imgs = sorted((DATA / "public_plastic" / "images" / "test").glob("*.*"))
    labels = DATA / "public_plastic" / "labels" / "test"
    check_classes(labels)
    print(f"测试集 {len(test_imgs)} 张")

    for tag, cls in (("部署口径（左上 letterbox）", Detector),
                     ("训练口径（居中 letterbox）", CenteredDetector)):
        det = cls(cfg, mock=False)
        det.load()
        ev = full_eval(det, test_imgs, labels)
        p50, r50 = ev["p50_r50"]
        print(f"{tag}: AP50={ev['ap50']:.4f}  conf0.50 P={p50:.3f} R={r50:.3f} "
              f"(候选 {ev['n_pred']} / 真值 {ev['n_gt']})")


if __name__ == "__main__":
    main()
