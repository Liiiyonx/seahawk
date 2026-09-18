"""报表定时聚合 —— 让 t_report_daily 真正由明细表生产。

背景（产品完整性缺陷）
----------------------
`t_report_daily` 曾经只由 `db/init/02_seed.sql` 灌入，代码里**没有任何
定时聚合任务** —— 系统跑一年，报表页的数字也一动不动。
更糟的是 `main.py` 的 docstring 早早就写了「启动定时任务（补派、报表聚合）」，
但实现只启动了补派，报表聚合从未接线：这是「声明 N 项、实现 N-1 项」
缺陷形状的又一例，而且因为是 docstring 与实现的错位，grep 都抓不到。

本模块补上缺失的最后一环：每天把明细表（t_event / t_task）聚合进宽表。

乡镇归属的单一真源
------------------
事件与任务都没有 `township` 字段，只有 POINT 坐标。乡镇归属按
「距离最近乡镇中心点」判定，中心点坐标在此处集中定义（`TOWNSHIPS`），
与 `db/init/02_seed.sql` 注释里的坐标、`frontend/src/utils/constants.js`
的 `TOWNSHIPS` 列表保持对账（有测试钉住，防止第五处定义漂移）。

coverage_area 为什么置 0
-------------------------
诚实边界：`coverage_area` 目前**没有可靠的真实数据源**。seed 里的
15000/12000 之类是拍脑袋数字，语义不明（「清扫面积」还是「到达范围」？
扫描宽度多少？）。轨迹点（t_track）稀疏，凹包面积不等于清扫覆盖面积。
与其造一个「看似真实」的数字，不如诚实置 0，把字段留给未来机器人
上报的真实清扫面积。event_count / task_count / done_count / collected_kg
这四个有可靠数据源，真实聚合。
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.geo import TOWNSHIPS, nearest_township
from app.db.session import get_session_factory
from app.models.event import Event
from app.models.misc import ReportDaily
from app.models.task import Task, TaskStatus

# 连江沿海乡镇中心点 —— 已抽到 app.core.geo（供事件/任务/报表三处共用，
# 避免循环 import）。这里 re-export 保持向后兼容。
# 每日聚合运行的时刻（本地时区），聚合「前一天」的数据
DAILY_RUN_HOUR = 1
DAILY_RUN_MINUTE = 0


async def aggregate_daily(session: AsyncSession, target_date: date) -> int:
    """把 target_date 一天的明细聚合进 t_report_daily，返回写入行数。

    幂等：同一 (stat_date, township, main_class) 重复聚合会 UPSERT 覆盖，
    不会产生重复行。
    """
    day_start = datetime.combine(target_date, time.min)
    day_end = day_start + timedelta(days=1)

    # ---------- 1) 事件数：按 (township, main_class) ----------
    ev_rows = await session.execute(
        select(
            Event.main_class,
            func.ST_X(Event.location).label("lng"),
            func.ST_Y(Event.location).label("lat"),
        ).where(Event.event_time >= day_start, Event.event_time < day_end)
    )
    event_counts: dict[tuple[str, str], int] = {}
    for main_class, lng, lat in ev_rows.all():
        if lng is None or lat is None:
            continue
        key = (nearest_township(float(lng), float(lat)), main_class)
        event_counts[key] = event_counts.get(key, 0) + 1

    # ---------- 2) 工单数 / 完成数 / 清理量：按 (township, main_class) ----------
    # 乡镇按 target_location（任务实际执行点）判定，比按事件点更贴近真实。
    # 人工建单（event_id 为 NULL）拿不到 main_class，这类任务不进分类报表，
    # 否则 (date, township, NULL) 会因 PostgreSQL 对 NULL 的等值语义而重复插行。
    tk_rows = await session.execute(
        select(
            Task.status,
            Task.collected_weight,
            func.ST_X(Task.target_location).label("lng"),
            func.ST_Y(Task.target_location).label("lat"),
            Event.main_class,
        )
        .outerjoin(Event, Event.event_id == Task.event_id)
        .where(Task.created_at >= day_start, Task.created_at < day_end)
    )
    task_agg: dict[tuple[str, str], dict[str, float]] = {}
    for status, weight, lng, lat, main_class in tk_rows.all():
        if lng is None or lat is None or main_class is None:
            continue
        key = (nearest_township(float(lng), float(lat)), main_class)
        row = task_agg.setdefault(key, {"task": 0, "done": 0, "kg": 0.0})
        row["task"] += 1
        if status == TaskStatus.DONE:
            row["done"] += 1
            row["kg"] += float(weight or 0)

    # ---------- 3) 合并 + UPSERT ----------
    keys = set(event_counts) | set(task_agg)
    for township, main_class in sorted(keys):
        ev = event_counts.get((township, main_class), 0)
        tk = task_agg.get((township, main_class), {"task": 0, "done": 0, "kg": 0.0})
        stmt = pg_insert(ReportDaily).values(
            stat_date=target_date,
            township=township,
            main_class=main_class,
            event_count=ev,
            task_count=int(tk["task"]),
            done_count=int(tk["done"]),
            collected_kg=tk["kg"],
            coverage_area=0,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_report_daily",
            set_={
                "event_count": stmt.excluded.event_count,
                "task_count": stmt.excluded.task_count,
                "done_count": stmt.excluded.done_count,
                "collected_kg": stmt.excluded.collected_kg,
                "coverage_area": stmt.excluded.coverage_area,
            },
        )
        await session.execute(stmt)

    return len(keys)


async def daily_report_worker() -> None:
    """每日定时聚合：凌晨 DAILY_RUN_HOUR 点聚合「前一天」的数据。

    启动时先补一次「今天」的数据（让演示/刚部署时报表立即可见），
    之后按天滚动。任何一次失败只记日志，不影响下一轮。
    """
    from app.db.session import get_session_factory as _factory

    logger.info("[报表] 报表聚合任务已启动")

    while True:
        try:
            now = datetime.now()
            next_run = (now + timedelta(days=1)).replace(
                hour=DAILY_RUN_HOUR, minute=DAILY_RUN_MINUTE, second=0, microsecond=0
            )
            await asyncio.sleep(max(1.0, (next_run - now).total_seconds()))

            target = date.today() - timedelta(days=1)
            async with _factory()() as session:
                n = await aggregate_daily(session, target)
                await session.commit()
            logger.info(f"[报表] 已聚合 {target} 报表，写入 {n} 行")
        except asyncio.CancelledError:
            logger.info("[报表] 报表聚合任务收到取消信号，退出")
            break
        except Exception as exc:   # noqa: BLE001
            logger.error(f"[报表] 聚合失败：{exc}")
            await asyncio.sleep(60)
