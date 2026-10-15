"""broker 冒烟测试：起临时 broker，用 paho 连上、订marine/#、发一条、收回一条。

用法：
    .venv-analysis\\Scripts\\python.exe verify\\arm_chain_e2e\\smoke_broker.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

HERE = Path(__file__).resolve().parent
PY = Path(sys.executable)
PORT = 11885


def main() -> int:
    proc = subprocess.Popen(
        [str(PY), str(HERE / "mqtt_broker.py"), "--port", str(PORT)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
    )
    try:
        line = ""
        deadline = time.time() + 20
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            print("broker:", line.rstrip())
            if "BROKER READY" in line:
                break
        else:
            print("broker 未就绪")
            return 1

        got: list[tuple[str, str]] = []
        client = mqtt.Client(client_id="smoke")
        client.on_message = lambda _c, _u, m: got.append((m.topic, m.payload.decode()))
        client.connect("127.0.0.1", PORT, 10)
        client.loop_start()
        client.subscribe("marine/#", 1)
        time.sleep(0.5)
        client.publish("marine/lianjiang/RBT-ARM-01/telemetry", '{"device_id":"RBT-ARM-01"}', qos=1)
        time.sleep(1.5)
        client.loop_stop()
        client.disconnect()
        print("收到消息:", got)
        assert got and got[0][0] == "marine/lianjiang/RBT-ARM-01/telemetry", "通配符订阅或 QoS1 未生效"
        print("SMOKE OK")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
