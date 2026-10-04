# 华为 ModelEngine Nexent 赛题适配说明

> 赛题：基于华为 ModelEngine Nexent 打造可进化决策智能体
>
> 本文说明 Oceanus 代码基线与赛题要求的对应关系、可验收入口和复用边界。
> 机器人是可选执行端；不接机器人时，领域资产认知、动态本体、多跳检索和
> 决策溯源仍可独立运行。

## 一、项目定位

Oceanus 原有主线是“事件理解 → 派单决策 → 工具调用 → 审批守卫 → MQTT
执行 → 回执审计”。Nexent 适配层在这个主线上追加领域资产认知能力：

```text
多模态资产
  → 不可变版本
  → 本体候选半自动抽取
  → 人工审核与发布
  → 跨文档多跳检索
  → 决策证据固化
  → Nexent Skills / MCP 编排
```

这条链路不导入后端 ORM，不直接连接数据库。Nexent 只能通过公开 `/api/v1`
接口访问系统，因此后端继续负责认证、角色、辖区权限、审批、幂等和审计。

## 二、赛题要求映射

| 赛题要求 | 当前实现 | 主要代码位置 | 验收方式 |
| --- | --- | --- | --- |
| 多模态异构数据统一识别、理解与资产标识 | 支持 document、table、image、event、telemetry、dataset 六类资产；资产身份稳定，内容按版本追加并记录哈希 | `backend/app/models/knowledge.py`、`backend/app/services/knowledge.py` | 调用 `/knowledge/assets` 登记资产并读取版本历史 |
| 低资源知识图谱本体半自动构建 | 从指定资产版本抽取候选节点/关系；候选默认未审核，不冒充模型准确率 | `KnowledgeService.extract_ontology` | 调用 `/knowledge/ontology/extract`，检查候选及来源版本 |
| 本体持续动态更新与标准对齐 | 本体版本可继承父版本，保留 `standard_codes`；节点/关系经过人工审核后才能发布 | `backend/app/api/v1/knowledge.py`、`backend/app/models/knowledge.py` | 创建新版本、审核、发布并查询发布版本 |
| 检索-推理双驱动执行流 | 已发布本体存在时执行带路径的多跳检索；无可用本体时明确回退普通资产检索 | `KnowledgeService.search` | 调用 `/knowledge/search`，检查 `mode`、`path`、`citations` |
| 跨文档多跳及决策链路可追溯 | 检索结果携带资产版本、节点、关系、跳数、片段和引用；决策轨迹按顺序固化证据 | `KnowledgeService.create_decision` | 创建决策后读取 `/knowledge/decisions/{id}/evidence` |
| 集成 Nexent MCP 与 Skills | 提供 stdio + Streamable HTTP/SSE MCP Server；支持出站令牌自动刷新；默认只注册只读工具；提供 5 个可复用 Skills | `integrations/nexent/mcp_server/`、`integrations/nexent/skills/` | `make nexent-acceptance`，再在 Nexent 中注册并导入 Skills |
| 沉淀可快速部署的 Skill 工作流 | 政策证据问答、事件研判、跨文档决策、工单编排、决策轨迹审计 | `integrations/nexent/README.md` | 替换本体和资产源后可复用于其他行业 |
| 智能体基于 Nexent 可运行 | 标准 MCP 工具面 + Skills 模板 + 后端公开接口 | `integrations/nexent/` | 已完成（2026-09-28，本地 Nexent v2.6.1） |

## 三、代码结构

| 模块 | 作用 |
| --- | --- |
| `backend/app/models/knowledge.py` | 资产、资产版本、本体版本、节点、关系、决策、证据的数据模型 |
| `backend/app/schemas/knowledge.py` | 对外 HTTP 契约 |
| `backend/app/services/knowledge.py` | 资产版本、候选抽取、审核发布、多跳检索和决策证据逻辑 |
| `backend/app/api/v1/knowledge.py` | `/api/v1/knowledge/*` 接口与权限控制 |
| `backend/alembic/versions/20260919_1900_knowledge_assets.py` | 追加式数据库迁移，当前 Alembic head |
| `frontend/src/views/KnowledgeView.vue` | 资产、本体、检索、决策四个工作台页签 |
| `integrations/nexent/mcp_server/server.py` | Oceanus Domain Cognition MCP |
| `integrations/nexent/skills/` | 5 个领域工作流模板 |

