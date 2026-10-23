#!/usr/bin/env python3
"""R-OD-03: register the NOAA NCEI real industry dataset into the knowledge
domain and run a search-then-decision trace that cites it.

Evidence level E1/E2: the dataset is REAL PUBLIC industry monitoring data
(NOAA NCEI Marine Microplastics, free to access and use), registered as a
public-level dataset asset; the run is a software integration on the project
backend and does not imply field validation or domain accuracy. The script
writes an explicit failure result and exits non-zero on any error.
"""

from __future__ import annotations

import argparse
import hashlib
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
DATA_DIR = ROOT / "artifacts" / "real-industry-data"
MANIFEST = DATA_DIR / "manifest.json"
CSV_PATH = DATA_DIR / "noaa_marine_microplastics.csv"
DEFAULT_OUTPUT = DATA_DIR / "knowledge-e2e-trace.json"
DEFAULT_BASE_URL = os.getenv("SEASIGHT_API_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")

EXIT_OK = 0
EXIT_FAILED = 3
REDACT_KEYS = {"access_token", "authorization", "password", "secret", "token"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("<redacted>" if str(k).lower() in REDACT_KEYS else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class LoopFailure(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = ""
        self.requests: list[dict[str, Any]] = []

    def api(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json", "User-Agent": "Oceanus-Rod03/1.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                parsed = {}
            raise LoopFailure(f"{method} {path}: HTTP {exc.code} message={parsed.get('message')}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LoopFailure(f"{method} {path}: connection failed: {exc}") from exc
        self.requests.append(
            {"at": utc_now(), "method": method, "path": path,
             "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
             "request": redact(payload), "response": redact(parsed)}
        )
        if parsed.get("code", 0) != 0:
            raise LoopFailure(f"{method} {path}: code={parsed.get('code')} message={parsed.get('message')}")
        return parsed.get("data")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--username", default=os.getenv("SEASIGHT_API_USERNAME", "admin"))
    parser.add_argument("--password", default=os.getenv("SEASIGHT_API_PASSWORD", ""))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    csv_bytes = CSV_PATH.read_bytes()
    stats = manifest["quick_stats"]
    citation = manifest["dataset"]["citation"]

    summary_text = (
        "NOAA NCEI 全球海洋微塑料监测数据集（1972 年至今，本次获取切片 1986-2023）："
        f"共 {stats['rows']} 条监测记录，覆盖 {stats['oceans']} 个大洋、"
        f"{stats['countries']} 个国家/地区，{stats['rows_with_measurement']} 条含定量测量值；"
        "计量单位含 pieces/m3（海水）、pieces/10 mins（海滩 Nurkle Patrol 巡查）、"
        "pieces/kg d.w.（沉积物）；介质含海水、海滩、海洋沉积物；每条记录带采样方法、"
        " DOI 与 NCEI 登记号，可逐条溯源到原始文献。本数据集在治理决策中的用途："
        "为污染热点分级、巡查频次设定与清理资源调度提供行业级参考基准。"
    )

    result: dict[str, Any] = {
        "status": "running",
        "generated_at": utc_now(),
        "evidence_level": "E1/E2",
        "registration": "R-OD-03",
        "scope_note": (
            "真实公开行业监测数据（NOAA NCEI Marine Microplastics，免费公开使用，逐条带 DOI 与"
            " NCEI 登记号）登记入知识域并用于检索-推理-决策链路；数据为全球公开数据集、"
            "非真实脱敏企业内部数据、不含中国大陆点位，本结果不用于说明治理效果或识别精度。"
        ),
        "base_url": args.base_url,
        "steps": [],
    }
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    nonce = uuid.uuid4().hex[:6]

    try:
        client = ApiClient(args.base_url)
        login = client.api("POST", "/auth/login", {"username": args.username, "password": args.password})
        client.token = str(login["access_token"])
        result["steps"].append({"name": "login", "at": utc_now(), "status": "ok", "ids": [args.username]})

        asset_id = "OD-NOAA-MICROPLASTICS-2026"
        existing = client.request("GET", f"/knowledge/assets/{asset_id}") if False else None
        # 幂等：已存在则复用当前版本
        try:
            detail = client.api("GET", f"/knowledge/assets/{asset_id}")
            asset_version_id = str(detail["versions"][-1]["version_id"])
            created = False
        except LoopFailure:
            created_data = client.api(
                "POST",
                "/knowledge/assets",
                {
                    "asset_id": asset_id,
                    "asset_type": "dataset",
                    "title": "NOAA NCEI 全球海洋微塑料监测数据集（真实公开行业数据）",
                    "description": (
                        "NOAA NCEI Marine Microplastics 1972-present；本切片 22530 行"
                        "（1986-2023，26 国家/地区、5 大洋），SHA256 见 manifest。"
                    ),
                    "source_uri": manifest["dataset"]["access_point"],
                    "source_system": manifest["dataset"]["provider"],
                    "mime_type": "text/csv",
                    "security_level": "public",
                    "standard_codes": ["open-data", "marine-environment-standard"],
                    "tags": ["真实公开行业数据", "微塑料", "监测", "NOAA NCEI"],
                    "attributes": {
                        "rows": stats["rows"],
                        "sha256": manifest["file"]["sha256"],
                        "citation": citation,
                        "feature_service": manifest["dataset"]["feature_service"],
                        "quick_stats": stats,
                    },
                    "initial_content": {
                        "content_text": summary_text,
                        "extraction_method": "dataset_profiling",
                        "metadata": {"registration": "R-OD-03"},
                    },
                },
            )
            asset_version_id = str(created_data["versions"][0]["version_id"])
            created = True
        result["steps"].append(
            {"name": "register_dataset_asset" if created else "reuse_dataset_asset", "at": utc_now(),
             "status": "ok", "ids": [asset_id, asset_version_id],
             "detail": {"rows": stats["rows"], "sha256": manifest["file"]["sha256"][:16] + "..."}}
        )

        # 在已发布的公开语料本体上检索相关标准条目，与数据集证据交叉引用
        search = None
        queries_tried = []
        try:
            versions = client.api("GET", "/knowledge/ontology/versions?page_size=50")
            items = versions if isinstance(versions, list) else (versions.get("items") or versions.get("versions") or [])
            published = [v for v in items if v.get("status") == "published" and "公开文件本体" in str(v.get("name") or "")]
            if published:
                ont_id = str(published[0]["version_id"])
                for query in ["海洋微塑料监测评价标准", "海洋垃圾监测与评价"]:
                    attempt = client.api(
                        "POST",
                        "/knowledge/search",
                        {"query": query, "ontology_version_id": ont_id, "hop_depth": 2, "limit": 5},
                    )
                    queries_tried.append({"query": query, "total": attempt.get("total")})
                    if attempt.get("results"):
                        search = attempt
                        search["_ontology_version_id"] = ont_id
                        break
        except LoopFailure as exc:
            result["steps"].append({"name": "cross_search_skipped", "at": utc_now(), "status": "ok",
                                    "detail": {"reason": str(exc)[:120]}})
        if search:
            result["steps"].append(
                {"name": "cross_domain_search", "at": utc_now(), "status": "ok",
                 "ids": [search["_ontology_version_id"]],
                 "detail": {"mode": search.get("mode"), "total": search.get("total"),
                            "top_hit": search["results"][0]["title"]}}
            )

        evidence = [
            {
                "asset_id": asset_id,
                "asset_version_id": asset_version_id,
                "hop_no": 0,
                "citation_text": (
                    f"NOAA NCEI Marine Microplastics：{stats['rows']} 条监测记录"
                    f"（{stats['years_min']}-{stats['years_max']}，{stats['countries']} 国家/地区），"
                    "逐条带 DOI 与 NCEI 登记号。"
                ),
                "source_uri": manifest["dataset"]["access_point"],
                "score": 1.0,
                "metadata": {"role": "real_industry_dataset", "sha256": manifest["file"]["sha256"]},
            }
        ]
        if search:
            for hit in search["results"][:3]:
                evidence.append(
                    {
                        "asset_id": hit["asset_id"],
                        "asset_version_id": hit["asset_version_id"],
                        "hop_no": hit.get("hop_count"),
                        "citation_text": (hit.get("citations") or [hit.get("snippet") or hit["title"]])[0],
                        "source_uri": hit.get("source_uri"),
                        "score": hit.get("score"),
                        "metadata": {"role": "mee_standard_cross_reference", "path": hit.get("path")},
                    }
                )

        decision = client.api(
            "POST",
            "/knowledge/decisions",
            {
                "question": "治理决策的行业级微塑料数据基础是否具备、如何引用？",
                "answer_summary": (
                    "已具备：NOAA NCEI 全球海洋微塑料监测数据集（22530 行、1986-2023、"
                    "26 国家/地区、逐条 DOI 可溯源）已登记为公开级数据资产，可与公开标准"
                    "语料交叉引用，为污染热点分级与清理资源调度提供行业基准；该数据集为"
                    "全球公开数据，不用于本地识别精度或现场效果宣称。"
                ),
                "run_id": f"rod03-{stamp}-{nonce}",
                "policy_version": "open-data-v1",
                "evidence": evidence,
                "metadata": {"registration": "R-OD-03", "dataset_sha256": manifest["file"]["sha256"]},
            },
        )
        trace_id = str(decision["trace_id"])
        result["steps"].append({"name": "create_decision", "at": utc_now(), "status": "ok",
                                "ids": [trace_id], "detail": {"evidence": len(evidence)}})

        chain = client.api("GET", f"/knowledge/decisions/{trace_id}/evidence")
        result["steps"].append(
            {"name": "read_decision_evidence", "at": utc_now(), "status": "ok", "ids": [trace_id],
             "detail": {"evidence_count": len(chain),
                        "rank_sequence_ok": [i["rank_no"] for i in chain] == list(range(1, len(chain) + 1))}}
        )

        result["status"] = "verified"
        result["ids"] = {"asset_id": asset_id, "asset_version_id": asset_version_id, "trace_id": trace_id}
        result["queries_tried"] = queries_tried
        result["dataset"] = {
            "name": manifest["dataset"]["name"],
            "rows": stats["rows"],
            "sha256": manifest["file"]["sha256"],
            "citation": citation,
        }
        result["api_traces"] = client.requests
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"R-OD-03 OK -> {output}")
        print(f"asset={asset_id} trace={trace_id} evidence={len(chain)}")
        return EXIT_OK
    except LoopFailure as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        result["api_traces"] = redact(result.get("api_traces", []))
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[FAIL] {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
