# 部署指南

> 两种模式：**Docker Compose（推荐）** 与 **本地裸机（无 Docker 时）**。

---

## 一、环境要求

### 1.1 Docker 模式

| 组件 | 最低 | 推荐 |
| --- | --- | --- |
| Docker | 20.10 | 最新稳定版 |
| Docker Compose | v2（`docker compose` 子命令） | v2.20+ |
| 内存 | 6 GB | 8 GB |
| 磁盘 | 20 GB | 40 GB |
| CPU | 2 核 | 4 核 |

### 1.2 裸机模式

| 组件 | 版本 | 备注 |
| --- | --- | --- |
| Python | 3.11 ~ 3.13 | 3.11 最稳（依赖轮子齐全） |
| Node.js | 20 LTS / 22 | 前端构建 |
| PostgreSQL | 14+ | **必须带 PostGIS 扩展** |
| Redis | 7+ | 需要 Streams 支持（5.0+ 即可，7 更好） |
| EMQX | 5.x | 或任意 MQTT 3.1.1+ broker（Mosquitto 也行） |
| MinIO | 任意 | 可选，不上传证据帧时不需要 |
| go2rtc | 最新 | 可选，没有真实摄像头时不需要 |

**Windows 裸机注意**：PostGIS 官方不提供 Windows 安装包，最省事的做法是只把 PostgreSQL 跑在 Docker 里，其余跑裸机。

---

## 二、Docker Compose 部署（推荐）

### 2.1 准备环境变量

```bash
cp .env.example .env
```

编辑 `.env`，**以下几项必须修改**：

```bash
# 生成一个随机密钥（不要用示例值）
SECRET_KEY=<openssl rand -hex 32 的输出>

# 数据库密码
POSTGRES_PASSWORD=<强密码>

# MQTT 密码（EMQX 启动时会用这个建账号）
MQTT_PASSWORD=<强密码>

# MinIO 密码
MINIO_SECRET_KEY=<强密码>

# EMQX Dashboard 密码
MQTT_DASHBOARD_PASSWORD=<强密码>
```

> **安全红线**：`.env` 已在 `.gitignore` 中排除，**永远不要提交**。若已在本地存有敏感凭据文件，放到仓库之外的固定目录（如 `D:\VeriCall_data\secrets\`），用 `set -a; source <文件>; set +a` 注入环境。

### 2.2 启动

```bash
# 启动全部依赖服务（postgres / redis / emqx / minio / go2rtc）
docker compose up -d

# 查看状态，等 healthcheck 全部变 healthy
docker compose ps
```

首次启动 `postgres` 会自动执行 `backend/db/init/` 下的 SQL（按文件名顺序）：

1. `01_schema.sql` —— 建表、枚举、索引、触发器、分区
2. `02_seed.sql` —— 种子数据（6 摄像头 + 1 无人机 + 3 机器人 + 14 条事件）

> **注意**：`docker-entrypoint-initdb.d` 只在数据卷**为空**时执行。若已启动过一次再改 SQL，需要 `make db-reset`（会丢数据）或手动执行。

### 2.3 初始化数据库（数据卷已存在时）

```bash
make db-init
```

### 2.3.1 数据库迁移（Alembic）—— schema 是「双轨制」

先说清架构，否则下面每条命令都会用错：

| 轨道 | 负责什么 | 工具 | 何时执行 |
| --- | --- | --- | --- |
| **A** | 初始建表、PostGIS 扩展、`t_event` 按月分区、触发器函数 | `backend/db/init/01_schema.sql` | postgres 容器**首次**启动时由 `docker-entrypoint-initdb.d` 自动执行 |
| **B** | 之后的一切增量变更（加字段、加索引、改约束） | Alembic | 由开发者显式执行 |

**为什么不全用 Alembic？** 因为 `01_schema.sql` 里有三样 Alembic 表达不了或表达起来很别扭的东西：`CREATE EXTENSION postgis`、`PARTITION OF` 分区子句、以及一组触发器函数。硬塞进 Alembic 会变成一大坨 `op.execute(...)` 原生 SQL，既失去 autogenerate 的价值，又多一层间接。

**双轨的对齐点**是那条空迁移 `20260918_1000_baseline`。新环境必须按这个顺序走：

```bash
# 1. 起数据库（自动跑 01_schema.sql + 02_seed.sql）
docker compose up -d postgres

