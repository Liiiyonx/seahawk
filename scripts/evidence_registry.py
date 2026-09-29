#!/usr/bin/env python
"""机器可读证据登记表（WP-15 证据门禁 / E0-E4 纪律）。

存在理由
--------
把《项目文档/商业证据台账.md》的证据纪律变成 `check_claims.py` 可查询的
机器可读登记表：一条“红线宣称”是否成立，取决于它能否被**已经登记的证据**
豁免。登记表只做两件事：

1. 提供必需的登记字段：id / claim / evidence_level / source_type /
   source_ref / captured_at / review_status / owner（与台账字段对齐）。
2. 向扫描器暴露豁免查询：`Registry.exempt(rule_id, text)` 与
   `Registry.cites_registered(text)` —— 扫描器不得仅靠关键词一刀切。

数据来源与维护
--------------
- 内嵌 `DEFAULT_RECORDS` 是当前可复现事实的机器镜像：台账 F/C/T/S/E/G
  编号 + 七条纪律记录（76% 口径、coverage_area 语义、Agent Runtime 边界、
  成交措辞、OpenCV 边界、合成/真实边界、证据等级定义）。
- 台账《商业证据台账.md》仍是商业数字的唯一事实源；本表是它的机器镜像，
  两者不一致时以台账为准，并由总控同步本表。
- 团队新证据通过 `docs/evidence-inbox/intake_template.yaml` 提交，
  总控复核后并入本表（`--registry <file>` 可合并外部 YAML，不影响内嵌）。

本模块不修改任何工作树文件；`--export-*` 只向 stdout 输出。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

# Windows 控制台默认 GBK：中文输出统一走 UTF-8（只改输出编码，不影响语义）。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

REQUIRED_FIELDS = (
    "id",
    "claim",
    "evidence_level",
    "source_type",
    "source_ref",
    "captured_at",
    "review_status",
    "owner",
)

# 冻结证据等级口径（与计划书 §1 / 台账 §0 一致）。
EVIDENCE_LEVELS: dict[str, str] = {
    "E0": "规划假设/内部测算（只有想法、文档或接口草案）",
    "E1": "有代码、单元测试或确定性仿真（已实现，已通过软件测试）",
    "E2": "多模块软件联调，合成数据或模拟设备（合成环境闭环验证）",
    "E3": "真实设备、真实海域或真实用户参与验证（现场验证）",
    "E4": "有合同、订单、回款、验收报告或复购（商业验证）",
}

# 来源类型受控集合（对齐台账“来源”列与产品就绪度清单）。
SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "public_fact",        # 外部公开事实（官方数据/公开报道）
        "internal_calculation",  # 内部测算/假设
        "interview",          # 用户访谈记录
        "inquiry",            # 供应商询价/报价单
        "policy_document",    # 政策文件原文
        "contract",           # 合同/订单/协议
        "receipt",            # 回款/发票/银行流水
        "acceptance",         # 验收报告/用户签字反馈
        "test_report",        # 测试/评测/自证报告
        "field_record",       # 现场/准现场验证记录
        "assumption",         # 团队假设
        "other",
    }
)


class RegistryError(ValueError):
    """登记表数据不合法（缺字段 / 非法等级 / 非法来源类型 / id 重复）。"""


@dataclass(frozen=True)
class EvidenceRecord:
    """一条机器可读证据记录。

    必填 8 字段与任务书/台账一致；`rule`/`matches`/`notes` 为扫描器豁免
    所需的可选增强字段。
    """

    id: str
    claim: str
    evidence_level: str
    source_type: str
    source_ref: str
    captured_at: str
    review_status: str
    owner: str
    rule: Optional[str] = None          # 豁免哪条红线（check_claims.py 的 rule_id）
    matches: tuple[str, ...] = ()       # 命中特征子串（用于 claim 之外的等价表述）
    notes: str = ""

    def hits(self, text: str) -> bool:
        """该记录是否命中一行文本（claim 子串或 matches 任一子串）。"""
        if self.claim and self.claim in text:
            return True
        return any(m and m in text for m in self.matches)


def _r(
    id_: str,
    claim: str,
    level: str,
    source_type: str,
    source_ref: str,
    captured_at: str,
    review_status: str = "待复核",
    owner: str = "待填",
    rule: Optional[str] = None,
    matches: Iterable[str] = (),
    notes: str = "",
) -> EvidenceRecord:
    return EvidenceRecord(
        id=id_,
        claim=claim,
        evidence_level=level,
        source_type=source_type,
        source_ref=source_ref,
        captured_at=captured_at,
        review_status=review_status,
        owner=owner,
        rule=rule,
        matches=tuple(matches),
        notes=notes,
    )


# ====================================================================
# 纪律记录：把项目当前“红线口径”登记为可查询事实。
# rule 字段 = check_claims.py 的 rule_id；命中即豁免该规则。
# ====================================================================
_DISCIPLINE: list[EvidenceRecord] = [
    _r(
        "R-76-01",
        "合成链路时序误报抑制率约 76%（被过滤检测数 / 输入检测数），不是识别精度或召回率",
        "E1",
        "test_report",
        "ml/scripts/evaluate_opencv.py + edge/detector/README.md",
        "2026-09-18",
        review_status="已复核",
        owner="WP-06",
        rule="seventy_six_as_accuracy",
        matches=("时序链路误报抑制率", "时序抑制率 76%", "76% 时序", "抑制率 76%"),
        notes="76% 只允许表述为时序链路误报抑制率；不得写成识别精度/召回率/准确率。",
    ),
    _r(
        "R-CA-01",
        "coverage_area 无可靠来源时为 NULL/留空（not_available），禁止写 0",
        "E1",
        "test_report",
        "backend/app/services/report.py + backend/tests/test_data_integrity.py",
        "2026-09-19",
        review_status="已复核",
        owner="WP-07",
        rule="coverage_area_zero",
        matches=("coverage_area 可空", "coverage_area.*NULL", "覆盖面积.*留空", "coverage_area.*not_available"),
        notes="WP-07 数据完整性：未统计=null，与真实 0 区分；迁移 downgrade 属历史回退。",
    ),
    _r(
        "R-AG-01",
        "Agent Runtime 默认内存、可选 SQL 持久化，均为 E1 确定性实现，不是生产级、分布式或高可用运行时",
        "E1",
        "test_report",
        "backend/app/services/agents/ + backend/tests/agent_evals/",
        "2026-09-19",
        review_status="已复核",
        owner="WP-01",
        rule="agent_memory_as_prod",
        matches=("E1 内存版", "进程内确定性 Agent Runtime", "本地确定性 Agent Runtime", "内存仓储", "可选 SQL 持久化"),
        notes="只可写“本地确定性 Agent Runtime 与 E1 持久化恢复已实现”；不可写生产级/在线协同/现场自主运行。",
    ),
    _r(
        "R-TR-01",
        "当前无任何成交凭证：全项目禁止“已成交/已签约/已回款/已部署/客户付费”表述",
        "E0",
        "assumption",
        "项目文档/商业证据台账.md §8",
        "2026-09-18",
        review_status="已复核",
        owner="WP-08",
        rule="banned_trade_claim",
        matches=("凭证条目数 = 0", "无任何凭证", "全项目禁止使用上述措辞"),
        notes="措辞红线冻结：上述词只允许出现在带凭证说明的条目中（台账 §8）。",
    ),
    _r(
        "R-OP-01",
        "当前检测为 OpenCV 传统视觉（背景建模+颜色/形状规则），不是 YOLO、视觉大模型或已训练模型",
        "E1",
        "test_report",
        "edge/detector/ + backend/app/services/ai/",
        "2026-09-18",
        review_status="已复核",
        owner="WP-06",
        rule="opencv_as_model",
        matches=("OpenCV 传统视觉", "传统视觉代码", "不是 YOLO"),
        notes="禁止把 OpenCV 写成 YOLO、视觉大模型或已训练模型（手册 §2）。",
    ),
    _r(
        "R-SIM-01",
        "合成/模拟/规划测试与真实海域/真实客户验证严格区分；当前无 E3 现场证据",
        "E1",
        "assumption",
        "项目文档/探海灵眸_项目计划书.md §1/§4.3",
        "2026-09-19",
        review_status="已复核",
        owner="总控",
        rule="sim_as_real",
        matches=("不等于真实海域", "不是现场验证", "不代表真实"),
        notes="禁止把合成/模拟/规划写成真实海域、真实客户或真实部署（手册 §2）。",
    ),
    _r(
        "R-EV-01",
        "证据等级定义 E0-E4（对外表述与计划书 §1 一致：E3=已完成现场验证，E4=已形成商业验证）",
        "E1",
        "policy_document",
        "项目文档/探海灵眸_项目计划书.md §1",
        "2026-09-18",
        review_status="已复核",
        owner="总控",
        rule="unregistered_evidence_level",
        matches=(
            "已形成商业验证",
            "有合同、订单、回款、验收报告或复购",
            "合同、订单、回款、验收报告或复购",
            "真实设备、真实海域或真实用户参与验证",
        ),
        notes="等级定义表属于政策文本，不构成 E3/E4 能力宣称。",
    ),
]

# ====================================================================
# 工程验证记录：软件链路中已形成、可复现的 E1/E2 证据。
# 等级按 evidence-claim-policy.md 冻结口径判定；协议级验收不等于本地
# Nexent 平台侧验收，本地平台侧验收不等于官方托管平台复验或海域验证。
# ====================================================================
_TECHNICAL: list[EvidenceRecord] = [
    _r(
        "R-KN-01",
        "知识进化闭环演示通过：登记 policy/ledger 两类资产、追加 2 个版本、"
        "创建本体版本并抽取 20 个候选节点/40 条候选关系、全部人工审核后发布、"
        "图谱多跳检索 4 命中、创建决策并读取 4 条有序证据链；"
        "E1/E2 软件内部闭环，非海域部署验证或感知精度",
        "E2",
        "test_report",
        "scripts/knowledge_evolution_demo.py + artifacts/evolution-demo/latest.json",
        "2026-09-29",
        review_status="已复核",
        owner="liyongxiang",
        notes="验收命令：.venv/Scripts/python.exe scripts/knowledge_evolution_demo.py "
        "--base-url http://127.0.0.1:8001/api/v1 --username admin --password <redacted>；"
        "trace_id=dtr_20260929003429_9fedc9b1。",
    ),
    _r(
        "R-KN-02",
        "本体候选抽取确定性评测通过：12 份内部合成治理语料上，top-20 中当前实现"
        "100% 为不超过 12 字的短语节点、0 条整句块候选，精确命中内部金标术语 35%"
        "（朴素频次基线 5%），top-100 术语覆盖 100%（基线 95%），并输出带来源证据的"
        "候选关系；top-20 短短语覆盖 40% 低于基线 60%，因基线把整句块当候选可一次"
        "命中多个术语，不据此宣称识别更准；评测为 E1 软件内部确定性结果，不是真实"
        "脱敏行业数据评测、领域准确率或感知精度",
        "E1",
        "test_report",
        "scripts/ontology_eval.py + artifacts/ontology-eval/latest.json",
        "2026-09-29",
        review_status="已复核",
        owner="liyongxiang",
        notes="验收命令：.venv/Scripts/python.exe scripts/ontology_eval.py "
        "--output artifacts/ontology-eval/latest.json；金标为内部 fixture，不是行业标准答案。",
    ),
    _r(
        "R-NX-01",
        "SeaSight 领域认知 MCP 协议级端到端验收通过：未认证请求 401、MCP 初始化、"
        "32 个工具（21 只读常驻 + 11 写入按开关注册）、5 个 Skills、出站令牌自动刷新；"
        "协议级验收不等于本地 Nexent 平台侧验收",
        "E2",
        "test_report",
        "scripts/nexent_acceptance.py + artifacts/nexent-acceptance/latest.json",
        "2026-09-28",
        review_status="已复核",
        owner="WP-15",
        notes="验收命令：.venv-nexent/Scripts/python.exe scripts/nexent_acceptance.py "
        "--report-path artifacts/nexent-acceptance/latest.json。",
    ),
    _r(
        "R-NX-02",
        "本地 Nexent v2.6.1 平台侧验收通过：SeaSight MCP 完成租户注册、21 个工具面加载、"
        "5 个 Skills 导入，并以 nexent_viewer 调用 knowledge_list_assets 返回 200；"
        "平台侧验收不等于海域部署验证、感知精度或官方托管平台复验",
        "E2",
        "test_report",
        "artifacts/nexent-platform-acceptance/latest.yaml + evidence/",
        "2026-09-28",
        review_status="已复核",
        owner="liyongxiang",
        notes="截图与 JSON 见 artifacts/nexent-platform-acceptance/evidence/。",
    ),
    _r(
        "R-NX-03",
        "本地官方源码部署复验：以 Nexent 配置服务 /tool/validate 通过 DB 中 MCP 注册"
        "与授权令牌，由 Nexent 侧真实调用 SeaSight knowledge_list_assets 返回 200；"
        "复验账号为官方内置 suadmin@nexent.com + seasight.acceptance@nexent.com；"
        "灌入知识域演示数据后再次调用返回非空资产列表（total=4）；"
        "本地官方源码部署复验不等于华为托管平台复验、海域部署验证或感知精度",
        "E2",
        "test_report",
        "artifacts/nexent-platform-acceptance/recheck-2026-09-29.yaml + evidence/",
        "2026-09-29",
        review_status="已复核",
        owner="liyongxiang",
        notes="工具调用 JSON 见 evidence/recheck-2026-09-29-tool-call.json 与 "
        "evidence/recheck-2026-09-29-with-data.json；界面截图见 "
        "recheck-2026-09-29-mcp-registered.png / recheck-2026-09-29-mcp-tools-21.png / "
        "recheck-2026-09-29-skills-imported.png。",
    ),

    _r(
        "R-NX-04",
        "本地官方源码部署 Agent 配置/发布证据：创建并发布 seasight-governance-decision-agent，"
        "绑定 5 个 Skill 与 21 个 MCP 工具，调用关系接口返回 21 个 MCP 工具，导出 Agent 配置 ZIP；"
        "未配置 LLM，未跑通完整问答；非华为托管平台验收、非海域验证或感知精度",
        "E2",
        "test_report",
        "artifacts/nexent-platform-acceptance/agent-create-2026-09-29.yaml + evidence/agent-run-*",
        "2026-09-29",
        review_status="已复核",
        owner="liyongxiang",
        notes="证据文件见 agent-create-2026-09-29.yaml（agent_run.json、call_relationship.json、"
        "export.zip 等）；界面截图见 agent-run-detail.png / agent-run-space.png。",
    ),
    _r(
        "R-NX-05",
        "华为托管平台（AgentArts）MCP 验收：注册 SeaSight Domain Cognition MCP，"
        "状态部署成功，21 个只读工具加载；同一公网端点 MCP 初始化、工具列表与 knowledge_list_assets "
        "真实只读调用返回 total=4；托管平台验收不等于海域验证或感知精度",
        "E2",
        "test_report",
        "artifacts/nexent-platform-acceptance/hosted-2026-09-29.yaml + evidence/hosted-2026-09-29-*",
        "2026-09-29",
        review_status="已复核",
        owner="liyongxiang",
        notes="界面截图与 JSON 见 evidence/hosted-2026-09-29-mcp-tools-21.png/json；"
        "公网端点握手与调用轨迹见 hosted-2026-09-29-tunnel-tools.json / hosted-2026-09-29-tool-call.json。",
    ),
    _r(
        "R-NX-06",
        "华为托管平台（AgentArts）Agent 创建验收：创建 seasight-governance-decision-agent，"
        "配置 deepseek-provider/deepseek-chat 模型（API key 已设）与诚实口径系统提示词；"
        "编辑页明确提示公网环境不支持 Skill（按钮 disabled），平台限制已留证；"
        "仅登记模型配置与平台限制验收，不写托管平台已跑通完整 Skill 问答",
        "E2",
        "test_report",
        "artifacts/nexent-platform-acceptance/hosted-agent-2026-09-29.yaml",
        "2026-09-29",
        review_status="已复核",
        owner="liyongxiang",
        notes="MCP 注册与公网端点真实调用由 R-NX-05 独立登记；本记录与 R-NX-05 互补，"
        "分别覆盖托管平台 MCP 层与 Agent 配置层验收。",
    ),
    _r(
        "R-KN-03",
        "本体维护模式确定性对比通过：同一进程内测量，追加 1 个资产版本后全量重抽"
        "中位数 3.364ms、增量追加中位数 1.116ms、时间节省 66.8%；增量模式复用已发布"
        "候选只对新增版本抽取，最终关系仍基于同一份文档全集生成；为 E1 软件内部相对"
        "对比，不是领域准确率、人工审核节省或真实脱敏行业数据评测",
        "E1",
        "test_report",
        "scripts/ontology_incremental_eval.py + artifacts/ontology-eval/incremental-latest.json",
        "2026-09-29",
        review_status="已复核",
        owner="liyongxiang",
        notes="验收命令：.venv/Scripts/python.exe scripts/ontology_incremental_eval.py "
        "--output artifacts/ontology-eval/incremental-latest.json。",
    ),
    _r(
        "R-MG-01",
        "Skill 模板轻量化迁移验证通过：同一套 5 个 Nexent SKILL.md 工作流模板在"
        "海洋治理、医疗、政务三个演示资产源上复用，每领域 3 个资产、候选 36-40 个、"
        "关系 60 条、检索命中 3/3；只替换资产源、领域词表、标准号、问题集与领域角色"
        "映射；为 E1/E2 合成演示语料迁移验证，不是真实脱敏行业数据评测，不代表"
        "生产跨行业迁移已交付",
        "E2",
        "test_report",
        "scripts/skill_migration_validate.py + artifacts/skill-migration/evidence/latest.json",
        "2026-09-29",
        review_status="已复核",
        owner="liyongxiang",
        notes="验收命令：.venv/Scripts/python.exe scripts/skill_migration_validate.py "
        "--output artifacts/skill-migration/evidence/latest.json "
        "--mapping artifacts/skill-migration/skill-migration-mapping.md。",
    ),
    _r(
        "R-KN-04",
        "知识域问答轨迹采集通过：真实后端登录后执行问题检索（mode=ontology_graph、"
        "4 条检索命中）并创建决策，读取 4 条有序证据链，保存 API JSON 与 2 张界面"
        "截图；本次轨迹为 hop_count=0 的直接资产引用检索，不是多跳路径问答、不是"
        "LLM 生成式问答、也不是真实脱敏行业数据评测",
        "E2",
        "test_report",
        "scripts/knowledge_qa_trace_capture.mjs + artifacts/knowledge-qa-trace/latest.json",
        "2026-09-29",
        review_status="已复核",
        owner="liyongxiang",
        notes="trace_id=dtr_20260929070315_4a524e79；截图见 "
        "artifacts/knowledge-qa-trace/01-检索结果-本体图检索与引用.png 与 "
        "02-决策证据链-资产版本引用.png。",
    ),
    _r(
        "R-OD-01",
        "生态环境部公开开放通知本体抽取评测通过：8 份公开通知语料（manifest 含来源 "
        "URL 与 SHA256），全量候选覆盖内部人工标注术语 23/32（71.9%）、关系 3/3"
        "（100%）；top-20 术语覆盖 21.9%（朴素基线 28.1%），top-200 覆盖 71.9%；"
        "top-N 关系命中为 0，因低频关系排在 top-N 之外；语料为公开开放数据，不是真实"
        "脱敏行业数据集，不据此宣称识别更准",
        "E1",
        "test_report",
        "scripts/open_data_eval.py + artifacts/open-data-eval/latest.json + corpus/manifest.json",
        "2026-09-29",
        review_status="已复核",
        owner="liyongxiang",
        notes="验收命令：.venv/Scripts/python.exe scripts/open_data_eval.py "
        "--output artifacts/open-data-eval/latest.json；公开开放数据仅作替代证据，"
        "真实脱敏行业数据评测仍未取得。",
    ),
]

# ====================================================================
# 台账数字镜像：F（外部公开事实）/ C（内部测算）/ T（市场规模假设）/
# S（敏感性）/ E（单位经济性）/ G（升级路线）。
# 与《项目文档/商业证据台账.md》最新版对齐（F-06 于 2026-09-30 复核）；口径变更由总控同步。
# ====================================================================
_LEDGER: list[tuple] = [
    # --- F 类：外部公开事实（乙类，F-06=E3 官方原文已核验；其余 E1=内部引用、原文待补）---
    ("F-01", "2023 年 1—10 月连江全县累计清理海漂垃圾 2.92 万吨（10 个月口径，非年度）", "E1", "public_fact", "docx 1.2 节引用公开报道（人民网福建频道/连江新闻网，链接待补）", "2026-09-18"),
    ("F-02", "连江县泡沫浮球升级改造累计 746.72 万粒（行动方案口径）", "E1", "public_fact", "docx 1.2 节引用《连江县海上养殖转型升级行动方案》，文号/链接待补", "2026-09-18"),
    ("F-03", "传统养殖渔排升级改造塑胶渔排累计 16.56 万口", "E1", "public_fact", "同 F-02（docx 1.2 节；方案原文待补）", "2026-09-18"),
    ("F-04", "马鼻镇“每粒 1 元”泡沫浮球收捡补贴（5 收集点、日均清运卡车 30 余车次）", "E1", "public_fact", "docx 1.2 节引用公开报道（链接待补）", "2026-09-18"),
    ("F-05", "WasteShark 起售价约 2.36 万美元（约 17 万元为 1 USD≈7.2 CNY 折算的 E0 假设）", "E1", "public_fact", "docx 2.1/4.1 节、docs/business-model.md 引用；RanMarine 官网报价页待补", "2026-09-18"),
    ("F-06", "连江海域面积 3112 平方千米、海岸线长达 238 千米（连江县政府官网原文已核验，2026-09-30；原“滩涂约 1.17 万平方千米”不成立）", "E3", "public_fact", "连江县人民政府《连江县情简介》https://www.fzlj.gov.cn/xjwz/zjlj/xqjj/ljjj/200505/t20050510_700838.htm（发布机关：连江县人民政府；来源：连江县政府办；页面 meta PubDate：2026-01-07 10:02）", "2026-09-30"),
    ("F-07", "连江碳汇制度事实：2022-01 首宗海洋渔业碳汇交易、2023-06 首张蓝色碳票、2025-04 首例跨区县认购碳汇交易", "E1", "public_fact", "docx 2.4 节引用公开报道（链接待补）", "2026-09-18"),
    ("F-08", "政策文件清单：连江县海上养殖转型升级行动方案等（文号/原文待补）", "E1", "public_fact", "docx 2.4 节列举；正式文号待补", "2026-09-18"),
    # --- C 类：内部测算（甲类，当前全部 E0=规划假设/内部测算）---
    ("C-01", "350 元/人·天 临水作业人员综合成本假设（工资约 200＋保险约 50＋船油/折旧约 100）", "E0", "internal_calculation", "docs/business-model.md 锚点 A；团队行业常识拆分，无访谈/询价底稿", "2026-09-18"),
    ("C-02", "0.4 吨/人·天 单日人工清理量假设", "E0", "internal_calculation", "docs/business-model.md 锚点 A；团队假设", "2026-09-18"),
    ("C-03", "≈875 元/吨（区间 800～1000）人工每吨清理成本＝350÷0.4", "E0", "internal_calculation", "docs/business-model.md 锚点 A（基于 C-01/C-02）；区间为 ±15% 缓冲假设", "2026-09-18"),
    ("C-04", "≈15,200 元/台 原型机 BOM 成本测算（双体船体 3000＋推进 2500＋边缘盒 1200＋摄像头 500＋打捞机构 3000＋电池 2000＋电气防水 1500＋结构装配 1500）", "E0", "internal_calculation", "docs/business-model.md §2 明细；行业常识估算，需询价验证", "2026-09-18"),
    ("C-05", "≈12,800 元/台 小批量（10 台）BOM 目标成本（目标价口径，非测算实价）", "E0", "internal_calculation", "docs/business-model.md §2", "2026-09-18"),
    ("C-06", "0.8～1.2 万元/台 量产（100 台以上）单台目标成本区间（目标价口径）", "E0", "internal_calculation", "docs/business-model.md §2 注；无询价支撑前不得写成“可达”", "2026-09-18"),
    ("C-07", "≈5,000 元/点位 岸基监测点位成本测算（摄像头 1200＋边缘盒 800＋立杆/供电/安装 3000）", "E0", "internal_calculation", "docs/business-model.md §3；需询价", "2026-09-18"),
    ("C-08", "≈60,000 元/县·年 平台 SaaS 年成本测算（云 15,000＋带宽/存储 5,000＋运维人力 40,000）", "E0", "internal_calculation", "docs/business-model.md §4；运维人力为最大假设项", "2026-09-18"),
    ("C-09", "4,000 元/点位·年 监测服务费测算单价（非成交价）", "E0", "internal_calculation", "docs/business-model.md §5 模式一", "2026-09-18"),
    ("C-10", "650 元/吨 清理服务费测算单价（≈875×0.74，约 7.4 折；非成交价）", "E0", "internal_calculation", "docs/business-model.md §5 模式一", "2026-09-18"),
    ("C-11", "60,000 元/台 设备销售目标价（含一年平台服务，约为进口 1/3；未验证）", "E0", "internal_calculation", "docs/business-model.md §5 模式二；基于 C-04/C-05 成本＋毛利假设倒推", "2026-09-18"),
    ("C-12", "2,500 元/台·月 设备租赁目标价（未验证）", "E0", "internal_calculation", "docs/business-model.md §5 模式二", "2026-09-18"),
    ("C-13", "2～5 万元/年 数据/生态服务目标价（远期延伸收入；当前 0 收入）", "E0", "internal_calculation", "docs/business-model.md §5 模式三", "2026-09-18"),
    ("C-14", "120 吨/年 试点（马鼻＋黄岐 2 乡镇）年清理量假设（±30% 波动）", "E0", "internal_calculation", "docs/business-model.md §6；外生变量，受潮汐/渔汛/气象影响", "2026-09-18"),
    ("C-15", "≈10.1 万元 试点前期硬件投入＝4×1.52 万（C-04）＋8×0.5 万（C-07）＝10.08 万≈10.1 万", "E0", "internal_calculation", "docs/business-model.md §6 重算；随 C-04/C-07 询价结果更新", "2026-09-18"),
    ("C-16", "≈11 万元/年 试点年营收测算＝8×4,000＋120×650（不是收入事实）", "E0", "internal_calculation", "docs/business-model.md §6（基于 C-09/C-10/C-14）", "2026-09-18"),
    ("C-17", "11/33/66 万元 三年回报模型年营收（第 1/2/3 年：试点→推广→全县）", "E0", "internal_calculation", "docs/business-model.md §7；推广假设需试点数据校准", "2026-09-18"),
    ("C-18", "第 2 年回本（累计毛利转正时点测算）", "E0", "internal_calculation", "docs/business-model.md §7/§8；对单价/量/利用率敏感（见 S 表）", "2026-09-18"),
    # --- T 类：TAM/SAM/SOM（全部 E0 假设，非官方数据）---
    ("T-01", "≈3.2 万吨/年（区间 3.0～3.5）连江年清理量年化假设（2.92÷10×12≈3.5，保守取 3.2）", "E0", "internal_calculation", "台账 §4（锚点 F-01）", "2026-09-18"),
    ("T-02", "≈2,080 万元/年 TAM＝连江清运服务费口径上限（3.2 万吨×650 元/吨，理论上限）", "E0", "internal_calculation", "台账 §4（T-01×C-10）", "2026-09-18"),
    ("T-03", "≈66 万元/年 SAM＝连江沿海乡镇复制（≈720 吨/年×650＝46.8 万＋48 点位×4,000＝19.2 万）", "E0", "internal_calculation", "台账 §4（C-14/C-09/C-10；乡镇数 12 为假设）", "2026-09-18"),
    ("T-04", "11 万→33 万→66 万/年 SOM（3 年实际可及，即 C-17 口径）", "E0", "internal_calculation", "台账 §4（C-16/C-17）", "2026-09-18"),
    ("T-05", "≈4.2 亿元/年 福建外推（约 20 县市区×T-02；数量级参考，禁止作为市场规模宣称）", "E0", "internal_calculation", "台账 §4（T-02；禁止宣称）", "2026-09-18"),
    # --- S 类：敏感性分析（全部 E0）---
    ("S-01", "清理服务单价敏感性：−30%＝455 元/吨→营收≈8.7 万回本第 3 年；+30%＝845 元/吨→回本第 2 年", "E0", "internal_calculation", "台账 §6（基准 C-10）", "2026-09-18"),
    ("S-02", "年清理量敏感性：−30%＝84 吨/年；+30%＝156 吨/年（基准 120 吨/年，C-14）", "E0", "internal_calculation", "台账 §6", "2026-09-18"),
    ("S-03", "单台成本敏感性：−30%＝10,640 元/台；+30%＝19,760 元/台（基准 15,200 元/台，C-04）", "E0", "internal_calculation", "台账 §6", "2026-09-18"),
    ("S-04", "利用率敏感性：21/30/39 吨/台·年 → 单吨 ≈1,770/1,240/950 元（基准 E-07）", "E0", "internal_calculation", "台账 §6", "2026-09-18"),
    ("S-05", "人工协同配比敏感性：0.25/0.5/1 人/台 → 单台年成本 ≈22,100/37,100/67,100 元", "E0", "internal_calculation", "台账 §6（基准 E-05）", "2026-09-18"),
    # --- E 类：单位经济性（全部 E0）---
    ("E-01", "≈5,067 元/台·年 设备折旧（15,200÷3 年直线，残值 0；小批量 12,800 时约 4,267）", "E0", "internal_calculation", "台账 §5（C-04 口径）", "2026-09-18"),
    ("E-02", "≈225 元/台·年 能源（1.5 kWh/日×0.6 元/kWh×250 作业日）", "E0", "internal_calculation", "台账 §5", "2026-09-18"),
    ("E-03", "≈1,500 元/台·年 运维（设备价 10%/年）", "E0", "internal_calculation", "台账 §5", "2026-09-18"),
    ("E-04", "≈300 元/台·年 通信（物联网卡）", "E0", "internal_calculation", "台账 §5", "2026-09-18"),
    ("E-05", "≈30,000 元/台·年 人工协同（0.5 人/台×6 万/人·年；最大假设项，需访谈校准）", "E0", "internal_calculation", "台账 §5", "2026-09-18"),
    ("E-06", "≈37,100 元/台·年 单台年成本合计（E-01～E-05 之和）", "E0", "internal_calculation", "台账 §5", "2026-09-18"),
    ("E-07", "30 吨/台·年 试点利用率（120 吨÷4 台，C-14）", "E0", "internal_calculation", "台账 §5", "2026-09-18"),
    ("E-08", "≈1,240 元/吨 试点单吨成本（37,100÷30；高于人工 875，验证期不经济）", "E0", "internal_calculation", "台账 §5", "2026-09-18"),
    ("E-09", "≈250 元/吨 满负荷单吨成本（0.6 吨/台·日×250 日＝150 吨/台·年；37,100÷150）", "E0", "internal_calculation", "台账 §5（0.6 吨/日假设需现场标定）", "2026-09-18"),
    ("E-10", "盈亏平衡利用率：与人工 875 平衡 ≈42 吨/台·年；与目标价 650 平衡 ≈57 吨/台·年", "E0", "internal_calculation", "台账 §5（37,100÷875；37,100÷650）", "2026-09-18"),
    # --- G 类：证据获取与升级路线 ---
    ("G-01", "F-01～F-04、F-07～F-08 补官方原文链接/文件或访谈确认；F-06 已于 2026-09-30 完成官方原文核验", "E0", "assumption", "台账 §7（G 表）", "2026-09-30"),
    ("G-02", "F-05 获取 RanMarine 官网报价页快照或官方询价回复 → 目标 E3（乙类核验）", "E0", "assumption", "台账 §7", "2026-09-18"),
    ("G-03", "C-04～C-08 供应商书面/盖章报价单（含日期、有效期、含税）→ E3 起点", "E0", "assumption", "台账 §7；询价模板 §1–§3", "2026-09-18"),
    ("G-04", "C-01/C-02/C-03 访谈海上环卫＋劳务询价 → E3 起点", "E0", "assumption", "台账 §7；访谈模板 C 类、询价模板 §3", "2026-09-18"),
    ("G-05", "C-09/C-10 付费意愿与预算科目访谈 → E3 起点", "E0", "assumption", "台账 §7；访谈模板 A/B/E 类", "2026-09-18"),
    ("G-06", "C-14/E-07 试点实测清理量与利用率 → E3", "E0", "assumption", "台账 §7；product-readiness 门禁", "2026-09-18"),
    ("G-07", "C-16/C-17/C-18、T/S/E 表以试点真实数据重算 → E3", "E0", "assumption", "台账 §7", "2026-09-18"),
]

_ID_RE_PREFIXES = ("F-", "C-", "T-", "S-", "E-", "G-", "R-")


def build_default_registry() -> list[EvidenceRecord]:
    """构造内嵌登记表：纪律记录 + 台账数字镜像。"""
    records: list[EvidenceRecord] = list(_DISCIPLINE) + list(_TECHNICAL)
    for id_, claim, level, stype, sref, captured in _LEDGER:
        # F-06 已于 2026-09-30 完成官方原文核验，其余台账数字仍待复核。
        review_status = "已复核" if id_ == "F-06" else "待复核"
        owner = "WP-15" if id_ == "F-06" else "待填"
        notes = (
            "F-06 官方原文核验：连江县政府官网《连江县情简介》，访问日期 2026-09-30；"
            "该等级仅指外部事实核验，不代表我方能力达到 E3。"
            if id_ == "F-06"
            else "台账数字镜像：口径与来源以《商业证据台账.md》为准。"
        )
        records.append(
            _r(
                id_,
                claim,
                level,
                stype,
                sref,
                captured,
                review_status=review_status,
                owner=owner,
                notes=notes,
            )
        )
    return records


def validate_records(records: Iterable[EvidenceRecord]) -> list[str]:
    """返回非法记录的错误清单（空 = 全部合法）。"""
    errors: list[str] = []
    seen: set[str] = set()
    for rec in records:
        for f in REQUIRED_FIELDS:
            value = getattr(rec, f)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{rec.id}: 缺少必填字段 {f}")
        if rec.evidence_level not in EVIDENCE_LEVELS:
            errors.append(f"{rec.id}: 非法 evidence_level={rec.evidence_level!r}")
        if rec.source_type not in SOURCE_TYPES:
            errors.append(f"{rec.id}: 非法 source_type={rec.source_type!r}")
        if rec.id in seen:
            errors.append(f"{rec.id}: id 重复")
        seen.add(rec.id)
    return errors


def records_from_mapping(mapping: dict[str, Any]) -> list[EvidenceRecord]:
    """从 YAML/JSON 反序列化记录列表（兼容 intake_template.yaml 结构）。"""
    items = mapping.get("intake_entries") or mapping.get("records")
    if items is None:
        raise RegistryError("登记表文件缺少 intake_entries 或 records 列表")
    records: list[EvidenceRecord] = []
    for item in items:
        if not isinstance(item, dict):
            raise RegistryError(f"登记条目不是字典: {item!r}")
        missing = [f for f in REQUIRED_FIELDS if not item.get(f)]
        if missing:
            raise RegistryError(f"条目 {item.get('id', '<无id>')} 缺少字段: {missing}")
        records.append(
            EvidenceRecord(
                id=str(item["id"]),
                claim=str(item["claim"]),
                evidence_level=str(item["evidence_level"]),
                source_type=str(item["source_type"]),
                source_ref=str(item["source_ref"]),
                captured_at=str(item["captured_at"]),
                review_status=str(item["review_status"]),
                owner=str(item["owner"]),
                rule=item.get("rule"),
                matches=tuple(str(m) for m in (item.get("matches") or ())),
                notes=str(item.get("notes") or ""),
            )
        )
    return records


def load_registry(
    path: Optional[str | Path] = None, *, include_default: bool = True
) -> list[EvidenceRecord]:
    """加载登记表：内嵌默认 + 可选外部 YAML 合并。

    外部文件格式见 `docs/evidence-inbox/intake_template.yaml`
    （顶层 `intake_entries:` 列表，字段与 EvidenceRecord 一致）。
    """
    records: list[EvidenceRecord] = list(build_default_registry()) if include_default else []
    if path:
        p = Path(path)
        if not p.exists():
            raise RegistryError(f"登记表文件不存在: {p}")
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RegistryError(
                f"读取 {p} 需要 PyYAML（.venv-analysis 已自带 pyyaml 6.0.3）；"
                f"未安装时请改用 --registry 传入 JSON 文件"
            ) from exc
        with p.open("r", encoding="utf-8") as fh:
            mapping = yaml.safe_load(fh) or {}
        records.extend(records_from_mapping(mapping))
    errors = validate_records(records)
    if errors:
        raise RegistryError("登记表校验失败：\n  " + "\n  ".join(errors))
    return records


class Registry:
    """面向扫描器的豁免查询接口。

    - `exempt(rule_id, text)`：text 命中任意一条 rule==rule_id 的记录 → 豁免。
    - `cites_registered(text)`：text 引用任意已登记编号（F-/C-/T-/S-/E-/G-/R-）
      → 视为“经登记的证据引用”，豁免无来源数字红线。
    - `records_for(rule_id)`：列出该规则下的登记记录（审计用）。
    """

    def __init__(self, records: Iterable[EvidenceRecord]) -> None:
        self._records: list[EvidenceRecord] = list(records)
        self._by_rule: dict[str, list[EvidenceRecord]] = {}
        for rec in self._records:
            if rec.rule:
                self._by_rule.setdefault(rec.rule, []).append(rec)

    @property
    def records(self) -> list[EvidenceRecord]:
        return list(self._records)

    @property
    def count(self) -> int:
        return len(self._records)

    def exempt(self, rule_id: str, text: str) -> bool:
        for rec in self._by_rule.get(rule_id, ()):
            if rec.hits(text):
                return True
        return False

    def cites_registered(self, text: str) -> bool:
        """text 中是否出现已登记编号（含规则记录与台账镜像编号）。"""
        for rec in self._records:
            token = rec.id
            if not token:
                continue
            # 兼容 "C-16" 与 "C16" 两种写法
            if token in text or token.replace("-", "") in text.replace("－", "-").replace(" ", ""):
                return True
        return False

    def records_for(self, rule_id: str) -> list[EvidenceRecord]:
        return list(self._by_rule.get(rule_id, ()))

    def summary(self) -> dict[str, Any]:
        return {
            "records": self.count,
            "by_rule": {k: len(v) for k, v in sorted(self._by_rule.items())},
            "by_level": {
                lv: sum(1 for r in self._records if r.evidence_level == lv)
                for lv in ("E0", "E1", "E2", "E3", "E4")
            },
        }


def records_to_json(records: Iterable[EvidenceRecord]) -> str:
    return json.dumps(
        {"records": [asdict(r) for r in records], "evidence_levels": EVIDENCE_LEVELS},
        ensure_ascii=False,
        indent=2,
    )


def records_to_yaml(records: Iterable[EvidenceRecord]) -> str:
    """序列化为 intake 同构 YAML（顶层 intake_entries 列表）。"""
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RegistryError("导出 YAML 需要 PyYAML") from exc
    payload = {"schema_version": 1, "intake_entries": [asdict(r) for r in records]}
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evidence_registry.py",
        description="机器可读证据登记表（WP-15）：读取/校验/导出登记记录。",
    )
    parser.add_argument("--registry", help="合并的外部登记表 YAML/JSON 文件")
    parser.add_argument(
        "--no-default",
        action="store_true",
        help="不使用内嵌默认登记表（仅外部文件）",
    )
    parser.add_argument("--validate", action="store_true", help="校验后打印统计并退出")
    parser.add_argument("--list", action="store_true", help="列出全部记录 id")
    parser.add_argument("--export-json", action="store_true", help="导出 JSON 到 stdout")
    parser.add_argument("--export-yaml", action="store_true", help="导出 YAML 到 stdout")
    args = parser.parse_args(argv)

    try:
        records = load_registry(args.registry, include_default=not args.no_default)
        reg = Registry(records)
    except RegistryError as exc:
        print(f"[registry-error] {exc}")
        return 2

    if args.list:
        for rec in records:
            print(f"{rec.id:<8} {rec.evidence_level}  {rec.claim}")
        return 0
    if args.export_json:
        print(records_to_json(records))
        return 0
    if args.export_yaml:
        print(records_to_yaml(records))
        return 0

    # 默认：校验 + 统计
    print(f"登记表记录数：{reg.count}")
    print(f"按证据等级：{reg.summary()['by_level']}")
    print(f"纪律规则豁免映射：{reg.summary()['by_rule']}")
    if args.registry:
        print(f"外部登记表：{args.registry}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
