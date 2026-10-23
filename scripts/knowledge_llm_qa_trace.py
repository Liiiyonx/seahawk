#!/usr/bin/env python3
"""Knowledge-domain retrieval-then-generate QA trace capture (E1, dual-mode).

Runs ``KnowledgeService.answer_question`` in-process against an in-memory
SQLite knowledge database seeded with a small demo corpus, and writes the full
trace (question → search mode/hits → answer → cited indexes) to
``artifacts/knowledge-llm-qa-trace/latest.json``.

Modes
-----
* scripted (default, deterministic, no network): a scripted client produces a
  grounded answer (with ``[c:n]`` citations) and an explicit refusal when the
  corpus lacks evidence.  This validates the CHANNEL; the answer text is
  scripted, NOT model-generated.
* real (--real): calls the OpenAI-compatible endpoint configured via
  ``KNOWLEDGE_LLM_*``.  The answers are then model-generated; the report
  records the model name.

Honest boundary: the demo corpus is synthetic demo data (E1).  Neither mode is
a real-user validation or real de-identified industry data.

Exit codes: 0 = ok, 2 = not configured, 3 = failed.
"""

from __future__ import annotations

import asyncio
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
DEFAULT_OUTPUT = ROOT / "artifacts" / "knowledge-llm-qa-trace" / "latest.json"
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

EXIT_OK = 0
EXIT_NOT_CONFIGURED = 2
EXIT_FAILED = 3

import argparse  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


DEMO_DOCS = [
    (
        "连江县海漂垃圾治理工作方案",
        (
            "连江县海漂垃圾治理工作方案明确：岸基摄像头发现泡沫、塑料、渔网等海漂"
            "垃圾后，由值班研判人员复核，再通过派单平台调度打捞机器人或机械臂执行"
            "拾取。拾取完成后回传照片与称重数据，形成处置闭环。"
        ),
    ),
    (
        "马鼻镇海漂垃圾月度台账",
        (
            "马鼻镇海漂垃圾月度台账显示：泡沫聚集次数最多，塑料和渔网占比高，"
            "网绳缠绕风险集中在养殖区。处置资源包括打捞机器人、岸基机械臂和"
            "人工回收队伍。"
        ),
    ),
]

QA_QUESTIONS = [
    {
        "question": "岸基摄像头发现泡沫垃圾后应按什么流程处置？",
        "expectation": "grounded_answer",
        "note": "语料含完整处置链路，模型应引用台账/方案给出带引用回答",
    },
    {
        "question": "辖区内发现疑似漏油事件，按现行政策应如何处置？",
        "expectation": "refusal",
        "note": "语料无任何油污条款，正确行为是明示证据不足并建议人工升级，"
        "与 R-NX-09 本地 Nexent 拒答案例同一叙事",
    },
]


class ScriptedQAClient:
    """Deterministic scripted client: NOT a model, channel verification only."""

    model = "scripted-deterministic-client"

    def complete(self, payload: dict) -> str:
        question = str(payload.get("question") or "")
        evidence = payload.get("evidence") or []
        if "漏油" in question or "油污" in question:
            return json.dumps(
                {
                    "answer": (
                        "现行资产库中不存在针对漏油/油污/溢油的适用政策条款，"
                        "不可套用海漂垃圾处置流程；建议升级人工研判并转报环保或"
                        "海事渠道，不得自动派单。"
                    ),
                    "insufficient_evidence": True,
                    "cited": [],
                },
                ensure_ascii=False,
            )
        cited = [item["index"] for item in evidence[:1]]
        first = evidence[0] if evidence else {}
        return json.dumps(
            {
                "answer": (
                    f"按《{first.get('title', '治理工作方案')}》，岸基摄像头发现泡沫等"
                    f"海漂垃圾后由值班研判人员复核，再派单打捞机器人或机械臂拾取，"
                    f"回传照片与称重数据形成处置闭环 [c:{cited[0] if cited else 1}]。"
                ),
                "insufficient_evidence": False,
                "cited": cited,
            },
            ensure_ascii=False,
        )


async def _build_service():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.db.session import Base
    from app.models.knowledge import (
        DecisionTrace,
        KnowledgeAsset,
        KnowledgeAssetType,
        KnowledgeAssetVersion,
        OntologyNode,
        OntologyRelation,
        OntologyVersion,
    )
    from app.services.knowledge import KnowledgeService

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[
                    KnowledgeAsset.__table__,
                    KnowledgeAssetVersion.__table__,
                    OntologyVersion.__table__,
                    OntologyNode.__table__,
                    OntologyRelation.__table__,
                    DecisionTrace.__table__,
                ],
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    session = factory()
    service = KnowledgeService(session)
    from app.schemas.knowledge import (
        KnowledgeAssetCreate,
        KnowledgeAssetVersionCreate,
    )

    for title, text in DEMO_DOCS:
        await service.create_asset(
            KnowledgeAssetCreate(
                asset_type=KnowledgeAssetType.DOCUMENT,
                title=title,
                township="马鼻镇",
                initial_content=KnowledgeAssetVersionCreate(content_text=text),
            ),
            username="qa-trace",
        )
    return service, engine


