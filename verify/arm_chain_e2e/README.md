# 机械臂链路：演示一键起栈 + 端到端验收

两个脚本，用途不同：

| 脚本 | 干什么 | 什么时候用 |
| --- | --- | --- |
| `demo_arm.py` | **一键起演示栈**（临时 broker + 后端 + 前端 + 桥接层）+ 演示动线卡 + 实时状态 | 演示/彩排前 30 秒 |
| `run_e2e.py` | **端到端验收**：派单→机械臂→回传→落库→API，32 项断言 + 报告 | 改完代码后 / 演示前最后一次确认 |

## 演示：一条命令起栈

```powershell
make demo-arm-check   # ① 演示前自检（只读，10 秒）：能开演 / 不要开演 + 具体原因
make demo-arm-live    # ② 正式起栈：清场 + 只让机械臂在线 + 造一条泡沫事件
make demo-arm         #    彩排（本机无硬件，桥接层用 mock 执行端）
make demo-arm-real    #    真机：不在本机假装真机，打印树莓派上要跑的命令
make demo-arm-fix     # ③ 救场：把上次残留的 offline 机器人恢复（自检会提示）
```

起完打印**一张演示动线卡**：平台入口（默认 <http://127.0.0.1:5173>）、演示账号、
「人工建单已预选机械臂 + 坐标已预填」、三种让机械臂动起来的方式、"回来看哪三处数据"，
以及**⑤万一出问题怎么办**的 30 秒救场步骤。之后每 3 秒刷新一块状态
（机械臂在线/电量/三仓/当前工单/最近舵机回读/最近 MQTT 报文），**只在有变化时重画**。

### 演示不翻车的四道保险

