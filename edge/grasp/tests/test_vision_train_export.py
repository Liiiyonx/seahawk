"""训练/导出尺寸口径（``grasp/vision/train.py`` 的 ``imgsz_for``）自测。

## 为什么必须测

``config.yaml`` 的 ``vision.input_size`` 是 640，``Detector`` 按它做 letterbox。
原先 ``lan`` 档是按档位表里的 416 **训练并导出 416** —— 于是「在作业台里训练完 →
部署 → 推理」必然 ``cv2.dnn`` 维度不匹配（正是 config 里「训练本来是 768，却导了
416」那条注释警告过的失败类别）。这条口径现在只有一处实现，且必须与 config 一致。

没有 ultralytics 的机器也要能跑：所以被抽成纯函数。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GRASP = HERE.parent
EDGE = GRASP.parent
for _p in (str(EDGE), str(GRASP)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from grasp.vision.train import TIERS, imgsz_for  # noqa: E402


def test_imgsz_follows_config_input_size_for_every_tier() -> None:
    cfg = {"vision": {"input_size": 640}}
    for key in ("local", "lan"):
        assert imgsz_for(cfg, TIERS[key]) == (640, 640), (
            f"{key} 档的训练/导出尺寸必须等于部署输入边长，否则部署链路必然维度不匹配"
        )


def test_imgsz_falls_back_to_tier_when_config_lacks_input_size() -> None:
    """config 没写 input_size 时才退回档位值 —— 这是兜底，不是常态。"""
    assert imgsz_for({}, TIERS["lan"]) == (416, 416)
    assert imgsz_for({}, TIERS["local"]) == (320, 320)


def test_train_and_export_sizes_are_always_identical() -> None:
    """训练与导出两边**必须**返回同一个数：只改一边就会跑出「训练 640 / 导出 416」。"""
    for size in (320, 416, 640, 768):
        train_sz, export_sz = imgsz_for({"vision": {"input_size": size}}, TIERS["lan"])
        assert train_sz == export_sz == size


def test_source_has_no_per_tier_size_branch() -> None:
    """源码守卫：绝不能再出现「按档位分叉尺寸」的写法。

    静态守卫比"跑一遍训练"便宜得多，而且能挡住回归 —— 这类缺陷只在部署后才暴露，
    跑训练的单测成本太高。
    """
    src = (GRASP / "vision" / "train.py").read_text(encoding="utf-8")
    assert 'if tier.key == "local"' not in src, "尺寸又按档位分叉了"
    assert "_export_onnx(model, best_pt, export_imgsz)" in src, "_export_onnx 必须用导出尺寸"
    assert "imgsz=train_imgsz" in src, "训练必须用训练尺寸变量"
    assert "train_imgsz = export_imgsz" in src or "imgsz_for(cfg, tier)" in src, \
        "尺寸必须来自同一次 imgsz_for 调用（两边同源）"
