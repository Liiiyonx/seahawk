# 探海灵眸 Oceanus · 赛道三随附文件说明

> 版本：1.2（国奖打磨版）
> 编制日期：2026-10-25
> 用途：华为 ICT 大赛 创新赛道三【材料 3】——与开发设计文档、智能体设计说明
> 同步提交的 json 文件、知识库文件与 MCP 代码附件说明。
> 配套：本文与 `01_开发设计文档.docx`、`02_智能体设计说明.docx` 同包提交。

## 〇、快速导航（评审建议阅读顺序）

1. **先看本文件**——了解随附文件分组、证据登记号与包内文件对照
2. `07_证据包/R-NX-08_COMPLETED.yaml`——华为托管平台完整问答（最强证据）
3. `07_证据包/R-KN-06_*`、`R-LLM-01/02_*`——检索-生成问答与三模型评测（含昇腾池）
4. `06_示例问答截图/`——8 张按登记号命名的界面证据
5. `04_代码附件/`——完整源码包（zip）+ MCP/Skills 明文源码
6. 需要复现：见源码包内 README 快速开始；证据登记规则见 `docs/evidence-claim-policy.md`

## 一、随附文件总览

随附文件分成五类：**完整源码包、MCP 实现、Skill 工作流模板、Agent 配置与平台
验收证据、知识库与评测证据**。每类都标注了证据等级与适用边界，避免评审把
演示级结果读成真实行业效果。

证据等级沿用项目内部纪律：E0 规划 / E1 软件内部或本地验证 / E2 合成或演示
环境 / E3 真实业务方参与 / E4 真实运营。

| 类别 | 位置 | 证据等级 |
| --- | --- | --- |
| 完整源码包 | `04_代码附件/完整源码包_seasight.zip`（427 个文件，与开源仓库一致） | 开源可复现 |
| MCP 实现 | `04_代码附件/MCP与Skills源码/nexent/mcp_server/` | E1（代码可运行、已复验） |
| Skill 模板 | `04_代码附件/MCP与Skills源码/nexent/skills/*/SKILL.md`（5 个） | E1（本地与托管平台均已导入并真实调用） |
| Agent 配置与平台验收 | `07_证据包/`（按登记号命名） | E1（本地）/ E1（托管平台，R-NX-08） |
| 知识库与评测 | `07_证据包/`（按登记号命名） | E1（软件内部评测） |

## 二、完整代码附件（官方模板必选项）

| 文件/目录 | 说明 |
| --- | --- |
| `04_代码附件/完整源码包_seasight.zip` | 与开源仓库 `github.com/Liiiyonx/seasight` 完全一致的脱敏快照（427 个文件；源码与配置 327 个文件 / 约 11.9 万行），开源前已通过隐私扫描（本机路径、密钥、内部证据零残留） |
| `04_代码附件/MCP与Skills源码/nexent/` | MCP 服务端、依赖、环境变量模板、接入说明与 5 个 SKILL.md 的明文目录，评审无需解压即可直接阅读 |

仓库不含模型密钥、MCP 令牌、后端密码与云账号 AK/SK；`.env.example` 仅为占位
模板。

## 三、MCP 相关文件

| 文件 | 类型 | 说明 |
| --- | --- | --- |
| `04_代码附件/MCP与Skills源码/nexent/mcp_server/server.py` | 源码 | Oceanus Domain Cognition MCP 服务实现。默认注册 21 个只读工具；开启 `SEASIGHT_MCP_ALLOW_WRITES=true` 后才注册写入工具（合计 32 个）。入站 Bearer 鉴权 fail-closed，出站调用 Oceanus `/api/v1` |
| `04_代码附件/MCP与Skills源码/nexent/mcp_server/requirements.txt` | 依赖 | MCP 服务运行依赖 |
| `04_代码附件/MCP与Skills源码/nexent/.env.example` | 配置模板 | 环境变量模板，**不含真实密钥**；密钥与令牌由部署方在平台侧配置 |
| `04_代码附件/MCP与Skills源码/nexent/README.md` | 文档 | 工具面清单、安全边界、本地与容器部署方式 |

工具面分组（只读，21 个）：

| 组 | 工具 |
| --- | --- |
| 资产 | `knowledge_list_assets`、`knowledge_asset_detail` |
| 本体 | `knowledge_list_ontology_versions`、`knowledge_ontology_version_detail`、`knowledge_list_ontology_nodes`、`knowledge_list_ontology_relations` |
| 检索 | `knowledge_search` |
| 决策 | `knowledge_list_decisions`、`knowledge_decision_evidence` |
| 业务 | `event_get`、`event_list`、`task_get`、`task_list`、`task_ack_history`、`dashboard_get` |
| Agent 审计 | `agent_runtime_status`、`agent_list_runs`、`agent_run_detail`、`agent_run_steps`、`agent_list_tools`、`agent_list_approvals` |

