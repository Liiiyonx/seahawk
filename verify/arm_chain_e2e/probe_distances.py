"""为什么自动派单选了 RBT-001 而不是机械臂？算一下各自到事件点的距离。"""

from __future__ import annotations

import asyncio

import asyncpg

DSN = dict(host="127.0.0.1", port=5432, user="seasight", password="seasight", database="seasight")


async def main() -> None:
    conn = await asyncpg.connect(**DSN)
    ev = await conn.fetchrow(
        "select event_id, ST_X(location::geometry) as lng, ST_Y(location::geometry) as lat, "
        "status, main_class from t_event where event_id like 'EVT-E2E-%' order by id desc limit 1"
    )
    print("事件：", dict(ev) if ev else None)
    if ev:
        rows = await conn.fetch(
            """
            select device_id, status,
                   ST_X(location::geometry) as lng,
                   ST_Y(location::geometry) as lat,
                   ST_Distance(location::geography,
                               ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) as dist_m
            from t_device where device_type = 'robot'
            order by dist_m asc
            """,
            ev["lng"], ev["lat"],
        )
        for r in rows:
            print(f"  {r['device_id']:<12} {r['status']:<8} ({r['lng']:.5f}, {r['lat']:.5f}) "
                  f"距事件 {r['dist_m']:.1f} m")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
