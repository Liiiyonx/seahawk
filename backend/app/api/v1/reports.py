"""报表接口（治理量化报表）。

数据源为预聚合宽表 t_report_daily —— 由定时任务每日凌晨生成，
报表页只读宽表，即使事件量到百万级仍毫秒响应。
"""

from __future__ import annotations

from datetime import date, date as _date, datetime, timedelta

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.core.exceptions import ApiResponse
from app.models.event import WasteClass
from app.models.misc import ReportDaily

router = APIRouter()


class AggregateRequest(BaseModel):
    """手动触发报表聚合的请求体。

    target_date 缺省为今天；传 YYYY-MM-DD 可回溯聚合历史某天
    （例如补跑、或验证聚合与 seed 口径一致）。
    """

    target_date: str | None = None


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


@router.post("/aggregate", summary="手动触发报表聚合")
async def aggregate_now(
    payload: AggregateRequest | None = None,
    session: AsyncSession = Depends(get_session),
):
    """把明细表（t_event / t_task）聚合进 t_report_daily。

    定时任务每日凌晨自动跑；本接口用于手动触发（演示、补跑、验证）。
    幂等：重复聚合同一日期会 UPSERT 覆盖，不会产生重复行。
    """
    from app.services.report import aggregate_daily

    target = date.today()
    if payload and payload.target_date:
        try:
            target = datetime.strptime(payload.target_date, "%Y-%m-%d").date()
        except ValueError:
            return ApiResponse.fail(code=4002, message="target_date 格式应为 YYYY-MM-DD")

    rows = await aggregate_daily(session, target)
    await session.commit()
    return ApiResponse.ok(
        {"stat_date": str(target), "rows": rows},
        message=f"已聚合 {target} 报表，写入/更新 {rows} 行",
    )


@router.get("/export", summary="导出日报表 CSV")
async def export_report(
    days: int = Query(30, ge=1, le=90),
    township: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """导出治理日报表为 CSV（带 UTF-8 BOM，Excel 打开中文不乱码）。"""
    since = date.today() - timedelta(days=days)
    conditions = [ReportDaily.stat_date >= since]
    if township:
        conditions.append(ReportDaily.township == township)

    stmt = (
        select(ReportDaily)
        .where(and_(*conditions))
        .order_by(ReportDaily.stat_date.desc(), ReportDaily.township)
    )
    rows = (await session.execute(stmt)).scalars().all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["统计日期", "乡镇", "垃圾类别", "事件数", "工单数", "完成数", "清理量(kg)", "覆盖面积(㎡)"])
    for r in rows:
        w.writerow([
            str(r.stat_date),
            r.township or "",
            WasteClass.LABELS.get(r.main_class or "", "") or (r.main_class or ""),
            r.event_count,
            r.task_count,
            r.done_count,
            f"{float(r.collected_kg):.2f}",
            f"{float(r.coverage_area):.2f}",
        ])

    content = "\ufeff" + buf.getvalue()   # UTF-8 BOM，否则 Excel 中文乱码
    filename = f"治理日报_{date.today().isoformat()}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
