# 探海灵眸 SeaSight · 赛道三随附文件说明

> 版本：1.0（提交件底稿）
> 编制日期：2026-09-30
> 用途：华为 ICT 大赛 创新赛道三【材料 3】——与开发设计文档、智能体设计说明
> 同步提交的 json 文件、知识库文件与 MCP 文件说明。
> 上位口径：《docs/competitions/huawei-ict-track3-submission-checklist.md》、
> 《docs/competitions/huawei-ict-track3-scoring-review.md》
> 配套：本文与 `01_开发设计文档.docx`、`02_Nexent智能体设计说明.docx` 同包提交。

## 一、随附文件总览

随附文件分成四类：**MCP 实现**、**Skill 工作流模板**、**Agent 配置与平台验收证据**、
**知识库与评测证据**。每类都标注了证据等级与适用边界，避免评审把演示级结果读成
真实行业效果。

证据等级沿用项目内部纪律：E0 规划 / E1 软件内部或本地验证 / E2 合成或演示环境 /
E3 真实业务方参与 / E4 真实运营。

| 类别 | 文件数 | 目录 | 证据等级 |
| --- | --- | --- | --- |
| MCP 实现 | 4 | `integrations/nexent/mcp_server/` | E1（代码可运行、已复验） |
| Skill 模板 | 5 | `integrations/nexent/skills/*/SKILL.md` | E1（平台内已导入并真实调用） |
| Agent 配置与平台验收 | 14 | `artifacts/nexent-platform-acceptance/` | E1（本地部署）/ E2（托管平台公网路径） |
| 知识库与评测 | 12 | `artifacts/` 下各证据目录 | E1（软件内部评测） |

## 二、MCP 相关文件

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `integrations/nexent/mcp_server/server.py` | 源码 | SeaSight Domain Cognition MCP 服务实现。默认注册 21 个只读工具；开启 `SEASIGHT_MCP_ALLOW_WRITES=true` 后才注册写入工具（合计 32 个）。入站 Bearer 鉴权 fail-closed，出站调用 SeaSight `/api/v1` |
| `integrations/nexent/mcp_server/requirements.txt` | 依赖 | MCP 服务运行依赖 |
| `integrations/nexent/.env.example` | 配置模板 | 环境变量模板，**不含真实密钥**；密钥与令牌由部署方在平台侧配置 |
| `integrations/nexent/README.md` | 文档 | 工具面清单、安全边界、本地与容器部署方式 |
| `artifacts/nexent-mcp-openapi.json` | 接口描述 | MCP 工具的接口定义，供平台导入与评审核对工具签名 |

工具面分组（只读，21 个）：

| 组 | 工具 |
| --- | --- |
| 资产 | `knowledge_list_assets`、`knowledge_asset_detail` |
| 本体 | `knowledge_list_ontology_versions`、`knowledge_ontology_version_detail`、`knowledge_list_ontology_nodes`、`knowledge_list_ontology_relations` |
| 检索 | `knowledge_search` |
| 决策 | `knowledge_list_decisions`、`knowledge_decision_evidence` |
| 业务 | `event_get`、`event_list`、`task_get`、`task_list`、`task_ack_history`、`dashboard_get` |
| Agent 审计 | `agent_runtime_status`、`agent_list_runs`、`agent_run_detail`、`agent_run_steps`、`agent_list_tools`、`agent_list_approvals` |

写入工具（11 个，本次验收**未启用**）：资产登记与版本追加、本体版本创建 / 抽取 /
审核 / 发布、决策创建、Agent 运行控制与审批。

## 三、Skill 工作流模板

`integrations/nexent/skills/` 下 5 个模板，每个定义触发条件、工具顺序、停止条件与
输出要求：

