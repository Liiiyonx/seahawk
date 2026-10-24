#!/usr/bin/env python3
"""Build the optimized Huawei ICT innovation-track design document.

Loads the official submission template (which ships with the required cover,
base-info table and chapter skeleton), replaces every placeholder body section
with the real Oceanus project content, fills the base-info table (abstract /
tech stack / agent showcase screenshots / team photo), and writes a new docx
next to the original. The original file is never modified.

Claims discipline: this script is scanned by scripts/check_claims.py. All
statements are kept at E1/E2 with the project's honest-evidence wording
(not_evaluated perception accuracy; public data labeled as public; local
Nexent acceptance not conflated with the hosted platform).
"""

from __future__ import annotations

import sys
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
COMP_DIR = Path(r"C:\Users\Liii\Desktop\华为ICT大赛")
TEMPLATE = COMP_DIR / "创新赛-开发设计文档-福州理工学院-潮汐守望队-李涌翔-18259099729（初赛阶段）.docx"
OUTPUT = COMP_DIR / "创新赛-开发设计文档-福州理工学院-潮汐守望队-李涌翔-18259099729（初赛阶段·优化版）.docx"

TEAM_PHOTO = COMP_DIR / "92adde5a9f99e59875a9056f36f371fd.jpg"
FIG_ARCH = ROOT / "artifacts/doc-figures/fig-architecture.png"
FIG_RUNTIME = ROOT / "artifacts/doc-figures/fig-runtime-evolution.png"
IMG_CONSOLE = ROOT / "artifacts/nexent-platform-acceptance/evidence/console-fresh-2026-10-24/01-nexent-console-qa-page-loggedin.png"
IMG_QA_GROUNDED = ROOT / "artifacts/knowledge-qa-llm-frontend/01-接地回答-引用徽章与证据卡.png"
IMG_QA_REFUSAL = ROOT / "artifacts/knowledge-qa-llm-frontend/02-证据不足拒答-banner与缺口说明.png"
IMG_MULTIHOP = ROOT / "artifacts/knowledge-qa-trace-multihop/01-检索结果-本体图检索与引用.png"
IMG_EVIDENCE = ROOT / "artifacts/knowledge-qa-trace-multihop/02-决策证据链-资产版本引用.png"

HEADINGS = {
    "background": "智能体设计背景、应用场景、数据来源（必填）",
    "agent": "agent设计（必填）",
    "mcp": "相关MCP及Skills设计（必填）",
    "other": "其他补充（如有）",
    "code": "第二章 代码说明（完整代码文件请作为单独附件（必选），与本文档一并打包上传）",
    "reference": "第三章 参考资料（如有）",
}

# ---------------------------------------------------------------------------
# Content model: ("p", text) body paragraph; ("h3", text) bold sub-heading;
# ("b", text) bullet; ("table", header, rows) grid table; ("img", path, cm, caption)
# Text supports **bold** spans.
# ---------------------------------------------------------------------------

