"""任务（工单）相关接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.core.exceptions import ApiResponse
from app.models.task import TaskStatus
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
):
    """人工创建清理任务。

    自动派单走事件流程；本接口用于人工干预（如平台判读后手动派单）。
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
):
    """更新任务状态（走状态机校验，非法跳转会被拒绝）。

    合法流转：pending→assigned→navigating→collecting→done
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
):
    """扫描待派单事件并尝试补派。

    使用场景：机器人离线期间产生的事件；机器人重新上线后调用本接口补派。
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