## 四、Nexent 接入

### 4.1 启动后端并取得令牌

先按 `docs/deployment.md` 启动 PostgreSQL、Redis、后端和前端。开发环境可使用
种子账号；生产环境必须通过 `make prod-create-admin` 创建正式管理员。

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<password>"}'
```

生产环境不要把管理员令牌交给只读智能体。按工作流创建最小权限账号：

| 工作流 | 建议角色 |
| --- | --- |
| 政策检索、资产浏览、决策查看 | `viewer` |
| 资产登记、本体候选抽取、决策创建 | `operator` |
| 本体审核发布、Agent 审批 | `approver` 或 `admin` |

### 4.2 安装并自检 MCP

```bash
make nexent-install
cp integrations/nexent/.env.example integrations/nexent/.env
# 编辑 SEASIGHT_API_BASE_URL 与专用最小权限账号
make nexent-check
```

长期运行优先使用 `SEASIGHT_API_USERNAME` 与 `SEASIGHT_API_PASSWORD`。
MCP 会调用 `/api/v1/auth/login` 获取短期令牌，在到期前自动刷新，并在
一个请求收到 401 时重新登录后只重试一次。`SEASIGHT_API_TOKEN` 仍是可选的
静态覆盖方式，但不会自动刷新。

`--check` 不会访问业务数据库，只输出服务名、API 地址、出站认证模式、
是否启用自动刷新、写入工具是否开启和传输方式。默认
`SEASIGHT_MCP_ALLOW_WRITES=false`；只读场景不应开启写入。

协议级端到端验收：

```bash
make nexent-acceptance
```

该命令会验证 HTTP 未认证拒绝、MCP 初始化、工具面、5 个 Skills 的结构，
并用模拟 Oceanus API 验证登录与过期令牌刷新。它不能替代真实 Nexent 平台
注册和调用验收（本地平台侧验收见 §4.4）。验收产物写入
`artifacts/nexent-acceptance/latest.json`。

### 4.3 在 Nexent 中注册

本地 Nexent 可在 MCP 配置中使用 stdio 命令：

```text
python integrations/nexent/mcp_server/server.py
```

工作目录应为仓库根目录。

若 Nexent 运行在容器或另一台服务器，使用生产 Compose 提供的
`nexent-mcp` 服务，并将传输设置为 `streamable-http`：

```dotenv
SEASIGHT_MCP_TRANSPORT=streamable-http
SEASIGHT_MCP_HOST=0.0.0.0
SEASIGHT_MCP_PORT=8100
SEASIGHT_MCP_SERVER_TOKEN=<至少 32 个随机字符>
SEASIGHT_MCP_PUBLIC_URL=https://<mcp-domain>/mcp
```

在 Nexent 中注册：

```text
URL: http://host.docker.internal:8100/mcp
Header: Authorization: Bearer <SEASIGHT_MCP_SERVER_TOKEN>
```

`host.docker.internal` 适用于 Nexent 容器访问同一宿主机上的 MCP 服务。
若两者不在同一宿主机，应通过受 VPN/防火墙保护的地址访问；公网部署必须
使用 HTTPS，并让 `SEASIGHT_MCP_PUBLIC_URL` 与实际域名一致。SSE 传输的
路径是 `/sse`，Streamable HTTP 使用 `/mcp`。

随后分别导入 `integrations/nexent/skills/` 下的 5 个 `SKILL.md`。每个 Skill
定义触发条件、工具顺序、停止条件和输出要求，不替代 MCP 的权限判断。

### 4.4 平台侧验收证据（已完成 2026-09-28）

已于 2026-09-28 在本地 Nexent v2.6.1 完成注册、工具面加载与工具调用。证据存放于 `artifacts/nexent-platform-acceptance/`：

2026-09-29 以官方内置 `suadmin@nexent.com` 复验同一入口；知识域演示数据灌入后，
`knowledge_list_assets` 返回非空资产列表（total=4），轨迹见
`artifacts/nexent-platform-acceptance/evidence/recheck-2026-09-29-with-data.json`。
复验仍为本地官方源码部署，不是华为托管平台复验。

2026-09-29 同日登记 R-NX-04：在本地官方源码部署中创建并发布
`seasight-governance-decision-agent`，绑定 5 个 Skill 与 21 个 MCP 工具，
发布版本 v2，调用关系 API 返回 21 个 MCP 工具并导出 Agent 配置 ZIP；
未配置 LLM，未跑通完整问答，非华为托管平台验收。登记见
`artifacts/nexent-platform-acceptance/agent-create-2026-09-29.yaml`，
接口返回与截图见 `artifacts/nexent-platform-acceptance/evidence/agent-run-*`。

2026-09-29 完成华为托管平台（AgentArts）MCP 注册与公网端点真实调用，登记为
R-NX-05：`Oceanus Domain Cognition MCP` 在托管平台状态“部署成功”，工具列表
加载 21 个只读工具；对同一公网端点执行 initialize → tools/list →
`knowledge_list_assets`，返回 total=4。证据见
`artifacts/nexent-platform-acceptance/hosted-2026-09-29.yaml` 与
`artifacts/nexent-platform-acceptance/evidence/hosted-2026-09-29-*.png/json`。
托管平台（AgentArts）Skill 页面暂无数据，导入需用户在控制台手动完成（AgentArts 不支持程序化批量导入）。5 个 Skill 已在本地 Nexent 官方源码部署完成导入与 Agent 绑定（R-NX-04）。控制台调试按钮未观察到调用输出。

同日登记 R-NX-06：AgentArts 已创建 Agent
`seasight-governance-decision-agent`（ID
`fdeccb8f-c35e-459b-8413-26f72a37edf3`），配置
`deepseek-provider/deepseek-chat` 模型，写入诚实系统提示词；编辑页明确
提示公网环境不支持 Skill（Skill 绑定按钮 disabled），完整 Skill 问答需
私网环境 + 私网可访问 MCP endpoint 后验收。结构化记录见
`artifacts/nexent-platform-acceptance/hosted-agent-2026-09-29.yaml`。

```text
artifacts/nexent-platform-acceptance/
  latest.yaml                 # 本次验收的结构化记录
  evidence/
    mcp-registered.png        # 租户侧 MCP 注册完成界面
    mcp-registered.json       # MCP 注册记录（已去除令牌字段）
    mcp-tools-21.png          # 编辑弹窗中加载出的 21 个工具
    mcp-tools-21.json         # 工具列表响应
    skills-imported.png       # Skills 导入完成界面
    skills-list-5.json        # 5 个已导入 Skills 清单
    skills-policy-evidence-qa.json
    tool-call-trace.json      # knowledge_list_assets 调用返回 200