async def _publish_demo_ontology(service) -> str:
    """规则通道抽取 → 全量人工审核通过 → 发布，返回可用本体版本 ID。

    发布后检索走 ontology_graph 模式，命中带 hop 路径与引用，
    问答轨迹因此展示『检索-推理双驱动 + 生成式引用』的完整口径。
    """
    from sqlalchemy import select

    from app.models.knowledge import (
        KnowledgeAssetVersion,
        OntologyRelation,
        OntologyReviewStatus,
        OntologyNode,
    )
    from app.schemas.knowledge import (
        OntologyExtractRequest,
        OntologyVersionCreate,
    )

    rows = (await service.session.scalars(select(KnowledgeAssetVersion))).all()
    version_ids = [row.version_id for row in rows]
    ontology = await service.create_ontology_version(
        OntologyVersionCreate(name="qa-trace-ontology"),
        username="qa-trace",
    )
    await service.extract_ontology(
        OntologyExtractRequest(
            ontology_version_id=ontology.version_id,
            asset_version_ids=version_ids,
        ),
        username="qa-trace",
    )
    nodes = (
        await service.session.scalars(
            select(OntologyNode).where(
                OntologyNode.ontology_version_id == ontology.version_id
            )
        )
    ).all()
    for node in nodes:
        if node.review_status != OntologyReviewStatus.APPROVED:
            await service.review_node(
                node.node_id, "approved", username="qa-trace", reason="qa-trace 审核通过"
            )
    relations = (
        await service.session.scalars(
            select(OntologyRelation).where(
                OntologyRelation.ontology_version_id == ontology.version_id
            )
        )
    ).all()
    for relation in relations:
        if relation.review_status != OntologyReviewStatus.APPROVED:
            await service.review_relation(
                relation.relation_id,
                "approved",
                username="qa-trace",
                reason="qa-trace 审核通过",
            )
    published, _counts = await service.publish_ontology(
        ontology.version_id, username="qa-trace"
    )
    return published.version_id


async def _run(mode: bool) -> dict[str, Any]:
    from app.core.config import settings
    from app.schemas.knowledge import KnowledgeQARequest
    from app.services.knowledge_llm import build_knowledge_llm_client

    service, engine = await _build_service()
    try:
        ontology_version_id = await _publish_demo_ontology(service)
        if mode:
            client, missing = build_knowledge_llm_client(
                system_prompt=(
                    "你是海洋环境治理决策支持组件。只依据提供的检索证据回答问题，"
                    "输出 JSON：{\"answer\": \"...[c:编号]\", "
                    "\"insufficient_evidence\": true|false, \"cited\": [编号]}。"
                    "证据不足时必须明示并说明缺口，禁止无引用给政策依据。"
                )
            )
            if client is None:
                return {
                    "skipped": True,
                    "reason": missing or "KNOWLEDGE_LLM_* 未配置",
                }
            label = f"real:{getattr(client, 'model', 'unknown')}"
        else:
            client = ScriptedQAClient()
            label = "scripted-deterministic-client（非真实模型）"

        traces: list[dict[str, Any]] = []
        for item in QA_QUESTIONS:
            result = await service.answer_question(
                KnowledgeQARequest(
                    query=item["question"],
                    limit=5,
                    ontology_version_id=ontology_version_id,
                ),
                llm_client=client,
            )
            traces.append(
                {
                    "question": item["question"],
                    "expectation": item["expectation"],
                    "note": item["note"],
                    "ontology_version_id": result.ontology_version_id,
                    "search_mode": result.mode,
                    "hit_count": len(result.hits),
                    "hits": [
                        {
                            "title": hit.title,
                            "asset_version_id": hit.asset_version_id,
                            "hop_count": hit.hop_count,
                            "snippet": hit.snippet[:160],
                            "citations": hit.citations,
                        }
                        for hit in result.hits
                    ],
                    "answer": result.answer,
                    "insufficient_evidence": result.insufficient_evidence,
                    "cited_indexes": result.cited_indexes,
                    "channel": result.channel,
                    "fallback_reason": result.fallback_reason,
                }
            )
        return {
            "skipped": False,
            "client": label,
            "traces": traces,
        }
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--real", action="store_true", help="使用 KNOWLEDGE_LLM_* 真实端点"
    )
    args = parser.parse_args(argv)

    try:
        report = asyncio.run(_run(args.real))
    except Exception as exc:  # noqa: BLE001
        print(f"[failed] {exc}")
        return EXIT_FAILED

    if report.get("skipped"):
        print(f"[not-configured] {report.get('reason')}")
        return EXIT_NOT_CONFIGURED

    document = {
        "artifact_type": "knowledge_llm_qa_trace",
        "generated_at": utc_now(),
        "mode": report["client"],
        "honest_boundary": [
            "语料为合成演示数据（E1）；本轨迹不代表任何现场验证，也不是真实脱敏行业数据；",
            "scripted 模式的回答文本是确定性脚本，仅验证『检索→生成→引用』链路，"
            "不代表任何模型质量；真实模型轨迹须以 --real 并配置 KNOWLEDGE_LLM_* 重跑。",
        ],
        "traces": report["traces"],
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    grounded = document["traces"][0]
    refusal = document["traces"][1]
    print(f"[ok] 报告已写入 {output_path}")
    print(
        f"[grounded] mode={grounded['search_mode']} hits={grounded['hit_count']} "
        f"cited={grounded['cited_indexes']}"
    )
    print(f"[refusal] insufficient_evidence={refusal['insufficient_evidence']}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
