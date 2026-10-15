"""E2E 前置探针：本地 Postgres 里到底有没有 seasight 的库表与种子数据（只读）。

用法：
    .venv-analysis\\Scripts\\python.exe verify\\arm_chain_e2e\\probe_db.py
"""

from __future__ import annotations

import asyncio
import os

import asyncpg

DSN = dict(
    host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    port=int(os.environ.get("POSTGRES_PORT", "5432")),
    user=os.environ.get("POSTGRES_USER", "seasight"),
    password=os.environ.get("POSTGRES_PASSWORD", "seasight"),
    database=os.environ.get("POSTGRES_DB", "seasight"),
)


async def main() -> None:
    conn = await asyncpg.connect(**DSN, timeout=5)
    tables = await conn.fetch(
        "select table_name from information_schema.tables "
        "where table_schema = 'public' order by 1"
    )
    names = [r["table_name"] for r in tables]
    print(f"public 表数量：{len(names)}")
    print("  " + ", ".join(names))

    for table in ("t_device", "t_event", "t_task", "t_track", "t_user", "t_telemetry"):
        if table not in names:
            print(f"{table}: 表不存在")
            continue
        count = await conn.fetchval(f"select count(*) from {table}")
        print(f"{table}: {count} 行")

    if "t_device" in names:
        rows = await conn.fetch(
            "select device_id, device_type, status, name from t_device order by device_type, device_id"
        )
        print("\n设备清单：")
        for r in rows:
            print(f"  {r['device_id']:<16} {r['device_type']:<14} {str(r['status']):<8} {r['name']}")

    if "t_user" in names:
        rows = await conn.fetch("select username, role from t_user order by role, username")
        print("\n账号：")
        for r in rows:
            print(f"  {r['username']:<20} {r['role']}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
