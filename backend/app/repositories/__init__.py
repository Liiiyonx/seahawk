"""数据访问层：把 SQL 与空间查询收敛在此，隔离 ORM 细节。

设计原则：service 层不直接写 SQL，repository 层不写业务逻辑。
"""

from datetime import datetime, timedelta
from typing import Any

from geoalchemy2.functions import ST_AsText, ST_DWithin, ST_MakePoint, ST_SetSRID, ST_SnapToGrid, ST_Transform, ST_X, ST_Y
from sqlalchemy import Float, Integer, String, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.event import Event, EventStatus, WasteClass
from app.models.task import Task, TaskStatus


class DeviceRepository:
    """设备数据访问。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_device_id(self, device_id: str) -> Device | None:
        result = await self.session.execute(
            select(Device).where(Device.device_id == device_id)
        )
        return result.scalar_one_or_none()

    async def list_devices(
        self,
        device_type: str | None = None,
        status: str | None = None,
    ) -> list[Device]:
        stmt = select(Device).order_by(Device.device_id)
        if device_type:
            stmt = stmt.where(Device.device_type == device_type)
        if status:
            stmt = stmt.where(Device.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_robots(self) -> list[Device]:
        return await self.list_devices(device_type="robot")

    async def upsert_heartbeat(
        self,
        device_id: str,
        status: str | None = None,
    ) -> None:
        """更新心跳时间与状态（设备上线/下线）。"""
        device = await self.get_by_device_id(device_id)
        if device is None:
            return
        device.last_heartbeat = datetime.now()
        if status:
            device.status = status

    async def find_nearest_available_robots(
        self,
        event_id: str,
        *,
        max_distance_m: int = 5000,
        limit: int = 5,
    ) -> list[tuple[Device, float]]:
        """KNN 就近查找可用机器人。

        使用 ST_DWithin 走 GiST 索引粗筛 + KNN 算子 <-> 排序，
        比 ORDER BY ST_Distance(...) 快得多（后者无法走索引）。

        返回：[(设备, 距离米), ...] 按距离升序。
        """
        event_geo = (
            select(Event.location)
            .where(Event.event_id == event_id)
            .scalar_subquery()
        )

        distance = func.ST_Distance(
            cast(Device.location, func.geography),
            cast(event_geo, func.geography),
        ).label("dist_m")

        stmt = (
            select(Device, distance)
            .where(
                and_(
                    Device.device_type == "robot",
                    Device.status == "online",
                    ST_DWithin(
                        cast(Device.location, func.geography),
                        cast(event_geo, func.geography),
                        max_distance_m,
                    ),
                )
            )
            .order_by(Device.location.op("<->")(event_geo))   # KNN 算子
            .limit(limit)
        )

        rows = await self.session.execute(stmt)
        return [(row[0], float(row[1])) for row in rows.all()]

    async def find_robot_by_id(self, robot_id: str) -> Device | None:
        """按编号查机器人（校验类型）。"""
        device = await self.get_by_device_id(robot_id)
        if device is not None and device.device_type != "robot":
            return None
        return device

    # 别名：语义更清晰
    get_robot_by_id = find_robot_by_id

    async def count_by_status(self) -> dict[str, int]:
        """按状态统计设备数（大屏指标用）。"""
        stmt = select(Device.status, func.count()).group_by(Device.status)
        rows = await self.session.execute(stmt)
        return {row[0]: int(row[1]) for row in rows.all()}


class EventRepository:
    """事件数据访问。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **fields: Any) -> Event:
        event = Event(**fields)
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_event_id(self, event_id: str) -> Event | None:
        result = await self.session.execute(
            select(Event).where(Event.event_id == event_id)
        )
        return result.scalar_one_or_none()

    async def exists_by_device_seq(self, device_id: str, seq: int) -> bool:
        """判重：同一设备同一序号是否已存在（防 MQTT 重传重复派单）。"""
        result = await self.session.execute(
            select(func.count()).select_from(Event).where(
                and_(Event.device_id == device_id, Event.seq == seq)
            )
        )
        return int(result.scalar_one()) > 0

    async def list_events(
        self,
        *,
        hours: int = 24,
        main_class: str | None = None,
        status: str | None = None,
        device_id: str | None = None,
        township: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Event], int]:
        since = datetime.now() - timedelta(hours=hours)
        conditions = [Event.event_time >= since]
        if main_class:
            conditions.append(Event.main_class == main_class)
        if status:
            conditions.append(Event.status == status)
        if device_id:
            conditions.append(Event.device_id == device_id)
        if township:
            conditions.append(Event.township == township)

        count_stmt = select(func.count()).select_from(Event).where(and_(*conditions))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            select(Event)
            .where(and_(*conditions))
            .order_by(Event.event_time.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all()), total

    async def heatmap_aggregate(
        self,
        *,
        hours: int = 24,
        grid_size: int = 500,
        main_class: str | None = None,
    ) -> list[dict[str, Any]]:
        """热力图网格聚合。

        关键：必须投影到 3857（米制），否则 ST_SnapToGrid 单位是「度」。
        返回密度而非总数 —— 否则大网格天然比小网格热，图会失真。
        """
        since = datetime.now() - timedelta(hours=hours)
        area_m2 = float(grid_size * grid_size)

        projected = ST_Transform(Event.location, 3857)
        grid = ST_SnapToGrid(projected, grid_size).label("grid")

        conditions = [Event.event_time >= since, Event.status != EventStatus.IGNORED]
        if main_class:
            conditions.append(Event.main_class == main_class)

        subq = (
            select(
                grid,
                func.count().label("cnt"),
                (func.count() / area_m2).label("density"),
                func.mode().within_group(Event.main_class).label("main_class"),
            )
            .where(and_(*conditions))
            .group_by(grid)
            .subquery()
        )

        stmt = select(
            ST_X(ST_Transform(subq.c.grid, 4326)).label("lng"),
            ST_Y(ST_Transform(subq.c.grid, 4326)).label("lat"),
            subq.c.cnt,
            subq.c.density,
            subq.c.main_class,
        ).order_by(subq.c.cnt.desc()).limit(2000)

        rows = await self.session.execute(stmt)
        return [
            {
                "lng": float(r.lng),
                "lat": float(r.lat),
                "count": int(r.cnt),
                "density": float(r.density),
                "main_class": r.main_class,
            }
            for r in rows.all()
            if r.lng is not None and r.lat is not None
        ]

    async def count_since(self, hours: int = 24, township: str | None = None) -> int:
        since = datetime.now() - timedelta(hours=hours)
        stmt = select(func.count()).select_from(Event).where(Event.event_time >= since)
        if township:
            stmt = stmt.where(Event.township == township)
        return int((await self.session.execute(stmt)).scalar_one())

    async def list_main_classes_for_events(self, event_ids: list[str]) -> set[str]:
        """批量取多条事件的主类别。

        供派单引擎做「类别匹配加权」：需要比对本次事件与机器人
        在途任务所属事件的类别是否相同。**必须批量查**，
        不能放进循环里逐条查（候选机器人 × 在途任务 = N×M 次查询）。
        """
        if not event_ids:
            return set()
        stmt = select(Event.main_class).where(Event.event_id.in_(event_ids))
        rows = await self.session.execute(stmt)
        return {r[0] for r in rows.all() if r[0] is not None}

    async def recent_for_dispatch(self, limit: int = 20) -> list[Event]:
        """取最近待派单的高优先级事件。"""
        stmt = (
            select(Event)
            .where(
                and_(
                    Event.status == EventStatus.NEW,
                    Event.main_class.in_(WasteClass.HIGH_PRIORITY),
                )
            )
            .order_by(Event.event_time.asc())   # 先到先处理
            .limit(limit)
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())


