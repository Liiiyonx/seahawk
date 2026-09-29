# 华为 ICT 大赛 创新赛道三 · 官方赛题对照与行动清单

> 版本：1.3 ｜ 日期：2026-09-30
> 上位口径：《docs/evidence-claim-policy.md》（证据分级与宣称纪律）、
> 《docs/competitions/huawei-nexent.md》（Nexent 赛题适配说明）
> 恢复执行手册：《docs/competitions/huawei-agentarts-vpc-target-runbook.md》
> 配套门禁：`python scripts/check_claims.py --root .`（必须退出码 0）

## 一、官方赛题要点（2026 赛道三）

赛题要求参赛队伍构建**领域资产认知智能体**，核心条目如下：

1. 面向医疗、金融、制造、政务任一或多个行业场景，搭建多模态异构数据资产认知智能体，实现对文本、表格、图文等多元行业数据的统一识别、理解与资产标识。
2. 设计低资源场景下领域知识图谱本体半自动化构建方案，实现本体持续动态更新，并支持与对应行业规范、标准体系对齐。
3. 深度集成 Nexent 的 MCP 协议与 Skills 编排能力，打造“检索-推理”双驱动协同智能体执行流。
4. 挖掘行业沉睡存量数据资产，实现跨文档多跳知识推理、决策链路可溯源；提炼通用业务逻辑，沉淀可复用、可快速部署的 Skill 工作流模板。
5. 智能体基于 Nexent 平台可运行。

**分享要求**：入围中国总决赛的作品需开源至 GitCode 或 GitHub。

**开发资料**：Nexent 可自行下载至本地开发，官方代码仓为
<https://github.com/ModelEngine-Group/nexent>（GitHub）与
<https://gitcode.com/ModelEngine/nexent>（GitCode）；官方文档见
<https://modelengine-group.github.io/nexent/zh/user-guide/home-page.html>。

**算力支持**：中国总决赛为每支队伍提供一卡华为云算力资源支持，使用代金券购买，
供 MCP 等自定义部署使用。

## 二、本项目落位：政务-海洋环境治理

赛题允许从医疗、金融、制造、政务中选择一个或多个行业。本项目面向**政务-县域海洋
环境治理**，是政府侧的“感知—决策—执行”治理决策智能体，不是纯海漂垃圾识别：

- 岸基摄像头等感知数据进入资产登记与事件链路；
- 政策、标准、监测报告等文本与表格资产进入知识域；
- 跨文档多跳检索支撑治理决策；
- 决策轨迹、审批、派单与执行回执全程可溯源；
- 机器人是可替换的 MQTT 执行端，Nexent 适配层不依赖机器人。

## 三、逐条对照表

| 官方要求 | 本项目现状 | 证据位置 | 状态 |
| --- | --- | --- | --- |
| 多模态异构数据统一识别、理解与资产标识 | 支持 document、table、image、event、telemetry、dataset 六类资产；资产身份稳定、内容按版本追加并记录哈希；感知识别当前为 OpenCV 传统视觉冷启动，精度保持 `not_evaluated` | `backend/app/models/knowledge.py`、`backend/app/services/knowledge.py` | 实线 |
| 低资源本体半自动构建与持续动态更新 | 从指定资产版本抽取候选节点与关系；候选默认未审核；新资产版本进入新一轮候选抽取，经人工审核后发布新本体版本；节点与本体版本保留 `standard_codes` 实现标准体系对齐 | `KnowledgeService.extract_ontology`、`backend/app/api/v1/knowledge.py` | 实线，持续更新需用演示证据展示 |
| 与行业规范、标准体系对齐 | 资产与本体版本可携带 `standard_codes`，检索可按标准码过滤 | `backend/app/services/knowledge.py` | 实线 |
| 深度集成 Nexent MCP 与 Skills | 默认注册 21 个只读工具，开启写入开关后共 32 个；5 个 Skills 工作流模板；协议级验收已通过；本地 Agent 绑定 21 工具 + 5 Skill 并跑通完整 LLM 问答（一次运行调用 13 个唯一工具） | `integrations/nexent/`、`artifacts/nexent-acceptance/latest.json`、`artifacts/nexent-platform-acceptance/recheck-2026-09-30-llm-qa.yaml` | 实线（协议级 + 本地 Nexent 端到端） |
| 检索-推理双驱动 | 已发布本体存在时执行带路径的多跳检索；无可用本体时明确回退普通资产检索，返回 `mode` 与引用 | `KnowledgeService.search` | 实线 |
| 跨文档多跳推理与决策链路可溯源 | 检索结果携带资产版本、节点、关系、跳数与片段；决策按顺序固化证据 | `KnowledgeService.create_decision`、`/knowledge/decisions/{id}/evidence` | 实线 |
| 可复用 Skill 工作流模板 | 政策证据问答、事件研判、跨文档决策、工单编排、决策轨迹审计 | `integrations/nexent/skills/` | 实线 |
| 智能体基于 Nexent 可运行 | 标准 MCP 工具面 + Skills 模板已就绪；本机 Nexent v2.6.1 完成注册、工具面加载与调用；2026-09-30 在本地官方源码部署中接入 DeepSeek `deepseek-v4-pro`，跑通完整 LLM Skill 问答 | `integrations/nexent/`、`artifacts/nexent-platform-acceptance/`、`recheck-2026-09-30-llm-qa.yaml` | **本地已完成（R-NX-09，2026-09-30）；华为托管平台内完整问答仍为 R-NX-07 blocked，持续维护中** |
| 开源至 GitCode/GitHub | 仓库已带 MIT LICENSE；README 已存在；需要公开前完成密钥与隐私检查 | `LICENSE`、`README.md` | **待开源发布** |

