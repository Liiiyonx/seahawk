# 接口契约（HTTP API）

> 基础地址：`http://localhost:8000/api/v1`
>
> 在线文档：`http://localhost:8000/docs`（Swagger）/ `http://localhost:8000/redoc`

---

## 一、通用约定

### 1.1 统一响应信封

**所有**业务接口都返回同一结构：

```json
{
  "code": 0,
  "message": "ok",
  "data": { },
  "trace_id": "a3f2c9d1e8b74f02"
}
```

| 字段 | 说明 |
| --- | --- |
| `code` | `0` = 成功；非 0 = 业务错误码（见 1.3） |
| `message` | 面向用户的中文提示，前端可直接展示 |
| `data` | 业务数据，失败时为 `null` |
| `trace_id` | 链路追踪 ID，排查问题时让用户提供此值 |

**为什么 HTTP 状态码统一 200**：前端 axios 拦截器只需看 `code` 一个维度，不用同时处理 HTTP 状态与业务码两套逻辑。只有系统级错误（参数校验 422、未捕获异常 500）才用非 200。

前端 `src/api/http.js` 的响应拦截器已统一拆信封：调用方直接拿到 `data`。

### 1.2 请求头

| 头 | 说明 |
| --- | --- |
| `X-User` | 用户名（演示阶段的身份传递方式） |
| `X-Role` | `admin` / `operator` / `viewer` |
| `X-Scope` | 数据辖区（乡镇名），operator 使用 |
| `X-Trace-Id` | 可选，客户端自带追踪 ID；不带则服务端生成 |
| `Authorization` | `Bearer <token>`，正式接入时使用 |

### 1.3 错误码表

| 段 | 范围 | 含义 |
| --- | --- | --- |
| 1xxx | 1000–1005 | 通用：未知 / 参数非法 / 未找到 / 未授权 / 无权限 / 冲突 |
| 2xxx | 2001–2003 | 设备：不存在 / 离线 / seq 重复 |
| 3xxx | 3001–3002 | 事件：不存在 / 重复 |
| 4xxx | 4001–4004 | 任务：不存在 / 非法状态跳转 / 无可用机器人 / ACK 超时 |
| 5xxx | 5001–5002 | AI：服务不可用 / 推理失败 |

具体值见 `backend/app/core/exceptions.py::ErrorCode`。

### 1.4 分页结构

```json
{
  "items": [ ],
  "meta": { "total": 128, "page": 1, "page_size": 20 }
}
```

---

## 二、认证 `/auth`

### POST `/auth/login` — 账号登录

**请求**
```json
{ "username": "admin", "password": "admin123456" }
```

