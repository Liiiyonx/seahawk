"""作业台「会话 / 背景负样本 / 帧列表」接口自测（mock，不需要 ROS / 相机 / ultralytics）。

## 为什么这几条必须测

这套接口决定「采完的帧到底有多少会进训练」，三处各有一个静默出错的方向：

1. ``/api/sessions`` 给出可用样本数 ``usable``：把「采了 40 帧」与「40 个训练样本」
   分开。没有它，界面只能显示帧数，操作员会以为全都进去了。
2. ``/api/background`` 整组标/撤背景：标错方向要么让纯负样本被静默丢掉（模型继续
   在臂体上误检），要么把整个会话当成「这场景什么都没有」喂给训练（必须能撤）。
3. ``/api/frames`` 的 ``limit``：不按会话解除截断的话，早于最近 60 帧的会话在标注台
   里一帧都看不见 —— 采完的旧组等于没法标注、没法进训练。

另外这条 fixture 比既有的多一条纪律：**把 ``cfg["data"]["root"]`` 也指到 tmp**，
否则测试会往仓库的 ``edge/grasp/data`` 里写帧与标签（同「不污染现场数据」的理由）。
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

from grasp.config import load_config            # noqa: E402
from grasp.web.server import create_app         # noqa: E402

JPEG = b"\xff\xd8\xff\xd9"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    from grasp import calibration as calib_mod
    monkeypatch.setattr(calib_mod, "DEFAULT_CALIBRATION_PATH", tmp_path / "calibration.json")
    cfg = load_config()
    # ★ 数据根目录也要重定向：否则帧/标签会写进仓库的 edge/grasp/data
    cfg.setdefault("data", {})["root"] = str(tmp_path / "data")
    app = create_app(cfg, mock=True)
    with TestClient(app) as c:
        from grasp.presets import PresetStore
        from grasp.web import server as srv
        srv.STATE.presets = PresetStore(tmp_path / "presets.json")
        yield c


def _fake_session(ds, name: str, frames: int, labeled: int = 0) -> None:
    """直接落帧与标签文件（绕开图源，专测接口口径）。"""
    raw = ds.raw_dir / name
    lbl = ds.labels_dir / name
    raw.mkdir(parents=True, exist_ok=True)
    lbl.mkdir(parents=True, exist_ok=True)
    for i in range(1, frames + 1):
        (raw / f"frame_{i:04d}.jpg").write_bytes(JPEG)
    for i in range(1, labeled + 1):
        (lbl / f"frame_{i:04d}.txt").write_text("0 0.5 0.5 0.1 0.1\n", encoding="utf-8")


def _ds():
    from grasp.web import server as srv
    return srv.STATE.dataset


def test_sessions_lists_every_session_including_long_ones(client: TestClient) -> None:
    """会话清单必须列出**全部**会话，包括帧数超过 60 的旧会话（不再从帧列表反推）。"""
    ds = _ds()
    _fake_session(ds, "20261018_101500_pool01_01_center", frames=70, labeled=7)
    _fake_session(ds, "20261018_110000_pool01_02_edge", frames=5, labeled=2)

    r = client.get("/api/sessions").json()
    assert r["count"] == 2
    by = {s["session"]: s for s in r["sessions"]}
    assert set(by) == {"20261018_101500_pool01_01_center", "20261018_110000_pool01_02_edge"}
    assert by["20261018_101500_pool01_01_center"]["frames"] == 70
    assert by["20261018_101500_pool01_01_center"]["labeled"] == 7
    assert by["20261018_101500_pool01_01_center"]["background"] is False


def test_usable_reflects_labels_not_frame_count(client: TestClient) -> None:
    """40 帧只标了 3 帧 → usable 必须是 3。这条锁住「采了 ≠ 有样本」的核心口径。"""
    _fake_session(_ds(), "s1", frames=40, labeled=3)
    item = client.get("/api/sessions").json()["sessions"][0]
    assert item["frames"] == 40
    assert item["labeled"] == 3
    assert item["usable"] == 3


def test_background_mark_and_unmark_changes_usable(client: TestClient) -> None:
    """整组标背景后 usable = 帧数；撤销后回落 —— 且标记文件真的落盘/删除。"""
    ds = _ds()
    _fake_session(ds, "neg_empty", frames=6, labeled=0)
    marker = ds.raw_dir / "neg_empty" / ".background"

    r = client.post("/api/background",
                    json={"session": "neg_empty", "note": "空池", "background": True}).json()
    assert r["ok"] is True and r["background"] is True
    assert r["usable"] == 6 and r["labeled"] == 0
    assert marker.exists(), "标记文件必须真的落盘（否则重启后背景语义丢失）"

    r2 = client.post("/api/background",
                     json={"session": "neg_empty", "background": False}).json()
    assert r2["background"] is False
    assert not marker.exists(), "撤销必须真的删掉标记（否则整组一直被当成背景喂进训练）"
    assert r2["usable"] == 0


def test_background_rejects_unknown_session_and_creates_nothing(client: TestClient) -> None:
    """不存在的会话必须 404 —— 否则 mark_background 的 mkdir 会凭空建出空会话目录。"""
    ds = _ds()
    r = client.post("/api/background", json={"session": "typo_会话", "background": True})
    assert r.status_code == 404
    assert "typo_会话" in r.json()["detail"]
    assert not (ds.raw_dir / "typo_会话").exists(), "不该为打错的名字建出会话目录"


def test_frames_session_scoped_is_not_truncated(client: TestClient) -> None:
    """按会话查必须能拿到全量；不带会话时保持默认截断（并如实回报 returned/limit）。"""
    _fake_session(_ds(), "long", frames=70, labeled=0)

    default = client.get("/api/frames").json()
    assert default["count"] == 70
    assert default["returned"] == 60          # 默认截断，避免把上千条灌进页面

    scoped = client.get("/api/frames", params={"session": "long", "limit": 0}).json()
    assert scoped["count"] == 70
    assert scoped["returned"] == 70           # 按会话查不截断 → 旧会话在标注台里看得见


def test_page_has_session_and_background_controls(client: TestClient) -> None:
    html = client.get("/").text
    for token in ("/api/sessions", "/api/background", "/api/sweep",
                  'id="train-sessions"', 'id="train-group"', 'id="train-mix"',
                  'id="lab-bg-btn"', 'id="dep-prec"', 'id="sweep-table"', 'id="sweep-log"'):
        assert token in html, f"页面缺少 {token}"
    # 旧的单会话下拉必须已经删掉（它只列得出最近 60 帧里的会话）
    assert 'id="train-session"' not in html


# ----------------------------------------------------------------------
# /api/sweep 的起停口径
# ----------------------------------------------------------------------
def test_sweep_without_any_model_is_409(client: TestClient, tmp_path: Path) -> None:
    """active 目录里三个候选都没有时必须 409 —— 不能让扫描跑起来、
    最后拿另一条推理链（或 mock）的结果冒充部署结论。"""
    from grasp.web import server as srv
    srv.STATE.detector.model_dir = tmp_path          # 空目录
    r = client.post("/api/sweep", json={})
    assert r.status_code == 409
    assert "没有可扫的模型" in r.json()["detail"]


def test_sweep_accepts_active_model_that_is_not_onnx(client: TestClient, tmp_path: Path) -> None:
    """只部署了 ncnn 的机器也要能扫。

    扫描本身支持 ncnn（后端由 ``Detector.load()`` 选），起停前置检查要是只认
    ``best.onnx``，就把这台机器整条扫描路堵死了 —— 而界面又没别的地方能发现。
    """
    from grasp.web import server as srv
    srv.STATE.detector.model_dir = tmp_path
    (tmp_path / "best.ncnn.param").write_text("probe", encoding="utf-8")
    r = client.post("/api/sweep", json={})
    assert r.status_code == 200, r.json()


def test_sweep_rejected_while_busy_keeps_last_result(client: TestClient) -> None:
    """被 409（已有作业在跑）拒掉时**不能**顺手擦掉上一次扫描结果。

    什么都没跑起来，证据却没了 —— 表现成「刷新一下，上次那张表就消失了」，
    比一开始就不显示更难查。
    """
    from grasp.web import server as srv
    srv.STATE.job = srv.Job(kind="train", running=True, stage="train")
    srv.STATE.last_sweep = {"model": "probe", "scan": []}
    r = client.post("/api/sweep", json={"model_path": "some.onnx"})
    assert r.status_code == 409
    assert srv.STATE.last_sweep == {"model": "probe", "scan": []}


# ----------------------------------------------------------------------
# 软停止与采集循环
# ----------------------------------------------------------------------
def test_soft_stop_ends_capture_job(client: TestClient) -> None:
    """软停止必须真的让采集循环退出，并如实报「中止 + 已存几帧」。

    作业体若只查 ``job.running``，那个标志在整个作业期间都是 True —— 「停」对采集
    完全无效，采集会继续往会话里写帧，而操作员以为已经停了。
    """
    import time

    from grasp.web import server as srv
    client.post("/api/capture/start", json={"frames": 2000, "augment": False})
    assert client.post("/api/stop").json()["stopped_job"] is True
    for _ in range(50):                       # 最长等 5s（帧间退出，通常 <0.2s）
        if not client.get("/api/train/status").json()["running"]:
            break
        time.sleep(0.1)
    st = client.get("/api/train/status").json()
    assert st["running"] is False, "软停止后采集循环仍在跑"
    assert srv.STATE.job.result.get("cancelled") is True, "中止必须显式标出来，不能当成采满"
