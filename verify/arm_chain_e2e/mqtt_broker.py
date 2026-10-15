#!/usr/bin/env python3
"""本地临时 MQTT broker（amqtt）—— 本机没起 EMQX 时用它跑通平台↔树莓派链路。

为什么需要它：平台后端用 aiomqtt 连 broker，桥接层用 paho 连 broker。本机
（开发机）通常只有 Postgres/Redis 在跑，1883 上没有东西 —— 于是链路"看起来
是通的，其实一条报文都没走"。这个脚本提供一台**真 broker**（真实 MQTT 3.1.1
协议、真实 QoS1/PUBACK、真实 LWT/retained、真实通配符订阅），因此平台侧
aiomqtt 客户端与设备侧 paho 客户端都不需要改一行、也不需要打桩。

⚠️ 口径：这是**本机联调用的临时 broker**，允许匿名连接、不做主题鉴权。
它只用于验证链路与数据落库，不是生产部署方案（生产是 EMQX + 账号/ACL）。

用法：
    .venv-analysis\\Scripts\\python.exe verify\\arm_chain_e2e\\mqtt_broker.py --port 11883

就绪时会打印 ``BROKER READY 127.0.0.1:11883``（E2E 脚本据此判断可以继续）。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal

from amqtt.broker import Broker

DEFAULT_PORT = 11883


def build_config(port: int) -> dict:
    """最小可用配置：匿名可连、不做主题鉴权、不跑系统主题定时器。

    ★ 键名按 amqtt 0.12 的 ``BrokerConfig`` 数据类：``topic_check`` 是下划线，
      ``plugins`` 是必填项，``auth`` 是给匿名认证插件的配置。
    """
    return {
        "listeners": {
            "default": {
                "type": "tcp",
                "bind": f"127.0.0.1:{port}",
                "max_connections": 128,
            }
        },
        # sys 主题（$SYS/...）每 0 秒刷新 = 不发布，省得干扰观察者抓包
        "sys_interval": 0,
        "auth": {"allow-anonymous": True},
        "topic_check": {"enabled": False},
        "plugins": [
            "amqtt.plugins.authentication.AnonymousAuthPlugin",
            "amqtt.plugins.sys.broker.BrokerSysPlugin",
        ],
    }


async def serve(port: int) -> None:
    broker = Broker(build_config(port))
    await broker.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, AttributeError):  # Windows
            pass

    print(f"BROKER READY 127.0.0.1:{port}", flush=True)
    try:
        await stop.wait()
    finally:
        await broker.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="临时 MQTT broker（amqtt）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="[broker] %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(serve(args.port))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
