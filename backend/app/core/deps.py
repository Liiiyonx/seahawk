"""FastAPI 依赖注入。

集中管理可复用的依赖：数据库会话、Redis 客户端、当前用户等。
"""

from __future__ import annotations

from typing import Annotated, AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Depends, Header
from redis.asyncio import Redis

from app.core.config import settings
from app.core.exceptions import AppException, ErrorCode

# ----------------------------------------------------------------------
# Redis 客户端（懒加载单例）
# ----------------------------------------------------------------------
_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """获取 Redis 客户端（全局复用连接池）。"""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
    return _redis_client


async def get_redis_dep() -> AsyncGenerator[Redis, None]:
    """FastAPI 依赖：Redis 客户端。"""
    yield await get_redis()


async def close_redis() -> None:
    """应用关闭时释放 Redis 连接。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None


# ----------------------------------------------------------------------
# 当前用户（简化版：从 Header 读角色；生产环境换成 JWT 校验）
# ----------------------------------------------------------------------
class CurrentUser:
    """当前登录用户上下文。"""

    def __init__(self, username: str, role: str, township_scope: str | None = None) -> None:
        self.username = username
        self.role = role
        self.township_scope = township_scope

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def can_write(self) -> bool:
        return self.role in ("admin", "operator")


async def get_current_user(
    x_user: Annotated[str | None, Header(alias="X-User")] = None,
    x_role: Annotated[str | None, Header(alias="X-Role")] = None,
    x_scope: Annotated[str | None, Header(alias="X-Scope")] = None,
) -> CurrentUser:
    """获取当前用户。

    简化实现：从请求头读取（便于开发与演示）。
    接入正式认证时，替换为 JWT 解析即可，调用方无需改动。
    """
    return CurrentUser(
        username=x_user or "anonymous",
        role=x_role or "viewer",
        township_scope=x_scope,
    )


async def require_operator(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """要求操作员及以上权限。"""
    if not user.can_write:
        raise AppException(
            code=ErrorCode.FORBIDDEN,
            message="当前账号无写权限（需要 operator 或 admin）",
            http_status=403,
        )
    return user
