#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC-FloatWaste 公开漂浮垃圾基准 —— 独立测试集构建器（探海灵眸 Oceanus）。

数据来源
--------
**SC-FloatWaste / FloatWaste** — 多区域河流漂浮垃圾检测基准。
``OliviaWuYJ/sc-floatwaste``（HuggingFace，CC BY 4.0；Zenodo DOI 10.5281/zenodo.21934286）
7,906 张标注图 / 27,583 个框 / 25 类，区域：Indonesia（Citarum 流域）、NSW（悉尼）、
Hobart（塔斯马尼亚）。官方划分 train 7,110 / val 796，**两者不相交**。

构建规则（冻结）
----------------
* ``test``  = 官方 **val** 划分的确定性子集（400 张）→ 独立测试集，**永不参与训练**
* ``train`` = 官方 **train** 划分的确定性子集（600 张，Indonesia）
* ``val``   = 官方 train 划分中余下的 Indonesia 图（172 张，训练期调参）

★ 只能照官方划分取子集，**不得再做随机切分** —— 随机切分只会破坏官方隔离。
★ test 覆盖三个区域，用于跨域泛化评测（数据集 README 亦要求分区域报告）。

产出（仓库根相对）
------------------
``ml/datasets/public_floatwaste/images/<split>/<region>__<stem>.<ext>``
``ml/datasets/public_floatwaste/labels/<split>/<region>__<stem>.txt``            单类 litter
``ml/datasets/public_floatwaste/labels_contract4/<split>/<region>__<stem>.txt``  四契约类
``ml/datasets/public_floatwaste/PROVENANCE.json``

用法
----
    python scripts/fetch_public_floatwaste.py --plan
    python scripts/fetch_public_floatwaste.py --download --workers 6
    python scripts/fetch_public_floatwaste.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEST = REPO_ROOT / "ml" / "datasets" / "public_floatwaste"
CACHE = Path("D:/seahawk-work/floatwaste")

HF_BASE = "https://hf-mirror.com/datasets/OliviaWuYJ/sc-floatwaste/resolve/main"
ZENODO_DOI = "10.5281/zenodo.21934286"
HF_ID = "OliviaWuYJ/sc-floatwaste"
LICENSE = "CC BY 4.0"
CITATION = (
    "Wu, Yujiao et al. FloatWaste: a multi-region riverine floating-waste "
    "detection benchmark (CC BY 4.0), https://huggingface.co/datasets/"
    "OliviaWuYJ/SC-floatwaste"
)

# 选取配额（冻结；改动必须同步 docs/competitions/public-floatwaste-benchmark.md）
TEST_QUOTA = {"Indonesia": 90, "NSW": 164, "Hobart": 146}   # = 400 张
TRAIN_QUOTA = {"Indonesia": 600}
VAL_QUOTA = {"Indonesia": 172}                              # Indonesia train 余量

# 官方 25 类 → 本项目四契约类（显式表，不做模糊匹配）。
# 契约类语义见 edge/detector/label_map.py：
#   foam=EPS 泡沫浮球及碎片 / plastic=塑料制品 / fishing_gear=废旧渔网绳索 / other=兜底
# ★ 这是**本项目自行定义的近似映射**，不是数据集官方标注，对外必须标注该边界。
CONTRACT4 = {
    1: "plastic", 2: "plastic", 3: "plastic", 4: "plastic", 5: "plastic",
    6: "plastic", 7: "fishing_gear", 8: "other", 9: "plastic", 10: "plastic",
    11: "plastic", 12: "plastic", 13: "plastic", 14: "other", 15: "other",
    16: "plastic", 17: "foam", 18: "plastic", 19: "plastic", 20: "plastic",
    21: "plastic", 22: "plastic", 23: "other", 24: "other", 25: "other",
}
CONTRACT4_NAMES = ("foam", "plastic", "fishing_gear", "other")

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def looks_like_image(p: Path) -> bool:
    """校验落盘文件真是图片（防止把 HTTP 错误页当图片存档）。"""
    try:
        if p.stat().st_size < 1024:
            return False
        head = p.open("rb").read(8)
    except OSError:
        return False
    return head.startswith(JPEG_MAGIC) or head.startswith(PNG_MAGIC)