CONTENT: dict[str, list[tuple]] = {
    "background": [
        ("h3", "〇、评审导览：赛题关键词 → 本项目落点与证据"),
        ("table",
         ["赛题关键词", "本项目落点", "对应章节与证据"],
         [
             ["基于 Nexent 平台可运行", "本地官方源码部署完整 LLM Skill 问答（一次运行 8 步、31 次工具调用）；华为 AgentArts 托管平台内完整 Skill 问答已跑通（9 分钟 1933 帧、真实模型、证据不足如实拒答）", "1.2 节；登记号 R-NX-09 / R-NX-08"],
             ["MCP 工具集成", "21 只读 + 11 写入工具；华为云 AgentArts 已注册并实证只读调用", "1.3 节；登记号 R-NX-05"],
             ["Skills 工作流编排", "5 个 SKILL.md 模板（触发条件/工具顺序/停止条件/输出要求）", "1.3 节"],
             ["决策“可进化”", "经验进化 / 知识进化 / 策略进化三条回路，均有固定场景或端到端验证", "1.2 节四；27 个固定场景评测"],
             ["检索-推理双驱动、决策可溯源", "ontology_graph 多跳检索 + 决策证据链；真实两跳实例", "1.3 节三；登记号 R-KN-05"],
             ["真实数据评测", "真实公开政务语料端到端闭环 + NOAA 真实公开行业监测数据接入", "1.1 节三；登记号 R-OD-02 / R-OD-03"],
         ]),
        ("h3", "一、设计背景"),
        ("p", "我国近岸海域（尤其是养殖业密集的县域岸段）长期受海漂垃圾影响：泡沫浮球碎片、废旧渔具、饵料袋等漂浮物威胁养殖安全与海岸景观。基层治理中沉淀了大量政策文件、巡查台账、事件记录与处置工单，但这些资产分散异构、难以被决策直接调用——治理决策长期依赖个人经验，说不清“依据哪份文件、哪个版本、哪条记录”。"),
        ("p", "与此同时，决策自动化面临三重现实约束：其一，领域语料稀缺，无法依赖大规模标注冷启动知识库；其二，治理决策必须可追责，不接受黑箱结论；其三，模型输出不可全信，越权操作必须能被拦住。传统规则引擎难以应对动态场景，单一 AI 模型又缺乏工具调用与多步推理能力。"),
        ("p", "本项目以华为 ModelEngine Nexent 为基座，构建面向县域海洋环境治理的**可进化决策智能体“探海灵眸 Oceanus”**。设计目标可以概括为：让智能体“看得见新东西、说得清理由、被管得住、事后查得到、越用越聪明”——前四点是决策可用的底线，最后一点是“可进化”的落点。"),
        ("h3", "二、应用场景"),
        ("p", "核心场景是养殖区海漂垃圾治理的完整决策闭环：岸基摄像头感知发现 → 事件生成与研判（智能体） → 策略守卫校验 → 多角色人工审批 → 平台派单 → 执行端作业（水面打捞机器人 / 岸基机械臂，均为可替换的 MQTT 作业端） → 作业回执 → 复盘进化。智能体在闭环中承担研判、规划、调度、复盘四个决策角色。"),
        ("p", "“可进化”落在三个层面。**经验进化**：每次运行终态自动复盘，提炼结构化经验（例如“某类事件在当前时段常无可用执行端”），同类事件规划期自动引用，置信度用贝叶斯后验校准——引用与确认分别计数、16 次确认封顶 0.95、永不到 1.0，因为只会上涨的置信度不是置信度。**知识进化**：本体以版本链演进，新资产版本进入新一轮候选抽取，人工审核后发布新版本，增量抽取较全量重抽节省 63.19% 耗时。**策略进化**：决策证据链同时固化资产版本、本体版本与策略版本，策略调整后历史决策仍可按当时口径回放。"),
        ("h3", "三、数据来源"),
        ("p", "知识域统一管理六类资产：document（政策/标准/通知）、table（台账）、image（识别帧）、event（事件）、telemetry（遥测）、dataset（数据集）。资产身份稳定、内容按版本追加并记录内容哈希，可引用到版本级。"),
        ("p", "**真实公开政务语料**：已登记 8 份生态环境部公开文件（海洋环境标准征求意见通知、海洋倾倒物质评价规范相关文件、中国海洋生态环境状况公报等），来源 URL 与 SHA256 全部可追溯，并已在其上完成“登记 → 本体候选抽取 → 人工审核 → 发布 → 多跳检索 → 决策证据链”端到端闭环（证据编号 R-OD-02，抽取 30 节点 / 47 关系，检索 9 命中、6 条带关系路径）。"),
        ("p", "**真实公开行业监测数据**：已获取 NOAA NCEI 全球海洋微塑料监测数据集（22,530 条监测记录，1986–2023 年，覆盖 5 个大洋、26 个国家/地区，逐条带 DOI 与 NCEI 登记号），已登记为公开级数据集资产并用于检索-推理-决策链路（证据编号 R-OD-03），为污染热点分级与清理资源调度提供行业级参考基准。"),
        ("p", "演示数据：业务闭环演示使用明确标注“演示”的资产，与真实数据严格分开表述。感知侧识别精度按诚实口径标注为 not_evaluated；公开基准（SC-FloatWaste）上的模型评测数字均带“第三方公开数据集、非现场实测”限定语。"),
        ("table",
         ["数据资产", "类型", "规模", "安全级", "证据编号"],
         [
             ["生态环境部公开文件", "document", "8 份，来源 URL + SHA256 可追溯", "public", "R-OD-02"],
             ["NOAA NCEI 全球海洋微塑料监测数据集", "dataset", "22,530 行（1986–2023，26 国家/地区，逐条带 DOI）", "public", "R-OD-03"],
             ["业务闭环演示资产", "event/table/image/telemetry/dataset", "6 项，标题标注“演示”", "internal", "R-KN-04 / R-KN-05"],
             ["SC-FloatWaste 公开漂浮垃圾基准", "dataset", "独立测试集 400 张 / 1,490 框", "public", "公开基准评测"],
         ]),
    ],
    "agent": [
        ("h3", "一、总体架构：认知—编排—执行三层"),
        ("p", "**认知层（Oceanus 知识域）**：多模态资产版本化登记 → 低资源半自动本体构建（候选抽取 → 人工审核 → 发布）→ 跨文档多跳检索（带关系路径与跳数）→ 决策证据链（按顺序固化证据、引用到资产版本）。领域语料稀缺场景下不依赖标注训练，用确定性的词频/共现候选算法加人工审核冷启动，全过程可解释、可审计。"),
        ("p", "**编排层（Nexent Agent）**：接入 DeepSeek 大模型，通过 MCP 协议调用 Oceanus 工具面，按 Skill 工作流模板组织“先查什么、再算什么、何时停止”。Skill 以自然语言固化触发条件、工具顺序与停止条件，是可跨行业复用的业务逻辑模板（替换本体与资产源即可迁移）。"),
        ("p", "**执行层（Oceanus 业务系统）**：角色权限（四类角色，服务端签名令牌）、辖区过滤、审批、幂等与审计；执行末端可插拔（岸基设备、水面机器人、机械臂统一走派单链路）。关键分工：Nexent 负责编排与推理，Oceanus 后端负责权限与事实——工具返回后端真实数据，业务失败被转换为工具错误返回给模型，不会伪装成成功数据。"),
        ("img", FIG_ARCH, 15.5, "图 1 系统总体架构：认知—编排—执行三层与 MCP 工具面"),
        ("h3", "二、决策运行时（Runtime）"),
        ("p", "单次决策的完整生命周期：任务规划 → MCP 工具调用 → 策略守卫校验（敏感工具、角色越权、步数预算） → 多角色人工审批（operator 申请、admin/approver 决策） → 执行 → 全程轨迹审计与回放。"),
        ("p", "工程可靠性：运行时持久化——等待审批的运行落库后，全新进程可续跑并完成派单闭环；并发幂等——同一幂等键只创建一次运行，重复触发复用；乐观锁冲突检测——旧版本保存被拒绝且不覆盖原数据。模型侧非法 JSON、超时、越权一律回退确定性规则规划器（source=rule_fallback），决策链路不因模型故障中断。"),
        ("img", FIG_RUNTIME, 15.5, "图 2 决策运行时生命周期与三条进化回路（紫色虚线）"),
        ("h3", "三、决策质量怎么验证"),
        ("table",
         ["评测体系", "规模", "说明"],
         [
             ["固定场景评测", "27 个", "场景 ID 冻结；覆盖持久化续跑、并发幂等、模型回退、多角色研判门禁、经验闭环、设备故障注入"],
             ["真实状态集成验收", "129 项", "真实 HTTP / 权限 / PostgreSQL / 审批 / 幂等 / 进程重启只读回放"],
             ["全量自动化测试", "1374 项", "pytest 全绿（1374 通过 / 17 环境跳过 / 0 失败）"],
             ["受控故障演练", "127 项", "健康降级、ACK 启动恢复、设备孪生闭环等 4 组"],
             ["浏览器端到端验收", "15 项", "真实登录 + 六页真实读取 + CSV 导出"],
         ]),
        ("img", IMG_CONSOLE, 14.5, "图 3 本地 Nexent 控制台（登录态）：已发布的治理决策智能体，可直接发起问答"),
        ("h3", "四、可进化机制（对应赛题核心）"),
        ("p", "**经验进化**有固定场景验证：lessons_retro_and_reuse 场景验证“第一次同类事件失败 → 终态复盘提炼经验（初始置信度 0.75）→ 第二次同类事件规划期引用该经验（hit_count=1），引用后运行失败会下调、确认后会上调，16 次确认封顶 0.95”；lessons_scoped_and_evict 场景验证经验按事件类别隔离、不串味、不膨胀。"),
        ("p", "**知识进化**有端到端证据：R-OD-02 在 8 份真实公开政务文件上完成本体版本全生命周期；R-KN-03 对比增量追加与全量重抽（1.615ms 对 4.387ms，节省 63.19%）。**决策进化**有真实多跳实例：R-KN-05（见 1.3 节三，图 5）。"),
        ("table",
         ["进化回路", "机制", "验证方式", "证据"],
         [
             ["经验进化", "终态复盘提炼结构化经验，同类事件规划期引用，贝叶斯后验置信度", "固定场景 lessons_retro_and_reuse / lessons_scoped_and_evict（按类别隔离、不串味、失败下调）", "27 场景评测"],
             ["知识进化", "本体候选 → 审核 → 发布版本链，新资产版本增量抽取", "真实公开语料端到端 + 增量/全量对比", "R-OD-02；R-KN-03"],
             ["策略进化", "决策证据链固化策略版本，策略调整后按当时口径回放", "决策轨迹 + 审计回放", "R-KN-04 / R-KN-05"],
         ]),
        ("h3", "五、一次完整决策的逐步轨迹（真实多跳实例 R-KN-05）"),
        ("table",
         ["步骤", "动作", "关键结果"],
         [
             ["1", "提出问题", "“马鼻镇出现泡沫聚集时，应如何处置并留存证据链？”"],
             ["2", "本体图检索", "mode=ontology_graph，命中 6 条，其中 3 条 hop=2（路径：泡沫垃圾[触发]→岸线巡查[生成]→打捞任务）"],
             ["3", "记录决策", "生成决策轨迹 dtr_20261023154439_63672815，状态 completed"],
             ["4", "证据链固化", "6 条证据覆盖 hop=0/1/2 三档，逐条引用资产版本（事件/表格/文档/遥测/图像/数据集）"],
             ["5", "回放审计", "前端决策页与 API 双通道可复核；截图见 1.3 节图 5、图 6"],
         ]),
    ],
    "mcp": [
        ("h3", "一、MCP 工具面：Oceanus Domain Cognition MCP"),
        ("p", "默认注册 21 个只读工具；显式开启开关后才追加 11 个写入工具（共 32 个）——写入能力不是隐藏，而是默认不注册。入站 Bearer 鉴权 fail-closed；出站调用 Oceanus /api/v1；业务失败转换为工具错误返回，不向模型伪装成功。"),
        ("table",
         ["工具组", "只读工具"],
         [
             ["资产（2）", "knowledge_list_assets、knowledge_asset_detail"],
             ["本体（4）", "knowledge_list_ontology_versions、knowledge_ontology_version_detail、knowledge_list_ontology_nodes、knowledge_list_ontology_relations"],
             ["检索（1）", "knowledge_search"],
             ["决策（2）", "knowledge_list_decisions、knowledge_decision_evidence"],
             ["业务（6）", "event_get、event_list、task_get、task_list、task_ack_history、dashboard_get"],
             ["Agent 审计（6）", "agent_runtime_status、agent_list_runs、agent_run_detail、agent_run_steps、agent_list_tools、agent_list_approvals"],
         ]),
        ("p", "华为云 AgentArts 托管平台内完整 Skill 问答已跑通（登记号 R-NX-08，2026-10-24）：智能体经官方 Managed Agents WebSocket 通道调用，一次运行 9 分钟、1933 帧、真实模型生成 2254 字回答——运行环境未加载知识库资产时，智能体全量检索后如实声明“引用全部 not_evaluated”并给出逐节标注“非知识库依据”的处置框架，拒绝编造政策依据（与本地验收的拒答行为同一设计）。前置的 MCP 注册（21 只读工具、公网端点真实调用）与调试过程（账号冻结、凭据释放、模型中转重建等连环修复）均留证。本地 Nexent（官方源码部署 v2.6.1）完整 LLM Skill 问答验收：Agent 发布版本 4，一次运行 HTTP 200、8 步、31 次工具调用、13 个唯一工具（登记号 R-NX-09）——完整 SSE 事件流与逐次工具调用轨迹随证据包提交。此外，知识域新增检索-生成问答（先多跳检索后生成、回答内嵌可点击引用、证据不足明示拒答，登记号 R-KN-06），前端提供“问答”工作台实测截图；本体抽取具备 LLM 主通道并在真实公开政务文本上完成双通道对照评测（登记号 R-LLM-01/02）。"),
        ("img", IMG_QA_GROUNDED, 14.5, "图 4 知识域“问答”工作台：检索-生成回答内嵌可点击引用徽章，证据卡带跳数路径与资产版本引用（真实模型实测）"),
        ("img", IMG_QA_REFUSAL, 14.5, "图 5 证据不足时的拒答横幅：模型拒绝编造政策依据，与处置建议逐节标注“非知识库依据”"),
        ("h3", "二、Skills 工作流模板"),
        ("table",
         ["Skill", "用途", "设计要点"],
         [
             ["policy-evidence-qa", "用可引用资产版本回答政策问题", "强制引用资产版本；证据不足时明确输出“不应套用”"],
             ["marine-event-assessment", "评估事件与对应治理依据", "检索事件快照 + 政策依据，输出研判结论"],
             ["cross-document-decision", "本体引导的跨文档多跳推理", "多跳路径逐步引用，停止条件为证据充分"],
             ["dispatch-work-order-orchestration", "协调事件、审批与工单", "不绑定机器人厂商，统一走派单链路"],
             ["decision-trace-audit", "核对决策可追溯性", "逐条核对证据与执行步骤"],
         ]),
        ("p", "口径：Agent 绑定 5 个 Skill；示例问题经 read_skill_md 实际加载 4 个（cross-document-decision 已绑定、该问题未触发）。对外不宣称“5 个全部验证通过”。"),
        ("h3", "三、检索-推理双驱动与真实多跳实例"),
        ("p", "已发布本体存在时，检索返回 mode=ontology_graph，带关系路径、跳数与引用片段；无可用本体时明确回退关键词模式，不冒充图谱检索。**真实两跳实例（R-KN-05）**：同一问题“马鼻镇出现泡沫聚集时，应如何处置并留存证据链？”命中 6 条，其中 3 条 hop=2（路径：泡沫垃圾[触发]→岸线巡查[生成]→打捞任务）；决策证据链 6 条覆盖 hop=0/1/2 三档、引用 6 份不同资产版本（事件/表格/文档/遥测/图像/数据集）。"),
        ("img", IMG_MULTIHOP, 14.5, "图 6 知识域“跨文档多跳检索”：命中带“2 跳”标记与可视关系路径"),
        ("img", IMG_EVIDENCE, 14.5, "图 7 决策证据链：按顺序固化证据，逐条引用资产版本，可回放"),
    ],
    "other": [
        ("h3", "一、质量与验收体系"),
        ("p", "项目建立七层验证体系，各自守住不同的失效面：算法逻辑与参数一致性、全量契约与推理后处理、前后端接口一致性、仓库卫生、开源前隐私扫描、MQTT/枚举契约漂移、端到端链路。其中宣称纪律门禁（check_claims.py）把“证据分级表述”变成可执行检查——扫描全部材料中的越级宣称与无来源数字，退出码 0 才允许打包；门禁自身由注入缺陷的自证脚本验证有效性。"),
        ("h3", "二、一键复现"),
        ("b", "基础设施：docker compose up -d（PostgreSQL/Redis/EMQX/MinIO）"),
        ("b", "初始化：make db-init && make migrate-stamp"),
        ("b", "启动：make dev-backend、make dev-frontend"),
        ("b", "Nexent 集成验收：make nexent-install && make nexent-acceptance"),
        ("b", "真实公开语料端到端复现：python scripts/open_data_knowledge_e2e.py（R-OD-02）"),
        ("b", "真实行业数据集评测复现：python scripts/real_dataset_knowledge_e2e.py（R-OD-03）"),
        ("h3", "三、演示材料"),
        ("p", "系统操作演示视频（约 4 分 39 秒、1080p）随代码附件一并提交；全部证据截图与 API 轨迹按证据编号（R-KN-04/05、R-OD-01/02/03、R-NX-05/06/09 等）归档，评审可逐条复核。"),
        ("h3", "四、诚实边界声明"),
        ("p", "感知识别精度为 not_evaluated（未评测）；本项目使用的真实公开数据（政务公开文件、NOAA NCEI 公开监测数据）不等于真实脱敏行业内部数据；演示数据不参与任何精度宣称；本地 Nexent 验收不等于华为托管平台内验收。全部材料按上述口径撰写，接受评审质询。"),
    ],
    "code": [
        ("p", "本项目完整源代码以附件形式提交（约 322 个源码文件 / 11 万行，不含运行产物与依赖）。主目录结构与职责如下（评审重点文件加粗）："),
        ("table",
         ["目录", "职责"],
         [
             ["backend/app/services/agents/", "**决策运行时**：规划（planner.py）、策略守卫（policy.py）、人工审批、持久化与续跑（runtime.py）、经验闭环（lessons.py）、贝叶斯校准（calibration.py）"],
             ["backend/app/services/knowledge.py", "**知识域**：资产版本化、本体候选抽取与审核发布、多跳检索（带路径/跳数/引用）、决策证据链"],
             ["integrations/nexent/mcp_server/server.py", "**Oceanus Domain Cognition MCP**：21 只读 + 11 写入工具，Bearer 鉴权 fail-closed"],
             ["integrations/nexent/skills/", "5 个 SKILL.md 工作流模板（政策问答/事件研判/跨文档决策/工单编排/轨迹审计）"],
             ["backend/app/api/v1/", "HTTP 接口层：事件、任务、知识域、Agent、认证、审计等 15 个模块"],
             ["frontend/src/", "Vue3 大屏、工单看板、知识域四工作台、智能体控制台"],
             ["edge/", "边缘感知双通道（OpenCV 传统视觉 + YOLO-World 开放词汇，现场加词不重训）与机械臂桥接"],
             ["ml/", "训练管线与第三方公开基准（SC-FloatWaste）评测脚本"],
             ["scripts/", "宣称纪律门禁、契约漂移守卫、端到端验收与采集脚本、提交打包"],
         ]),
        ("p", "代码规模（按模块统计，不含空行统计口径差异与依赖产物）："),
        ("table",
         ["模块", "文件数", "行数"],
         [
             ["backend（Python）", "149", "48,660"],
             ["frontend（Vue/TS/JS）", "53", "30,183"],
             ["edge（Python/YAML）", "105", "24,602"],
             ["ml（Python）", "14", "5,575"],
             ["integrations（Python）", "1", "982"],
             ["合计", "322", "110,002"],
         ]),
        ("p", "关键代码片段一：经验置信度的贝叶斯校准（backend/app/services/agents/calibration.py）——“只会涨的置信度不是置信度”的代码落点："),
        ("code", "def bayesian_confidence(prior, successes, trials, prior_strength=4.0) -> float:\n    \"\"\"Beta 后验均值：(α·prior + successes) / (α + trials)。\"\"\"\n    if not 0.0 <= prior <= 1.0:\n        raise ValueError(f\"prior 必须在 [0,1]：{prior}\")\n    if prior_strength <= 0:\n        raise ValueError(f\"prior_strength 必须为正：{prior_strength}\")\n    if successes < 0 or trials < successes:\n        raise ValueError(f\"非法观测计数：successes={successes}, trials={trials}\")\n    return (prior_strength * prior + successes) / (prior_strength + trials)"),
        ("p", "解读：无观测时恒等于先验；经验被引用后的真实成功使置信度上升、失败使它下降——这与“只增不减的计数递增”有本质区别，是经验进化不会被自我强化的关键设计。"),
        ("p", "运行环境：Python 3.11、Node.js 20、Docker Compose（PostgreSQL 14 + PostGIS、Redis 7、EMQX 5、MinIO、go2rtc）、Nexent v2.6.1（本地官方源码部署）。快速启动见仓库 README：docker compose up -d → make db-init → make dev-backend → make dev-frontend；Nexent 集成验收：make nexent-acceptance。"),
    ],
    "reference": [
        ("b", "ModelEngine-Group/nexent 官方开源仓库（GitHub / GitCode）与官方文档站"),
        ("b", "Model Context Protocol 规范（modelcontextprotocol.io）"),
        ("b", "Nyadjro, E. S., et al. The NOAA NCEI marine microplastics database. Scientific Data, 10(1), 2023. DOI: 10.1038/s41597-023-02632-y"),
        ("b", "生态环境部：《中国海洋生态环境状况公报》（2023）及海洋环境标准公开征求意见文件（来源 URL 随证据包归档）"),
        ("b", "SC-FloatWaste 公开漂浮垃圾基准（神经网络通道独立评测集，评测产物随证据包提交）"),
        ("b", "Yao, S., et al. ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023."),
        ("b", "Schick, T., et al. Toolformer: Language Models Can Teach Themselves to Use Tools. NeurIPS 2023."),
        ("b", "《中华人民共和国海洋环境保护法》（2023 年修订）"),
    ],
}

