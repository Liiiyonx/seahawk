"""类型化快判断层（decisions.py）的单元测试。

钉死三件事：
1. 规则基线：命中给集中概率、未命中给均匀分布（低置信信号），
   历史成功率经贝叶斯平滑修正先验；
2. logits 增强路径：softmax 归一化正确、温度软化/硬化、模型侧
   任何故障回退规则基线且可审计；
3. 诚实纪律：概率和恒为 1、非法入参直接抛错（不静默纠正）。
"""

from __future__ import annotations

import pytest

from app.services.agents.calibration import fit_temperature
from app.services.agents.decisions import (
    LogitsTypedDecider,
    RuleTypedDecider,
)


def _fixed_logits(question: str, candidates: list[str], state: dict) -> dict[str, float]:
    """确定性的假「模型」：按 state 里给的分数字典返回。"""
    return dict(state["logits"])


class TestRuleTypedDecider:
    def test_choose_hit_concentrates_probability(self) -> None:
        """规则命中：选中项拿先验 0.9，其余选项均分剩余。"""
        decider = RuleTypedDecider()
        answer = decider.choose(
            "工单该合并还是新建",
            ["merge", "create", "manual"],
            {"rule_choice": "merge"},
        )
        assert answer.choice == "merge"
        assert answer.confidence == pytest.approx(0.9)
        assert sum(answer.probabilities.values()) == pytest.approx(1.0)
        rest = answer.probabilities["create"]
        assert rest == pytest.approx(0.1 / 2)

    def test_choose_miss_gives_uniform_low_confidence(self) -> None:
        """规则未命中：均匀分布 —— 「没有依据」本身就是低置信信号。"""
        decider = RuleTypedDecider()
        answer = decider.choose("怎么处理", ["a", "b", "c", "d"], {})
        assert answer.confidence == pytest.approx(0.25)
        assert set(answer.probabilities) == {"a", "b", "c", "d"}

    def test_history_adjusts_prior(self) -> None:
        """历史成功率参与贝叶斯平滑：全胜上调、全败下调选中概率。"""
        strong = RuleTypedDecider(successes=6, trials=6)
        weak = RuleTypedDecider(successes=0, trials=6)
        assert strong.hit_rate > 0.9 > weak.hit_rate

    def test_score_and_noul(self) -> None:
        decider = RuleTypedDecider()
        scored = decider.score("风险等级", [0, 1, 2], {"rule_score": 2})
        assert scored.score == 2
        assert scored.probabilities[2] == pytest.approx(0.9)

        yes = decider.noul("需要人工审批吗", {"rule_bool": True})
        no = decider.noul("需要人工审批吗", {"rule_bool": False})
        unknown = decider.noul("需要人工审批吗", {})
        assert yes.probability == pytest.approx(0.9)
        assert no.probability == pytest.approx(0.1)
        assert unknown.probability == pytest.approx(0.5)

    def test_empty_candidates_raise(self) -> None:
        decider = RuleTypedDecider()
        with pytest.raises(ValueError):
            decider.choose("q", [], {})
        with pytest.raises(ValueError):
            decider.score("q", [], {})


class TestLogitsTypedDecider:
    def test_softmax_normalizes_and_picks_max(self) -> None:
        decider = LogitsTypedDecider(_fixed_logits)
        answer = decider.choose(
            "转给哪个组",
            ["billing", "logistics", "finance"],
            {"logits": {"billing": 3.0, "logistics": 0.0, "finance": 0.0}},
        )
        assert answer.choice == "billing"
        assert sum(answer.probabilities.values()) == pytest.approx(1.0)
        assert answer.confidence > 0.8

    def test_temperature_softens_and_hardens(self) -> None:
        logits = {"yes": 2.0, "no": 0.0}
        hot = LogitsTypedDecider(_fixed_logits, temperature=5.0)
        cold = LogitsTypedDecider(_fixed_logits, temperature=0.5)
        hot_p = hot.noul("q", {"logits": logits}).probability
        cold_p = cold.noul("q", {"logits": logits}).probability
        assert 0.5 < hot_p < cold_p  # 高温软化（更接近 0.5），低温硬化（更极端）

    def test_model_failure_falls_back_to_rules(self) -> None:
        """模型侧任何故障 → 回退规则基线，且回退原因可审计。"""

        def broken(question: str, candidates: list[str], state: dict) -> dict[str, float]:
            raise RuntimeError("endpoint 503")

        decider = LogitsTypedDecider(broken)
        answer = decider.choose("q", ["a", "b"], {"rule_choice": "a"})
        assert answer.choice == "a"
        assert answer.confidence == pytest.approx(0.9)
        assert decider.last_fallback_reason and "503" in decider.last_fallback_reason

    def test_empty_logits_result_falls_back(self) -> None:
        decider = LogitsTypedDecider(lambda q, c, s: {})
        answer = decider.choose("q", ["a", "b"], {})
        assert sum(answer.probabilities.values()) == pytest.approx(1.0)
        assert decider.last_fallback_reason is not None

    def test_invalid_temperature_raises(self) -> None:
        with pytest.raises(ValueError):
            LogitsTypedDecider(_fixed_logits, temperature=0.0)


class TestCalibrationWiring:
    def test_fitted_temperature_wire_into_decider(self) -> None:
        """端到端接线：历史观测 → fit_temperature → 注入快判断层。"""
        # 合成观测：声明 yes 时 60% 为真（过度自信的原始标尺）
        observations = [(0.9, True)] * 6 + [(0.9, False)] * 4
        temperature = fit_temperature(observations)
        assert temperature > 1.0  # 需要软化

        decider = LogitsTypedDecider(_fixed_logits, temperature=temperature)
        raw = LogitsTypedDecider(_fixed_logits)
        logits = {"yes": 2.0, "no": 0.0}
        calibrated = decider.noul("q", {"logits": logits}).probability
        uncalibrated = raw.noul("q", {"logits": logits}).probability
        assert calibrated < uncalibrated  # 校准后压低过度自信的声明