def load_split(split: str) -> dict:
    p = CACHE / ("instances_%s.json" % split)
    if not p.exists():
        raise SystemExit(
            "缺少标注文件 %s。先下载：\n"
            "  curl.exe -L -o %s https://hf-mirror.com/datasets/%s/resolve/main/annotations/instances_%s.json"
            % (p, p, HF_ID, split)
        )
    return json.load(io.open(p, encoding="utf-8"))


def select(images: list, quota: dict) -> dict:
    """按区域配额做**确定性**选取：区域内按 file_name 升序取前 N 张。"""
    out: dict[str, list] = {}
    for region, n in quota.items():
        pool = sorted(
            (im for im in images if im.get("region") == region),
            key=lambda im: im["file_name"],
        )
        if len(pool) < n:
            raise SystemExit("区域 %s 可用 %d 张 < 配额 %d" % (region, len(pool), n))
        out[region] = pool[:n]
    return out


def build_plan() -> dict:
    val_j = load_split("val")
    train_j = load_split("train")
    test_sel = select(val_j["images"], TEST_QUOTA)
    ind = sorted(
        (im for im in train_j["images"] if im.get("region") == "Indonesia"),
        key=lambda im: im["file_name"],
    )
    n_tr, n_va = TRAIN_QUOTA["Indonesia"], VAL_QUOTA["Indonesia"]
    if len(ind) < n_tr + n_va:
        raise SystemExit("Indonesia train 只有 %d 张，不足 %d" % (len(ind), n_tr + n_va))
    return {
        "test": (val_j, test_sel),
        "train": (train_j, {"Indonesia": ind[:n_tr]}),
        "val": (train_j, {"Indonesia": ind[n_tr:n_tr + n_va]}),
    }


def write_labels(anns_by_img: dict, im: dict, root: Path, split: str, tag: str) -> int:
    w, h = float(im["width"]), float(im["height"])
    lines_litter, lines_c4 = [], []
    for a in anns_by_img.get(im["id"], []):
        x, y, bw, bh = a["bbox"]
        if bw <= 0 or bh <= 0:
            continue
        cx, cy = (x + bw / 2.0) / w, (y + bh / 2.0) / h
        nw, nh = bw / w, bh / h
        cx, cy = min(max(cx, 0.0), 1.0), min(max(cy, 0.0), 1.0)
        nw, nh = min(max(nw, 0.0), 1.0), min(max(nh, 0.0), 1.0)
        row = "%.6f %.6f %.6f %.6f" % (cx, cy, nw, nh)
        lines_litter.append("0 " + row)
        cname = CONTRACT4.get(int(a["category_id"]))
        if cname is not None:
            lines_c4.append("%d %s" % (CONTRACT4_NAMES.index(cname), row))
    for sub, lines in (("labels", lines_litter), ("labels_contract4", lines_c4)):
        d = root / sub / split
        d.mkdir(parents=True, exist_ok=True)
        (d / (tag + ".txt")).write_text("\n".join(lines), encoding="utf-8")
    return len(lines_litter)


