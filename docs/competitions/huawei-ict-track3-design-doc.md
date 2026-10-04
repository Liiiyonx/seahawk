# 探海灵眸 Oceanus · 可进化决策智能体开发设计文档（赛道三底稿）

> 版本：1.4（提交件底稿）
> 编制日期：2026-09-30
> 用途：华为 ICT 大赛 创新赛道三初赛/决赛评测要求的开发设计文档底稿，
> 覆盖项目概述、整体方案设计、知识图谱构建方案、智能体构建方案、
> 原始数据说明、数据处理说明六节。
> 上位口径：《docs/evidence-claim-policy.md》、《docs/competitions/huawei-tech-matrix.md》

## 一、项目概述

### 1.1 项目名称

探海灵眸 Oceanus —— 面向县域海洋环境治理的“感知—决策—执行”可进化决策
智能体。

### 1.2 一句话定位

本项目不是单纯的海漂垃圾识别系统，而是**政务-县域海洋环境治理场景下的领域
资产认知智能体**：把政策文件、监测报告、事件、台账等沉睡数据资产登记为可
溯源的知识域，通过半自动本体构建与跨文档多跳检索支撑治理决策，并把决策
轨迹、审批、派单和执行回执固化为可审计的证据链。

### 1.3 目标用户与业务痛点

- 目标用户：县级海洋渔业主管部门、乡镇海渔站、环卫队、值班研判人员。
- 业务痛点：
  1. 政策、标准、监测报告、月度台账分散在不同系统，跨文档查找和比对靠人工；
  2. 治理决策依赖经验，缺少可追溯的决策依据；
  3. 海漂垃圾事件从发现、研判到派单、回执的链路存在人工断点；
  4. 低资源场景下缺少标注数据，难以直接训练领域知识图谱本体。

### 1.4 赛题定位

赛道三要求面向医疗、金融、制造、政务任一或多个行业构建领域资产认知智能体。
本项目选择**政务-县域海洋环境治理**单行业深度落地，并以 Skill 模板方式预留
多行业轻量化迁移能力。

## 二、整体方案设计

### 2.1 总体架构

```text
多模态行业数据（政策文本 / 表格台账 / 事件 / 遥测 / 图像 / 数据集）
        │  登记 + 版本化 + 内容哈希
        ▼
Oceanus 知识域（六类资产，不可变版本）
        │  候选抽取（低资源、无需标注）
        ▼
本体候选 → 人工审核 → 本体版本发布（携带 standard_codes）
        │
        ▼
跨文档多跳检索（检索-推理双驱动）
        │
        ▼
决策轨迹与证据固化（可溯源、可审计）
        │
        ▼
Nexent 智能体编排（MCP 工具面 + 5 个 Skill 工作流）
        │
        ▼
事件研判 → 审批 → MQTT 派单 → 执行回执（机器人/机械臂为可插拔执行端）
```

### 2.2 技术栈

| 层 | 技术 | 作用 |
| --- | --- | --- |
| 后端 | FastAPI + SQLAlchemy + PostgreSQL 16 + PostGIS | 公开 API、权限、审计、知识域 |
| 消息 | Redis + EMQX MQTT | 事件队列、派单与执行回执 |
| 前端 | Vue 3 | 大屏、知识域四工作台、Agent 审批 |
| 智能体 | ModelEngine Nexent | MCP 协议接入、Skill 编排、平台运行 |
| 集成 | 自研 Oceanus Domain Cognition MCP | 通过 `/api/v1` 暴露领域认知能力 |

### 2.3 安全与权限边界

- Nexent 只能通过公开 `/api/v1` 接口访问系统，MCP 不导入后端 ORM、
  不直连数据库。
- MCP 默认只注册 21 个只读工具；开启 `SEASIGHT_MCP_ALLOW_WRITES=true`
  后才注册 11 个写入工具（合计 32 个）。
- 后端继续负责角色、辖区权限、本体审核、审批、幂等和审计。
- 出站认证使用最小权限账号，通过 `/api/v1/auth/login` 获取短期令牌并自动刷新。

## 三、知识图谱构建方案

### 3.1 资产模型

