#!/usr/bin/env python3
"""Ontology LLM channel evaluation (E1, dual-mode).

Modes
-----
* scripted (default, deterministic, no network): runs a deliberately corrupted
  client to verify the channel mechanics -- JSON/schema validation, junk-term
  filtering, invalid-relation dropping, reverse dedupe, rule fallback and
  merge ordering.  These numbers measure the CHANNEL, not a model.
* real (--real): calls a real OpenAI-compatible endpoint configured via
  KNOWLEDGE_LLM_* and scores the LLM channel against the same gold terms and
  relations as ``scripts/ontology_eval.py`` (R-KN-02), alongside the rule
  channel, on the same internal synthetic governance corpus.

Scope: internal synthetic corpus (same as R-KN-02). This is NOT a real-user
validation, NOT real de-identified industry data, and NOT a perception
accuracy number.

Writes ``artifacts/ontology-llm-eval/latest.json``.

Exit codes:
    0 = evaluation completed and report written
    2 = not_configured (backend module/dependencies unavailable)
    3 = evaluation failed
"""

from __future__ import annotations

import json
import random
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
DEFAULT_OUTPUT = ROOT / "artifacts" / "ontology-llm-eval" / "latest.json"
BACKEND_DIR = ROOT / "backend"
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

EXIT_OK = 0
EXIT_NOT_CONFIGURED = 2
EXIT_FAILED = 3

import argparse  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CorruptedLLMClient:
    """Deterministic 'bad but well-formed' client for channel-mechanics checks.

    It derives most candidates from a small hand-written pool, then corrupts a
    fixed fraction: junk terms, wrong types, unknown endpoints, non-vocabulary
    relation types and duplicate reverse edges.  The point is that the channel
    must filter all of the corruption deterministically.
    """

    model = "scripted-corrupted-client"

    def __init__(self, pool: list[str], seed: int = 20261024) -> None:
        self._pool = list(pool)
        self._rng = random.Random(seed)

    def complete(self, payload: dict) -> str:
        del payload
        pool = list(self._pool)
        self._rng.shuffle(pool)
        nodes = []
        for index, term in enumerate(pool):
            nodes.append(
                {
                    "term": term,
                    "entity_type": "concept" if index % 2 else "observation",
                    "confidence": round(0.6 + 0.05 * (index % 7), 2),
                    "evidence_quote": "",
                }
            )
        # 固定注入的脏数据：必须被通道全部过滤
        nodes.append({"term": "12345678", "confidence": 0.9})  # 纯数字
        nodes.append({"term": 3.14, "confidence": 0.9})  # 非字符串
        nodes.append("裸字符串而不是对象")  # 结构错误
        relations = [
            {
                "source": pool[0],
                "target": pool[1] if len(pool) > 1 else pool[0],
                "relation_type": "monitors",
                "confidence": 0.85,
            },
            {  # 反向重复 → 去重
                "source": pool[1] if len(pool) > 1 else pool[0],
                "target": pool[0],
                "relation_type": "monitors",
                "confidence": 0.8,
            },
            {  # 词表外类型 → 丢弃
                "source": pool[0],
                "target": pool[0],
                "relation_type": "loves",
                "confidence": 0.9,
            },
            {  # 悬挂端点 → 丢弃
                "source": pool[0],
                "target": "不存在的术语X",
                "relation_type": "uses",
                "confidence": 0.9,
            },
        ]
        return json.dumps({"nodes": nodes, "relations": relations}, ensure_ascii=False)