def fetch_one(url: str, dest: Path, retries: int = 4) -> tuple[bool, str]:
    if looks_like_image(dest):
        return True, "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        if tmp.exists():
            tmp.unlink()
        cmd = [
            "curl.exe", "-s", "-L", "--retry", "3", "--retry-delay", "3",
            "--connect-timeout", "30", "-o", str(tmp), url,
        ]
        try:
            subprocess.run(cmd, capture_output=True, timeout=600)
        except (subprocess.TimeoutExpired, OSError):
            continue
        if looks_like_image(tmp):
            tmp.replace(dest)
            return True, "ok"
        time.sleep(1 + attempt * 2)
    if tmp.exists():
        tmp.unlink()
    return False, "failed"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="构建 SC-FloatWaste 独立测试集")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default=str(DEST))
    args = ap.parse_args(argv)
    root = Path(args.out)

    if args.verify:
        bad, tot = [], 0
        for split in ("train", "val", "test"):
            d = root / "images" / split
            if not d.exists():
                continue
            for p in sorted(d.iterdir()):
                if p.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    continue
                tot += 1
                if not looks_like_image(p):
                    bad.append(str(p))
        print("verify: images=%d invalid=%d" % (tot, len(bad)))
        for b in bad[:20]:
            print("  INVALID", b)
        return 1 if bad else 0

    plan = build_plan()
    tasks, stats = [], {}
    for split, (j, sel) in plan.items():
        by_img: dict[int, list] = {}
        for a in j["annotations"]:
            by_img.setdefault(a["image_id"], []).append(a)
        n_ann = sum(len(by_img.get(im["id"], [])) for v in sel.values() for im in v)
        stats[split] = {"images": sum(len(v) for v in sel.values()),
                        "annotations": n_ann,
                        "by_region": {k: len(v) for k, v in sel.items()}}
        for region, imgs in sel.items():
            for im in imgs:
                fn = im["file_name"].replace("\\", "/")
                stem = Path(fn).stem
                ext = Path(fn).suffix.lower()
                tag = "%s__%s" % (region, stem)
                tasks.append({
                    "im": im, "by_img": by_img, "split": split, "tag": tag,
                    "url": "%s/%s" % (HF_BASE, fn),
                    "img_dest": root / "images" / split / (tag + ext),
                })

    print("== 选取计划 ==")
    for split, s in stats.items():
        print("  %-6s images=%-5d annotations=%-6d by_region=%s"
              % (split, s["images"], s["annotations"], s["by_region"]))
    print("  合计 images=%d" % sum(s["images"] for s in stats.values()))
    if args.plan:
        return 0
    if not args.download:
        print("\n（未指定 --download，仅打印计划）")
        return 0

    print("\n== 下载 %d 张图（并行 %d）==" % (len(tasks), args.workers))
    ok = cached = fail = 0
    failures: list[str] = []
    t0 = time.time()

    def work(t):
        good, how = fetch_one(t["url"], t["img_dest"])
        if good:
            write_labels(t["by_img"], t["im"], root, t["split"], t["tag"])
        return good, how, t["tag"]

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, (good, how, tag) in enumerate(ex.map(work, tasks), 1):
            if good:
                cached += how == "cached"
                ok += how != "cached"
            else:
                fail += 1
                failures.append(tag)
            if i % 50 == 0 or i == len(tasks):
                mb = sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) / 1e6
                print("  %d/%d ok=%d cached=%d fail=%d  %.1f MB  %.0fs"
                      % (i, len(tasks), ok, cached, fail, mb, time.time() - t0))

    prov = {
        "schema_version": "1.0",
        "dataset": "SC-FloatWaste (FloatWaste)",
        "hf_id": HF_ID,
        "zenodo_doi": ZENODO_DOI,
        "license": LICENSE,
        "citation": CITATION,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source_annotations_sha256": {
            "instances_val.json": sha256_file(CACHE / "instances_val.json"),
            "instances_train.json": sha256_file(CACHE / "instances_train.json"),
        },
        "selection": stats,
        "selection_rule": (
            "test 全部取自官方 val 划分；train/val 全部取自官方 train 划分"
            "（官方声明两者不相交）。区域内按 file_name 升序确定性取样，无随机种子。"
        ),
        "contract4_mapping": {str(k): v for k, v in CONTRACT4.items()},
        "claim_boundary": (
            "第三方公开数据集，非连江海域、非本项目设备；结果只能表述为"
            "『在公开漂浮垃圾基准独立测试集上的精度』，不得表述为『连江现场验证』"
            "或『本项目设备实测精度』。"
        ),
        "download_result": {"ok": ok, "cached": cached, "failed": fail,
                            "failed_tags": failures[:50]},
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "PROVENANCE.json").write_text(
        json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n== 完成 ==  ok=%d cached=%d failed=%d" % (ok, cached, fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