**响应**
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "access_token": "eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc...b6a2",
    "token_type": "bearer",
    "expires_in": 86400,
    "role": "admin",
    "full_name": "系统管理员"
  }
}
```

失败返回 `code=1003` + HTTP 401。

### GET `/auth/me` — 当前用户信息

```json
{ "username": "admin", "role": "admin", "township_scope": null, "can_write": true }
```

### GET `/auth/users` — 用户列表（仅 admin）

非 admin 调用返回 `code=1004`。

---

## 三、事件 `/events`

### POST `/events` — 事件上报（HTTP 备用通道）

主通道是 MQTT；此接口用于**调试与冒烟测试**，也作为边缘盒在 MQTT 不可用时的降级路径。

**请求体**
```json
{
  "event_id": "evt_CAM-MABI-01_000123",
  "device_id": "CAM-MABI-01",
  "device_type": "shore_camera",
  "timestamp": "2026-09-18T01:23:45+08:00",
  "location": { "lng": 119.6531, "lat": 26.3867 },
  "detections": [
    { "class": "foam", "confidence": 0.91, "bbox": [412, 288, 468, 331] }
  ],
  "aggregate": { "main_class": "foam", "count": 3, "max_confidence": 0.91 },
  "evidence_url": null,
  "model_version": "det_v0.1.0",
  "seq": 123
}
```

**字段约束**

| 字段 | 约束 |
| --- | --- |
| `event_id` | ≤64 字符，全局唯一 |
| `device_id` | ≤64 字符，**必须已在 `t_device` 注册**，否则返回 `code=2001` |
| `device_type` | `shore_camera` / `drone` / `robot` |
| `aggregate.count` | ≥1 |
| `aggregate.max_confidence` | 0~1 |
| `detections` | 可为空（边缘端已聚合），最多 100 条 |
| `seq` | ≥0，**同设备内单调递增**，用于幂等判重 |

**响应**
```json
{
  "accepted": true,
  "event_id": "evt_CAM-MABI-01_000123",
  "duplicate": false,
  "task_created": true,
  "task_id": "tsk_20260918_a3f2c9",
  "message": "事件已受理"
}
```

`duplicate=true` 表示 `(device_id, seq)` 或 `event_id` 已存在，本次被忽略——这是**正常路径**，不是错误。

高优先级类别（`foam` / `fishing_gear`）会同步触发派单尝试。

### GET `/events` — 事件列表

**查询参数**

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `hours` | 24 | 时间窗口（1~720） |
| `main_class` | — | 类别筛选 |
| `status` | — | `new` / `dispatched` / `resolved` / `ignored` |
| `device_id` | — | 设备筛选 |
| `page` | 1 | 页码 |
| `page_size` | 20 | 每页条数（1~200） |

**响应**（`items[]` 中每项）
```json
{
  "event_id": "evt_demo_0001",
  "device_id": "CAM-MABI-01",
  "event_time": "2026-09-17T23:23:45+08:00",
  "lng": 119.653,
  "lat": 26.387,
  "main_class": "foam",
  "main_class_label": "泡沫类",
  "det_count": 5,
  "max_confidence": 0.91,
  "evidence_url": null,
  "model_version": "det_v0.1.0",
  "status": "new",
  "status_label": "待处理",
  "created_at": "2026-09-17T23:23:45+08:00"
}
```

### GET `/events/heatmap` — 热力图聚合

**查询参数**

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `hours` | 24 | 时间窗口 |
| `grid_size` | 500 | 网格边长（**米**，100~5000） |
| `main_class` | — | 类别筛选 |

**响应**
```json
[
  { "lng": 119.6532, "lat": 26.3868, "count": 12, "density": 0.000048, "main_class": "foam" }
]
```

> **两个必读注意点**
>
> 1. `density` 是**单位面积密度**（个/m²），不是总数。返回总数会让大网格天然更热，热力图失真。
> 2. `grid_size` 单位是**米**。服务端内部会把坐标投影到 EPSG:3857 再聚合，若直接在 4326 上做，1 度 ≈ 100km，网格毫无意义。

### GET `/events/{event_id}` — 事件详情

不存在返回 `code=3001`。

---

## 四、任务 `/tasks`

### POST `/tasks` — 人工创建任务

自动派单走事件流程；本接口用于人工干预（平台判读后手动派单）。

**请求体**
```json
{
  "event_id": "evt_demo_0001",
  "robot_id": "RBT-001",
  "target": { "lng": 119.653, "lat": 26.387 },
  "priority": 3
}
```

`robot_id` 为空时任务停在 `pending` 等派单；指定时直接置为 `assigned`。

### GET `/tasks` — 任务列表

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `status` | — | 状态筛选 |
| `robot_id` | — | 机器人筛选 |
| `page` / `page_size` | 1 / 50 | 分页 |

**响应项**（含完整生命周期时间戳链）
```json
{
  "task_id": "tsk_demo_0001",
  "event_id": "evt_demo_0005",
  "robot_id": "RBT-001",
  "lng": 119.6518,
  "lat": 26.3858,
  "status": "done",
  "status_label": "已完成",
  "priority": 1,
  "created_at": "2026-09-17T13:23:45+08:00",
  "assigned_at": "2026-09-17T13:28:45+08:00",
  "ack_at": "2026-09-17T13:29:45+08:00",
  "started_at": "2026-09-17T13:33:45+08:00",
  "finished_at": "2026-09-17T13:53:45+08:00",
  "collected_weight": 12.5,
  "review_result": "confirmed",
  "remark": null
}
```

### PATCH `/tasks/{task_id}` — 更新任务状态

**请求体**
```json
{
  "status": "collecting",
  "robot_id": "RBT-001",
  "collected_weight": 0,
  "review_result": "pending",
  "remark": "现场有风浪，作业延缓"
}
```

**★ 状态机约束**——非法跳转返回 `code=4002`：

```
pending ──► assigned ──► navigating ──► collecting ──► done
   │            │             │              │
   │            └──► pending  │              │
   │            （ACK 超时回退）              │
   └────────────┴─────────────┴──────────────┴──► cancelled
