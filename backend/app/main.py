"""探海灵眸 SeaSight — 后端应用入口。

启动流程（lifespan）：
    1. 初始化日志
    2. 连接 Redis
    3. 启动 MQTT 订阅
    4. 启动派单消费者（Redis Streams）
    5. 启动定时任务（补派、报表聚合）
    关闭时逆序释放资源。
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# ★ Windows 上 aiomqtt（基于 paho-mqtt）依赖事件循环的 add_reader/add_writer，
#   而 Windows 默认的 ProactorEventLoop 不支持这两个 API（抛 NotImplementedError），
#   导致 MQTT 客户端永远连不上、表现为「Operation timed out」。
#   必须在任何事件循环创建之前（uvicorn 启动前）切到 Selector 事件循环。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.v1 import api_router
from app.core.config import settings
from app.core.deps import close_redis, get_redis
from app.db.session import dispose_engine
from app.middleware.response import register_exception_handlers, trace_id_middleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期管理。"""
    logger.info(f"[启动] {settings.app_name} 环境={settings.app_env}")

    # ---------- 1. Redis ----------
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info(f"[启动] Redis 已连接 {settings.redis_host}:{settings.redis_port}")
    except Exception as exc:   # noqa: BLE001
        logger.warning(f"[启动] Redis 连接失败（{exc}），队列功能不可用")

    # ---------- 2. MQTT 订阅 ----------
    # ★ import 必须放在 try 里：把 import 留在 try 外面，就等于宣称
    #   「aiomqtt 缺失时能降级」但实际会直接崩在启动阶段 ——
    #   降级路径必须把「依赖不存在」和「依赖存在但连不上」一视同仁。
    mqtt_client = None
    try:
        from app.mqtt.client import mqtt_client
        from app.mqtt.handlers import HANDLERS

        await mqtt_client.start(HANDLERS)
    except Exception as exc:   # noqa: BLE001
        logger.warning(f"[启动] MQTT 启动失败（{exc}），设备上报通道不可用")

    # ---------- 3. 后台任务（派单消费者 + 补派定时器 + 报表聚合） ----------
    background_tasks: list[asyncio.Task[None]] = []
    try:
        from app.services.consumer import dispatch_consumer, pending_dispatcher
        from app.services.report import daily_report_worker

        background_tasks.append(asyncio.create_task(dispatch_consumer()))
        background_tasks.append(asyncio.create_task(pending_dispatcher()))
        background_tasks.append(asyncio.create_task(daily_report_worker()))
        logger.info("[启动] 后台任务已启动（派单消费者 + 补派定时器 + 报表聚合）")
    except Exception as exc:   # noqa: BLE001
        logger.warning(f"[启动] 后台任务启动失败（{exc}）")

    logger.info(f"[启动] 完成，接口文档：http://localhost:8000/docs")

    yield

    # ---------- 关闭 ----------
    # 每步都独立 try：启动阶段降级掉的组件（mqtt_client 可能是 None），
    # 关闭时不能反过来把进程打崩。
    logger.info("[关闭] 正在释放资源...")
    for task in background_tasks:
        task.cancel()
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)

    if mqtt_client is not None:
        try:
            await mqtt_client.stop()
        except Exception as exc:   # noqa: BLE001
            logger.warning(f"[关闭] MQTT 释放异常（{exc}）")

    for name, closer in (("Redis", close_redis), ("数据库引擎", dispose_engine)):
        try:
            await closer()
        except Exception as exc:   # noqa: BLE001
            logger.warning(f"[关闭] {name} 释放异常（{exc}）")

    logger.info("[关闭] 完成")


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    app = FastAPI(
        title="探海灵眸 SeaSight API",
        description=(
            "海漂垃圾「感知—决策—执行」一体化智能治理系统 · 后端接口\n\n"
            "**平台是中枢，不是显示屏** —— 识别到垃圾不是弹框，"
            "而是产生事件 → 触发派单 → 形成可追溯工单。"
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ---------- 中间件 ----------
    app.middleware("http")(trace_id_middleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------- 异常处理 ----------
    register_exception_handlers(app)

    # ---------- 路由 ----------
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    # ---------- 健康检查 ----------
    @app.get("/health", tags=["系统"], summary="健康检查")
    async def health() -> dict:
        """健康检查 —— 必须反映**真实降级状态**。

        早期实现无条件返回 status=ok，即使 Redis / MQTT / 数据库全挂。
        这对运维是误导：编排系统（compose healthcheck、K8s probe）
        会认为服务健康而不去重启，故障被静默吞掉。
        现在逐个探测依赖，整体状态取最差项：
            ok      全部正常
            degraded 部分不可用（服务仍能提供只读接口）
            down    核心依赖不可用
        """
        from app.ws.manager import ws_manager

        deps: dict[str, str] = {}

        # Redis
        try:
            redis = await get_redis()
            await asyncio.wait_for(redis.ping(), timeout=2.0)
            deps["redis"] = "ok"
        except Exception as exc:   # noqa: BLE001
            deps["redis"] = f"down: {type(exc).__name__}"

        # MQTT（只看客户端状态，不做网络探测）
        try:
            from app.mqtt.client import mqtt_client

            deps["mqtt"] = "ok" if mqtt_client.is_connected else "down"
        except Exception as exc:   # noqa: BLE001
            deps["mqtt"] = f"down: {type(exc).__name__}"

        # 数据库
        try:
            from sqlalchemy import text

            from app.db.session import get_session_factory

            async with get_session_factory()() as session:
                await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=2.0)
            deps["database"] = "ok"
        except Exception as exc:   # noqa: BLE001
            deps["database"] = f"down: {type(exc).__name__}"

        bad = [k for k, v in deps.items() if v != "ok"]
        status = "ok" if not bad else ("degraded" if len(bad) < len(deps) else "down")

        return {
            "status": status,
            "app": settings.app_name,
            "env": settings.app_env,
            "ws_connections": ws_manager.connection_count,
            "dependencies": deps,
        }

    @app.get("/", tags=["系统"], summary="服务信息")
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "description": "海漂垃圾智能治理系统后端",
            "docs": "/docs",
            "api_prefix": settings.api_v1_prefix,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
