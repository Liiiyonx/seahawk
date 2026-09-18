"""报表接口（治理量化报表）。

数据源为预聚合宽表 t_report_daily —— 由定时任务每日凌晨生成，
报表页只读宽表，即使事件量到百万级仍毫秒响应。
"""

from __future__ import annotations

from datetime import date, date as _date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.core.exceptions import ApiResponse
from app.models.event import WasteClass
from app.models.misc import ReportDaily

router = APIRouter()


@router.get("/daily", summary="日报表查询")
async def daily_report(
    days: int = Query(7, ge=1, le=90),
    township: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """查询日报表（读预聚合宽表，毫秒响应）。"""
    since = date.today() - timedelta(days=days)
    conditions = [ReportDaily.stat_date >= since]
    if township:
        conditions.append(ReportDaily.township == township)

    stmt = (
        select(ReportDaily)
        .where(and_(*conditions))
        .order_by(ReportDaily.stat_date.desc())
        .limit(500)
    )
    rows = await session.execute(stmt)

    items = [
        {
            "stat_date": str(r.stat_date),
            "township": r.township,
            "main_class": r.main_class,
            "main_class_label": WasteClass.LABELS.get(r.main_class or "", ""),
            "event_count": r.event_count,
            "task_count": r.task_count,
            "done_count": r.done_count,
            "collected_kg": float(r.collected_kg),
            "coverage_area": float(r.coverage_area),
        }
        for r in rows.scalars().all()
    ]
    return ApiResponse.ok(items)


@router.get("/summary", summary="报表汇总（按乡镇聚合）")
async def report_summary(
    days: int = Query(7, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
):
    """按乡镇聚合的治理成果汇总（报表页顶部卡片）。"""
    since = _date.today() - timedelta(days=days)
    stmt = (
        select(
            ReportDaily.township,
            func.sum(ReportDaily.event_count).label("events"),
            func.sum(ReportDaily.done_count).label("done"),
            func.sum(ReportDaily.collected_kg).label("kg"),
            func.sum(ReportDaily.coverage_area).label("area"),
        )
        .where(ReportDaily.stat_date >= since)
        .group_by(ReportDaily.township)
        .order_by(func.sum(ReportDaily.event_count).desc())
    )
    rows = await session.execute(stmt)

    items = [
        {
            "township": r.township or "未标注",
            "event_count": int(r.events or 0),
            "done_count": int(r.done or 0),
            "collected_kg": round(float(r.kg or 0), 2),
            "coverage_area": round(float(r.area or 0), 2),
        }
        for r in rows.all()
    ]
    return ApiResponse.ok(items)
