"""任务（工单）相关接口。"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.core.deps import CurrentUser, require_operator
from app.core.exceptions import ApiResponse
from app.models.task import ReviewResult, TaskStatus
from app.repositories import TaskRepository
from app.schemas import TaskCreate, TaskOut, TaskStatusUpdate
from app.services.dispatch import DispatchEngine
from app.ws.manager import ws_manager

router = APIRouter()


async def _to_out(session: AsyncSession, task) -> TaskOut:
    row = (
        await session.execute(
            select(func.ST_X(task.target_location), func.ST_Y(task.target_location))
        )
    ).first()
    lng = float(row[0]) if row and row[0] is not None else 0.0
    lat = float(row[1]) if row and row[1] is not None else 0.0

    return TaskOut(
        task_id=task.task_id,
        event_id=task.event_id,
        robot_id=task.robot_id,
        lng=lng,
        lat=lat,
        status=task.status,
        status_label=TaskStatus.LABELS.get(task.status),
        priority=task.priority,
        created_at=task.created_at,
        assigned_at=task.assigned_at,
        ack_at=task.ack_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        collected_weight=task.collected_weight,
        review_result=task.review_result,
        remark=task.remark,
    )


@router.post("", response_model=ApiResponse[TaskOut], summary="创建任务（人工指派）")
async def create_task(
    payload: TaskCreate,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(require_operator),
):
    """人工创建清理任务。

    自动派单走事件流程；本接口用于人工干预（如平台判读后手动派单）。
    需要 operator 或 admin 写权限。
    """
    from datetime import datetime
    import uuid

    repo = TaskRepository(session)
    task_id = f"tsk_{datetime.now():%Y%m%d}_{uuid.uuid4().hex[:6]}"

    task = await repo.create(
        task_id=task_id,
        event_id=payload.event_id,
        robot_id=payload.robot_id,
        target_location=f"SRID=4326;POINT({payload.target.lng} {payload.target.lat})",
        status=TaskStatus.PENDING,
        priority=payload.priority,
    )
    await session.flush()

    from app.services.audit import record_audit

    await record_audit(
        session,
        username=_user.username,
        role=_user.role,
        action="task_create",
        target_type="task",
        target_id=task_id,
        detail=f"目标=({payload.target.lng},{payload.target.lat}) 机器人={payload.robot_id or '待派单'}",
    )

    # 若指定了机器人，直接派单
    if payload.robot_id:
        engine = DispatchEngine(session)
        await engine.transition(task, TaskStatus.ASSIGNED, robot_id=payload.robot_id)

    return ApiResponse.ok(await _to_out(session, task), message="任务已创建")


@router.get("", response_model=ApiResponse[dict], summary="任务列表")
async def list_tasks(
    status: str | None = Query(None, description="状态筛选"),
    robot_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """分页查询任务列表（工单看板数据源）。"""
    repo = TaskRepository(session)
    tasks, total = await repo.list_tasks(
        status=status,
        robot_id=robot_id,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    items = [await _to_out(session, t) for t in tasks]
    return ApiResponse.ok(
        {
            "items": [i.model_dump() for i in items],
            "meta": {"total": total, "page": page, "page_size": page_size},
        }
    )


@router.patch("/{task_id}", response_model=ApiResponse[TaskOut], summary="更新任务状态")
async def update_task_status(
    task_id: str,
    payload: TaskStatusUpdate,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(require_operator),
):
    """更新任务状态（走状态机校验，非法跳转会被拒绝）。

    合法流转：pending→assigned→navigating→collecting→done
    需要 operator 或 admin 写权限。
    """
    from app.core.exceptions import NotFoundError

    repo = TaskRepository(session)
    task = await repo.get_by_task_id(task_id)
    if task is None:
        raise NotFoundError(f"任务 {task_id} 不存在", code=4001)

    engine = DispatchEngine(session)
    await engine.transition(
        task,
        payload.status,
        robot_id=payload.robot_id,
        collected_weight=payload.collected_weight,
        review_result=payload.review_result,
        remark=payload.remark,
    )
    await session.flush()

    from app.services.audit import record_audit

    await record_audit(
        session,
        username=_user.username,
        role=_user.role,
        action="task_status_update",
        target_type="task",
        target_id=task_id,
        detail=(
            f"状态 → {payload.status}"
            + (f" 打捞量={payload.collected_weight}kg" if payload.collected_weight is not None else "")
            + (f" 复核={payload.review_result}" if payload.review_result else "")
        ),
    )

    out = await _to_out(session, task)
    await ws_manager.push_task_update(out.model_dump())

    return ApiResponse.ok(out, message="状态已更新")


@router.get("/{task_id}", response_model=ApiResponse[TaskOut], summary="任务详情")
async def get_task(task_id: str, session: AsyncSession = Depends(get_session)):
    from app.core.exceptions import NotFoundError

    task = await TaskRepository(session).get_by_task_id(task_id)
    if task is None:
        raise NotFoundError(f"任务 {task_id} 不存在", code=4001)
    return ApiResponse.ok(await _to_out(session, task))


@router.post("/dispatch/pending", response_model=ApiResponse[dict], summary="补派待处理事件")
async def dispatch_pending(
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(require_operator),
):
    """扫描待派单事件并尝试补派。

    使用场景：机器人离线期间产生的事件；机器人重新上线后调用本接口补派。
    需要 operator 或 admin 写权限。
    """
    engine = DispatchEngine(session)
    created = await engine.assign_pending_tasks(limit=limit)
    return ApiResponse.ok(
        {
            "dispatched": len(created),
            "task_ids": [t.task_id for t in created],
        },
        message=f"完成补派 {len(created)} 个任务",
    )


_REVIEW_LABELS = {
    ReviewResult.PENDING: "待复核",
    ReviewResult.CONFIRMED: "确认清理",
    ReviewResult.NOT_FOUND: "到场未发现",
    ReviewResult.RECHECK: "需人工复查",
}


@router.get("/export", summary="导出工单 CSV")
async def export_tasks(
    status: str | None = Query(None),
    robot_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """导出工单为 CSV（带 UTF-8 BOM，Excel 打开中文不乱码）。"""
    from app.models.task import Task

    conditions = []
    if status:
        conditions.append(Task.status == status)
    if robot_id:
        conditions.append(Task.robot_id == robot_id)

    stmt = select(
        Task,
        func.ST_X(Task.target_location).label("lng"),
        func.ST_Y(Task.target_location).label("lat"),
    ).order_by(Task.created_at.desc())
    if conditions:
        from sqlalchemy import and_

        stmt = stmt.where(and_(*conditions))

    rows = (await session.execute(stmt)).all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["任务编号", "事件编号", "执行机器人", "状态", "优先级", "目标经度", "目标纬度",
                "打捞量(kg)", "复核结果", "创建时间", "完成时间"])
    for task, lng, lat in rows:
        w.writerow([
            task.task_id,
            task.event_id or "",
            task.robot_id or "",
            TaskStatus.LABELS.get(task.status, task.status),
            task.priority,
            f"{float(lng):.6f}" if lng is not None else "",
            f"{float(lat):.6f}" if lat is not None else "",
            f"{float(task.collected_weight):.2f}" if task.collected_weight is not None else "",
            _REVIEW_LABELS.get(task.review_result, task.review_result or ""),
            task.created_at.isoformat() if task.created_at else "",
            task.finished_at.isoformat() if task.finished_at else "",
        ])

    content = "\ufeff" + buf.getvalue()   # UTF-8 BOM，否则 Excel 中文乱码
    filename = f"工单台账_{datetime.now():%Y%m%d}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
