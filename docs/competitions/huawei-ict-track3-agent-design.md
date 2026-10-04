# 探海灵眸 Oceanus · Nexent 平台智能体整体设计说明

> 版本：1.0（提交件底稿）
> 编制日期：2026-09-30
> 用途：华为 ICT 大赛 创新赛道三「材料 2」提交件底稿，覆盖智能体整体设计思路、
> Agent 配置完整细节（模型信息 / 工具信息 / 知识库信息 / 调用关系图）、
> Skill 分层编排、调试迭代经验、示例问答截图索引与随附文件说明。
> 上位口径：《docs/competitions/huawei-ict-track3-design-doc.md》、
> 《docs/competitions/huawei-ict-track3-scoring-review.md》、
> 《docs/competitions/huawei-ict-track3-compliance.md》
> 配套手册：《docs/competitions/huawei-agentarts-vpc-target-runbook.md》

## 一、文档定位与诚实边界

本文档是赛道三「材料 2」的正文，回答一个问题：**这个智能体在 Nexent 上是怎么
搭起来的、每一层配置是什么、证据在哪里**。

本文档同时是**证据分级声明**，三种运行位置在全文中严格分开，不得互相替换：

| 运行位置 | 含义 | 当前状态 |
| --- | --- | --- |
| 本地官方源码部署 Nexent | 按官方仓库 `ModelEngine-Group/nexent` 本地部署，v2.6.1 | **完整 LLM Skill 问答已跑通**（R-NX-09） |
| 华为 AgentArts 托管平台 | 华为云控制台内注册 MCP、导入 Skill、创建 Agent | MCP 注册与公网端点只读调用完成（R-NX-05）、Agent 与模型配置完成（R-NX-06）、5 个 Skill 已导入；**平台内完整 Skill 问答未跑通**（R-NX-07 `blocked`） |
| Oceanus 生产后端 | 项目自研 FastAPI + PostgreSQL 业务系统 | 独立运行，内置规则规划器；本地 LLM 规划器尚未真实调用外部模型 |

由此产生四条**不可宣称**：

1. 本地 Nexent 跑通 **不等于** 华为 AgentArts 托管平台验收通过；
2. 平台侧验收 **不等于** 海域现场部署验证，也不代表治理效果；
3. 感知精度一律 `not_evaluated`，`76%` 仅指**时序链路误报抑制率**，不是识别准确率；
4. 当前知识资产为演示数据，**不等于**真实脱敏行业数据集。

## 二、智能体整体设计思路

### 2.1 设计目标与约束

目标不是做一个“问答机器人”，而是把县域海洋环境治理里**沉睡的存量治理资产**
（政策文件、月度台账、事件记录、处置工单、决策痕迹）变成可检索、可推理、
可追溯的决策依据。约束有三条：

- **数据异构**：文档、表格、事件流、工单记录并存，字段与粒度不统一；
- **标注稀缺**：县域治理领域没有现成的标注语料，无法靠监督学习冷启动本体；
- **责任可追**：治理决策必须能回答“依据是哪一条资产、哪一个版本、哪一步执行”，
  不接受黑箱结论。

### 2.2 三层结构

```text
认知层  Oceanus 知识域：资产版本化 → 半自动本体 → 图谱检索 → 决策证据链
              │  以 MCP 工具面暴露为 21 个只读工具
              ▼
编排层  Nexent Agent：模型 + Skill 工作流模板 + MCP 工具调用
              │  Skill 决定“先查什么、再算什么、何时停止”
              ▼
执行层  Oceanus 业务系统：角色 / 辖区 / 审批 / 幂等 / 审计
              │  执行末端可插拔（岸基设备、机器人、机械臂统一走派单链路）
              ▼
        PostgreSQL：资产 / 本体 / 决策 / 事件 / 任务
```

关键分工：**Nexent 负责编排与推理，Oceanus 后端负责权限与事实**。工具返回
的是后端真实数据；后端 `code != 0` 会被 MCP 转成工具错误，业务失败不会伪装成
成功数据返回给模型。