ABSTRACT = (
    "本项目基于华为 ModelEngine Nexent 平台，面向县域海洋环境治理场景构建可进化决策智能体"
    "“探海灵眸 Oceanus”。智能体采用“认知—编排—执行”三层架构：知识域完成六类资产版本化、"
    "低资源半自动本体构建与跨文档多跳检索；编排层通过 21 个只读 MCP 工具与 5 个 Skill 工作流"
    "模板实现检索-推理双驱动决策；执行层落实策略守卫、多角色人工审批、幂等与全程审计回放。"
    "可进化性体现在三处：跨运行经验闭环（复盘提炼、贝叶斯置信度校准、同类事件规划期引用）、"
    "本体版本增量进化（增量抽取较全量重抽节省 63.19% 耗时）、决策证据链随资产/本体/策略版本"
    "可追溯。已在本地 Nexent 与华为 AgentArts 托管平台双端完成完整 LLM Skill 问答验收（托管平台一次运行 9 分钟、1933 帧、证据不足如实拒答），并在真实"
    "公开政务语料与真实公开行业监测数据（NOAA NCEI 全球海洋微塑料数据集，22,530 条记录）上"
    "完成端到端评测；全项目 1374 项自动化测试全绿。"
)

TECH_STACK = (
    "华为 ModelEngine Nexent 平台、MCP（Model Context Protocol）、Skills 工作流编排、"
    "DeepSeek LLM、FastAPI + PostgreSQL/PostGIS + Redis + EMQX(MQTT)、Vue3 + ECharts、"
    "YOLO-World 开放词汇感知、Redis Streams 事件队列、Playwright 端到端验收、贝叶斯置信度校准"
)

