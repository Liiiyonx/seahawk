"""批量检测 D_six 水面图，筛出适合放进软著说明书的检测效果帧。

背景：原图 5-11~5-13 用的都是「沙滩人工清理新闻照」，置信度 0.4%~6.5%，
且与产品定位（岸基摄像头监控水面）不符。本脚本改用 D_six 数据集的
水面漂浮垃圾图（USV 第一人称水面视角），用仓库自带的 YOLO-World 权重
跑开放词表检测，按「高置信度 + 目标框面积占比合理」筛选。

输出：artifacts/vision-preview/ 下若干 *-water-*.jpg 候选帧 + 选型报告 JSON。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Liii\Desktop\seahawk")
VP = ROOT / "artifacts" / "vision-preview"
PROBE = ROOT / ".d_six_probe"
PY = r"C:\Users\Liii\.workbuddy\binaries\python\versions\3.13.12\python.exe"
CLIP_DIR = r"C:\Users\Liii\.cache\clip-vit-base-patch32-fixed"

# 开放词表提示词：只保留水面漂浮物的类别，去掉「shoe」这类陆上词
PROMPTS = [
    "plastic bottle floating in water",
    "plastic bag floating in water",
    "floating garbage in sea",
    "white plastic debris on water",
    "container floating in water",
]


def run_detect(images: list[Path], conf: float, out_json: Path, prev_dir: Path) -> dict:
    cmd = [
        PY, str(ROOT / "scripts" / "detect_marine_demo.py"),
        "--output", str(out_json),
        "--weights", "yolov8s-worldv2.pt",
        "--conf", str(conf),
        "--device", "cpu",
        "--clip-dir", CLIP_DIR,
        "--preview-dir", str(prev_dir),
        "--imgsz", "1600",
    ]
    for img in images:
        cmd += ["--image", str(img)]
    for prompt in PROMPTS:
        cmd += ["--class", prompt]
    print("运行:", " ".join(cmd[:6]), f"... (+{len(images)} 图, {len(PROMPTS)} 提示词)")
    subprocess.run(cmd, check=True, cwd=ROOT)
    return json.loads(out_json.read_text(encoding="utf-8"))


def score(det: dict, img_w: int, img_h: int) -> tuple[float, list[dict]]:
    """给单图打分：优先「多目标 + 中高置信度 + 框不太小」。

    软著材料里要展示的是「系统确实框出了目标」，所以：
      · 框面积占比 < 0.05% 的忽略（太小看不清）
      · 置信度低于 0.25 的不计入（避免再出现 0.4% 那种刺眼数字）
    """
    import cv2

    keep = []
    for d in det.get("detections", []):
        x1, y1, x2, y2 = d["bbox"]
        area = max(0, x2 - x1) * max(0, y2 - y1)
        ratio = area / (img_w * img_h)
        if ratio < 0.0005 or d["confidence"] < 0.25:
            continue
        keep.append({**d, "area_ratio": round(ratio, 5)})
    if not keep:
        return 0.0, []
    top = sorted((d["confidence"] for d in keep), reverse=True)
    # 打分：最高置信度为主，数量为辅（体现「不漏检」）
    return round(top[0] + 0.05 * min(len(keep), 6), 4), keep


def main() -> int:
    images = sorted(VP.glob("image (*.jpg"))
    if not images:
        print("没有待测图片，先跑 fetch_remote_zip_members.py 下载")
        return 1
    out_json = PROBE / "d_six_batch.json"
    prev_dir = PROBE / "d_six_prev"
    prev_dir.mkdir(parents=True, exist_ok=True)

    data = run_detect(images, conf=0.12, out_json=out_json, prev_dir=prev_dir)

    import cv2

    results = []
    for item in data.get("items", []):
        dets = item.get("detections", [])
        if not dets:
            continue
        # 找出对应原图尺寸
        path = None
        for cand in images:
            if cand.name in json.dumps(item, ensure_ascii=False):
                path = cand
                break
        if path is None:
            continue
        img = cv2.imread(str(path))
        h, w = img.shape[:2]
        s, keep = score(item, w, h)
        if s > 0:
            results.append({"image": path.name, "score": s, "kept": keep})
    results.sort(key=lambda r: r["score"], reverse=True)
    report = PROBE / "d_six_report.json"
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'图':22} {'分数':>6}  保留框")
    for r in results:
        classes = ",".join(
            f"{d['class'][:22]} {d['confidence']:.0%}" for d in r["kept"][:4]
        )
        print(f"{r['image']:22} {r['score']:>6.2f}  {classes}")
    if not results:
        print("没有图通过筛选（阈值可能仍偏高）")
    print(f"\n报告: {report}")
    print(f"预览目录: {prev_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