| Skill | 用途 | 本次完整问答是否被触发 |
| --- | --- | --- |
| `policy-evidence-qa` | 用可引用资产版本回答政策问题 | 是 |
| `marine-event-assessment` | 评估事件与对应治理依据 | 是 |
| `cross-document-decision` | 本体引导的跨文档多跳推理 | **否**（已绑定，该问题未触发） |
| `dispatch-work-order-orchestration` | 协调事件、Agent 运行、审批与工单检查，不绑定机器人厂商 | 是 |
| `decision-trace-audit` | 核对决策是否可追溯到证据与执行步骤 | 是 |

口径提醒：Agent 共**绑定 5 个** Skill，本次问题经 `read_skill_md` **实际加载 4 个**，
`cross-document-decision` 未被触发。对外只写“绑定 5 个、本次触发 4 个”，不写成
“5 个 Skill 全部验证通过”。

## 四、Agent 配置与平台验收证据

### 4.1 Agent 配置与调用关系

| 文件 | 登记号 | 说明 |
| --- | --- | --- |
| `artifacts/nexent-platform-acceptance/agent-create-2026-09-29.yaml` | R-NX-04 | Agent 创建、发布、绑定 5 Skill 与 21 MCP 工具、调用关系 API 返回、配置导出 |
| `artifacts/nexent-platform-acceptance/evidence/agent-run-export.zip` | R-NX-04 | Agent 配置与绑定 Skills 导出物 |
| `artifacts/nexent-platform-acceptance/evidence/agent-run-*.json` | R-NX-04 | Agent 创建、绑定、发布、版本、调用关系接口真实返回 |

### 4.2 本地官方源码部署 Nexent 验收（R-NX-09）

| 文件 | 说明 |
| --- | --- |
| `.../recheck-2026-09-30-llm-qa.yaml` | 结构化验收登记：平台版本、账号、Agent、模型、绑定、问答指标、诚实边界 |
| `.../evidence/llm-qa-2026-09-30/agent-run-sse.txt` | 完整 SSE 原始事件流（约 1.58 MB），可直接复核 |
| `.../evidence/llm-qa-2026-09-30/agent-run-events.json` | 解析后事件序列（13,204 事件） |
| `.../evidence/llm-qa-2026-09-30/agent-run-tools.json` | 工具调用轨迹（31 次调用、13 个唯一工具） |
| `.../evidence/llm-qa-2026-09-30/agent-run-summary.json` | 运行摘要（8 步、最终回答） |
| `.../evidence/llm-qa-2026-09-30/agent-publish.json`、`agent-versions.json` | 发布版本 4 `v0.2.0-seasight-governance-llm` 与版本列表 |
| `.../evidence/llm-qa-2026-09-30/nexent-console-home.png`、`nexent-console-newchat.png` | 控制台内 Agent 可见性与新建对话界面截图 |
| `artifacts/nexent-platform-acceptance/probe-agent-llm-qa.cjs` | 复现脚本（可重跑同一次问答） |

### 4.3 华为 AgentArts 托管平台证据（R-NX-05 / R-NX-06 / R-NX-07）

| 文件 | 登记号 | 说明 |
| --- | --- | --- |
| `.../hosted-2026-09-29.yaml` | R-NX-05 | MCP 服务注册“部署成功”、21 工具加载、公网端点 `knowledge_list_assets` 真实只读调用返回 total=4 |
| `.../evidence/hosted-2026-09-29-mcp-tools-21.png/json` | R-NX-05 | 托管平台 MCP 详情页 21 工具清单 |
| `.../evidence/hosted-2026-09-29-tunnel-tools.json`、`hosted-2026-09-29-tool-call.json` | R-NX-05 | MCP 初始化、工具列表与真实只读调用返回 |
| `.../hosted-agent-2026-09-29.yaml` | R-NX-06 | 托管平台 Agent 创建、DeepSeek 模型配置、公网环境 Skill 绑定受限留证 |
| `.../hosted-2026-09-30-target-blocked.yaml` | R-NX-07 `blocked` | 私网环境与网关已建；账号欠费使“创建 Target”禁用（Target 0/10）；Agent 启用 VPC 报 `AgentArts.03002206`；`live_skill_qa_completed: false` |
| `.../evidence/hosted-2026-09-30-private-gateway-target-blocked.png` | R-NX-07 | 私网网关 Target 禁用界面截图 |
| `artifacts/nexent-platform-acceptance/hosted-skill-qa.template.yaml` | R-NX-08 | 托管平台内完整 Skill 问答完成后的登记模板（留空待填） |
| `docs/competitions/huawei-agentarts-vpc-target-runbook.md` | R-NX-08 | 解除欠费后的执行手册 |