### 2.3 为什么同时用 MCP 和 Skill

两者不是重复，职责不同：

- **MCP 工具面**解决“能做什么”。21 个只读工具是受权限约束的能力边界，工具本身
  不知道业务顺序；
- **Skill**解决“该怎么做”。每个 Skill 用自然语言固化触发条件、工具调用顺序、
  停止条件和输出要求，是可直接复用的**业务逻辑模板**，跨行业时替换本体与
  资产源即可迁移。

把业务顺序写在 Skill 而不是硬编码在 Agent 提示词里，是为了让同一套工具面支撑
多种行业工作流，同时让每一步可在调试轨迹里被单独检查。

## 三、Agent 配置完整细节

### 3.1 Agent 标识与版本

| 项 | 值 |
| --- | --- |
| Agent ID | `1` |
| 平台内 identifier | `seasight_governance_decision_agent` |
| 对外展示名 | Oceanus 治理决策智能体 |
| 当前发布版本 | 版本 4 `v0.2.0-seasight-governance-llm`（`RELEASED`） |
| 版本历史 | v1/v2 `v0.1.0-seasight-governance`（未接模型）；v3/v4 `v0.2.0-seasight-governance-llm`（接入 DeepSeek 后的完整问答版本） |

命名上踩过一次真实约束：Nexent 要求 Agent 的 `name` 是合法 Python 标识符，
含连字符的形式会在运行时被拒绝（`must be a valid Python identifier`），
因此平台内 identifier 使用下划线形式，对外展示名保持不变。这一点属于调试经验，
写在本文 §5。

### 3.2 模型信息

| 项 | 值 |
| --- | --- |
| 模型 ID | `1` |
| 提供方 | DeepSeek |
| 模型名 | `deepseek-v4-pro` |
| Base URL | `https://api.deepseek.com/v1` |
| 凭据位置 | Nexent 平台内模型配置；**密钥不随仓库提交** |

模型可用性是控制台可见性的前置条件：模型状态需为 `available`，经官方
`/api/model/healthcheck` 后 `/api/agent/list` 才返回 `is_available: true`，
控制台才会正常展示该 Agent。

**降级与回退**：Oceanus 后端内置规划器默认走确定性规则；当模型不可用、超时或
输出不符合 schema 时，规划器返回 `source="rule_fallback"` 与结构化
`fallback_reason`，由规则规划器接管，保证链路不中断。这条设计使平台侧模型成为
**增强项而非单点依赖**。

### 3.3 工具信息（MCP 工具面）

MCP 服务：`Oceanus Domain Cognition MCP`。默认注册 **21 个只读工具**；
显式开启 `SEASIGHT_MCP_ALLOW_WRITES=true` 后才注册写入工具，合计 32 个。
写入工具不是“隐藏”，而是**根本不注册**。

| 组 | 只读工具 |
| --- | --- |
| 资产 | `knowledge_list_assets`、`knowledge_asset_detail` |
| 本体 | `knowledge_list_ontology_versions`、`knowledge_ontology_version_detail`、`knowledge_list_ontology_nodes`、`knowledge_list_ontology_relations` |
| 检索 | `knowledge_search` |
| 决策 | `knowledge_list_decisions`、`knowledge_decision_evidence` |
| 业务 | `event_get`、`event_list`、`task_get`、`task_list`、`task_ack_history`、`dashboard_get` |
| Agent 审计 | `agent_runtime_status`、`agent_list_runs`、`agent_run_detail`、`agent_run_steps`、`agent_list_tools`、`agent_list_approvals` |

写入工具（按开关启用，本次验收未启用）：资产登记与版本追加、本体版本创建 /
抽取 / 审核 / 发布、决策创建、Agent 运行控制与审批。

**入站鉴权**：MCP 服务对入站请求做 Bearer 鉴权并 fail-closed，未授权请求不会
落到后端。**出站鉴权**：MCP 到 Oceanus `/api/v1` 使用最小权限只读账号，
支持账号密码模式自动刷新令牌；静态令牌模式过期需人工轮换并重启服务（已文档化）。

