# MQTT 主题树设计规范

> 设备接入的唯一契约。三组（算法 / 硬件 / 平台）按本文档并行开发，互不阻塞。

---

## 一、为什么选 MQTT

| 需求 | MQTT | HTTP 轮询 | WebSocket |
| --- | --- | --- | --- |
| 移动网络（4G/5G，会抖动、会断） | ✅ 为不稳定网络设计，自带重连与遗嘱 | ❌ 每次都要建连 | ⚠️ 长连接维持成本高 |
| 设备数量级 | ✅ 单 broker 十万级连接 | ⚠️ 轮询压力大 | ⚠️ 连接数受限 |
| 功耗（渔港设备靠太阳能） | ✅ 支持休眠 + 心跳 | ❌ 持续唤醒 | ❌ 长连接耗电 |
| 弱网下不丢关键消息 | ✅ QoS1 + 本地队列 | ❌ 失败即丢 | ⚠️ 需自行实现 |

渔港现场的现实：4G 信号时好时坏，设备装在太阳能供电的杆子上。MQTT 的遗嘱消息（LWT）能让我们**立刻**知道设备掉线，而不是等心跳超时。

---

## 二、主题树

### 2.1 结构设计原则

```
marine/{site_id}/{device_id}/{action}      设备上行 & 平台下发
robot/{robot_id}/{action}[/{sub_action}]   机器人专用通道
```

**三条硬规则**：

1. **禁止前导斜杠**。`/marine/...` 与 `marine/...` 在 MQTT 中是两个不同主题，前导斜杠会造成静默失配。
2. **全小写**。主题大小写敏感，`Event` 与 `event` 会被当作两个主题。
3. **结构静态、变量在 payload**。不要把类别、时间戳放进主题层级——否则订阅通配符会爆炸，且 ACL 无法按固定规则配置。

### 2.2 完整主题表

| 主题 | 方向 | QoS | retain | 说明 |
| --- | --- | --- | --- | --- |
| `marine/{site}/{dev}/event` | 设备 → 平台 | **1** | ❌ | 垃圾检测事件 |
| `marine/{site}/{dev}/telemetry` | 设备 → 平台 | **0** | ❌ | 心跳 / 电量 / 仓容 |
| `marine/{site}/{dev}/status` | 设备 → 平台 | 1 | ✅ | 在线状态（含 LWT） |
| `marine/{site}/{dev}/cmd` | 平台 → 设备 | 1 | ❌ | 通用指令下发 |
| `marine/{site}/{dev}/cmd/ack` | 设备 → 平台 | 1 | ❌ | 指令回执 |
| `robot/{robot_id}/task` | 平台 → 机器人 | **1** | ❌ | 派单下发 |
| `robot/{robot_id}/task/progress` | 机器人 → 平台 | 1 | ❌ | 作业进度回传 |
| `robot/{robot_id}/cmd/ack` | 机器人 → 平台 | 1 | ❌ | 任务确认（ACK） |

后端订阅通配符（见 `backend/app/mqtt/topics.py`）：

```
marine/+/+/event
marine/+/+/telemetry
marine/+/+/status
robot/+/task/progress
robot/+/cmd/ack
```

> **禁止使用 `#` 大范围订阅**。`#` 会订阅到所有主题（包括 `$SYS` 系统主题与 topic 元数据），既浪费带宽也带来安全隐患。用 `+` 精确到层级。

### 2.3 为什么 `site_id` 要放在第二层

它是 **ACL 的隔离维度**。EMQX 按 clientid 前缀授权时，站点可作为粗粒度的权限边界：

```
lianjiang 站的边缘盒 → 只允许 publish marine/lianjiang/{自己的device_id}/#
```

如果 `site_id` 塞进 payload，ACL 就无法用主题模式表达，只能写 Lua 脚本——复杂度上一个台阶。

---

## 三、QoS 选择

