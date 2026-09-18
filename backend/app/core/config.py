"""探海灵眸 SeaSight — 应用配置。

所有配置从环境变量读取（支持 .env 文件），集中在此处管理。
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。字段名小写，环境变量大写（自动匹配）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 应用 ----------
    app_name: str = "SeaSight"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    secret_key: str = Field(default="dev-only-change-me", min_length=8)
    access_token_expire_minutes: int = 1440
    timezone: str = "Asia/Shanghai"

    # ---------- 数据库 ----------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "seasight"
    postgres_user: str = "seasight"
    postgres_password: str = "seasight"

    @property
    def database_url(self) -> str:
        """异步数据库连接串（asyncpg 驱动）。"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """同步连接串（Alembic 迁移用）。"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ---------- Redis ----------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ---------- MQTT ----------
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = "seasight"
    mqtt_password: str = "seasight"
    mqtt_client_id: str = "seasight-backend"
    mqtt_topic_prefix: str = "marine"
    mqtt_keepalive: int = 60

    # ---------- MinIO ----------
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_events: str = "events"
    minio_secure: bool = False

    # ---------- 流媒体 ----------
    stream_base_url: str = "http://localhost:1984"

    # ---------- AI 服务 ----------
    ai_service_url: str = "http://localhost:8081"
    ai_model_version: str = "det_v0.1.0"
    ai_timeout_seconds: int = 10

    # ---------- 通知外发 ----------
    # 企业微信机器人 webhook；为空 = 不启用告警外发（只落日志）。
    # 这是刻意的降级：告警推送失败绝不能阻塞事件派单主流程。
    wecom_webhook: str = ""
    wecom_mention_mobile: str = ""     # 告警 @ 的手机号（逗号分隔），可选

    # ---------- CORS ----------
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """支持逗号分隔字符串（环境变量）或列表。"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # ---------- 派单引擎参数 ----------
    dispatch_min_battery: int = 30            # 最低电量百分比
    dispatch_max_bin_usage: float = 0.8       # 最大仓容占用
    dispatch_ack_timeout_seconds: int = 15    # ACK 超时（秒）
    dispatch_merge_window_minutes: int = 10   # 同区域事件合并窗口
    dispatch_range_meters: int = 5000         # 派单搜索半径（米）

    # ---------- 事件队列 ----------
    redis_stream_events: str = "stream:events"       # 事件队列
    redis_stream_dispatch: str = "stream:dispatch"   # 派单队列
    redis_consumer_group: str = "dispatch-group"
    redis_dead_letter: str = "stream:dead_letter"    # 死信队列


@lru_cache
def get_settings() -> Settings:
    """获取配置单例（缓存，避免重复解析 .env）。"""
    return Settings()


settings = get_settings()
