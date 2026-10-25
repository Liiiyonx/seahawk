# 探海灵眸 Oceanus Nexent 智能体整体设计说明

> 版本：1.1（国奖打磨版）
> 编制日期：2026-10-25
> 参赛赛道：华为 ICT 大赛 创新赛道三
> 文档定位：初赛/决赛评测要求的智能体整体设计说明（材料 2）
> 证据口径：本地官方源码部署与华为 AgentArts 托管平台双端均已跑通完整 Skill 问答（R-NX-09 / R-NX-08）；知识域 LLM 通道已在 ModelArts Studio MaaS（昇腾资源池）完成真实推理评测（R-MA-01）

## 一、文档定位与诚实边界

本文档是赛道三「材料 2」的正文，回答一个问题：**这个智能体在 Nexent 上是怎么
搭起来的、每一层配置是什么、证据在哪里**。

本文档同时是**证据分级声明**，三种运行位置在全文中严格分开，不得互相替换：

| 运行位置 | 含义 | 当前状态 |
| --- | --- | --- |
| 本地官方源码部署 Nexent | 按官方仓库 `ModelEngine-Group/nexent` 本地部署，v2.6.1 | **完整 LLM Skill 问答已跑通**（R-NX-09） |
| 华为 AgentArts 托管平台 | 华为云控制台内注册 MCP、导入 Skill、创建 Agent | MCP 注册与公网端点只读调用完成（R-NX-05）、Agent 与模型配置完成（R-NX-06）、5 个 Skill 已导入；平台内完整 Skill 问答已跑通（R-NX-08，2026-10-24）；**平台内 MCP 工具面真实调用已验证（R-NX-10，2026-10-25：event_list + knowledge_search 端到端，服务端日志逐条对应）** |
| Oceanus 生产后端 | 项目自研 FastAPI + PostgreSQL 业务系统 | 独立运行，内置规则规划器；知识域 LLM 通道已接 ModelArts MaaS（昇腾池）真实推理（R-MA-01） |

由此产生四条**不可宣称**：

1. 本地 Nexent 验收与华为 AgentArts 托管平台验收是**两次独立验收**，证据分别
   登记（R-NX-09 / R-NX-08），不得合并表述或互相替代；
2. 平台侧验收 **不等于** 海域现场部署验证，也不代表治理效果；
3. 感知精度一律 `not_evaluated`，`76%` 仅指时序链路误报抑制率，不是识别准确率；
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
| 托管平台验收智能体 | `seasight-governance-agent-vpc2`（R-NX-08，2026-10-24，见 §八） |

命名上踩过一次真实约束：Nexent 要求 Agent 的 `name` 是合法 Python 标识符，
含连字符的形式会在运行时被拒绝（`must be a valid Python identifier`），
因此平台内 identifier 使用下划线形式，对外展示名保持不变。这一点属于调试经验，
写在本文 §五。

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

托管平台侧模型链路不同（私网内经 ECS TLS 中转与模型名重写调用
`deepseek-chat`），完整链路见 §八图 11，两者不混写。

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

知识层不是“向量库 + 文档”这么简单，而是**版本化资产 + 本体图谱**双层结构，
完整生命周期见图 1：

![图 1 知识域生命周期：六类资产版本化 → 双通道候选抽取 → 人工审核 → 本体版本发布 → 多跳检索 / 证据链 / 检索-生成问答（数字均有登记产物）](artifacts/doc-figures/fig-m2-knowledge-pipeline.png)

| 层 | 内容 | 检索方式 |
| --- | --- | --- |
| 资产层 | 治理方案 document、月度台账 table，各含版本；共 2 个资产、4 个资产版本（R-KN-01） | `knowledge_search` 确定性打分，返回资产版本、片段、引用 |
| 本体层 | 半自动抽取的节点与关系，按本体版本管理 | 已发布本体存在时走本体引导多跳检索，返回 `mode`、`path`、`citations`；无可用本体时明确回退普通检索 |

当前库内数据为**演示数据**（total=4），用于打通往返链路与截图取证，不表述为
真实脱敏行业数据。真实脱敏数据的评测状态见 §九。

**知识域 LLM 通道（2026-10-24 上线，登记号 R-LLM-01）**：OpenAI 兼容端点
（`KNOWLEDGE_LLM_*` 独立配置，默认关闭）承担两件事，规则与检索通道始终兜底：