写入工具（11 个，本次验收**未启用**）：资产登记与版本追加、本体版本创建 /
抽取 / 审核 / 发布、决策创建、Agent 运行控制与审批。

## 四、Skill 工作流模板

`04_代码附件/MCP与Skills源码/nexent/skills/` 下 5 个模板，每个定义触发条件、
工具顺序、停止条件与输出要求：

| Skill | 用途 | 本次完整问答是否被触发 |
| --- | --- | --- |
| `policy-evidence-qa` | 用可引用资产版本回答政策问题 | 是 |
| `marine-event-assessment` | 评估事件与对应治理依据 | 是 |
| `cross-document-decision` | 本体引导的跨文档多跳推理 | **否**（已绑定，该问题未触发） |
| `dispatch-work-order-orchestration` | 协调事件、Agent 运行、审批与工单检查，不绑定机器人厂商 | 是 |
| `decision-trace-audit` | 核对决策是否可追溯到证据与执行步骤 | 是 |

口径提醒：Agent 共**绑定 5 个** Skill，本地示例问题经 `read_skill_md` **实际
加载 4 个**，`cross-document-decision` 未被触发。对外只写“绑定 5 个、本次触发
4 个”，不写成“5 个 Skill 全部验证通过”。华为托管平台侧同一套 5 个 Skill
已随 vpc2 智能体验收（R-NX-08）。

## 五、Agent 配置与平台验收证据

### 5.1 登记号 → 包内文件对照（07_证据包/，23 个文件全部按登记号命名）

| 登记号 | 包内文件 | 内容 |
| --- | --- | --- |
| R-NX-03 | `R-NX-03_recheck.yaml` | 本地官方源码部署复验（suadmin 入口，total=4） |
| R-NX-04 | `R-NX-04_agent-create.yaml` | Agent 创建/发布/绑定 5 Skill + 21 工具/调用关系/配置导出 |
| R-NX-05 | `R-NX-05_hosted.yaml` | 托管平台 MCP 注册“部署成功”、21 工具、公网端点真实只读调用 |
| R-NX-06 | `R-NX-06_hosted-agent.yaml` | 托管平台 Agent 创建与 DeepSeek 模型配置（公网 Skill 限制留证） |
| R-NX-07 | `R-NX-07_blocked.yaml` | 历史阻断记录（账号欠费致 Target 禁用）——修复链中间态，如实保留 |
| R-NX-08-PROBE | `R-NX-08-PROBE_2026-10-24.yaml` | 复跑探测（握手 401，卡点收敛为鉴权核验）——中间态，如实保留 |
| **R-NX-08** | `R-NX-08_COMPLETED.yaml` + `R-NX-08_ws-frames.json` | **托管平台完整 Skill 问答已完成**（9 分钟 1933 帧、真实模型、证据不足如实拒答；含完整修复链） |
| R-NX-09 | `R-NX-09_recheck.yaml` | 本地官方源码部署完整 LLM Skill 问答（8 步 31 次工具调用、2777 字回答） |
| R-KN-01~03 | `R-KN-01_latest.json`、`R-KN-02_ontology-eval.json`、`R-KN-03_incremental-eval.json` | 知识进化闭环 / 本体抽取确定性评测 / 增量维护对比（省 63.19%） |
| R-KN-04 | `R-KN-04_knowledge-qa-trace.json` | 知识域问答轨迹（hop=0 直接引用） |
| R-KN-05 | `R-KN-05_knowledge-multihop-trace.json` | 跨文档多跳实例（hop=0/1/2 三档、跨 6 份资产版本） |
| R-KN-06 | `R-KN-06_knowledge-llm-qa-trace.json` | 检索-生成问答真实模型轨迹（带引用拒答） |
| R-LLM-01/02 | `R-LLM-01_ontology-llm-eval.json`、`R-LLM-02_open-data-llm-channel-eval.json` | 双通道真模型评测 / 真实公开政务文本对照 |
| R-MG-01 | `R-MG-01_skill-migration.json` | 三领域 Skill 迁移验证 |
| R-OD-01~03 | `R-OD-01_open-data-eval.json`、`R-OD-02_open-data-e2e.json`、`R-OD-03_knowledge-e2e-trace.json`、`R-OD-03_real-industry-dataset.json` | 公开数据替代评测 / 真实公开语料端到端 / NOAA 真实行业监测数据接入（22,530 行） |