| 等级 | 语义 | 开销 | 本项目用途 |
| --- | --- | --- | --- |
| QoS0 | 至多一次（可能丢） | 1 次传输 | 遥测（高频、丢一帧无所谓） |
| QoS1 | 至少一次（可能重） | 2 次握手 | **事件与指令**（必须送达，需幂等） |
| QoS2 | 恰好一次 | 4 次握手 | **不用** |

### 为什么不用 QoS2

QoS2 的两次往返握手在弱网下显著增加延迟与失败窗口。而且它并不能免除幂等设计——**真正的去重必须靠业务主键，而不是协议保证**。

我们用 `(device_id, seq)` 唯一约束做幂等（见第四节），在这个前提下 QoS1 完全够用。

### QoS1 的代价必须正视

QoS1 是「至少一次」——**重复投递是正常行为，不是异常**。所以：

- `EventService.ingest()` 必须先查 `(device_id, seq)` 再落库
- 数据库层用唯一约束兜底（并发下应用层预查可能漏）
- 模拟器提供 `--dup-rate` 参数，专门用来验证这条

---

## 四、幂等设计：`seq` 单调序号

### 4.1 机制

每个边缘设备维护一个**单调递增**的序号 `seq`，随事件一起上报。平台侧：

```sql
CONSTRAINT uq_event_device_seq UNIQUE (device_id, seq)
```

**为什么是 `(device_id, seq)` 组合而不是只用 seq**：多设备各自从 1 开始计数，只用 seq 会互相冲突。

### 4.2 `seq` 必须持久化

这是最容易被忽略、也最容易在演示时翻车的点：

```
边缘盒跑到 seq=4821，突然断电重启
   ↓
如果 seq 从内存归零 → 重启后第一条事件是 seq=1
   ↓
而平台里 (device, 1) 已经存在 → 平台判为重复，直接忽略！
   ↓
结果：设备重启后所有事件都被吞掉，且没有任何报错
```

**正确做法**：`seq` 落到本地文件（本项目模拟器写到 `.simulator_state.json`），每次自增后同步落盘，重启时读取续上。

```json
{
  "CAM-MABI-01": { "seq": 4821 },
  "CAM-HUANGQI-01": { "seq": 3107 }
}
```

### 4.3 `event_id` 也要唯一

`seq` 防的是**同一设备的重传**；`event_id` 防的是**跨设备的碰撞**（以及日志里人工可见的编号）。

命名规范：`evt_{device_id}_{seq:06d}`，例如 `evt_CAM-MABI-01_000123`。

---

## 五、报文契约

### 5.1 事件上报 `marine/{site}/{dev}/event`

**QoS1**。平台侧由 `handle_event` 处理。

