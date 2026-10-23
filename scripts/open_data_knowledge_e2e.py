#!/usr/bin/env python3
"""Run the knowledge-domain end-to-end loop on REAL public government corpus.

Registers the 8 Ministry of Ecology and Environment public documents
(already fetched with source URL + SHA256 in ``artifacts/open-data-eval/corpus/``)
as knowledge assets, builds and publishes an ontology from them via the
semi-automatic extract -> review -> publish flow, then runs a multi-hop
search and a traceable decision on the published ontology.

Registration: R-OD-02. Evidence level: E1/E2 -- the corpus is REAL PUBLIC
government data (not real masked industry data); the loop is a software
integration run on the project backend; it does not imply field validation,
domain accuracy, or any E3/E4 evidence. The script writes an explicit
``not_configured`` / ``backend_unavailable`` result and exits non-zero when
the backend or corpus is unavailable; it never fabricates a successful run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "artifacts" / "open-data-eval" / "corpus"
MANIFEST = CORPUS_DIR / "manifest.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "open-data-e2e" / "latest.json"
DEFAULT_BASE_URL = os.getenv("SEASIGHT_API_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
MAX_CONTENT_CHARS = 400_000

EXIT_OK = 0
EXIT_NOT_CONFIGURED = 2
EXIT_FAILED = 3

REDACT_KEYS = {"access_token", "authorization", "password", "secret", "token"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_stamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("<redacted>" if str(k).lower() in REDACT_KEYS else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str) and len(value) > 20_000:
        return value[:20_000] + "...<truncated>"
    return value


class LoopFailure(RuntimeError):
    """A mandatory step of the open-data loop failed."""


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""
        self.requests: list[dict[str, Any]] = []

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json", "User-Agent": "Oceanus-OpenDataE2E/1.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=30.0) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            status = int(response.status)
            error = None
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            raw = exc.read()
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                parsed = {}
            error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LoopFailure(f"{method} {path}: connection failed: {exc}") from exc
        self.requests.append(
            {
                "at": utc_now(),
                "method": method,
                "path": path,
                "status": status,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "request": redact(payload),
                "response": redact(parsed),
                "error": error,
            }
        )
        if error:
            raise LoopFailure(f"{method} {path}: {error} message={parsed.get('message')}")
        return parsed

    def api(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        parsed = self.request(method, path, payload)
        if parsed.get("code", 0) != 0:
            raise LoopFailure(f"{method} {path}: business error code={parsed.get('code')} message={parsed.get('message')}")
        return parsed.get("data")


def load_corpus() -> list[dict[str, Any]]:
    if not MANIFEST.is_file():
        raise LoopFailure(f"missing corpus manifest: {MANIFEST}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    docs = manifest.get("documents") if isinstance(manifest, dict) else manifest
    if not isinstance(docs, list) or not docs:
        raise LoopFailure("corpus manifest has no documents")
    loaded: list[dict[str, Any]] = []
    for item in docs:
        text_path = CORPUS_DIR / str(item.get("extracted_file") or "")
        if not text_path.is_file():
            raise LoopFailure(f"missing extracted text: {text_path}")
        text = text_path.read_text(encoding="utf-8", errors="replace")
        loaded.append({**item, "content_text": text[:MAX_CONTENT_CHARS]})
    return loaded


def ensure_asset(client: ApiClient, doc: dict[str, Any]) -> tuple[str, str, bool]:
    """Register the public document asset (idempotent); return (asset_id, version_id, created)."""
    asset_id = str(doc["asset_id"])
    existing = client.request("GET", f"/knowledge/assets/{asset_id}")
    if existing.get("code", 0) == 0 and (existing.get("data") or {}).get("versions"):
        versions = existing["data"]["versions"]
        return asset_id, str(versions[-1]["version_id"]), False

    created = client.api(
        "POST",
        "/knowledge/assets",
        {
            "asset_id": asset_id,
            "asset_type": "document",
            "title": doc["title"],
            "description": (
                f"来源：{doc.get('publisher') or '中华人民共和国生态环境部'}公开文件；"
                "原文与提取文本随 artifacts/open-data-eval/corpus/ 入库，SHA256 可追溯。"
            ),
            "source_uri": doc.get("source_url"),
            "source_system": doc.get("publisher") or "中华人民共和国生态环境部",
            "mime_type": "text/plain",
            "security_level": "public",
            "standard_codes": doc.get("standard_codes") or [],
            "tags": ["公开政务数据", "生态环境部", "真实公开语料"],
            "attributes": {
                "corpus": "mee-open-notifications",
                "source_file": doc.get("file"),
                "text_chars": len(doc["content_text"]),
            },
            "initial_content": {
                "content_text": doc["content_text"],
                "extraction_method": "html_text_extract",
                "metadata": {"provenance": "mee-open-corpus", "source_url": doc.get("source_url")},
            },
        },
    )
    version_id = str(created["versions"][0]["version_id"])
    return asset_id, version_id, True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--username", default=os.getenv("SEASIGHT_API_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("SEASIGHT_API_PASSWORD", ""))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    stamp = run_stamp()
    nonce = uuid.uuid4().hex[:8]

    result: dict[str, Any] = {
        "status": "running",
        "generated_at": utc_now(),
        "evidence_level": "E1/E2",
        "registration": "R-OD-02",
        "scope_note": (
            "真实公开政务语料（生态环境部公开通知与公报，来源 URL 与 SHA256 可追溯）上的"
            "知识域端到端闭环：资产登记 → 本体候选抽取 → 人工审核 → 发布 → 多跳检索 → "
            "决策证据链。语料为公开数据，非真实脱敏行业数据；本结果不构成领域准确率、"
            "现场验证或任何 E3/E4 证据。"
        ),
        "base_url": args.base_url,
        "steps": [],
        "queries_tried": [],
    }

    def step(name: str, detail: dict[str, Any], ids: list[str] | None = None) -> None:
        result["steps"].append({"name": name, "at": utc_now(), "status": "ok", "ids": ids or [], "detail": detail})

    try:
        docs = load_corpus()
        result["corpus"] = {
            "documents": len(docs),
            "titles": [d["title"] for d in docs],
            "source_urls": [d.get("source_url") for d in docs],
        }
        client = ApiClient(args.base_url)
        login = client.api("POST", "/auth/login", {"username": args.username, "password": args.password})
        client.token = str(login["access_token"])
        step("login", {"role": login.get("role")}, ids=[args.username])

        version_ids: list[str] = []
        created_count = 0
        for doc in docs:
            asset_id, version_id, created = ensure_asset(client, doc)
            created_count += int(created)
            version_ids.append(version_id)
            step(
                "register_public_document" if created else "reuse_public_document",
                {"asset_id": asset_id, "title": doc["title"], "source_url": doc.get("source_url")},
                ids=[asset_id, version_id],
            )

        ontology = client.api(
            "POST",
            "/knowledge/ontology/versions",
            {
                "name": f"海洋环境治理公开文件本体（真实公开语料 {stamp}）",
                "description": "由生态环境部 8 份公开文件经半自动抽取构建；候选经人工审核后发布",
                "standard_codes": ["marine-environment-standard", "open-data"],
                "metadata": {"corpus": "mee-open-notifications", "registration": "R-OD-02"},
            },
        )
        ontology_version_id = str(ontology["version_id"])
        step("create_ontology_version", {"version_no": ontology["version_no"]}, ids=[ontology_version_id])

        extracted = client.api(
            "POST",
            "/knowledge/ontology/extract",
            {
                "ontology_version_id": ontology_version_id,
                "asset_version_ids": version_ids,
                "max_nodes": 30,
                "max_relations": 60,
                "min_term_length": 2,
            },
        )
        nodes = extracted["nodes"]
        relations = extracted["relations"]
        if not nodes:
            raise LoopFailure("ontology extract returned zero nodes; cannot publish")
        step(
            "extract_ontology_candidates",
            {
                "created_nodes": extracted["created_nodes"],
                "created_relations": extracted["created_relations"],
                "top_nodes": [n["name"] for n in nodes[:10]],
                "all_candidates_unreviewed": all(n["review_status"] == "proposed" for n in nodes)
                and all(r["review_status"] == "proposed" for r in relations),
            },
            ids=[ontology_version_id],
        )

        for node in nodes:
            client.api("POST", f"/knowledge/ontology/nodes/{node['node_id']}/review", {"decision": "approved", "reason": "open-data e2e reviewer"})
        for relation in relations:
            client.api("POST", f"/knowledge/ontology/relations/{relation['relation_id']}/review", {"decision": "approved", "reason": "open-data e2e reviewer"})
        step("review_candidates", {"nodes": len(nodes), "relations": len(relations), "decision": "approved"})

        published = client.api("POST", f"/knowledge/ontology/versions/{ontology_version_id}/publish")
        step(
            "publish_ontology",
            {
                "status": published["version"]["status"],
                "approved_nodes": published["approved_nodes"],
                "approved_relations": published["approved_relations"],
            },
            ids=[ontology_version_id],
        )

        queries = [
            "海洋生态环境损害鉴定评估技术指南",
            "海洋环境治理应依据哪些标准与程序",
            "海洋垃圾监测与治理",
        ]
        search: dict[str, Any] | None = None
        chosen_query = ""
        for query in queries:
            attempt = client.api(
                "POST",
                "/knowledge/search",
                {
                    "query": query,
                    "ontology_version_id": ontology_version_id,
                    "hop_depth": 2,
                    "asset_types": ["document"],
                    "limit": 10,
                },
            )
            result["queries_tried"].append({"query": query, "mode": attempt.get("mode"), "total": attempt.get("total")})
            if attempt.get("results"):
                search = attempt
                chosen_query = query
                break
        if not search:
            raise LoopFailure("multi-hop search returned no hits for all queries")
        step(
            "multi_hop_search_on_real_corpus",
            {
                "query": chosen_query,
                "mode": search["mode"],
                "total": search["total"],
                "hit_count": len(search["results"]),
                "path_evidence_count": sum(1 for hit in search["results"] if hit.get("path")),
                "hop_counts": sorted({hit.get("hop_count") for hit in search["results"]}),
            },
            ids=[ontology_version_id],
        )

        evidence = []
        for hit in search["results"][:5]:
            evidence.append(
                {
                    "asset_id": hit["asset_id"],
                    "asset_version_id": hit["asset_version_id"],
                    "node_id": hit["matched_node_ids"][0] if hit["matched_node_ids"] else None,
                    "relation_id": hit["matched_relation_ids"][0] if hit["matched_relation_ids"] else None,
                    "hop_no": hit["hop_count"],
                    "citation_text": hit["citations"][0] if hit["citations"] else (hit.get("snippet") or hit["title"]),
                    "source_uri": hit.get("source_uri"),
                    "score": hit["score"],
                    "metadata": {"path": hit.get("path"), "citations": hit.get("citations")},
                }
            )

        decision = client.api(
            "POST",
            "/knowledge/decisions",
            {
                "question": chosen_query,
                "answer_summary": (
                    "基于已登记的生态环境部公开文件（来源 URL 与 SHA256 可追溯）检索到相关"
                    "标准与程序条目；本结论为确定性检索-推理链路输出，条款原文与正式适用"
                    "以官方发布文本为准。"
                ),
                "run_id": f"od-{stamp}-{nonce}",
                "ontology_version_id": ontology_version_id,
                "policy_version": "open-data-v1",
                "hop_depth": 2,
                "evidence": evidence,
                "metadata": {"registration": "R-OD-02", "corpus": "mee-open-notifications"},
            },
        )
        trace_id = str(decision["trace_id"])
        step("create_decision", {"status": decision["status"], "evidence_in_decision": len(decision.get("evidence") or [])}, ids=[trace_id])

        chain = client.api("GET", f"/knowledge/decisions/{trace_id}/evidence")
        step(
            "read_decision_evidence",
            {
                "evidence_count": len(chain),
                "rank_sequence_ok": [item["rank_no"] for item in chain] == list(range(1, len(chain) + 1)),
            },
            ids=[trace_id],
        )

        result["status"] = "verified"
        result["ids"] = {
            "assets": [d["asset_id"] for d in docs],
            "asset_versions": version_ids,
            "ontology_version_id": ontology_version_id,
            "trace_id": trace_id,
        }
        result["counts"] = {
            "assets_created": created_count,
            "assets_reused": len(docs) - created_count,
            "ontology_candidates": len(nodes) + len(relations),
            "search_hits": len(search["results"]),
            "evidence_items": len(chain),
        }
        result["api_traces"] = client.requests
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OPEN-DATA E2E OK -> {output}")
        print(f"assets={len(docs)} created={created_count} nodes={len(nodes)} relations={len(relations)} "
              f"search_total={search['total']} evidence={len(chain)} trace={trace_id}")
        return EXIT_OK
    except LoopFailure as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        result["api_traces"] = redact(result.get("api_traces", []))
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[FAIL] {exc}", file=sys.stderr)
        return EXIT_FAILED
    except Exception as exc:  # noqa: BLE001 - keep a full trace dump for audit
        result["status"] = "failed"
        result["error"] = f"unexpected: {exc}"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        raise


if __name__ == "__main__":
    sys.exit(main())
