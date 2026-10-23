"""决策置信度校准（calibration.py + LessonStore.settle）的单元测试。

覆盖三件事，缺一不可：
1. 校准原语的数学正确性（ECE / 温度缩放 / 保序回归 / 贝叶斯平滑）；
2. 经验闭环的收口行为 —— settle 把「引用后的真实结果」写回置信度：
   成功升、失败降、幂等、非终态不结算；
3. 诚实纪律 —— 样本不足时校准报告给 None 而不是编数字。

这组测试全部纯内存、无模型、无随机：与项目「可离线复现」的纪律一致。
runtime 侧的端到端接入（_terminate → settle → harvest）由
test_agent_api.py::TestLessons 覆盖，这里不重复搭 HTTP 栈。
"""

from __future__ import annotations

import pytest

from app.services.agents.calibration import (
    IsotonicCalibrator,
    bayesian_confidence,
    expected_calibration_error,
    fit_temperature,
    reliability_buckets,
)
from app.services.agents.lessons import (
    LESSON_MEMORY_TYPE,
    LESSON_SCOPE_TYPE,
    LessonStore,
)
from app.services.agents.memory import InMemoryMemoryStore


# ----------------------------------------------------------------------
# 贝叶斯平滑
# ----------------------------------------------------------------------


class TestBayesianConfidence:
    def test_no_observations_returns_prior(self) -> None:
        """无观测时恒等于先验：新经验的初始置信度就是它的基准值。"""
        assert bayesian_confidence(0.85, 0, 0) == pytest.approx(0.85)

    def test_success_raises_and_failure_lowers(self) -> None:
        """成功上调、失败下调 —— 「只会涨的置信度不是置信度，是计数器」。"""
        prior = 0.85
        raised = bayesian_confidence(prior, 3, 3)
        lowered = bayesian_confidence(prior, 0, 3)
        assert lowered < prior < raised

    def test_evidence_eventually_dominates_prior(self) -> None:
        """长期结果压过先验：40 次全败后接近 0，40 次全胜后接近 1。"""
        assert bayesian_confidence(0.9, 0, 40) == pytest.approx(0.1, abs=0.02)
        assert bayesian_confidence(0.1, 40, 40) == pytest.approx(0.9, abs=0.02)

    def test_invalid_arguments_raise(self) -> None:
        with pytest.raises(ValueError):
            bayesian_confidence(1.5, 0, 0)
        with pytest.raises(ValueError):
            bayesian_confidence(0.5, 0, 0, prior_strength=0)
        with pytest.raises(ValueError):
            bayesian_confidence(0.5, 3, 2)  # successes > trials


# ----------------------------------------------------------------------
# 可靠性分桶与 ECE
# ----------------------------------------------------------------------


class TestReliabilityAndECE:
    def test_perfect_calibration_gives_zero_ece(self) -> None:
        """声明 0.8 的桶里恰好 80% 成功：完美校准 → ECE 为 0。"""
        observations = [(0.8, True)] * 8 + [(0.8, False)] * 2
        assert expected_calibration_error(observations) == pytest.approx(0.0, abs=1e-9)

    def test_systematic_overconfidence_gives_large_ece(self) -> None:
        """声明 0.9 但只有一半成功：过度自信 → ECE 接近 0.4。"""
        observations = [(0.9, True)] * 5 + [(0.9, False)] * 5
        assert expected_calibration_error(observations) == pytest.approx(0.4, abs=1e-9)

    def test_empty_observations_give_zero(self) -> None:
        """空观测 ECE=0（无声明即无偏差；要不要信由调用方按样本量判断）。"""
        assert expected_calibration_error([]) == 0.0

    def test_buckets_skip_empty_and_clamp_top(self) -> None:
        """空桶不出现（不伪造 0）；confidence=1.0 归最后一桶。"""
        buckets = reliability_buckets([(0.05, False), (1.0, True)], n_bins=10)
        ranges = [bucket["range"] for bucket in buckets]
        assert ranges == ["0.0-0.1", "0.9-1.0"]

    def test_invalid_confidence_raises(self) -> None:
        with pytest.raises(ValueError):
            reliability_buckets([(1.2, True)])