**口径提醒**：托管平台侧目前只完成“MCP 注册 + 工具加载 + 公网端点只读调用 + Agent
与模型配置 + Skill 导入 + 私网环境与网关创建”，**平台内完整 Skill 问答未跑通**。
不得把公网隧道只读调用、本地验收或准备手册写成托管平台平台内验收。

### 4.4 知识库与评测证据

| 文件 | 登记号 | 说明 | 边界 |
| --- | --- | --- | --- |
| `artifacts/evolution-demo/latest.json` | R-KN-01 | 知识进化闭环完整请求/响应：2 资产、4 版本、60 候选、图谱多跳检索 4 命中、决策证据 4 条 | 演示数据 |
| `artifacts/ontology-eval/latest.json` | R-KN-02 | 本体候选抽取确定性评测 | E1 软件内部，非领域准确率 |
| `artifacts/ontology-eval/incremental-latest.json` | R-KN-03 | 本体全量重抽 vs 增量追加对比（节省 66.8%） | E1 相对对比 |
| `artifacts/knowledge-qa-trace/latest.json` | R-KN-04 | 示例问答轨迹（问题 → 检索 → 决策 → 证据链） | `hop_count=0` 直接引用检索，非多跳、非 LLM 生成 |
| `artifacts/knowledge-qa-trace/01-检索结果-本体图检索与引用.png`、`02-决策证据链-资产版本引用.png` | R-KN-04 | 知识域前端界面截图 | 同上 |
| `artifacts/open-data-eval/latest.json`、`corpus/manifest.json` | R-OD-01 | 8 份生态环境部公开通知的本体抽取评测，来源 URL 与 SHA256 可追溯 | E1 替代证据，**非真实脱敏行业数据** |
| `artifacts/skill-migration/evidence/latest.json`、`skill-migration-mapping.md` | R-MG-01 | 海洋 / 医疗 / 政务三领域模板迁移，检索命中 3/3 | E1 演示级，非真实行业配置 |
| `docs/competitions/standard-code-mapping.md` | — | `standard_codes` 到规范名称、条款、来源状态的映射表 | 未取得原文的规范标注“待获取真实规范条款” |

## 五、提交前自检

- [ ] `python scripts/check_claims.py --root .` 退出码 0；
- [ ] 公开仓库隐私扫描通过（若提交到 GitCode/GitHub）；
- [ ] 材料中不出现未脱敏真实数据、真实联系方式与未公开证据；
- [ ] 模型密钥、MCP 令牌、后端账号、云账号 AK/SK 一律不入包；
- [ ] 托管平台完整 Skill 问答未完成时，材料明确写“托管平台完整 Skill 问答待私网环境 + 私网可访问 MCP endpoint 就绪后补充”（公网环境不支持 Skill）；
- [ ] 公开开放数据替代评测（R-OD-01）标注“非真实脱敏行业数据”；
- [ ] Skill 口径为“绑定 5 个、本次触发 4 个”；
- [ ] 感知精度保持 `not_evaluated`，`76%` 标注为时序链路误报抑制率。

## 六、变更记录

| 日期 | 变更 | 操作人 |
| --- | --- | --- |
| 2026-09-30 | 建立【材料 3】独立《随附文件说明》提交件：MCP / Skill / Agent 配置与平台验收 / 知识库与评测四类随附文件逐项说明、证据等级与适用边界、提交前自检清单 | WP-15 |
