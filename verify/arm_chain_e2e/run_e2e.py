#!/usr/bin/env python3
"""探海灵眸 · 机械臂链路端到端验收（本机全链路，不需要真树莓派硬件）。

## 这条链路上每一环都是真的

| 环节 | 真/假 | 说明 |
| --- | --- | --- |
| Postgres `seasight` | **真** | 本机 PG17 里的项目库（52 张表、演示种子数据） |
| MQTT broker | **真** | `mqtt_broker.py`（amqtt）——真实 MQTT 3.1.1、真 QoS1/PUBACK、真 LWT/retained |
| 平台后端 | **真** | `backend/run_server.py`（uvicorn + aiomqtt 客户端 + 派单引擎 + 全部 handler） |
| 桥接层 | **真** | `edge/arm_bridge`（paho 客户端，argparse 入口同生产） |
| 视觉闭环驱动 | **真** | `oceanus_vision`（YOLO→IK→舵机那份代码，注册表加载） |
| 机械臂物理动作 / 相机 / 舵机 | **mock** | `edge/grasp` 的 mock 后端合成画面与回读（开发机没有 ROS/硬件） |

所以本脚本证明的是**报文、状态机与数据落库**这条链，不是物理拾取。
对外口径仍是 E1/E2，不得写成"真机现场验证"。

## 验证路径

1. **人工指派**：`POST /tasks`（robot_id=RBT-ARM-01）→ 平台下发 → 桥接收单 →
   ACK → collecting → 抓取+入槽 → done。
2. **事件自动派单**：`POST /events` → `POST /tasks/dispatch/pending` →
   派单引擎按 KNN 选最近的可用机器人（事件就放在机械臂坐标上）→ 同一条链。

## 断言（工单数据到底有没有同步变化）

- MQTT 时间线：`robot/<id>/task`、`cmd/ack`、`task/progress`(collecting/done)、
  `marine/<site>/<id>/telemetry`(servos 非空)
- `t_task`：assigned→navigating→collecting→done + collected_weight/review_result/finished_at
- `t_task_ack`：ACCEPTED 的规范回执落库（判重/审计）
- `t_track`：任务期间新增轨迹行，且 **`servo_telemetry` 非空**（"机械臂真的动了"的硬证据）
- `t_device`：`last_heartbeat` 推进、meta 电量/仓容被遥测覆盖、任务终结后摘掉 `current_task_id`
- `t_event`：任务完成后事件转 resolved
- 平台 API：`/tasks/{id}`、`/tasks/{id}/acks`、`/robots`、`/devices/{id}`、
  `/simulations/{task_id}`（前端控制台读的那份舵机数据）

用法：
    .venv-analysis\\Scripts\\python.exe verify\\arm_chain_e2e\\run_e2e.py
    # 想留在本机手动看页面：加 --keep-running，脚本会打印仍在跑的端口
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import asyncpg
import httpx
import paho.mqtt.client as mqtt
import yaml

ROOT = Path(__file__).resolve().parents[2]
EDGE = ROOT / "edge"
BACKEND = ROOT / "backend"
HERE = Path(__file__).resolve().parent
PY = Path(sys.executable)

ARM = "RBT-ARM-01"
SITE = "lianjiang"
ARM_LNG, ARM_LAT = 119.6540, 26.3870        # 与 edge/arm_bridge/config.yaml 的 home 一致
OPERATOR = ("operator", "operator123456")   # backend/scripts/bootstrap_demo_users.py 的演示账号

DB = dict(
    host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    port=int(os.environ.get("POSTGRES_PORT", "5432")),
    user=os.environ.get("POSTGRES_USER", "seasight"),
    password=os.environ.get("POSTGRES_PASSWORD", "seasight"),
    database=os.environ.get("POSTGRES_DB", "seasight"),
)


# ======================================================================
# 报告
# ======================================================================
@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    critical: bool = True


class Report:
    def __init__(self) -> None:
        self.checks: list[Check] = []
        self.notes: list[str] = []
        self.timeline: list[dict[str, Any]] = []

    def check(self, name: str, ok: bool, detail: str = "", *, critical: bool = True) -> bool:
        self.checks.append(Check(name, bool(ok), detail, critical))
        mark = "PASS" if ok else ("FAIL" if critical else "WARN")
        print(f"  [{mark}] {name}" + (f" —— {detail}" if detail else ""), flush=True)
        return bool(ok)

    def note(self, text: str) -> None:
        self.notes.append(text)
        print(f"  · {text}", flush=True)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok and c.critical]

    def render(self, ctx: dict[str, Any]) -> str:
        lines = ["# 机械臂链路端到端验收报告", ""]
        lines.append(f"- 时间：{datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}")
        lines.append(f"- 机器人：`{ctx.get('robot')}` · 站点：`{ctx.get('site')}`")
        lines.append(f"- 平台：`{ctx.get('api_base')}` · broker：`127.0.0.1:{ctx.get('broker_port')}`")
        lines.append("")
        lines.append("## 断言")
        lines.append("")
        lines.append("| # | 断言 | 结果 | 详情 |")
        lines.append("| --- | --- | --- | --- |")
        for i, c in enumerate(self.checks, start=1):
            mark = "✅" if c.ok else ("❌" if c.critical else "⚠️")
            lines.append(f"| {i} | {c.name} | {mark} | {c.detail.replace('|', '/')} |")
        lines.append("")
        if ctx.get("tasks"):
            lines.append("## 工单")
            lines.append("")
            for row in ctx["tasks"]:
                lines.append(f"- `{row['task_id']}`（{row['via']}）："
                             f"{row.get('status')} · robot={row.get('robot_id')} · "
                             f"weight={row.get('collected_weight')} · review={row.get('review_result')}")
            lines.append("")
        if self.timeline:
            lines.append("## MQTT 时间线（观察者订 `#`）")
            lines.append("")
            lines.append("| t+ | topic | payload |")
            lines.append("| --- | --- | --- |")
            for ev in self.timeline:
                payload = ev["payload"].replace("|", "/")
                lines.append(f"| {ev['t_plus']:.2f}s | `{ev['topic']}` | `{payload[:160]}` |")
            lines.append("")
        if self.notes:
            lines.append("## 说明")
            lines.append("")
            for n in self.notes:
                lines.append(f"- {n}")
        return "\n".join(lines) + "\n"


# ======================================================================
# 子进程与观察者
# ======================================================================
class Service:
    def __init__(self, name: str, cmd: list[str], cwd: Path, env: dict[str, str], log: Path) -> None:
        self.name = name
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.log = log
        self.proc: subprocess.Popen | None = None
        self._fh = None

    def start(self, append: bool = False) -> None:
        """起进程；``append=True`` 用于**重启**（保留上一次崩溃前的日志）。"""
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        self._fh = self.log.open("a" if append else "w", encoding="utf-8")
        if append:
            self._fh.write(f"\n\n===== 重启 {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
            self._fh.flush()
        self.proc = subprocess.Popen(
            self.cmd, cwd=str(self.cwd), env=self.env,
            stdout=self._fh, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        )

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def tail(self, lines: int = 12) -> str:
        try:
            text = self.log.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return ""
        return "\n".join(text[-lines:])


class Observer:
    """订 `#` 记录全链路报文（时间线证据）。"""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.msgs: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        try:
            self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e-observer")
        except (AttributeError, ValueError):
            self._client = mqtt.Client(client_id="e2e-observer")
        self._client.on_message = self._on_message
        self.t0 = time.time()

    def _on_message(self, _c: Any, _u: Any, msg: Any) -> None:
        with self._lock:
            self.msgs.append({
                "ts": time.time(),
                "topic": msg.topic,
                "payload": msg.payload.decode("utf-8", "ignore"),
            })

    def start(self) -> None:
        self._client.connect(self.host, self.port, 30)
        self._client.loop_start()
        self._client.subscribe("#", 0)

    def stop(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.msgs)

    def find(self, topic: str | None = None, contains: str | None = None) -> list[dict[str, Any]]:
        out = []
        for m in self.snapshot():
            if topic is not None and topic not in m["topic"]:
                continue
            if contains is not None and contains not in m["payload"]:
                continue
            out.append(m)
        return out


async def wait_until(pred: Callable[[], Any], timeout: float, interval: float = 0.5,
                     desc: str = "") -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if await pred() if asyncio.iscoroutinefunction(pred) else pred():
            return True
        await asyncio.sleep(interval)
    return False


# ======================================================================
# 主流程
# ======================================================================
@dataclass
class Ctx:
    api_base: str
    broker_port: int
    api_port: int
    robot: str = ARM
    site: str = SITE
    run_dir: Path = field(default_factory=Path)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    token: str = ""


async def db_snapshot(conn: asyncpg.Connection, robot: str) -> dict[str, Any]:
    device = await conn.fetchrow(
        "select device_id, status, meta, last_heartbeat from t_device where device_id = $1", robot
    )
    tracks = await conn.fetchval("select count(*) from t_track where robot_id = $1", robot)
    return {
        "device": dict(device) if device else None,
        "tracks": tracks,
    }


async def seed_arm(conn: asyncpg.Connection, log: Callable[[str], None]) -> None:
    meta = {
        "battery": 100,
        "bins": {"foam": 0.0, "plastic": 0.0, "mixed": 0.0},
        "chassis": "arm",
        "hull": "双体",
        "arm": "ArmPi FPV 6-DOF（Oceanus Arm）",
        "home": {"lng": ARM_LNG, "lat": ARM_LAT},
    }
    await conn.execute(
        """
        insert into t_device (device_id, device_type, name, location, status, meta, last_heartbeat)
        values ($1, 'robot'::device_type_enum, $2,
                ST_SetSRID(ST_MakePoint($3, $4), 4326)::geometry,
                'online'::device_status_enum, $5::jsonb, now())
        on conflict (device_id) do update
           set device_type = 'robot'::device_type_enum,
               name = excluded.name,
               location = excluded.location,
               status = 'online'::device_status_enum,
               meta = $5::jsonb
        """,
        # ★ 传 dict（连接上注册了 jsonb 编解码器）；传 json 字符串会被当成
        #   jsonb **标量字符串**，与旧值 || 合并后 meta 变成数组 —— 
        #   平台侧读 meta.get(...) 直接 500。
        ARM, "机械臂一号（Oceanus Arm）", ARM_LNG, ARM_LAT, meta,
    )
    log(f"设备已就绪：{ARM} @ ({ARM_LNG}, {ARM_LAT}) type=robot status=online chassis=arm")


async def login(client: httpx.AsyncClient) -> str:
    resp = await client.post("/api/v1/auth/login",
                             json={"username": OPERATOR[0], "password": OPERATOR[1]})
    resp.raise_for_status()
    body = resp.json()
    data = body.get("data", body)
    return data["access_token"]


def api_ok(resp: httpx.Response) -> tuple[bool, str]:
    """平台约定：**HTTP 状态码未必说明业务结果** —— 业务错误也走 200 + ``body.code``。

    只看 ``status_code < 300`` 会把「事件被序号判重拒绝」这类失败看成成功。
    """
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return resp.status_code < 300, f"HTTP {resp.status_code}"
    code = body.get("code", 0)
    return (resp.status_code < 300 and code == 0,
            f"HTTP {resp.status_code} code={code} {body.get('message', '')}"[:200])


async def task_row(conn: asyncpg.Connection, task_id: str) -> dict[str, Any] | None:
    row = await conn.fetchrow("select * from t_task where task_id = $1", task_id)
    return dict(row) if row else None


async def cleanup_active_tasks(conn: asyncpg.Connection, robot: str,
                               log: Callable[[str], None]) -> int:
    """把机械臂身上残留的活跃工单标成 cancelled（测试现场清场）。

    ★ 为什么需要：库里可能留着上一次跑失败/中断的工单（尤其 `pending` 且
      `robot_id` 已占位的那些 —— 补派只扫 `robot_id IS NULL`，它们永远不会
      再被派出去）。不清掉的话 `/robots` 会一直显示"当前任务"，本次断言就
      分不清是残留还是新问题。这里直接改库（测试现场清理，不走状态机），
      并在报告里写明清了几个。
    """
    rows = await conn.fetch(
        "update t_task set status = 'cancelled'::task_status_enum,"
        "                  remark = coalesce(remark, '') || ' [e2e 清场]',"
        "                  updated_at = now() "
        "where robot_id = $1 and status in ('pending','assigned','navigating','collecting') "
        "returning task_id",
        robot,
    )
    if rows:
        log(f"清场：{len(rows)} 个残留活跃工单已标 cancelled（{', '.join(r['task_id'] for r in rows[:5])}"
            f"{' …' if len(rows) > 5 else ''}）")
    return len(rows)


async def cleanup_merge_window(conn: asyncpg.Connection, lng: float, lat: float,
                               log: Callable[[str], None]) -> int:
    """清掉「防抖合并窗口」内的活跃工单（锚点附近 200m / 10 分钟）。

    ★ 为什么必须清：派单引擎有**防抖合并**（`_try_merge`：10 分钟内、200 米内的
      活跃工单会被复用，事件合并进去而**不再新建工单**）。库里有前几轮 E2E 在
      同一坐标留下的活跃工单时，新事件会被合并掉 —— 表现为"事件入库成功但
      没有任何新工单"，看起来像派单坏了。这些工单都是本脚本自己造出来的，
      清掉即可；真实演示前同理（清场正是这个道理）。
    """
    rows = await conn.fetch(
        "update t_task set status = 'cancelled'::task_status_enum,"
        "                  remark = coalesce(remark, '') || ' [e2e 合并窗口清场]',"
        "                  updated_at = now() "
        "where status in ('pending','assigned','navigating','collecting') "
        "  and created_at >= now() - interval '10 minutes' "
        "  and ST_DWithin(target_location::geography,"
        "                 ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, 200) "
        "returning task_id",
        lng, lat,
    )
    if rows:
        log(f"合并窗口清场：{len(rows)} 个活跃工单已标 cancelled"
            f"（{', '.join(r['task_id'] for r in rows[:4])}{' …' if len(rows) > 4 else ''}）")
    return len(rows)


async def robot_candidates(conn: asyncpg.Connection, lng: float, lat: float) -> list[dict[str, Any]]:
    """列出「在线机器人 × 到锚点距离 × 是否有同类在途工单」—— 解释派单选择的证据。"""
    rows = await conn.fetch(
        """
        select d.device_id, d.status,
               ST_Distance(d.location::geography,
                           ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) as dist_m,
               (select count(*) from t_task t
                  where t.robot_id = d.device_id
                    and t.status in ('pending','assigned','navigating','collecting')) as active
        from t_device d
        where d.device_type = 'robot' and d.status = 'online'
        order by dist_m asc
        """,
        lng, lat,
    )
    return [dict(r) for r in rows]


async def set_robots_status(conn: asyncpg.Connection, robot_ids: list[str],
                            status: str) -> None:
    if not robot_ids:
        return
    await conn.execute(
        "update t_device set status = $2::device_status_enum where device_id = any($1::text[])",
        robot_ids, status,
    )


async def wait_task_done(conn: asyncpg.Connection, task_id: str, timeout: float,
                         report: Report) -> dict[str, Any] | None:
    seen: list[str] = []
    deadline = time.time() + timeout
    row = None
    while time.time() < deadline:
        row = await task_row(conn, task_id)
        if row is not None:
            status = str(row["status"])
            if not seen or seen[-1] != status:
                seen.append(status)
                report.note(f"工单 {task_id} 状态推进：{status}")
            if status in ("done", "cancelled"):
                break
        await asyncio.sleep(0.8)
    if row is not None:
        row["_status_path"] = seen
    return row


# ----------------------------------------------------------------------
async def run(args: argparse.Namespace) -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = HERE / "runs" / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    ctx = Ctx(api_base=f"http://127.0.0.1:{args.api_port}", broker_port=args.broker_port,
              api_port=args.api_port, run_dir=run_dir)
    report = Report()
    services: list[Service] = []
    observer = Observer("127.0.0.1", args.broker_port)
    broker_service = backend_service = bridge_service = None
    cfg_path = run_dir / "arm_bridge.e2e.yaml"

    print(f"\n=== 探海灵眸机械臂链路 E2E（证据目录 {run_dir}）===\n")

    conn = await asyncpg.connect(**DB, timeout=6)
    # jsonb 默认以字符串返回；设了编解码器才能像字典一样读 meta / servo_telemetry
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    try:
        # ---------- 0. 前置 ----------
        ver = await conn.fetchval("select version()")
        report.note(f"数据库：{ver.split(' on ')[0]}")
        await seed_arm(conn, report.note)

        # ---------- 1. broker ----------
        print("\n[1/7] 启动临时 MQTT broker …")
        broker_service = Service(
            "broker", [str(PY), str(HERE / "mqtt_broker.py"), "--port", str(args.broker_port)],
            HERE, {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            run_dir / "broker.log",
        )
        broker_service.start()
        services.append(broker_service)
        ready = await wait_until(
            lambda: "BROKER READY" in broker_service.tail(50), args.start_timeout, 0.4)
        report.check("临时 broker 就绪", ready, f"127.0.0.1:{args.broker_port}",
                     critical=True)
        if not ready:
            raise RuntimeError("broker 未就绪")

        # ---------- 2. 后端 ----------
        print("\n[2/7] 启动平台后端（uvicorn + aiomqtt）…")
        backend_env = {
            **os.environ,
            "APP_ENV": "development", "DEBUG": "true",
            "POSTGRES_HOST": DB["host"], "POSTGRES_PORT": str(DB["port"]),
            "POSTGRES_DB": DB["database"], "POSTGRES_USER": DB["user"],
            "POSTGRES_PASSWORD": DB["password"],
            "REDIS_HOST": "127.0.0.1", "REDIS_PORT": "6379", "REDIS_PASSWORD": "",
            "MQTT_HOST": "127.0.0.1", "MQTT_PORT": str(args.broker_port),
            "MQTT_USERNAME": "backend_service", "MQTT_PASSWORD": "e2e-local",
            "MQTT_TOPIC_PREFIX": "marine",
            "SECRET_KEY": "e2e-local-secret-key-0123456789abcdef",
            # ★ 演示纪律：关掉后台定时补派（消费者 + 定时器）。开着的话它会
            #   不停地替库里那批演示工单派单（RBT-001..006 无 ACK → 30s 超时
            #   → 再派），既刷屏又会抢机械臂；联调走显式「触发补派」接口。
            "BACKGROUND_WORKERS_ENABLED": "false",
            "AGENT_MODEL_ADAPTER_ENABLED": "false",
            "AGENT_PERSISTENT_REPOSITORY_ENABLED": "false",
            "CORS_ORIGINS": "http://localhost:5173",
            "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
        }
        backend_service = Service(
            "backend",
            [str(PY), "run_server.py", "--host", "127.0.0.1", "--port", str(args.api_port)],
            BACKEND, backend_env, run_dir / "backend.log",
        )
        backend_service.start()
        services.append(backend_service)

        async with httpx.AsyncClient(base_url=ctx.api_base, timeout=10) as client:
            async def api_ready() -> bool:
                if not backend_service.alive():
                    return False
                try:
                    r = await client.get("/api/v1/robots")
                    return r.status_code == 200
                except Exception:  # noqa: BLE001
                    return False

            ok = await wait_until(api_ready, args.start_timeout, 1.0)
            report.check("平台后端就绪（/api/v1/robots 200）", ok, ctx.api_base)
            if not ok:
                raise RuntimeError("后端未就绪：\n" + backend_service.tail(20))

            ctx.token = await login(client)
            headers = {"Authorization": f"Bearer {ctx.token}"}
            report.check("操作员登录", bool(ctx.token), f"{OPERATOR[0]} / Bearer 令牌")

            # ---------- 3. 观察者 + 桥接层 ----------
            print("\n[3/7] 启动报文观察者与树莓派桥接层 …")
            observer.t0 = time.time()
            observer.start()

            bridge_cfg = yaml.safe_load((EDGE / "arm_bridge" / "config.yaml").read_text(encoding="utf-8"))
            bridge_cfg["site_id"] = SITE
            bridge_cfg["device_id"] = ARM
            bridge_cfg["mqtt"].update({
                "host": "127.0.0.1", "port": args.broker_port,
                "username": "robot_device", "password": "e2e-local",
            })
            bridge_cfg["driver"]["backend"] = "oceanus_vision"
            bridge_cfg["driver"].setdefault("oceanus_vision", {})
            bridge_cfg["driver"]["oceanus_vision"].update({
                # ★ 本机没有 ROS/相机/机械臂：物理执行端用 mock（合成画面 + 模拟舵机）
                "mock": True,
                "config_path": str(EDGE / "grasp" / "config.yaml"),
                "calibration_path": None,
                "review_result": "recheck",
            })
            cfg_path.write_text(yaml.safe_dump(bridge_cfg, allow_unicode=True, sort_keys=False),
                                encoding="utf-8")

            bridge_service = Service(
                "bridge",
                [str(PY), "-m", "arm_bridge.main", "--config", str(cfg_path),
                 "--driver", "oceanus_vision"],
                EDGE,
                {**os.environ, "OCEANUS_MQTT_HOST": "127.0.0.1",
                 "OCEANUS_MQTT_PORT": str(args.broker_port),
                 "OCEANUS_MQTT_USER": "robot_device", "OCEANUS_MQTT_PASSWORD": "e2e-local",
                 # 临时 broker（amqtt）只支持 MQTT 3.1.1；生产 EMQX 用默认的 v5
                 "OCEANUS_MQTT_PROTOCOL": "311",
                 "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                 "PYTHONUNBUFFERED": "1"},
                run_dir / "bridge.log",
            )
            bridge_service.start()
            services.append(bridge_service)

            connected = await wait_until(
                lambda: "waiting for tasks" in bridge_service.tail(40) or not bridge_service.alive(),
                args.start_timeout, 0.5)
            report.check("桥接层连上 broker 并准备收单", connected,
                         "bridge.log: " + (bridge_service.tail(3).replace("\n", " / ") or "—"))
            if not connected:
                raise RuntimeError("桥接层未就绪：\n" + bridge_service.tail(20))

            online = await wait_until(
                lambda: bool(observer.find(f"marine/{SITE}/{ARM}/status")), 15.0, 0.5)
            report.check("桥接层上线状态已上报（retained）", online,
                         (observer.find(f"marine/{SITE}/{ARM}/status") or [{}])[0].get("payload", "—"))

            # ---------- 4. 派单（人工指派） ----------
            print("\n[4/7] 平台派单 → 机械臂（人工指派路径）…")
            stale = await cleanup_active_tasks(conn, ARM, report.note)
            before = await db_snapshot(conn, ARM)
            report.note(f"基线：t_track={before['tracks']} 行，"
                        f"meta.current_task_id={(before['device'] or {}).get('meta', {}).get('current_task_id')}")

            resp = await client.post(
                "/api/v1/tasks",
                json={"robot_id": ARM, "target": {"lng": ARM_LNG, "lat": ARM_LAT}, "priority": 1},
                headers=headers,
            )
            report.check("创建并指派工单（POST /tasks）", resp.status_code < 300,
                         f"HTTP {resp.status_code}")
            task_id = resp.json()["data"]["task_id"]
            report.note(f"工单号：{task_id}")

            row = await wait_task_done(conn, task_id, args.task_timeout, report)
            report.check("工单走到 done", bool(row) and row["status"] == "done",
                         f"status={row['status'] if row else '—'} "
                         f"path={'→'.join(row.get('_status_path', [])) if row else '—'}")
            if row:
                ctx.tasks.append({**row, "via": "人工指派"})

            # ---------- 5. 数据同步断言 ----------
            print("\n[5/7] 核对数据是否真的同步变化 …")
            mqtt_msgs = observer.snapshot()
            for m in mqtt_msgs:
                m["t_plus"] = m["ts"] - observer.t0
            report.timeline = sorted(mqtt_msgs, key=lambda m: m["ts"])

            dispatch = observer.find(f"robot/{ARM}/task")
            report.check("派单报文到达桥接层", bool(dispatch),
                         f"{len(dispatch)} 条 robot/{ARM}/task")

            acks_mqtt = observer.find(f"robot/{ARM}/cmd/ack")
            report.check("桥接层回 ACK", any('"accepted": true' in m["payload"] or
                                            '"accepted":true' in m["payload"] for m in acks_mqtt),
                         f"{len(acks_mqtt)} 条 cmd/ack")

            ack_rows = await conn.fetch(
                "select command_id, task_id, accepted, reason, mode, outcome, received_at "
                "from t_task_ack where task_id = $1 order by id", task_id)
            report.check("ACK 回执落库（t_task_ack）", bool(ack_rows) and all(r["accepted"] for r in ack_rows),
                         f"{len(ack_rows)} 行，outcome="
                         f"{sorted({r['outcome'] for r in ack_rows})}")

            progress = observer.find(f"robot/{ARM}/task/progress")
            statuses = []
            for m in progress:
                try:
                    statuses.append(json.loads(m["payload"]).get("status"))
                except Exception:  # noqa: BLE001
                    pass
            report.check("进度回传 collecting → done",
                         "collecting" in statuses and "done" in statuses, f"statuses={statuses}")

            telemetry = observer.find(f"marine/{SITE}/{ARM}/telemetry")
            servo_msgs = [m for m in telemetry if '"servos"' in m["payload"] and
                          '"servos": {}' not in m["payload"] and '"servos":{}' not in m["payload"]]
            report.check("遥测上报逐舵机回读", bool(servo_msgs),
                         f"telemetry {len(telemetry)} 条，其中带舵机 {len(servo_msgs)} 条")

            tracks = await conn.fetch(
                "select id, task_id, battery, bin_plastic, servo_telemetry, recorded_at "
                "from t_track where robot_id = $1 order by id desc limit 5", ARM)
            with_servo = [t for t in tracks if t["servo_telemetry"]]
            newest = tracks[0] if tracks else None
            report.check("轨迹落库并带 servo_telemetry（硬证据）", bool(with_servo),
                         f"最近 {len(tracks)} 行中 {len(with_servo)} 行有舵机数据；"
                         f"舵机数={len((with_servo[0]['servo_telemetry'] or {})) if with_servo else 0}")
            report.check("轨迹带电量/仓容", bool(newest) and newest["battery"] is not None,
                         f"battery={newest['battery'] if newest else '—'} "
                         f"bin_plastic={newest['bin_plastic'] if newest else '—'}")
            report.check("轨迹与本工单关联", any(t["task_id"] == task_id for t in tracks),
                         f"task_id 命中 {sum(1 for t in tracks if t['task_id'] == task_id)}/{len(tracks)}")

            if row:
                report.check("工单收尾字段齐全",
                             row["finished_at"] is not None and row["collected_weight"] is not None,
                             f"finished_at={row['finished_at']} weight={row['collected_weight']} "
                             f"review={row['review_result']}")

            after = await db_snapshot(conn, ARM)
            meta = (after["device"] or {}).get("meta", {})
            report.check("设备心跳推进", (after["device"] or {}).get("last_heartbeat") is not None,
                         f"last_heartbeat={(after['device'] or {}).get('last_heartbeat')}")
            report.check("设备 meta 被遥测覆盖（电量/仓容）",
                         meta.get("battery") is not None and bool(meta.get("bins")),
                         f"battery={meta.get('battery')} bins={meta.get('bins')}")
            report.check("任务终结后摘掉 meta.current_task_id",
                         meta.get("current_task_id") in (None, ""),
                         f"current_task_id={meta.get('current_task_id')!r}")
            report.check("轨迹行数增加", after["tracks"] > before["tracks"],
                         f"{before['tracks']} → {after['tracks']}")

            # ---------- 6. 平台 API（前端看到的那份数据） ----------
            print("\n[6/7] 平台 API 读回（前端同源）…")
            detail = (await client.get(f"/api/v1/tasks/{task_id}", headers=headers)).json().get("data", {})
            report.check("GET /tasks/{id} 显示 done", detail.get("status") == "done",
                         f"status={detail.get('status')} weight={detail.get('collected_weight')}")
            ack_api = (await client.get(f"/api/v1/tasks/{task_id}/acks", headers=headers)).json().get("data", {})
            total = ack_api.get("total") if isinstance(ack_api, dict) else None
            report.check("GET /tasks/{id}/acks 可审计", bool(ack_api), f"total={total}")
            robots = (await client.get("/api/v1/robots", headers=headers)).json().get("data", [])
            arm_row = next((r for r in robots if r["robot_id"] == ARM), None)
            report.check("GET /robots 有机械臂且无残留任务",
                         bool(arm_row) and arm_row.get("current_task_id") in (None, ""),
                         f"current_task_id={arm_row.get('current_task_id') if arm_row else '—'} "
                         f"battery={arm_row.get('battery') if arm_row else '—'}")
            device = (await client.get(f"/api/v1/devices/{ARM}", headers=headers)).json().get("data", {})
            report.check("GET /devices/{id} 与 /robots 口径一致",
                         device.get("meta", {}).get("current_task_id") in (None, ""),
                         f"device.meta.current_task_id="
                         f"{device.get('meta', {}).get('current_task_id')!r}")
            sim = (await client.get(f"/api/v1/simulations/{task_id}/trajectory",
                                    headers=headers)).json().get("data", [])
            traj = sim if isinstance(sim, list) else []
            sim_servo = [p for p in traj if isinstance(p, dict) and p.get("servo_telemetry")]
            report.check("GET /simulations/{task_id}/trajectory 带舵机数据（前端控制台同源）",
                         bool(sim_servo), f"轨迹 {len(traj)} 点，带舵机 {len(sim_servo)} 点")

            # ---------- 7. 事件自动派单 ----------
            print("\n[7/7] 事件自动派单路径（事件 → 派单引擎 → 机械臂）…")
            camera = "CAM-MABI-01"

            async def seq_for(device: str) -> int:
                last = await conn.fetchval(
                    "select coalesce(max(seq), 0) from t_event where device_id = $1", device)
                return int(last) + 1

            async def ingest_foam(eid: str) -> tuple[bool, str]:
                # ★ main_class 必须用**高优先级类别**：自动派单只对
                #   `WasteClass.HIGH_PRIORITY`（foam / fishing_gear）生效 ——
                #   塑料事件按设计要人工研判后才派单，不在这条自动链上。
                # ★ seq 必须大于该设备上一条：事件入库有「序号回退/重复」判重，
                #   用 seq=1 会被判重拒绝（HTTP 200 + body.code≠0，库里不留行）。
                resp = await client.post("/api/v1/events", json={
                    "event_id": eid,
                    "device_id": camera,
                    "device_type": "shore_camera",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "location": {"lng": ARM_LNG, "lat": ARM_LAT},
                    "detections": [{"class": "foam", "confidence": 0.91,
                                    "bbox": [10, 10, 60, 60]}],
                    "aggregate": {"main_class": "foam", "count": 1, "max_confidence": 0.91},
                    "seq": await seq_for(camera),
                }, headers=headers)
                return api_ok(resp)

            # ---- 7a. 原样派单：观察引擎在**当前演示数据**下会选谁 ----
            await cleanup_merge_window(conn, ARM_LNG, ARM_LAT, report.note)
            candidates = await robot_candidates(conn, ARM_LNG, ARM_LAT)
            report.note("在线机器人与候选信息（距离 / 在途工单数）：" + "; ".join(
                f"{c['device_id']} {c['dist_m']:.0f}m/{c['active']}单" for c in candidates))

            event_a = f"EVT-E2E-A-{stamp}"
            ok, detail = await ingest_foam(event_a)
            report.check("事件自动派单：事件入库", ok, detail)

            row_a = await conn.fetchrow(
                "select task_id, robot_id, status from t_task where event_id = $1 "
                "order by id desc limit 1", event_a)
            picked = row_a["robot_id"] if row_a else None
            report.check("事件 → 自动生成工单并下发",
                         bool(row_a), f"task={row_a['task_id'] if row_a else '—'} → robot={picked}")
            if picked and picked != ARM:
                # ★ 不是失败，是**策略结果**：派单引擎按「类别匹配加权优先，
                #   其次按距离」排序（_select_robot_at_possible）。别的船手上有
                #   同类在途工单时，0 米的机械臂也会输给它（实测 3.2km）。
                #   演示要么先清场，要么走人工指派。
                report.check(
                    f"自动派单选中机械臂（当前数据下选了 {picked}）", False,
                    "派单引擎「同类任务顺路复用」优先于距离：别的机器人手上有同类在途工单，"
                    "0 米的机械臂会被跳过。演示前清掉滞留工单，或用人工指派（见下一项）",
                    critical=False,
                )

            # ---- 7b. 确定性验证：其它船不可用时，自动派单必须给机械臂 ----
            await cleanup_merge_window(conn, ARM_LNG, ARM_LAT, report.note)
            others = [c["device_id"] for c in candidates if c["device_id"] != ARM]
            await set_robots_status(conn, others, "offline")
            report.note(f"为验证自动派单能落到机械臂，临时把其它在线机器人置为 offline：{others}（跑完恢复）")
            try:
                event_b = f"EVT-E2E-B-{stamp}"
                ok, detail = await ingest_foam(event_b)
                report.check("事件自动派单（其它船 offline）：事件入库", ok, detail)
                row_b = await conn.fetchrow(
                    "select task_id, robot_id, status from t_task where event_id = $1 "
                    "order by id desc limit 1", event_b)
                report.check("自动派单选中机械臂", bool(row_b) and row_b["robot_id"] == ARM,
                             f"task={row_b['task_id'] if row_b else '—'} "
                             f"robot={row_b['robot_id'] if row_b else '—'}")
                if row_b:
                    row2 = await wait_task_done(conn, row_b["task_id"], args.task_timeout, report)
                    report.check("自动派单的工单走到 done",
                                 bool(row2) and row2["status"] == "done",
                                 f"status={row2['status'] if row2 else '—'}")
                    if row2:
                        ctx.tasks.append({**row2, "via": "事件自动派单"})
                    ev = await conn.fetchrow("select status from t_event where event_id = $1", event_b)
                    report.check("事件随任务完成转 resolved",
                                 bool(ev) and ev["status"] == "resolved",
                                 f"event.status={ev['status'] if ev else '—'}")
            finally:
                await set_robots_status(conn, others, "online")
                report.note("其它机器人 online 状态已恢复")

        # ---------- 收尾 ----------
        print("\n=== 结果 ===")
        failed = report.failed
        if failed:
            print(f"❌ {len(failed)} 项未通过：" + "、".join(c.name for c in failed))
        else:
            print(f"✅ 全部 {len(report.checks)} 项断言通过")
        if not bridge_service.alive():
            print("⚠️ 桥接层已退出，日志尾部：\n" + bridge_service.tail(15))
        if not backend_service.alive():
            print("⚠️ 后端已退出，日志尾部：\n" + backend_service.tail(15))

        (run_dir / "report.md").write_text(report.render(ctx.__dict__), encoding="utf-8")
        (run_dir / "mqtt_timeline.json").write_text(
            json.dumps(report.timeline, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n证据已写入：{run_dir}")

        if args.keep_running:
            print("\n--keep-running：服务继续运行，Ctrl+C 结束")
            print(f"  平台 API : {ctx.api_base}/api/v1/robots")
            print(f"  broker   : 127.0.0.1:{args.broker_port}")
            try:
                while True:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass

        return 1 if failed else 0
    finally:
        observer.stop()
        for svc in reversed(services):
            svc.stop()
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="机械臂链路端到端验收（本机全链路）")
    parser.add_argument("--broker-port", type=int, default=11883)
    parser.add_argument("--api-port", type=int, default=8001)
    parser.add_argument("--start-timeout", type=float, default=90.0)
    parser.add_argument("--task-timeout", type=float, default=150.0)
    parser.add_argument("--keep-running", action="store_true",
                        help="跑完不退出，保留后端/broker/桥接层供手动看页面")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
