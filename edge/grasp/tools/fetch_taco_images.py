#!/usr/bin/env python3
"""按标注挑图并下载 TACO 图像 —— 只下含目标类的那些图。

## 为什么需要它

TACO 的 GitHub 仓库里**没有图像**：只有 ``data/annotations.json`` 与一份 URL 表，
图像要按每张图的 ``flickr_640_url`` 逐张从 Flickr 取。仓库自带的 ``download.py``
会把**全部 1500 张原图**拉下来（约 1.6GB），而建「单类塑料袋」集只需要含袋框的
那批（实测 **539 张**）。这里就只下这批，并且默认取 640 版（部署输入本来就是
640，量级约 70MB）。

## 与 build_taco_plastic.py 的口径关系（重要）

挑图用的类别匹配**直接导入** ``build_taco_plastic.match_bag_categories``，
不另写一套。两处各写一套的结果是「下了一批图、却建出另一批标注」——这种错位
在两边都自洽、只有对不上时才暴露，最难查。

同理，默认排除 ``paper``（纸袋的 supercategory 字面含 "bag"，会被误当塑料袋）。

## 分辨率与标注是否对得上

标注里的 bbox 是按**原图** width/height 归一化后存的，而 Flickr 的 640 版是按
比例缩放的，归一化坐标不变，所以下 640 版不影响标注正确性（本工具下载后由
``build_taco_plastic.py`` 用**标注里的 w/h** 换算，与下载分辨率无关）。

用法::

    python edge/grasp/tools/fetch_taco_images.py --src D:\seahawk-work\taco
    python edge/grasp/tools/fetch_taco_images.py --src ... --limit 20     # 先试跑
    python edge/grasp/tools/fetch_taco_images.py --src ... --original    # 下原图（大）

★ 断点续传：已存在且是合法 JPEG 的文件直接跳过，中断后再跑一次即可接着下。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRASP_DIR = HERE.parent
for _p in (str(HERE), str(GRASP_DIR), str(GRASP_DIR.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from build_taco_plastic import (  # noqa: E402
    DEFAULT_BAG_KEYS,
    DEFAULT_EXCLUDE_KEYS,
    match_bag_categories,
)

JPEG_MAGIC = b"\xff\xd8\xff"
UA = "oceanus-taco-fetch/1.0 (research; contact: project owner)"


def _is_valid_jpeg(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(3) == JPEG_MAGIC
    except OSError:
        return False


def _fetch_one(url: str, dest: Path, timeout: float, retries: int) -> str:
    """下到 ``dest.tmp`` 再原子改名 —— 中断不会留下半截文件被误当已下载。"""
    if dest.exists() and _is_valid_jpeg(dest):
        return "skip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    last = ""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if not data.startswith(JPEG_MAGIC):
                last = f"非 JPEG 响应（{len(data)}B，可能是错误页）"
                continue
            tmp.write_bytes(data)
            tmp.replace(dest)
            return "ok"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    return f"fail: {last}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="只下载含袋框的 TACO 图像")
    ap.add_argument("--src", required=True, help="TACO 目录（含 annotations.json）")
    ap.add_argument("--limit", type=int, default=0, help="只下前 N 张（0=全部）")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=30.0, help="单张超时（s）")
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--original", action="store_true",
                    help="下原图（flickr_url，量大）；默认下 640 版")
    ap.add_argument("--bag-keys", default=",".join(DEFAULT_BAG_KEYS))
    ap.add_argument("--exclude-keys", default=",".join(DEFAULT_EXCLUDE_KEYS))
    args = ap.parse_args(argv)

    src = Path(args.src)
    ann = src / "annotations.json"
    if not ann.exists():
        print(f"[错误] 找不到 {ann}（见 build_taco_plastic.py 头部「获取原始数据」）")
        return 2
    raw = json.loads(ann.read_text(encoding="utf-8"))
    cats = {c["id"]: c for c in raw.get("categories", [])}
    keys = tuple(k.strip().lower() for k in args.bag_keys.split(",") if k.strip())
    exclude = tuple(k.strip().lower() for k in args.exclude_keys.split(",") if k.strip())
    bag_cids = match_bag_categories(cats, keys, exclude)
    if not bag_cids:
        print(f"[错误] 没匹配到袋类（keys={keys} exclude={exclude}）：先跑 --report")
        return 2

    img_by_id = {i["id"]: i for i in raw.get("images", [])}
    need_ids = {a["image_id"] for a in raw.get("annotations", [])
                if a.get("category_id") in bag_cids and not a.get("iscrowd")}
    url_key = "flickr_url" if args.original else "flickr_640_url"
    # ★ 需要回退：实测 522 张含袋图里有 **176 张没有 flickr_640_url**（它们指向
    #   另一个 S3 桶上的原图，不是 Flickr）。若只认 640 URL，这 176 张会被静默
    #   跳过 —— 直接少掉三分之一的底料。所以按优先级逐个试，取第一个非空的。
    order = [url_key] + [k for k in ("flickr_640_url", "flickr_url", "coco_url") if k != url_key]

    def _pick_url(img: dict) -> tuple[str, str]:
        for k in order:
            u = str(img.get(k) or "").strip()
            if u:
                return u, k
        return "", ""

    picked = [(img_by_id[i], *_pick_url(img_by_id[i]))
              for i in sorted(need_ids) if i in img_by_id]
    targets = [(i, u) for i, u, _k in picked if u]
    if args.limit:
        targets = targets[: args.limit]

    have = sum(1 for i, _ in targets
               if _is_valid_jpeg(src / "data" / str(i.get("file_name") or "")))
    n_fallback = sum(1 for _i, _u, k in picked if k and k != url_key)
    print(f"[目标] 含袋框的图 {len(need_ids)} 张 · 待下载 {len(targets)} 张 · "
          f"本地已有 {have} 张 · 首选源={url_key} · 回退到其他源 {n_fallback} 张")

    ok = skipped = 0
    failures: list[str] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = {}
        for img, url in targets:
            dest = src / "data" / str(img.get("file_name") or "")
            if not str(img.get("file_name") or ""):
                continue
            futs[pool.submit(_fetch_one, url, dest, args.timeout, args.retries)] = dest
        for n, fut in enumerate(as_completed(futs), 1):
            dest = futs[fut]
            res = fut.result()
            if res == "ok":
                ok += 1
            elif res == "skip":
                skipped += 1
            else:
                failures.append(f"{dest.name}: {res}")
            if n % 25 == 0 or n == len(futs):
                print(f"  进度 {n}/{len(futs)}  新下 {ok} 跳过 {skipped} "
                      f"失败 {len(failures)}  用时 {time.time() - t0:.0f}s", end="\r", flush=True)

    print(f"\n[完成] 新下 {ok} · 跳过（已存在）{skipped} · 失败 {len(failures)}"
          f" · 用时 {time.time() - t0:.0f}s")
    if failures:
        print(f"[失败明细] 前 10 条：")
        for line in failures[:10]:
            print("   ", line)
        print("  ★ 断点续传：直接重跑本命令即可，已成功的会跳过。")
    print(f"[下一步] python edge/grasp/tools/build_taco_plastic.py --src {src}")
    return 0 if not failures or ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