| 通道 | 行为 | 兜底 |
| --- | --- | --- |
| 本体候选抽取主通道 | LLM 按严格 JSON schema 抽取节点/关系（关系类型限定 8 词表、实体类型限定 6 词表、引文必摘原文），经校验后与规则候选按 canonical 去重合并 | 调用失败/输出非法 → 整体回退规则通道，`extraction_fallback_reason` 落版本 metadata |
| 检索-生成问答（R-KN-06） | `POST /api/v1/knowledge/qa`：先多跳检索，模型只允许依据检索证据作答，回答内嵌 [c:编号] 引用 | 模型失败 → 降级输出原始证据列表并明示“未生成模型结论”；证据不足 → `insufficient_evidence=true` 拒答 |

通道机制由 20 项专项测试与确定性评测守卫；**2026-10-24 已配真实端点并完成
真模型评测（R-LLM-01 real / R-KN-06 real，DeepSeek `deepseek-chat`）**：

| 评测 | 真实数字 | 口径 |
| --- | --- | --- |
| 双通道抽取对照（R-LLM-01 real） | 规则 top-20 术语 11/20、关系 1/7（与 R-KN-02 对账一致）；LLM 合并列表 9/20、关系 1/7（命中"海漂垃圾→机械臂"）；纯 LLM 候选命中全部 7 个核心领域词，漏乡镇/动作词 | 内部合成语料（E1）；**负结果如实报告**：本语料上 LLM 未跑赢手调规则先验，价值在零样本扩展与引文证据 |
| 生成式问答（R-KN-06 real） | 接地问题按检索证据回答并标 [c:1]；漏油问题明示 `insufficient_evidence=true` 并列出四类证据缺口（应急预案/上报流程/围油栏吸油材料/监测取证） | 演示语料（E1）；拒答叙事与 R-NX-09 本地 Nexent 案例一致 |
| 真实公开文本对照（R-LLM-02） | R-OD-02 的 8 份生态环境部真实文件：规则 30 节点/40 关系（29 条无类型共现）；LLM 26 节点/18 关系全部带类型与资产版本引用，抽出许可证核发、倾倒区选划、流域监督管理局等法规术语 | 真实公开政务文本（E1/E2）；描述性对照无金标，不宣称准确率 |
| **ModelArts(昇腾池)推理（R-MA-01）** | 同一双通道切换至华为 ModelArts Studio MaaS 端点：GLM-5.3 术语 13/20 反超规则 11/20；问答双景复现（接地双引用+漏油拒答）；真实政务文本 34 关系全带类型与引用 | MaaS 共享端点按 token 计费；语料口径同上 |

**三模型 × 三语料评测汇总（2026-10-24）**：

| 通道/端点 | 合成语料术语 top-20 | 合成语料关系 | 真实政务文本关系质量 | 备注 |
| --- | --- | --- | --- | --- |
| 规则通道（词频+共现，基线） | 11/20 | 1/7 | 40 条中 29 条无类型共现 | 手调先验：乡镇/动作词加权 |
| DeepSeek deepseek-chat（公网） | 9/20 | 1/7 | 18 条全带类型与引用 | 纯 LLM 命中全部 7 核心领域词 |
| GLM-5.3（ModelArts 昇腾池） | **13/20 反超规则** | 0/7（如实） | 34 条全带类型与引用 | 首个在合成语料反超规则的 LLM；负结果并存如实报告 |

**检索与本体定量化评测（2026-10-26，登记号 R-KN-07 / R-KN-08）**——把检索与
本体从"功能演示"推进到"有基准、有指标、有对照"：

| 项 | 结果 | 口径 |
| --- | --- | --- |
| 公开语料扩容 | 8 → **20 份**生态环境部公开文件（"海洋倾废管理与审批""海洋生态环境保护"两专栏采集：倾倒区设立公告、入海排污口监督管理技术指南、重点海域综合治理攻坚战行动方案等），库内 27 资产 | 公开数据（E1/E2），采集脚本与 URL/SHA256 清单随包 |
| 本体重建（扩容后） | **100 节点 / 200 关系**（规则 167 + LLM 33 混合抽取） | 确定性 + LLM 混合通道，接口上限内 |
| 本体证据可回溯审计（R-KN-08） | 关系 evidence 引用片段可在所引资产原文逐字回溯 **89.9%**（302/336）；关系完全可回溯 **85.0%**；节点名可回溯 **96.0%** | 确定性字符串核验（零模型调用、可复现），非专家金标准；未回溯样本留档 |
| 检索基准（R-KN-07） | **306 题**（81 标题型 / 100 实体型 / 120 本体二跳 / 5 拒答），金标准全部由本体/资产表自身生成，零模型调用 | 模板固定、可复现；运行全留档；2026-10-26 发现题 id 冲突缺陷并修复重跑（更正说明随证据包，冲突期产物留档） |

三系统对照（27 资产 / 306 题，hit@1 / hit@5 / MRR，2026-10-26 id 更正后冻结快照）：

