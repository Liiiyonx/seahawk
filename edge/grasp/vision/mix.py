"""把多个 YOLO 数据集「混」成一份图像清单 + data.yaml（replay 混采）。

## 为什么要能混

实测教训：先拿 TACO 真实照片底料预训练、再只用**合成泳池域**微调，会发生
**灾难性遗忘** —— TACO val 的 mAP50 从 0.397 掉到 0.014，真实域能力基本归零，
底料等于白训。把底料**混进**微调（replay）才是保住真实域特征的标准做法：
实测真实域保到 0.369（test 0.571），而池域几乎不掉。

## 为什么不拷文件也能混

各数据集都遵循 ``images/<split>`` → ``labels/<split>`` 惯例，ultralytics 由图像
路径推导标签路径（把 ``/images/`` 换成 ``/labels/``）。所以只要给它一份**图像
路径清单**，标签就自动对上，无需复制任何图像或标签文件。

## 前提（不满足就报错，不静默产出错位标签）

追加集的类名必须是主集类名的**子集**，否则类索引会整体错位、必须重写标签文件
才能混 —— 那种情况这里明确拒绝，而不是产出一批「标签还算对得上、只是类别错了」
的数据。

## 为什么异常是 MixError 而不是 SystemExit

本模块同时被 CLI（``tools/finetune_pool.py``）与作业台（``web/server.py``）调用。
作业台的后台任务运行器只 ``except Exception``（``web/server.py`` 的
``AppState.start_job._runner``）：``SystemExit`` 继承 ``BaseException``，不会被
捕获 —— 任务会停在 ``starting`` 阶段、``error`` 为空、日志无内容，表现成
「任务看着起了、永远不动、也不说为什么」。所以统一抛 ``MixError(RuntimeError)``，
两边都能正常上报。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("oceanus.grasp.mix")

IMG_SUFFIX = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class MixError(RuntimeError):
    """混采不可行（类名不是子集 / 数据集描述缺失等）。"""


def load_yaml(path: Path) -> dict:
    """读数据集描述（延迟导入 yaml：Pi 侧不在 import 期就依赖它）。"""
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def names_list(raw: dict) -> list[str]:
    """把 ``names`` 归一成按下标排列的类名列表（yaml 里可能是 dict 也可能是 list）。"""
    names = raw.get("names") or []
    if isinstance(names, dict):
        return [str(names[k]) for k in sorted(names, key=lambda x: int(x))]
    return [str(n) for n in names]


def images_of(root: Path, spec: object) -> list[Path]:
    """从 data.yaml 的 train/val 字段取图像列表（目录递归 / 已是 .txt 清单）。"""
    if not spec:
        return []
    p = Path(str(spec))
    if not p.is_absolute():
        p = root / p
    if p.is_dir():
        return sorted(q for q in p.rglob("*") if q.suffix.lower() in IMG_SUFFIX)
    if p.suffix == ".txt" and p.exists():
        return [Path(line.strip()) for line in p.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    return []


def _root_of(yaml_path: Path, raw: dict) -> Path:
    root = Path(str(raw.get("path") or yaml_path.parent))
    return root if root.is_absolute() else (yaml_path.parent / root).resolve()


def mix_datasets(primary: Path, extras: list[Path], out_dir: Path) -> dict[str, Any]:
    """把主集与若干追加集的图并成一份清单 + data.yaml，返回摘要（不拷任何文件）。

    返回 ``{"data_yaml", "train", "val", "extras", "names", "sources"}``；
    ``sources`` 是每个来源的 train 图数，供 CLI 与控制台日志复用同一份数字。
    """
    p_raw = load_yaml(primary)
    p_root = _root_of(primary, p_raw)
    p_names = names_list(p_raw)

    srcs: list[tuple[Path, dict, str]] = [(p_root, p_raw, "primary")]
    extras_desc: list[str] = []
    for extra in extras:
        e_raw = load_yaml(extra)
        e_names = names_list(e_raw)
        missing = [n for n in e_names if n not in p_names]
        if missing:
            raise MixError(
                f"{extra} 含主集没有的类 {missing}（主集 {p_names}）—— 类索引会错位，"
                "必须重写标签；本模块不支持，请先统一类名"
            )
        srcs.append((_root_of(extra, e_raw), e_raw, extra.stem))
        extras_desc.append(str(extra))

    out_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for split in ("train", "val"):
        lines: list[str] = []
        for root, raw, _tag in srcs:
            lines.extend(str(q) for q in images_of(root, raw.get(split)))
        (out_dir / f"{split}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        counts[split] = len(lines)

    names_block = "\n".join(f"  {i}: {n}" for i, n in enumerate(p_names))
    yaml_path = out_dir / "data.yaml"
    yaml_path.write_text(
        "# 由 grasp/vision/mix.py 生成（replay 混采，只写清单不拷文件）\n"
        f"path: {out_dir.as_posix()}\n"
        "train: train.txt\n"
        "val: val.txt\n"
        f"names:\n{names_block}\n",
        encoding="utf-8",
    )
    # 来源标签用**数据集目录名**而不是 yaml 文件名：各家数据集描述文件几乎都叫
    # data.yaml，用它的 stem 当 key 会让两个追加集互相覆盖（"下了两批、只报了一批"）。
    sources = {"primary": len(images_of(p_root, p_raw.get("train")))}
    for root, raw, _tag in srcs[1:]:
        sources[root.name] = len(images_of(root, raw.get("train")))
    logger.info("混采：train=%d val=%d 来源=%s", counts["train"], counts["val"], sources)
    return {"data_yaml": str(yaml_path), "train": counts["train"], "val": counts["val"],
            "extras": extras_desc, "names": p_names, "sources": sources}
