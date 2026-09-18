"""后端启动脚本（Windows 专用）。

为什么不用 `python -m uvicorn app.main:app`：
uvicorn 会**先创建事件循环、后 import app.main**，于是 main.py 里
`asyncio.set_event_loop_policy(...)` 执行时事件循环已经建好，设置无效。
aiomqtt（paho-mqtt）在 Windows 上依赖 `add_reader/add_writer`，
ProactorEventLoop 不支持 → MQTT 永远连不上。

本脚本在 import uvicorn 之前设置 Selector 事件循环策略，确保生效。
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    # loop="none" 让 uvicorn 用 asyncio 默认策略（即上面设的 Selector 策略），
    # 而不是 uvicorn 在 Windows 上硬编码的 ProactorEventLoop。
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, loop="none")