## 四、平台侧验收的两条免费/低成本路线

### 路线 A：本地 Nexent 自建（官方允许，平台软件免费）

官方明确可自行下载 Nexent 至本地开发。自建要求来自官方 README：

- Docker 24+ 与 Docker Compose v2+；
- 最低 4 核 CPU、8 GiB 内存、40 GiB 磁盘（推荐 8 核、16 GiB、100 GiB）；
- x86_64 / ARM64 均可。

标准命令：

```bash
git clone https://github.com/ModelEngine-Group/nexent.git
cd nexent
bash deploy.sh docker
```

部署完成后，在 Nexent 中注册 SeaSight MCP：

```text
名称：SeaSight Domain Cognition MCP
传输：streamable-http（本地自建可改用 stdio）
URL：http://host.docker.internal:8100/mcp
Header：Authorization: Bearer <SEASIGHT_MCP_SERVER_TOKEN>
```

随后导入 `integrations/nexent/skills/` 下 5 个 `SKILL.md`，并由 Nexent 侧发起一次
只读 MCP 工具调用（例如 `knowledge_list_assets` 或 `policy-evidence-qa` Skill），
留存截图与轨迹，填写 `artifacts/nexent-platform-acceptance/latest.yaml`。

**本机现状（2026-09-28）**：已在本地 Nexent v2.6.1 完成平台侧验收：注册 SeaSight MCP、加载 21 个只读工具、导入 5 个 Skills，并以 `nexent_viewer` 调用 `knowledge_list_assets` 返回 200。证据与截图见 `artifacts/nexent-platform-acceptance/`，登记号 `R-NX-02`。

**复验完成（2026-09-29）**：以本地官方源码部署内置 suadmin 复验（R-NX-03），见 `artifacts/nexent-platform-acceptance/recheck-2026-09-29.yaml`。华为托管平台（AgentArts）MCP 注册与公网端点真实只读调用已完成（R-NX-05），见 `artifacts/nexent-platform-acceptance/hosted-2026-09-29.yaml`；Agent 创建与 DeepSeek 模型配置亦已完成（R-NX-06），见 `artifacts/nexent-platform-acceptance/hosted-agent-2026-09-29.yaml`；公网环境不支持 Skill（控制台明确提示），完整 Skill 问答需私网环境 + 私网可访问 MCP endpoint。

知识域演示数据灌入后，同一 Nexent 配置服务调用 `knowledge_list_assets` 返回非空资产列表（total=4），见 `artifacts/nexent-platform-acceptance/evidence/recheck-2026-09-29-with-data.json`。仍为本地官方源码部署复验，不是华为托管平台复验。

**本地完整 Skill 问答（2026-09-30，登记号 R-NX-09）**：在本地官方源码部署的 Nexent v2.6.1 中，Agent `seasight_governance_decision_agent` 发布版本 4（`v0.2.0-seasight-governance-llm`），配置 DeepSeek `deepseek-v4-pro`，绑定 21 个 MCP 只读工具与 5 个 Skill，经 `POST /agent/run`（SSE）完成一次真实 LLM 问答：HTTP 200、13,204 个事件、8 步、31 次工具调用、13 个唯一工具、无 run error、最终回答 2,777 字；`read_skill_md` 实际加载 `policy-evidence-qa`、`marine-event-assessment`、`dispatch-work-order-orchestration`、`decision-trace-audit` 4 个 Skill。完整 SSE、事件、工具轨迹、发布记录与控制台截图见 `artifacts/nexent-platform-acceptance/evidence/llm-qa-2026-09-30/`。**这是本地官方源码部署验收，不是华为托管平台内验收。**

### 路线 B：华为云免费试用 / 总决赛代金券