### 3.4 知识库信息

知识层不是“向量库 + 文档”这么简单，而是**版本化资产 + 本体图谱**双层结构：

| 层 | 内容 | 检索方式 |
| --- | --- | --- |
| 资产层 | 治理方案 document、月度台账 table，各含版本；共 2 个资产、4 个资产版本（R-KN-01） | `knowledge_search` 确定性打分，返回资产版本、片段、引用 |
| 本体层 | 半自动抽取的节点与关系，按本体版本管理 | 已发布本体存在时走本体引导多跳检索，返回 `mode`、`path`、`citations`；无可用本体时明确回退普通检索 |

当前库内数据为**演示数据**（total=4），用于打通往返链路与截图取证，不表述为
真实脱敏行业数据。真实脱敏数据的评测状态见 §9。

### 3.5 调用关系图

Agent 在平台内的真实调用关系由 `GET /api/agent/call_relationship/1` 返回，
绑定 21 个 MCP 工具（`knowledge_*`、`event_*`、`task_*`、`dashboard_*`、
`agent_*`），登记号 R-NX-04；升级到版本 4 后同一 Agent 叠加模型配置与 5 个
Skill，形成下面的端到端结构：

```text
Nexent Agent: seasight_governance_decision_agent (v0.2.0-seasight-governance-llm)
  ├── 模型：DeepSeek deepseek-v4-pro
  ├── Skill：policy-evidence-qa
  ├── Skill：marine-event-assessment
  ├── Skill：cross-document-decision
  ├── Skill：dispatch-work-order-orchestration
  └── Skill：decision-trace-audit
          │
          ▼
Oceanus Domain Cognition MCP（21 个只读工具 · Bearer 入站鉴权）
          │  出站令牌自动刷新 · 最小权限只读账号
          ▼
Oceanus /api/v1（角色 / 辖区 / 审批 / 幂等 / 审计）
          │
          ▼
PostgreSQL（资产 / 本体 / 决策 / 事件 / 任务）
```

### 3.6 权限与安全边界

- 工具面默认只读，写入能力必须显式开启；
- 后端始终是角色、辖区范围、审批与幂等的唯一权威，MCP 不自行判定权限；
- Agent 仅使用专用最小权限账号，不复用生产管理员账号；
- 决策写入与工单派发在需要审批的场景下必须经过审批墙，Agent 不得绕过；
- 仓库不包含模型密钥、MCP 令牌、后端密码与云账号 AK/SK。

## 四、Skill 分层编排

### 4.1 五个 Skill 的职责

每个 Skill 定义**触发条件、工具顺序、停止条件、输出要求**四要素，刻意保持比
Agent 提示词更小的粒度，以便跨行业替换本体与资产源后复用。

| Skill | 用途 | 典型工具顺序 |
| --- | --- | --- |
| `policy-evidence-qa` | 用可引用资产版本回答政策问题 | 资产/本体定位 → `knowledge_search` → 引用资产版本 |
| `marine-event-assessment` | 评估事件与对应治理依据 | `event_list`/`event_get` → `knowledge_search` → 依据与缺口 |
| `cross-document-decision` | 本体引导的跨文档多跳推理 | 本体版本 → 节点/关系 → 多跳检索 → `path` + `citations` |
| `dispatch-work-order-orchestration` | 协调事件、Agent 运行、审批与工单检查，不绑定机器人厂商 | `task_list` → `agent_list_runs` → 审批状态 |
| `decision-trace-audit` | 核对决策是否可追溯到证据与执行步骤 | `knowledge_list_decisions` → `knowledge_decision_evidence` → `agent_run_steps` |

Skill **不替代 MCP 权限判断**：Skill 只描述业务顺序，能不能做仍由工具面与后端
权限决定。

### 4.2 检索-推理双驱动执行流