```

合法迁移表：

| 当前状态 | 允许迁移到 |
| --- | --- |
| `pending` | `assigned`、`cancelled` |
| `assigned` | `navigating`、`pending`（ACK 超时）、`cancelled` |
| `navigating` | `collecting`、`cancelled` |
| `collecting` | `done`、`cancelled` |
| `done` | 终态 |
| `cancelled` | 终态 |

成功更新后，服务端会通过 WebSocket 广播 `task_update`。

### GET `/tasks/{task_id}` — 任务详情

不存在返回 `code=4001`。

### POST `/tasks/dispatch/pending` — 补派待处理事件

**场景**：机器人离线期间产生的事件积压；机器人重新上线后调用本接口补派。

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `limit` | 10 | 单次最多补派数（1~100） |

**响应**
```json
{ "dispatched": 3, "task_ids": ["tsk_...", "tsk_...", "tsk_..."] }
```

---

## 五、设备 `/devices`

### GET `/devices` — 设备列表

| 参数 | 说明 |
| --- | --- |
| `device_type` | `shore_camera` / `drone` / `robot` |
| `status` | `online` / `offline` / `fault` |

**响应项**
```json
{
  "device_id": "CAM-MABI-01",
  "device_type": "shore_camera",
  "name": "马鼻码头摄像头",
  "lng": 119.6521,
  "lat": 26.3864,
  "status": "online",
  "last_heartbeat": "2026-09-18T00:05:00+08:00",
  "stream_url": "http://localhost:1984/api/stream.mp4?src=cam01",
  "meta": { "model": "HK-DS2CD", "resolution": "1920x1080" }
}
```

### GET `/devices/{device_id}` — 设备详情

### GET `/devices/{device_id}/stream` — 获取视频流地址

**响应**
```json
{
  "device_id": "CAM-MABI-01",
  "flv_url": "http://localhost:1984/api/stream.flv?src=cammabi01",
  "webrtc_url": "http://localhost:1984/api/webrtc?src=cammabi01",
  "hls_url": "http://localhost:1984/api/stream.m3u8?src=cammabi01"
}
```

| 协议 | 延迟 | 适用 |
| --- | --- | --- |
| WebRTC | <500ms | 需要实时操控时 |
| HTTP-FLV | 1~3s | **大屏默认**（前端用 mpegts.js 播放） |
| HLS | 5~15s | 兼容性兜底（iOS Safari） |

---

## 六、机器人 `/robots`

### GET `/robots` — 机器人列表与实时状态

**响应项**
```json
{
  "robot_id": "RBT-001",
  "name": "打捞机器人 01 号",
  "lng": 119.654,
  "lat": 26.387,
  "status": "online",
  "battery": 92,
  "bins": { "foam": 0.05, "plastic": 0.02, "mixed": 0.01 },
  "current_task_id": "tsk_20260918_a3f2c9",
  "last_heartbeat": "2026-09-18T00:05:00+08:00"
}
```

> `bins` 是「打捞即粗分三仓」设计的软件侧落点。没有仓容数据，三仓在平台上就是空的——所以遥测链路必须把三仓占用带上（见 `mqtt-topics.md`）。

### GET `/robots/{robot_id}` — 机器人详情

---

## 七、统计 `/stats`（大屏实时）

> 与 `/reports` 分开的原因：stats 服务「大屏实时」，查明细、刷新快；reports 服务「治理报表」，读预聚合宽表、刷新慢。数据源与访问频率完全不同。

### GET `/stats/dashboard` — 大屏顶部指标卡

```json
{
  "event_count_24h": 47,
  "pending_tasks": 2,
  "collecting_tasks": 3,
  "done_tasks_24h": 8,
  "robots_online": 2,
  "robots_total": 3,
  "collected_kg_total": 12.5,
  "devices_online": 7,
  "devices_total": 10
}
```

### GET `/stats/classes` — 类别分布

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `hours` | 24 | 时间窗口 |

```json
[
  { "main_class": "foam", "label": "泡沫类", "count": 28 },
  { "main_class": "fishing_gear", "label": "渔具类", "count": 11 }
]
```

饼图数据源。

### GET `/stats/trend` — 事件趋势（按小时）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `hours` | 24 | 时间窗口（1~168） |

```json
[ { "time": "2026-09-17T20:00:00+08:00", "count": 5 } ]
```

折线图数据源。

---

## 八、报表 `/reports`

> 数据源为预聚合宽表 `t_report_daily`——由定时任务每日凌晨生成。报表页只读宽表，即使事件量到百万级仍毫秒响应。

### GET `/reports/daily` — 日报表查询

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `days` | 7 | 回溯天数（1~90） |
| `township` | — | 乡镇筛选 |

```json
[
  {
    "stat_date": "2026-09-17",
    "township": "马鼻镇",
    "main_class": "foam",
    "main_class_label": "泡沫类",
    "event_count": 12,
    "task_count": 3,
    "done_count": 3,
    "collected_kg": 28.5,
    "coverage_area": 15000.0
  }
]
```

### GET `/reports/summary` — 报表汇总（按乡镇聚合）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `days` | 7 | 回溯天数 |

```json
[
  { "township": "马鼻镇", "event_count": 26, "done_count": 6, "collected_kg": 62.0, "coverage_area": 35000.0 }
]
```

---

## 九、WebSocket `/ws/alerts`

> 注意：WebSocket 路由**不带 `/api/v1` 前缀**，直连 `ws://localhost:8000/ws/alerts`。

### 服务端推送消息

统一结构：
```json
{ "type": "new_event", "data": { }, "ts": "2026-09-18T00:05:00.123456" }
```