SHOWCASE_TEXT = "① 本地 Nexent 控制台（登录态）：已发布治理决策智能体，可直接发起问答；② 知识域“跨文档多跳检索”：命中带 2 跳关系路径的证据；③ 决策证据链：6 条证据覆盖 hop=0/1/2、引用 6 份资产版本；④ 知识域“问答”工作台：检索-生成回答内嵌可点击引用徽章，证据不足时明示拒答横幅（R-KN-06，真实模型实测）。本地（R-NX-09）与华为托管平台（R-NX-08）双端完整问答的轨迹与截图随证据包提交。"


def add_runs(paragraph, text: str, *, size: Pt = None, bold: bool = False, color: RGBColor = None) -> None:
    """Add runs to a paragraph, honoring **bold** spans."""
    parts = text.split("**")
    for i, part in enumerate(parts):
        if not part:
            continue
        run = paragraph.add_run(part)
        run.bold = bold or (i % 2 == 1)
        run.font.name = "Times New Roman"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        if size is not None:
            run.font.size = size
        if color is not None:
            run.font.color.rgb = color
    if not text:
        run = paragraph.add_run("")
        run.font.name = "Times New Roman"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")


def body_para(anchor, text: str):
    p = anchor.insert_paragraph_before()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.3
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    add_runs(p, text, size=Pt(12))
    return p


