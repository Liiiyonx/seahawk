# SeaSight × 华为技术纽带矩阵

> 版本：1.0 ｜ 日期：2026-09-27
> 上位口径：`docs/evidence-claim-policy.md`（证据分级与宣称纪律）、
> `docs/competitions/huawei-nexent.md`（Nexent 赛题适配说明）
> 配套门禁：`python scripts/check_claims.py --root .`（必须退出码 0）
>
> 本文用途：在答辩、申报书与现场提问中，**用一份不越级的材料说明本项目和华为技术的关系**。
> 每条"实线"附代码证据；每条"虚线"必须能在字面上看出"尚未在真机验证"。

---

## 一、一句话口径

SeaSight 与华为技术的结合是**一实三虚**：

- **实线一条**：ModelEngine Nexent —— 已集成，已通过协议级验收（E1/E2，见 §四第 1 行）。
- **虚线三条**：昇腾 Atlas + CANN、ModelArts 模型服务、鲲鹏 arm64 / openGauss ——
  **架构与配置层面已就绪，尚未在目标硬件或目标云上实测**。

虚实以**证据等级**划分，不以叙事需要划分。凡本文写"虚线"的，现场被追问时标准答复是
"架构已就绪、验证在下一步计划"，而不是"已经跑过"。

---

## 二、纽带矩阵

| # | 项目侧能力 | 华为产品 | 虚实 | 证据位置 | 现有可验收方式 |
| --- | --- | --- | --- | --- | --- |
| 1 | 领域资产认知、多跳检索、决策证据固化；以 MCP 工具面 + Skills 供外部智能体编排 | ModelEngine Nexent | **实线**：已集成，已通过协议级验收 | `integrations/nexent/mcp_server/server.py`（21 个只读工具常驻 + 11 个写入工具按 `SEASIGHT_MCP_ALLOW_WRITES` 注册，合计 32）；`integrations/nexent/skills/`（5 个 `SKILL.md`）；`integrations/nexent/README.md`；验收产物 `artifacts/nexent-acceptance/latest.json` | `make nexent-check`、`make nexent-acceptance` |
| 2 | 检测模型服务化（HTTP 推理、模型版本追溯、热加载） | 昇腾 Atlas + CANN | 虚线：架构就绪，待验证 | `backend/app/services/ai/server.py`（onnxruntime 多 provider 探测：`TensorrtExecutionProvider` → `CUDAExecutionProvider` → `CPUExecutionProvider`）；`ml/scripts/export_onnx.py`（ONNX 导出） | AI 服务健康检查当前报告的 provider 为 CPU 或 stub；CANN 路径见 `huawei-ascend-modelarts.md` |
| 3 | LLM 规划器（事故研判 / 派单方案生成） | ModelArts 模型服务（OpenAI 兼容协议） | 虚线：配置级兼容 | `backend/app/services/agents/model_adapter.py`（`OpenAICompatibleModelClient`：`base_url` + Bearer `api_key`，超时与错误分类）；`.env.example`（`AGENT_MODEL_ADAPTER_ENABLED` / `AGENT_MODEL_BASE_URL` / `AGENT_MODEL_API_KEY` / `AGENT_MODEL_NAME`） | `backend/tests/test_agent_model_adapter.py`（含模型不可用时的回落行为） |
| 4 | 全栈容器化迁移到 arm64 节点 | 鲲鹏 | 虚线：容器迁移说明 | `backend/Dockerfile`（`FROM python:3.11-slim`，官方多架构基础镜像）；`docker-compose.prod.yml`（postgres / redis / emqx / minio / backend / ai-service / nexent-mcp / frontend） | 现状在 x86 主机上通过 `make prod-up` 编排；**arm64 未实测** |
| 5 | 主库替代（关系型 + 空间数据） | openGauss | 虚线：可行性评估，**存在明确改造点** | `backend/db/init/01_schema.sql`（`CREATE EXTENSION IF NOT EXISTS postgis`；`location geometry(Point, 4326)` 等 4 处空间列）；模型层用 `geoalchemy2.Geometry`；`JSONB` 已用 `.with_variant(JSON, "sqlite")` 做方言回落 | 现状：PostgreSQL 16 + PostGIS。**openGauss 不提供 PostGIS**，迁移前必须替换空间数据层，详见 §四第 5 行 |

---

## 三、架构图

实线 = 已集成并在本仓库可复现；虚线 = 架构与配置已就绪、尚未在目标硬件或目标云实测。

```text
                    ┌────────────────────────────────────────────────────┐
                    │        ModelEngine Nexent          【实线】         │
                    │  MCP 32 工具（21 只读常驻 + 11 写入按开关注册）      │
                    │  5 个 Skills 模板 · 出站令牌自动刷新                │
                    └───────────────────┬────────────────────────────────┘
                                        │  MCP：stdio / streamable-http
                                        ▼
   ┌──────────────────────────── SeaSight 平台（本仓库） ────────────────────────────┐
   │   FastAPI ── PostgreSQL 16 + PostGIS ── Redis ── EMQX ── MinIO ── Vue3 大屏     │
   │   Agent Runtime（Run/Step/Tool/Policy/Approval/Replay/Eval）                    │
   └───┬────────────────────────────┬────────────────────────────┬─────────────────┘
       │ 【虚线】OpenAI 兼容协议     │ 【虚线】ONNX 权重           │ 【虚线】整栈容器
       │  可指向 ModelArts 在线服务  │  可经 ATC 转 om 交 CANN     │  arm64 多架构基础镜像
       ▼                            ▼                            ▼
  ModelArts 在线服务           昇腾 Atlas + CANN              鲲鹏 arm64 节点
  AGENT_MODEL_BASE_URL          ATC: onnx → om                 python:3.11-slim
  AGENT_MODEL_API_KEY           CANNExecutionProvider          PostgreSQL / Redis
  AGENT_MODEL_NAME                                             EMQX / MinIO
       ┊                            ┊                            ┊
       └─ 回落：rule_fallback       └─ 回落：CPUExecutionProvider └─ 回落：x86 现状
          （规则规划器）                  （onnxruntime CPU）           （当前编排主机）
```

