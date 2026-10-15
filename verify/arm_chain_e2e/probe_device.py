"""E2E 前置探针 2：t_device 的列结构与一台现役机器人的样例行（只读）。

用法：
    .venv-analysis\\Scripts\\python.exe verify\\arm_chain_e2e\\probe_device.py
"""

from __future__ import annotations

import asyncio
import json

import asyncpg

DSN = dict(host="127.0.0.1", port=5432, user="seasight", password="seasight", database="seasight")


async def main() -> None:
    conn = await asyncpg.connect(**DSN, timeout=5)
    cols = await conn.fetch(
        "select column_name, data_type, is_nullable, column_default "
        "from information_schema.columns where table_name = 't_device' order by ordinal_position"
    )
    print("t_device 列：")
    for c in cols:
        print(f"  {c['column_name']:<18} {c['data_type']:<28} null={c['is_nullable']:<4} {c['column_default'] or ''}")

    row = await conn.fetchrow("select * from t_device where device_id = 'RBT-001'")
    print("\nRBT-001 样例：")
    for k, v in dict(row).items():
        print(f"  {k:<18} {str(v)[:110]}")

    arms = await conn.fetch("select device_id from t_device where device_id like 'RBT-ARM%'")
    print("\nRBT-ARM* 是否已存在：", [r["device_id"] for r in arms] or "无")

    # 分区表：t_track 的当前分区是否覆盖今天
    parts = await conn.fetch(
        "select inhrelid::regclass::text as part from pg_inherits "
        "where inhparent = 't_track'::regclass order by 1 desc limit 5"
    )
    print("t_track 最近分区：", [p["part"] for p in parts])
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