```

`latest.yaml` 建议结构：

```yaml
acceptance:
  date: "2026-09-28"
  platform_version: "Nexent v2.6.1"
  operator_account: "suadmin@nexent.com / seasight.acceptance@nexent.com"
  mcp_transport: "streamable-http"
  endpoint: "http://host.docker.internal:8100/mcp"
  invoked_tools:
    - "knowledge_list_assets"
  skills_imported:
    - "policy-evidence-qa"
    - "marine-event-assessment"
    - "cross-document-decision"
    - "dispatch-work-order-orchestration"
    - "decision-trace-audit"
  result: "success"
  evidence_files:
    - "mcp-registered.png"
    - "mcp-registered.json"
    - "mcp-tools-21.png"
    - "mcp-tools-21.json"
    - "skills-imported.png"
    - "skills-list-5.json"
    - "skills-policy-evidence-qa.json"
    - "tool-call-trace.json"
  reviewed_by: "liyongxiang"
  review_note: "平台侧验收；不是海域验证，不代表检测精度"
```

创建最小权限只读账号（在 backend 容器内执行）：

```bash
SEASIGHT_API_PASSWORD=<随机密码> python scripts/create_nexent_service_account.py \
  --username nexent_viewer --role viewer
```

口径：Nexent 平台侧验收记录只证明「Oceanus MCP 能在该平台版本上完成注册、
Skills 导入和被调用」。它不等于海域部署验证，也不等于任何感知精度或
现场治理效果证据。

## 五、最少验收路径

以下步骤不需要机器人，也不需要 MQTT：

1. 使用 `operator` 登记一份治理文档和一个表格资产。
2. 对两份资产追加版本，确认历史版本仍可读取。
3. 创建本体版本，调用候选抽取，再以 `approver` 审核并发布。
4. 调用 `/knowledge/search`，确认结果包含资产版本、路径和引用。
5. 调用 `/knowledge/decisions`，随后读取 evidence，核对证据顺序和版本 ID。
6. 在 Nexent 注册 `/mcp` 并导入 Skills，通过 Nexent 调用 MCP 只读工具，
   执行“政策证据问答”或“跨文档决策”Skill。
7. 可选：登记一个事件、运行 Agent 工作流并检查审批与执行审计；机器人是否在线不影响前六步。

真实后端上可复现第 1–5 步的自动化脚本：

```bash
make knowledge-evolution-demo
```

该脚本会写入 `artifacts/evolution-demo/latest.json`，包含每一步请求时间、
状态、ID 和数量；后端或账号不可用时输出 `not_configured` /
`backend_unavailable` 并给出非零退出码，不会伪造成功结果。

2026-09-29 已在真实后端跑通并登记为 `R-KN-01`：2 个资产、4 个资产版本、
60 个本体候选（20 节点 + 40 关系）、图谱多跳检索 4 命中、决策证据 4 条。
该记录为 E1/E2 软件内部闭环证据，不代表海域部署验证或感知精度。

## 六、与连江比赛成果的复用

这组改造是追加式扩展，不替换原有事件、任务、机器人、MQTT 和前端大屏：

- 新增知识域表，不改 `t_event` / `t_task` 的业务含义。
- 新增 Alembic migration，旧库按 `upgrade head` 顺序升级。
- 机器人继续作为可替换执行端；Nexent 适配层不依赖机器人 SDK。
- 连江比赛使用的感知、派单、回执和报表链路仍可单独运行。

正式复用同一代码仓库参加两个赛事前，建议：

1. 为连江提交版本创建只读 tag 或冻结分支，保留当时的材料与可复现记录。
2. 在独立分支完成 Nexent 赛题部署、演示数据和提交材料。
3. 对外分别说明两个项目的增量工作和复用关系，不把同一份成果宣称为两份完全独立研发。
4. 向两个赛事主办方确认重复参赛、开源和知识产权规则。

代码复用与功能独立是工程事实；是否允许同时报名、是否构成同一作品重复参赛，
属于赛事规则解释，不能在代码层替主办方作出承诺。

## 七、如实边界

- 当前本体抽取是确定性候选算法，不是训练完成的领域大模型。
- 当前多跳检索基于已发布的显式本体关系，不应宣称为通用图谱推理引擎。
- 仓库没有真实海域部署、医疗/金融生产客户或检测精度结论时，不应在答辩中虚构。
- MCP 已通过独立 MCP SDK 的 HTTP 鉴权、初始化、工具列表和模拟令牌刷新
  验收；本地 Nexent v2.6.1 平台侧注册、Skills 导入和真实调用已于
  2026-09-28 完成（见 §4.4）。2026-09-29 以本地官方源码部署内置 suadmin 复验完成（R-NX-03），见 `artifacts/nexent-platform-acceptance/recheck-2026-09-29.yaml`。华为托管平台（AgentArts）MCP 注册与公网端点真实只读调用已于 2026-09-29 完成并登记 R-NX-05。
- 华为托管平台（AgentArts）MCP 注册与公网端点真实只读调用已于 2026-09-29
  完成并登记 R-NX-05；托管平台（AgentArts）Skill 页面暂无数据，导入需用户在控制台手动完成。5 个 Skill 已在本地 Nexent 官方源码部署完成导入与 Agent 绑定（R-NX-04）。控制台调试按钮未观察到调用输出。
  同日创建 Agent 并配置 DeepSeek 模型（R-NX-06），公网环境不支持 Skill
  （平台 UI 明确提示），完整 Skill 问答需私网环境 + 私网可访问 MCP
  endpoint 后验收。
- Agent 配置/发布/调用关系/导出证据登记为 R-NX-04（2026-09-29，本地官方
  源码部署），见 `artifacts/nexent-platform-acceptance/agent-create-2026-09-29.yaml`；
  未配置 LLM，未跑通完整问答，非华为托管平台验收。
- “可接入 Nexent”不等于 Nexent 官方认证或生产 SLA。

