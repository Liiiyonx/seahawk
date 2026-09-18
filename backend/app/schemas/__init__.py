"""Pydantic 出入参 Schema（API 契约）。

命名约定：
- XxxCreate  ：创建请求体
- XxxUpdate  ：部分更新请求体
- XxxOut     ：响应体
- XxxQuery   ：查询参数
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ============================================================
# 类别枚举（单一真源来自 app.models.event.WasteClass）
# ============================================================
# ★ 为什么在 schema 层用 Literal 硬约束，而不是放行任意字符串：
#   这个字段同时被三处消费 —— 前端配色（CLASS_ORDER 查表）、
#   派单白名单（WasteClass.HIGH_PRIORITY）、数据库 enum 列。
#   放行非法值的后果不是报错，而是**三处同时静默失效**：
#   配色回退成灰、派单条件不命中、入库被 DB 拒绝而整个事件丢失。
#   故在此收紧为四类枚举，让坏报文在入口就被挡下并留下明确错误。
#
#   契约依据：docs/mqtt-topics.md §5.1 声明 detections[].class 与
#   aggregate.main_class 均为 enum；db/init/01_schema.sql 的
#   waste_class_enum 同为这四个取值。
WasteClassLiteral = Literal["foam", "plastic", "fishing_gear", "other"]


# ============================================================
# 通用
# ============================================================
class GeoPoint(BaseModel):
    """经纬度坐标点。"""

    lng: float = Field(..., ge=-180, le=180, description="经度")
    lat: float = Field(..., ge=-90, le=90, description="纬度")


class BBox(BaseModel):
    """检测框：[x1, y1, x2, y2] 像素坐标。"""

    x1: int
    y1: int
    x2: int
    y2: int


class PageMeta(BaseModel):
    """分页元信息。"""

    total: int = 0
    page: int = 1
    page_size: int = 20

    @property
    def pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.page_size else 0


class PageResult(BaseModel):
    """分页结果。"""

    items: list[Any] = Field(default_factory=list)
    meta: PageMeta = Field(default_factory=PageMeta)


# ============================================================
# 事件
# ============================================================
class DetectionItem(BaseModel):
    """单个检测目标。"""

    cls: WasteClassLiteral = Field(..., alias="class", description="类别：foam/plastic/fishing_gear/other")
    confidence: float = Field(..., ge=0, le=1)
    bbox: list[int] = Field(..., min_length=4, max_length=4, description="[x1,y1,x2,y2]")

    model_config = ConfigDict(populate_by_name=True)


class EventAggregate(BaseModel):
    """边缘端聚合结果（平台不重复聚合，减少算力占用）。"""

    main_class: WasteClassLiteral
    count: int = Field(..., ge=1)
    max_confidence: float = Field(..., ge=0, le=1)


class EventIngest(BaseModel):
    """边缘盒上报的事件报文（MQTT / HTTP 共用）。

    对应 docs/mqtt-topics.md 中的事件 payload 契约。
    """

    event_id: str = Field(..., max_length=64, description="事件编号")
    device_id: str = Field(..., max_length=64)
    device_type: Literal["shore_camera", "drone", "robot"] = "shore_camera"
    timestamp: datetime
    location: GeoPoint
    detections: list[DetectionItem] = Field(default_factory=list)
    aggregate: EventAggregate
    evidence_url: str | None = None
    model_version: str | None = None
    seq: int = Field(..., ge=0, description="单调递增序号，用于判重")

    @field_validator("detections")
    @classmethod
    def _check_detections(cls, v: list[DetectionItem]) -> list[DetectionItem]:
        # 允许为空（aggregate 已给出结论），但不应超出合理上限
        if len(v) > 100:
            raise ValueError("单次上报目标数不应超过 100")
        return v


class EventOut(BaseModel):
    """事件响应体。"""

    model_config = ConfigDict(from_attributes=True)

    event_id: str
    device_id: str
    event_time: datetime
    lng: float
    lat: float
    main_class: str
    main_class_label: str | None = None
    det_count: int
    max_confidence: Decimal
    evidence_url: str | None
    model_version: str | None
    status: str
    status_label: str | None = None
    created_at: datetime


class EventIngestResult(BaseModel):
    """事件上报结果。"""

    accepted: bool
    event_id: str
    duplicate: bool = False
    task_created: bool = False
    task_id: str | None = None
    message: str = ""


# ============================================================
# 任务
# ============================================================
class TaskCreate(BaseModel):
    """人工创建任务。"""

    event_id: str | None = None
    robot_id: str | None = None
    target: GeoPoint
    priority: int = Field(default=5, ge=1, le=9)


class TaskStatusUpdate(BaseModel):
    """更新任务状态（走状态机校验）。"""

    status: Literal["pending", "assigned", "navigating", "collecting", "done", "cancelled"]
    robot_id: str | None = None
    collected_weight: float | None = Field(default=None, ge=0)
    review_result: Literal["pending", "confirmed", "not_found", "recheck"] | None = None
    remark: str | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    event_id: str | None
    robot_id: str | None
    lng: float
    lat: float
    status: str
    status_label: str | None = None
    priority: int
    created_at: datetime
    assigned_at: datetime | None
    ack_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    collected_weight: Decimal | None
    review_result: str | None
    remark: str | None


# ============================================================
# 设备 / 机器人
# ============================================================
class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    device_type: str
    name: str
    lng: float
    lat: float
    status: str
    last_heartbeat: datetime | None
    stream_url: str | None
    meta: dict[str, Any] = Field(default_factory=dict)


class RobotOut(BaseModel):
    """机器人实时状态（含三仓占用）。"""

    robot_id: str
    name: str
    lng: float
    lat: float
    status: str
    battery: int | None = None
    bins: dict[str, float] = Field(default_factory=dict)
    current_task_id: str | None = None
    last_heartbeat: datetime | None = None

    @property
    def available(self) -> bool:
        """是否可接单（供派单引擎参考）。"""
        return self.status == "online" and (self.battery or 0) >= 30


class RobotTelemetry(BaseModel):
    """机器人回传的遥测报文。"""

    robot_id: str
    timestamp: datetime
    location: GeoPoint
    status: Literal["idle", "navigating", "collecting", "returning", "error"] = "idle"
    battery: int = Field(..., ge=0, le=100)
    bins: dict[str, float] = Field(default_factory=dict, description="三仓占用率 0~1")
    task_id: str | None = None
    speed: float | None = None


# ============================================================
# 热力图
# ============================================================
class HeatmapCell(BaseModel):
    """热力图网格单元。"""

    lng: float
    lat: float
    count: int
    density: float = Field(..., description="单位面积事件密度（个/m²）")
    main_class: str | None = None


class HeatmapQuery(BaseModel):
    """热力图查询参数。"""

    hours: int = Field(default=24, ge=1, le=720, description="时间窗口（小时）")
    grid_size: int = Field(default=500, ge=100, le=5000, description="网格边长（米）")
    main_class: str | None = None


# ============================================================
# 报表
# ============================================================
class ReportDailyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stat_date: str
    township: str | None
    main_class: str | None
    main_class_label: str | None = None
    event_count: int
    task_count: int
    done_count: int
    collected_kg: Decimal
    coverage_area: Decimal


class DashboardStats(BaseModel):
    """大屏顶部指标卡。"""

    event_count_24h: int = 0
    pending_tasks: int = 0
    collecting_tasks: int = 0
    done_tasks_24h: int = 0
    robots_online: int = 0
    robots_total: int = 0
    collected_kg_total: float = 0.0
    devices_online: int = 0
    devices_total: int = 0


# ============================================================
# 认证
# ============================================================
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    full_name: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    full_name: str | None
    role: str
    township_scope: str | None


# ============================================================
# WebSocket 消息
# ============================================================
class WsMessage(BaseModel):
    """WebSocket 推送消息。

    type: new_event | task_update | robot_status | alert
    """

    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=datetime.now)