支持六类资产：`document`、`table`、`image`、`event`、`telemetry`、
`dataset`。每条资产有稳定资产 ID，内容按版本追加，版本记录内容哈希，
支持 `standard_codes` 与行业规范/标准体系对齐。

### 3.2 低资源半自动本体构建

当前实现采用**确定性候选算法**，不依赖标注数据、不冒充训练模型：

- 候选节点：对资产标题与正文做词频/标题权重统计，输出候选术语；
- 候选关系：基于文档内共现生成候选关系，并携带来源资产版本与引用片段；
- 候选默认未审核；人工审核通过后才能发布；
- 本体版本可继承父版本，新资产版本可进入新一轮候选抽取；
- 抽取与检索过程可解释，候选带来源证据，便于人工复核。
- 软件内部确定性评测已登记 R-KN-02：在 12 份内部合成治理语料上，
  top-20 中当前实现 100% 为不超过 12 字的短语节点、0 条整句块候选，
  精确命中内部金标术语 11/20（55%，朴素频次基线 1/20=5%），top-20
  术语覆盖 12/20=60%、top-100 覆盖 100%（基线 95%），并输出带来源证据
  的候选关系；top-20 关系命中 1/7=14.29%，预算放宽到 200 后覆盖 7/7。
  金标为内部 fixture，不是行业标准答案，不据此宣称识别更准。

### 3.3 持续动态更新与标准对齐

- 新资产版本追加后，可对指定资产版本重新抽取候选；
- 节点、关系、本体版本均带审核状态与发布状态，已发布版本会自动退役
  旧版本，保证检索使用最新已发布本体；
- `standard_codes` 字段用于对接行业规范/标准体系，检索可按标准码过滤；
- 标准体系对齐目前落到映射表 `docs/competitions/standard-code-mapping.md`，
  真实规范条款待获取；未取得官方原文、文号或条款的规范不写条文。

### 3.4 算法边界

当前本体抽取是确定性规则算法，不是训练完成的领域大模型；多跳检索基于
已发布的显式本体关系，不应表述为通用图谱推理引擎。后续可在不改变 API
与证据契约的前提下，将抽取方法替换为外部模型。

## 四、智能体构建方案

> 本节是开发设计文档视角的摘要。赛道三【材料 2】要求的独立《Nexent 智能体
> 整体设计说明》见 `docs/competitions/huawei-ict-track3-agent-design.md`
> （Word：`项目文档/华为ICT赛道三_Nexent智能体设计说明.docx`）。

### 4.1 模型信息（如实说明）

本节区分两个不同的模型位置，避免把平台侧验收写成后端已内置 LLM：

- **Oceanus 后端内置规划器**：默认使用**确定性规则回退**；LLM 规划器通过
  `OpenAICompatibleModelClient` 接入，配置项
  `AGENT_MODEL_BASE_URL` / `AGENT_MODEL_API_KEY` / `AGENT_MODEL_NAME` 已就绪。
  截至 2026-09-30，后端内置 LLM 规划器**尚未真实调用外部模型**，验收依赖
  平台侧注入的模型。
- **Nexent 平台侧 Agent 模型**：本地官方源码部署已验证 Agent
  `seasight_governance_decision_agent` 配置 DeepSeek `deepseek-v4-pro`，
  并完成一次真实 LLM 完整 Skill 问答（R-NX-09，2026-09-30）；华为
  AgentArts 托管平台 Agent 配置 `deepseek-provider/deepseek-chat`（R-NX-06），
  托管平台内完整问答仍待私网 Target 打通（R-NX-07 blocked）。
- 模型不可用、超时或输出不合 schema 时，规划器返回
  `source="rule_fallback"` 与结构化 `fallback_reason`，由规则规划器接管。
- 感知识别当前为 OpenCV 传统视觉冷启动，独立测试集就绪前一律写
  `not_evaluated`。

### 4.2 工具信息（MCP 工具面）

默认 21 个只读工具，开启写入后 32 个，分组如下：

