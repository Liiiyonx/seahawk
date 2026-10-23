"""类型化快判断层（Typed Decisions）—— 快慢分工架构的「快」侧接口。

## 这个模块解决什么问题

智能体闭环里最高频的不是「规划」这类慢思考，而是原子化的快判断：
该合并还是新建、风险有多高、证据够不够、要不要转人工。这些判断
过去散落在规则代码的 if/else 里，输出是裸值 —— 软件既无法按「判断
有多可信」分流，也无法度量判断质量。

本模块把快判断统一为三个类型化原语（对齐决策模型 / System One 路线
的公开范式，如 TypeSafe Jev 与 APUS 开源复现）：

    Choice —— 从固定选项里选一个，返回全选项概率分布
    Score  —— 在有序等级上打分，返回各等级概率
    Noul   —— 返回「是」的概率

输出永远是「类型化答案 + 概率」，不是自由文本：调用方按阈值分流
（高置信自动执行 / 中间区间升级慢思考 / 低置信转人工），不需要解析
模型输出，从机制上杜绝格式幻觉。

## 两条实现路径（快慢分工纪律，手册 5.6）

1. `RuleTypedDecider`（基线，默认）：确定性规则实现 —— 规则命中给
   集中概率，未命中给均匀分布（低置信）。无模型、无随机、可离线
   复现；概率可由规则的历史成功率经贝叶斯平滑修正。
2. `LogitsTypedDecider`（可选增强）：LLM 单 token logits 路径 ——
   候选答案各由注入的 `logits_fn` 给出分数，softmax（可选温度）归
   一化为概率，跳过自回归解码。本模块不做网络调用：注入什么算力
   用什么算力；`logits_fn` 异常时回退注入的规则基线，模型不可用时
   核心能力不下降。

## 诚实边界

- 概率不等于校准：`LogitsTypedDecider` 的温度可用
  `calibration.fit_temperature` 在历史观测上拟合，但校准有效性取决
  于样本量 —— 样本不足时概率只是排序信号，不是可信度。
- `RuleTypedDecider` 的概率含义是「规则模式下该判断的先验可信度」，
  不冒充模型的语义理解。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.services.agents.calibration import bayesian_confidence

# 规则命中时的先验可信度与等效样本数：确定性规则在其适用条件内
# 视为「先验 0.9、等效 4 个观测」，历史成功率可进一步修正它。
_RULE_PRIOR = 0.9
_RULE_PRIOR_STRENGTH = 4.0

# state 里携带规则结果的键名（调用方确实知道的业务事实，不是模型猜的）
RULE_CHOICE_KEY = "rule_choice"
RULE_SCORE_KEY = "rule_score"
RULE_BOOL_KEY = "rule_bool"


@dataclass(frozen=True)
class ChoiceAnswer:
    """Choice 原语的答案：选中的选项 + 全选项概率分布（和为 1）。"""

    choice: str
    probabilities: dict[str, float]

    @property
    def confidence(self) -> float:
        """选中项的概率 —— 调用方分流用的那个数。"""
        return self.probabilities[self.choice]


@dataclass(frozen=True)
class ScoreAnswer:
    """Score 原语的答案：打中的等级 + 各等级概率分布（和为 1）。"""

    score: int
    probabilities: dict[int, float]


@dataclass(frozen=True)
class NoulAnswer:
    """Noul 原语的答案：「是」的概率（单数，不是分布）。"""

    probability: float


def _softmax(scores: Mapping[str, float], temperature: float) -> dict[str, float]:
    """数值稳定的带温度 softmax：exp((x - max)/T) 归一化；T 必须为正。

    温度在 exp **里面**除：T>1 软化（分布更平）、T<1 硬化（分布更尖）。
    """
    if temperature <= 0:
        raise ValueError(f"temperature 必须为正：{temperature}")
    peak = max(scores.values())
    exps = {
        key: math.exp((value - peak) / temperature) for key, value in scores.items()
    }
    total = sum(exps.values())
    if total <= 0:
        n = len(exps)
        return {key: 1.0 / n for key in exps}
    return {key: value / total for key, value in exps.items()}


class TypedDecider(Protocol):
    """快判断协议：三个原语，输入 question + state，输出类型化答案。"""

    def choose(
        self, question: str, options: Sequence[str], state: Mapping[str, Any]
    ) -> ChoiceAnswer:
        if not isinstance(question, str) or not options:
            raise TypeError("question 必须是 str 且 options 非空")
        if not isinstance(state, Mapping):
            raise TypeError(f"state 必须是 Mapping：{type(state).__name__}")
        raise NotImplementedError("TypedDecider.choose 未实现")

    def score(
        self, question: str, scale: Sequence[int], state: Mapping[str, Any]
    ) -> ScoreAnswer:
        if not isinstance(question, str) or not scale:
            raise TypeError("question 必须是 str 且 scale 非空")
        if not isinstance(state, Mapping):
            raise TypeError(f"state 必须是 Mapping：{type(state).__name__}")
        raise NotImplementedError("TypedDecider.score 未实现")

    def noul(self, question: str, state: Mapping[str, Any]) -> NoulAnswer:
        if not isinstance(question, str):
            raise TypeError("question 必须是 str")
        if not isinstance(state, Mapping):
            raise TypeError(f"state 必须是 Mapping：{type(state).__name__}")
        raise NotImplementedError("TypedDecider.noul 未实现")


class RuleTypedDecider:
    """确定性规则实现（基线）。

    规则结果由调用方放进 `state`（`rule_choice` / `rule_score` /
    `rule_bool`）—— 调用方**确实知道**的业务事实，本实现只做类型化
    包装与概率分配，不做语义理解：

    - 命中：选中项拿 `bayesian_confidence(0.9, successes, trials)`
      的概率，其余选项均分剩余；
    - 未命中：均匀分布（1/n）—— 没有规则依据时每个选项等可信，
      这本身就是「低置信」信号，调用方应当转人工或升级慢思考。

    `successes / trials` 是该规则的历史命中统计（可选）：与经验库的
    置信度共用同一套贝叶斯平滑数学（calibration.bayesian_confidence）。
    """

    def __init__(self, *, successes: int = 0, trials: int = 0) -> None:
        self._hit_rate = bayesian_confidence(
            _RULE_PRIOR, successes, trials, prior_strength=_RULE_PRIOR_STRENGTH
        )

    @property
    def hit_rate(self) -> float:
        """规则命中时的选中概率（先验 + 历史成功率的贝叶斯平滑）。"""
        return self._hit_rate

    def choose(
        self, question: str, options: Sequence[str], state: Mapping[str, Any]
    ) -> ChoiceAnswer:
        options = list(options)
        if not options:
            raise ValueError("options 不能为空")
        if not isinstance(question, str):
            raise TypeError(f"question 必须是 str：{type(question).__name__}")
        picked = state.get(RULE_CHOICE_KEY)
        if picked is not None and picked in options:
            rest = (1.0 - self._hit_rate) / (len(options) - 1) if len(options) > 1 else 0.0
            probabilities = {
                option: (self._hit_rate if option == picked else rest) for option in options
            }
            return ChoiceAnswer(choice=picked, probabilities=probabilities)
        even = 1.0 / len(options)
        return ChoiceAnswer(
            choice=options[0], probabilities={option: even for option in options}
        )

    def score(
        self, question: str, scale: Sequence[int], state: Mapping[str, Any]
    ) -> ScoreAnswer:
        scale = list(scale)
        if not scale:
            raise ValueError("scale 不能为空")
        if not isinstance(question, str):
            raise TypeError(f"question 必须是 str：{type(question).__name__}")
        picked = state.get(RULE_SCORE_KEY)
        if picked is not None and picked in scale:
            rest = (1.0 - self._hit_rate) / (len(scale) - 1) if len(scale) > 1 else 0.0
            probabilities = {
                level: (self._hit_rate if level == picked else rest) for level in scale
            }
            return ScoreAnswer(score=picked, probabilities=probabilities)
        even = 1.0 / len(scale)
        return ScoreAnswer(
            score=scale[0], probabilities={level: even for level in scale}
        )

    def noul(self, question: str, state: Mapping[str, Any]) -> NoulAnswer:
        if not isinstance(question, str):
            raise TypeError(f"question 必须是 str：{type(question).__name__}")
        flag = state.get(RULE_BOOL_KEY)
        if flag is None:
            return NoulAnswer(probability=0.5)
        return NoulAnswer(
            probability=self._hit_rate if flag else round(1.0 - self._hit_rate, 4)
        )


class LogitsTypedDecider:
    """LLM 单 token logits 快判断（可选增强路径）。

    核心机制（Jev / APUS 公开复现的范式）：候选答案的打分由注入的
    `logits_fn(question, candidates, state)` 给出（例如：把 state +
    问题格式化为 prompt，一次前向计算读取各候选 token 的 logit），
    本类负责 softmax（可选温度）归一化与 argmax —— 全程不生成任何
    文本，跳过自回归解码。

    `fallback` 必须提供（规则基线）：`logits_fn` 抛异常或返回非法
    结果时回退它 —— 模型不可用时核心能力不下降。回退不会静默：
    `last_fallback_reason` 记录最近一次原因，调用方可审计。
    """

    def __init__(
        self,
        logits_fn: Callable[[str, Sequence[str], Mapping[str, Any]], dict[str, float]],
        *,
        temperature: float = 1.0,
        fallback: RuleTypedDecider | None = None,
    ) -> None:
        if temperature <= 0:
            raise ValueError(f"temperature 必须为正：{temperature}")
        self._logits_fn = logits_fn
        self._temperature = temperature
        self._fallback = fallback or RuleTypedDecider()
        self.last_fallback_reason: str | None = None

    def _scores(
        self, question: str, candidates: Sequence[str], state: Mapping[str, Any]
    ) -> dict[str, float] | None:
        """调 logits_fn 取候选分数；异常返回 None（触发回退）。"""
        try:
            scores = self._logits_fn(question, list(candidates), dict(state))
        except Exception as exc:  # noqa: BLE001 —— 任何模型侧故障都回退，不冒泡
            self.last_fallback_reason = f"logits_fn 异常：{exc}"
            return None
        if not isinstance(scores, dict) or not scores:
            self.last_fallback_reason = "logits_fn 返回空结果"
            return None
        return {str(key): float(value) for key, value in scores.items()}

    def choose(
        self, question: str, options: Sequence[str], state: Mapping[str, Any]
    ) -> ChoiceAnswer:
        options = list(options)
        if not options:
            raise ValueError("options 不能为空")
        scores = self._scores(question, options, state)
        if scores is None:
            return self._fallback.choose(question, options, state)
        probabilities = _softmax(scores, self._temperature)
        picked = max(probabilities, key=lambda key: (probabilities[key], key))
        return ChoiceAnswer(choice=picked, probabilities=probabilities)

    def score(
        self, question: str, scale: Sequence[int], state: Mapping[str, Any]
    ) -> ScoreAnswer:
        scale = list(scale)
        if not scale:
            raise ValueError("scale 不能为空")
        scores = self._scores(question, [str(level) for level in scale], state)
        if scores is None:
            return self._fallback.score(question, scale, state)
        probabilities = _softmax(scores, self._temperature)
        picked = max(probabilities, key=lambda key: (probabilities[key], key))
        return ScoreAnswer(
            score=int(picked),
            probabilities={level: probabilities.get(str(level), 0.0) for level in scale},
        )

    def noul(self, question: str, state: Mapping[str, Any]) -> NoulAnswer:
        scores = self._scores(question, ["yes", "no"], state)
        if scores is None:
            return self._fallback.noul(question, state)
        probabilities = _softmax(scores, self._temperature)
        return NoulAnswer(probability=round(probabilities.get("yes", 0.5), 4))


__all__ = [
    "ChoiceAnswer",
    "LogitsTypedDecider",
    "NoulAnswer",
    "RULE_BOOL_KEY",
    "RULE_CHOICE_KEY",
    "RULE_SCORE_KEY",
    "RuleTypedDecider",
    "ScoreAnswer",
    "TypedDecider",
]