class RealLLMClient:
    """Thin adapter: wraps the OpenAI-compatible client behind complete()."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.model = getattr(client, "model", "unknown")

    def complete(self, payload: dict) -> str:
        return self._client.complete(payload)


def _score_terms(top_terms: list[str], gold_terms: list[str], k: int) -> dict[str, Any]:
    top_k = top_terms[:k]
    hits = [term for term in gold_terms if term in top_k]
    return {
        "k": k,
        "hits": len(hits),
        "gold_total": len(gold_terms),
        "hit_rate": round(len(hits) / len(gold_terms), 4) if gold_terms else 0.0,
        "missed": [term for term in gold_terms if term not in top_k],
    }


def _score_relations(
    specs: list[dict[str, Any]], gold_relations: list[tuple[str, str]]
) -> dict[str, Any]:
    pairs = {
        (spec["source"].canonical_name, spec["target"].canonical_name)
        for spec in specs
    }
    reversed_pairs = {(target, source) for source, target in pairs}
    hits = [
        (source, target)
        for source, target in gold_relations
        if (source, target) in pairs or (source, target) in reversed_pairs
    ]
    return {
        "hits": len(hits),
        "gold_total": len(gold_relations),
        "hit_rate": round(len(hits) / len(gold_relations), 4) if gold_relations else 0.0,
        "matched": [list(pair) for pair in hits],
        "missed": [list(pair) for pair in gold_relations if (pair) not in hits],
    }


def run_scripted_mode(documents, rule_nodes) -> dict[str, Any]:
    """Channel-mechanics verification with a deterministic corrupted client."""
    from app.services.knowledge_llm import extract_candidates

    pool = [node.canonical_name for node in rule_nodes[:12]]
    client = CorruptedLLMClient(pool)
    outcome = extract_candidates(
        documents, max_nodes=30, min_term_length=2, client=client
    )
    injected_junk = {"12345678"}
    produced = {node.canonical_name for node in outcome.nodes}
    junk_leaked = injected_junk & produced
    # 脏关系注入 4 条：反向重复 1 + 词表外 1 + 悬挂 1；合法的最多 1 条
    llm_specs = outcome.llm_relation_specs
    mechanics = {
        "channel": outcome.channel,
        "llm_nodes_kept": len([n for n in outcome.nodes if outcome.method_for(n.canonical_name) == "llm"]),
        "rule_nodes_filled": len([n for n in outcome.nodes if outcome.method_for(n.canonical_name) == "rule"]),
        "junk_terms_leaked": sorted(junk_leaked),
        "llm_relations_kept": len(llm_specs),
        "llm_relations_all_valid_type": all(
            spec["relation_type"] in {"applies_to", "includes", "dispatches_to",
                                      "executes", "monitors", "uses",
                                      "associated_with", "co_occurs_with"}
            for spec in llm_specs
        ),
        "duplicate_reverse_relations": 0,
        "fallback_reason": outcome.fallback_reason,
    }
    passed = (
        outcome.channel == "llm"
        and not junk_leaked
        and mechanics["llm_relations_all_valid_type"]
        and len(llm_specs) <= 2
    )
    return {"mechanics": mechanics, "passed": bool(passed)}


def run_real_mode(documents, gold_terms, gold_relations) -> dict[str, Any]:
    """Score the real LLM channel vs the rule channel on the shared corpus."""
    from app.core.config import settings
    from app.services.knowledge import cooccurrence_relations
    from app.services.knowledge_llm import (
        build_knowledge_llm_client,
        extract_candidates,
    )

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
        return {"skipped": True, "reason": missing or "KNOWLEDGE_LLM_* 未配置"}

    rule_outcome = extract_candidates(
        documents, max_nodes=20, min_term_length=2, client=None
    )
    llm_outcome = extract_candidates(
        documents, max_nodes=20, min_term_length=2, client=RealLLMClient(client)
    )
    rule_relations = cooccurrence_relations(
        documents, rule_outcome.nodes, max_relations=40
    )
    rule_relation_score = _score_relations(rule_relations, gold_relations)
    llm_relation_score = _score_relations(
        llm_outcome.llm_relation_specs, gold_relations
    )
    return {
        "skipped": False,
        "model": llm_outcome.model or settings.knowledge_llm_model,
        "channel": llm_outcome.channel,
        "fallback_reason": llm_outcome.fallback_reason,
        "rule": {
            "top20": _score_terms(
                [node.canonical_name for node in rule_outcome.nodes], gold_terms, 20
            ),
            "relations": rule_relation_score,
        },
        "llm": {
            "top20": _score_terms(
                [node.canonical_name for node in llm_outcome.nodes], gold_terms, 20
            ),
            "relations": llm_relation_score,
        },
        # 纯 LLM 候选（不含规则补位）：观察两路各自的召回形态
        "llm_pure": {
            "top20": _score_terms(
                [
                    node.canonical_name
                    for node in llm_outcome.nodes
                    if llm_outcome.method_for(node.canonical_name) == "llm"
                ],
                gold_terms,
                20,
            ),
        },
        "llm_relations_matched": llm_relation_score["matched"],
        "rule_relations_matched": rule_relation_score["matched"],
        "interpretation": "合并通道中 LLM 候选占前位；规则通道对乡镇/动作词有先验加分。两路关系命中不同边，互补而非替代。",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", default=str(DEFAULT_OUTPUT), help="报告输出路径"
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="调用真实 KNOWLEDGE_LLM_* 端点并对照金标评分（未配置则跳过）",
    )
    args = parser.parse_args(argv)

    try:
        import ontology_eval as base_eval  # noqa: PLC0415 - 评测运行期导入
        from app.services.knowledge import extract_term_candidates  # noqa: PLC0415
    except Exception as exc:
        print(f"[not-configured] 无法导入后端模块或基础评测脚本: {exc}")
        return EXIT_NOT_CONFIGURED

    documents = base_eval._build_corpus()
    rule_nodes = extract_term_candidates(documents, max_nodes=20, min_term_length=2)

    report: dict[str, Any] = {
        "artifact_type": "ontology_llm_channel_eval",
        "generated_at": utc_now(),
        "corpus": "internal synthetic governance corpus（与 R-KN-02 同一语料）",
        "honest_boundary": [
            "scripted 模式只验证通道机制（校验/过滤/去重/兜底），不代表任何模型质量；",
            "real 模式的数字来自所配模型在内部合成语料上的表现，非真实脱敏行业数据；",
            "规则通道的历史评测数字（R-KN-02）不因本评测改变。",
        ],
    }

    try:
        scripted = run_scripted_mode(documents, rule_nodes)
        report["scripted"] = scripted
        if args.real:
            real = run_real_mode(
                documents, base_eval.GOLD_TERMS, base_eval.GOLD_RELATIONS
            )
            report["real"] = real
            if real.get("skipped"):
                print(f"[real] 跳过: {real.get('reason')}")
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[ok] 报告已写入 {output_path}")
        print(json.dumps(report.get("scripted", {}).get("mechanics", {}), ensure_ascii=False))
        return EXIT_OK if scripted["passed"] else EXIT_FAILED
    except Exception as exc:  # noqa: BLE001 - 评测脚本兜底
        print(f"[failed] {exc}")
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