| 组 | 工具 |
| --- | --- |
| 资产 | `knowledge_list_assets`、`knowledge_asset_detail` |
| 本体 | `knowledge_list_ontology_versions`、`knowledge_ontology_version_detail`、`knowledge_list_ontology_nodes`、`knowledge_list_ontology_relations` |
| 检索 | `knowledge_search` |
| 决策 | `knowledge_list_decisions`、`knowledge_decision_evidence` |
| 业务 | `event_get`、`event_list`、`task_get`、`task_list`、`task_ack_history`、`dashboard_get` |
| Agent 审计 | `agent_runtime_status`、`agent_list_runs`、`agent_run_detail`、`agent_run_steps`、`agent_list_tools`、`agent_list_approvals` |

写入工具（按开关注册）：资产登记与版本追加、本体版本创建/抽取/审核/发布、
决策创建、Agent 运行控制与审批。

### 4.3 知识库信息

当前知识域演示数据为 4 个资产版本（2 个资产：治理方案 document + 月度台账
table，各 2 个版本），见 R-KN-01 记录。数据为演示数据，未声称是真实
脱敏行业数据集。

### 4.4 调用关系图

```text
Nexent Agent
  ├── Skill：policy-evidence-qa
  ├── Skill：marine-event-assessment
  ├── Skill：cross-document-decision
  ├── Skill：dispatch-work-order-orchestration
  └── Skill：decision-trace-audit
          │
          ▼
Oceanus Domain Cognition MCP（Bearer 入站鉴权）
          │  出站令牌自动刷新
          ▼
Oceanus /api/v1（角色 / 辖区 / 审批 / 审计）
          │
          ▼
PostgreSQL（资产 / 本体 / 决策 / 事件 / 任务）
```

已在本地产物中生成真实调用关系：Agent `seasight_governance_decision_agent`
通过 `GET /api/agent/call_relationship/1` 返回 21 个 MCP
工具（`knowledge_*`、`event_*`、`task_*`、`dashboard_*`、`agent_*`），
登记号 R-NX-04（发布版本 v2，未配置 LLM）。2026-09-30 在同一本地
官方源码部署中把该 Agent 升到发布版本 4
`v0.2.0-seasight-governance-llm`，叠加 DeepSeek `deepseek-v4-pro` 模型配置
并跑通完整问答（登记号 R-NX-09），该关系图由此从“工具/Skill 编排关系”
延伸为包含模型问答链路的端到端运行，证据见
`evidence/llm-qa-2026-09-30/`。该端到端运行限定在**本地官方源码部署**，
不等于华为 AgentArts 托管平台内跑通。

### 4.5 检索-推理双驱动执行流

- 检索驱动：`knowledge_search` 对资产做确定性打分检索，返回资产版本、
  片段和引用；
- 推理驱动：已发布本体存在时执行带路径的多跳检索，返回 `mode`、
  `path`、`citations`；无可用本体时明确回退普通检索；
- 决策驱动：决策轨迹按顺序固化证据，每条证据带资产版本、节点、关系、
  跳数和引用，读取 `/knowledge/decisions/{id}/evidence` 可复核。

### 4.6 Skill 工作流模板

5 个 Skill 定义触发条件、工具顺序、停止条件和输出要求：

| Skill | 用途 |
| --- | --- |
| 政策证据问答 | 用可引用资产版本回答政策问题 |
| 事件研判 | 评估事件及对应治理依据 |
| 跨文档决策 | 本体引导的多跳推理 |
| 工单编排 | 协调事件、Agent、审批与工单检查，不绑定机器人厂商 |
| 决策轨迹审计 | 核对决策是否可追溯到证据与执行步骤 |

Skill 不替代 MCP 权限判断，可替换本体和资产源后跨行业复用。

### 4.7 调试迭代经验

- 2026-09-28：本地 Nexent v2.6.1 完成 MCP 注册、21 工具加载、5 Skills
  导入和一次 `knowledge_list_assets` 调用（R-NX-02）。
- 2026-09-29：以本地官方源码部署内置 suadmin 复验同一入口（R-NX-03）；
  灌入知识域演示数据后返回 total=4。
- 2026-09-29：在本地官方源码部署中创建并发布 Agent（R-NX-04，发布版本
  v2），绑定 5 个 Skill 与 21 个 MCP 工具，调用关系 API 返回 21 个 MCP
  工具，导出 Agent 配置 ZIP；当时未配置 LLM，完整问答列为待补。