# 2. ★ 把 baseline 标记为「已应用」——不执行任何 SQL，只是写一条版本记录
make migrate-stamp

# 3. 验证：应输出 20260918_1000_baseline (head)
make migrate-current
```

> **跳过第 2 步会怎样？** 第一次 `make migration` 时 autogenerate 会把
> `01_schema.sql` 建好的表当成「模型里有、数据库里没有」，于是生成一整串
> `op.create_table('t_event', ...)`。一执行就报 `relation "t_event" already exists`。
> 这是双轨制唯一容易踩的坑。

**日常变更流程**：

```bash
# 改完 app/models/ 下的模型后，按差异生成迁移
make migration m="给 t_event 加 severity 字段"

# 应用迁移
make migrate

# 查看历史
make migrate-history
```

> ⚠️ **autogenerate 的结果必须人工审一遍**。它对字段类型变更、默认值变更、
> 以及 PostGIS 几何列（`Geometry`/`Geography`）的判断并不总是可靠，
> 涉及分区表时更是完全不认。生成后请打开 `backend/alembic/versions/` 下的
> 新文件逐行确认，尤其是 `op.drop_*` 之类的破坏性语句 —— autogenerate
> 有时会把它当成「清理多余对象」而你没有察觉。

**给 DBA 审核用（离线导出，不连库）**：

```bash
make migrate-sql > migration.sql    # 产出纯 SQL，可交 DBA 审完再执行
```

**回退**：

```bash
cd backend && python -m alembic downgrade -1   # 回退一步
```

注意 baseline 的 `downgrade()` 是**刻意留空**的 —— 回退到建表之前意味着
`DROP` 掉全部业务表，那是灾难性操作，不该出现在随手敲的 `downgrade base` 里。
真要清库请用 `make db-reset`（有二次确认）。

#### ⚠️ 中文 Windows 上的 Alembic 编码坑（已绕过，但务必了解）

Alembic 读 `.ini` 文件时硬编码了 `encoding="locale"`：

```python
# alembic/util/compat.py:130
return file_config.read(file_argument, encoding="locale")
```

而 Python 的 `open(encoding="locale")` 直接取 `locale.getencoding()`，
**绕过 UTF-8 模式**。中文 Windows 上实测：

| 表达式 | 结果 |
| --- | --- |
| `locale.getencoding()` | `cp936`（GBK） |
| `open(encoding="locale").encoding` | `cp936` ← Alembic 走这条 |
| `open(encoding=None).encoding` | `utf-8`（因为设了 `PYTHONUTF8=1`） |

于是 `alembic.ini` 里只要有一个非 ASCII 字节（哪怕只是中文注释），
所有 `alembic` 子命令都会死在：

```
UnicodeDecodeError: 'gbk' codec can't decode byte 0x80 in position 21
```

**因此本项目把 Alembic 主配置放在 `backend/pyproject.toml`** —— Alembic 读 TOML
用的是 `open(path, "rb")` + `tomllib.load()`，二进制模式，编码参数根本不参与，根治。
`alembic.ini` 只保留日志配置段落，且**必须保持纯 ASCII**。

如果哪天需要改这两个文件，请记住两条硬约束：

1. `alembic.ini` 里不要写任何中文（含注释）——想写说明写到 `pyproject.toml`
2. `pyproject.toml` 里的 `file_template` 和 `version_locations` 写法**不能照抄 ini**：
   - `file_template` 要写 `%%(year)d`（双百分号）—— Alembic 对 TOML 的字符串值**也**做 `%` 插值，单写 `%(year)d` 会抛 `KeyError: 'year'`
   - `version_locations` 必须是 **TOML 数组** `["...(here)s/alembic/versions"]`，写成字符串会被**逐字符**遍历，`'C'` 被当包名喂给 `importlib.resources.files()`，报一个极具误导性的 `ValueError: Empty module name`

### 2.4 启动应用

```bash
# 后端（容器内热重载）
docker compose up -d backend