```json
{
  "event_id": "evt_CAM-MABI-01_000123",
  "device_id": "CAM-MABI-01",
  "device_type": "shore_camera",
  "timestamp": "2026-09-18T01:23:45+08:00",
  "location": { "lng": 119.6531, "lat": 26.3867 },
  "detections": [
    { "class": "foam", "confidence": 0.91, "bbox": [412, 288, 468, 331] },
    { "class": "foam", "confidence": 0.83, "bbox": [520, 305, 561, 344] }
  ],
  "aggregate": { "main_class": "foam", "count": 2, "max_confidence": 0.91 },
  "evidence_url": "http://minio:9000/events/2026/09/18/evt_...jpg",
  "model_version": "det_v0.1.0",
  "seq": 123
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `event_id` | string(64) | ✅ | 全局唯一 |
| `device_id` | string(64) | ✅ | 必须已注册 |
| `device_type` | enum | ✅ | `shore_camera` / `drone` / `robot` |
| `timestamp` | ISO8601 | ✅ | **设备本地时间**，带时区 |
| `location` | object | ✅ | WGS84 经纬度 |
| `detections` | array | ⚠️ | 可为空数组（边缘端已聚合） |
| `detections[].class` | enum | ✅ | `foam` / `plastic` / `fishing_gear` / `other` |
| `detections[].confidence` | float | ✅ | 0~1 |
| `detections[].bbox` | int[4] | ✅ | `[x1, y1, x2, y2]` **像素坐标**，原点左上 |
| `aggregate` | object | ✅ | 边缘端聚合结果，**平台不重新聚合** |
| `aggregate.main_class` | enum | ✅ | `foam` / `plastic` / `fishing_gear` / `other` |
| `aggregate.count` | int | ✅ | ≥1 |
| `aggregate.max_confidence` | float | ✅ | 0~1 |
| `evidence_url` | string | ❌ | 证据帧地址，可后补 |
| `model_version` | string(32) | ❌ | 缺省用平台配置值 |
| `seq` | int | ✅ | ≥0，同设备单调递增 |

**关于 `bbox` 的坐标系**：约定原点在**左上角**，单位像素，基于设备原始分辨率。前端叠加检测框时按 `bbox / 分辨率 × 100%` 转成百分比定位，所以报文的 `bbox` 与分辨率必须同源，否则框会错位。

**为什么平台不重新聚合**：边缘端已经算过一遍，平台再算一遍纯属浪费算力，还会因为采样时机不同产生不一致。平台**信任 edge 的 aggregate，只把 detections 存档**。

### 5.2 遥测 `marine/{site}/{dev}/telemetry`

**QoS0**。平台侧由 `handle_telemetry` 处理。

```json
{
  "device_id": "RBT-001",
  "device_type": "robot",
  "timestamp": "2026-09-18T01:23:50+08:00",
  "location": { "lng": 119.6541, "lat": 26.3869 },
  "status": "collecting",
  "battery": 87,
  "bins": { "foam": 0.42, "plastic": 0.18, "mixed": 0.09 },
  "task_id": "tsk_20260918_a3f2c9",
  "speed": 0.8
}
```

| 字段 | 说明 |
| --- | --- |
| `status` | `idle` / `navigating` / `collecting` / `returning` / `error` |
| `battery` | 0~100 整数百分比 |
| `bins` | 三仓占用率，各 0~1 浮点 |
| `speed` | m/s，可选 |

**平台对遥测做两件额外的事**：
1. 更新 `t_device.meta` 里的 `battery` 与 `bins` —— **派单引擎直接读这里判断可用性**
2. 写一条 `t_track` 轨迹点

> **为什么 `bins` 这么重要**：产品设计里机器人是"打捞即粗分三仓"。如果遥测不带仓容，平台上三仓就是三个永远为 0 的进度条——概念验证时会直接被问倒。所以仓容遥测是**功能**，不是"锦上添花的监控"。

### 5.3 设备状态 `marine/{site}/{dev}/status`

**QoS1 + retain=true**。由 LWT 与设备主动上报共同使用。

```json
{ "device_id": "RBT-003", "online": false, "ts": "2026-09-18T01:20:00+08:00" }
```

### 5.4 派单下发 `robot/{robot_id}/task`

**QoS1**，平台 → 机器人。由 `MqttClient.publish_task()` 发出。

```json
{
  "task_id": "tsk_20260918_a3f2c9",
  "target": { "lng": 119.6531, "lat": 26.3867 },
  "priority": 1,
  "issued_at": "2026-09-18T01:23:46+08:00"
}
```

`priority`：1 = 最高（泡沫类），3 = 普通，5 = 默认，9 = 最低。

> **派单引擎实际使用的取值只有两个**：`foam` / `fishing_gear`
> （即 `WasteClass.HIGH_PRIORITY`）→ **1**，其余类别 → **3**。
> 这个映射的**唯一真源是 `models/task.py` 的 `TaskPriority`**
> —— 全工程不得再写 `1 if ... else 3` 的字面量。
> `5` 是数据库列的默认值（人工建任务未指定时），`9` 是语义下界。
> 分级依据直接引用 `WasteClass.HIGH_PRIORITY`，
> 调整「哪些类别算高优先级」只需改那一处。

### 5.5 任务 ACK `robot/{robot_id}/cmd/ack`

**QoS1**。机器人收到派单后**立即**回 ACK。

```json
{
  "task_id": "tsk_20260918_a3f2c9",
  "robot_id": "RBT-001",
  "accepted": true,
  "eta_seconds": 240,
  "ts": "2026-09-18T01:23:48+08:00"
}
```

平台收到后把任务从 `assigned` 推进到 `navigating`。

**为什么必须有 ACK**：MQTT 的 QoS1 只保证「送达 broker」，**不保证「设备收到并处理」**。如果没有应用层 ACK，平台无法区分「机器人正在赶来」与「派单石沉大海」。ACK 超时（默认 15 秒）会触发任务回退重派——这是避免工单永久卡死的唯一手段。

### 5.6 作业回传 `robot/{robot_id}/task/progress`

**QoS1**。状态变更时上报，不是高频。

```json
{
  "task_id": "tsk_20260918_a3f2c9",
  "robot_id": "RBT-001",
  "status": "done",
  "progress": 1.0,
  "collected_weight": 12.5,
  "review_result": "confirmed",
  "evidence_url": "http://minio:9000/events/tasks/tsk_..._after.jpg",
  "bins_after": { "foam": 0.55, "plastic": 0.21, "mixed": 0.10 },
  "ts": "2026-09-18T01:53:45+08:00"
}
```

| `status` | 平台动作 |
| --- | --- |
| `navigating` | `assigned` → `navigating` |
| `collecting` | `navigating` → `collecting`（记录 `started_at`） |
| `returning` | 映射为 `collecting`（返航仍属作业中） |
| `done` | `collecting` → `done`（记录 `finished_at`；同步事件状态为 `resolved`） |

`review_result` 取值：`confirmed`（复核确认存在垃圾）/ `not_found`（到场未发现，疑似误报）/ `recheck`（需人工复查）。

> **`review_result` 是闭环质量的关键字段**。它让系统能反过来统计**误报率**——如果某台摄像头大量任务都是 `not_found`，说明那个点位的模型需要重训，或者时序校验参数要调。没有这个字段，误报就永远是个说不清的数字。

---

## 六、遗嘱消息（LWT）与在线检测

### 6.1 机制

连接时注册遗嘱：

```
will_topic   = marine/{site}/{dev}/status
will_payload = {"device_id": "<dev>", "online": false, "ts": "<now>"}
will_qos     = 1
will_retain  = true
```

设备正常连上后，**主动发一条 retained 的在线消息**：

```
topic   = marine/{site}/{dev}/status
payload = {"device_id": "<dev>", "online": true, "ts": "<now>"}
qos     = 1
retain  = true
```

此后设备异常断开（断电、掉网、崩溃）时，broker 会代为发布遗嘱消息，平台**立即**知道设备离线。

### 6.2 为什么 retain 在这里是对的

`retain=true` 让 broker 保存该主题的最后一条消息。新订阅者（比如平台重启后重新订阅）连上就能立刻知道每台设备当前是在线还是离线——**不需要等下一次心跳**。

如果不用 retain，平台重启后的头 60 秒里，所有设备状态都是"未知"，大屏会显示一片灰。这在演示场景是灾难。

### 6.3 但 retain 绝不用于事件流

高频事件用 retain 会：① 让 broker 存储膨胀；② 新订阅者会收到一条**过期的历史告警**并被误当成新事件。

**规则：retain 只用于状态类主题（低频、需要"当前值"语义），绝不用于事件流。**

---

## 七、安全与 ACL

### 7.1 认证

EMQX 默认关闭匿名（`EMQX_ALLOW_ANONYMOUS: "false"`）。所有客户端必须提供用户名/密码，通过 `deploy/emqx/bootstrap.csv` 在启动时导入。

### 7.2 授权（ACL）

按 clientid 前缀与主题模式授权：

| 客户端 | clientid 前缀 | 允许 publish | 允许 subscribe |
| --- | --- | --- | --- |
| 边缘盒 | `edge-` | `marine/{site}/{自己的dev}/#` | `marine/{site}/{自己的dev}/cmd` |
| 机器人 | `robot-` | `robot/{自己的id}/#` | `robot/{自己的id}/task` |
| 平台后端 | `seasight-backend` | `robot/+/task`、`marine/+/+/cmd` | `marine/+/+/event`、`marine/+/+/telemetry`、`marine/+/+/status`、`robot/+/task/progress`、`robot/+/cmd/ack` |
| 前端 | — | ❌ 不直连 | ❌ 不直连 |