- 2026-09-30：本地官方源码部署完成模型接入与完整问答（R-NX-09）：Agent
  identifier 修正为 `seasight_governance_decision_agent`（Nexent 要求合法
  Python 标识符，连字符形式会被运行时拒绝），发布版本 4
  `v0.2.0-seasight-governance-llm`，配置 DeepSeek `deepseek-v4-pro`，经
  `POST /agent/run`（SSE）跑通一次真实 LLM Skill 问答：HTTP 200、13,204
  个事件、8 步、31 次工具调用、13 个唯一工具、无 run error，最终回答
  2,777 字；`read_skill_md` 实际加载 `policy-evidence-qa`、
  `marine-event-assessment`、`dispatch-work-order-orchestration`、
  `decision-trace-audit` 4 个 Skill（第 5 个 `cross-document-decision`
  已绑定但本次问题未触发）。调试中发现并修复控制台不可见问题：模型状态需为
  `available`，经官方 `/api/model/healthcheck` 后 `/api/agent/list` 返回
  `is_available: true`，控制台恢复可见。该问答在证据不足时明确输出
  “不适用/不可自动派单”结论并列出 4 项证据缺口，未伪造政策依据。
- 2026-09-29：真实后端跑通知识进化闭环 R-KN-01：2 资产、4 版本、60 候选、
  图谱多跳检索 4 命中、决策证据 4 条。
- 2026-09-30：本体候选抽取确定性评测重跑通过（R-KN-02），结果见
  `artifacts/ontology-eval/latest.json`；E1 软件内部结果，不是真实脱敏
  行业数据评测、领域准确率或感知精度。
- 2026-09-29：知识域问答轨迹采集通过（R-KN-04）：真实后端执行
  “问题 → 检索（ontology_graph，4 条命中）→ 创建决策 → 读取 4 条有序
  证据链”，保存 API JSON 与 2 张界面截图；轨迹为 hop=0 的直接资产引用
  检索，不是多跳路径、不是 LLM 生成式问答。
- 2026-09-30：公开开放数据本体抽取评测重跑通过（R-OD-01）：8 份生态环境部
  公开通知，来源 URL 与 SHA256 可追溯；全量候选覆盖内部标注术语 9/32
  （28.125%）、精确命中 6/32（18.75%）、关系 3/3（100%）；top-20 术语
  覆盖 28.125%（朴素基线 28.125%），top-20/50/100/200 关系均为 3/3；
  不据此宣称识别更准；为 E1 替代证据，不是真实脱敏行业数据评测。
- 华为托管平台（AgentArts，区域 cn-southwest-2）MCP 注册与公网端点真实只读
  调用已于 2026-09-29 完成并登记 R-NX-05：`Oceanus Domain Cognition MCP`
  状态“部署成功”，工具列表加载 21 个只读工具，`knowledge_list_assets` 返回
  total=4；当日 Skills 导入与控制台调用输出尚未完成，后续在 2026-09-30
  复核中确认 5 个 Skill 已全部导入（见 R-NX-07），控制台内完整问答输出仍受
  Target 阻断。
- 2026-09-29：华为托管平台（AgentArts）创建 Agent
  `seasight-governance-decision-agent`（R-NX-06），配置
  `deepseek-provider/deepseek-chat`，写入诚实系统提示词；编辑页明确提示
  公网环境不支持 Skill（Skill 绑定按钮 disabled），平台限制已留证。完整
  Skill 问答需私网环境 + 私网可访问 MCP endpoint 后验收。
- 2026-09-30：华为托管平台私网路径复核受阻（R-NX-07 `blocked`）：已建
  私网环境 `environment-seasight-vpc-verify` 与网关 `seasight-vpc-gateway`，但
  华为云账号欠费使“创建 Target”原生 disabled（0/10），Agent 启用 VPC 报
  `AgentArts.03002206`；经验教训是托管平台 Skill 验收必须同时满足
  “私网环境 + 可达 endpoint + Target 绑定”，缺一不可，不能用临时隧道或
  `127.0.0.1` 代替。

## 五、原始数据说明

### 5.1 当前演示数据