| 查询类型 | 现有检索（词法+本体图） | 两阶段（BGE-M3+Reranker，昇腾池） | RRF 混合（已合入生产） |
| --- | --- | --- | --- |
| 标题型 | 51.9% / 85.2% / 0.65 | 48.1% / 48.1% / 0.48 | **81.5% / 100% / 0.88（hit@1 +57% 相对提升）** |
| 实体型（无标题词） | **60.0% / 93.0% / 0.74** | 37.0% / 45.0% / 0.41 | 51.0% / 86.0% / 0.65 |
| 本体二跳 | **80.0% / 98.3% / 0.89** | 57.5% / 72.5% / 0.63 | 78.3% / 98.3% / 0.87 |

**v3 迭代（2026-10-26 当日完成并上生产）**：稠密分块文本改为标题三重加权后，
混合检索在标题型查询的 **hit@3 93.8% / hit@5 100%**（hit@1 77.8%）。
**规则路由器**（确定性信号：查询与资产标题的字符二元覆盖≥0.5 → 走 BM25，其余 →
走本体图扩展）总体 hit@1 74.8% / hit@5 97.0% / MRR 0.85，**显著优于全部单一系统**
（Wilcoxon 逐题配对 p<0.001，Holm 校正后依然全部显著）、与逐题型最优 oracle 无显著差异（p=0.10）。
生产 HybridIndex 已切换为标题加权分块，热验证 3.7 秒完成索引重建。

![图 14 R-KN-07 检索评测三系统对照（hit@1 / hit@5，306 题 / 27 资产语料，id 更正后）：RRF 混合标题型 hit@1 81.5%（+57% 相对）且多跳不损失；本体二跳走图扩展最强（98.3%）](artifacts/doc-figures/fig-m2-retrieval-eval.png)

三条诚实发现：**①** 没有全能检索配置——BM25 称霸标题型（hit@1 90.1%、hit@5 100%），
本体图扩展称霸实体型（93.0%）与多跳（98.3%），每类专家在对方地盘显著掉分（Wilcoxon
逐题配对检验）；**②** 稠密+精排在近同构公文语料上全题型显著最差（整篇嵌入稀释判别性
词项，精排只能重排稠密候选窗）——反向印证词法标题加权与本体图扩展不可替代；**③**
规则路由器以一个确定性字符串信号捕获几乎全部路由收益——本 regime 的自适应检索无需
学习型路由器。拒答判定在所有配置下均不能只靠检索分（词法零分地板重叠 / BM25 反转 /
稠密低尾重叠），须结合证据覆盖判定——与 QA 层现有设计一致。

**混合检索已合入生产接口**：`POST /api/v1/knowledge/search` 新增
`retrieval_mode=hybrid`（词法/图排序与 BGE-M3 稠密排序的 RRF 融合；昇腾池嵌入），
冷启动建索引约 4 秒、热查询约 0.35 秒；嵌入通道未配置或调用失败时安全回退词法排序
并以 `mode` 字段如实标注，行为有 5 项单元测试守卫。

脚本客户端轨迹保留为机制验证口径，与真实模型轨迹分开表述，不得混写。

### 3.5 调用关系图

Agent 在平台内的真实调用关系由 `GET /api/agent/call_relationship/1` 返回，
绑定 21 个 MCP 工具（`knowledge_*`、`event_*`、`task_*`、`dashboard_*`、
`agent_*`），登记号 R-NX-04；升级到版本 4 后同一 Agent 叠加模型配置与 5 个
Skill，端到端结构见图 2：

![图 2 Agent → 5 Skill → MCP 工具面 → Oceanus API → 数据库：端到端调用关系（R-NX-04 真实返回 + R-NX-09 实测指标）](artifacts/doc-figures/fig-m2-call-graph.png)

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

执行流见图 3：

![图 3 检索-推理双驱动执行流：检索驱动与推理驱动并行汇聚 → 证据充分性判断 → 决策固化或明示拒答](artifacts/doc-figures/fig-m2-dual-drive.png)

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

本次运行的控制台实测界面见图 4、图 5：

![图 4 本地 Nexent 控制台（登录态）：已发布的治理决策智能体，可直接发起问答（R-NX-09，2026-10-24 复采）](artifacts/nexent-platform-acceptance/evidence/console-fresh-2026-10-24/01-nexent-console-qa-page-loggedin.png)

![图 5 本地 Nexent 模型配置：DeepSeek deepseek-v4-pro，健康检查通过后控制台可见（R-NX-09）](artifacts/nexent-platform-acceptance/evidence/console-fresh-2026-10-24/02-nexent-model-config-deepseek.png)

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

