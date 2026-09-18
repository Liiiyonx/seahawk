"""统计接口（大屏指标卡与类别分布）。

与 reports.py 分开的原因：
stats 服务于「大屏实时」，reports 服务于「治理报表」，
两者的数据源与刷新频率完全不同（前者查明细、后者读预聚合宽表）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.core.exceptions import ApiResponse
from app.models.event import Event, WasteClass
from app.repositories import DeviceRepository, EventRepository, TaskRepository

router = APIRouter()


@router.get("/dashboard", summary="大屏顶部指标卡")
async def dashboard_stats(session: AsyncSession = Depends(get_session)):
    """大屏实时指标：事件数、工单数、机器人状态、累计清理量。"""
    event_repo = EventRepository(session)
    task_repo = TaskRepository(session)
    device_repo = DeviceRepository(session)

    event_count_24h = await event_repo.count_since(hours=24)
    task_counts = await task_repo.count_by_status()
    device_counts = await device_repo.count_by_status()
    collected = await task_repo.sum_collected_weight()
    done_24h = await task_repo.done_count_since(hours=24)

    robots = await device_repo.list_robots()
    robots_online = sum(1 for d in robots if d.status == "online")

    return ApiResponse.ok(
        {
            "event_count_24h": event_count_24h,
            "pending_tasks": task_counts.get("pending", 0),
            "collecting_tasks": task_counts.get("collecting", 0)
            + task_counts.get("navigating", 0),
            "done_tasks_24h": done_24h,
            "robots_online": robots_online,
            "robots_total": len(robots),
            "collected_kg_total": round(collected, 2),
            "devices_online": device_counts.get("online", 0),
            "devices_total": sum(device_counts.values()),
        }
    )


@router.get("/classes", summary="类别分布统计")
async def class_distribution(
    hours: int = Query(24, ge=1, le=720),
    session: AsyncSession = Depends(get_session),
):
    """按垃圾类别统计事件数（饼图数据源）。"""
    since = datetime.now() - timedelta(hours=hours)
    stmt = (
        select(Event.main_class, func.count().label("cnt"))
        .where(Event.event_time >= since)
        .group_by(Event.main_class)
        .order_by(func.count().desc())
    )
    rows = await session.execute(stmt)

    data = [
        {
            "main_class": row[0],
            "label": WasteClass.LABELS.get(row[0], row[0]),
            "count": int(row[1]),
        }
        for row in rows.all()
    ]
    return ApiResponse.ok(data)


@router.get("/trend", summary="事件趋势（按小时）")
async def event_trend(
    hours: int = Query(24, ge=1, le=168),
    session: AsyncSession = Depends(get_session),
):
    """近 N 小时事件趋势折线图数据源。"""
    since = datetime.now() - timedelta(hours=hours)
    bucket = func.date_trunc("hour", Event.event_time).label("bucket")

    stmt = (
        select(bucket, func.count().label("cnt"))
        .where(Event.event_time >= since)
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = await session.execute(stmt)

    return ApiResponse.ok(
        [
            {"time": row[0].isoformat() if row[0] else None, "count": int(row[1])}
            for row in rows.all()
        ]
    )