| 资产 | 类型 | 版本数 | 内容 | 来源口径 |
| --- | --- | --- | --- | --- |
| 连江海漂垃圾治理工作方案（演示） | document | 2 | 治理流程、重点区域、执行末端 | 演示数据 |
| 连江重点区域海漂垃圾月度台账（演示） | table | 2 | 重点区域聚集次数、资源、回执口径 | 演示数据 |

资产 ID 前缀 `EVO`，标题带“演示”标记，避免与真实行业数据混淆。

### 5.2 真实行业数据状态

- 尚未取得真实脱敏行业数据集，未进行效果评测；
- 已用 8 份生态环境部公开开放通知完成替代评测（R-OD-01，E1），来源 URL
  与 SHA256 可追溯；替代评测不等于赛题要求的“真实脱敏行业数据集开展效果
  评测”，也不冒充真实脱敏数据；
- 赛题附加分“真实脱敏行业数据集开展效果评测”待数据来源确认后执行；
- 若后续引入连江真实数据，需先完成脱敏并确认与连江赛材料的关系，
  不把同一份未脱敏证据直接复用。

## 六、数据处理说明

### 6.1 登记与版本化

- `operator` 登记资产，写入资产类型、标题、描述、来源、区域、辖区、
  安全级别、标准码和标签；
- 首次登记生成 v1，追加版本时旧版本置为 `superseded`，新版本记录
  `content_hash`，内容按不可变版本保留。

### 6.2 本体处理

- 对指定资产版本抽取候选节点与关系，候选默认 `proposed`；
- `approver`/`admin` 逐条审核节点与关系；
- 发布时校验：不允许存在未审核候选，且至少一个节点审核通过；
- 新版本发布后旧版本自动退役，检索使用最新已发布本体。

### 6.3 检索与决策

- 检索仅覆盖 `active` 资产的最新版本；
- 支持资产类型、标准码、辖区过滤；
- 决策创建时自动执行检索并把命中证据按顺序固化；证据不足时状态记为
  `insufficient_evidence`，不伪造答案。

## 七、平台运行与验收证据

| 登记号 | 内容 | 证据位置 |
| --- | --- | --- |
| R-NX-02 | 本地 Nexent v2.6.1 平台侧验收：注册、21 工具、5 Skills、调用一次 | `artifacts/nexent-platform-acceptance/` |
| R-NX-03 | 本地官方源码部署复验：真实调用 `knowledge_list_assets`，灌数据后 total=4 | `artifacts/nexent-platform-acceptance/recheck-2026-09-29.yaml` |
| R-NX-04 | 本地官方源码部署 Agent 配置/发布：5 Skill + 21 MCP 工具绑定、调用关系、导出 ZIP；未配置 LLM，未跑通完整问答 | `artifacts/nexent-platform-acceptance/agent-create-2026-09-29.yaml` |
| R-NX-03B | 本地 MCP 端点复验：`mcp 1.30.0` / 协议 `2025-11-25`、21 工具、3 次真实只读调用 | `artifacts/nexent-platform-acceptance/recheck-2026-09-30.yaml` + `evidence/recheck-2026-09-30/` |
| R-NX-05 | 华为托管平台（AgentArts）MCP 注册、21 工具加载、公网端点真实只读调用 total=4 | `artifacts/nexent-platform-acceptance/hosted-2026-09-29.yaml` + `evidence/hosted-2026-09-29-*` |
| R-NX-06 | 华为托管平台（AgentArts）Agent 创建与 DeepSeek 模型配置；公网环境明确提示不支持 Skill，平台限制已留证 | `artifacts/nexent-platform-acceptance/hosted-agent-2026-09-29.yaml` |
| R-NX-07 | 华为托管平台完整 Skill 问答：**blocked**。私网环境与网关已建；华为云账号欠费，创建 Target 原生 disabled（0/10），Agent 启用 VPC 时报 `AgentArts.03002206` | `artifacts/nexent-platform-acceptance/hosted-2026-09-30-target-blocked.yaml` + `evidence/hosted-2026-09-30-private-gateway-target-blocked.png` |
| R-NX-09 | 本地官方源码部署完整 Skill 问答（**不是华为托管平台验收**）：Agent 发布版本 4、DeepSeek `deepseek-v4-pro`、21 MCP 只读工具 + 5 Skill 绑定、HTTP 200、8 步、31 次调用、13 个唯一工具、2,777 字回答 | `artifacts/nexent-platform-acceptance/recheck-2026-09-30-llm-qa.yaml` + `evidence/llm-qa-2026-09-30/` |
| R-KN-01 | 知识进化闭环：资产、版本、候选、审核、发布、多跳检索、决策证据 | `artifacts/evolution-demo/latest.json` |
| R-KN-02 | 本体候选抽取确定性评测：12 份合成语料、金标术语命中、候选结构、基线对比 | `scripts/ontology_eval.py + artifacts/ontology-eval/latest.json` |
| R-KN-03 | 本体维护模式对比：全量重抽 4.387ms vs 增量追加 1.615ms、节省 63.19%、候选/关系差异说明 | `scripts/ontology_incremental_eval.py + artifacts/ontology-eval/incremental-latest.json` |
| R-KN-04 | 知识域问答轨迹：问题 → 检索（ontology_graph，4 条命中）→ 决策 → 4 条有序证据链，2 张界面截图 + API JSON；hop=0 直接资产引用，非多跳 | `scripts/knowledge_qa_trace_capture.mjs + artifacts/knowledge-qa-trace/latest.json` |
| R-OD-01 | 公开开放数据替代评测：8 份生态环境部公开通知、来源 URL 与 SHA256、全量候选术语覆盖 9/32、精确命中 6/32 与关系 3/3、top-N 对比；E1，非真实脱敏行业数据 | `scripts/open_data_eval.py + artifacts/open-data-eval/latest.json + corpus/manifest.json` |
| R-MG-01 | Skill 模板多行业轻量化迁移验证：海洋/医疗/政务三领域演示语料、同一套 5 SKILL.md、检索命中 3/3 | `scripts/skill_migration_validate.py + artifacts/skill-migration/` |

