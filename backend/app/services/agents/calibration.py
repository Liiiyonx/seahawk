"""决策置信度校准 —— 让「声明的置信度」对齐「实际成功率」。

## 这个模块解决什么问题

`lessons.py` 的经验置信度过去是「基准值 + 固定步长 × 计数」的线性递增
启发式，它有一个诚实的缺陷：**只会涨，不会跌**。一条经验哪怕每次被
引用后 run 都失败，置信度依然单调上升，「说 0.85」并不等于「引用后
85% 会成功」。

决策模型（System One）路线的核心主张是**校准的置信度**：模型说 80%，
就应当在长期统计上真的约 80% 正确，软件才能据此分流 —— 高置信自动
执行、低置信转人工。本模块把这套主张用**确定性数学**落到规则模式上，
提供四个原语（全部纯标准库、可离线复现，不依赖模型与随机性）：

1. `bayesian_confidence` —— Beta 后验均值：把「先验基准 + 引用后真实
   结果」平滑成一个置信度，成功升、失败降；
2. `expected_calibration_error` / `reliability_buckets` —— 衡量声明
   置信度与实际成功率的偏差（ECE 越低越可信），分桶数据可直接画
   可靠性曲线；
3. `fit_temperature` —— 温度缩放：在累积观测后对整条置信度标尺做
   全局软化/硬化（确定性网格搜索，非梯度迭代）；
4. `IsotonicCalibrator` —— 保序回归（PAVA）：非参数的单调校准映射，
   不假设任何函数形式。

## 诚实边界

- 同样的输入永远得到同样的输出；本模块不引入任何随机源。
- 校准的有效性取决于观测样本量：样本少时后验以先验为主。这不是
  缺陷，是刻意保守 —— 宁可不信，不可虚报。
- 温度缩放与保序回归需要「置信度-结果」观测对；在 `LessonStore`
  里这份数据自 run 终态结算（`LessonStore.settle`）起累积，样本
  不足时 `calibration_report` 会显式返回 `ece=None` 而不是硬给数字。
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

# 观测的类型：`(声明置信度, 结果是否为正)`。置信度取值 [0,1]，结果为布尔。
Observation = tuple[float, bool]

# 数值边界：logit 在 p=0/1 处发散，统一裁剪到这个开区间内再计算
_EPS = 1e-6


def bayesian_confidence(
    prior: float,
    successes: int,
    trials: int,
    prior_strength: float = 4.0,
) -> float:
    """Beta 后验均值：`(α·prior + successes) / (α + trials)`。

    把 `prior` 视为先验成功率、`prior_strength` 视为先验等效样本数，
    观测是 `successes / trials`（引用该经验后的真实结果）。无观测时
    恒等于先验；成功使置信度上升、失败使它下降 —— 这是与「只增不减
    的计数递增」的本质区别。

    参数约束：`trials >= successes >= 0`、`prior ∈ [0,1]`、
    `prior_strength > 0`，违反即 ValueError（静默纠正会掩盖调用方 bug）。
    """
    if not 0.0 <= prior <= 1.0:
        raise ValueError(f"prior 必须在 [0,1]：{prior}")
    if prior_strength <= 0:
        raise ValueError(f"prior_strength 必须为正：{prior_strength}")
    if successes < 0 or trials < successes:
        raise ValueError(f"非法观测计数：successes={successes}, trials={trials}")
    return (prior_strength * prior + successes) / (prior_strength + trials)


def _clip_probability(value: float) -> float:
    """把概率裁剪进开区间 (0,1)，避免 logit 发散。"""
    return min(1.0 - _EPS, max(_EPS, float(value)))


def reliability_buckets(
    observations: Sequence[Observation],
    n_bins: int = 10,
) -> list[dict[str, float | int | str]]:
    """把观测按声明置信度分桶，产出可靠性曲线数据。

    每桶返回 `{range, count, avg_confidence, success_rate}`；空桶不返回
    （画曲线时直接跳过，不伪造 0）。`confidence=1.0` 归入最后一桶。
    """
    if n_bins < 1:
        raise ValueError(f"n_bins 必须为正：{n_bins}")
    buckets: list[list[Observation]] = [[] for _ in range(n_bins)]
    for confidence, ok in observations:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"置信度必须在 [0,1]：{confidence}")
        index = min(n_bins - 1, int(confidence * n_bins))
        buckets[index].append((confidence, ok))
    report: list[dict[str, float | int | str]] = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        count = len(bucket)
        avg_conf = sum(item[0] for item in bucket) / count
        success_rate = sum(1.0 for _, ok in bucket if ok) / count
        low = index / n_bins
        high = (index + 1) / n_bins
        report.append(
            {
                "range": f"{low:.1f}-{high:.1f}",
                "count": count,
                "avg_confidence": round(avg_conf, 4),
                "success_rate": round(success_rate, 4),
            }
        )
    return report


def expected_calibration_error(
    observations: Sequence[Observation],
    n_bins: int = 10,
) -> float:
    """期望校准误差（ECE）：`Σ (n_b/N)·|acc_b − conf_b|`。

    完美校准时为 0；声明置信度系统性偏离实际成功率时增大。空观测
    返回 0.0（无声明即无偏差 —— 调用方应先用样本量判断要不要信这个数）。
    """
    total = len(observations)
    if total == 0:
        return 0.0
    buckets = reliability_buckets(observations, n_bins=n_bins)
    ece = 0.0
    for bucket in buckets:
        weight = int(bucket["count"]) / total
        ece += weight * abs(
            float(bucket["success_rate"]) - float(bucket["avg_confidence"])
        )
    return ece


def _nll(observations: Sequence[Observation], temperature: float) -> float:
    """给定温度的平均负对数似然（二分类、单概率声明）。"""
    total = 0.0
    for confidence, ok in observations:
        clipped = _clip_probability(confidence)
        logit = math.log(clipped / (1.0 - clipped))
        calibrated = 1.0 / (1.0 + math.exp(-logit / temperature))
        p = _clip_probability(calibrated if ok else 1.0 - calibrated)
        total -= math.log(p)
    return total / len(observations)


def fit_temperature(
    observations: Sequence[Observation],
    *,
    t_min: float = 0.05,
    t_max: float = 20.0,
) -> float:
    """温度缩放：搜索让 NLL 最小的温度 T（确定性两层网格）。

    `T > 1` 软化（系统性过度自信时压低声明），`T < 1` 硬化（欠自信时
    抬高声明），`T = 1` 保持原标尺。搜索本身不依赖初值与迭代顺序，
    同样的观测永远返回同一个 T。观测不足 2 条时返回 1.0（无可校准）。
    """
    if len(observations) < 2:
        return 1.0
    # 第一层：对数均匀粗网格
    coarse: list[float] = [
        math.exp(math.log(t_min) + (math.log(t_max) - math.log(t_min)) * i / 60)
        for i in range(61)
    ]
    best = min(coarse, key=lambda t: (_nll(observations, t), t))
    # 第二层：最优点邻域细化（步长为粗网格间距的 1/10）
    step = best * (math.exp((math.log(t_max) - math.log(t_min)) / 60) - 1.0) / 10.0
    fine = [max(t_min, min(t_max, best + (i - 10) * step)) for i in range(21)]
    return min(fine, key=lambda t: (_nll(observations, t), t))


class IsotonicCalibrator:
    """保序回归校准器（PAVA，纯标准库实现）。

    拟合一个单调非降的映射 `声明置信度 → 校准成功率`。与温度缩放的
    区别：不假设任何函数形式，只要求「更高的声明不该对应更低的实际
    成功率」这一条常识。观测按置信度排序后做池相邻违规合并（PAVA），
    `calibrate()` 在块边界之间线性插值，越界裁剪到首末块取值。
    """

    def __init__(self) -> None:
        self._x: list[float] = []
        self._y: list[float] = []
        self._fitted = False

    def fit(self, observations: Iterable[Observation]) -> "IsotonicCalibrator":
        points = sorted(
            (_clip_probability(conf), 1.0 if ok else 0.0) for conf, ok in observations
        )
        if not points:
            raise ValueError("观测为空：保序回归至少需要一条观测")
        # PAVA：维护块栈，每块是 (x 的加权和均值, y 的加权均值, 权重)
        blocks: list[tuple[float, float, float]] = []
        for x, y in points:
            blocks.append((x, y, 1.0))
            # 合并违反单调的相邻块（后面块的均值低于前面）
            while len(blocks) >= 2 and blocks[-2][1] > blocks[-1][1] + 1e-12:
                x1, y1, w1 = blocks[-2]
                x2, y2, w2 = blocks[-1]
                blocks[-2:] = [
                    (
                        (x1 * w1 + x2 * w2) / (w1 + w2),
                        (y1 * w1 + y2 * w2) / (w1 + w2),
                        w1 + w2,
                    )
                ]
        self._x = [block[0] for block in blocks]
        self._y = [block[1] for block in blocks]
        self._fitted = True
        return self

    def calibrate(self, confidence: float) -> float:
        if not self._fitted:
            raise RuntimeError("未 fit 就调用 calibrate：先提供观测")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"置信度必须在 [0,1]：{confidence}")
        if confidence <= self._x[0]:
            return self._y[0]
        if confidence >= self._x[-1]:
            return self._y[-1]
        # 块间线性插值（块很少时退化为分段常数，同样单调）
        for index in range(1, len(self._x)):
            if confidence <= self._x[index]:
                x0, y0 = self._x[index - 1], self._y[index - 1]
                x1, y1 = self._x[index], self._y[index]
                if x1 <= x0:
                    return y1
                ratio = (confidence - x0) / (x1 - x0)
                return y0 + ratio * (y1 - y0)
        return self._y[-1]


__all__ = [
    "IsotonicCalibrator",
    "Observation",
    "bayesian_confidence",
    "expected_calibration_error",
    "fit_temperature",
    "reliability_buckets",
]