```text
用户问题
  → Skill 选择（触发条件匹配，read_skill_md 载入工作流）
  → 检索驱动：knowledge_search / 资产与本体列举（确定性，可引用）
  → 推理驱动：本体多跳检索（mode / path / citations）或明确回退
  → 决策固化：按顺序写入证据（资产版本 + 节点 + 关系 + 跳数 + 引用）
  → 输出：结论 + 引用 + 显式证据缺口
```

设计要点：**推理必须落在可检索到的资产版本上**。模型可以判断“证据不足”，
但不允许在无引用的前提下生成政策依据。

### 4.3 实测一次完整问答的编排轨迹

登记号 R-NX-09（2026-09-30，本地官方源码部署 Nexent v2.6.1）：

| 项 | 实测值 |
| --- | --- |
| 调用方式 | `POST http://127.0.0.1:5014/agent/run`（`text/event-stream`，`is_debug=true`） |
| HTTP 状态 | `200` |
| 事件数 | 13,204 |
| 步骤数 | 8 |
| 工具调用 | 31 次，覆盖 13 个唯一工具 |
| 实际加载 Skill | 4 个（见下） |
| 最终回答 | 2,777 字 |
| run error | `null` |

唯一工具集合：`parallel_executor`、`read_skill_md`、`event_list`、`dashboard_get`、
`agent_runtime_status`、`knowledge_list_assets`、`knowledge_list_ontology_versions`、
`knowledge_list_decisions`、`task_list`、`knowledge_asset_detail`、
`knowledge_list_ontology_nodes`、`knowledge_list_ontology_relations`、
`knowledge_search`。

本次问题（岸基监控发现疑似漏油事件，要求按现有政策给出评估与处置建议并给出
证据链）经 `read_skill_md` 实际加载 `policy-evidence-qa`、
`marine-event-assessment`、`dispatch-work-order-orchestration`、
`decision-trace-audit` 四个 Skill；第 5 个 `cross-document-decision` 已绑定，
但未被该问题触发。**绑定 5 个、本次触发 4 个**是如实口径。

值得单独说明的是本次输出的**拒答行为**：系统判定现行资产库中不存在针对
“漏油／油污／溢油”的适用政策条款，明确结论为疑似漏油事件不可套用海漂垃圾
处置流程，应升级人工研判并转报环保／海事渠道，**不得自动派单给打捞机器人或
机械臂**，同时列出四项证据缺口：

1. 事件库近 168 小时无油污记录，按 `main_class=oil` 过滤两次返回 `[1000]` 服务器内部错误；
2. 全部事件 `evidence_url=null`，无影像可复核；
3. 政策资产 `source_uri=null`，属演示资产，无外部法规原文可溯源；
4. 无任何关联油污的工单或决策痕迹。

**“证据不足时拒绝给出处置动作”比“给出流畅答案”更能说明这套编排是可信的**，
这正是本设计要展示的能力边界。

## 五、调试迭代经验

| 时间 | 问题 | 处理与结论 |
| --- | --- | --- |
| 2026-09-28 | Nexent 首次接入 Oceanus MCP | 完成 MCP 注册、21 工具加载、5 个 Skill 导入与一次 `knowledge_list_assets` 调用（R-NX-02） |
| 2026-09-29 | 换个入口复验同一能力 | 以本地官方源码部署内置 suadmin 复验（R-NX-03）；灌入演示数据后返回 total=4 |
| 2026-09-29 | 无 Agent，工具面无法端到端 | 创建并发布 Agent（R-NX-04，版本 v2），绑定 5 个 Skill 与 21 个工具，导出配置 ZIP；当时未配模型，完整问答列为待补 |
| 2026-09-30 | Agent 运行时被拒 | 根因：Nexent 要求 Agent `name` 为合法 Python 标识符，连字符形式不合法。改为 `seasight_governance_decision_agent` |
| 2026-09-30 | 控制台看不到 Agent | 根因：模型状态非 `available`。经官方 `/api/model/healthcheck` 后 `/api/agent/list` 返回 `is_available: true`，控制台恢复可见 |
| 2026-09-30 | 本地完整问答验收 | 发布版本 4 `v0.2.0-seasight-governance-llm`，跑通完整 Skill 问答（R-NX-09，指标见 §4.3） |
| 2026-09-30 | 托管平台私网路径 | 已建私网环境与网关，但账号欠费使“创建 Target”原生禁用（Target 0/10），Agent 启用 VPC 报 `AgentArts.03002206`（R-NX-07 `blocked`） |
| 2026-09-29 | 托管平台公网路径 | MCP 注册、21 工具加载、公网端点真实只读调用完成（R-NX-05）；导入 5 个 Skill（R-NX-07）；公网环境 Skill 绑定按钮 disabled，平台限制已留证（R-NX-06） |