# ----------------------------------------------------------------------
# 温度缩放
# ----------------------------------------------------------------------


class TestFitTemperature:
    def test_overconfident_claims_are_softened(self) -> None:
        """声明 0.9 但只有一半成功：最优温度应当 > 1（软化标尺）。"""
        observations = [(0.9, True)] * 10 + [(0.9, False)] * 10
        assert fit_temperature(observations) > 1.0

    def test_underconfident_claims_are_hardened(self) -> None:
        """声明 0.6 但全部成功：最优温度应当 < 1（硬化标尺）。"""
        observations = [(0.6, True)] * 20
        assert fit_temperature(observations) < 1.0

    def test_too_few_observations_return_neutral(self) -> None:
        """不足 2 条观测：无可校准，返回中性温度 1.0。"""
        assert fit_temperature([(0.9, True)]) == 1.0
        assert fit_temperature([]) == 1.0

    def test_search_is_deterministic(self) -> None:
        """同样的观测永远返回同一个温度（网格搜索无随机性）。"""
        observations = [(0.85, True)] * 6 + [(0.85, False)] * 4
        assert fit_temperature(observations) == fit_temperature(observations)


# ----------------------------------------------------------------------
# 保序回归
# ----------------------------------------------------------------------


class TestIsotonicCalibrator:
    def test_monotonicity_violations_are_pooled(self) -> None:
        """低声明全成功、高声明全失败 → 违反单调，合并后得到折中映射。"""
        calibrator = IsotonicCalibrator().fit(
            [(0.2, True), (0.2, True), (0.8, False), (0.8, False)]
        )
        low = calibrator.calibrate(0.2)
        high = calibrator.calibrate(0.8)
        # 合并后两端的校准值被拉平：低声明不再被抬高到 1.0
        assert low == high

    def test_calibrate_interpolates_and_clips(self) -> None:
        """块间线性插值；越界裁剪到首末块取值，不外推。"""
        calibrator = IsotonicCalibrator().fit(
            [(0.2, True), (0.2, True), (0.9, False)]
        )
        assert 0.0 <= calibrator.calibrate(0.5) <= 1.0
        assert calibrator.calibrate(0.05) == calibrator.calibrate(0.2)
        assert calibrator.calibrate(0.95) == calibrator.calibrate(0.9)

    def test_unfitted_calibrate_raises(self) -> None:
        with pytest.raises(RuntimeError):
            IsotonicCalibrator().calibrate(0.5)

    def test_fit_on_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            IsotonicCalibrator().fit([])


# ----------------------------------------------------------------------
# LessonStore.settle：校准闭环收口
# ----------------------------------------------------------------------


def _make_store() -> LessonStore:
    return LessonStore(InMemoryMemoryStore(), enabled=True)


def _harvest_merge_lesson(store: LessonStore, run_id: str) -> None:
    """以 foam/merge_preferred 为例提炼一条经验（成功 + merged 分支）。"""
    store.harvest(
        run_id=run_id,
        main_class="foam",
        outcome="succeeded",
        termination_reason="succeeded",
        bindings={"action": "merged"},
    )


def _use_lesson(store: LessonStore, run_id: str) -> None:
    """模拟 runtime 的调用顺序：规划期检索命中 → 登记引用。"""
    hits = store.match(main_class="foam", context={"merge_candidate": True})
    assert hits, "前置条件：经验应当被命中"
    store.note_hit(hits, run_id=run_id)