口径：以上均为软件内部 E1/E2 证据、本地平台侧验收，以及华为托管平台 MCP
注册 / 公网端点调用 / Agent 创建记录。R-NX-09 证明的是**本地官方源码
部署**内的完整 LLM Skill 问答；华为托管平台内完整 Skill 问答仍为
R-NX-07 `blocked`，不得写成“托管平台已验收”。以上记录均不代表真实海域
部署验证，也不代表感知精度。

## 八、能力沉淀与多行业复用

### 8.1 Skill 工作流模板沉淀

模板仓库位于 `integrations/nexent/skills/`，5 个模板均采用同一结构：
`SKILL.md` 的 frontmatter（name / description）定义触发入口，正文固定为
Goal、Workflow、Stop Conditions、Required Output 四段。

| 模板 | 触发条件 | 工具顺序 | 输出 |
| --- | --- | --- | --- |
| `policy-evidence-qa` | 政策/规范依据问答 | 资产列表 → 多跳检索 → 资产详情核验 → 本体检索 | 带版本引用的依据答案与证据缺口 |
| `marine-event-assessment` | 海漂垃圾/治理事件研判 | 事件资产检索 → 台账比对 → 处置建议 | 研判结论、依据引用、待确认项 |
| `cross-document-decision` | 跨文档决策 | 多类型资产检索 → 版本冲突识别 → 决策证据链 | 可溯源决策摘要与引用清单 |
| `dispatch-work-order-orchestration` | 派单工单编排 | 研判结果 → 审批条件核验 → 派单回执 | 工单状态、审批人、回执闭环 |
| `decision-trace-audit` | 决策轨迹审计 | 决策列表 → 证据链读取 → 版本核对 | 审计轨迹与差异报告 |

版本管理：模板目录随仓库 git 冻结；Agent 配置与绑定 Skills 导出 ZIP 已登记
R-NX-04，本地完整问答与发布版本 4 已登记 R-NX-09；华为托管平台 MCP
注册已登记 R-NX-05，5 个 Skill 导入已登记 R-NX-07。发布流程为：模板修改 →
SKILL.md 评审 → Nexent 导入 → 示例问答验证 → 导出配置并存档。

### 8.2 多行业轻量化迁移验证（R-MG-01）