按时间排序的真实排障史（全部有登记产物，含失败与阻断记录）：

| 时间 | 问题 | 处理与结论 |
| --- | --- | --- |
| 2026-09-28 | Nexent 首次接入 Oceanus MCP | 完成 MCP 注册、21 工具加载、5 个 Skill 导入与一次 `knowledge_list_assets` 调用（R-NX-02） |
| 2026-09-29 | 换个入口复验同一能力 | 以本地官方源码部署内置 suadmin 复验（R-NX-03）；灌入演示数据后返回 total=4 |
| 2026-09-29 | 托管平台公网路径 | MCP 注册、21 工具加载、公网端点真实只读调用完成（R-NX-05）；导入 5 个 Skill（R-NX-07）；公网环境 Skill 绑定按钮 disabled，平台限制已留证（R-NX-06） |
| 2026-09-29 | 无 Agent，工具面无法端到端 | 创建并发布 Agent（R-NX-04，版本 v2），绑定 5 个 Skill 与 21 个工具，导出配置 ZIP；当时未配模型，完整问答列为待补 |
| 2026-09-30 | Agent 运行时被拒 | 根因：Nexent 要求 Agent `name` 为合法 Python 标识符，连字符形式不合法。改为 `seasight_governance_decision_agent` |
| 2026-09-30 | 控制台看不到 Agent | 根因：模型状态非 `available`。经官方 `/api/model/healthcheck` 后 `/api/agent/list` 返回 `is_available: true`，控制台恢复可见 |
| 2026-09-30 | 本地完整问答验收 | 发布版本 4 `v0.2.0-seasight-governance-llm`，跑通完整 Skill 问答（R-NX-09，指标见 §4.3） |
| 2026-09-30 | 托管平台私网路径受阻 | 账号欠费使“创建 Target”原生禁用（Target 0/10），Agent 启用 VPC 报 `AgentArts.03002206`（R-NX-07 `blocked`，如实登记） |
| 2026-10-24 | 托管平台 401 探测 | 账号解冻后复跑：网关与鉴权层在线但 WebSocket 握手 401，卡点收敛为控制台身份鉴权核验（R-NX-08-PROBE，如实登记） |
| 2026-10-24 | **托管平台完整问答验收** | 充值解冻 + 新建 vpc2 智能体（绕过被欠费释放的 CSMS 凭据）+ 重建 ECS TLS 模型中转 + 模型名重写，平台内跑通完整 Skill 问答：9 分钟、1933 帧、2254 字回答、证据不足如实拒答（R-NX-08 **completed**，详见 §八） |
| 2026-10-25 | **托管平台 MCP 工具面打通** | 修复两个 MCP 资产的死亡隧道端点 → 定位预览"系统异常"为运行时未注入版本 → DELETE 旧运行时后以 API Key 认证重建并同步部署 → 平台内两次问答共 6 次 MCP 真实调用（event_list 500 后自动重试成功、knowledge_search 200），ECS 服务端日志逐条对应（R-NX-10 **completed**，详见 §八） |

三条最值得写进答辩的经验：

- **平台有硬约束，必须在设计早期发现**。Nexent 的 Agent 命名规则、托管平台
  “公网环境不支持 Skill”两条限制都不是文档里一眼能看到的，是实跑撞出来的；
- **托管平台 Skill 验收必须同时满足“私网环境 + 可达 endpoint + Target 绑定”，
  缺一不可**，不能用临时隧道或 `127.0.0.1` 代替——R-NX-07 到 R-NX-08 的完整
  修复链（§八）就是这三个条件逐一补齐的过程；
- **智能体版本快照会固化保存时的 provider 配置**：改完供应商 Base_url 必须
  重存一版，否则运行时仍用旧地址——这是托管平台鉴权修好后仍超时的真实根因。

## 六、示例问答与截图索引

截图与 API 轨迹随提交包归档：界面截图在 `06_示例问答截图/`，结构化证据在
`07_证据包/`（文件名均带登记号，可逐条复核）。关键界面直接内嵌如下。

**（1）托管平台 MCP 注册与 21 工具加载（R-NX-05）**——AgentArts 控制台内
`Oceanus Domain Cognition MCP` 状态“部署成功”，工具列表 21 个只读工具：

![图 6 华为 AgentArts 托管平台：Oceanus Domain Cognition MCP 注册成功，加载 21 个只读工具（R-NX-05）](artifacts/nexent-platform-acceptance/evidence/hosted-2026-09-29-mcp-tools-21.png)

**（2）跨文档多跳检索与决策证据链（R-KN-05）**——同一问题命中 6 条，其中
3 条 hop=2；证据链覆盖 hop=0/1/2 三档、跨 6 份资产版本：

