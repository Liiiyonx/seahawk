"""手动控制接口自测（mock，不需要 ROS / 相机 / 硬件）。

## 为什么这些必须测

手动控制是**唯一会直接驱动物理机械臂**的界面。它出事不像识别错那样只是「没抓到」，
而是「臂撞到东西」或「按了半天没反应、然后突然连动几下」。所以这里锁五件事：

1. `/api/move_to` 的**绝对**与**增量**两种用法（方向键走增量）；
2. 俯仰角越界（>0 或 <-180）**必须 400** —— 越界不报错时 IK 会静默解出
   完全不同的姿态，比夹住更危险；
3. 目标不可达时**不更新记录位姿**（否则方向键连按会把目标越推越远，
   之后每次都失败，而操作员只看到「没反应」）；
4. 软停止后基准失效：再按方向键必须 **409 并给出可执行提示**，
   不能拿一个错误的基准乱动；
5. 姿态预设的增删/应用，以及**名称与脉宽的非法输入必须被挡住**。

这些口径与 `edge/grasp/presets.py` 的注释一一对应，改行为前先看那里。
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


@pytest.fixture()
def client(tmp_path: Path, monkeypatch) -> TestClient:
    # ★ 标定文件也重定向到临时目录（与下面 presets 同一条纪律）：否则测试会往仓库里
    #   写 edge/grasp/calibration.json —— 既写坏了开发者本机的真标定，又会让作业台
    #   把那份残留标定判成「真机标定」而不是演示标定，使演示口径的断言误失败。
    #   必须在 create_app **之前**打补丁：AppState 在构造时就会读标定。
    from grasp import calibration as calib_mod
    monkeypatch.setattr(calib_mod, "DEFAULT_CALIBRATION_PATH",
                        tmp_path / "calibration.json")
    cfg = load_config()
    app = create_app(cfg, mock=True)
    with TestClient(app) as c:
        # ★ 预设文件重定向到临时目录：否则测试会往仓库里写/删 presets.json，
        #   把操作员真存的预设搞掉（这是"测试污染现场数据"，不可接受）。
        from grasp.web import server as srv
        from grasp.presets import PresetStore
        srv.STATE.presets = PresetStore(tmp_path / "presets.json")
        yield c


# ----------------------------------------------------------------------
# /api/move_to
# ----------------------------------------------------------------------
def test_move_to_absolute_sets_target_and_reports_it(client: TestClient) -> None:
    r = client.post("/api/move_to", json={"x": 0.0, "y": 0.12, "z": 0.25, "pitch": -90}).json()
    assert r["ok"] is True and r["reachable"] is True
    assert r["target"] == pytest.approx({"x": 0.0, "y": 0.12, "z": 0.25, "pitch": -90})

    # 状态接口要能回显同一份目标（界面靠它显示"当前目标"）
    st = client.get("/api/status").json()
    assert st["manual_target"] == pytest.approx(r["target"])


def test_move_to_incremental_accumulates_on_recorded_target(client: TestClient) -> None:
    """方向键走的是纯增量：连续按要在**上一次结果**上叠加，而不是各自独立。"""
    client.post("/api/move_to", json={"x": 0.0, "y": 0.10, "z": 0.20, "pitch": -65})
    a = client.post("/api/move_to", json={"dy": 0.01}).json()["target"]
    b = client.post("/api/move_to", json={"dy": 0.01}).json()["target"]
    assert a["y"] == pytest.approx(0.11)
    assert b["y"] == pytest.approx(0.12)          # 累积，不是每次回到 0.10
    assert b["x"] == pytest.approx(0.0) and b["z"] == pytest.approx(0.20)

    c = client.post("/api/move_to", json={"dpitch": -10}).json()["target"]
    assert c["pitch"] == pytest.approx(-75)       # 俯仰也是增量


def test_move_to_absolute_and_delta_combine(client: TestClient) -> None:
    client.post("/api/move_to", json={"x": 0.0, "y": 0.10, "z": 0.20, "pitch": -65})
    r = client.post("/api/move_to", json={"y": 0.05, "dz": 0.02}).json()["target"]
    assert r["y"] == pytest.approx(0.05)          # 绝对值覆盖
    assert r["z"] == pytest.approx(0.22)          # 增量叠加


def test_move_to_rejects_pitch_out_of_vendor_range(client: TestClient) -> None:
    """俯仰角必须在 [-180, 0]：越界不报错时 IK 会静默解出别的姿态。"""
    for bad in (5.0, 30.0, -181.0, -400.0):
        resp = client.post("/api/move_to", json={"x": 0.0, "y": 0.1, "z": 0.2, "pitch": bad})
        assert resp.status_code == 400, f"pitch={bad} 应被拒绝"
        assert "俯仰角" in resp.json()["detail"]


def test_move_to_rejects_target_beyond_work_radius(client: TestClient) -> None:
    """工作半径上限来自 config 的 agent.work_radius（默认 0.20m）。"""
    resp = client.post("/api/move_to",
                       json={"x": 0.0, "y": 0.80, "z": 0.20, "pitch": -65})
    assert resp.status_code == 400
    assert "工作半径" in resp.json()["detail"]


# ----------------------------------------------------------------------
# /api/stop
# ----------------------------------------------------------------------
def test_stop_holds_current_positions_and_invalidates_baseline(client: TestClient) -> None:
    r = client.post("/api/stop").json()
    assert r["ok"] is True
    assert r["target_known"] is False
    # mock 下舵机回读有 6 个（夹爪 + 腕 + 4 关节）
    assert len(r["held"]) == 6
    assert client.get("/api/status").json()["manual_target"] is None


def test_move_after_stop_requires_absolute_coords(client: TestClient) -> None:
    """基准失效后按方向键（纯增量）必须 409，并告诉人怎么恢复。"""
    client.post("/api/stop")
    resp = client.post("/api/move_to", json={"dy": 0.01})
    assert resp.status_code == 409
    assert "基准已失效" in resp.json()["detail"]

    # 但给全绝对坐标是允许的 —— 那本身就是恢复基准的方式
    ok = client.post("/api/move_to",
                     json={"x": 0.0, "y": 0.10, "z": 0.20, "pitch": -65})
    assert ok.status_code == 200
    assert client.get("/api/status").json()["manual_target"]["y"] == pytest.approx(0.10)


def test_stop_cancels_running_job(client: TestClient) -> None:
    """软停止要能中止正在跑的作业（否则"停"只是把舵机按住，闭环还在继续发指令）。"""
    client.post("/api/place", json={"coord": [0.16, 0.02]})
    assert client.post("/api/grasp/start", json={"task_id": "tsk_stop"}).status_code == 200
    r = client.post("/api/stop").json()
    assert r["ok"] is True
    # 作业要么已经被中止，要么已经自然结束 —— 两者都不该还在 running
    assert r["stopped_job"] in (True, False)


# ----------------------------------------------------------------------
# /api/presets
# ----------------------------------------------------------------------
def test_presets_save_from_live_readback_and_apply(client: TestClient) -> None:
    # 不给 pose = 用当前舵机回读值存
    r = client.post("/api/presets", json={"name": "  相机朝下  "}).json()
    assert r["ok"] is True
    assert r["name"] == "相机朝下"                 # 前后空格被规整掉
    assert len(r["pose"]) == 6
    assert r["count"] == 1

    lst = client.get("/api/presets").json()
    assert lst["count"] == 1
    assert lst["items"][0]["name"] == "相机朝下"

    ap = client.post("/api/presets/apply", json={"name": "相机朝下"}).json()
    assert ap["ok"] is True and ap["target_known"] is False
    # 应用预设后笛卡尔基准失效（脉宽无法反推坐标）
    assert client.get("/api/status").json()["manual_target"] is None


def test_presets_explicit_pose_and_overwrite(client: TestClient) -> None:
    pose = {"1": 200, "2": 500, "3": 205, "4": 511, "5": 491, "6": 500}
    r = client.post("/api/presets", json={"name": "抓取预备", "pose": pose}).json()
    assert r["overwritten"] is False
    assert r["pose"] == pose
    # 同名再存 = 覆盖，不是报错
    r2 = client.post("/api/presets", json={"name": "抓取预备", "pose": {**pose, "1": 450}}).json()
    assert r2["overwritten"] is True and r2["count"] == 1


def test_presets_delete(client: TestClient) -> None:
    client.post("/api/presets", json={"name": "临时", "pose": {"1": 200}})
    r = client.post("/api/presets", json={"name": "临时", "delete": True}).json()
    assert r["ok"] is True and r["deleted"] is True and r["count"] == 0
    # 删不存在的要 400（静默成功会让人以为删掉了）
    assert client.post("/api/presets", json={"name": "临时", "delete": True}).status_code == 400


def test_presets_reject_bad_input(client: TestClient) -> None:
    # 空名
    assert client.post("/api/presets", json={"name": "   ", "pose": {"1": 200}}).status_code == 400
    # 脉宽越界
    assert client.post("/api/presets",
                       json={"name": "x", "pose": {"1": 1500}}).status_code == 400
    # 名字过长（界面是按钮文字，太长会撑坏布局）
    assert client.post("/api/presets",
                       json={"name": "a" * 30, "pose": {"1": 200}}).status_code == 400
    # 应用不存在的预设要 404
    assert client.post("/api/presets/apply", json={"name": "没有这个"}).status_code == 404


def test_preset_store_is_separate_from_calibration(client: TestClient) -> None:
    """预设必须存在 presets.json，不能混进 calibration.json。

    为什么：标定文件放的是设备的**物理事实**（重标定就失效），
    预设是**操作习惯**，不该因为重跑一次 9 点标定就被清掉。
    """
    lst = client.get("/api/presets").json()
    assert lst["path"].endswith("presets.json")
    assert "calibration" not in lst["path"]


# ----------------------------------------------------------------------
# 开机默认姿态（板子每次启动都会摆到它）
# ----------------------------------------------------------------------
def test_boot_default_set_and_export(client: TestClient, tmp_path: Path) -> None:
    """设开机默认要同时产出板上要读的 boot_pose.json。

    板子连不到开发机（AP 客户端隔离），所以只能由开发机把姿态**推**过去；
    推的那个文件就是这里导出的 boot_pose.json。导出失败必须让界面知道，
    否则操作员以为「已设开机默认」而板子上根本没生效。
    """
    import json

    client.post("/api/presets", json={"name": "开机位", "pose": {"1": 200, "3": 165}})
    r = client.post("/api/presets/boot", json={"name": "开机位"}).json()
    assert r["ok"] is True
    assert r["boot_default"] == "开机位"
    assert r["cleared"] is False

    export = r["export"]
    assert export["ok"] is True, export
    path = Path(export["path"])
    assert path.name == "boot_pose.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["name"] == "开机位"
    assert payload["pose"] == {"1": 200, "3": 165}

    # 状态接口要能看到，界面才好显示「开机默认：xxx」
    assert client.get("/api/status").json()["presets"]["boot_default"] == "开机位"


def test_boot_default_rejects_unknown_preset(client: TestClient) -> None:
    resp = client.post("/api/presets/boot", json={"name": "没有这个"})
    assert resp.status_code == 400
    assert "没有这个预设" in resp.json()["detail"]


def test_boot_default_is_preserved_across_preset_edits(client: TestClient) -> None:
    """★ 改别的预设时不能把开机默认真丢了。

    这类「存 A 时把 B 清掉」的 bug 很难被发现：设好开机默认、之后再存一个新
    预设，开机默认就悄悄没了 —— 而现场表现是「明明设过，开机怎么没摆位」。
    """
    client.post("/api/presets", json={"name": "开机位", "pose": {"1": 200}})
    client.post("/api/presets/boot", json={"name": "开机位"})

    # 再存一个新预设
    client.post("/api/presets", json={"name": "另一个", "pose": {"2": 500}})
    assert client.get("/api/presets").json()["boot_default"] == "开机位"

    # 删掉「另一个」也不该影响开机默认
    client.post("/api/presets", json={"name": "另一个", "delete": True})
    assert client.get("/api/presets").json()["boot_default"] == "开机位"


def test_deleting_boot_default_preset_clears_it(client: TestClient) -> None:
    """把开机默认那个预设删了 → 开机默认要一起清掉。

    否则会留下一个悬空引用，板子每次启动都读不到、每次都在 journal 里告警。
    """
    client.post("/api/presets", json={"name": "临时开机位", "pose": {"1": 200}})
    client.post("/api/presets/boot", json={"name": "临时开机位"})
    assert client.get("/api/presets").json()["boot_default"] == "临时开机位"

    client.post("/api/presets", json={"name": "临时开机位", "delete": True})
    lst = client.get("/api/presets").json()
    assert lst["boot_default"] is None
    # 导出的 boot_pose.json 也该被清掉，否则板子还在按旧姿态摆位
    import json
    from grasp.presets import PresetStore
    from grasp.web import server as srv
    export_path = Path(srv.STATE.presets.describe()["path"]).parent / "boot_pose.json"
    assert not export_path.exists(), "删掉开机默认预设后 boot_pose.json 应被清理"


def test_boot_default_clear_endpoint(client: TestClient) -> None:
    client.post("/api/presets", json={"name": "x", "pose": {"1": 200}})
    client.post("/api/presets/boot", json={"name": "x"})
    r = client.post("/api/presets/boot", json={"name": "   "}).json()
    assert r["cleared"] is True
    assert r["boot_default"] is None
    assert client.get("/api/presets").json()["boot_default"] is None


def test_board_apply_script_reads_same_shape(client: TestClient) -> None:
    """板上脚本读的 boot_pose.json 结构必须与作业台导出的**完全一致**。

    两边分别解析同一个文件、由不同的人在不同机器上写 —— 一旦字段名漂移，
    表现是「开机没摆位」而没有任何报错（板上脚本对缺字段是「跳过」而不是崩）。
    所以在这里把契约钉住：必须有 name / pose，且 pose 是 {舵机: 脉宽}。
    """
    import json
    import re

    script = (Path(__file__).resolve().parent.parent
              / "deploy" / "board_apply_boot_pose.py").read_text(encoding="utf-8")
    # 脚本读的字段
    assert 'raw.get("pose")' in script
    assert 'raw.get("name")' in script

    client.post("/api/presets", json={"name": "契约", "pose": {"1": 200, "5": 866}})
    r = client.post("/api/presets/boot", json={"name": "契约"}).json()
    payload = json.loads(Path(r["export"]["path"]).read_text(encoding="utf-8"))
    assert set(payload) >= {"name", "pose"}
    assert payload["pose"] == {"1": 200, "5": 866}
    # 舵机号必须是能转成 int 的字符串键（板上就是这么转的）
    for k, v in payload["pose"].items():
        int(k); int(v)


# ----------------------------------------------------------------------
# 页面接线
# ----------------------------------------------------------------------
def test_page_has_manual_control_tab_wired_to_api(client: TestClient) -> None:
    html = client.get("/").text
    assert 'data-view="manual"' in html
    assert 'id="view-manual"' in html
    for endpoint in ("/api/move_to", "/api/stop", "/api/presets", "/api/presets/apply"):
        assert endpoint in html, f"页面没有接到 {endpoint}"
    # 键盘控制的按键说明必须在页面上（否则没人知道能按方向键）
    assert "ArrowLeft" in html and "ArrowUp" in html
    # 安全口径必须写在页面上：软停止不是物理急停
    assert "不是物理急停" in html


# ----------------------------------------------------------------------
# /api/wrist —— 最前端关节（腕部旋转）
# ----------------------------------------------------------------------
def test_wrist_moves_within_measured_safe_range(client: TestClient) -> None:
    from grasp.web.server import WRIST_MAX, WRIST_MIN

    for pos in (WRIST_MIN, 400, 500, 620, WRIST_MAX):
        r = client.post("/api/wrist", json={"position": pos}).json()
        assert r["ok"] is True, f"pos={pos} 应被接受"
        assert r["position"] == pos
        assert r["servo_id"] == 2                      # 腕部就是 id2
        assert r["range"] == [WRIST_MIN, WRIST_MAX]
        assert r["center"] == 500


def test_wrist_rejects_out_of_range(client: TestClient) -> None:
    """越界必须 400：腕转到底会让夹爪带着相机一起甩，可能撞到自身或台面。

    这段行程（300~700）是**真机实测**出来的安全区，不是拍脑袋的默认值；
    没验证过的区间不能放开，所以宁可拒绝。
    """
    for bad in (0, 299, 701, 1000):
        resp = client.post("/api/wrist", json={"position": bad})
        assert resp.status_code == 400, f"pos={bad} 应被拒绝"
        assert "实测安全区" in resp.json()["detail"]
    # pydantic 的硬约束仍然兜底（0..1000 之外直接 422）
    assert client.post("/api/wrist", json={"position": 2000}).status_code == 422


def test_wrist_does_not_invalidate_cartesian_baseline(client: TestClient) -> None:
    """腕转只绕臂轴转向、不改变末端位置，所以位置控制的基准**应当保持有效**。

    这条与 /api/stop、/api/presets/apply 的行为刻意不同：那两者之后基准会失效。
    如果这里也失效，操作员每次调方向都得重填坐标，等于把最常用的动作搞残。
    """
    client.post("/api/move_to", json={"x": 0.0, "y": 0.12, "z": 0.25, "pitch": -65})
    before = client.get("/api/status").json()["manual_target"]
    assert before is not None

    client.post("/api/wrist", json={"position": 620})

    after = client.get("/api/status").json()["manual_target"]
    assert after is not None, "腕转后笛卡尔基准不该失效"
    assert after == pytest.approx(before)
    # 而且方向键（纯增量）仍然可用
    moved = client.post("/api/move_to", json={"dy": 0.01})
    assert moved.status_code == 200


def test_page_has_front_joint_control(client: TestClient) -> None:
    """最前端关节的控件必须在页面上，且放在手动控制页的**最前面**。"""
    html = client.get("/").text
    assert "/api/wrist" in html
    assert 'id="mc-front-val"' in html and 'id="mc-front-range"' in html
    assert "腕部旋转" in html and "最前端关节" in html
    # 位置顺序：前置关节卡片要出现在「安全」卡片之前
    assert html.index("最前端关节") < html.index('id="mc-note"')


# ----------------------------------------------------------------------
# /api/joint 与 /api/joints —— 骨架关节 id3~id6
# ----------------------------------------------------------------------
def test_joints_endpoint_exposes_measured_envelopes(client: TestClient) -> None:
    """行程口径只能有一份来源：界面从接口取，不能两边各写一份数字。"""
    r = client.get("/api/joints").json()
    assert r["ok"] is True
    got = {j["joint"]: j for j in r["joints"]}
    assert set(got) == {"J3", "J4", "J5", "J6"}
    # 关节名与舵机号的对应关系必须固定（J3→id3 … J6→id6）
    for key, sid in (("J3", 3), ("J4", 4), ("J5", 5), ("J6", 6)):
        assert got[key]["servo_id"] == sid
        assert got[key]["min"] < got[key]["max"]
        # 界面行程必须是实测极值的**内段**（外段舵机跟不上，会静默失真）
        assert got[key]["measured"][0] <= got[key]["min"]
        assert got[key]["measured"][1] >= got[key]["max"]


def test_joint_moves_within_envelope(client: TestClient) -> None:
    """每个关节都用**它自己行程的中点**测 —— 别用一个全局的 500。

    （写这条时踩过：J4 的行程是 520~980，500 落在区间外，
      测试自己先挂了。这恰好证明约束是真的在生效。）
    """
    envelopes = {j["joint"]: j for j in client.get("/api/joints").json()["joints"]}
    for joint, sid in (("J3", 3), ("J4", 4), ("J5", 5), ("J6", 6)):
        spec = envelopes[joint]
        mid = (spec["min"] + spec["max"]) // 2
        r = client.post("/api/joint", json={"joint": joint, "position": mid}).json()
        assert r["ok"] is True
        assert r["joint"] == joint
        assert r["servo_id"] == sid
        assert r["position"] == mid
        assert r["range"] == [spec["min"], spec["max"]]
    # 小写名字也要能用（界面上是 J3，但别让调用方踩大小写）
    assert client.post("/api/joint", json={"joint": "j3", "position": 400}).status_code == 200


def test_joint_rejects_out_of_envelope(client: TestClient) -> None:
    """越界必须 400：落在「跟不动」的区间时舵机会不到位但不报错，
    末端位置就与预期不符 —— 抓取会瞄错地方，比直接报错危险得多。"""
    cases = [("J3", 100), ("J3", 700), ("J4", 400), ("J4", 1000),
             ("J5", 300), ("J5", 900), ("J6", 200), ("J6", 800)]
    for joint, pos in cases:
        resp = client.post("/api/joint", json={"joint": joint, "position": pos})
        assert resp.status_code == 400, f"{joint} pos={pos} 应被拒绝"
        assert "实测可用" in resp.json()["detail"]
    # 未知关节名要 400，而不是静默不动作
    bad = client.post("/api/joint", json={"joint": "J9", "position": 500})
    assert bad.status_code == 400
    assert "J3" in bad.json()["detail"]


def test_joint_invalidates_cartesian_baseline(client: TestClient) -> None:
    """★ 与腕转刻意相反：耦合关节动过之后，笛卡尔基准**必须作废**。

    理由：id3~id6 决定夹爪在空间里的位置，动完它之后末端已经不在
    manual_target 记的那个点了。如果基准还留着，方向键就会从一个错误位置
    继续增量，越走越偏 —— 而且操作员完全看不出来。
    """
    client.post("/api/move_to", json={"x": 0.0, "y": 0.12, "z": 0.25, "pitch": -65})
    assert client.get("/api/status").json()["manual_target"] is not None

    r = client.post("/api/joint", json={"joint": "J3", "position": 450}).json()
    assert r["target_known"] is False
    assert client.get("/api/status").json()["manual_target"] is None

    # 基准没了之后，纯增量移动必须被拒并给出恢复方式
    inc = client.post("/api/move_to", json={"dy": 0.01})
    assert inc.status_code == 409
    assert "基准已失效" in inc.json()["detail"]


def test_page_has_skeleton_joint_control(client: TestClient) -> None:
    html = client.get("/").text
    assert "/api/joint" in html
    assert 'id="mc-jtabs"' in html and 'id="mc-joint-val"' in html
    assert 'id="mc-joint-range"' in html
    # 四个关节都要能选到
    for key in ("J3", "J4", "J5", "J6"):
        assert f"'{key}'" in html, f"页面缺少 {key} 的定义"
    # 必须点明「第三个关节」是哪个，否则操作员只能猜
    assert "第三个关节" in html
    # 默认选中的必须是 J3
    assert "selectJoint(3)" in html


# ----------------------------------------------------------------------
# 前端 api() 的方法契约 + 页面调用与后端路由的对齐
# ----------------------------------------------------------------------
def test_page_api_calls_match_route_methods(client: TestClient) -> None:
    """把前端 ``api()`` 的**方法契约**钉死，并检查页面调用与后端路由对齐。

    ## 为什么要这条（真实故障复盘）

    前端 `api(url, body)` 原来的实现是「不传 body 就发 GET」。而页面上有一批
    **无参数的动作端点**是按 `api('/api/home')` 这样调的 —— 全是 POST-only。
    结果这些按钮变成发 GET，服务端回 405，按钮**点了静默没反应**（只在控制台
    有一行错误，页面上什么都不显示）。受害按钮：回待命位、夹爪张开、
    夹爪自适应闭合、保存标定、评估当前模型。

    ## 这条测试为什么这样写

    第一次我写的是「解析页面调用 + 比对路由方法」的静态检查，并用「把 api()
    改回 GET 默认」做突变验证 —— **结果突变没被检出**：页面文本里
    `api('/api/home')` 这个写法在两种实现下完全一样，静态解析根本看不出
    运行时发的是 GET 还是 POST。那条检查只能发现「调用了一个方法不存在的
    端点」，抓不住这次的真 bug。

    所以真正有效的是两段断言：
      1. **契约**：页面里 `api()` 必须「无 body → POST」「'GET' → GET」。
         这才是那次故障的根因所在，改回去会立刻红灯。
      2. **对齐**：页面调用用到的端点，后端得真的支持对应方法
         （防以后加端点时把方法写错）。
    """
    import re

    from grasp.web import server as srv

    html = client.get("/").text

    # ---- 1) 契约：无 body 必须 POST，GET 必须显式 ----
    assert "body === 'GET'" in html, "api() 丢失了显式 GET 的口径"
    assert "opt = { method: 'POST' };" in html, (
        "api() 对「无 body」不再是 POST —— 这正是那次按钮静默失效的原因"
        "（无参数的动作端点都是 POST-only，发 GET 会 405）")

    # ---- 2) 对齐：页面调用 vs 实际注册的路由 ----
    app = srv.create_app(srv.load_config(), mock=True)
    routes: dict[str, set[str]] = {}
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if path and methods:
            routes.setdefault(path, set()).update(methods)

    calls = re.findall(r"api\('(/api/[^']*)'(?:\s*,\s*('[^']*'|\{[^}]*\}))?\s*\)", html)
    assert calls, "页面上找不到 api() 调用"

    problems: list[str] = []
    for path, arg in calls:
        clean = path.split("?")[0]
        if clean not in routes:
            continue                      # 带路径参数的模板跳过
        allowed = routes[clean]
        if arg == "'GET'":
            if "GET" not in allowed:
                problems.append(f"{path} 显式 GET，但路由只支持 {sorted(allowed)}")
        else:
            # 无 body（arg == ''）在**新契约**下也是 POST
            if "POST" not in allowed:
                problems.append(
                    f"{path}（arg={arg!r}）会发 POST，但路由只支持 {sorted(allowed)}"
                    f" —— 只读查询请显式写成 api('{path}', 'GET')")
    assert not problems, "前端调用与后端路由方法不匹配：\n  " + "\n  ".join(problems)


def test_pitch_keys_documented_match_actual_binding(client: TestClient) -> None:
    """键位**说明**和**实际绑定**必须一致。

    为什么单独测这一条：这两处是页面里两段独立的代码（一个在 HTML 的键位表里，
    一个在 JS 的 MC_KEYS 映射里）。改了绑定忘了改说明（或反过来），
    操作员会照着一个失效的键位表按键、然后以为「机械臂坏了」——
    这是纯靠肉眼 review 很容易漏、而现场代价很高的一类错。
    """
    import re

    html = client.get("/").text
    # 从 JS 映射里取实际绑定（形如 'j': 'pitchDown',）
    bindings = dict(re.findall(r"'([A-Za-z\[\]])'\s*:\s*'(pitchDown|pitchUp)'", html))
    assert bindings, "页面里找不到 pitch 的键位映射"
    down_keys = {k.lower() for k, v in bindings.items() if v == "pitchDown"}
    up_keys = {k.lower() for k, v in bindings.items() if v == "pitchUp"}
    assert down_keys, "没有绑定「更朝下」的键"
    assert up_keys, "没有绑定「更平」的键"

    # 键位表里 <kbd>X</kbd> 出现的键必须真的是 pitch 键之一
    legend = set(re.findall(r"<kbd>([A-Za-z])</kbd>", html))
    assert legend, "页面上没有 <kbd> 键位提示"
    # 至少每个 pitch 键在键位表里有体现（大小写不敏感）
    for key in (down_keys | up_keys):
        assert key in {k.lower() for k in legend}, f"键 {key} 有绑定但键位表里没写"

    # 说明文字里不能残留已经不用的方括号写法
    assert "<kbd>[</kbd>" not in html, "键位表里还留着旧的 [ ] 写法"
    assert "调 Pitch" in html or "Pitch −/+" in html, "缺少 Pitch 的英文标注"
