"""看看待派单事件积压情况（补派按 event_time ASC 取前 N 条）。"""

from __future__ import annotations

import asyncio

import asyncpg

DSN = dict(host="127.0.0.1", port=5432, user="seasight", password="seasight", database="seasight")


async def main() -> None:
    conn = await asyncpg.connect(**DSN)
    rows = await conn.fetch(
        "select main_class, status, count(*) as n from t_event group by 1,2 order by 1,2"
    )
    print("t_event 分布：")
    for r in rows:
        print(f"  {r['main_class']:<12} {r['status']:<10} {r['n']}")
    pending = await conn.fetchval(
        "select count(*) from t_event where status='new' and main_class in ('foam','fishing_gear')"
    )
    print("可被补派扫描的 new 高优先级事件：", pending)
    oldest = await conn.fetchrow(
        "select event_id, event_time from t_event where status='new' "
        "and main_class in ('foam','fishing_gear') order by event_time asc limit 1"
    )
    print("最早一条：", dict(oldest) if oldest else None)
    busy = await conn.fetch(
        "select device_id, status from t_device where device_type='robot' order by 1"
    )
    print("机器人：", [(r["device_id"], r["status"]) for r in busy])
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