> **前端绝不直连 MQTT**。浏览器暴露 broker 地址意味着任何人拿到地址就能伪造设备上报。前端只连后端 WebSocket，由后端做 MQTT 的唯一出口。

### 7.3 生产环境必做

- MQTT over TLS，端口 8883
- 每台设备独立凭据（不复用），便于单台吊销
- 打开 EMQX Dashboard 的访问控制并改默认密码
- 关闭 8083（MQTT over WebSocket）——本项目不需要

---

## 八、连接参数

| 参数 | 建议值 | 说明 |
| --- | --- | --- |
| `keepalive` | 60s | 边缘盒；太阳能设备可加到 120s 省电 |
| `clean_session` | false | 让 broker 缓存 QoS1 消息，弱网下减少丢失 |
| `reconnect_interval` | 5s | 断线重连间隔 |
| 本地队列上限 | 1000 条 | 满了丢最旧（新的更重要） |
| 补传批大小 | 20 条/批 | 恢复后按原 seq 顺序补发 |

### 8.1 断网补传的正确顺序

恢复连接后**必须按原 seq 顺序补发**。如果乱序补发，平台的 `(device_id, seq)` 判重仍然生效（不会重复入库），但平台看到的事件时间顺序会错乱，热力图与趋势图会出现"倒流"。