- 智果（AgentArts）平台免费试用入口：
  <https://console.huaweicloud.com/agentarts/?region=cn-southwest-2#/home/overview>
- 申请公测入口：
  <https://account.huaweicloud.com/usercenter/#/betaManagement?serviceCode=beta_agentarts>
- 入围总决赛后按主办方规则使用代金券购买华为云算力，用于 MCP 等自定义部署。

成本结论：注册华为云账号、下载开源 Nexent、完成一次只读平台验收通常不产生费用；
真正可能产生费用的是商用部署、超出试用配额或额外购买 ECS、带宽、对象存储等云资源。
材料中仍写“平台侧验收”，不写“华为认证”或“生产 SLA”。

**华为托管平台验收记录（2026-09-29，登记号 R-NX-05）**：已用华为云账号 `hid_b7bcgi-i88yqw0x`
（区域 cn-southwest-2）登录 AgentArts，公测已于 2026-09-29 审批通过，控制台已解锁。
MCP 详情页确认 `SeaSight Domain Cognition MCP` 状态“部署成功”，工具列表加载
21 个只读工具；对同一公网端点完成 initialize → tools/list →
`knowledge_list_assets` 真实只读调用，返回 total=4。界面截图与轨迹见
`artifacts/nexent-platform-acceptance/evidence/hosted-2026-09-29-*.png/json`，
结构化记录见 `artifacts/nexent-platform-acceptance/hosted-2026-09-29.yaml`。
托管平台（AgentArts）已创建智能体并配置 DeepSeek 模型（R-NX-06）；
控制台编辑页明确提示公网环境不支持 Skill（Environment 区域显示"公网访问环境"
且 Skill 绑定按钮 disabled）。公网环境限制由平台 UI 文档记录，完整 Skill 问答
需切换为私网环境 + 私网可访问 MCP endpoint 后方能验收。
托管平台验收不代表海域验证，也不代表感知精度。

**私网复验状态（2026-09-30，登记号 R-NX-07 blocked）**：私网环境
`environment-seasight-vpc-verify` 与网关 `seasight-vpc-gateway` 已建立，MCP、Agent
和 5 个 Skill 已就绪；华为云账号欠费使“创建 Target”按钮禁用（Target 0/10），
完整 Skill 问答尚未跑通，`live_skill_qa_completed: false`。解除欠费后的 Target
字段、VPC endpoint 方案、截图清单、失败排查和 R-NX-08 登记模板见
`docs/competitions/huawei-agentarts-vpc-target-runbook.md` 与
`artifacts/nexent-platform-acceptance/hosted-skill-qa.template.yaml`。手册本身不构成验收证据。

## 五、开源准备（入围总决赛前提）

仓库已具备 MIT LICENSE 和 README。公开到 GitCode/GitHub 前完成以下检查：

- [ ] 运行 `make check-public-repo-privacy`（等价于
      `python scripts/check_public_repo_privacy.py`），确认公开仓库无本机路径、
      生产地址或未脱敏验收证据；
- [ ] 确认 `.env`、`*.pem`、`*.key`、生产 bootstrap 等敏感文件未被跟踪；
- [ ] 扫描仓库内是否残留本机绝对路径、桌面路径、聊天截图或隐私材料；
- [ ] 将 E3 访谈、询价、试点意向等真实证据材料保留在私有提交中，不开源到公开仓库；
- [ ] README 增加华为赛题入口、Nexent 集成说明与快速验收命令；
- [ ] 选择 GitCode 或 GitHub 一个公开地址，提交材料中填写该地址；
- [ ] 与主办方确认开源范围是否包含数据集、演示材料与视频。

开源不等于把比赛材料全部公开：公开的是可复现代码与文档，真实访谈、个人联系方式和
未公开证据不随仓库外泄。

## 六、诚实口径

1. 本地 Nexent 自建验收证明“SeaSight MCP 能在该 Nexent 版本上完成注册、Skills 导入
   与被调用”；它不等于华为云商业环境认证，也不等于海域部署验证或感知精度。
2. 感知精度在独立测试集就绪前一律写 `not_evaluated`；76% 只能表述为时序链路误报抑制率。
3. 本地官方源码部署的 Nexent 已真实调用 DeepSeek 模型并跑通完整 Skill 问答
   （R-NX-09），可写“本地 Nexent 内已接入 LLM 并跑通完整问答”；不得写成
   “华为托管平台已跑通”或暗示 SeaSight 后端内置 LLM 规划器已启用。
   昇腾、ModelArts、鲲鹏继续写“架构/配置已就绪、待验证”。
4. 总决赛代金券是主办方提供的资源支持，不等于免费商用授权，也不等于可无上限调用。

## 七、下一步行动