def h3_para(anchor, text: str):
    p = anchor.insert_paragraph_before()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(6)
    add_runs(p, text, size=Pt(13), bold=True)
    for run in p.runs:
        # 小标题统一黑体（含西文），与正文宋体形成层级对比
        run.font.name = "黑体"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
    return p


def bullet_para(anchor, text: str, style_name: str | None):
    if style_name:
        p = anchor.insert_paragraph_before(style=style_name)
        add_runs(p, text, size=Pt(12))
        return p
    p = anchor.insert_paragraph_before()
    add_runs(p, "· " + text, size=Pt(12))
    return p


def caption_para(anchor, text: str):
    p = anchor.insert_paragraph_before()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    add_runs(p, text, size=Pt(9), color=RGBColor(0x59, 0x59, 0x59))
    return p


def code_para(anchor, text: str):
    p = anchor.insert_paragraph_before()
    p.paragraph_format.space_after = Pt(6)
    for line in text.split("\n"):
        run = p.add_run(line)
        run.font.name = "Consolas"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x1F, 0x29, 0x37)
    return p


def image_para(anchor, path: Path, width_cm: float):
    p = anchor.insert_paragraph_before()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(str(path), width=Cm(width_cm))
    return p


def insert_table(doc, anchor, header: list[str], rows: list[list[str]]):
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.style = "Table Grid"
    for j, text in enumerate(header):
        cell = table.rows[0].cells[j]
        cell.text = ""
        # 表头浅蓝底纹，与正文行形成视觉层级
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), "E3ECF7")
        cell._tc.get_or_add_tcPr().append(shd)
        add_runs(cell.paragraphs[0], text, size=Pt(10.5), bold=True)
    for i, row in enumerate(rows, start=1):
        for j, text in enumerate(row):
            cell = table.rows[i].cells[j]
            cell.text = ""
            add_runs(cell.paragraphs[0], text, size=Pt(10.5))
    anchor._p.addprevious(table._tbl)
    spacer = anchor.insert_paragraph_before()
    spacer.paragraph_format.space_after = Pt(4)
    add_runs(spacer, "", size=Pt(2))
    return table


