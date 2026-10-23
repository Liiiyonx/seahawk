"""检测评测口径（``grasp/vision/metrics.py``）自测：纯数学，不需要 cv2 / 模型 / ultralytics。

## 为什么必须测

同一批预测在「ultralytics 自带推理」与「部署链路 cv2.dnn + Detector」上会算出不同的
P/R（前后处理不同），但**匹配口径必须共用**。这套 IoU / 贪心匹配被三处同时使用：
CLI 的 ``eval_robustness.py``、``verify_pool_model.py``，以及作业台的部署链路扫描。
它算错一次，三个地方的结论一起错，而且错得"看起来很正常"。
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

from grasp.vision import metrics as M  # noqa: E402


def test_iou_and_threshold_boundary() -> None:
    a = (0.0, 0.0, 10.0, 10.0)
    assert M.iou(a, a) == pytest.approx(1.0)
    assert M.iou(a, (20.0, 20.0, 30.0, 30.0)) == 0.0        # 不相交
    b = (5.0, 0.0, 15.0, 10.0)                              # 一半重叠
    assert M.iou(a, b) == pytest.approx(50.0 / 150.0)
    assert M.iou_at_least(a, b, 0.30) is True
    assert M.iou_at_least(a, b, 0.40) is False
    # 临界：恰好达到门限要算「够」（>= 而不是 >）
    assert M.iou_at_least(a, a, 1.0) is True


def test_match_is_one_to_one_and_greedy() -> None:
    """一个 gt 被多个 pred 争时只算一个 TP，其余进未匹配（=误检）。"""
    gt = [(0.0, 0.0, 10.0, 10.0)]
    preds = [(0.9, (0.0, 0.0, 10.0, 10.0)), (0.8, (0.0, 0.0, 10.0, 10.0))]
    tp, unmatched = M.match(preds, gt, 0.5)
    assert tp == 1
    assert len(unmatched) == 1


def test_match_greedy_order_can_mispair_on_dense_gt() -> None:
    """贪心按 conf 降序：高分框先占坑，与 ultralytics 口径一致（不追求最优指派）。"""
    gt = [(0.0, 0.0, 10.0, 10.0)]
    preds = [(0.5, (0.0, 0.0, 10.0, 10.0)), (0.9, (100.0, 100.0, 110.0, 110.0))]
    tp, unmatched = M.match(preds, gt, 0.5)
    assert tp == 1
    assert unmatched == [1]          # 那个高分框落在别处 → 记为误检


def test_load_yolo_gt_skips_bad_lines(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    # 第 2 行只有 3 个字段、第 3 行是空行 → 都必须跳过，而不是抛异常
    p.write_text("0 0.5 0.5 0.2 0.2\n0 0.1 0.1\n\n1 0.5 0.5 0.1 0.1\n", encoding="utf-8")
    gt = M.load_yolo_gt(p, 100, 50)
    assert sorted(gt) == [0, 1]
    assert len(gt[0]) == 1
    assert gt[0][0] == pytest.approx((40.0, 20.0, 60.0, 30.0))
    assert M.load_yolo_gt(tmp_path / "missing.txt", 10, 10) == {}


def test_scan_rows_counts_and_fp_split() -> None:
    """阈值扫描的指标必须与手算一致，且误检能按「其他类 / 纯背景」分开。"""
    raw = [
        # 帧 1：目标类 1 个真值框；两个检出 —— 0.9 命中目标，0.7 落在别的类物体上
        {"gt": {0: [(0.0, 0.0, 10.0, 10.0)], 1: [(50.0, 50.0, 60.0, 60.0)]},
         "preds": [(0.9, (0.0, 0.0, 10.0, 10.0)), (0.7, (50.0, 50.0, 60.0, 60.0))]},
        # 帧 2：纯背景（无任何真值），1 个检出 0.6
        {"gt": {}, "preds": [(0.6, (5.0, 5.0, 15.0, 15.0))]},
    ]
    rows = {r["conf"]: r for r in M.scan_rows(raw, thresholds=[0.8, 0.5], iou=0.5,
                                              target_idx=0, split_fp_by_other=True)}
    hi = rows[0.8]
    assert (hi["tp"], hi["fp"], hi["fn"]) == (1, 0, 0)
    assert hi["precision"] == pytest.approx(1.0) and hi["recall"] == pytest.approx(1.0)
    assert hi["hit_frames"] == 1

    # 0.5：0.7 与 0.6 两个误检都过阈（注意 0.6 < 0.65，用 0.65 就只剩一个了）
    lo = rows[0.5]
    assert (lo["tp"], lo["fp"], lo["fn"]) == (1, 2, 0)
    assert lo["fp_other"] == 1       # 落在其他类物体上
    assert lo["fp_background"] == 1  # 落在纯背景上
    assert lo["precision"] == pytest.approx(1 / 3, abs=1e-4)   # 行内指标保留 4 位小数
    assert lo["hit_frames"] == 1


def test_scan_rows_without_fp_split_buckets_all_as_background() -> None:
    """``split_fp_by_other=False`` 时全部误检进 fp_background 桶（eval_robustness 的旧口径）。"""
    raw = [{"gt": {1: [(0.0, 0.0, 10.0, 10.0)]},
            "preds": [(0.9, (0.0, 0.0, 10.0, 10.0))]}]
    row = M.scan_rows(raw, thresholds=[0.5], iou=0.5, target_idx=0,
                      split_fp_by_other=False)[0]
    assert row["tp"] == 0 and row["fp"] == 1
    assert row["fp_other"] == 0 and row["fp_background"] == 1
    assert row["fn"] == 0            # 目标类真值为 0 → 没有漏检