![图 7 知识域“跨文档多跳检索”：命中带“2 跳”标记与可视关系路径（R-KN-05）](artifacts/knowledge-qa-trace-multihop/01-检索结果-本体图检索与引用.png)

![图 8 决策证据链：按顺序固化证据，逐条引用资产版本，可回放（R-KN-05）](artifacts/knowledge-qa-trace-multihop/02-决策证据链-资产版本引用.png)

**（3）知识域「问答」工作台（R-KN-06）**——检索-生成回答内嵌可点击引用徽章，
证据不足时明示拒答（GLM-5.3 经 ModelArts MaaS 昇腾池生成，R-MA-01）：

![图 9 知识域“问答”工作台：接地回答带 c:n 引用徽章，点击定位证据卡（R-KN-06 / R-MA-01，真实模型）](artifacts/knowledge-qa-llm-frontend/01-接地回答-引用徽章与证据卡.png)

![图 10 证据不足时的拒答横幅：模型拒绝编造政策依据，列出证据缺口（R-KN-06 / R-MA-01）](artifacts/knowledge-qa-llm-frontend/02-证据不足拒答-banner与缺口说明.png)

其余证据的归档索引：

| 编号 | 内容 | 包内证据文件 |
| --- | --- | --- |
| R-NX-08 | 托管平台完整 Skill 问答登记（completed） | `07_证据包/R-NX-08_COMPLETED.yaml` |
| R-NX-10 | 托管平台 MCP 工具调用验收登记（completed，含根因链与诚实边界） | `07_证据包/R-NX-10_COMPLETED.yaml` + `evidence/hosted-qa-2026-10-25/`（12 张截图 + ECS 服务端日志） |
| R-KN-07 | 检索评测基准与三系统对照（306 题，id 更正后冻结快照） | `07_证据包/R-KN-07_retrieval-benchmark.yaml` + `R-KN-07_benchmark.json` + `R-KN-07_eval-results.json` |
| R-KN-08 | 本体证据可回溯审计（引用 89.9% / 关系 85.0% / 节点 96.0%） | `07_证据包/R-KN-08_audit.yaml` + `R-KN-08_audit.json` |
| R-NX-08 | 平台问答全帧记录与 2254 字答案原文 | `07_证据包/R-NX-08_ws-frames.json` |
| R-NX-09 | 完整 SSE 原始事件流 / 事件序列 / 工具轨迹 / 运行摘要 / 发布版本记录 | 证据包随开源仓库归档（`artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/`） |
| R-KN-04 | 问答轨迹 API JSON（问题 → 检索 → 决策 → 证据链，hop=0） | `07_证据包/R-KN-04_knowledge-qa-trace.json` |
| R-KN-05 | 多跳问答轨迹 API JSON（hop=0/1/2 三档证据，跨 6 份资产版本） | `07_证据包/R-KN-05_knowledge-multihop-trace.json` |
| R-KN-06 | 检索-生成问答真实模型轨迹（带引用拒答） | `07_证据包/R-KN-06_knowledge-llm-qa-trace.json` |
| R-LLM-01/02、R-MA-01 | 三模型 × 三语料评测原始产物 | `07_证据包/R-LLM-01_*、R-LLM-02_*` |

口径提醒：

- R-KN-04 是 `hop_count=0` 的**直接资产引用检索**，不是多跳路径问答，也不是
  LLM 生成式问答，不得与 R-NX-09 混写；
- R-KN-05 是确定性“检索-推理”链路（本体图检索 + 决策证据链），演示资产、
  E1/E2 证据等级，不是 LLM 生成式问答；
- R-KN-06 轨迹中脚本客户端口径仅作机制验证留存，与真实模型轨迹分开表述。

## 七、随附文件说明