class TaskRepository:
    """任务数据访问。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **fields: Any) -> Task:
        task = Task(**fields)
        self.session.add(task)
        await self.session.flush()
        return task

    async def get_by_task_id(self, task_id: str) -> Task | None:
        result = await self.session.execute(
            select(Task).where(Task.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def has_active_task_for_event(self, event_id: str) -> bool:
        """防重复派单：该事件是否已有未完成任务。"""
        stmt = select(func.count()).select_from(Task).where(
            and_(
                Task.event_id == event_id,
                Task.status.in_(TaskStatus.ACTIVE),
            )
        )
        return int((await self.session.execute(stmt)).scalar_one()) > 0

    async def find_mergeable_task(
        self,
        *,
        lng: float,
        lat: float,
        window_minutes: int = 10,
        radius_m: int = 200,
    ) -> Task | None:
        """防抖合并：查找附近时间窗内的活跃任务，避免机器人被反复派往同一片水域。

        注意：合并逻辑必须在派单引擎层做，因为需要知道「当时有没有在途任务」。
        """
        since = datetime.now() - timedelta(minutes=window_minutes)
        point = ST_SetSRID(ST_MakePoint(lng, lat), 4326)

        stmt = (
            select(Task)
            .where(
                and_(
                    Task.status.in_(TaskStatus.ACTIVE),
                    Task.created_at >= since,
                    ST_DWithin(
                        cast(Task.target_location, func.geography),
                        cast(point, func.geography),
                        radius_m,
                    ),
                )
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        *,
        status: str | None = None,
        robot_id: str | None = None,
        township: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Task], int]:
        conditions = []
        if status:
            conditions.append(Task.status == status)
        if robot_id:
            conditions.append(Task.robot_id == robot_id)
        if township:
            conditions.append(Task.township == township)

        count_stmt = select(func.count()).select_from(Task)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all()), total

    async def list_active_tasks_for_robot(self, robot_id: str) -> list[Task]:
        stmt = select(Task).where(
            and_(Task.robot_id == robot_id, Task.status.in_(TaskStatus.ACTIVE))
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def list_by_status(self, status: str, limit: int = 50) -> list[Task]:
        """按状态取任务（供 ACK 超时回退与换车重派扫描）。"""
        stmt = select(Task).where(Task.status == status).limit(limit)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def count_by_status(self, township: str | None = None) -> dict[str, int]:
        stmt = select(Task.status, func.count()).group_by(Task.status)
        if township:
            stmt = stmt.where(Task.township == township)
        rows = await self.session.execute(stmt)
        return {row[0]: int(row[1]) for row in rows.all()}

    async def pending_count(self) -> int:
        stmt = select(func.count()).select_from(Task).where(
            Task.status == TaskStatus.PENDING
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def done_count_since(self, hours: int = 24, township: str | None = None) -> int:
        since = datetime.now() - timedelta(hours=hours)
        stmt = select(func.count()).select_from(Task).where(
            and_(Task.status == TaskStatus.DONE, Task.finished_at >= since)
        )
        if township:
            stmt = stmt.where(Task.township == township)
        return int((await self.session.execute(stmt)).scalar_one())

    async def sum_collected_weight(self, township: str | None = None) -> float:
        stmt = select(func.coalesce(func.sum(Task.collected_weight), 0))
        if township:
            stmt = stmt.where(Task.township == township)
        return float((await self.session.execute(stmt)).scalar_one())