def clear_cell(cell) -> None:
    """Remove every paragraph inside a tc (keeping tcPr), leaving it empty."""
    tc = cell._tc
    for p in tc.findall(qn("w:p")):
        tc.remove(p)
    tc.append(OxmlElement("w:p"))


def fill_table(doc) -> None:
    """Locate target cells by direct XML iteration (merge-safe: touching only
    the exact w:tc whose text matches; never via row.cells aliasing)."""
    table = doc.tables[0]
    matched = []
    seen = set()
    tcs = list(table._tbl.iter(qn("w:tc")))
    print(f"[fill_table] tables={len(doc.tables)} tc_count={len(tcs)}")
    for tc in tcs:
        text = "".join(tc.itertext()).strip()
        cell = docx.table._Cell(tc, table)
        if text.startswith("本项目基于华为ModelEngine"):
            clear_cell(cell)
            add_runs(cell.paragraphs[0], ABSTRACT, size=Pt(10.5))
            matched.append("abstract")
        elif text.startswith("华为ModelEngine Nexent平台、MCP协议"):
            clear_cell(cell)
            add_runs(cell.paragraphs[0], TECH_STACK, size=Pt(10.5))
            matched.append("tech")
        elif text.startswith("（展示区域"):
            clear_cell(cell)
            add_runs(cell.paragraphs[0], SHOWCASE_TEXT, size=Pt(10.5))
            for img, cap in (
                (IMG_CONSOLE, "展示 1 Nexent 控制台（登录态）：已发布治理决策智能体"),
                (IMG_QA_GROUNDED, "展示 2 知识域“问答”工作台：引用徽章与证据卡（真实模型）"),
                (IMG_MULTIHOP, "展示 3 跨文档多跳检索（2 跳路径）"),
                (IMG_EVIDENCE, "展示 4 决策证据链（hop=0/1/2）"),
            ):
                p = cell.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.add_run().add_picture(str(img), width=Cm(13.5))
                cp = cell.add_paragraph()
                cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                add_runs(cp, cap, size=Pt(9), color=RGBColor(0x59, 0x59, 0x59))
            matched.append("showcase")
        elif text.startswith("（请插入团队合照"):
            clear_cell(cell)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(str(TEAM_PHOTO), width=Cm(8.5))
            matched.append("team-photo")
    expected = {"abstract", "tech", "showcase", "team-photo"}
    if set(matched) != expected:
        raise SystemExit(f"FAIL: base-table cells not all matched: matched={matched}")


