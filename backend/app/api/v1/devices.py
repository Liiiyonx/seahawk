"""设备与机器人相关接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.core.exceptions import ApiResponse
from app.repositories import DeviceRepository, TaskRepository
from app.schemas import DeviceOut, RobotOut

router = APIRouter()


async def _to_device_out(session: AsyncSession, device) -> DeviceOut:
    row = (
        await session.execute(
            select(func.ST_X(device.location), func.ST_Y(device.location))
        )
    ).first()
    lng = float(row[0]) if row and row[0] is not None else 0.0
    lat = float(row[1]) if row and row[1] is not None else 0.0
    return DeviceOut(
        device_id=device.device_id,
        device_type=device.device_type,
        name=device.name,
        lng=lng,
        lat=lat,
        status=device.status,
        last_heartbeat=device.last_heartbeat,
        stream_url=device.stream_url,
        meta=device.meta or {},
    )


@router.get("", response_model=ApiResponse[list], summary="设备列表")
async def list_devices(
    device_type: str | None = Query(None, description="shore_camera / drone / robot"),
    status: str | None = Query(None, description="online / offline / fault"),
    session: AsyncSession = Depends(get_session),
):
    """查询设备列表（设备管理页数据源）。"""
    devices = await DeviceRepository(session).list_devices(
        device_type=device_type, status=status
    )
    items = [await _to_device_out(session, d) for d in devices]
    return ApiResponse.ok([i.model_dump() for i in items])


@router.get("/{device_id}", response_model=ApiResponse[DeviceOut], summary="设备详情")
async def get_device(device_id: str, session: AsyncSession = Depends(get_session)):
    from app.core.exceptions import NotFoundError

    device = await DeviceRepository(session).get_by_device_id(device_id)
    if device is None:
        raise NotFoundError(f"设备 {device_id} 不存在", code=2001)
    return ApiResponse.ok(await _to_device_out(session, device))


@router.get("/{device_id}/stream", response_model=ApiResponse[dict], summary="获取视频流地址")
async def get_stream_url(device_id: str, session: AsyncSession = Depends(get_session)):
    """获取设备视频流播放地址。

    返回 go2rtc 转发地址；前端用 mpegts.js 播放 HTTP-FLV，
    或直接用 WebRTC（延迟更低）。
    """
    from app.core.exceptions import NotFoundError

    device = await DeviceRepository(session).get_by_device_id(device_id)
    if device is None:
        raise NotFoundError(f"设备 {device_id} 不存在", code=2001)

    # go2rtc 标准播放地址
    stream_key = device.meta.get("stream_key") if device.meta else None
    if not stream_key:
        stream_key = device_id.lower().replace("_", "")

    return ApiResponse.ok(
        {
            "device_id": device_id,
            "flv_url": f"{settings.stream_base_url}/api/stream.flv?src={stream_key}",
            "webrtc_url": f"{settings.stream_base_url}/api/webrtc?src={stream_key}",
            "hls_url": f"{settings.stream_base_url}/api/stream.m3u8?src={stream_key}",
        }
    )
