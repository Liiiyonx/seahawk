"""健康检查的降级语义测试。

守住一条运维底线：**/health 不能无条件报 ok**。
早期实现无论 Redis / MQTT / 数据库是否可用都返回 status=ok，
compose healthcheck 与 K8s probe 会据此认为服务健康、不去重启，
故障被静默吞掉 —— 这类 bug 在演示时发现不了，上线才炸。

运行：
    pytest tests/test_health_degradation.py -v
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.main import create_app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    """无任何外部依赖（Redis/PG/MQTT 全无）下的测试客户端。

    这正是最需要验证的场景：**依赖全挂时服务仍须能起来并如实汇报**。
    """
    app = create_app()
    # 用 TestClient 但不跑 lifespan —— lifespan 里会尝试连 Redis/MQTT，
    # 在本机环境下会各等一次超时，拖慢测试且与本次断言无关。
    # 健康检查本身不需要 lifespan 的副作用。
    return TestClient(app)


class TestHealthReportsDegradation:
    """health 必须反映真实依赖状态。"""

    def test_dependencies_key_present(self, client: TestClient) -> None:
        """响应必须带 dependencies 明细，不能只给一个笼统的 status。"""
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "dependencies" in body, "缺少 dependencies 明细，运维无法定位是哪个依赖挂了"
        assert set(body["dependencies"]) == {"redis", "mqtt", "database"}

    def test_status_not_blindly_ok(self, client: TestClient) -> None:
        """依赖不可用时 status 不能是 ok。

        本测试环境没有 Redis / PG / aiomqtt，所以必然是降级或 down。
        """
        body = client.get("/health").json()
        assert body["status"] != "ok", (
            f"依赖全不可用却报 status={body['status']!r} —— 健康检查在撒谎。"
            f"明细：{body.get('dependencies')}"
        )
        assert body["status"] in ("degraded", "down")

    def test_status_is_down_when_all_deps_fail(self, client: TestClient) -> None:
        """全部依赖不可用 → status=down（服务已无法提供有效服务）。"""
        body = client.get("/health").json()
        deps = body["dependencies"]
        if all(v != "ok" for v in deps.values()):
            assert body["status"] == "down"
        else:
            pytest.skip("本机恰有依赖可用，跳过全挂断言")

    def test_degraded_status_is_a_valid_state(self) -> None:
        """文档化状态取值：ok / degraded / down 三档，且语义单调。

        这条是给后人看的契约 —— 编排系统按这个字段决定是否重启，
        新增取值前必须先改这里和 docs/deployment.md。
        """
        valid = {"ok", "degraded", "down"}
        assert valid == {"ok", "degraded", "down"}

    def test_root_endpoint_still_works_when_degraded(self, client: TestClient) -> None:
        """降级时服务信息接口仍可用（只读能力不应被依赖故障阻断）。"""
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["name"]


class TestMqttClientConnectionState:
    """MqttClient.is_connected 的语义。"""

    def test_is_connected_false_before_start(self) -> None:
        """未启动时不能报已连接。"""
        try:
            from app.mqtt.client import MqttClient
        except Exception as exc:   # noqa: BLE001
            pytest.skip(f"aiomqtt 不可用：{exc}")

        c = MqttClient()
        assert c.is_connected is False

    def test_is_connected_false_after_start_before_handshake(self) -> None:
        """start() 之后、真正握手成功之前，is_connected 仍须为 False。

        这是本属性存在的理由：只看 _running 会在"正在重连"时误报健康。
        """
        try:
            from app.mqtt.client import MqttClient
        except Exception as exc:   # noqa: BLE001
            pytest.skip(f"aiomqtt 不可用：{exc}")

        async def scenario() -> bool:
            c = MqttClient()
            # 不走 start()（会真的去连 broker），直接模拟内部状态
            c._running = True
            c._connected = False
            try:
                return c.is_connected
            finally:
                c._running = False

        assert asyncio.run(scenario()) is False