# 前端
docker compose up -d frontend
```

或本地开发模式（改代码即时生效，无需重建镜像）：

```bash
make dev-backend    # uvicorn --reload，端口 8000
make dev-frontend   # vite dev，端口 5173
```

### 2.5 验证

| 服务 | 地址 | 默认凭据 |
| --- | --- | --- |
| 前端大屏 | http://localhost:5173 | admin / admin123456 |
| 后端 API 文档 | http://localhost:8000/docs | — |
| 健康检查 | http://localhost:8000/health | — |
| EMQX Dashboard | http://localhost:18083 | admin / 见 `.env` |
| MinIO 控制台 | http://localhost:9001 | 见 `.env` |
| go2rtc Web UI | http://localhost:1984 | — |

#### 健康检查的语义（编排系统依赖它）

`/health` 不只是"进程还活着"，它会**逐个探测依赖**并给出三档状态：

| status | 含义 | 编排系统应如何处理 |
| --- | --- | --- |
| `ok` | redis / mqtt / database 全部正常 | 无需干预 |
| `degraded` | 部分依赖不可用，服务仍能提供只读接口 | 告警，但**不要**重启 —— 重启解决不了下游故障 |
| `down` | 全部依赖不可用 | 告警并可考虑摘流量 |

```json
{
  "status": "down",
  "app": "SeaSight",
  "env": "production",
  "ws_connections": 0,
  "dependencies": {
    "redis": "down: TimeoutError",
    "mqtt": "down: ModuleNotFoundError",
    "database": "down: TimeoutError"
  }
}
```

> **为什么不用简单的 `{"status":"ok"}`** ——
> 早期实现就是无条件返回 ok。结果是：Redis、PostgreSQL、MQTT 全挂，
> 进程仍报健康，compose healthcheck 与 K8s probe 都不会重启容器，
> 故障被静默吞掉，直到有人打开前端发现一片空白。
> 这个坑由 `backend/tests/test_health_degradation.py` 守住。

**降级启动是设计允许的**：任何一个依赖缺失都不阻断应用启动
（见第 3 节的降级能力表），所以本地没起 Docker 也能 `uvicorn` 起后端调接口。
但此时 `/health` 会如实报 `degraded`/`down`，冒烟测试也会明确提示。

### 2.6 跑通演示

```bash
# 终端 1：模拟边缘盒上报（无真实摄像头时）
make simulate

# 终端 2：观察后端日志，应能看到
#   [事件] 入库 evt_... 类别=泡沫类 设备=CAM-MABI-01 数量=3
#   [派单] 事件 evt_... → 任务 tsk_... → 机器人 RBT-001
make logs
```

打开 http://localhost:5173 应看到：告警流滚动、地图出现标记、工单看板出现新卡片。

### 2.7 服务依赖关系

```
postgres ──┐
redis ─────┼──► backend ──► frontend
emqx ──────┤       ▲
minio ─────┤       │
go2rtc ────┘    ai-service
```

`backend` 在 `postgres`/`redis`/`emqx` 全部 healthy 后才启动。若某项迟迟不 healthy，先单独排查该项。

---

## 三、本地裸机模式（无 Docker）

本机若无 Docker，可在 Windows/macOS/Linux 上分别跑各组件。以下是 Windows + 托管 venv 的完整流程。

### 3.1 前端

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173

# 构建产物
npm run build        # 输出到 frontend/dist/
npm run preview      # 本地预览构建产物
```

### 3.2 后端（托管 venv）

**不要污染全局环境**，用独立 venv：

```bash
# 创建 venv
"C:/Users/<你>/.workbuddy/binaries/python/versions/3.13.12/python.exe" -m venv "C:/Users/<你>/.workbuddy/binaries/python/envs/seasight"

# 激活（Git Bash）
source "C:/Users/<你>/.workbuddy/binaries/python/envs/seasight/Scripts/activate"

# 安装依赖
cd backend
pip install -r requirements.txt
```

**依赖缺失时的降级能力**（本项目有意设计）：

| 缺少的组件 | 后果 | 服务能否启动 |
| --- | --- | --- |
| Redis | 派单队列失效，但 `pending_dispatcher` 定时扫表补派 | ✅ 能 |
| MQTT Broker | 设备上报通道不可用，可用 HTTP `/events` 备用通道 | ✅ 能 |
| MinIO | 证据帧不上传 | ✅ 能 |
| 模型文件 | AI 服务进入 **stub 模式**，返回确定性模拟结果 | ✅ 能 |
| passlib/bcrypt | 登录降级为演示账号比对 | ✅ 能 |

这是刻意的：**任何单一依赖缺失都不应阻断整个系统启动**，否则演示现场一个组件挂掉就全盘皆输。

