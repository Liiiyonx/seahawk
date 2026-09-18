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
from app.core.deps import CurrentUser, get_current_user
from app.core.exceptions import ApiResponse
from app.models.event import Event, WasteClass
from app.models.task import Task, TaskStatus
from app.repositories import DeviceRepository, EventRepository, TaskRepository

router = APIRouter()


@router.get("/dashboard", summary="大屏顶部指标卡")
async def dashboard_stats(
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
):
    """大屏实时指标：事件数、工单数、机器人状态、累计清理量。

    operator 角色只统计本辖区（township_scope），admin/viewer 看全部。
    """
    event_repo = EventRepository(session)
    task_repo = TaskRepository(session)
    device_repo = DeviceRepository(session)

    township = user.township_scope if user.role == "operator" else None
    event_count_24h = await event_repo.count_since(hours=24, township=township)
    task_counts = await task_repo.count_by_status(township=township)
    device_counts = await device_repo.count_by_status()
    collected = await task_repo.sum_collected_weight(township=township)
    done_24h = await task_repo.done_count_since(hours=24, township=township)

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
    user: CurrentUser = Depends(get_current_user),
):
    """按垃圾类别统计事件数（饼图数据源）。"""
    since = datetime.now() - timedelta(hours=hours)
    township = user.township_scope if user.role == "operator" else None
    conditions = [Event.event_time >= since]
    if township:
        conditions.append(Event.township == township)
    stmt = (
        select(Event.main_class, func.count().label("cnt"))
        .where(*conditions)
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
    user: CurrentUser = Depends(get_current_user),
):
    """近 N 小时事件趋势折线图数据源。"""
    since = datetime.now() - timedelta(hours=hours)
    township = user.township_scope if user.role == "operator" else None
    bucket = func.date_trunc("hour", Event.event_time).label("bucket")

    conditions = [Event.event_time >= since]
    if township:
        conditions.append(Event.township == township)
    stmt = (
        select(bucket, func.count().label("cnt"))
        .where(*conditions)
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


@router.get("/notifications", summary="站内通知（最近告警 + 工单动态）")
async def notifications(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """最近告警与工单动态的合并时间线，供顶栏通知铃铛使用。

    数据来自明细表（t_event / t_task），不是独立通知表——避免为「已读」
    状态引入一套新表；铃铛的未读判断由前端用「上次查看时间」本地完成。
    """
    since = datetime.now() - timedelta(hours=hours)

    ev_rows = await session.execute(
        select(
            Event.event_id,
            Event.main_class,
            Event.event_time,
            Event.device_id,
            Event.status,
        )
        .where(Event.event_time >= since)
        .order_by(Event.event_time.desc())
        .limit(limit)
    )

    tk_rows = await session.execute(
        select(
            Task.task_id,
            Task.status,
            Task.updated_at,
            Task.robot_id,
        )
        .where(Task.updated_at >= since)
        .order_by(Task.updated_at.desc())
        .limit(limit)
    )

    items: list[dict] = []
    for event_id, main_class, event_time, device_id, status in ev_rows.all():
        label = WasteClass.LABELS.get(main_class, main_class)
        items.append({
            "type": "event",
            "event_id": event_id,
            "main_class": main_class,
            "main_class_label": label,
            "title": f"识别到{label}，已进入事件中心",
            "time": event_time.isoformat() if event_time else None,
            "device_id": device_id,
            "status": status,
        })
    for task_id, status, updated_at, robot_id in tk_rows.all():
        items.append({
            "type": "task",
            "task_id": task_id,
            "status": status,
            "status_label": TaskStatus.LABELS.get(status, status),
            "title": f"工单 {task_id} 状态更新为 {TaskStatus.LABELS.get(status, status)}",
            "time": updated_at.isoformat() if updated_at else None,
            "robot_id": robot_id,
        })

    items.sort(key=lambda x: x["time"] or "", reverse=True)
    return ApiResponse.ok(items[:limit])