---

## 四、逐行证据

### 1. ModelEngine Nexent（实线）

- **工具面**：`integrations/nexent/mcp_server/server.py` 中 21 个 `@mcp.tool()` 常驻注册；
  `WRITE_TOOLS` 元组内 11 个写入工具仅在 `SEASIGHT_MCP_ALLOW_WRITES=true` 时循环注册。
  因此"32 工具"的准确表述是 **"默认注册 21 个只读工具，开启写入开关后为 32 个"**。
- **Skills**：`integrations/nexent/skills/` 下 5 个 `SKILL.md`
  （政策证据问答、事件研判、跨文档决策、工单编排、决策轨迹审计）。
- **出站认证**：MCP 以最小权限账号登录 `/api/v1/auth/login` 取短期令牌，到期前自动刷新，
  收到 401 时重新登录并只重试一次；`SEASIGHT_API_TOKEN` 为不自动刷新的可选静态覆盖。
- **边界**：`/api/v1` 是唯一入口，MCP 不导入后端 ORM、不直连数据库。
- **尚未完成**：在**实际 Nexent 平台**上完成一次注册与调用。协议级验收不能替代平台侧验收
  （原文见 `docs/competitions/huawei-nexent.md` §四）。

### 2. 昇腾 Atlas + CANN（虚线）

- **已就绪的事实**：推理服务不绑定具体加速卡，启动时用
  `onnxruntime.get_available_providers()` 自动探测并按 TensorRT → CUDA → CPU 顺序装配；
  模型文件缺失或加载失败时降级 stub 模式且**不阻断服务启动**。
  这套结构使"换执行后端"是配置与运行时环境问题，而不是改代码问题。
- **未实测**：仓库中没有在昇腾硬件上装载 CANN 版 onnxruntime 并跑通的记录；
  现有运行环境为 x86 主机 CPU。
- 接入方法（ATC 转换、`CANNExecutionProvider`、Atlas 边缘盒拓扑）见
  `docs/competitions/huawei-ascend-modelarts.md`，该文每段均标注为**方案级说明、未实测**。

### 3. ModelArts 模型服务（虚线）

- **已就绪的事实**：规划器通过 `OpenAICompatibleModelClient` 调用，配置项是
  `AGENT_MODEL_BASE_URL` / `AGENT_MODEL_API_KEY` / `AGENT_MODEL_NAME`，
  与部署地址无耦合；协议为 OpenAI Chat Completions 兼容形态。
- **护栏**：模型不可用、超时、输出不合 schema 或越权时，规划器返回
  `source="rule_fallback"` 与结构化 `fallback_reason`，由确定性规则规划器接管。
  该行为有单元测试覆盖，可在现场演示"拔掉模型仍然出方案"。
- **未实测**：没有实际指向 ModelArts 在线服务地址跑过一次的记录。
  配置示例见 `docs/competitions/huawei-ascend-modelarts.md`。

### 4. 鲲鹏 arm64（虚线）

- **已就绪的事实**：基础镜像为 `python:3.11-slim`（官方多架构 manifest，
  arm64 可直接拉取）；依赖链为 FastAPI、SQLAlchemy、psycopg、redis、paho-mqtt 等
  python 包，以及 PostgreSQL / Redis / EMQX / MinIO 四个具备 arm64 官方镜像的组件。
  没有 x86 专有编译产物或私有二进制。
- **未实测**：当前编排在 x86 主机上验证；**没有在鲲鹏服务器上执行过 `make prod-up`**。
  因此本文只写"容器迁移说明"，不写"已在鲲鹏运行"。

### 5. openGauss（虚线，且有明确改造点）

这一行**不能"一句话带过"**，因为存在一个具体的技术阻碍：

- 初始 schema 依赖 PostGIS：`backend/db/init/01_schema.sql` 执行
  `CREATE EXTENSION IF NOT EXISTS postgis`，并定义 `location geometry(Point, 4326)` 等空间列；
  应用层用 `geoalchemy2.Geometry` 映射，查询里出现 `ST_SnapToGrid` / `ST_Transform`
  （热力图网格聚合路径）。
- **openGauss 不提供 PostGIS**。因此"换 openGauss"不等于"改连接串"，
  而是一次空间数据层替换（改为经纬度数值列 + 应用层网格化，或接入 openGauss 自身的空间能力）。
- 结构上利多的一点：模型层已具备方言回落习惯（`JSONB().with_variant(JSON, "sqlite")`），
  说明抽象层是分层设计的；但空间层当前**没有**这样的回落路径。
- 结论表述：**"openGauss 可作为主库替代方向评估；当前空间数据依赖 PostGIS，迁移需先行改造，
  未实测。"**

---

## 五、如实边界（现场被追问时的实话）

1. 只有 Nexent 一条是实线；其余三条是"架构/配置就绪、待验证"，**不是已适配**。
2. 仓库中不存在任何昇腾硬件上的运行记录、鲲鹏服务器上的部署记录或 ModelArts 实际调用记录。
3. "可接入"不等于"华为认证"或"生产 SLA"。
4. 感知侧当前为 OpenCV 传统视觉方案（零数据依赖冷启动），
   开放词汇检测通道为并行评估通道，**不改变主链路**。
5. 本文所有能力陈述均可在仓库中定位到文件；本文不包含任何未经核验的第三方数字。
