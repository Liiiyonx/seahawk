"""知识域 LLM 通道：本体候选抽取主通道 + 生成式问答，规则与检索始终兜底。

默认不装配：未配齐 ``KNOWLEDGE_LLM_*`` 三要素（base_url / model / api_key）时
``build_knowledge_llm_client`` 返回 ``None``，抽取与问答走纯规则/纯检索路径，
行为与未引入本模块的历史版本完全一致。测试注入假 ``complete`` 可调用对象，
绝不访问网络。

诚实边界：本模块只负责通道机制（请求装配、schema 校验、合并、兜底、可观测）。
模型质量必须由配好真实端点后的评测脚本给出，规则通道的历史评测数字不因本模块
存在而改变。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.config import settings
from app.services.knowledge import (
    DocumentCandidate,
    TermCandidate,
    _normalize_term,
    cooccurrence_relations,
    extract_term_candidates,
)

logger = logging.getLogger(__name__)

# 与 knowledge._RELATION_TYPE_NAMES 保持一致的关系类型词表（抽取与校验共用）。
RELATION_TYPES: frozenset[str] = frozenset(
    {
        "applies_to",
        "includes",
        "dispatches_to",
        "executes",
        "monitors",
        "uses",
        "associated_with",
        "co_occurs_with",
    }
)

# 与 _entity_type_for_asset 的映射保持一致；LLM 给出词表外的实体类型时回退 concept。
ENTITY_TYPES: frozenset[str] = frozenset(
    {"concept", "metric", "observation", "event", "measurement", "dataset"}
)

# 单次抽取送入模型的文档预算：超限文档截断，防止请求体失控。
PER_DOC_CHAR_BUDGET = 4000
TOTAL_CHAR_BUDGET = 12000

EXTRACTION_SYSTEM_PROMPT = (
    "你是县域海洋环境治理知识库的本体抽取组件。"
    "从给定的资产文档中抽取候选实体术语与候选关系，只输出一个 JSON 对象："
    '{"nodes": [{"term": "...", "entity_type": "concept|metric|observation|event|measurement|dataset",'
    ' "confidence": 0.0-1.0, "evidence_quote": "原文片段"}],'
    ' "relations": [{"source": "术语", "target": "术语",'
    ' "relation_type": "applies_to|includes|dispatches_to|executes|monitors|uses|associated_with|co_occurs_with",'
    ' "confidence": 0.0-1.0, "evidence_quote": "原文片段"}]}。'
    "要求：术语必须是文档中实际出现的领域词汇（如政策条款、设备、乡镇、垃圾类别、业务动作），"
    "不要输出通用词、代词或数字；关系两端必须是 nodes 中出现过的术语；"
    "evidence_quote 必须摘自原文；不要输出 markdown、注释或解释。"
)

QA_SYSTEM_PROMPT = (
    "你是海洋环境治理决策支持组件。只依据提供的检索证据回答问题，"
    "输出一个 JSON 对象："
    '{"answer": "结论性回答，每个关键论断后用 [c:编号] 标注所依据的证据",'
    ' "insufficient_evidence": true|false,'
    ' "cited": [依据的证据编号列表]}。'
    "要求：证据不足时必须置 insufficient_evidence 为 true 并说明缺口，"
    "禁止在无证据引用的前提下给出政策依据或处置动作；"
    "不要输出 markdown、注释或解释。"
)

CompleteFn = Callable[[dict[str, Any]], str]


class LLMChannelError(Exception):
    """LLM 通道任何环节失败时抛出；上层据此回退规则通道并记录原因。"""


@dataclass
class ExtractionOutcome:
    """一次候选抽取的通道结果：节点、合并后的关系与可观测信息。"""

    nodes: list[TermCandidate]
    channel: str  # "llm" | "rule"
    fallback_reason: str | None = None
    model: str | None = None
    llm_relation_specs: list[dict[str, Any]] = field(default_factory=list)
    method_by_canonical: dict[str, str] = field(default_factory=dict)
    confidence_by_canonical: dict[str, float] = field(default_factory=dict)
    entity_type_by_canonical: dict[str, str] = field(default_factory=dict)

    def method_for(self, canonical_name: str) -> str:
        return self.method_by_canonical.get(canonical_name, "rule")

    @property
    def used_llm(self) -> bool:
        return self.channel == "llm"


@dataclass
class QAOutcome:
    """一次生成式问答的通道结果。"""

    answer: str
    insufficient_evidence: bool
    cited_indexes: list[int]
    model: str | None
    fallback_reason: str | None = None
    channel: str = "llm"  # "llm" | "degraded"


@dataclass
class EvidenceQAResult:
    """检索-生成问答的服务层结果：模型回答 + 检索证据原样返回。"""

    answer: str
    insufficient_evidence: bool
    mode: str
    ontology_version_id: str | None
    hits: list[Any]
    cited_indexes: list[int]
    model: str | None
    fallback_reason: str | None
    channel: str


def build_knowledge_llm_client(
    *,
    system_prompt: str,
) -> tuple[Any | None, str | None]:
    """按 KNOWLEDGE_LLM_* 配置装配 OpenAI 兼容客户端。

    返回 ``(client, None)`` 或 ``(None, 缺失原因)``。未启用开关直接返回
    ``(None, None)``——这是正常路径（规则兜底），不是错误。
    """
    if not settings.knowledge_llm_enabled:
        return None, None
    missing = [
        name
        for name, value in (
            ("KNOWLEDGE_LLM_BASE_URL", settings.knowledge_llm_base_url),
            ("KNOWLEDGE_LLM_MODEL", settings.knowledge_llm_model),
        )
        if not str(value or "").strip()
    ]
    if missing:
        return None, f"缺少 {', '.join(missing)}"
    # 延迟导入：未启用时不应为本模块引入 agents 包的依赖链。
    from app.services.agents.model_adapter import OpenAICompatibleModelClient

    client = OpenAICompatibleModelClient(
        base_url=settings.knowledge_llm_base_url,
        model=settings.knowledge_llm_model,
        api_key=settings.knowledge_llm_api_key,
        timeout_ms=settings.knowledge_llm_timeout_ms,
        max_output_tokens=settings.knowledge_llm_max_output_tokens,
        system_prompt=system_prompt,
    )
    return client, None


def _strip_fences(text: str) -> str:
    cleaned = str(text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", cleaned, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return cleaned


def _parse_llm_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(_strip_fences(text))
    except (TypeError, ValueError) as exc:
        raise LLMChannelError(f"模型输出不是合法 JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise LLMChannelError(f"模型输出不是 JSON 对象: {type(payload).__name__}")
    return payload


def _clean_llm_term(raw: Any, *, min_term_length: int) -> str | None:
    if not isinstance(raw, str):
        return None
    term = _normalize_term(raw)
    if not (min_term_length <= len(term) <= 16):
        return None
    if term.isdigit():
        return None
    if not re.fullmatch(r"[\w\u4e00-\u9fff.]+", term):
        return None
    return term


def _confidence(raw: Any, default: float) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return min(0.95, max(0.05, value))


def _resolve_source_doc(
    documents: list[DocumentCandidate], evidence_quote: str, term: str
) -> DocumentCandidate:
    """优先按引文定位来源文档，其次按术语出现，最后取首篇。"""
    quote = " ".join(str(evidence_quote or "").split()).lower()
    if quote:
        for doc in documents:
            if quote in doc.text.lower() or quote in doc.title.lower():
                return doc
    for doc in documents:
        if term in doc.text.lower() or term in doc.title.lower():
            return doc
    return documents[0]


def _truncate_documents(documents: list[DocumentCandidate]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    total = 0
    for doc in documents:
        if total >= TOTAL_CHAR_BUDGET:
            break
        text = doc.text or ""
        if len(text) > PER_DOC_CHAR_BUDGET:
            text = text[:PER_DOC_CHAR_BUDGET] + "…[截断]"
        total += len(text) + len(doc.title or "")
        payload.append(
            {
                "asset_id": doc.asset_id,
                "asset_version_id": doc.asset_version_id,
                "asset_type": doc.asset_type,
                "title": doc.title,
                "text": text,
            }
        )
    return payload


def llm_extract_candidates(
    documents: list[DocumentCandidate],
    *,
    complete: CompleteFn,
    max_nodes: int,
    min_term_length: int,
) -> tuple[list[TermCandidate], list[dict[str, Any]], dict[str, str]]:
    """调用模型抽取候选节点与关系，严格校验后返回。

    任何结构性失败抛 ``LLMChannelError``；部分非法条目静默丢弃。
    返回 ``(节点, 关系 spec, 实体类型映射)``；关系 spec 与
    ``cooccurrence_relations`` 同形，另带 ``extraction_method`` 与
    预计算的 ``confidence``。
    """
    if not documents:
        raise LLMChannelError("没有可抽取的文档")
    payload = {
        "task": "ontology_candidate_extraction",
        "relation_types": sorted(RELATION_TYPES),
        "documents": _truncate_documents(documents),
    }
    try:
        raw = complete(payload)
    except Exception as exc:  # 传输层任何异常都归一为通道失败
        raise LLMChannelError(f"模型调用失败: {exc}") from exc
    parsed = _parse_llm_json(raw)

    doc_by_version = {doc.asset_version_id: doc for doc in documents}
    nodes: list[TermCandidate] = []
    node_confidence: dict[str, float] = {}
    node_entity_type: dict[str, str] = {}
    seen: set[str] = set()
    for item in parsed.get("nodes") or []:
        if not isinstance(item, dict) or len(nodes) >= max_nodes:
            continue
        term = _clean_llm_term(item.get("term"), min_term_length=min_term_length)
        if term is None or term in seen:
            continue
        source_doc = _resolve_source_doc(
            documents, str(item.get("evidence_quote") or ""), term
        )
        confidence = _confidence(item.get("confidence"), default=0.75)
        entity_type = str(item.get("entity_type") or "").strip()
        nodes.append(
            TermCandidate(
                term=term,
                canonical_name=term,
                score=round(confidence * 100, 4),
                source_asset_id=source_doc.asset_id,
                source_version_id=source_doc.asset_version_id,
            )
        )
        seen.add(term)
        node_confidence[term] = confidence
        if entity_type in ENTITY_TYPES:
            node_entity_type[term] = entity_type
    if not nodes:
        raise LLMChannelError("模型未返回任何合法候选术语")

    candidate_by_key = {node.canonical_name: node for node in nodes}
    relations: list[dict[str, Any]] = []
    relation_keys: set[tuple[str, str, str]] = set()
    for item in parsed.get("relations") or []:
        if not isinstance(item, dict):
            continue
        source_key = _clean_llm_term(item.get("source"), min_term_length=min_term_length)
        target_key = _clean_llm_term(item.get("target"), min_term_length=min_term_length)
        relation_type = str(item.get("relation_type") or "").strip()
        if source_key not in candidate_by_key or target_key not in candidate_by_key:
            continue
        if relation_type not in RELATION_TYPES:
            continue
        forward = (source_key, target_key, relation_type)
        reverse = (target_key, source_key, relation_type)
        if forward in relation_keys or reverse in relation_keys:
            continue
        quote = str(item.get("evidence_quote") or "").strip()
        source_doc = doc_by_version.get(
            candidate_by_key[source_key].source_version_id
        ) or documents[0]
        citation = " ".join(quote.split())[:320] or (
            f"{source_key} 与 {target_key} 在资产 {source_doc.asset_id} 中被联合抽取"
        )
        relation_keys.add(forward)
        relations.append(
            {
                "source": candidate_by_key[source_key],
                "target": candidate_by_key[target_key],
                "relation_type": relation_type,
                "count": 1,
                "score": round(_confidence(item.get("confidence"), default=0.75), 4),
                "distance": 0,
                "confidence": _confidence(item.get("confidence"), default=0.75),
                "extraction_method": "llm",
                "evidence": [
                    {
                        "asset_id": source_doc.asset_id,
                        "asset_version_id": source_doc.asset_version_id,
                        "citation": citation,
                    }
                ],
            }
        )
    return nodes, relations, node_entity_type


def extract_candidates(
    documents: list[DocumentCandidate],
    *,
    max_nodes: int,
    min_term_length: int,
    client: Any | None = None,
) -> ExtractionOutcome:
    """抽取编排：LLM 主通道 + 规则兜底合并。

    - ``client is None`` → 纯规则（与历史行为逐位一致）。
    - LLM 成功 → LLM 候选在前，规则候选按 canonical 去重后补位到 ``max_nodes``。
    - LLM 失败 → 整体回退规则通道并记录 ``fallback_reason``。
    """
    rule_nodes = extract_term_candidates(
        documents, max_nodes=max_nodes, min_term_length=min_term_length
    )
    if client is None:
        return ExtractionOutcome(
            nodes=rule_nodes,
            channel="rule",
            method_by_canonical={node.canonical_name: "rule" for node in rule_nodes},
        )

    model_name = getattr(client, "model", None)
    try:
        llm_nodes, llm_relations, llm_entity_types = llm_extract_candidates(
            documents,
            complete=client.complete,
            max_nodes=max_nodes,
            min_term_length=min_term_length,
        )
    except LLMChannelError as exc:
        logger.warning("[Knowledge] LLM 抽取通道失败，回退规则通道: %s", exc)
        return ExtractionOutcome(
            nodes=rule_nodes,
            channel="rule",
            fallback_reason=str(exc),
            model=model_name,
            method_by_canonical={node.canonical_name: "rule" for node in rule_nodes},
        )

    merged: list[TermCandidate] = list(llm_nodes)
    method: dict[str, str] = {node.canonical_name: "llm" for node in llm_nodes}
    confidence: dict[str, float] = {
        node.canonical_name: min(0.95, max(0.05, node.score / 100)) for node in llm_nodes
    }
    for node in rule_nodes:
        if len(merged) >= max_nodes:
            break
        if node.canonical_name in method:
            continue
        merged.append(node)
        method[node.canonical_name] = "rule"
    return ExtractionOutcome(
        nodes=merged,
        channel="llm",
        model=model_name,
        llm_relation_specs=llm_relations,
        method_by_canonical=method,
        confidence_by_canonical=confidence,
        entity_type_by_canonical=llm_entity_types,
    )


def merge_relation_specs(
    llm_specs: list[dict[str, Any]],
    rule_specs: list[dict[str, Any]],
    *,
    limit: int,
    valid_keys: set[str],
) -> list[dict[str, Any]]:
    """关系合并：LLM 关系在前，规则关系补位；双向前缀去重并过滤悬挂引用。"""
    merged: list[dict[str, Any]] = []
    keys: set[tuple[str, str, str]] = set()

    def _push(spec: dict[str, Any], method: str) -> None:
        if len(merged) >= limit:
            return
        source_key = spec["source"].canonical_name
        target_key = spec["target"].canonical_name
        if source_key not in valid_keys or target_key not in valid_keys:
            return
        forward = (source_key, target_key, spec["relation_type"])
        reverse = (target_key, source_key, spec["relation_type"])
        if forward in keys or reverse in keys:
            return
        keys.add(forward)
        enriched = dict(spec)
        enriched["extraction_method"] = method
        merged.append(enriched)

    for spec in llm_specs:
        _push(spec, "llm")
    for spec in rule_specs:
        _push(spec, "rule")
    return merged


async def answer_question_with_evidence(
    *,
    complete: CompleteFn,
    question: str,
    search_payload: dict[str, Any],
) -> QAOutcome:
    """检索-生成问答：把检索证据交给模型，产出带 [c:编号] 引用的回答。

    模型只允许依据证据作答；解析失败或回答为空时抛 ``LLMChannelError``，
    由调用方决定降级输出（附原始检索证据，不伪装成模型结论）。
    """
    evidence: list[dict[str, Any]] = []
    for index, hit in enumerate(search_payload.get("results") or [], start=1):
        evidence.append(
            {
                "index": index,
                "title": hit.get("title"),
                "asset_version_id": hit.get("asset_version_id"),
                "hop_count": hit.get("hop_count", 0),
                "snippet": (hit.get("snippet") or "")[:400],
                "citations": hit.get("citations") or [],
            }
        )
    payload = {
        "task": "evidence_grounding_qa",
        "search_mode": search_payload.get("mode"),
        "question": question,
        "evidence": evidence,
    }
    try:
        raw = complete(payload)
    except Exception as exc:
        raise LLMChannelError(f"模型调用失败: {exc}") from exc
    parsed = _parse_llm_json(raw)
    answer = str(parsed.get("answer") or "").strip()
    if not answer:
        raise LLMChannelError("模型未返回有效回答")
    cited_raw = parsed.get("cited") or []
    cited: list[int] = []
    if isinstance(cited_raw, list):
        for value in cited_raw:
            try:
                index = int(value)
            except (TypeError, ValueError):
                continue
            if 1 <= index <= len(evidence) and index not in cited:
                cited.append(index)
    return QAOutcome(
        answer=answer[:8000],
        insufficient_evidence=bool(parsed.get("insufficient_evidence")),
        cited_indexes=cited,
        model=getattr(complete, "__self__", None) and getattr(complete.__self__, "model", None),
    )