| 类别 | 包内文件 | 说明 |
| --- | --- | --- |
| 完整源码包 | `04_代码附件/完整源码包_seasight.zip` | 与开源仓库（GitHub `Liiiyonx/seasight`）一致的脱敏快照，已过隐私扫描 |
| MCP 实现 | `04_代码附件/MCP与Skills源码/nexent/mcp_server/server.py` | Oceanus Domain Cognition MCP 服务实现（默认 21 只读 + 显式开关 11 写入） |
| MCP 依赖与配置 | `04_代码附件/MCP与Skills源码/nexent/mcp_server/requirements.txt`、`04_代码附件/MCP与Skills源码/nexent/.env.example` | 运行依赖与环境变量模板，不含真实密钥 |
| MCP 接入说明 | `04_代码附件/MCP与Skills源码/nexent/README.md` | 工具面、安全边界、部署方式 |
| Skills | `04_代码附件/MCP与Skills源码/nexent/skills/*/SKILL.md` | 5 个工作流模板（政策证据问答 / 事件研判 / 跨文档决策 / 工单编排 / 决策轨迹审计） |
| 本地问答登记 | `07_证据包/R-NX-09_recheck.yaml` | R-NX-09 结构化验收登记 |
| 托管平台记录 | `07_证据包/R-NX-05_hosted.yaml`、`R-NX-06_hosted-agent.yaml` | MCP 注册与 Agent/模型配置 |
| 阻断与探测记录 | `07_证据包/R-NX-07_blocked.yaml`、`R-NX-08-PROBE_2026-10-24.yaml` | 修复链中间态，如实保留 |
| 托管平台完成登记 | `07_证据包/R-NX-08_COMPLETED.yaml` + `R-NX-08_ws-frames.json` | 平台内完整 Skill 问答（§八） |
| 托管平台工具面验收 | `07_证据包/R-NX-10_COMPLETED.yaml` + `evidence/hosted-qa-2026-10-25/` | 平台内 MCP 真实调用验证（§8.1） |
| 知识库证据 | `07_证据包/R-KN-01_latest.json`、`R-KN-02_ontology-eval.json` 等 | 知识域评测产物（登记号命名） |

说明：模型密钥、MCP 令牌、后端账号与云凭据一律不随包提交。

## 八、托管平台（AgentArts）验收记录与工程攻坚

**结论先行：华为 AgentArts 托管平台内完整 Skill 问答已跑通（R-NX-08，
2026-10-24，verdict=completed）**——一次运行 9 分钟、1,933 帧、真实模型、
2,254 字回答；运行环境未加载知识库资产时，智能体全量检索后**如实声明
“引用全部 not_evaluated”**，逐节标注“非知识库依据”给出通用溢油处置框架，
拒绝编造政策依据——与本地验收（R-NX-09）的拒答行为是同一设计在托管平台的
复现。

部署拓扑见图 11：

![图 11 华为云全栈部署拓扑：AgentArts 托管智能体（VPC 私网）→ ECS TLS 模型中转 → DeepSeek API；知识域 LLM 通道 → ModelArts MaaS（昇腾池）；网关 Target 恢复为后续待办（如实标注）](artifacts/doc-figures/fig-huawei-fullstack.png)

验收要素（均有登记产物）：

| 要素 | 实测值 |
| --- | --- |
| 验收智能体 | `seasight-governance-agent-vpc2`（managed runtime，区域 cn-south-west-2） |
| 运行环境 | `environment-seasight-vpc-verify`（VPC 私网——平台内运行 Skill 的必要条件） |
| 调用通道 | Managed Agents WebSocket（官方 `managed_agents_client` 协议，API Key 认证） |
| 模型链路 | `deepseek-provider-vpc`（Base_url 指向 VPC 内中转）→ socat TLS :8080 → relay :18080（模型名重写 `deepseek-v4.1-flash`→`deepseek-chat`）→ DeepSeek 官方 API |
| 验收问题 | “连江县海漂垃圾治理中，岸基监控发现疑似漏油事件，请按照现有政策给出评估与处置建议，并给出证据链” |
| 运行结果 | 539.7 秒 / 1,933 帧 / 2,254 字回答 / 证据不足如实拒答 |

**工程攻坚链（从 blocked 到 completed，全程留证）**——这段修复史本身是
平台工程能力的证据，也是答辩素材：

1. **账号欠费**（R-NX-07，09-30）：欠费使“创建 Target”原生禁用（0/10），
   Agent 启用 VPC 报 `AgentArts.03002206` → 充值解冻；
2. **CSMS 凭据被释放**：欠费期间网关凭据被系统释放且系统身份不可改 →
   新建 vpc2 智能体绕过旧凭据；
3. **旧 ECS 系统盘被释放**：中转宿主丢失 → 重建 ECS（`ecs-6b91`）并以
   socat TLS + 模型名重写重建 VPC 内模型中转；
4. **鉴权修复后仍超时**：根因是**智能体版本快照固化了保存时的 provider 配置**，
   改完 Base_url 必须重存一版——修复后问答即通；
5. **探测 401（R-NX-08-PROBE，10-24）**：API Key 形态与历史成功记录一致但被
   服务端拒绝，卡点收敛为控制台身份核验——完成前的中间态也如实登记。

**诚实边界（R-NX-08 当次）**：该次运行中 MCP 知识域工具不可用（网关 Target 仍指向
已丢失的旧 ECS `192.168.0.65:8100`），智能体改用文件检索并如实报告证据缺口——这本身
是编排可信性的证据。工具面缺口已于次日由 R-NX-10 补齐（见下节），两次验收分别登记、
不混写。

