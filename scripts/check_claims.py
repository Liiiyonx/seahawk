#!/usr/bin/env python
"""宣称扫描器 / 证据门禁（WP-15）。

用途
----
把 E0-E4 证据纪律变成可执行检查，防止计划书、README、答辩材料和代码注释
出现：无来源商业数字、越级宣称（合成/模拟/规划写成真实）、`coverage_area`
无来源写 0、`76%` 冒充识别精度/召回率/准确率、Agent 内存实现写成生产级/
高可用/分布式，以及无凭证的“已成交/已签约/已回款/已部署/客户付费”。

设计要点
--------
1. **登记豁免优先**：每条红线先问 `evidence_registry.Registry` —— 文本命中
   已登记记录（或引用已登记编号）即豁免，再叠加“自限措辞”豁免（不是/仅/
   测算/台账/来源/E0-E4/凭证/禁止 等）。不得仅靠关键词一刀切。
2. **稳定退出码**：0 = 无未登记红线；1 = 存在未登记红线；2 = 参数/读取错误。
   警告级问题当前并入输出（exempted 计数）不改变退出码。
3. **只读扫描**：本脚本不修改任何文件；JSON 摘要输出到 stdout（`--json`）。
4. **默认排除**：.git/.venv*/node_modules/__pycache__/artifacts 等生成物，
   以及本门禁自身的实现与夹具脚本（由 selftest_evidence_gate.py 另行验证）。

用法
----
    python scripts/check_claims.py --root .
    python scripts/check_claims.py --root . --json
    python scripts/check_claims.py --root docs --registry docs/evidence-inbox/xxx.yaml
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# 默认排除（目录或文件名；生成物与门禁自身实现/夹具不参与扫描）
# ---------------------------------------------------------------------------
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".venv-analysis",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "artifacts",
    ".idea",
    ".vscode",
}
DEFAULT_EXCLUDED_FILES = {
    "$null",
    ".harness-status.png",
    "scripts/selftest_result.txt",
    "scripts/selftest_events_result.txt",
    "scripts/selftest_contract_drift.py",
    "scripts/selftest_dispatch_contract.py",
    "scripts/selftest_dispatch_finalize.py",
    "scripts/selftest_events_contract.py",
    "scripts/selftest_consumer_pel.py",
}
# 门禁自身：实现与夹具被默认排除（它们的规则字面量/夹具文本天然命中红线，
# 门禁是否真的会红由 selftest_evidence_gate.py 用夹具单独验证）。
SELF_EXCLUDED = {
    "scripts/evidence_registry.py",
    "scripts/check_claims.py",
    "scripts/selftest_evidence_gate.py",
}
SCAN_EXTENSIONS = {
    ".md",
    ".markdown",
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".jsx",
    ".ts",
    ".vue",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
}
MAX_FILE_BYTES = 2 * 1024 * 1024

# 证据等级标签（出现在文本中 = 自限措辞，属于“已带等级”的合规表述）
_LEVEL_TAG = r"E[0-4]"
# 台账/就绪度编号（登记表编号，用于 cites_registered 之外的兜底）
_LEDGER_ID = r"(?:F|C|T|S|E|G|R|PR)[-－][0-9A-Za-z]{1,3}"


# ---------------------------------------------------------------------------
# 规则定义
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    description: str
    trigger: Any  # callable(line) -> list[str] 命中的片段
    negations: tuple[str, ...] = ()
    window: int = 0  # 回看行数（窗口内出现豁免词也豁免）

    def self_exempt(self, line: str, lookback: str) -> bool:
        if any(n and n in line for n in self.negations):
            return True
        if self.window and lookback:
            return any(n and n in lookback for n in self.negations)
        return False


_MONEY_RE = re.compile(r"\d[\d,．\.]*\s*(?:万元人民币|亿元人民币|万元|亿元|美元|美金|元)")
_QUANTITY_RE = re.compile(r"\d[\d,．\.]*\s*(?:万吨|万粒|万口|吨|台/年|吨/年|吨/台|吨/人|人·天)")
_BUSINESS_KW = (
    "营收",
    "收入",
    "利润",
    "回本",
    "成本",
    "售价",
    "报价",
    "单价",
    "价格",
    "补贴",
    "清运",
    "清理",
    "付费",
    "采购",
    "订单",
    "合同",
    "回款",
    "成交",
    "市场规模",
    "结算",
    "预算",
    "收益",
    "毛利",
    "经费",
    "费率",
    "资金",
    "投入",
    "TAM",
    "SAM",
    "SOM",
)
_UNSOURCED_QUALIFIERS = (
    "来源",
    "台账",
    "编号",
    "测算",
    "假设",
    "目标",
    "折算",
    "引用",
    "口径",
    "锚点",
    "区间",
    "±",
    "无成交",
    "待复核",
    "待核",
    "待获取",
    "待填",
    _LEVEL_TAG,
    "禁止",
    "不得",
    "不允许",
    "非",
    "仅",
    "只",
    "理论上限",
    "数量级",
    "基准",
    "示例",
    "模板",
    "待验证",
    "未验证",
    "参考",
    "基线",
    "上下限",
    "对标",
    "可比",
    "既有",
)
_VOUCHER_RE = re.compile(
    r"(?:合同编号|发票号|回款单号|流水号|协议号|凭证号|凭证)[:：]?\s*[A-Za-z0-9×Xx\-－]{2,}"
    r"|[A-Z]{2,6}[-－][0-9]{3,}"
)
_QUESTION_RE = re.compile(r"[？?]\s*$|是否|多少|多少钱|怎样|怎么|如何|哪些|为何|为什么|合理吗|会吗|能吗|过吗|多久")

_BANNED_TRADE = re.compile(r"已成交|已签约|已回款|已部署|客户付费")
_BANNED_TRADE_NEG = (
    "凭证",
    "禁止",
    "禁用",
    "不得",
    "不允许",
    "不应",
    "不能",
    "不可",
    "不写",
    "未取得",
    "尚未",
    "未获",
    "无凭证",
    "无成交",
    "只允许",
    "只出现",
    "禁",
    "待",
    "E4",
    "合同编号",
    "发票",
    "回款单",
    "银行流水",
    "验收单",
    "盖章",
    "用印",
    "复函",
    "未签",
    "未回款",
    "未部署",
    "示例",
    "模板",
    "占位",
    "缺少",
    "红线",
)

_SIM_TOKENS = ("合成", "模拟", "仿真", "规划", "拟建", "stub", "MD5")
_REAL_TOKENS = ("真实海域", "真实客户", "实际海域", "真船", "现场验收", "现场验证", "已部署", "真实订单", "真实用户", "真实现场")
_AFFIRM_RE = re.compile(r"已|经|于|在|通过|完成|验收|验证|部署|确认|证明|等同|即|就是|达到|实现")
_SIM_AS_REAL_NEG = (
    "不等于",
    "不是",
    "禁止",
    "不得",
    "不代表",
    "仅",
    "只",
    "≠",
    "不可",
    "不能",
    "待",
    "尚未",
    "无真实",
    "未",
    "候选",
    "仍需",
    "需要",
    "将",
    "应",
    "目标",
    "计划",
    "拟",
    "写成",
    "被写成",
    "冒充",
    "伪装",
    "当成",
    "当作",
    "视为",
    "红线",
    "纪律",
    "不以",
    "≠",
)

_COVERAGE_A = re.compile(r"coverage_area\s*=\s*0\b")
_COVERAGE_B = re.compile(r"(?:覆盖面积|coverage_area)\s*(?:为|是|[:：])\s*0\b")
_COVERAGE_NEG = (
    "NULL",
    "null",
    "可空",
    "未统计",
    "无来源",
    "留空",
    "禁止",
    "不得",
    "历史",
    "迁移",
    "恢复",
    "回退",
    "回滚",
    "downgrade",
    "假指标",
    "清除",
    "清理",
    "不是",
    "写成",
    "被写成",
    "not_available",
    "占位",
    "删除",
    "去掉",
    "去除",
)
_COVERAGE_WINDOW_NEG = ("downgrade", "恢复原状", "回退", "回滚", "降级", "可空", "未统计")

_76_RE = re.compile(r"76\s*%")
_76_PRECISION_WORDS = (
    "识别精度",
    "精度",
    "准确率",
    "召回率",
    "precision",
    "recall",
    "accuracy",
    "AP50",
    "F1",
    "泛化",
    "模型精度",
    "识别准确率",
)
_76_NEG = (
    "时序",
    "抑制率",
    "被过滤",
    "分母",
    "不是",
    "≠",
    "非",
    "仅",
    "只",
    "禁止",
    "不得",
    "不代表",
    "待",
    "必须",
    "只能",
    "不能",
    "不可",
    "禁用",
    "写成",
    "被写成",
    "冒充",
    "伪装",
    "当成",
    "当作",
    "口径",
    "边界",
    "待验证",
    "未验证",
)

_MEM_RE = re.compile(r"(?:内存|in[- ]memory|进程内).{0,40}(?:生产级|高可用|分布式|集群|production[- ]grade|high[- ]availability|distributed)")
_MEM_REV = re.compile(r"(?:生产级|高可用|分布式|集群).{0,40}(?:内存|进程内)")
_MEM_NEG = (
    "非",
    "不是",
    "不等于",
    "不代表",
    "仅",
    "只",
    "仍",
    "尚未",
    "待",
    _LEVEL_TAG,
    "确定性",
    "本地",
    "不可写",
    "不能",
    "禁止",
    "不得",
    "候选",
    "当前",
    "边界",
    "未",
    "不具备",
    "不承诺",
    "不声称",
    "写成",
    "被写成",
)

_OCV_RE = re.compile(r"OpenCV.{0,24}(?:YOLO|视觉大模型|已训练模型|深度学习|深度模型)")
_OCV_REV = re.compile(r"(?:YOLO|视觉大模型|已训练模型).{0,24}OpenCV")
_OCV_NEG = (
    "不是",
    "不等于",
    "非",
    "仅",
    "只",
    "禁止",
    "不得",
    "候选",
    "待",
    "备用",
    "备选",
    "接口一致",
    "未来",
    "数据攒够",
    "管线保留",
    "相对",
    "不如",
    "传统",
    "当前",
    "路线",
    "仍",
    "写成",
    "被写成",
    "方案",
    "接口预留",
    "冷启动",
)

_MD5_RE = re.compile(r"MD5.{0,16}(?:推理|模型|检测框|识别|结果)")
_MD5_NEG = ("造假", "stub", "伪", "冒充", "禁止", "不得", "红线", "伪造", "不是", "≠", "仅", "只", "假")

_STATIC_RE = re.compile(r"(?:6 个|六个)智能体.{0,12}(?:在线|协同|运行)|智能体在线协同|N 个智能体在线")
_STATIC_NEG = (
    "不再",
    "删除",
    "禁用",
    "禁止",
    "不得",
    "不写死",
    "移除",
    "已改为",
    "接入真实",
    "真实 API",
    "不展示",
    "不允许",
    "已接入",
    "不是",
    "待",
    "拟",
    "计划",
)

_EV_RE = re.compile(r"(?:E[34]).{0,10}(?:验证|证据|阶段|商业验证)|(?:已|达|完成).{0,6}(?:达到|达成|完成|通过).{0,6}E[34]|现场验证|商业验证|已达 E[34]")
_EV_NEG = (
    "不得",
    "不能",
    "不可",
    "禁止",
    "禁用",
    "待",
    "目标",
    "候选",
    "起点",
    "推向",
    "必须",
    "需要",
    "尚未",
    "未",
    "无",
    "不是",
    "仅",
    "只",
    "拟",
    "将",
    "应",
    "定义",
    "口径",
    "红线",
    "纪律",
    "未取得",
    "未形成",
    "不是事实",
    "写成",
    "被写成",
    "仅用于",
    "术语",
    "不代表",
    "不以",
    "准现场",
    "[ ]",
)


def _make_rules() -> list[Rule]:
    def trigger_unsourced(line: str) -> list[str]:
        hits: list[str] = []
        if _MONEY_RE.search(line):
            hits.append(_MONEY_RE.search(line).group(0))
        elif any(kw in line for kw in _BUSINESS_KW):
            for m in _QUANTITY_RE.finditer(line):
                hits.append(m.group(0))
        return hits

    def trigger_sim_as_real(line: str) -> list[str]:
        if not any(t in line for t in _SIM_TOKENS):
            return []
        if not any(t in line for t in _REAL_TOKENS):
            return []
        if not _AFFIRM_RE.search(line):
            return []
        return [t for t in _REAL_TOKENS if t in line]

    def trigger_76(line: str) -> list[str]:
        if not _76_RE.search(line):
            return []
        if not any(w in line.lower() for w in _76_PRECISION_WORDS):
            return []
        return [_76_RE.search(line).group(0)]

    def trigger_mem(line: str) -> list[str]:
        m = _MEM_RE.search(line) or _MEM_REV.search(line)
        return [m.group(0)] if m else []

    def trigger_ocv(line: str) -> list[str]:
        m = _OCV_RE.search(line) or _OCV_REV.search(line)
        return [m.group(0)] if m else []

    def trigger_md5(line: str) -> list[str]:
        m = _MD5_RE.search(line)
        return [m.group(0)] if m else []

    def trigger_static(line: str) -> list[str]:
        m = _STATIC_RE.search(line)
        return [m.group(0)] if m else []

    def trigger_coverage(line: str) -> list[str]:
        m = _COVERAGE_A.search(line) or _COVERAGE_B.search(line)
        return [m.group(0)] if m else []

    def trigger_ev(line: str) -> list[str]:
        m = _EV_RE.search(line)
        return [m.group(0)] if m else []

    return [
        Rule(
            "banned_trade_claim",
            "无凭证成交/部署宣称",
            "“已成交/已签约/已回款/已部署/客户付费”缺少凭证编号（台账 §8 措辞红线）",
            trigger=lambda line: (
                [m.group(0) for m in _BANNED_TRADE.finditer(line)]
                if not _VOUCHER_RE.search(line)
                else []
            ),
            negations=_BANNED_TRADE_NEG,
        ),
        Rule(
            "unsourced_business_number",
            "无来源商业数字",
            "商业数字（金额/吨量/市场规模）缺少来源、台账编号或测算/假设/等级等自限措辞",
            trigger=trigger_unsourced,
            negations=_UNSOURCED_QUALIFIERS,
        ),
        Rule(
            "sim_as_real",
            "合成/模拟/规划冒充真实",
            "合成、模拟、仿真、规划被写成真实海域/真实客户/现场验收",
            trigger=trigger_sim_as_real,
            negations=_SIM_AS_REAL_NEG,
        ),
        Rule(
            "coverage_area_zero",
            "coverage_area 无来源写 0",
            "coverage_area/覆盖面积 在无可靠来源时被写成 0（应为 NULL/留空）",
            trigger=trigger_coverage,
            negations=_COVERAGE_NEG,
            window=12,
        ),
        Rule(
            "seventy_six_as_accuracy",
            "76% 冒充识别精度",
            "76% 被写成识别精度/召回率/准确率（它只是时序链路误报抑制率）",
            trigger=trigger_76,
            negations=_76_NEG,
        ),
        Rule(
            "agent_memory_as_prod",
            "内存 Agent 冒充生产级",
            "Agent 内存/进程内实现被写成生产级、高可用或分布式",
            trigger=trigger_mem,
            negations=_MEM_NEG,
        ),
        Rule(
            "opencv_as_model",
            "OpenCV 冒充训练模型",
            "OpenCV 传统视觉被写成 YOLO/视觉大模型/已训练模型",
            trigger=trigger_ocv,
            negations=_OCV_NEG,
        ),
        Rule(
            "md5_as_model",
            "MD5 冒充模型输出",
            "MD5 伪结果被写成推理/模型输出/检测框",
            trigger=trigger_md5,
            negations=_MD5_NEG,
        ),
        Rule(
            "static_agents_online",
            "静态智能体冒充在线",
            "静态/写死的智能体状态被写成在线协同运行",
            trigger=trigger_static,
            negations=_STATIC_NEG,
        ),
        Rule(
            "unregistered_evidence_level",
            "未登记 E3/E4 越级宣称",
            "宣称 E3（现场验证）/E4（商业验证）但无登记记录支撑",
            trigger=trigger_ev,
            negations=_EV_NEG,
            window=12,
        ),
    ]


RULES = _make_rules()
RULES_BY_ID = {r.id: r for r in RULES}


# ---------------------------------------------------------------------------
# 扫描核心
# ---------------------------------------------------------------------------
@dataclass
class Finding:
    rule_id: str
    rule_name: str
    severity: str
    path: str
    line: int
    snippet: str
    matched: str
    exempted_by: str = ""


@dataclass
class ScanResult:
    root: Path
    files_scanned: int
    files_skipped: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def red_lines(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "red_line"]

    @property
    def exempted(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "exempted"]

    def to_dict(self, registry_summary: dict[str, Any], scanned_at: str, version: str) -> dict[str, Any]:
        red = self.red_lines
        return {
            "tool": "check_claims.py",
            "version": version,
            "root": str(self.root),
            "scanned_at": scanned_at,
            "registry": registry_summary,
            "files": {"scanned": self.files_scanned, "skipped": self.files_skipped},
            "summary": {
                "red_lines": len(red),
                "exempted_occurrences": len(self.exempted),
                "clean": len(red) == 0,
            },
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "rule_name": f.rule_name,
                    "severity": f.severity,
                    "file": f.path,
                    "line": f.line,
                    "snippet": f.snippet,
                    "matched": f.matched,
                    "exempted_by": f.exempted_by,
                }
                for f in self.findings
            ],
            "exit_code": 0 if not red else 1,
        }


def iter_target_files(root: Path, extra_excludes: Iterable[str] = ()) -> tuple[list[Path], int]:
    excluded_dirs = set(DEFAULT_EXCLUDED_DIRS)
    excluded_files = set(DEFAULT_EXCLUDED_FILES) | SELF_EXCLUDED | set(extra_excludes)
    files: list[Path] = []
    skipped = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts = set(p.parts)
        if parts & excluded_dirs:
            skipped += 1
            continue
        if p.name in excluded_files or rel in excluded_files:
            skipped += 1
            continue
        if p.suffix.lower() not in SCAN_EXTENSIONS:
            skipped += 1
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                skipped += 1
                continue
        except OSError:
            skipped += 1
            continue
        files.append(p)
    return files, skipped


def read_lines(p: Path) -> list[str]:
    try:
        data = p.read_bytes()
    except OSError:
        return []
    if b"\x00" in data[:8192]:
        return []
    return data.decode("utf-8", errors="replace").splitlines()


def scan_file(
    p: Path,
    registry: Any,
    root: Path,
    out: list[Finding],
) -> None:
    lines = read_lines(p)
    rel = p.relative_to(root).as_posix()
    lookback = ""
    recent: list[str] = []
    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith(("|---", "| ---")):
            recent.append(raw)
            continue
        if _QUESTION_RE.search(line):
            recent.append(raw)
            continue
        lookback = "\n".join(recent[-12:]) if recent else ""
        for rule in RULES:
            matched = rule.trigger(line)
            if not matched:
                continue
            snippet = line[:160]
            if registry is not None and registry.exempt(rule.id, line):
                out.append(
                    Finding(
                        rule.id, rule.name, "exempted", rel, idx, snippet,
                        " / ".join(matched), f"registry:{rule.id}",
                    )
                )
                continue
            if rule.id == "unsourced_business_number" and registry is not None and registry.cites_registered(line):
                out.append(
                    Finding(
                        rule.id, rule.name, "exempted", rel, idx, snippet,
                        " / ".join(matched), "registry:cites_registered",
                    )
                )
                continue
            if rule.self_exempt(line, lookback):
                out.append(
                    Finding(
                        rule.id, rule.name, "exempted", rel, idx, snippet,
                        " / ".join(matched), "self_limiting",
                    )
                )
                continue
            out.append(
                Finding(
                    rule.id, rule.name, "red_line", rel, idx, snippet,
                    " / ".join(matched), "",
                )
            )
        recent.append(raw)


def scan_root(root: Path, registry: Any, extra_excludes: Iterable[str] = ()) -> ScanResult:
    files, skipped = iter_target_files(root, extra_excludes)
    result = ScanResult(root=root, files_scanned=len(files), files_skipped=skipped)
    for p in files:
        scan_file(p, registry, root, result.findings)
    return result


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def render_summary(result: ScanResult, registry_summary: dict[str, Any]) -> str:
    lines_out: list[str] = []
    red = result.red_lines
    lines_out.append("== 探海灵眸 SeaSight 宣称扫描器（WP-15 证据门禁）==")
    lines_out.append(f"规则：{len(RULES)} 条红线；登记表：{registry_summary['records']} 条"
                     f"（外部 {registry_summary.get('external', 0)}）")
    lines_out.append(f"扫描目录：{result.root}")
    lines_out.append(f"扫描文件：{result.files_scanned}（跳过 {result.files_skipped}）")
    lines_out.append("")
    lines_out.append("== 红线统计 ==")
    by_rule: dict[str, list[Finding]] = {}
    for f in red:
        by_rule.setdefault(f.rule_id, []).append(f)
    for rule in RULES:
        n = len(by_rule.get(rule.id, []))
        lines_out.append(f"  {rule.id:<32} {rule.name:<22} {n}")
    lines_out.append("")
    if red:
        lines_out.append("== 红线明细 ==")
        for f in red:
            lines_out.append(f"[RED] {f.rule_id}  {f.path}:{f.line}")
            lines_out.append(f"      {f.snippet}")
            lines_out.append(f"      命中：{f.matched}")
        lines_out.append("")
        lines_out.append(f"== 结论 ==\nFOUND {len(red)} RED LINE(S) —— 存在未登记红线（exit code 1）")
    else:
        lines_out.append(f"== 结论 ==\nCLEAN —— 未发现未登记红线（exit code 0）")
    return "\n".join(lines_out)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_claims.py",
        description="宣称扫描器 / 证据门禁（WP-15）：扫描无来源数字、越级宣称与幻觉指标。",
    )
    parser.add_argument("--root", default=str(ROOT), help="扫描根目录（默认仓库根）")
    parser.add_argument("--registry", help="合并的外部登记表 YAML（见 docs/evidence-inbox/）")
    parser.add_argument("--exclude", action="append", default=[], help="额外排除的相对路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON 到 stdout")
    parser.add_argument("--no-default-registry", action="store_true", help="不使用内嵌登记表")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[error] 扫描根目录不存在: {root}", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"[error] 扫描根不是目录: {root}", file=sys.stderr)
        return 2

    from evidence_registry import Registry, load_registry, RegistryError

    try:
        records = load_registry(args.registry, include_default=not args.no_default_registry)
        registry: Optional[Registry] = Registry(records)
    except RegistryError as exc:
        print(f"[error] 登记表加载失败: {exc}", file=sys.stderr)
        return 2

    result = scan_root(root, registry, args.exclude)
    reg_summary = registry.summary()
    reg_summary["external"] = 1 if args.registry else 0
    scanned_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if args.json:
        print(json.dumps(result.to_dict(reg_summary, scanned_at, VERSION), ensure_ascii=False, indent=2))
    else:
        print(render_summary(result, reg_summary))
    return 0 if not result.red_lines else 1


if __name__ == "__main__":
    sys.exit(main())