两条最值得写进答辩的经验：

- **平台有硬约束，必须在设计早期发现**。Nexent 的 Agent 命名规则、托管平台
  “公网环境不支持 Skill”两条限制都不是文档里一眼能看到的，是实跑撞出来的；
- **托管平台 Skill 验收必须同时满足“私网环境 + 可达 endpoint + Target 绑定”，
  缺一不可**，不能用临时隧道或 `127.0.0.1` 代替，这正是当前 R-NX-07 卡住的点。

## 六、示例问答与截图索引

已采集（均为本地运行，非托管平台内）：

| 编号 | 内容 | 证据文件 |
| --- | --- | --- |
| R-NX-09 | Nexent 控制台首页（Agent 可见） | `artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/nexent-console-home.png` |
| R-NX-09 | Nexent 控制台新建对话界面 | `artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/nexent-console-newchat.png` |
| R-NX-09 | 完整 SSE 原始事件流 | `.../llm-qa-2026-09-30/agent-run-sse.txt` |
| R-NX-09 | 事件序列 / 工具轨迹 / 运行摘要 | `.../agent-run-events.json`、`agent-run-tools.json`、`agent-run-summary.json` |
| R-NX-09 | 发布与版本记录 | `.../agent-publish.json`、`agent-versions.json` |
| R-KN-04 | 知识域前端“检索结果 + 引用”截图 | `artifacts/knowledge-qa-trace/01-检索结果-本体图检索与引用.png` |
| R-KN-04 | 知识域前端“决策证据链 + 资产版本引用”截图 | `artifacts/knowledge-qa-trace/02-决策证据链-资产版本引用.png` |
| R-KN-04 | 问答轨迹 API JSON（问题 → 检索 → 决策 → 证据链） | `artifacts/knowledge-qa-trace/latest.json` |

**待补**：华为 AgentArts 托管平台内的完整 Skill 问答截图（R-NX-07 `blocked`）。
解除账号欠费并按 `huawei-agentarts-vpc-target-runbook.md` 创建 Target、绑定
Agent、发布后，在平台内跑一次完整问答并另存为 `evidence/hosted-*-qa-*.png`，
届时登记 R-NX-08。

R-KN-04 的口径提醒：该轨迹为 `hop_count=0` 的**直接资产引用检索**，不是多跳
路径问答，也不是 LLM 生成式问答，不得与 R-NX-09 混写。

## 七、随附文件说明