### 8.1 MCP 工具面打通与平台内工具调用验证（R-NX-10，2026-10-25）

**结论先行：托管平台内智能体对 Oceanus Domain Cognition MCP 的真实工具调用已
端到端验证**——两次预览调试问答共 6 次 MCP 调用全部成功，平台调试抽屉调用链
与服务端（ECS）MCP 日志逐条对应；`event_list` 与 `knowledge_search` 两个不同
工具均验证。登记见 `07_证据包/R-NX-10_COMPLETED.yaml`。

两次运行实测：

| 运行 | 问题 | 调用链（平台调试抽屉） | MCP 调用明细 |
| --- | --- | --- | --- |
| 运行 1（50.26s） | “当前系统里有哪些泡沫浮球类垃圾事件？” | LLM(6.69s) → MCP(5.12s) → MCP(4.72s) → LLM(24.42s) | `event_list {"main_class":"泡沫浮球"}` 返回 [500]（后端无该分类枚举）→ 智能体感知错误后自动去除过滤重试 → 17 条事件返回（近 720 小时）→ 筛出 9 条泡沫类并给出编号/状态/坐标 |
| 运行 2（67.42s） | “泡沫浮球垃圾治理有哪些政策依据？” | LLM → MCP×2 → LLM → MCP×2 → LLM → MCP → LLM（单次 4 次 MCP 调用） | `knowledge_search` 经 `POST /api/v1/knowledge/search` 返回 200，多轮检索-推理交替 |

服务端证据（ECS `ecs-6b91`，`journalctl -u seasight-mcp`）：15:42:43–15:43:07
与 15:48:05–15:48:15 两段，`CallToolRequest`×3、`ListToolsRequest`×3，调用方
IP 为 Cloudflare 隧道入口；`GET /api/v1/events?main_class=泡沫浮球` 500、
`GET /api/v1/events?hours=720` 200、`POST /api/v1/knowledge/search` 200——
与平台侧调用链逐一对应。

![图 12 托管平台调试抽屉调用链：LLM → Oceanus Domain Cognition MCP → Oceanus Domain Cognition MCP → LLM，全部成功（R-NX-10）](artifacts/nexent-platform-acceptance/evidence/hosted-qa-2026-10-25/04-调用详情-调用链-LLM-MCP-LLM.png)

![图 13 MCP 调用真实返回：17 条事件数据（事件号/设备/坐标/分类），经运行时→隧道→ECS→Oceanus 后端全链路（R-NX-10）](artifacts/nexent-platform-acceptance/evidence/hosted-qa-2026-10-25/08-MCP调用2-输出-17条事件真实数据.png)

**根因与修复链（R-NX-08 遗留缺口的收口）**：

1. 两个 MCP 资产端点自 09-29 起指向临时 Cloudflare 快速隧道，旧隧道死亡——
   这是“工具加载成功但运行时调不通”的源头；已更新为当前活隧道并固化
   systemd 服务（`seasight-mcp-tunnel`，重启自动拉起）；
2. 旧版托管智能体编辑表单不暴露 MCP 绑定（平台绑定机制缺口，如实登记）——
   改用新版单智能体经平台 API 完成 `Oceanus Domain Cognition MCP`（21 工具）绑定；
3. 预览“系统异常，运行终止”且 ECS 零流量 → 定位为**运行时创建后未注入智能体
   版本**（API 直接部署只建空运行时），且旧运行时 IAM 认证不可改（官方文档：
   入站认证类型创建后不可改）——DELETE 后以 **API Key 认证重建运行时**并
   「更新版本 + 同步部署至实例」注入 v2 版本，预览即通。

**诚实边界（R-NX-10）**：验收走预览调试通道（studio 会话），非生产 API 通道；
该运行时类型的 WS 数据面通道握手 500（平台 node-proxy 层，已留证），
`sessions-start` HTTP 通道实测 200；`event_list` 首次调用的 500 为后端分类
枚举校验，智能体重试行为本身构成编排韧性证据；写入类工具未启用。

## 九、诚实边界与不可宣称项

- 感知精度 `not_evaluated`；`76%` 仅指时序链路误报抑制率；
- 演示数据（total=4）不等于真实脱敏行业数据集；公开开放数据替代评测
  （R-OD-01，8 份生态环境部公开通知）也只是 E1 替代证据，不代表领域准确率；
- R-KN-04 为 `hop=0` 直接引用检索；跨文档多跳实例由 R-KN-05 补齐
  （hop=0/1/2 三档证据、演示资产、E1/E2），两者均非 LLM 生成式问答；
