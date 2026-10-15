"""看最近几秒的机械臂活动（验证看门狗重启后链路是否恢复）。"""

from __future__ import annotations

import asyncio
import json

import asyncpg

DSN = dict(host="127.0.0.1", port=5432, user="seasight", password="seasight", database="seasight")


async def main() -> None:
    conn = await asyncpg.connect(**DSN)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads,
                              schema="pg_catalog")
    rows = await conn.fetch(
        "select task_id, status, created_at from t_task where robot_id = 'RBT-ARM-01' "
        "order by id desc limit 4"
    )
    print("最近工单：")
    for r in rows:
        print(f"  {r['task_id']} {r['status']:<10} {r['created_at']}")
    tracks = await conn.fetch(
        "select id, recorded_at, (servo_telemetry is not null) as has_servo, task_id "
        "from t_track where robot_id = 'RBT-ARM-01' order by id desc limit 4"
    )
    print("最近轨迹：")
    for r in tracks:
        print(f"  #{r['id']} {r['recorded_at']} 舵机={'有' if r['has_servo'] else '无'} task={r['task_id']}")
    dev = await conn.fetchrow(
        "select status, last_heartbeat, meta from t_device where device_id = 'RBT-ARM-01'")
    print(f"设备：{dev['status']} 心跳 {dev['last_heartbeat']} 电量 {(dev['meta'] or {}).get('battery')}%")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