启动：

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3.3 数据库（裸机）

需要 PostgreSQL 14+ 且安装 PostGIS：

```bash
# 建库建用户
psql -U postgres -c "CREATE USER seasight WITH PASSWORD '你的密码';"
psql -U postgres -c "CREATE DATABASE seasight OWNER seasight;"
psql -U postgres -d seasight -c "CREATE EXTENSION IF NOT EXISTS postgis;"

# 执行初始化脚本
psql -U seasight -d seasight -f backend/db/init/01_schema.sql
psql -U seasight -d seasight -f backend/db/init/02_seed.sql
```

**验证 PostGIS 可用**：

```bash
psql -U seasight -d seasight -c "SELECT PostGIS_Version();"
```

若报 `type "geometry" does not exist`，说明 PostGIS 未装或扩展未创建。

### 3.4 前端生产构建 + Nginx

```bash
cd frontend && npm run build
```

Nginx 配置要点：

```nginx
server {
    listen 80;
    server_name _;

    root /var/www/seasight/dist;
    index index.html;

    # SPA 路由回退（必须！否则刷新子页面 404）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # WebSocket 升级（必需的三行头）
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }

    # 静态资源缓存
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

> **`proxy_read_timeout 3600s` 不能省**。WebSocket 默认 60 秒无数据就被 Nginx 断开，前端会陷入"连上→断开→重连"的死循环。

---

## 四、AI 推理服务

### 4.1 独立部署

```bash
cd backend
pip install -r requirements-ai.txt
AI_MODEL_PATH=/path/to/best.onnx \
AI_MODEL_VERSION=det_v0.2.0 \
uvicorn app.services.ai.server:app --host 0.0.0.0 --port 8081
```

`requirements-ai.txt` 与主 `requirements.txt` 分开的原因：边缘部署时不需要装 FastAPI 全家桶，只需 onnxruntime + opencv + numpy。

### 4.2 模型准备

在仓库根目录（`seahawk/`）下执行：

```bash
python ml/scripts/export_onnx.py \
    --weights ml/runs/detect/train/weights/best.pt \
    --output  ml/models/best.onnx