同一套 5 个 SKILL.md 模板已在海洋治理、医疗、政务三个演示资产源上完成
轻量化复用验证，见 `scripts/skill_migration_validate.py` 与
`artifacts/skill-migration/`：

| 领域 | 演示资产数 | 候选数 | 关系数 | 检索命中资产数 |
| --- | --- | --- | --- | --- |
| marine | 3 | 36 | 60 | 3 |
| medical | 3 | 39 | 60 | 3 |
| government | 3 | 40 | 60 | 3 |

迁移时只替换 5 个变更点：资产源、领域词表、标准号、问题集、领域角色映射；
模板结构、候选抽取、共现关系、跨文档检索、证据链输出格式与 MCP 工具风格
保持不变。本验证为 E1/E2 合成演示语料迁移，不是真实脱敏行业数据评测，
也不代表生产跨行业迁移已交付。

### 8.3 业务价值量化框架（E1 测算，非真实运营数字）

下表用于回答“业务价值有没有量化指标”，口径全部标注为测算/演示，不以
内部测算冒充真实运营收益：

| 环节 | 基线（人工口径，E0 假设） | 系统链路（E1/E2 演示实测） | 测算结论 |
| --- | --- | --- | --- |
| 跨文档检索 | 跨系统人工查找政策与台账，10-30 分钟/次 | 知识域多跳检索 <2s，4 条证据链（R-KN-01 / R-KN-04） | 单次检索耗时降低一个数量级以上；运营级节省待 E3 实测 |
| 决策依据固化 | 人工整理证据清单，15-30 分钟/份 | 决策自动固化 4 条有序证据 <5s（R-KN-04） | 依据整理与审计留痕成本下降；测算口径 |
| 派单链路 | 人工电话/口头派单，5-10 分钟 | MQTT 派单秒级下发（E2 联调） | 派单延迟从分钟级降至秒级；现场验证待 E3 |
| 本体维护 | 人工梳理本体，小时级 | 全量重抽 4.772ms / 增量追加 1.755ms，节省 63.22%（R-KN-03） | 低资源本体维护成本降低；仅软件内部相对对比 |

以上数字均为 E0-E2 测算与演示口径，不作为真实业务收益承诺；后续以 E3
真实数据替换基线后重算。

### 8.4 模板复用指南

1. 复制 `integrations/nexent/skills/` 中需要的模板目录；
2. 替换 SKILL.md 触发条件与工具参数中的领域词表；
3. 配置新行业的资产源与标准码；
4. 导入演示/评测语料，运行 `scripts/skill_migration_validate.py` 验证
   候选抽取、关系与检索命中；
5. 在 Nexent 导入模板并完成示例问答验证；
6. 导出 Agent 配置并存档，登记版本。

### 8.5 决赛规划

- **本地完整问答已闭环**：本地官方源码部署的 nexent v2.6.1 + DeepSeek
  `deepseek-v4-pro` 已跑通 21 工具 / 5 Skill 的完整问答（R-NX-09），
  证据链、SSE 事件、工具轨迹与控制台截图均已落盘，可作为初赛“智能体
  可运行 + 示例问答”的已验收材料。
- **托管平台完整问答仍未跑通**：托管平台 MCP 注册（R-NX-05）与 Agent
  创建/模型配置（R-NX-06）已完成，但公网环境不支持 Skill；切私网后
  因华为云账号欠费“创建 Target”原生 disabled（0/10，R-NX-07
  `blocked`），Agent 启用 VPC 时报 `AgentArts.03002206`。充值后可执行
  `docs/competitions/huawei-agentarts-vpc-target-runbook.md`，创建 Target →
  绑定 VPC 网络模式 → 发布新版本 → 平台内完整 Skill 问答，完成后登记
  R-NX-08。完成前不写“托管平台已跑通完整 Skill 问答”。
- 公开开放数据替代评测已完成（R-OD-01）；真实脱敏行业数据评测仍待数据
  来源与脱敏规则确认后执行，不编造评测结果。

## 九、诚实边界