- “已跑通完整 Skill 问答”指**本地官方源码部署（R-NX-09）与华为 AgentArts
  托管平台（R-NX-08）两次独立验收均已完成**；R-NX-08 当次运行 MCP 工具不可用
  为如实登记的历史中间态，工具面已于 R-NX-10（2026-10-25）恢复并完成平台内
  真实工具调用验证（§8.1），两次验收分别登记、不混写；R-NX-10 为预览调试
  通道验收，WS 数据面通道在该运行时类型上未通（已留证），不得写成
  “生产 API 全通道验收”；
- 本体抽取评测（R-KN-02）、增量维护对比（R-KN-03）、多行业迁移（R-MG-01）
  均为 E1 级软件内部或演示级结果，不表述为真实行业效果；
- ModelArts MaaS 评测（R-MA-01）为共享推理端点按 token 计费的真实推理，
  语料为合成与真实公开文本，不代表生产 SLA。

## 十、变更记录

| 日期 | 变更 | 操作人 |
| --- | --- | --- |
| 2026-10-26 | **R-KN-07 v3**：标题加权嵌入上生产（混合标题型 hit@3/5 93.8%/100%）；规则路由器实验（显著优于全部单一系统、≈逐题型 oracle）；材料同步（§3.4） | liyongxiang + ZCode |
| 2026-10-26 | **检索与本体定量化（R-KN-07/08）**：公开语料 8→20 份（27 资产）、本体 100 节点/200 关系；本体证据可回溯审计（引用 89.9%/关系 85%/节点 96%）；306 题三系统检索评测（RRF 混合标题型 hit@1 81.5%，+57% 相对提升）并合入生产接口 `retrieval_mode=hybrid`（§3.4） | liyongxiang + ZCode |
| 2026-10-26 | **R-KN-07 id 冲突更正**：发现基准题 id 不唯一（306 题仅 22 个唯一 id）致逐题分析被污染，修复 builder 并全量重跑——更正后数字普遍大幅提升（更正说明 ID_COLLISION_CORRECTION_20261026.md 随证据包），本表以上数字均为更正后口径 | liyongxiang + ZCode |
| 2026-10-25 | **R-NX-10 完成**：托管平台内 MCP 工具面真实调用验证（event_list 500 后自动重试成功 + knowledge_search 200，两次运行 6 次 MCP 调用、ECS 服务端日志逐条对应）；§8.1 新增、§五时间线/§六证据索引/§九诚实边界同步更新 | liyongxiang + ZCode |
| 2026-10-25 | **国奖打磨版 1.1**：①对齐 R-NX-08 完成后的全文档口径（§一状态表、§八整节重写为验收记录+工程攻坚、§九边界重写，消除 v1.0 中“托管平台 blocked”的旧表述残留）；②内嵌 11 张图（知识域管线/调用关系/双驱动执行流/华为云全栈拓扑 4 张示意图 + 控制台/多跳/证据链/问答工作台等 7 张实测截图）；③§五调试经验按时间重排并补 R-NX-08 攻坚链；④§六/§七证据路径全部对齐提交包结构（06_示例问答截图 / 07_证据包 / 04_代码附件）；⑤封面口径与编制日期刷新 | liyongxiang + ZCode |
| 2026-10-24 | §3.4 增 R-MA-01：知识域 LLM 通道切换至 ModelArts MaaS(昇腾池)完成真实推理评测 | liyongxiang + ZCode |
| 2026-10-24 | 知识域「问答」前端工作台上线（[c:n] 引用徽章可点、证据卡、拒答横幅）；真实模型实测两景截图入包 | liyongxiang + ZCode |
| 2026-10-24 | **R-NX-08 完成**：托管平台内完整 Skill 问答跑通（vpc2 智能体 + VPC TLS 模型中转 + 模型名重写 + 真实拒答答案 2254 字） | liyongxiang + ZCode |
| 2026-10-24 | §3.4 增 R-LLM-02：真实公开政务文本双通道行为对照（LLM 关系 100% 带类型与引用，抽出法规术语） | liyongxiang + ZCode |
| 2026-10-24 | §3.4/§六 升级为真模型口径：R-LLM-01 real 双通道对照评测（含负结果）与 R-KN-06 real 真实模型问答轨迹（DeepSeek `deepseek-chat`） | liyongxiang + ZCode |
| 2026-09-30 | 建立「材料 2」独立提交件底稿：整体设计思路、Agent 配置完整细节、Skill 分层编排、调试迭代经验、示例问答截图索引、随附文件说明、托管平台状态与恢复路径、诚实边界 | WP-15 |