python ml/scripts/export_onnx.py --verify ml/models/best.onnx    # 校验输出通道数
```

> 说明路径口径：`ml/` 是仓库根目录下的一级目录（与 `backend/`、`frontend/` 同级）。
> 导出脚本内部会把 ONNX 写到 `--output` 指定位置；模型权重不入 git
> （见 `.gitignore` 的 `ml/datasets/**` 与 `*.onnx` 规则），
> 部署时用对象存储或镜像构建阶段灌入。

> **RK3588 部署的坑**：必须使用 `airockchip/ultralytics_yolov8` 分支。官方 ultralytics 导出的 ONNX 在 RKNN 工具链上会因 DFL 层布局报错。`export_onnx.py` 会自动检测当前 ultralytics 是否来自该分支，不是则拒绝导出并打印安装命令。

> **TensorRT engine 不可跨设备复用**。engine 与 GPU 架构、CUDA/TensorRT 版本强绑定，换机器必须重新 `trtexec` 构建。

### 4.3 推理后端优先级

服务自动探测：`TensorrtExecutionProvider` → `CUDAExecutionProvider` → `CPUExecutionProvider`。

模型文件不存在时进入 **stub 模式**，返回基于图片字节哈希的确定性模拟结果（同一张图结果一致，便于写断言）。

---

## 五、边缘盒部署

真实边缘盒上要跑三件事：拉流、推理、MQTT 上报。

### 5.1 配置

复制 `edge/simulator/config.yaml` 作为模板，放到边缘盒 `/opt/seasight/config.yaml`：

```yaml
site_id: "lianjiang"

mqtt:
  host: "<平台 IP>"
  port: 1883
  username: "edge-cam-mabi-01"   # 每台独立凭据，便于单台吊销
  password: "<强密码>"
  keepalive: 60
  use_lwt: true                  # 必须开启

temporal:
  enabled: true
  window_frames: 15
  min_hits: 3
  grid_size: 64
  min_confidence: 0.45

reporting:
  cooldown_seconds: 90

buffer:
  enabled: true
  max_size: 1000
```

> **`device_id` 必须与平台 `t_device` 表一致**，否则平台会因"设备未注册"直接拒收（返回 `code=2001`）。这是最常见的联调失败原因。

### 5.2 抽帧策略

`每 3 帧取 1 帧` —— 25fps 降到 ~8fps。理由：垃圾漂浮速度约 0.1~0.5 m/s，8fps 足以形成连续轨迹。全帧率推理只是徒耗算力，不提升检出率。

### 5.3 系统服务（systemd）

```ini
[Unit]
Description=SeaSight Edge Inference
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=seasight
WorkingDirectory=/opt/seasight
ExecStart=/opt/seasight/venv/bin/python -m edge.main --config /opt/seasight/config.yaml
Restart=always
RestartSec=5
# 崩溃重启后 seq 能续上（状态文件持久化）
Environment=SEASIGHT_STATE_FILE=/var/lib/seasight/state.json

[Install]
WantedBy=multi-user.target
```

**`Restart=always` 是必需的**。边缘盒部署在无人值守的渔港杆子上，崩溃必须自愈。

---

## 六、摄像头流接入

### 6.1 go2rtc 配置

`deploy/go2rtc/go2rtc.yaml`：

```yaml
log:
  level: info

api:
  listen: ":1984"

rtsp:
  listen: ":8554"

webrtc:
  listen: ":8555"

streams:
  cam01: rtsp://admin:<密码>@192.168.1.101:554/Streaming/Channels/101
  cam02: rtsp://admin:<密码>@192.168.1.102:554/Streaming/Channels/101
  cam03: rtsp://admin:<密码>@192.168.1.103:554/Streaming/Channels/101
```

加一路摄像头 = 加一行。改完重启 go2rtc 容器即可，不用动后端。

### 6.2 三条取流链路

| 链路 | 源 | 目标 | 说明 |
| --- | --- | --- | --- |
| ① 转发 | 摄像头 RTSP | go2rtc → 前端 FLV | 给人看 |
| ② 推理 | 摄像头 RTSP | 边缘盒直接拉 | 给模型算 |
| ③ 留证 | 边缘盒抽帧 | MinIO | 证据帧 |

**② 必须独立于 ①**。如果让边缘盒转流给前端，一路 4Mbps 的转发会持续挤占 CPU，推理帧率掉下去——而推理帧率是这套系统唯一的实质产出。

摄像头需要支持多路并发拉流（主流 IP 摄像头支持 4~8 路）。若摄像头只支持单路，就用 go2rtc 的 `exec` 源或加一个便宜的中继。

### 6.3 前端播放

用 **mpegts.js** 播放 HTTP-FLV，关键参数：

```js
mpegts.createPlayer({
  type: 'flv',
  isLive: true,                  // 直播模式，禁用 seek
  url: flvUrl,
}, {
  enableWorker: true,
  liveBufferLatencyChasing: true, // 自动追帧，防止延迟累积
  liveBufferLatencyMaxLatency: 3.0,
  liveBufferLatencyMinRemain: 0.5,
})
```

> **不要用 flv.js**。该项目已停止维护，在长时间直播流上会出现延迟持续累积（跑几小时后延迟到几十秒），且无修复。

---

## 七、数据库运维

### 7.1 分区维护

`t_track` 按日分区，建表脚本创建了「当日 -1 到 +7」共 9 个分区。生产环境需要定期滚动创建：

```sql
-- 手工创建明天的分区
CREATE TABLE IF NOT EXISTS t_track_20260919
  PARTITION OF t_track
  FOR VALUES FROM ('2026-09-19') TO ('2026-09-20');
```

或装 `pg_partman` 自动管理。**没装 pg_partman 又忘了手工建分区，写入会直接报错**——这是必须放进运维 checklist 的一项。

### 7.2 备份

```bash
# 每日全量备份
docker compose exec -T postgres pg_dump -U seasight -d seasight -Fc > backup_$(date +%F).dump

# 恢复
docker compose exec -T postgres pg_restore -U seasight -d seasight --clean < backup_2026-09-18.dump
```

**别只备份主表而漏了分区**。`pg_dump` 会包含分区子表，但若用了 `-t t_track` 只备份父表则数据会丢。

### 7.3 常用运维 SQL

```sql
-- 表大小排名
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;

-- 索引使用率（找出有没有白建/漏建的索引）
SELECT indexrelname, idx_scan, idx_tup_read
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC LIMIT 20;

-- 热力图索引是否真的被用上
EXPLAIN ANALYZE
SELECT COUNT(*) FROM t_event
WHERE event_time > now() - interval '24 hours'
  AND ST_DWithin(location::geography, ST_MakePoint(119.65, 26.39)::geography, 3000);
-- 应出现 "Index Scan using idx_event_location"
```

### 7.4 数据保留策略

| 数据 | 保留期 | 处理 |
| --- | --- | --- |
| `t_event` | 永久 | 每年约 29 万条，可忽略 |
| `t_task` | 永久 | 工单是治理凭证，不可删 |
| `t_track` | 90 天 | 超期降采样为 1 点/分钟，再超期丢弃 |
| 证据帧（MinIO） | 180 天 | 用生命周期规则自动过期 |
| `t_report_daily` | 永久 | 宽表，体积极小 |

---

## 八、故障排查

| 现象 | 排查 | 常见原因 |
| --- | --- | --- |
| 后端启动报连接错误 | `docker compose logs postgres` | `POSTGRES_PASSWORD` 未设 |
| 事件上报返回 `code=2001` | 查 `t_device` | `device_id` 未注册，或与种子数据不一致 |
| 热力图返回空数组 | `SELECT count(*) FROM t_event` | 数据卷已存在但未跑 seed；或时间窗口无数据 |
| 热力图格子大得离谱 | 检查 grid_size 单位 | 误以为单位是"度"；实际是"米" |
| 派单一直不触发 | 查事件 `main_class` | 只有 `foam`/`fishing_gear` 会触发自动派单 |
| 派单报"无可用机器人" | 查 `t_device` 中 robot 的 `status` 与 `meta.battery` | 机器人离线 / 电量 <30% / 三仓总占用 ≥80% |
| 任务卡在 `assigned` | 查机器人是否回 ACK | ACK 超时 15 秒后会自动回退重派 |
| 状态更新报 `code=4002` | 对照状态机迁移表 | 非法跳转，例如 `pending` 直接跳 `done` |
| 前端大屏无数据 | `curl localhost:8000/health` | CORS 未放通；或后端未启动 |
| 前端刷新子页面 404 | 检查 Nginx `try_files` | 缺少 SPA 路由回退 |
| WebSocket 反复重连 | 检查 Nginx `proxy_read_timeout` | 默认 60 秒会掐断空闲连接 |
| 视频一直转圈 | 浏览器 F12 看 FLV 请求 | go2rtc 未启动；或 `src` 参数与 streams key 不匹配 |
| 地图空白 | F12 控制台看 SDK 加载 | 腾讯地图需走 `_TMapSecurityConfig` 代理；SDK URL 不能带 key |
| 模拟器报 seq 冲突 | 删 `edge/simulator/.simulator_state.json` | 状态文件与数据库不同步 |

### 日志查看

```bash
docker compose logs -f backend      # 后端全部日志
docker compose logs -f backend | grep '\[派单\]'    # 只看派单
docker compose logs -f backend | grep '\[状态机\]'  # 只看状态流转

# 死信队列（处理失败的消息）
docker compose exec redis redis-cli XRANGE stream:dead_letter - + COUNT 10
```

---

## 九、上线检查清单

- [ ] `.env` 中所有 `CHANGE_ME` 已替换为强密码
- [ ] `SECRET_KEY` 用 `openssl rand -hex 32` 生成（不是示例值）
- [ ] `.env` 未被提交（`git status` 确认）
- [ ] EMQX Dashboard 默认密码已改，匿名访问已关闭
- [ ] `TMapSecurityConfig` 代理模式生效，前端源码中**搜不到任何地图密钥**
- [ ] 生产环境 `APP_ENV=production`、`DEBUG=false`
- [ ] `CORS_ORIGINS` 只放实际域名，不用 `*`
- [ ] 全站 HTTPS / WSS 已配置
- [ ] Nginx `proxy_read_timeout` 已加到 3600s
- [ ] 数据库备份任务已配置并**实际演练过一次恢复**
- [ ] `t_track` 分区滚动创建任务已配置（或 pg_partman 已装）
- [ ] MinIO 生命周期规则已配置（证据帧 180 天过期）
- [ ] 演示用默认账号密码已修改
- [ ] `python scripts/smoke_test.py` 全绿

---

相关文档：`architecture.md`（架构与数据流）· `api.md`（接口契约）· `mqtt-topics.md`（MQTT 主题树）· `development.md`（协作）
