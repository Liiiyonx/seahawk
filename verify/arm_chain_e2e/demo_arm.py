#!/usr/bin/env python3
r"""探海灵眸 · 机械臂演示「一键起栈」（本机演示/彩排用）。

一条命令把演示要用的东西全起好，并打印**一张演示动线卡**（打开哪个地址、点哪里、
预期看到什么）+ 一块**实时状态**（机械臂在线/电量/三仓/当前工单/最近舵机回读/MQTT 报文）。

```powershell
# 彩排（本机无硬件：桥接层用 mock 执行端）+ 平台前端
.\.venv-analysis\Scripts\python.exe verify\arm_chain_e2e\demo_arm.py

# 演示前清场 + 只让机械臂在线（自动派单必落机械臂），退出时自动恢复
.\.venv-analysis\Scripts\python.exe verify\arm_chain_e2e\demo_arm.py --clean --arm-only

# 真机：本脚本**不会**在本机假装真机 —— 它会打印树莓派上该跑的那条命令
.\.venv-analysis\Scripts\python.exe verify\arm_chain_e2e\demo_arm.py --real
```

起的东西：临时 MQTT broker（amqtt，:11883）→ 平台后端（uvicorn，:8000）→
平台前端（vite preview，:5173）→ 机械臂桥接层（edge/arm_bridge，`--driver oceanus_vision`）。

口径：`--mock`（默认）下机械臂的物理动作/相机/舵机是合成后端，只有链路是真的 ——
**彩排可以，对外不得说成真机现场验证**。真机请用 `--real` 并在树莓派上起桥接层。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg
import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# 复用验收脚本里的基础设施（服务守护、MQTT 观察者、清场/选机证据等）
from run_e2e import (  # noqa: E402
    ARM,
    ARM_LAT,
    ARM_LNG,
    BACKEND,
    DB,
    EDGE,
    OPERATOR,
    PY,
    ROOT,
    SITE,
    Observer,
    Service,
    api_ok,
    cleanup_active_tasks,
    cleanup_merge_window,
    robot_candidates,
    set_robots_status,
    wait_until,
)

FRONTEND = ROOT / "frontend"
DEMO_DIR = HERE / "demo"
#: `--arm-only` 把哪些机器人临时置了 offline —— 落盘一份，脚本被强杀后下次启动能自动恢复
ARM_ONLY_STATE = DEMO_DIR / "arm_only_state.json"
BAR = "─" * 68


async def db_q(conn: asyncpg.Connection, sql: str, *args: Any) -> Any:
    return await conn.fetch(sql, *args)


def read_arm_only_state() -> list[str]:
    """读「被 --arm-only 置为 offline」的机器人清单（脚本被强杀后的恢复依据）。

    ★ `utf-8-sig`：这个文件可能被记事本 / PowerShell 写成带 BOM 的 UTF-8，
      带 BOM 时 `json.loads` 直接抛 ValueError —— 那样"自愈"会静默失效，
      机器人就一直停在 offline。读的时候把 BOM 吃掉。
    """
    if not ARM_ONLY_STATE.exists():
        return []
    try:
        data = json.loads(ARM_ONLY_STATE.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def write_arm_only_state(robot_ids: list[str]) -> None:
    ARM_ONLY_STATE.parent.mkdir(parents=True, exist_ok=True)
    ARM_ONLY_STATE.write_text(json.dumps(sorted(set(robot_ids)), ensure_ascii=False),
                              encoding="utf-8")


# ======================================================================
# 演示自检 / 看门狗
# ======================================================================
def port_free(port: int, host: str = "127.0.0.1") -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) != 0


def dist_stale_days() -> float | None:
    """已构建产物相对 `frontend/src` 的滞后（天）。None = 没有产物。"""
    dist = FRONTEND / "dist" / "index.html"
    if not dist.exists():
        return None
    newest_src = 0.0
    for path in (FRONTEND / "src").rglob("*"):
        if path.is_file():
            newest_src = max(newest_src, path.stat().st_mtime)
    for extra in (FRONTEND / "vite.config.js", FRONTEND / ".env.local"):
        if extra.exists():
            newest_src = max(newest_src, extra.stat().st_mtime)
    return (newest_src - dist.stat().st_mtime) / 86400.0


class Watchdog:
    """进程看门狗：演示中谁挂了就立刻拉起来，并在屏幕上喊一声。

    ★ 为什么必须有：演示时最怕的不是"报错"，而是**静默死掉** ——
      桥接层崩了，工单派下去没人接，看板永远停在「已派单」；
      后端崩了，页面白屏。人还在讲，观众已经在看空屏。
      这里 2 秒巡检一次，最多重启 `max_restarts` 次（防止崩溃风暴刷屏）。
    """

    def __init__(self, services: list[Service], *, max_restarts: int = 20,
                 interval: float = 2.0, reset_after_s: float = 300.0) -> None:
        self.services = services
        self.max_restarts = max_restarts
        self.interval = interval
        #: 连续存活超过这个时长，就把重启计数清零 —— 展台长时间循环演示时
        #  不能因为几次偶发崩溃就用光重启额度。
        self.reset_after_s = reset_after_s
        self.restarts: dict[str, int] = {}
        self.last_restart_at: dict[str, float] = {}
        self.events: list[str] = []
        self._stop = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True

    def _loop(self) -> None:
        while not self._stop:
            time.sleep(self.interval)
            now = time.time()
            for svc in self.services:
                if svc.alive():
                    if now - self.last_restart_at.get(svc.name, 0.0) > self.reset_after_s:
                        self.restarts[svc.name] = 0
                    continue
                name = svc.name
                if self.restarts.get(name, 0) >= self.max_restarts:
                    continue
                self.restarts[name] = self.restarts.get(name, 0) + 1
                self.last_restart_at[name] = now
                msg = (f"⚠️ [{datetime.now():%H:%M:%S}] {name} 进程退出，"
                       f"自动重启（第 {self.restarts[name]} 次）")
                with self._lock:
                    self.events.append(msg)
                print(f"\n{msg}", flush=True)
                try:
                    svc.start(append=True)
                except Exception as exc:  # noqa: BLE001
                    print(f"   ✗ 重启 {name} 失败：{exc}", flush=True)

    def take_events(self) -> list[str]:
        with self._lock:
            out, self.events = self.events, []
        return out


def banner(text: str) -> None:
    print(f"\n{BAR}\n{text}\n{BAR}", flush=True)


def demo_card(api: str, ui: str, real: bool, broker_port: int) -> None:
    mode = "真机（桥接层在树莓派上）" if real else "彩排（本机 mock 执行端）"
    banner(f"演示动线卡 · {mode}")
    print(f"""  ① 打开平台： {ui}
     账号：operator / operator123456（操作员，有写权限）

  ② 让机械臂动起来（三种任选，从简到繁）：
     A. 工单看板 →「人工建单」→ 机器人已预选【机械臂】，坐标已预填 →
        点「创建任务」。机械臂立刻接单（ACK → 作业中 → 完成）。
     B. 事件页 → 选一条泡沫/渔具事件 →「触发补派」/派单 →
        若想让单子一定落到机械臂，起本脚本时加 --arm-only。
     C. 机械臂作业台：工单详情 →「打开机械臂作业台 · 输 IP 接入」
        → 在控制台里输树莓派 IP（默认 192.168.149.1）→ 打开 :8090 作业台。

  ③ 一边看机械臂，一边回来看这三处数据（这就是"真的同步了"）：
     · 工单看板：卡片从「已派单」→「前往中」→「作业中」→「已完成」
     · 设备页/机器人：电量、三仓占用、当前任务随之变化，任务完成后清空
     · 作业台控制台底部「舵机遥测」：电压/位置逐舵机滚动（来自舵机回读）

  ④ 链路证据（答辩用）：MQTT broker 127.0.0.1:{broker_port}
     robot/{ARM}/task → cmd/ack → task/progress → marine/{SITE}/{ARM}/telemetry

  ⑤ 万一出问题（照这个顺序做，30 秒内能救回来）：
     · 页面白屏 / 登录没反应 → 先刷新；还不行看状态卡有没有「⚠️ 自动重启」，
       重启后刷新页面即可（进程由看门狗自动拉起，不用重新起栈）
     · 工单卡在「已派单」不动 → 看状态卡最近报文；若没有 cmd/ack：
       桥接层没连上，等 5 秒（自动重连）或看 demo/bridge_*.log 最后 20 行
     · 机械臂不动 / 舵机遥测为空 → 真机：树莓派侧 `python3 -m arm_bridge.main
       --config arm_bridge/config.yaml --driver oceanus_vision` 是否在跑；
       作业台 :8090 是否开着（precheck 五项）
     · 实在来不及 → 直接讲「平台派单链路 + 数据同步」（工单看板 + 舵机遥测两屏），
       机械臂动作作为旁证，不要现场调设备

  ⚠️ 演示纪律：后端已按录屏口径用 BACKGROUND_WORKERS_ENABLED=false 起（不跑定时补派）。
  ⚠️ 真机前先在树莓派上跑 edge/grasp/tools/precheck.py 并完成 9 点标定 + 放置点示教。""")


async def preflight(conn: asyncpg.Connection, api_port: int, ui_port: int,
                    broker_port: int, with_frontend: bool) -> tuple[list[str], list[str]]:
    """演示前自检（只读、几秒钟）。返回 (通过项, 阻断项)。"""
    ok: list[str] = []
    bad: list[str] = []

    ver = await conn.fetchval("select version()")
    tables = await conn.fetchval(
        "select count(*) from information_schema.tables where table_schema='public'")
    ok.append(f"数据库 {ver.split(' on ')[0]} · public 表 {tables} 张")

    dev = await conn.fetchrow(
        "select status, meta from t_device where device_id = $1", ARM)
    if dev is None:
        bad.append(f"{ARM} 未登记（起栈时会自动登记，可忽略）")
    else:
        ok.append(f"机械臂设备在位 · {dev['status']} · 电量 {(dev['meta'] or {}).get('battery', '—')}%")

    for name, port in (("后端 API", api_port), ("前端", ui_port), ("broker", broker_port)):
        if with_frontend or name != "前端":
            if port_free(port):
                ok.append(f"端口 {port}（{name}）空闲")
            else:
                bad.append(f"端口 {port}（{name}）已被占用 —— 先关掉占用进程，"
                           f"或用 --api-port/--ui-port/--broker-port 换端口")

    stale = dist_stale_days()
    if stale is None:
        bad.append("frontend/dist 不存在 —— 先 `cd frontend && npm run build`")
    elif stale > 0.02:
        bad.append(f"frontend/dist 比源码旧 {stale * 24:.1f} 小时 —— "
                   f"先 `cd frontend && npm run build`（否则页面是旧版本）")
    else:
        ok.append("前端构建产物是最新的")

    env_local = FRONTEND / ".env.local"
    if not env_local.exists() or "VITE_ARM_CONSOLE_URL_TEMPLATE" not in env_local.read_text(
            encoding="utf-8"):
        bad.append("frontend/.env.local 缺 VITE_ARM_CONSOLE_URL_TEMPLATE —— "
                   "「打开机械臂作业台」按钮会显示未配置")
    else:
        ok.append("作业台跳转配置就绪（控制台可输 IP）")

    model = EDGE / "grasp" / "models" / "active" / "best.onnx"
    ok.append(f"视觉模型：{'已部署 best.onnx' if model.exists() else '未部署（真机 pick 会明确报错）'}")
    cal = EDGE / "grasp" / "calibration.json"
    if cal.exists():
        ok.append("9 点标定文件存在（真机可直接作业）")
    else:
        ok.append("尚无 9 点标定文件 —— 彩排无妨；真机演示前必须在作业台跑一次")

    # ★ 上次演示残留的 offline 机器人会让"自动派单"落到别的船上
    stale = read_arm_only_state()
    if stale:
        bad.append(f"上次演示残留：{stale} 仍是 offline —— 先跑 "
                   f"`demo_arm.py --fix-status`（或直接起栈，会自动恢复）")
    return ok, bad


async def status_card(conn: asyncpg.Connection, observer: Observer, api: str,
                      quiet: bool = False) -> str:
    """一块状态行：机械臂 + 最近工单 + 最近舵机回读 + 最近 MQTT 报文。

    返回本次的「状态指纹」—— 调用方用它判断要不要重画（演示时每 3 秒刷一屏
    同样的内容很吵，只有**真的变了**才值得打印）。
    """
    dev = await conn.fetchrow(
        "select device_id, status, last_heartbeat, meta from t_device where device_id = $1", ARM)
    task = await conn.fetchrow(
        "select task_id, status, robot_id, created_at from t_task "
        "where robot_id = $1 order by id desc limit 1", ARM)
    track = await conn.fetchrow(
        "select id, servo_telemetry, battery, bin_plastic, recorded_at from t_track "
        "where robot_id = $1 order by id desc limit 1", ARM)
    meta = (dev or {}).get("meta") or {}
    servo = (track or {}).get("servo_telemetry") or {}
    servos = " ".join(f"#{k}:{v.get('position')}" for k, v in list(servo.items())[:6]) or "—"
    msgs = observer.snapshot()
    sig = f"{(dev or {}).get('last_heartbeat')}|{(task or {}).get('status')}|" \
          f"{(track or {}).get('id')}|{len(msgs)}"
    if quiet:
        return sig

    print(f"\n[{datetime.now():%H:%M:%S}] 机械臂 {ARM} {(dev or {}).get('status', '—')} · "
          f"电量 {meta.get('battery', '—')}% · 三仓 {meta.get('bins', {})}")
    if task:
        print(f"            最近工单 {task['task_id']} → {task['status']}")
    print(f"            最近舵机回读（{servo and '有' or '无'}）：{servos}")
    for m in msgs[-4:]:
        print(f"            ↳ {m['topic']}  {m['payload'][:110]}")
    if not msgs:
        print("            （MQTT 观察者还没有报文）")
    return sig


async def main() -> int:
    parser = argparse.ArgumentParser(description="机械臂演示一键起栈")
    parser.add_argument("--broker-port", type=int, default=11883)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--ui-port", type=int, default=5173)
    parser.add_argument("--real", action="store_true",
                        help="真机模式：不在本机起桥接层，而是打印树莓派上要跑的命令")
    parser.add_argument("--clean", action="store_true",
                        help="起栈后清场：把机械臂与合并窗口内的滞留活跃工单标 cancelled")
    parser.add_argument("--arm-only", action="store_true",
                        help="把其它机器人临时置 offline（自动派单必落机械臂），退出时恢复")
    parser.add_argument("--no-frontend", action="store_true", help="不起前端（另开终端跑 npm run dev）")
    parser.add_argument("--event", action="store_true",
                        help="起栈后造一条泡沫事件并派单，作为演示起点")
    parser.add_argument("--interval", type=float, default=3.0, help="状态刷新间隔（秒）")
    parser.add_argument("--check", action="store_true",
                        help="只做演示前自检（不起任何服务），几秒钟出结论")
    parser.add_argument("--no-watchdog", action="store_true",
                        help="关闭进程看门狗（默认开着：进程死了自动拉起）")
    parser.add_argument("--auto-repeat", type=float, default=0.0, metavar="秒",
                        help="无人值守循环演示：每隔 N 秒自动给机械臂派一单")
    parser.add_argument("--fix-status", action="store_true",
                        help="只做一件事：把上次演示残留的 offline 机器人恢复 online，然后退出")
    args = parser.parse_args()

    api_base = f"http://127.0.0.1:{args.api_port}"
    ui_base = f"http://127.0.0.1:{args.ui_port}"
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    services: list[Service] = []
    observer = Observer("127.0.0.1", args.broker_port)
    offline_flipped: list[str] = []
    watchdog: Watchdog | None = None
    conn = await asyncpg.connect(**DB, timeout=6)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads,
                              schema="pg_catalog")
    try:
        # ---------- 只修状态：--fix-status ----------
        if args.fix_status:
            banner("恢复上次演示临时置为 offline 的机器人")
            stale = read_arm_only_state()
            if not stale:
                print("  · 没有需要恢复的记录")
                return 0
            await set_robots_status(conn, stale, "online")
            ARM_ONLY_STATE.unlink(missing_ok=True)
            print(f"  ✓ 已恢复 online：{stale}")
            return 0

        # ---------- 演示前自检（--check：只查不起） ----------
        if args.check:
            banner("演示前自检（--check，只读）")
            oks, bads = await preflight(conn, args.api_port, args.ui_port,
                                        args.broker_port, not args.no_frontend)
            for line in oks:
                print(f"  ✓ {line}")
            for line in bads:
                print(f"  ✗ {line}")
            print()
            if bads:
                print(f"❌ 不要开演：{len(bads)} 项需要先处理")
                return 1
            print("✅ 可以开演（真机请再确认：树莓派桥接层在跑、9 点标定 + 放置点已示教）")
            return 0

        # ---------- 前置自检 ----------
        banner("[1/5] 前置自检")
        print(f"  数据库：{(await conn.fetchval('select version()')).split(' on ')[0]}")
        arm_row = await conn.fetchrow(
            "select device_id, status, meta from t_device where device_id = $1", ARM)
        print(f"  机械臂设备：{'已登记 · ' + str(arm_row['status']) if arm_row else '未登记（将自动登记）'}")

        # 上一次 --arm-only 被强杀（没走到收尾）时留下的 offline 状态，这里自愈
        stale = read_arm_only_state()
        if stale:
            await set_robots_status(conn, stale, "online")
            print(f"  修复上次演示残留：已把 {stale} 恢复为 online")
            ARM_ONLY_STATE.unlink(missing_ok=True)

        # ---------- broker ----------
        banner("[2/5] 启动 MQTT broker（临时 amqtt）")
        broker = Service("broker", [str(PY), str(HERE / "mqtt_broker.py"),
                                    "--port", str(args.broker_port)],
                         HERE, {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
                         DEMO_DIR / f"broker_{stamp}.log")
        broker.start()
        services.append(broker)
        if not await wait_until(lambda: "BROKER READY" in broker.tail(40), 30, 0.4):
            print(broker.tail(15))
            raise RuntimeError("broker 未就绪")
        print(f"  ✓ 127.0.0.1:{args.broker_port}")

        # ---------- 后端 ----------
        banner("[3/5] 启动平台后端（演示纪律：不跑定时补派）")
        backend_env = {
            **os.environ,
            "APP_ENV": "development", "DEBUG": "true",
            "POSTGRES_HOST": DB["host"], "POSTGRES_PORT": str(DB["port"]),
            "POSTGRES_DB": DB["database"], "POSTGRES_USER": DB["user"],
            "POSTGRES_PASSWORD": DB["password"],
            "REDIS_HOST": "127.0.0.1", "REDIS_PORT": "6379", "REDIS_PASSWORD": "",
            "MQTT_HOST": "127.0.0.1", "MQTT_PORT": str(args.broker_port),
            "MQTT_USERNAME": "backend_service", "MQTT_PASSWORD": "demo-local",
            "MQTT_TOPIC_PREFIX": "marine",
            "SECRET_KEY": "demo-local-secret-key-0123456789abcd",
            "BACKGROUND_WORKERS_ENABLED": "false",
            "CORS_ORIGINS": f"{ui_base},http://localhost:{args.ui_port}",
            "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
        }
        backend = Service("backend", [str(PY), "run_server.py", "--host", "127.0.0.1",
                                      "--port", str(args.api_port)],
                          BACKEND, backend_env, DEMO_DIR / f"backend_{stamp}.log")
        backend.start()
        services.append(backend)

        async with httpx.AsyncClient(base_url=api_base, timeout=10) as client:
            async def ready() -> bool:
                if not backend.alive():
                    return False
                try:
                    return (await client.get("/api/v1/robots")).status_code == 200
                except Exception:  # noqa: BLE001
                    return False

            if not await wait_until(ready, 90, 1.0):
                print(backend.tail(20))
                raise RuntimeError("后端未就绪")
            print(f"  ✓ {api_base}")

            ctx_token = (await client.post("/api/v1/auth/login", json={
                "username": OPERATOR[0], "password": OPERATOR[1]})).json()
            token = (ctx_token.get("data") or {}).get("access_token", "")
            headers = {"Authorization": f"Bearer {token}"}
            print(f"  ✓ 演示账号可登录：{OPERATOR[0]}")

            # ---------- 前端 ----------
            if not args.no_frontend:
                banner("[4/5] 启动平台前端（vite preview，服务已构建产物）")
                npm = "npm.cmd" if os.name == "nt" else "npm"
                frontend = Service("frontend", [npm, "run", "preview", "--", "--port",
                                                str(args.ui_port), "--strictPort"],
                                   FRONTEND, {**os.environ, "VITE_BACKEND_URL": api_base},
                                   DEMO_DIR / f"frontend_{stamp}.log")
                frontend.start()
                services.append(frontend)

                async def ui_ready() -> bool:
                    if not frontend.alive():
                        return False
                    try:
                        async with httpx.AsyncClient(timeout=5) as c:
                            return (await c.get(ui_base)).status_code < 400
                    except Exception:  # noqa: BLE001
                        return False

                if await wait_until(ui_ready, 60, 1.0):
                    print(f"  ✓ {ui_base}")
                else:
                    print(f"  ⚠️ 前端未就绪，看 {frontend.log}；可 --no-frontend 自己跑 npm run dev")
            else:
                banner("[4/5] 跳过前端（--no-frontend）")
                ui_base = "（自己起前端：cd frontend && npm run dev）"

            # ---------- 桥接层 ----------
            banner("[5/5] 机械臂桥接层")
            if args.real:
                print("""  真机模式：桥接层必须跑在树莓派上（那里才有 ROS 与该机械臂的驱动）。
  请在树莓派上执行（edge/ 已就位时）：

    cd <repo>/edge && \\
      OCEANUS_MQTT_HOST=<平台 IP> OCEANUS_MQTT_PORT=1883 \\
      OCEANUS_MQTT_USER=robot_device OCEANUS_MQTT_PASSWORD=<口令> \\
      python3 -m arm_bridge.main --config arm_bridge/config.yaml --driver oceanus_vision

  或直接用 systemd 单元：edge/grasp/deploy/systemd/oceanus-arm-bridge.service
  ★ 上真机前先跑 edge/grasp/tools/precheck.py（配置/模型/标定/放置点/相机五项）。""")
            else:
                import yaml

                cfg = yaml.safe_load((EDGE / "arm_bridge" / "config.yaml").read_text(encoding="utf-8"))
                cfg["site_id"] = SITE
                cfg["device_id"] = ARM
                cfg["mqtt"].update({"host": "127.0.0.1", "port": args.broker_port,
                                    "username": "robot_device", "password": "demo-local"})
                cfg["driver"]["backend"] = "oceanus_vision"
                cfg["driver"].setdefault("oceanus_vision", {})
                cfg["driver"]["oceanus_vision"].update({
                    "mock": True, "config_path": str(EDGE / "grasp" / "config.yaml"),
                    "calibration_path": None, "review_result": "recheck"})
                cfg_path = DEMO_DIR / f"arm_bridge_{stamp}.yaml"
                cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False),
                                    encoding="utf-8")
                bridge = Service("bridge",
                                 [str(PY), "-m", "arm_bridge.main", "--config", str(cfg_path),
                                  "--driver", "oceanus_vision"],
                                 EDGE,
                                 {**os.environ, "OCEANUS_MQTT_HOST": "127.0.0.1",
                                  "OCEANUS_MQTT_PORT": str(args.broker_port),
                                  "OCEANUS_MQTT_USER": "robot_device",
                                  "OCEANUS_MQTT_PASSWORD": "demo-local",
                                  "OCEANUS_MQTT_PROTOCOL": "311",
                                  "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                                  "PYTHONUNBUFFERED": "1"},
                                 DEMO_DIR / f"bridge_{stamp}.log")
                bridge.start()
                services.append(bridge)
                if not await wait_until(lambda: "waiting for tasks" in bridge.tail(40)
                                        or not bridge.alive(), 60, 0.5):
                    print(bridge.tail(20))
                    raise RuntimeError("桥接层未就绪")
                print("  ✓ 桥接层已连接（mock 执行端：合成画面 + 模拟舵机回读）")

            # ---------- 演示准备 ----------
            observer.start()
            await conn.execute(
                """
                insert into t_device (device_id, device_type, name, location, status, meta,
                                      last_heartbeat)
                values ($1, 'robot'::device_type_enum, $2,
                        ST_SetSRID(ST_MakePoint($3, $4), 4326)::geometry,
                        'online'::device_status_enum, $5::jsonb, now())
                on conflict (device_id) do update
                   set device_type = 'robot'::device_type_enum, status = 'online'::device_status_enum
                """,
                ARM, "机械臂一号（Oceanus Arm）", ARM_LNG, ARM_LAT,
                {"battery": 100, "bins": {"foam": 0.0, "plastic": 0.0, "mixed": 0.0},
                 "chassis": "arm", "hull": "双体", "arm": "ArmPi FPV 6-DOF（Oceanus Arm）",
                 "home": {"lng": ARM_LNG, "lat": ARM_LAT}},
            )

            if args.clean:
                banner("演示清场")
                await cleanup_active_tasks(conn, ARM, lambda s: print(f"  · {s}"))
                await cleanup_merge_window(conn, ARM_LNG, ARM_LAT, lambda s: print(f"  · {s}"))

            if args.arm_only:
                cands = await robot_candidates(conn, ARM_LNG, ARM_LAT)
                others = [c["device_id"] for c in cands if c["device_id"] != ARM]
                # ★ 与上一轮残留的清单取并集：上一次被强杀时别的机器人已经是 offline，
                #   这次 `robot_candidates` 看不到它们 —— 若直接覆盖状态文件，恢复依据就丢了。
                merged = sorted(set(read_arm_only_state()) | set(others))
                await set_robots_status(conn, merged, "offline")
                offline_flipped = merged
                write_arm_only_state(merged)
                print(f"  · 其它机器人已置 offline（自动派单必落机械臂）：{merged}")
                print("  · 退出时会自动恢复；被强杀也能在下次启动时自愈")

            if args.event:
                cam_last = await conn.fetchval(
                    "select coalesce(max(seq),0) from t_event where device_id = 'CAM-MABI-01'")
                eid = f"EVT-DEMO-{stamp}"
                resp = await client.post("/api/v1/events", json={
                    "event_id": eid, "device_id": "CAM-MABI-01", "device_type": "shore_camera",
                    "timestamp": datetime.now().astimezone().isoformat(),
                    "location": {"lng": ARM_LNG, "lat": ARM_LAT},
                    "detections": [{"class": "foam", "confidence": 0.92,
                                    "bbox": [10, 10, 60, 60]}],
                    "aggregate": {"main_class": "foam", "count": 1, "max_confidence": 0.92},
                    "seq": int(cam_last) + 1}, headers=headers)
                ok, detail = api_ok(resp)
                print(f"  · 演示事件已造：{eid}（{detail}）")

            demo_card(api_base, ui_base, args.real, args.broker_port)

            # ---------- 看门狗：演示中进程挂了自动拉起 ----------
            if not args.no_watchdog:
                watchdog = Watchdog(services)
                watchdog.start()
                print("  · 进程看门狗已开启：任一服务退出会在 2 秒内自动重启")

            print("\n状态（只在**有变化**时重画；Ctrl+C 结束演示，会自动停服务并恢复机器人状态）")

            last_sig = ""
            idle_ticks = 0
            next_auto = time.time() + args.auto_repeat if args.auto_repeat > 0 else 0.0
            if args.auto_repeat > 0:
                print(f"  · 无人值守循环演示：每 {args.auto_repeat:.0f} 秒自动给机械臂派一单")

            while True:
                try:
                    sig = await status_card(conn, observer, api_base, quiet=True)
                    if sig != last_sig:
                        await status_card(conn, observer, api_base)
                        last_sig = sig
                        idle_ticks = 0
                    else:
                        idle_ticks += 1
                        if idle_ticks % 10 == 0:      # 每 10 拍提醒一次"还活着"
                            print(f"  · {datetime.now():%H:%M:%S} 无变化，脚本仍在监听 "
                                  f"（机械臂在线待命）")
                except Exception as exc:  # noqa: BLE001
                    print(f"  （状态读取失败：{exc}）")

                if next_auto and time.time() >= next_auto:
                    next_auto = time.time() + args.auto_repeat
                    try:
                        resp = await client.post(
                            "/api/v1/tasks",
                            json={"robot_id": ARM,
                                  "target": {"lng": ARM_LNG, "lat": ARM_LAT},
                                  "priority": 3},
                            headers=headers)
                        k, d = api_ok(resp)
                        tid = (resp.json().get("data") or {}).get("task_id", "—")
                        print(f"  · [循环演示] 已派单 {tid}（{d}）")
                    except Exception as exc:  # noqa: BLE001
                        print(f"  · [循环演示] 派单失败：{exc}")
                await asyncio.sleep(args.interval)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if services or offline_flipped:
            print("\n正在收尾 …")
        if watchdog is not None:
            watchdog.stop()
        observer.stop()
        if offline_flipped:
            try:
                await set_robots_status(conn, offline_flipped, "online")
                ARM_ONLY_STATE.unlink(missing_ok=True)
                print(f"  已恢复机器人 online：{offline_flipped}")
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠️ 恢复机器人状态失败，请手动改回：{exc}")
                print(f"     （状态文件留着：{ARM_ONLY_STATE}，下次启动会自动恢复）")
        for svc in reversed(services):
            svc.stop()
        if services:
            print(f"  已停服务；日志在 {DEMO_DIR}")
        await conn.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