class TestLessonSettle:
    def test_successful_use_raises_confidence(self) -> None:
        """引用后 run 成功：use 计数入账，置信度上升（贝叶斯后验）。"""
        store = _make_store()
        _harvest_merge_lesson(store, "run_1")
        before = store.all_lessons()[0].confidence  # 0.85

        _use_lesson(store, "run_2")
        settled = store.settle(run_id="run_2", outcome="succeeded")

        lesson = store.all_lessons()[0]
        assert settled == 1
        assert lesson.use_total == 1
        assert lesson.use_success == 1
        assert lesson.confidence > before

    def test_failed_use_lowers_confidence(self) -> None:
        """引用后 run 失败：置信度必须下降 —— 旧线性公式做不到这一点。"""
        store = _make_store()
        _harvest_merge_lesson(store, "run_1")
        before = store.all_lessons()[0].confidence  # 0.85

        _use_lesson(store, "run_2")
        store.settle(run_id="run_2", outcome="failed")

        lesson = store.all_lessons()[0]
        assert lesson.use_total == 1
        assert lesson.use_success == 0
        assert lesson.confidence < before

    def test_hit_count_alone_does_not_change_confidence(self) -> None:
        """「被引用」不是正确性证据：只 note_hit 不结算，置信度不动。"""
        store = _make_store()
        _harvest_merge_lesson(store, "run_1")
        before = store.all_lessons()[0].confidence

        _use_lesson(store, "run_2")  # 只引用，不结算

        lesson = store.all_lessons()[0]
        assert lesson.hit_count == 1
        assert lesson.confidence == before

    def test_settle_is_idempotent(self) -> None:
        """同一 run 重复结算返回 0，计数不重复入账。"""
        store = _make_store()
        _harvest_merge_lesson(store, "run_1")
        _use_lesson(store, "run_2")

        assert store.settle(run_id="run_2", outcome="succeeded") == 1
        assert store.settle(run_id="run_2", outcome="succeeded") == 0

        lesson = store.all_lessons()[0]
        assert lesson.use_total == 1

    def test_settle_ignores_unreferenced_run_and_nonterminal_outcome(self) -> None:
        """没引用过经验的 run、以及取消/超时口径，都不产生观测。"""
        store = _make_store()
        _harvest_merge_lesson(store, "run_1")
        assert store.settle(run_id="run_unknown", outcome="succeeded") == 0

        _use_lesson(store, "run_2")
        assert store.settle(run_id="run_2", outcome="cancelled") == 0
        lesson = store.all_lessons()[0]
        assert lesson.use_total == 0

    def test_settle_appends_memory_audit_trail(self) -> None:
        """结算也走追加式留痕：记忆里能看到 use_total 的演化。"""
        store = _make_store()
        _harvest_merge_lesson(store, "run_1")
        _use_lesson(store, "run_2")
        store.settle(run_id="run_2", outcome="succeeded")

        logged = store.memory.find(
            scope_type=LESSON_SCOPE_TYPE,
            scope_id="foam",
            memory_type=LESSON_MEMORY_TYPE,
        )
        # 提炼 1 条 + 引用 bump 1 条 + 结算 1 条 = 3 条审计记录
        assert len(logged) == 3
        latest = logged[-1].content
        assert latest["use_total"] == 1
        assert latest["use_success"] == 1


# ----------------------------------------------------------------------
# 校准报告（「可进化」的量化证据线）
# ----------------------------------------------------------------------


class TestCalibrationReport:
    def test_report_holds_back_ece_when_samples_insufficient(self) -> None:
        """样本不足 8 条时 ece=None —— 不硬给数字是诚实纪律，不是缺失。"""
        store = _make_store()
        _harvest_merge_lesson(store, "run_1")
        for i in range(2, 5):  # 3 次引用 + 结算
            _use_lesson(store, f"run_{i}")
            store.settle(run_id=f"run_{i}", outcome="succeeded")

        report = store.calibration_report()
        assert report["observation_count"] == 3
        assert report["ece"] is None
        assert report["buckets"], "分桶数据仍然给出（画曲线用）"

    def test_report_computes_ece_with_enough_samples(self) -> None:
        """凑够样本后 ece 是有限数：声明 0.8x 但全成功 → 偏差显著为正。"""
        store = _make_store()
        _harvest_merge_lesson(store, "run_1")
        for i in range(2, 10):  # 8 次引用 + 全部成功结算
            _use_lesson(store, f"run_{i}")
            store.settle(run_id=f"run_{i}", outcome="succeeded")

        report = store.calibration_report()
        assert report["observation_count"] == 8
        assert report["ece"] is not None
        assert 0.05 < report["ece"] < 0.2

    def test_disabled_store_reports_empty(self) -> None:
        store = LessonStore(InMemoryMemoryStore(), enabled=False)
        report = store.calibration_report()
        assert report["observation_count"] == 0
        assert report["buckets"] == []