1. 感知精度在独立测试集就绪前一律写 `not_evaluated`；
2. 76% 只能表述为时序链路误报抑制率，不写成识别精度/召回率/准确率；
3. 昇腾、ModelArts、鲲鹏三条均为架构/配置就绪、待验证，未在目标硬件实测；
4. 当前本体抽取是确定性候选算法，不是训练完成的领域大模型；
5. “可接入 Nexent”不等于 Nexent 官方认证或生产 SLA。
6. 标准码映射表中未取得原文的规范一律写“待获取真实规范条款”，
   不为演示资产伪造标准条文。
7. R-KN-04 是本地知识域前端问答轨迹（hop=0 直接资产引用），不写成
   “多跳问答”或“Nexent 平台完整 Skill 问答”。
8. R-OD-01 是公开开放数据替代评测，不写成“真实脱敏行业数据集效果评测”。
9. R-NX-05/R-NX-06 是华为托管平台（AgentArts）MCP 注册、公网端点只读
   调用与 Agent 创建/模型配置证据；R-NX-07 记录托管平台完整 Skill 问答因
   账号欠费、私网 Target 未绑定（0/10）而 `blocked`，不写成“托管平台完整
   Skill 问答已通过”。
10. R-NX-09 是**本地官方源码部署** Nexent 的完整 LLM Skill 问答，可以写
    “本地 Nexent 完整 Skill 问答已跑通”，不得写成“华为托管平台已跑通”
    或“华为 AgentArts 平台验收通过”；它也不构成海域验证或精度证据。

## 十、变更记录

| 日期 | 变更 | 操作人 |
| --- | --- | --- |
| 2026-09-29 | 建立赛道三开发设计文档底稿，覆盖赛题六节 | WP-15 |
| 2026-09-29 | 登记 R-KN-02 本体抽取确定性评测、标准体系映射表，升版 1.0 并转 Word | WP-15 |
| 2026-09-29 | 登记 R-NX-04：Agent 配置/发布、21 MCP 工具绑定、调用关系与导出证据；未配置 LLM | liyongxiang + WP-15 |
| 2026-09-29 | 登记 R-NX-05：华为托管平台 MCP 注册、21 工具加载与公网端点真实只读调用；Skills 导入与控制台调试输出待手动完成 | WP-15 + liyongxiang |
| 2026-09-29 | 补充八章能力沉淀：Skill 模板仓库/版本/发布、多行业迁移 R-MG-01、业务价值量化 E1 测算表、模板复用指南、决赛规划；登记 R-KN-03 增量维护评测，升版 1.1 | WP-15 |
| 2026-09-29 | 登记 R-KN-04 知识域问答轨迹（hop=0 直接引用，非多跳）与 R-OD-01 公开开放数据替代评测（8 份生态环境部公开通知，E1，非真实脱敏），更新 4.7/5.2/七/8.3/8.5/九，升版 1.2 | WP-15 + liyongxiang |
| 2026-09-29 | 登记 R-NX-06 华为托管平台 Agent 创建与 DeepSeek 模型配置（公网环境不支持 Skill，平台限制已留证），更新 4.7/七/8.5/九，升版 1.3 | liyongxiang + WP-15 |
| 2026-09-30 | 登记 R-NX-03B 本地 MCP 端点复验（`mcp 1.30.0` / 协议 `2025-11-25`，21 工具、3 次只读调用） | WP-15 |
| 2026-09-30 | 第四章增加与【材料 2】《Nexent 智能体整体设计说明》的交叉引用（`docs/competitions/huawei-ict-track3-agent-design.md`），消除封面重复版本行，升版 1.4 | WP-15 |
| 2026-09-30 | 登记 R-NX-07 `blocked`：华为托管平台私网环境/网关已建，Target 因账号欠费原生 disabled（0/10），Agent 启用 VPC 报 `AgentArts.03002206`；新增充值后 runbook（R-NX-08 准备） | liyongxiang + WP-15 |
| 2026-09-30 | 登记 R-NX-09 本地官方源码部署完整 Skill 问答：Agent 版本 4 `v0.2.0-seasight-governance-llm` + DeepSeek `deepseek-v4-pro`，21 工具 / 5 Skill，HTTP 200、8 步、31 次工具调用、2,777 字回答，含证据链与控制台截图；更新 4.1/4.4/4.7/七/8.5/九，升版 1.4。**华为托管平台完整问答仍为 R-NX-07 blocked** | liyongxiang + WP-15 |