| 优先级 | 动作 | 完成判据 | 谁能做 |
| --- | --- | --- | --- |
| 连江赛前 | 补 E3 真实证据（访谈、询价、试点意向），不因华为赛挤占 | 见 `pre-competition-execution.md` | 真人 |
| 已完成 | 本地 Nexent 部署并完成平台侧验收 | `artifacts/nexent-platform-acceptance/`（截图 + `latest.yaml`，2026-09-28） | 我 + 用户 |
| 已完成 | 赛道三提交件底稿三件套：评委自评、开发设计文档、提交件打包清单 | `docs/competitions/huawei-ict-track3-scoring-review.md`、`huawei-ict-track3-design-doc.md`、`huawei-ict-track3-submission-checklist.md` | WP-15 |
| 1 | 本地 Nexent 端到端已闭环：本地官方源码部署复验（R-NX-03，2026-09-29）；知识域演示数据 total=4（R-KN-01）；Agent 配置/发布/调用关系（R-NX-04）；**本地完整 LLM Skill 问答已跑通**（R-NX-09：DeepSeek `deepseek-v4-pro`、21 工具 + 5 Skill、HTTP 200、8 步、31 次调用、2,777 字回答）；华为托管平台（AgentArts）MCP 注册与公网端点真实只读调用已完成（R-NX-05），21 个工具；Agent 创建与 DeepSeek 模型配置已完成（R-NX-06）；5 个 Skill 已导入。托管平台完整 Skill 问答仍 `blocked`（R-NX-07：账号欠费使创建 Target 禁用，Target 0/10，`AgentArts.03002206`） | `recheck-2026-09-30-llm-qa.yaml` + `evidence/llm-qa-2026-09-30/` + `recheck-2026-09-29-with-data.json` + `agent-create-2026-09-29.yaml` + `hosted-2026-09-29-mcp-tools-21.png/json` + `hosted-2026-09-30-target-blocked.yaml` | 用户：先充值解除欠费，再按 runbook 建 Target + 绑 Agent + 跑平台内完整问答（R-NX-08） |
| 2 | 开源准备：密钥/隐私扫描、README 补充 | `python scripts/check_public_repo_privacy.py` 通过，公开仓库无敏感文件 | 我先扫描并出报告，公开动作由用户执行 |
| 3 | 向两个主办方确认重复参赛、开源、知识产权规则 | 书面回复 | 用户 |

## 八、变更记录

| 日期 | 变更 | 操作人 |
| --- | --- | --- |
| 2026-09-28 | 依据官方赛题原文建立对照表、平台验收路线与开源准备清单 | WP-15 |
| 2026-09-28 | 本地 Nexent v2.6.1 平台侧验收完成：MCP 注册、21 工具、5 Skills、真实调用一次 | WP-15 + liyongxiang |
| 2026-09-29 | 同步“本地平台侧验收已完成”状态，增加公开仓库隐私扫描命令 | WP-15 |
| 2026-09-29 | 上线公开仓库隐私扫描器，文档/脚本中的本机路径与生产地址改为占位符 | WP-15 |
| 2026-09-29 | 本地官方源码部署复验完成并登记 R-NX-03 | liyongxiang |
| 2026-09-29 | 华为托管平台（AgentArts）公测审批通过，控制台解锁；托管平台复验待周边依赖服务授权 | WP-15 + liyongxiang |
| 2026-09-29 | 华为托管平台 MCP 注册、21 工具加载与公网端点真实只读调用完成，登记 R-NX-05 | WP-15 + liyongxiang |
| 2026-09-29 | 依据赛道三官方评分表建立评委自评、开发设计文档底稿与提交件打包清单 | WP-15 |
| 2026-09-29 | 登记 R-NX-04 Agent 配置/发布/调用关系/导出证据（未配置 LLM） | liyongxiang + WP-15 |
| 2026-09-29 | 登记 R-NX-06：华为托管平台 Agent 创建、DeepSeek 模型配置与公网环境不支持 Skill 的限制留证；完整 Skill 问答需私网环境 + 私网可访问 MCP endpoint | WP-15 + liyongxiang |
| 2026-09-30 | 登记 R-NX-07 blocked；新增充值后 VPC Target runbook 与 R-NX-08 模板，保持平台侧与海域验证、感知精度分离 | WP-15 + liyongxiang |
| 2026-09-30 | 登记 R-NX-09 本地官方源码部署完整 LLM Skill 问答（发布版本 4、DeepSeek `deepseek-v4-pro`、21 工具 + 5 Skill、HTTP 200、8 步、31 次调用、2,777 字回答）；更新三/四路线 A/六/七，升版 1.3；托管平台内完整问答仍为 R-NX-07 blocked | liyongxiang + WP-15 |
