"""replay 混采（``grasp/vision/mix.py``）自测。

## 为什么必须测

混采是把「真实照片底料」保住的那一步（实测：只在合成域微调会把底料能力灾难性
遗忘，TACO val mAP50 0.397 → 0.014）。它有三个容易出错的点，各对应一条断言：

1. **只写清单不拷文件** —— 拷了就等于把第三方数据复制进仓库；
2. **行数必须等于各来源之和** —— 少写一批图会静默少喂数据；
3. **类名不是子集时必须报错** —— 静默混进去会让类索引整体错位（标签"看着对得上、
   其实类别错了"），而且抛的必须是普通异常而非 ``SystemExit``：作业台的后台运行器
   只 ``except Exception``，``SystemExit`` 会让任务停在 starting 且不报错。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
GRASP = HERE.parent
EDGE = GRASP.parent
for _p in (str(EDGE), str(GRASP)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from grasp.vision import mix as mixmod  # noqa: E402


def _dataset(root: Path, names: list[str], train: int, val: int) -> Path:
    """造一个最小 YOLO 数据集（只要目录 + 图 + data.yaml，标签内容与本模块无关）。"""
    for split, n in (("train", train), ("val", val)):
        d = root / "images" / split
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            (d / f"{split}_{i:03d}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    names_block = "\n".join(f"  {i}: {n}" for i, n in enumerate(names))
    yaml_path = root / "data.yaml"
    yaml_path.write_text(
        f"path: {root.as_posix()}\ntrain: images/train\nval: images/val\n"
        f"names:\n{names_block}\n", encoding="utf-8")
    return yaml_path


def test_mix_writes_only_lists_never_copies(tmp_path: Path) -> None:
    primary = _dataset(tmp_path / "primary", ["plastic_bag", "buoy"], 5, 2)
    extra = _dataset(tmp_path / "extra", ["plastic_bag"], 3, 1)
    out = tmp_path / "mixed"

    summary = mixmod.mix_datasets(primary, [extra], out)

    # ① 只写清单：输出目录里除 txt/yaml 外不得有任何图像或标签文件
    stray = [p for p in out.rglob("*") if p.is_file()
             and p.suffix.lower() not in (".txt", ".yaml", ".yml")]
    assert stray == [], f"混采不该拷贝文件，却发现：{stray}"
    assert sorted(p.name for p in out.iterdir()) == ["data.yaml", "train.txt", "val.txt"]

    # ② 行数 = 两集之和（少一批就静默少喂数据）
    train_lines = [x for x in (out / "train.txt").read_text(encoding="utf-8").splitlines() if x]
    val_lines = [x for x in (out / "val.txt").read_text(encoding="utf-8").splitlines() if x]
    assert len(train_lines) == 5 + 3
    assert len(val_lines) == 2 + 1
    assert summary["train"] == 8 and summary["val"] == 3
    assert summary["names"] == ["plastic_bag", "buoy"]     # 类名取主集的
    # 来源标签用数据集目录名（data.yaml 这个名字会撞车），值必须是各来源的图数
    assert summary["sources"]["primary"] == 5
    assert list(summary["sources"].values())[1] == 3
    # 清单里必须是**图像**路径（ultralytics 会据此把 images 段换成 labels 段；
    # Windows 下 Path 用反斜杠，ultralytics 用 os.sep 匹配，两种都对）
    assert all("/images/" in line or "\\images\\" in line for line in train_lines)


def test_mix_rejects_superset_class_names_with_plain_exception(tmp_path: Path) -> None:
    primary = _dataset(tmp_path / "primary", ["plastic_bag"], 5, 2)
    # 追加集多了一个主集没有的类 → 类索引会错位，必须拒绝
    extra = _dataset(tmp_path / "extra", ["plastic_bag", "foam"], 3, 1)
    with pytest.raises(mixmod.MixError) as exc:
        mixmod.mix_datasets(primary, [extra], tmp_path / "mixed")
    assert isinstance(exc.value, RuntimeError)      # 普通异常（不是 SystemExit）
    assert "foam" in str(exc.value)


def test_mix_error_is_not_systemexit(tmp_path: Path) -> None:
    """显式钉住：绝不能是 SystemExit。

    作业台后台任务的运行器只 ``except Exception``（``web/server.py`` 的
    ``start_job._runner``），``SystemExit`` 继承 ``BaseException`` 抓不到 ——
    表现是「任务看着起了、永远不动、也不说为什么」。这条断言把那个缺陷钉死。
    """
    primary = _dataset(tmp_path / "primary", ["plastic_bag"], 5, 2)
    extra = _dataset(tmp_path / "extra", ["foam"], 3, 1)
    try:
        mixmod.mix_datasets(primary, [extra], tmp_path / "mixed")
    except BaseException as exc:  # noqa: BLE001
        assert not isinstance(exc, SystemExit), "混采失败抛了 SystemExit，作业台会上报不出来"
        assert isinstance(exc, mixmod.MixError)
    else:
        pytest.fail("类名不是子集却没报错")


def test_images_of_accepts_dir_and_txt_list(tmp_path: Path) -> None:
    """两种 spec 都要支持：目录（本仓数据集的样子）与 .txt 清单（混采产物的样子）。"""
    root = tmp_path / "ds"
    d = root / "images" / "train"
    d.mkdir(parents=True)
    for i in range(2):
        (d / f"a{i}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    assert len(mixmod.images_of(root, "images/train")) == 2

    txt = root / "list.txt"
    txt.write_text(f"{d / 'a0.jpg'}\n\n{d / 'a1.jpg'}\n", encoding="utf-8")
    assert len(mixmod.images_of(root, "list.txt")) == 2
    assert mixmod.images_of(root, None) == []
    assert mixmod.images_of(root, "nope") == []


def test_names_list_normalizes_dict_and_list() -> None:
    assert mixmod.names_list({"names": {1: "b", 0: "a"}}) == ["a", "b"]
    assert mixmod.names_list({"names": ["a", "b"]}) == ["a", "b"]
    assert mixmod.names_list({}) == []