| 保险 | 行为 |
| --- | --- |
| **进程看门狗** | 后端 / 前端 / 桥接层 / broker 任一退出，2 秒内自动重启并打印「⚠️ 自动重启（第 N 次）」；连续存活 5 分钟会清零重启计数（展台长时间循环演示不会用光额度）。已实测：杀掉桥接层进程后自动拉起，工单继续跑通 |
| **演示前自检** | `--check` 逐项验：数据库/设备在位/端口(8000/5173/11883)占用/前端产物是否比源码旧/作业台跳转配置/视觉模型/9 点标定/**上次演示残留的 offline 状态**；有阻断项直接给「❌ 不要开演」 |
| **状态自愈** | `--arm-only` 的恢复清单落盘（容忍 BOM）；被强杀也能在下次启动或 `--fix-status` 时自动恢复 |
| **无人值守循环** | `--auto-repeat 15` 每 15 秒自动派一单（展台/彩排循环演示，数据会持续滚动） |

### 演示前顺手修掉的两个坑

- `frontend/.env.local` 里残留的 `VITE_BACKEND_URL=http://localhost:8010` 已注释掉
  （它是当时截屏用的临时指向；现在回到默认 8000，与 `make dev-backend` 一致）。
- `frontend/vite.config.js` 给 `preview` 补了与 `server` 相同的 `/api`、`/stream` 代理 ——
  否则 `npm run preview` 服务的是静态产物、`/api/v1` 会 404（表现为"登录没反应"）。
  演示用 `preview` 比 `dev` 稳（无 HMR、跑的就是构建产物）。

## 验收：一条命令验完

```powershell
.\.venv-analysis\Scripts\python.exe verify\arm_chain_e2e\run_e2e.py
# 想在浏览器里手动看页面：加 --keep-running（跑完不退出，打印端口）
```

产物落在 `verify/arm_chain_e2e/runs/<时间戳>/`：`report.md`（断言表 + MQTT 时间线）、
`mqtt_timeline.json`、`backend.log`、`bridge.log`、`arm_bridge.e2e.yaml`。

## 这条链上什么是真的、什么是 mock

| 环节 | 真/假 | 说明 |
| --- | --- | --- |
| Postgres `seasight` | **真** | 本机 PG17 里的项目库（52 张表 + 演示种子数据） |
| MQTT broker | **真** | `mqtt_broker.py`（amqtt）：真实 MQTT 3.1.1、QoS1/PUBACK、LWT、通配符订阅 |
| 平台后端 | **真** | `backend/run_server.py`（uvicorn + aiomqtt + 派单引擎 + 全部 handler + 状态机） |
| 桥接层 | **真** | `edge/arm_bridge`（paho 客户端，与生产同一个入口） |
| 视觉闭环驱动 | **真** | `oceanus_vision`（YOLO→IK→舵机那份代码，走注册表加载） |
| 机械臂动作 / 相机 / 舵机回读 | **mock** | `edge/grasp` 的 mock 后端合成画面与舵机读数（本机没有 ROS 与硬件） |

所以它证明的是**报文、状态机与数据落库**，不是物理拾取；对外口径仍是 **E1/E2**，
不得写成"真机现场验证"。真机上线前必须再跑 `edge/grasp/tools/precheck.py` 与 9 点标定。

## 验证的两条派单路径

1. **人工指派**（工单看板「人工建单」并选机器人）：`POST /tasks {robot_id}` →
   平台下发 → 桥接收单 → ACK → collecting → 抓取+入槽 → done。
2. **事件自动派单**（摄像头发现泡沫）：`POST /events` → 派单引擎按
   「类别匹配加权 → 距离最近」选机器人 → 同一条链 → 完成后事件转 `resolved`。

第 2 条会先按**当前演示数据**原样跑一次并记录引擎选了谁；再把其它机器人临时置为
`offline` 复跑一次，确定性验证「自动派单 → 机械臂」这一段（跑完恢复状态）。

## 断言清单（32 项）

- broker/后端/桥接层就绪；桥接层上线状态（retained）已上报
- MQTT 时间线：`robot/<id>/task`、`cmd/ack`、`task/progress`(collecting→done)、
  `marine/<site>/<id>/telemetry`（`servos` 非空）
- `t_task`：`assigned → done`、`collected_weight`、`review_result`、`finished_at`
- `t_task_ack`：`accepted=true` 的规范回执落库（审计/判重）
- `t_track`：新增轨迹行且 **`servo_telemetry` 非空**（逐舵机回读 = "机械臂真的动了"的硬证据）
- `t_device`：`last_heartbeat` 推进、meta 电量/仓容被遥测覆盖、**任务终结后摘掉 `current_task_id`**
- `t_event`：任务完成后转 `resolved`
- 平台 API：`/tasks/{id}`、`/tasks/{id}/acks`、`/robots`、`/devices/{id}`、
  `/simulations/{task_id}/trajectory`（前端控制台读的那份舵机数据）

## 前置条件

- 本机 Postgres 17（`seasight` 库）与 Redis 在跑；口令默认 `seasight/seasight`，
  可用 `POSTGRES_*` 环境变量覆盖。
- `.venv-analysis` 里有 `amqtt / paho-mqtt / httpx / asyncpg`（缺 amqtt：
  `pip install amqtt`）。
- 不需要 Docker、不需要 EMQX、不需要树莓派。

## 诊断小工具

| 脚本 | 用途 |
| --- | --- |
| `mqtt_broker.py` | 单独起一台临时 broker（本机没有 EMQX 时给桥接层/后端用） |
| `smoke_broker.py` | broker 冒烟：连上、订 `marine/#`、QoS1 收发 |
| `probe_db.py` | 库表与种子数据概览（设备/账号/分区） |
| `probe_device.py` | `t_device` 列结构与样例（插设备时要照这个形状） |
| `probe_events.py` | 待派单事件积压（补派按 `event_time ASC` 取前 N 条） |
| `probe_distances.py` | 各机器人到事件的真实距离 —— 解释"为什么派给了它" |

## 踩过的坑（都会让链路"看起来通了其实没通"）

1. **MQTT 协议版本**：桥接层默认 MQTT **v5**（生产 EMQX 支持），而本地临时 broker
   （amqtt）只支持 3.1.1 → CONNECT 直接被拒。用 `OCEANUS_MQTT_PROTOCOL=311` 切换
   （与 `OCEANUS_MQTT_HOST/PORT/USER/PASSWORD` 同一组 env 覆盖，生产默认不变）。
2. **CONNACK 竞态**：paho 的 `connect()` 只完成 TCP 握手，连接结果在异步回调里。
   不等 CONNACK 就 `publish_online()`，上线状态会被**静默丢弃**（平台侧看不到机械臂上线）。
   `MqttTransport.connect()` 现在会等 CONNACK，等不到就明确报错。
3. **事件 seq 判重**：同设备的 `seq` 必须递增，否则事件被拒（HTTP 200 但 `body.code≠0`，
   库里不留行）。平台约定 HTTP 200 ≠ 业务成功，判断要看 `body.code`。
4. **防抖合并窗口**：10 分钟内、200 米内的活跃工单会被复用 —— 事件合并进去而**不新建工单**。
   库里有上一轮测试的活跃工单时，新事件"入库成功但没有工单"。脚本会先清掉合并窗口内的
   活跃工单（都是它自己造的）。
5. **同类任务顺路复用优先于距离**：派单引擎排序是 `(类别匹配权重, 距离)`。别的机器人手上
   有同类在途工单时，**0 米的机械臂也会被跳过**（实测派给了 3.2 公里外的 RBT-001）。
   演示前先清场，或直接用人工指派。
6. **演示纪律**：脚本用 `BACKGROUND_WORKERS_ENABLED=false` 起后端（与录屏口径一致），
   否则定时补派会不停给演示库里那批滞留工单派单（无 ACK → 超时 → 再派），既刷屏又抢机械臂。
7. **演示账号**：`operator / operator123456`（见 `backend/scripts/bootstrap_demo_users.py`）。

## 口径红线

- mock 执行端 ≠ 真机执行；本脚本结果不得对外写成"真机现场验证/已交付"。
- `servo_telemetry` 有值只说明"驱动侧有回读并上报"，真机上线后要用
  `edge/grasp/tools/precheck.py` + 实拍确认物理动作。
- 不要在演示库里留下本脚本造的工单/事件；`report.md` 会列出本次产生的工单号。
