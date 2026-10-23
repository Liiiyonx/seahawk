"""知识域 LLM 通道回归测试（抽取主通道 + 检索-生成问答）。

全部注入假客户端，不访问网络。守四件事：
1. 未启用/未配置时与历史纯规则行为逐位一致；
2. LLM 输出经严格 schema 校验，任何失败都回退规则通道并留 fallback_reason；
3. LLM 候选与规则候选合并时按 canonical 去重、关系双向前缀去重、悬挂引用被过滤；
4. 生成式问答只依据检索证据作答，降级输出绝不伪装成模型结论。
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.exceptions import AppException
from app.db.session import Base
from app.models.knowledge import (
    KnowledgeAsset,
    KnowledgeAssetType,
    KnowledgeAssetVersion,
    OntologyNode,
    OntologyRelation,
    OntologyVersion,
)
from app.schemas.knowledge import (
    KnowledgeAssetCreate,
    KnowledgeAssetVersionCreate,
    KnowledgeQARequest,
    KnowledgeSearchRequest,
    OntologyExtractRequest,
    OntologyVersionCreate,
)
from app.services.knowledge import (
    DocumentCandidate,
    KnowledgeService,
    extract_term_candidates,
)
from app.services.knowledge_llm import (
    ExtractionOutcome,
    LLMChannelError,
    build_knowledge_llm_client,
    extract_candidates,
    merge_relation_specs,
)

DOC_CORPUS = DocumentCandidate(
    asset_id="asset-1",
    asset_version_id="ver-1",
    title="马鼻镇海漂垃圾治理方案",
    text=(
        "岸基摄像头发现泡沫漂浮物后，值班研判形成事件，随后派单打捞机器人前往处置。"
        "打捞机器人搭载机械臂，可拾取网绳缠绕垃圾，称重回执后形成处置闭环。"
        "泡沫与塑料瓶属于高频海漂垃圾，回收队伍负责岸基精分。"
    ),
    asset_type="document",
    source_uri=None,
)


class FakeLLMClient:
    """可编程假客户端：按 task 路由固定响应，可注入异常。"""

    model = "fake-ontology-model"

    def __init__(
        self,
        extraction_response: object | None = None,
        qa_response: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self.extraction_response = extraction_response
        self.qa_response = qa_response
        self.error = error
        self.calls: list[dict] = []

    def complete(self, payload: dict) -> str:
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        task = payload.get("task")
        response = (
            self.extraction_response
            if task == "ontology_candidate_extraction"
            else self.qa_response
        )
        if isinstance(response, str):
            return response  # 已是原始模型输出（如带 markdown 围栏）
        return json.dumps(response, ensure_ascii=False)


@pytest_asyncio.fixture
async def knowledge_session() -> AsyncSession:
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
                ],
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ----------------------------------------------------------------------
# 通道编排：extract_candidates
# ----------------------------------------------------------------------


def test_rule_channel_when_client_is_none() -> None:
    outcome = extract_candidates(
        [DOC_CORPUS], max_nodes=20, min_term_length=2, client=None
    )
    assert isinstance(outcome, ExtractionOutcome)
    assert outcome.channel == "rule"
    assert outcome.fallback_reason is None
    assert outcome.nodes == extract_term_candidates(
        [DOC_CORPUS], max_nodes=20, min_term_length=2
    )
    assert all(
        outcome.method_for(node.canonical_name) == "rule" for node in outcome.nodes
    )


def test_llm_channel_takes_priority_and_rule_fills() -> None:
    fake = FakeLLMClient(
        extraction_response={
            "nodes": [
                {
                    "term": "泡沫浮球",
                    "entity_type": "observation",
                    "confidence": 0.9,
                    "evidence_quote": "岸基摄像头发现泡沫漂浮物",
                },
                {"term": "应急联动", "confidence": 0.6},
            ],
            "relations": [
                {
                    "source": "泡沫浮球",
                    "target": "应急联动",
                    "relation_type": "monitors",
                    "confidence": 0.8,
                    "evidence_quote": "岸基摄像头发现泡沫漂浮物",
                }
            ],
        }
    )
    outcome = extract_candidates(
        [DOC_CORPUS], max_nodes=8, min_term_length=2, client=fake
    )
    assert outcome.channel == "llm"
    assert outcome.model == "fake-ontology-model"
    # LLM 候选在前，规则候选去重后补位
    assert outcome.nodes[0].canonical_name == "泡沫浮球"
    assert outcome.method_for("泡沫浮球") == "llm"
    assert outcome.method_for("应急联动") == "llm"
    rule_names = {node.canonical_name for node in outcome.nodes} - {
        "泡沫浮球",
        "应急联动",
    }
    assert rule_names, "规则候选应补位"
    assert all(outcome.method_for(name) == "rule" for name in rule_names)
    assert outcome.entity_type_by_canonical["泡沫浮球"] == "observation"
    assert 0.85 <= outcome.confidence_by_canonical["泡沫浮球"] <= 0.95
    assert len(outcome.llm_relation_specs) == 1
    spec = outcome.llm_relation_specs[0]
    assert spec["relation_type"] == "monitors"
    assert spec["extraction_method"] == "llm"
    assert spec["evidence"][0]["asset_id"] == "asset-1"


def test_llm_garbage_falls_back_to_rule_with_reason() -> None:
    fake = FakeLLMClient(extraction_response="这不是JSON")
    outcome = extract_candidates(
        [DOC_CORPUS], max_nodes=20, min_term_length=2, client=fake
    )
    assert outcome.channel == "rule"
    assert outcome.fallback_reason is not None and "JSON" in outcome.fallback_reason
    assert outcome.nodes == extract_term_candidates(
        [DOC_CORPUS], max_nodes=20, min_term_length=2
    )


def test_llm_transport_error_falls_back() -> None:
    fake = FakeLLMClient(error=RuntimeError("connection refused"))
    outcome = extract_candidates(
        [DOC_CORPUS], max_nodes=20, min_term_length=2, client=fake
    )
    assert outcome.channel == "rule"
    assert outcome.fallback_reason is not None and "模型调用失败" in outcome.fallback_reason


def test_llm_empty_nodes_falls_back() -> None:
    fake = FakeLLMClient(extraction_response={"nodes": [], "relations": []})
    outcome = extract_candidates(
        [DOC_CORPUS], max_nodes=20, min_term_length=2, client=fake
    )
    assert outcome.channel == "rule"
    assert outcome.fallback_reason is not None and "候选术语" in outcome.fallback_reason


def test_llm_markdown_fence_is_tolerated() -> None:
    payload = json.dumps(
        {
            "nodes": [{"term": "岸基精分", "confidence": 0.8}],
            "relations": [],
        },
        ensure_ascii=False,
    )
    fake = FakeLLMClient(extraction_response=f"```json\n{payload}\n```")
    outcome = extract_candidates(
        [DOC_CORPUS], max_nodes=10, min_term_length=2, client=fake
    )
    assert outcome.channel == "llm"
    assert "岸基精分" in {node.canonical_name for node in outcome.nodes}


def test_llm_relation_validation_drops_invalid() -> None:
    fake = FakeLLMClient(
        extraction_response={
            "nodes": [
                {"term": "泡沫浮球", "confidence": 0.9},
                {"term": "打捞机器人", "confidence": 0.9},
            ],
            "relations": [
                # 端点不在 nodes 中 → 丢弃
                {
                    "source": "泡沫浮球",
                    "target": "回收队伍",
                    "relation_type": "uses",
                },
                # 词表外关系类型 → 丢弃
                {
                    "source": "泡沫浮球",
                    "target": "打捞机器人",
                    "relation_type": "loves",
                },
                # 合法
                {
                    "source": "打捞机器人",
                    "target": "泡沫浮球",
                    "relation_type": "monitors",
                    "confidence": 0.85,
                },
                # 与上一条互为反向 → 去重丢弃
                {
                    "source": "泡沫浮球",
                    "target": "打捞机器人",
                    "relation_type": "monitors",
                },
            ],
        }
    )
    outcome = extract_candidates(
        [DOC_CORPUS], max_nodes=10, min_term_length=2, client=fake
    )
    assert len(outcome.llm_relation_specs) == 1
    assert outcome.llm_relation_specs[0]["source"].canonical_name == "打捞机器人"


def test_merge_relation_specs_filters_and_dedupes() -> None:
    from app.services.knowledge import TermCandidate

    left = TermCandidate("左", "左", 1.0, "asset", "ver")
    right = TermCandidate("右", "右", 1.0, "asset", "ver")
    outside = TermCandidate("外", "外", 1.0, "asset", "ver")
    llm_specs = [
        {
            "source": left,
            "target": right,
            "relation_type": "uses",
            "count": 1,
            "score": 0.9,
            "distance": 0,
            "evidence": [],
        },
        {
            "source": left,
            "target": outside,  # 悬挂引用 → 过滤
            "relation_type": "uses",
            "count": 1,
            "score": 0.9,
            "distance": 0,
            "evidence": [],
        },
    ]
    rule_specs = [
        {
            "source": right,
            "target": left,  # 与 LLM 互为反向 → 去重
            "relation_type": "uses",
            "count": 3,
            "score": 2.0,
            "distance": 4,
            "evidence": [],
        },
        {
            "source": left,
            "target": outside,
            "relation_type": "includes",  # 不同类型但端点悬挂 → 过滤
            "count": 1,
            "score": 1.0,
            "distance": 2,
            "evidence": [],
        },
    ]
    merged = merge_relation_specs(
        llm_specs, rule_specs, limit=10, valid_keys={"左", "右"}
    )
    assert len(merged) == 1
    assert merged[0]["extraction_method"] == "llm"

    only_rule = merge_relation_specs([], rule_specs, limit=10, valid_keys={"左", "右", "外"})
    assert [spec["extraction_method"] for spec in only_rule] == ["rule", "rule"]

    capped = merge_relation_specs(llm_specs, [], limit=1, valid_keys={"左", "右", "外"})
    assert len(capped) == 1


# ----------------------------------------------------------------------
# 服务集成：extract_ontology 携带通道信息
# ----------------------------------------------------------------------


async def _seed_asset_and_ontology(service: KnowledgeService):
    _asset, version = await service.create_asset(
        KnowledgeAssetCreate(
            asset_type=KnowledgeAssetType.DOCUMENT,
            title="马鼻镇海漂垃圾治理方案",
            township="马鼻镇",
            initial_content=KnowledgeAssetVersionCreate(
                content_text=(
                    "岸基摄像头发现泡沫漂浮物后，值班研判形成事件，随后派单打捞机器人前往处置。"
                    "打捞机器人搭载机械臂，可拾取网绳缠绕垃圾，称重回执后形成处置闭环。"
                )
            ),
        ),
        username="operator-a",
    )
    ontology = await service.create_ontology_version(
        OntologyVersionCreate(name="llm-channel-test"),
        username="operator-a",
    )
    return version, ontology


@pytest.mark.asyncio
async def test_extract_ontology_with_llm_marks_provenance(
    knowledge_session: AsyncSession,
) -> None:
    service = KnowledgeService(knowledge_session)
    version, ontology = await _seed_asset_and_ontology(service)
    fake = FakeLLMClient(
        extraction_response={
            "nodes": [
                {"term": "泡沫浮球", "entity_type": "observation", "confidence": 0.9},
            ],
            "relations": [],
        }
    )
    result = await service.extract_ontology(
        OntologyExtractRequest(
            ontology_version_id=ontology.version_id,
            asset_version_ids=[version.version_id],
        ),
        username="operator-a",
        llm_client=fake,
    )
    _version, nodes, relations, _node_count, _relation_count = result
    methods = {node.canonical_name: node.properties_json["extraction_method"] for node in nodes}
    assert methods["泡沫浮球"] == "llm"
    rule_marked = [name for name, method in methods.items() if method == "rule"]
    assert rule_marked, "规则候选应补位并标记 rule"
    llm_node = next(node for node in nodes if node.canonical_name == "泡沫浮球")
    assert llm_node.entity_type == "observation"
    assert _version.metadata_json["extraction_channel"] == "llm"
    assert _version.metadata_json["extraction_model"] == "fake-ontology-model"
    for relation in relations:
        assert relation.properties_json["extraction_method"] in {"llm", "rule"}


@pytest.mark.asyncio
async def test_extract_ontology_rule_channel_metadata(
    knowledge_session: AsyncSession,
) -> None:
    service = KnowledgeService(knowledge_session)
    version, ontology = await _seed_asset_and_ontology(service)
    _version, _nodes, _relations, _nc, _rc = await service.extract_ontology(
        OntologyExtractRequest(
            ontology_version_id=ontology.version_id,
            asset_version_ids=[version.version_id],
        ),
        username="operator-a",
    )
    assert _version.metadata_json["extraction_channel"] == "rule"
    assert "extraction_fallback_reason" not in _version.metadata_json


@pytest.mark.asyncio
async def test_extract_ontology_fallback_reason_recorded(
    knowledge_session: AsyncSession,
) -> None:
    service = KnowledgeService(knowledge_session)
    version, ontology = await _seed_asset_and_ontology(service)
    fake = FakeLLMClient(error=RuntimeError("timeout"))
    _version, _nodes, _relations, _nc, _rc = await service.extract_ontology(
        OntologyExtractRequest(
            ontology_version_id=ontology.version_id,
            asset_version_ids=[version.version_id],
        ),
        username="operator-a",
        llm_client=fake,
    )
    assert _version.metadata_json["extraction_channel"] == "rule"
    assert "timeout" in (_version.metadata_json.get("extraction_fallback_reason") or "")


# ----------------------------------------------------------------------
# 生成式问答
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_answer_question_requires_client(knowledge_session: AsyncSession) -> None:
    service = KnowledgeService(knowledge_session)
    with pytest.raises(AppException) as error:
        await service.answer_question(
            KnowledgeQARequest(query="泡沫怎么处置？"),
        )
    assert error.value.code == 7011


@pytest.mark.asyncio
async def test_answer_question_grounds_on_retrieved_evidence(
    knowledge_session: AsyncSession,
) -> None:
    service = KnowledgeService(knowledge_session)
    version, _ontology = await _seed_asset_and_ontology(service)
    del version
    fake = FakeLLMClient(
        qa_response={
            "answer": "泡沫漂浮物由打捞机器人处置 [c:1]。",
            "insufficient_evidence": False,
            "cited": [1, 99],
        }
    )
    result = await service.answer_question(
        KnowledgeQARequest(query="泡沫漂浮物由谁处置？"),
        llm_client=fake,
    )
    assert result.channel == "llm"
    assert result.cited_indexes == [1], "越界引用应被过滤"
    assert result.insufficient_evidence is False
    assert result.fallback_reason is None
    assert result.hits, "检索命中应随答返回"
    # 模型只应看到检索证据，不看到任何工具或自由文本
    assert fake.calls[0]["task"] == "evidence_grounding_qa"
    assert all("evidence_quote" not in item for item in fake.calls[0]["evidence"])


@pytest.mark.asyncio
async def test_answer_question_degrades_on_model_failure(
    knowledge_session: AsyncSession,
) -> None:
    service = KnowledgeService(knowledge_session)
    version, _ontology = await _seed_asset_and_ontology(service)
    del version
    fake = FakeLLMClient(error=RuntimeError("rate limited"))
    result = await service.answer_question(
        KnowledgeQARequest(query="泡沫漂浮物由谁处置？"),
        llm_client=fake,
    )
    assert result.channel == "degraded"
    assert result.insufficient_evidence is True
    assert "原始证据" in result.answer
    assert "rate limited" in (result.fallback_reason or "")


@pytest.mark.asyncio
async def test_answer_question_passes_through_refusal(
    knowledge_session: AsyncSession,
) -> None:
    service = KnowledgeService(knowledge_session)
    version, _ontology = await _seed_asset_and_ontology(service)
    del version
    fake = FakeLLMClient(
        qa_response={
            "answer": "现行资产库无适用政策条款，应升级人工研判 [c:1]。",
            "insufficient_evidence": True,
            "cited": [],
        }
    )
    result = await service.answer_question(
        KnowledgeQARequest(query="漏油事件怎么处置？"),
        llm_client=fake,
    )
    assert result.insufficient_evidence is True
    assert "升级人工研判" in result.answer


def test_answer_question_with_evidence_rejects_bad_json() -> None:
    from app.services.knowledge_llm import answer_question_with_evidence

    class Bare:
        def complete(self, payload: dict) -> str:
            return "[]"

    async def _run() -> None:
        with pytest.raises(LLMChannelError):
            await answer_question_with_evidence(
                complete=Bare().complete,
                question="q",
                search_payload={"mode": "keyword", "results": []},
            )

    asyncio.run(_run())


# ----------------------------------------------------------------------
# 客户端装配
# ----------------------------------------------------------------------


def test_client_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "knowledge_llm_enabled", False)
    client, missing = build_knowledge_llm_client(system_prompt="p")
    assert client is None
    assert missing is None


def test_client_missing_config_reports_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "knowledge_llm_enabled", True)
    monkeypatch.setattr(settings, "knowledge_llm_base_url", "")
    client, missing = build_knowledge_llm_client(system_prompt="p")
    assert client is None
    assert missing is not None and "KNOWLEDGE_LLM_BASE_URL" in missing


def test_client_built_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "knowledge_llm_enabled", True)
    monkeypatch.setattr(settings, "knowledge_llm_base_url", "http://localhost:9000/v1")
    monkeypatch.setattr(settings, "knowledge_llm_model", "test-model")
    monkeypatch.setattr(settings, "knowledge_llm_api_key", "sk-test")
    client, missing = build_knowledge_llm_client(system_prompt="抽取提示词")
    assert missing is None
    assert client is not None
    assert client.request_url == "http://localhost:9000/v1/chat/completions"
    assert client.system_prompt == "抽取提示词"


def test_search_request_contract_still_valid() -> None:
    payload = KnowledgeSearchRequest(query="泡沫")
    assert payload.hop_depth == 2 and payload.limit == 10
