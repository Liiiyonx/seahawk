#!/usr/bin/env python3
"""Dual-channel ontology extraction on the REAL public government corpus.

Runs the knowledge-domain candidate extraction (rule channel vs LLM channel,
R-LLM-01) over the same 8 Ministry of Ecology and Environment public documents
registered by ``scripts/open_data_knowledge_e2e.py`` (R-OD-02).  Unlike
``scripts/ontology_llm_eval.py`` (internal synthetic corpus with gold terms),
this script reports DESCRIPTIVE channel behaviour on real public text:

* per-channel candidate counts and overlap (both / llm_only / rule_only);
* relation counts per channel with relation-type breakdown;
* LLM evidence coverage (relations carrying asset-version citations).

There is NO gold standard here and none is implied: the numbers describe how
the two channels behave on real public text, not accuracy against ground
truth.  Honest boundary: real public government text (E1/E2), NOT real
de-identified industry data, and NOT a perception-accuracy number.

Writes ``artifacts/open-data-llm-channel-eval/latest.json``.

Exit codes: 0 = ok, 2 = not configured (corpus or LLM endpoint missing), 3 = failed.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "artifacts" / "open-data-eval" / "corpus"
MANIFEST = CORPUS_DIR / "manifest.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "open-data-llm-channel-eval" / "latest.json"
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

EXIT_OK = 0
EXIT_NOT_CONFIGURED = 2
EXIT_FAILED = 3

MAX_CONTENT_CHARS = 6000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_corpus() -> list[Any]:
    from app.services.knowledge import DocumentCandidate

    if not MANIFEST.is_file():
        print(f"[not-configured] 缺少语料清单: {MANIFEST}")
        sys.exit(EXIT_NOT_CONFIGURED)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    docs = manifest.get("documents") if isinstance(manifest, dict) else manifest
    if not isinstance(docs, list) or not docs:
        print("[not-configured] 语料清单为空")
        sys.exit(EXIT_NOT_CONFIGURED)
    loaded: list[Any] = []
    for item in docs:
        text_path = CORPUS_DIR / str(item.get("extracted_file") or "")
        if not text_path.is_file():
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")[:MAX_CONTENT_CHARS]
        loaded.append(
            DocumentCandidate(
                asset_id=str(item.get("asset_id") or text_path.stem),
                asset_version_id=f"{item.get('asset_id')}_{item.get('version_no', 1)}",
                title=str(item.get("title") or text_path.stem),
                text=text,
                asset_type="document",
                source_uri=item.get("source_url"),
                standard_codes=list(item.get("standard_codes") or []),
            )
        )
    if not loaded:
        print("[not-configured] 语料文件缺失")
        sys.exit(EXIT_NOT_CONFIGURED)
    return loaded


def channel_stats(nodes: list[Any], specs: list[dict[str, Any]]) -> dict[str, Any]:
    type_counts: dict[str, int] = {}
    for spec in specs:
        rel = spec["relation_type"]
        type_counts[rel] = type_counts.get(rel, 0) + 1
    return {
        "node_count": len(nodes),
        "top_terms": [node.canonical_name for node in nodes][:25],
        "relation_count": len(specs),
        "relation_types": type_counts,
        "relations": [
            {
                "source": spec["source"].canonical_name,
                "target": spec["target"].canonical_name,
                "relation_type": spec["relation_type"],
                "evidence": [
                    {
                        "asset_id": e.get("asset_id"),
                        "asset_version_id": e.get("asset_version_id"),
                        "citation": str(e.get("citation") or "")[:120],
                    }
                    for e in (spec.get("evidence") or [])[:2]
                ],
            }
            for spec in specs[:20]
        ],
    }


def main() -> int:
    from app.core.config import settings
    from app.services.knowledge_llm import (
        build_knowledge_llm_client,
        extract_candidates,
    )

    docs = load_corpus()
    print(f"[corpus] {len(docs)} 份真实公开政务文档")

    rule_outcome = extract_candidates(
        docs, max_nodes=30, min_term_length=2, client=None
    )
    rule = channel_stats(
        rule_outcome.nodes, rule_outcome.nodes and [] or []
    )
    rule_specs: list[dict[str, Any]] = []
    from app.services.knowledge import cooccurrence_relations

    rule_specs = cooccurrence_relations(docs, rule_outcome.nodes, max_relations=40)
    rule = channel_stats(rule_outcome.nodes, rule_specs)

    client, missing = build_knowledge_llm_client(
        system_prompt=(
            "你是县域海洋环境治理知识库的本体抽取组件。从给定资产文档中抽取候选"
            "实体术语与候选关系，只输出一个 JSON 对象："
            '{"nodes": [{"term": "...", "entity_type": "concept|metric|observation|event|measurement|dataset",'
            ' "confidence": 0.0-1.0, "evidence_quote": "原文片段"}],'
            ' "relations": [{"source": "术语", "target": "术语",'
            ' "relation_type": "applies_to|includes|dispatches_to|executes|monitors|uses|associated_with|co_occurs_with",'
            ' "confidence": 0.0-1.0, "evidence_quote": "原文片段"}]}。'
            "术语必须是文档中实际出现的领域词汇；关系两端必须在 nodes 中。"
        )
    )
    if client is None:
        print(f"[not-configured] KNOWLEDGE_LLM_* 未配置: {missing}")
        sys.exit(EXIT_NOT_CONFIGURED)

    # 内联适配：把带 system_prompt 的客户端包装成 complete() 协议
    class _Adapter:
        def __init__(self, inner: Any) -> None:
            self._inner = inner
            self.model = getattr(inner, "model", "unknown")

        def complete(self, payload: dict) -> str:
            return self._inner.complete(payload)

    llm_outcome = extract_candidates(
        docs, max_nodes=30, min_term_length=2, client=_Adapter(client)
    )

    rule_names = {node.canonical_name for node in rule_outcome.nodes}
    llm_names = {
        node.canonical_name
        for node in llm_outcome.nodes
        if llm_outcome.method_for(node.canonical_name) == "llm"
    }
    overlap_report = {
        "both": sorted(rule_names & llm_names),
        "llm_only": sorted(llm_names - rule_names),
        "rule_only_count": len(rule_names - llm_names),
    }
    llm_specs = llm_outcome.llm_relation_specs
    llm = channel_stats(
        [n for n in llm_outcome.nodes if llm_outcome.method_for(n.canonical_name) == "llm"],
        llm_specs,
    )
    with_evidence = sum(1 for spec in llm_specs if spec.get("evidence"))

    report: dict[str, Any] = {
        "artifact_type": "open_data_llm_channel_eval",
        "generated_at": utc_now(),
        "corpus": "8 份生态环境部真实公开文件（R-OD-02 同一语料，来源 URL 与 SHA256 可追溯）",
        "model": llm_outcome.model or settings.knowledge_llm_model,
        "llm_channel": llm_outcome.channel,
        "fallback_reason": llm_outcome.fallback_reason,
        "honest_boundary": [
            "真实公开政务文本（E1/E2），不是真实脱敏行业数据；",
            "无金标评分：本报告描述双通道在真实文本上的行为对照（候选/关系/重叠/证据），"
            "不宣称任何准确率；",
            "规则通道的 R-KN-02 数字不受本报告影响。",
        ],
        "rule": rule,
        "llm": llm,
        "overlap": overlap_report,
        "llm_evidence_coverage": {
            "relations_with_citation": with_evidence,
            "relations_total": len(llm_specs),
        },
    }
    output_path = Path(DEFAULT_OUTPUT)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ok] 报告已写入 {output_path}")
    print(
        f"[rule] nodes={rule['node_count']} relations={rule['relation_count']}"
        f" | [llm] nodes={llm['node_count']} relations={llm['relation_count']}"
        f" (带引用 {with_evidence})"
    )
    print(f"[overlap] both={len(overlap_report['both'])} llm_only={len(overlap_report['llm_only'])}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