模拟器已实现该路径：断网时事件进 `OutboxBuffer`，恢复后按原顺序分批补发。

---

## 九、调试工具

```bash
# 订阅所有上行主题（看设备到底发了什么）
mosquitto_sub -h localhost -p 1883 \
  -u seasight -P <password> \
  -t 'marine/+/+/event' -t 'marine/+/+/telemetry' -t 'robot/+/#' -v

# 手动发一条事件（触发平台派单）
mosquitto_pub -h localhost -p 1883 \
  -u seasight -P <password> \
  -t 'marine/lianjiang/CAM-MABI-01/event' -q 1 \
  -m '{"event_id":"evt_manual_001","device_id":"CAM-MABI-01","device_type":"shore_camera","timestamp":"2026-09-18T01:00:00+08:00","location":{"lng":119.6531,"lat":26.3867},"detections":[{"class":"foam","confidence":0.9,"bbox":[400,280,470,340]}],"aggregate":{"main_class":"foam","count":1,"max_confidence":0.9},"seq":888001}'

# 模拟机器人 ACK
mosquitto_pub -h localhost -p 1883 \
  -u seasight -P <password> \
  -t 'robot/RBT-001/cmd/ack' -q 1 \
  -m '{"task_id":"tsk_xxx","robot_id":"RBT-001","accepted":true}'

# EMQX Dashboard
open http://localhost:18083    # 默认 admin / 见 .env
```

模拟器（无真实设备时驱动整套演示）：

```bash
cd edge/simulator
python simulator.py --scenario demo --loop          # 演示模式
python simulator.py --scenario demo --dup-rate 0.3  # 验证幂等
python simulator.py --scenario demo --net-drop-every 8 --dry-run   # 看补传报文
python simulator.py --scenario regression --seed 42 --duration 60  # 可复现回归
```

---

相关文档：`architecture.md`（架构与数据流）· `api.md`（HTTP 接口契约）· `deployment.md`（部署）· `development.md`（协作）
