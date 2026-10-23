"""作业台「训练任务」接口与组装口径自测（其中的数据层不需要 ultralytics）。

## 为什么必须测

训练卡是本次改造里输入面最复杂的一处：多会话、整组切分、replay 混采三个口径
都会改变「模型到底吃了什么数据」，而它们全都很容易**静默**搞错：

* 单会话却勾了整组切分 → 无法切分。这里必须 400 并说明，**不静默降级成逐帧洗牌**
  （静默降级的结果是「有 val 集、但已泄漏」，指标虚高却看不出来）。
* 混采类名不是主集子集 → 类索引整体错位 → 必须报错，且必须是普通异常
  （``SystemExit`` 会让作业台的任务停在 starting 且不报错）。
* 组装统计（train/val/**背景帧**/整组切分的 val 单元）要真的进 Job.detail 与日志，
  否则界面上的数字就成了摆设。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
GRASP = HERE.parent
EDGE = GRASP.parent
for _p in (str(EDGE), str(GRASP)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from grasp.config import load_config                          # noqa: E402
from grasp.vision.mix import MixError                         # noqa: E402
from grasp.web.server import Job, _compose_dataset, create_app  # noqa: E402

JPEG = b"\xff\xd8\xff\xd9"


@pytest.fixture()
def tmp_env(tmp_path: Path, monkeypatch):
    """隔离数据根目录，并**先把 app 建起来**（_compose_dataset 走的是 STATE.dataset）。

    返回 ``(STATE.dataset, cfg)``。必须经 create_app 建 state：不建的话
    ``_state()`` 会抛 503，而且可能拿到上一个测试残留的 STATE（那会静默读写
    别人的临时目录 —— 这类"看起来过了、其实测的是别的东西"最难查）。
    """
    from grasp import calibration as calib_mod
    monkeypatch.setattr(calib_mod, "DEFAULT_CALIBRATION_PATH", tmp_path / "calibration.json")
    cfg = load_config()
    cfg.setdefault("data", {})["root"] = str(tmp_path / "data")
    create_app(cfg, mock=True)
    from grasp.presets import PresetStore
    from grasp.web import server as srv
    srv.STATE.presets = PresetStore(tmp_path / "presets.json")
    return srv.STATE.dataset, cfg


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    from grasp import calibration as calib_mod
    monkeypatch.setattr(calib_mod, "DEFAULT_CALIBRATION_PATH", tmp_path / "calibration.json")
    cfg = load_config()
    cfg.setdefault("data", {})["root"] = str(tmp_path / "data")
    app = create_app(cfg, mock=True)
    with TestClient(app) as c:
        from grasp.presets import PresetStore
        from grasp.web import server as srv
        srv.STATE.presets = PresetStore(tmp_path / "presets.json")
        yield c


def _frames(ds, name: str, n: int, labeled: int) -> None:
    raw, lbl = ds.raw_dir / name, ds.labels_dir / name
    raw.mkdir(parents=True, exist_ok=True)
    lbl.mkdir(parents=True, exist_ok=True)
    for i in range(1, n + 1):
        (raw / f"frame_{i:04d}.jpg").write_bytes(JPEG)
    for i in range(1, labeled + 1):
        (lbl / f"frame_{i:04d}.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")


# ----------------------------------------------------------------------
# 契约层（不需要 ultralytics：这些校验都在起作业之前）
# ----------------------------------------------------------------------
def test_unknown_tier_is_400(client: TestClient) -> None:
    r = client.post("/api/train", json={"tier": "nope"})
    assert r.status_code == 400
    assert "未知档位" in r.json()["detail"]


def test_session_and_sessions_are_mutually_exclusive(client: TestClient) -> None:
    r = client.post("/api/train", json={"tier": "calibrate", "session": "a", "sessions": ["b"]})
    assert r.status_code == 400
    assert "二选一" in r.json()["detail"]


def test_group_splits_with_single_session_is_400(client: TestClient) -> None:
    """整组切分至少要 2 个采集单元；只给一个必须 400，不许静默降级成逐帧洗牌。"""
    r = client.post("/api/train", json={"tier": "calibrate", "session": "only", "group_splits": True})
    assert r.status_code == 400
    assert "至少要 2 个" in r.json()["detail"]


def test_group_splits_without_explicit_sessions_is_not_rejected_upfront(client: TestClient) -> None:
    """★ 「全部会话 + 整组切分」必须放行 —— 只在**显式给了清单**时才校验条数。

    清单为空 = 全部会话，磁盘上有几个采集单元此刻没人知道（要知道就得扫一遍盘）。
    一律按 "<2" 拒绝会把这条完全正常的组合堵死，而且提示文不对题（人明明选的是
    「全部」，回你的却是「只有一个会话请改用逐帧切分」）。单元数真的不足时由组装
    阶段（``dataset._pick_val_units``）报错 —— 它会报出实际有几个单元，那条信息才对。
    """
    r = client.post("/api/train", json={"tier": "calibrate", "group_splits": True})
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["group_splits"] is True and body["sessions"] == []


def test_mix_path_must_exist_and_be_yaml(client: TestClient, tmp_path: Path) -> None:
    r = client.post("/api/train", json={"tier": "calibrate",
                                        "mix_dataset_yaml": [str(tmp_path / "nope.yaml")]})
    assert r.status_code == 400
    assert "不存在" in r.json()["detail"]
    # 后缀不对（即便文件存在）也要拦
    bad = tmp_path / "x.txt"
    bad.write_text("hi", encoding="utf-8")
    r2 = client.post("/api/train", json={"tier": "calibrate", "mix_dataset_yaml": [str(bad)]})
    assert r2.status_code == 400


# ----------------------------------------------------------------------
# 数据层：直接调 _compose_dataset（不需要 ultralytics）
# ----------------------------------------------------------------------
def test_compose_multi_session_group_split_keeps_units_together(tmp_env) -> None:
    """整组切分：Job.detail 与日志要如实报出 val 单元，且训练/验证集非空。"""
    ds, _cfg = tmp_env
    _frames(ds, "grp_a", 6, 6)
    _frames(ds, "grp_b", 6, 6)
    _frames(ds, "grp_c", 6, 6)
    job = Job(kind="train")
    yaml_path, stats = _compose_dataset(job, ["grp_a", "grp_b", "grp_c"], True, [])

    assert yaml_path.exists() and Path(yaml_path).name == "data.yaml"
    assert stats["group_splits"] is True
    assert stats["train"] + stats["val"] == 18
    assert stats["val"] >= 1 and stats["train"] >= 1
    assert job.detail["group_splits"] is True
    assert len(job.detail["val_units"]) == len(stats["val_units"])
    assert any("整组切分" in line for line in job.log)
    # 背景帧数必须出现在组装日志里（负样本到底有没有进去，一眼可见）
    assert any("背景帧" in line for line in job.log)


def test_compose_reports_background_frames(tmp_env) -> None:
    ds, _cfg = tmp_env
    _frames(ds, "pos", 6, 6)
    _frames(ds, "neg", 6, 0)
    ds.mark_background("neg", note="空池")
    job = Job(kind="train")
    _compose_dataset(job, ["pos", "neg"], False, [])
    assert job.detail["background"] == 6, "整组标了背景的帧必须计入 background"
    assert job.detail["total"] == 12


def test_compose_mix_reports_sources_and_warns(tmp_env, tmp_path: Path) -> None:
    """混采要报出各来源图数与那条「合并 val 不能当泳池域指标」的警示。"""
    ds, _cfg = tmp_env
    _frames(ds, "pool", 8, 8)
    extra = tmp_path / "extra"
    (extra / "images" / "train").mkdir(parents=True)
    (extra / "images" / "val").mkdir(parents=True)
    for i in range(3):
        (extra / "images" / "train" / f"e{i}.jpg").write_bytes(JPEG)
    (extra / "images" / "val" / "ev.jpg").write_bytes(JPEG)
    extra_yaml = extra / "data.yaml"
    extra_yaml.write_text(
        f"path: {extra.as_posix()}\ntrain: images/train\nval: images/val\nnames:\n  0: plastic_bag\n",
        encoding="utf-8")

    job = Job(kind="train")
    yaml_path, stats = _compose_dataset(job, ["pool"], False, [str(extra_yaml)])

    assert Path(yaml_path).parent.name == "built_mixed"
    mixed = job.detail["mixed"]
    # sources 统计的是各来源的 **train** 图数：主集 8 帧按 val_ratio 切成 6/2
    assert mixed["sources"]["primary"] == 6
    assert list(mixed["sources"].values())[1] == 3
    assert mixed["train"] == 6 + 3
    assert any("混采" in line and "replay" in line for line in job.log)
    assert any("不能当泳池域指标读" in line for line in job.log)
    # 泳池域自己的 data.yaml 必须仍然指向未混的那份（界面靠它单量泳池域指标）
    assert Path(stats["data_yaml"]).parent.name == "built"


def test_compose_mix_superset_raises_plain_exception_not_systemexit(tmp_env, tmp_path: Path) -> None:
    """类名不是子集 → 必须报错，且**不是 SystemExit**（作业台只捕 Exception）。"""
    ds, _cfg = tmp_env
    _frames(ds, "pool", 8, 8)          # 主集类名 = plastic_bag + buoy
    extra = tmp_path / "bad"
    (extra / "images" / "train").mkdir(parents=True)
    (extra / "images" / "train" / "x.jpg").write_bytes(JPEG)
    bad_yaml = extra / "data.yaml"
    bad_yaml.write_text(
        f"path: {extra.as_posix()}\ntrain: images/train\nval: images/train\n"
        "names:\n  0: plastic_bag\n  1: foam\n", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc:
        _compose_dataset(Job(kind="train"), ["pool"], False, [str(bad_yaml)])
    assert not isinstance(exc.value, SystemExit)
    assert "混采不可行" in str(exc.value)


# ----------------------------------------------------------------------
# 「同一套口径只有一份实现」的守卫
# ----------------------------------------------------------------------
def test_single_implementation_guards() -> None:
    """这些算法/逻辑必须只有一份实现（CLI 与控制台共用），别又长出第二份。"""
    checks = [
        (GRASP / "tools" / "finetune_pool.py", "def _mix_datasets"),
        (GRASP / "tools" / "verify_pool_model.py", "def _iou_at_least"),
        (GRASP / "tools" / "verify_pool_model.py", "def _load_yolo_gt"),
        (GRASP / "tools" / "eval_robustness.py", "def _iou("),
        (GRASP / "tools" / "eval_robustness.py", "def match("),
    ]
    for path, needle in checks:
        src = path.read_text(encoding="utf-8")
        assert needle not in src, f"{path.name} 里又出现了 {needle}（应改调 grasp/vision/）"
    # 共享实现确实存在
    assert (GRASP / "vision" / "mix.py").exists()
    assert (GRASP / "vision" / "metrics.py").exists()
    assert (GRASP / "vision" / "sweep.py").exists()