def clear_section(heading_p, stop_p) -> None:
    """Remove every body element after this heading until (excluding) stop_p.

    Never touches the body-level ``w:sectPr`` (page setup lives there and is
    the last child of the body).
    """
    node = heading_p._p.getnext()
    while node is not None and (stop_p is None or node is not stop_p._p):
        if node.tag == qn("w:sectPr"):
            break
        nxt = node.getnext()
        node.getparent().remove(node)
        node = nxt


def insert_items(doc, anchor_p, items, bullet_style) -> None:
    for item in items:
        kind = item[0]
        if kind == "p":
            body_para(anchor_p, item[1])
        elif kind == "h3":
            h3_para(anchor_p, item[1])
        elif kind == "b":
            bullet_para(anchor_p, item[1], bullet_style)
        elif kind == "table":
            insert_table(doc, anchor_p, item[1], item[2])
        elif kind == "code":
            code_para(anchor_p, item[1])
        elif kind == "img":
            image_para(anchor_p, Path(item[1]), item[2])
            caption_para(anchor_p, item[3])
        else:
            raise ValueError(f"unknown item kind: {kind}")


def main() -> None:
    for name, path in [("template", TEMPLATE), ("team photo", TEAM_PHOTO), ("console", IMG_CONSOLE), ("multihop", IMG_MULTIHOP), ("evidence", IMG_EVIDENCE)]:
        if not Path(path).is_file():
            raise SystemExit(f"FAIL: missing {name}: {path}")

    doc = docx.Document(str(TEMPLATE))

    # 官方模板 body 缺少 sectPr，python-docx 的 add_table 依赖它计算页宽；
    # 补一个 A4 + 1 英寸页边距的节属性（幂等）。
    body_elm = doc.element.body
    if body_elm.find(qn("w:sectPr")) is None:
        sect = OxmlElement("w:sectPr")
        pg_sz = OxmlElement("w:pgSz")
        pg_sz.set(qn("w:w"), "11906")
        pg_sz.set(qn("w:h"), "16838")
        pg_mar = OxmlElement("w:pgMar")
        for attr, value in (("w:top", "1440"), ("w:right", "1440"), ("w:bottom", "1440"), ("w:left", "1440"), ("w:header", "851"), ("w:footer", "992"), ("w:gutter", "0")):
            pg_mar.set(qn(attr), value)
        sect.append(pg_sz)
        sect.append(pg_mar)
        body_elm.append(sect)

    heading_ps: dict[str, object] = {}
    order: list[object] = []
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            for key, text in HEADINGS.items():
                if p.text.strip() == text:
                    heading_ps[key] = p
                    order.append(key)
    missing = [k for k in HEADINGS if k not in heading_ps]
    if missing:
        raise SystemExit(f"FAIL: template headings not found: {missing}")

    # 清空各节旧正文（标题后的全部兄弟元素，直到下一标题）
    for idx, key in enumerate(order):
        stop = heading_ps[order[idx + 1]] if idx + 1 < len(order) else None
        clear_section(heading_ps[key], stop)

    # 逐节插入新内容；锚点 = 下一标题段（内容插在其前），最后一节用文末哨兵段
    # （哨兵必须插在 sectPr 之前，否则页面属性之后出现游离段落）
    bullet_style = next((s.name for s in doc.styles if s.name == "List Bullet"), None)
    sentinel_elm = OxmlElement("w:p")
    body_elm.find(qn("w:sectPr")).addprevious(sentinel_elm)
    from docx.text.paragraph import Paragraph

    sentinel = Paragraph(sentinel_elm, heading_ps[order[-1]]._parent)
    for idx, key in enumerate(order):
        anchor = heading_ps[order[idx + 1]] if idx + 1 < len(order) else sentinel
        insert_items(doc, anchor, CONTENT[key], bullet_style)
    sentinel_elm.getparent().remove(sentinel_elm)

    fill_table(doc)
    doc.save(str(OUTPUT))
    print(f"OK -> {OUTPUT}")


if __name__ == "__main__":
    sys.exit(main())
