#!/usr/bin/env python3
"""构建单类「塑料袋」数据集：从 TACO（Trash Annotations in Context）抽取。

## 为什么选 TACO 作底料（而不是又一个航拍海面集）

我们的目标是**机械臂贴水面 8~20cm 的第一人称视角**。公开集里视角最接近的是
CANSURF（ASV 船载近水面），但它只有铝罐；其余全是航拍/3m 高俯拍 —— 视角差距
正是本项目已经踩过的坑（公开岸基俯拍数据保不住机械臂视角精度）。

TACO 的价值不在"水面"，而在：
  1. 它的 ``Plastic bag & wrapper`` 是**全库最大类**（含 Garbage bag /
     Single-use carrier bag / Plastic Film 等子类），塑料袋形态覆盖最全；
  2. 它带**场景标签**（含 ``Water``），可以据此只取水面附近的样本；
  3. 标注是**实例分割**（有 segmentation），对"机器人抓取"这类形状敏感任务是加分项；
  4. 许可 CC BY 4.0（标注），图像逐张带原始许可。

## 与 build_plastic_dataset.py 的关系

那份构建器处理的是 SC-FloatWaste（**官方有 train/val/test 划分**，必须沿用）。
TACO **没有官方划分**，所以这里按 `file_name` 的稳定哈希做**确定性**切分，
并把这个事实写进 PROVENANCE —— 因此它产出的 test 集**不能当公开基准引用**，
只能当"预训练/微调底料"。

> ⚠️ 口径边界：TACO 是第三方公开数据、非本项目设备、非现场。基于它训练出来的
> 指标只能表述为「公开数据集上的精度」，禁止写成「现场验证精度」。

## 获取原始数据（本机当前离线，这两步需要网络）

★ 推荐用配套的 ``fetch_taco_images.py``，它会**只下含袋框的图**（实测 522/1500 张，
约 70MB 而不是全量原图 1.6GB），且带回退、重试与断点续传::

    curl -L -o <src>/annotations.json \
      https://raw.githubusercontent.com/pedropro/TACO/master/data/annotations.json
    python edge/grasp/tools/fetch_taco_images.py --src <src>
    python edge/grasp/tools/build_taco_plastic.py --src <src>

手工获取亦可，解到 ``--src`` 目录，使其形如::

    <src>/annotations.json          # COCO 格式标注
    <src>/data/batch_1/*.jpg        # 图像（TACO 按 batch_* 分目录）

  * 官方仓库：https://github.com/pedropro/TACO  （annotations 随仓库；图像需按其说明取得，
    仓库自带的 ``download.py`` 会下**全部 1500 张原图**）
  * Kaggle 镜像：`kaggle datasets download -d sohamchaudhari2004/taco-trash-detection-dataset`

★ 拿到真实 ``annotations.json`` 后先跑一次 ``--report``：它会打印类别/超类名
与场景标签的实际取值，据此再用 ``--bag-keys`` / ``--exclude-keys`` / ``--scene``
收紧匹配（不同镜像的类别命名不一致，别硬编码）。
★ 实测官方 ``annotations.json`` 里**没有** scene 字段（1500 张全无），
所以 ``--scene water`` 不生效 —— 本脚本会检测到并如实降级为"不过滤"并在
PROVENANCE 里记 null，不会写成"已按水面筛选"。

用法::

    python edge/grasp/tools/build_taco_plastic.py --src <taco_raw> --report
    python edge/grasp/tools/build_taco_plastic.py --src <taco_raw>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRASP_DIR = HERE.parent
REPO_ROOT = GRASP_DIR.parent.parent
DEFAULT_OUT = GRASP_DIR / "data" / "public_taco_plastic"

TARGET_CLASS_NAME = "plastic_bag"
#: 默认的「袋子」匹配关键词（对 **supercategory 与 category name 都做小写包含匹配**）。
#: TACO 的 supercategory 是 "Plastic bag & wrapper"；不同镜像可能写成
#: "plastic_bag_wrapper" / "PlasticBag" 等，所以用关键词而不是精确串。
DEFAULT_BAG_KEYS = ("bag", "wrapper", "film")
#: ★ 必须排除的关键词。光靠 ``bag`` 关键词会**误收纸袋**：TACO 里
#: "Paper bag"（27 框）/ "Plastified paper bag" 的 supercategory 字面就含 "bag"。
#: 把纸袋标成 ``plastic_bag`` 是**错的标签** —— 会让模型去抓纸袋，而演示目标是
#: 白色半透明塑料袋。所以默认排掉 paper。
DEFAULT_EXCLUDE_KEYS = ("paper",)
#: 默认的场景过滤值（TACO 的 scene 标签含 Water）；空=不做场景过滤。
DEFAULT_SCENE = "water"
#: 确定性切分：按 file_name 哈希取模。没有官方划分的集只能用这种办法，
#: 好处是可复现、且同一张图永远落同一边。
SPLIT_RATIOS = (("train", 0.8), ("val", 0.1), ("test", 0.1))


def match_bag_categories(cats: dict, keys: tuple[str, ...],
                         exclude_keys: tuple[str, ...] = ()) -> set[int]:
    """按关键词匹配袋类 category_id。

    ★ 本函数是**唯一**的匹配口径：``fetch_taco_images.py`` 也导入它来挑要下载的图，
    两处若不共用同一套规则，就会「下了一批图、却建出另一批标注」这种最难查的错位。
    排除项优先于命中项（"paper bag" 同时含 bag 与 paper → 排除）。
    """
    out: set[int] = set()
    for cid, c in cats.items():
        text = " ".join(str(c.get(k, "")) for k in ("name", "supercategory")).lower()
        if any(k in text for k in exclude_keys):
            continue
        if any(k in text for k in keys):
            out.add(cid)
    return out


def _split_of(file_name: str) -> str:
    h = int(hashlib.sha1(file_name.encode("utf-8")).hexdigest()[:8], 16)
    r = (h % 1000) / 1000.0
    acc = 0.0
    for name, ratio in SPLIT_RATIOS:
        acc += ratio
        if r < acc:
            return name
    return SPLIT_RATIOS[-1][0]


def _link_or_copy(src: Path, dst: Path) -> str:
    if dst.exists():
        return "exists"
    try:
        os.link(src, dst)
        return "link"
    except OSError:
        shutil.copy2(src, dst)
        return "copy"


def _load(src: Path) -> dict:
    path = src / "annotations.json"
    if not path.exists():
        raise SystemExit(
            f"找不到 {path}。TACO 的标注是 annotations.json（COCO 格式），"
            "见本文件顶部「获取原始数据」。"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _scene_of(image: dict) -> str | None:
    """尽量取场景标签：不同镜像把它放在不同键上，逐个试。"""
    for key in ("scene", "background", "scenes", "scene_tag", "environment"):
        v = image.get(key)
        if isinstance(v, str):
            return v.lower()
        if isinstance(v, (list, tuple)) and v:
            return " ".join(str(x).lower() for x in v)
    return None


def report(raw: dict) -> None:
    cats = {c["id"]: c for c in raw.get("categories", [])}
    print(f"图像 {len(raw.get('images', []))} 张 · 标注 {len(raw.get('annotations', []))} 条")
    print("\n[类别 → 超类] 标注数")
    per = Counter(a["category_id"] for a in raw.get("annotations", []))
    for cid, c in sorted(cats.items(), key=lambda kv: -per.get(kv[0], 0)):
        print("  %-28s → %-28s %d" % (c.get("name"), c.get("supercategory"), per.get(cid, 0)))
    scenes = Counter(_scene_of(i) or "<无 scene 字段>" for i in raw.get("images", []))
    print("\n[场景标签] 图像数")
    for s, n in scenes.most_common(20):
        print("  %-32s %d" % (s, n))
    print("\n提示：若你的镜像里袋类的超类名不含 bag/wrapper/film，"
          "用 --bag-keys 补关键词；若场景标签键不同，改 _scene_of()。")


def build(src: Path, out: Path, bag_keys: tuple[str, ...], scene: str,
          keep_background: bool, exclude_keys: tuple[str, ...] = ()) -> dict:
    raw = _load(src)
    cats = {c["id"]: c for c in raw.get("categories", [])}

    bag_cids = match_bag_categories(cats, bag_keys, exclude_keys)
    if not bag_cids:
        raise SystemExit(
            f"没有匹配到任何袋类（关键词 {bag_keys}，排除 {exclude_keys}）。"
            "先跑 --report 看实际类别名。"
        )
    kept = sorted({cats[c]["name"] for c in bag_cids})
    dropped = sorted({f'{c["name"]}(含排除词)' for cid, c in cats.items()
                      if cid not in bag_cids and any(k in " ".join(
                          str(c.get(kk, "")) for kk in ("name", "supercategory")).lower()
                          for k in exclude_keys) and any(k in " ".join(
                          str(c.get(kk, "")) for kk in ("name", "supercategory")).lower()
                          for k in bag_keys)})
    print(f"[类别] 命中 {len(bag_cids)} 类：{kept}")
    if dropped:
        print(f"[类别] 因排除词丢弃：{dropped}")

    img_by_id = {i["id"]: i for i in raw.get("images", [])}
    boxes_by_img: dict[int, list] = {}
    for a in raw.get("annotations", []):
        if a.get("category_id") in bag_cids and not a.get("iscrowd"):
            bbox = a.get("bbox")
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                boxes_by_img.setdefault(a["image_id"], []).append(bbox)

    stats: dict[str, dict] = {}
    total = Counter()
    # ★ 先清掉上一次的 images/labels，让重建是幂等的：不清的话，`_link_or_copy`
    #   会对已存在的目标直接返回 "exists" 并跳过 —— 改名重跑时结果会与旧残留
    #   叠加，"看着多了一批、其实一半是上次的旧文件"。
    for sub in ("images", "labels"):
        old = out / sub
        if old.exists():
            shutil.rmtree(old)
    for split, _ in SPLIT_RATIOS:
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)

    modes: Counter = Counter()
    # ★ 场景过滤的诚实性护栏：官方 TACO ``annotations.json`` 里**没有** scene /
    #   background 字段（实测 1500 张全都没有）。此时 ``--scene water`` 不会筛掉
    #   任何一张图，但 PROVENANCE 照样会写下 scene_filter="water" —— 等于把一件
    #   没发生过的事记成发生过，后来的人会以为这批数据"只剩水面样本"。
    #   实测发现就如实降级为"不过滤"并明说，别让它变成静默的假陈述。
    n_with_scene = sum(1 for i in img_by_id.values() if _scene_of(i) is not None)
    scene_effective = scene
    if scene and n_with_scene == 0:
        print(f"[场景] ⚠ 标注文件里没有任何场景字段（{len(img_by_id)} 张图都没有）——"
              f"--scene {scene!r} 实际不生效。已按「不过滤」处理，PROVENANCE 记为 null。")
        scene_effective = ""
    elif scene:
        print(f"[场景] 有场景字段的图 {n_with_scene}/{len(img_by_id)} 张，"
              f"按 {scene!r} 过滤。")

    for iid, boxes in boxes_by_img.items():
        img = img_by_id.get(iid)
        if img is None:
            continue
        s = _scene_of(img)
        if scene_effective and s is not None and scene_effective not in s:
            continue                      # 有场景标签且不匹配 → 跳过
        fname = str(img.get("file_name") or "")
        rel = Path(fname)
        src_img = src / "data" / rel
        if not src_img.exists():
            src_img = src / rel            # 兼容平铺目录
        if not src_img.exists():
            total["missing_images"] += 1
            continue
        w, h = float(img.get("width") or 0), float(img.get("height") or 0)
        if w <= 0 or h <= 0:
            total["bad_size"] += 1
            continue
        split = _split_of(fname)
        rows: list[str] = []
        for (bx, by, bw, bh) in boxes:
            cx, cy = (bx + bw / 2) / w, (by + bh / 2) / h
            rows.append("0 %.6f %.6f %.6f %.6f" % (cx, cy, bw / w, bh / h))
        # ★ 输出名必须**带上 TACO 的 batch 目录前缀**：TACO 的图像名在各 batch 之间
        #   完全重复（batch_1/000006.jpg 与 batch_11/000006.jpg…），只取 basename
        #   平铺到同一个目录会**静默互相覆盖**（实测 522 张只落了 235 张，而 stats
        #   仍报 522 —— 报数与磁盘不一致，是最坏的那种"看起来成功"）。
        #   与 arm 管线 Dataset.built_stem() 用「会话名_原名」消歧是同一个教训。
        out_stem = f"{rel.parent.name}_{src_img.stem}" if rel.parent.name else src_img.stem
        stats.setdefault(split, {"images": 0, "boxes": 0})
        stats[split]["images"] += 1
        stats[split]["boxes"] += len(rows)
        total["images"] += 1
        total["boxes"] += len(rows)
        modes[_link_or_copy(src_img, out / "images" / split / f"{out_stem}{src_img.suffix}")] += 1
        (out / "labels" / split / f"{out_stem}.txt").write_text(
            "\n".join(rows) + "\n", encoding="utf-8"
        )

    # 落盘自检：出现 "exists" 就说明有重名（同一输出名被写了两次 → 有图被覆盖丢了）。
    # 宁可直接失败，也不要交出一份"统计数字比磁盘文件多"的数据集。
    if modes.get("exists"):
        raise SystemExit(
            f"有 {modes['exists']} 个输出文件名冲突（同一名字被写两次），图像会静默覆盖。"
            "检查 file_name 是否只有 basename、或不同 batch 是否重名。"
        )
    if total["images"] == 0:
        raise SystemExit(
            "没有可导出的图像。常见原因：①图像没解到 <src>/data/ 下；"
            "②--scene 过滤太严（先 --report 看场景标签实际取值）。"
        )

    (out / "data.yaml").write_text(
        "# 由 edge/grasp/tools/build_taco_plastic.py 生成，请勿手工编辑\n"
        "# 来源：TACO (Trash Annotations in Context)，标注 CC BY 4.0\n"
        "# 类别：单类 plastic_bag（由 TACO 的 bag/wrapper/film 类合并重映射）\n"
        f"path: {out.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n  0: plastic_bag\n",
        encoding="utf-8",
    )

    prov = {
        "schema_version": "1.0",
        "built_by": "edge/grasp/tools/build_taco_plastic.py",
        "source_dataset": "TACO (Trash Annotations in Context)",
        "source_dir": str(src),
        "homepage": "http://tacodataset.org/",
        "repo": "https://github.com/pedropro/TACO",
        "paper": "arXiv:2003.06975",
        "license": "标注 CC BY 4.0；图像逐张带原始许可（见 TACO 标注内 licence 字段）",
        "label_space": {"output_classes": [TARGET_CLASS_NAME],
                        "bag_match_keys": list(bag_keys),
                        "exclude_keys": list(exclude_keys),
                        "matched_category_ids": sorted(bag_cids)},
        "scene_filter": scene_effective or None,
        "scene_applied": bool(scene_effective),
        "scene_info_images": n_with_scene,
        "split_policy": ("TACO 无官方划分 → 按 file_name 稳定哈希确定性切分 "
                         "train/val/test = 80/10/10；因此其 test 集不得当公开基准引用"),
        "background_policy": ("只保留含袋框的图；其余类别的框一律去除，"
                              "使其成为未标注背景负样本"),
        "stats": stats,
        "totals": dict(total),
        "claim_boundary": ("第三方公开数据、非本项目设备、非现场。基于它训练的指标"
                           "只能表述为「公开数据集上的精度」，禁止写成「现场验证精度」。"),
        "role": "预训练底料（不是最终交付模型的数据来源）",
    }
    (out / "PROVENANCE.json").write_text(
        json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return prov


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="从 TACO 构建单类塑料袋预训练集")
    ap.add_argument("--src", required=True, help="TACO 原始目录（含 annotations.json 与 data/）")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--bag-keys", default=",".join(DEFAULT_BAG_KEYS),
                    help="袋类匹配关键词（逗号分隔，对 supercategory 与 name 小写包含匹配）")
    ap.add_argument("--exclude-keys", default=",".join(DEFAULT_EXCLUDE_KEYS),
                    help="排除关键词（逗号分隔）；默认 paper —— 纸袋的 supercategory "
                         "字面含 bag，会被误当塑料袋")
    ap.add_argument("--scene", default=DEFAULT_SCENE,
                    help="场景过滤（默认 water；传空串=不过滤）")
    ap.add_argument("--report", action="store_true", help="只打印类别与场景统计，不建库")
    args = ap.parse_args(argv)

    src = Path(args.src)
    if args.report:
        report(_load(src))
        return 0

    keys = tuple(k.strip().lower() for k in args.bag_keys.split(",") if k.strip())
    exclude = tuple(k.strip().lower() for k in args.exclude_keys.split(",") if k.strip())
    prov = build(src, Path(args.out), keys, args.scene.strip().lower(),
                 keep_background=True, exclude_keys=exclude)
    print(json.dumps({"stats": prov["stats"], "totals": prov["totals"]},
                     ensure_ascii=False, indent=2))
    print(f"[完成] {args.out}")
    print(f"[清单] {Path(args.out) / 'data.yaml'} · {Path(args.out) / 'PROVENANCE.json'}")
    print("[提醒] 还要按 ml/datasets/manifests/README.md 补一份 manifests_public/ 清单。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