界面截图在 `06_示例问答截图/`（8 张，按登记号命名）：R-NX-09 控制台 ×2、
R-KN-04 检索与证据链 ×2、R-KN-05 多跳与证据链 ×2、R-KN-06 问答工作台接地
回答与拒答 ×2。本地问答的完整 SSE 事件流、工具轨迹与发布记录随开源仓库归档
（`artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/`，见源码包）。

### 5.2 口径提醒（重要）

**本地（R-NX-09）与华为 AgentArts 托管平台（R-NX-08）是两次独立验收，均已完成
完整 Skill 问答**，证据分别登记、不得互相替代。R-NX-08 的诚实边界：本次运行中
MCP 知识域工具不可用（网关 Target 指向已丢失的旧 ECS），智能体改用文件检索并
如实报告证据缺口；恢复 Target 后复跑补工具调用轨迹为后续待办，不影响
“平台内完整 Skill 问答已验收”的口径。R-NX-05/06/07/08-PROBE 为其前置步骤与
修复链中间态，按时间序阅读即可看到完整的工程攻坚过程。

### 5.3 知识库与评测证据边界

| 登记号 | 边界 |
| --- | --- |
| R-KN-01~03 | 演示数据 / E1 软件内部，非领域准确率 |
| R-KN-04 | `hop_count=0` 直接引用检索，非多跳、非 LLM 生成 |
| R-KN-05 | 确定性检索-推理链路，演示资产，E1/E2；非 LLM 生成式问答 |
| R-KN-06 | 真实模型生成，演示语料（E1）；脚本轨迹与真实轨迹分开 |
| R-OD-01 | 公开开放数据替代评测，**非真实脱敏行业数据** |
| R-OD-02 | 真实**公开**政务语料端到端（公开 ≠ 脱敏行业内部数据）；不构成领域准确率 |
| R-OD-03 | NOAA NCEI 全球公开数据集（22,530 行，逐条带 DOI），**非脱敏企业内部数据、不含中国大陆点位**；不用于说明治理效果或识别精度 |
| R-MG-01 | E1 演示级三领域迁移，非真实行业配置 |
| R-LLM-01/02、R-MA-01 | 真模型评测含如实负结果；语料为合成与真实公开文本；MaaS 共享端点不代表生产 SLA |

### 5.4 演示视频

| 文件 | 说明 | 边界 |
| --- | --- | --- |
| `08_演示视频/探海灵眸Oceanus_演示视频.mp4` | 系统操作演示录屏（2026-10-24 重录版，1080p，4 分 39 秒）：登录 → 大屏 → 事件 → 工单 → 知识域 → 派单闭环 | 项目自产演示材料；演示环境为演示数据，不构成现场部署或真实海域验证；不含未公开凭证 |

### 5.5 标准映射

`05_标准映射表.md`：`standard_codes` 到规范名称、条款、来源状态的映射表；
未取得原文的规范标注“待获取真实规范条款”，不为演示资产伪造标准条文。

## 六、提交前自检

- [x] `python scripts/check_claims.py --root .` 退出码 0（宣称纪律门禁）；
- [x] 公开仓库隐私扫描通过（源码包与 GitHub `Liiiyonx/seasight` 完全一致）；
- [x] 材料中不出现未脱敏真实数据、真实联系方式与未公开证据；
- [x] 模型密钥、MCP 令牌、后端账号、云账号 AK/SK 一律不入包；
- [x] 托管平台完整 Skill 问答已完成（R-NX-08，2026-10-24，verdict=completed），
      材料 1/2/3 口径一致：本地与托管平台双端验收、两次独立登记、不混写；
      R-NX-08 运行中 MCP 工具面不可用的边界在材料 2 §八如实标注；
- [x] 公开开放数据替代评测（R-OD-01）标注“非真实脱敏行业数据”；
- [x] Skill 口径为“绑定 5 个、本地示例问题触发 4 个”；
- [x] 感知精度保持 `not_evaluated`，`76%` 标注为时序链路误报抑制率。

## 七、变更记录

| 日期 | 变更 | 操作人 |
| --- | --- | --- |
| 2026-10-25 | **v1.2 国奖打磨版**：①§〇/§一/§五 导航与路径全部对齐提交包新结构（04_代码附件 / 06_示例问答截图 / 07_证据包 / 08_演示视频）；②新增§二完整代码附件说明（zip 与开源仓库一致）与§5.1 登记号→包内文件对照表；③§5.2 口径提醒改为“双端均已完成”（消除 v1.1 与 R-NX-08 完成状态矛盾的残留）；④§六自检逐项落勾并附口径说明 | liyongxiang + ZCode |
| 2026-10-23 | 新增 R-KN-05 跨文档多跳实例与演示视频说明 | liyongxiang |
| 2026-09-30 | 建立【材料 3】独立《随附文件说明》提交件 | WP-15 |