| `type` | 触发时机 | `data` 主要字段 |
| --- | --- | --- |
| `connected` | 连接建立后立即发送 | `{ message }` |
| `new_event` | 新事件入库 | `event_id`、`device_id`、`main_class`、`lng`、`lat`、`det_count`、`confidence`、`event_time` |
| `task_update` | 任务状态变更 | `task_id`、`event_id`、`robot_id`、`status` |
| `robot_status` | 机器人遥测上报 | `robot_id`、`battery`、`status`、`lng`、`lat` |
| `pong` | 收到客户端 ping | — |
| `heartbeat` | 服务端 60 秒无消息时主动探测 | — |

### 客户端消息

```json
{ "type": "ping" }
```

前端 `src/utils/realtime.js` 每 25 秒发一次心跳，采用指数退避重连（1s → 30s 封顶）。

### 兜底策略

WebSocket 只推**增量**。若前端丢消息，数据会永久缺失且不自愈。因此 `App.vue` 保留了 30 秒的全量轮询对账——**WebSocket 负责快，轮询负责对**。

---

## 十、系统接口

| 接口 | 说明 |
| --- | --- |
| `GET /health` | 健康检查，返回 `{ status, app, env, ws_connections, dependencies }` |
| `GET /` | 服务信息与接口文档地址 |
| `GET /docs` | Swagger UI |
| `GET /openapi.json` | OpenAPI 规范 |

### 10.1 `/health` 必须反映真实降级

`status` 是三档枚举，**不是**永远返回 `ok`：

| status | 触发条件 |
| --- | --- |
| `ok` | `dependencies` 里三项全为 `ok` |
| `degraded` | 部分依赖不可用 |
| `down` | 所有依赖都不可用 |

```json
{
  "status": "degraded",
  "app": "SeaSight",
  "env": "production",
  "ws_connections": 3,
  "dependencies": {
    "redis": "ok",
    "mqtt": "down: MqttError",
    "database": "ok"
  }
}
```

`dependencies` 的值只有两种形态：成功为 `"ok"`，失败为 `"down: <异常类名>"`。
刻意不把原始异常消息塞进去 —— 异常文本可能带连接串、主机名、账号，
而 `/health` 通常是**免认证**暴露给编排系统的。

> 每个依赖的探测都有 2 秒超时，所以即使数据库在黑洞路由上，
> `/health` 也能在 6 秒内返回，不会把探针挂死。

---

## 十一、AI 推理服务（独立端口 8081）

| 接口 | 说明 |
| --- | --- |
| `GET /infer/health` | 返回 `{ status, backend, model_version, classes }` |
| `POST /infer/detect` | 上传图片（multipart），返回 `detections` + `aggregate` |
| `POST /infer/reload` | 热加载模型，不重启服务 |

`POST /infer/detect` 响应：
```json
{
  "code": 0,
  "data": {
    "detections": [ { "class": "foam", "confidence": 0.91, "bbox": [412, 288, 468, 331] } ],
    "aggregate": { "main_class": "foam", "count": 1, "max_confidence": 0.91 },
    "model_version": "det_v0.1.0",
    "backend": "onnxruntime:CPUExecutionProvider",
    "elapsed_ms": 42.7
  }
}
```

返回的 `detections` 结构**与边缘端事件报文中的同名字段一致**，边缘盒可以直接组装上报，不需要转换。

---

## 十二、调试速查

```bash
# 健康检查
curl http://localhost:8000/health

# 事件列表
curl "http://localhost:8000/api/v1/events?hours=24&page_size=5"

# 热力图
curl "http://localhost:8000/api/v1/events/heatmap?hours=24&grid_size=500"

# 大屏指标卡
curl http://localhost:8000/api/v1/stats/dashboard

# 上报一个事件（触发自动派单）
curl -X POST http://localhost:8000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt_test_001",
    "device_id": "CAM-MABI-01",
    "device_type": "shore_camera",
    "timestamp": "2026-09-18T00:10:00+08:00",
    "location": {"lng": 119.6531, "lat": 26.3867},
    "detections": [{"class": "foam", "confidence": 0.91, "bbox": [412,288,468,331]}],
    "aggregate": {"main_class": "foam", "count": 3, "max_confidence": 0.91},
    "seq": 999001
  }'

# 手动推进任务状态
curl -X PATCH http://localhost:8000/api/v1/tasks/tsk_xxx \
  -H "Content-Type: application/json" \
  -d '{"status": "collecting"}'

# 端到端冒烟测试（一条命令跑完整个闭环）
python scripts/smoke_test.py
```

---

相关文档：`architecture.md`（架构与数据流）· `mqtt-topics.md`（MQTT 主题树）· `deployment.md`（部署）· `development.md`（协作）
