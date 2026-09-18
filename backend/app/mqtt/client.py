"""MQTT 客户端：订阅设备上行消息，分发到处理器。

使用 aiomqtt（异步），在 FastAPI lifespan 中以 asyncio task 运行。
注意：不要在 MQTT 回调里直接做阻塞 DB 操作——通过 asyncio 调度。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import aiomqtt
from loguru import logger

from app.core.config import settings
from app.mqtt.topics import SUBSCRIBE_PLAN, Topics


class MqttClient:
    """MQTT 客户端封装。"""

    def __init__(self) -> None:
        self._client: aiomqtt.Client | None = None
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._connected = False
        self._handlers: dict[str, Any] = {}

    @property
    def is_connected(self) -> bool:
        """当前是否真的连上了 Broker。

        用于健康检查 —— 只看 `_running` 是不够的：`start()` 之后
        `_running` 立刻为 True，但此时可能还在重连、根本没握上手，
        健康检查会误报"正常"。
        """
        return self._running and self._connected

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    async def start(self, handlers: dict[str, Any]) -> None:
        """启动订阅循环（非阻塞）。"""
        self._handlers = handlers
        self._running = True
        self._task = asyncio.create_task(self._run_forever())
        logger.info("[MQTT] 客户端已启动")

    async def stop(self) -> None:
        """停止订阅。"""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[MQTT] 客户端已停止")

    # ------------------------------------------------------------------
    # 订阅循环（含断线重连）
    # ------------------------------------------------------------------
    async def _run_forever(self) -> None:
        """持续订阅，断线自动重连。"""
        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=settings.mqtt_host,
                    port=settings.mqtt_port,
                    username=settings.mqtt_username or None,
                    password=settings.mqtt_password or None,
                    identifier=settings.mqtt_client_id,
                    keepalive=settings.mqtt_keepalive,
                ) as client:
                    self._client = client
                    self._connected = True
                    logger.info(
                        f"[MQTT] 已连接 {settings.mqtt_host}:{settings.mqtt_port}"
                    )

                    # 订阅全部上行主题
                    for topic in SUBSCRIBE_PLAN:
                        await client.subscribe(topic, qos=1)
                        logger.info(f"[MQTT] 订阅 {topic}")

                    # 消息循环
                    async for message in client.messages:
                        try:
                            await self._dispatch(message)
                        except Exception as exc:   # noqa: BLE001
                            logger.exception(f"[MQTT] 消息处理异常：{exc}")

            except aiomqtt.MqttError as exc:
                self._connected = False
                if not self._running:
                    break
                logger.warning(f"[MQTT] 连接断开（{exc}），5 秒后重连")
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                self._connected = False
                break
            except Exception as exc:   # noqa: BLE001
                self._connected = False
                logger.exception(f"[MQTT] 未预期错误：{exc}")
                await asyncio.sleep(5)
            finally:
                # 退出 async with 后连接必然失效，别让 is_connected 假阳性
                self._connected = False

    # ------------------------------------------------------------------
    # 消息分发
    # ------------------------------------------------------------------
    async def _dispatch(self, message: aiomqtt.Message) -> None:
        """按主题路由到对应处理器。"""
        topic = str(message.topic)
        try:
            payload = json.loads(message.payload) if message.payload else {}
        except json.JSONDecodeError:
            logger.warning(f"[MQTT] 非法 JSON payload，topic={topic}")
            return

        # 通配主题 → handler 名
        handler_name = self._match_handler(topic)
        if handler_name is None:
            logger.debug(f"[MQTT] 无处理器匹配：{topic}")
            return

        handler = self._handlers.get(handler_name)
        if handler is None:
            logger.warning(f"[MQTT] 处理器未注册：{handler_name}")
            return

        await handler(topic, payload)

    def _match_handler(self, topic: str) -> str | None:
        """把具体主题映射到 SUBSCRIBE_PLAN 中声明的处理器。

        ★ 判据必须是**结构**（第 n 段是什么），不能是**总段数**。
        ────────────────────────────────────────────────────────
        这里踩过一个把整条作业链路掐断的坑：

            robot/{robot_id}/task/progress  → 4 段，parts[3] == "progress"
            robot/{robot_id}/cmd/ack        → 4 段，parts[3] == "ack"

        两个主题**段数完全相同**。早期用 `len(parts) == 5` 去认 cmd/ack，
        该条件永远不成立（通配符 `robot/+/cmd/ack` 展开就是 4 段），
        于是 ACK 消息一路落到 `return None`，被静默丢弃。

        后果不是"报个错"，而是：机器人回了 ACK → 平台没收到 →
        任务永远停在 assigned → 大屏上工单卡住不动。
        而 handle_robot_ack 本身写得好好的，测试也是绿的 ——
        **它只是永远不会被调用**。这类"路由不到"的缺陷没有任何日志，
        只有端到端演示时才以"业务不动了"的形式浮现。

        正确做法：逐段比对固定位置的常量，长度只在必要时做下界校验。
        """
        parts = topic.split("/")

        # ---- marine/{site}/{device}/<suffix> ----
        if len(parts) == 4 and parts[0] == "marine":
            suffix = parts[3]
            return {
                "event": "handle_event",
                "telemetry": "handle_telemetry",
                "status": "handle_device_status",
            }.get(suffix)

        # ---- robot/{robot_id}/<固定路径> ----
        # 注意：不判断总段数，而是看机器人 ID 之后的那两段
        if len(parts) == 4 and parts[0] == "robot":
            if parts[2] == "task" and parts[3] == "progress":
                return "handle_robot_progress"
            if parts[2] == "cmd" and parts[3] == "ack":
                return "handle_robot_ack"

        return None

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------
    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        *,
        qos: int = 1,
        retain: bool = False,
    ) -> bool:
        """发布消息（下发指令、派单）。"""
        if self._client is None:
            logger.error(f"[MQTT] 客户端未连接，发布失败：{topic}")
            return False
        try:
            await self._client.publish(
                topic,
                payload=json.dumps(payload, ensure_ascii=False, default=str),
                qos=qos,
                retain=retain,
            )
            logger.debug(f"[MQTT] 发布 {topic}")
            return True
        except Exception as exc:   # noqa: BLE001
            logger.error(f"[MQTT] 发布失败 {topic}：{exc}")
            return False

    async def publish_task(
        self, robot_id: str, task_id: str, lng: float, lat: float, priority: int
    ) -> bool:
        """下发派单任务。"""
        return await self.publish(
            Topics.robot_task(robot_id),
            {
                "task_id": task_id,
                "target": {"lng": lng, "lat": lat},
                "priority": priority,
                "issued_at": datetime.now().isoformat(),
            },
            qos=1,
        )


# 全局单例
mqtt_client = MqttClient()