| 类别 | 文件 | 说明 |
| --- | --- | --- |
| MCP 实现 | `integrations/nexent/mcp_server/server.py` | Oceanus Domain Cognition MCP 服务实现 |
| MCP 依赖 | `integrations/nexent/mcp_server/requirements.txt` | 运行依赖 |
| MCP 配置模板 | `integrations/nexent/.env.example` | 环境变量模板，不含真实密钥 |
| MCP 接入说明 | `integrations/nexent/README.md` | 工具面、安全边界、部署方式 |
| MCP 接口描述 | `artifacts/nexent-mcp-openapi.json` | 工具接口定义 |
| Skills | `integrations/nexent/skills/*/SKILL.md` | 5 个工作流模板（政策证据问答 / 事件研判 / 跨文档决策 / 工单编排 / 决策轨迹审计） |
| Agent 配置导出 | `artifacts/nexent-platform-acceptance/evidence/agent-run-export.zip` | Agent 配置与绑定 Skills 导出物 |
| Agent 配置记录 | `artifacts/nexent-platform-acceptance/agent-create-2026-09-29.yaml` | R-NX-04 配置 / 发布 / 调用关系 |
| 本地问答登记 | `artifacts/nexent-platform-acceptance/recheck-2026-09-30-llm-qa.yaml` | R-NX-09 结构化验收登记 |
| 托管平台记录 | `artifacts/nexent-platform-acceptance/hosted-2026-09-29.yaml`、`hosted-agent-2026-09-29.yaml` | R-NX-05 / R-NX-06 |
| 阻断记录 | `artifacts/nexent-platform-acceptance/hosted-2026-09-30-target-blocked.yaml` | R-NX-07 `blocked` |
| 恢复手册 | `docs/competitions/huawei-agentarts-vpc-target-runbook.md` | R-NX-08 执行手册 |
| 知识库证据 | `artifacts/evolution-demo/latest.json`、`artifacts/ontology-eval/latest.json` | R-KN-01 / R-KN-02 |

说明：以上文件均由仓库版本控制；模型密钥、MCP 令牌、后端账号与云凭据一律
不随包提交。

## 八、托管平台（AgentArts）状态与恢复路径

已完成的托管平台动作：

1. 注册 MCP 服务 `Oceanus Domain Cognition MCP`，状态“部署成功”，工具列表
   加载 21 个只读工具，公网端点 `knowledge_list_assets` 真实只读调用返回
   total=4（R-NX-05）；
2. 创建 Agent 并配置 `deepseek-provider/deepseek-chat`，写入诚实系统提示词
   （R-NX-06）；
3. 导入 5 个 Skill（R-NX-07）；
4. 创建私网环境 `environment-seasight-vpc-verify` 与网关 `seasight-vpc-gateway`
   （R-NX-07）。

当前阻断（R-NX-07 `blocked`）：华为云账号欠费导致私网网关“创建 Target”原生
禁用（Target 0/10），Agent 启用 VPC 时报 `AgentArts.03002206`，因此托管平台内
完整 Skill 问答**尚未跑通**，`live_skill_qa_completed: false`。

恢复路径（R-NX-08，2026-10-01 已取得部分进展）：网关层 MCP POST 与
`agent_runtime_status` 工具调用已实证成功；仍需在私网环境绑定 Agent、发布并
在平台内跑通一次完整 Skill 问答。后续步骤：在 `vpc-seasight` 内创建可达的
`/mcp` Target → 绑定 Agent → 发布 → 在平台内跑一次完整 Skill 问答并留存平台内
截图 → 按 `hosted-skill-qa.template.yaml` 登记。完成前，全部对外材料维持
“本地已验收、托管平台未验收”的口径。

## 九、诚实边界与不可宣称项

- 感知精度 `not_evaluated`；`76%` 仅指时序链路误报抑制率；
- 演示数据（total=4）不等于真实脱敏行业数据集；公开开放数据替代评测
  （R-OD-01，8 份生态环境部公开通知）也只是 E1 替代证据，不代表领域准确率；
- R-KN-04 为 `hop=0` 直接引用检索，不是多跳问答；
- 本文档所有“已跑通”仅指**本地官方源码部署 Nexent**，不含华为 AgentArts
  托管平台内验收；
- 本体抽取评测（R-KN-02）、增量维护对比（R-KN-03）、多行业迁移（R-MG-01）
  均为 E1 级软件内部或演示级结果，不表述为真实行业效果。

## 十、变更记录

| 日期 | 变更 | 操作人 |
| --- | --- | --- |
| 2026-09-30 | 建立「材料 2」独立提交件底稿：整体设计思路、Agent 配置完整细节、Skill 分层编排、调试迭代经验、示例问答截图索引、随附文件说明、托管平台状态与恢复路径、诚实边界 | WP-15 |
