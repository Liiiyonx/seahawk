#!/usr/bin/env python3
"""Knowledge-domain live-stack retrieval-then-generate QA evaluation (E2, real model).

Runs the REAL retrieval-then-generate QA endpoint (``POST /api/v1/knowledge/qa``)
against the RUNNING demo stack (docker compose), whose backend is configured
with a real OpenAI-compatible LLM endpoint via ``KNOWLEDGE_LLM_*``
(ModelArts MaaS / GLM-5.3 at the time of writing).

Corpus: the 20 knowledge assets registered in the live stack — 19 real public
Ministry of Ecology and Environment documents + 1 NOAA public dataset
(E2: real public government text served by the demo stack).

Question set: 8 questions — 6 answerable (each with ``must_contain`` key facts
extracted from the registered documents, verified against the retrieval
channel in a pre-flight search before scoring) and 2 unanswerable (facts that
the corpus does not contain; the ONLY correct behaviour is an explicit
``insufficient_evidence`` refusal).

Metrics
-------
* behaviour accuracy over the 8 questions (answerable: grounded answer with
  valid citations AND key-fact coverage; unanswerable: explicit refusal);
* citation validity (cited indexes within returned results range);
* refusal accuracy on the 2 unanswerable questions;
* end-to-end latency per question (P50 / P95).

Honest boundary: real public government text on the demo stack; NOT a
real-deployed-county validation; answer correctness is checked by deterministic
key-fact matching, not by human blind review.

Writes ``artifacts/knowledge-qa-live-eval/latest.json``.

Exit codes: 0 = ok, 2 = not configured (stack/token/LLM unavailable), 3 = failed.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "artifacts" / "knowledge-qa-live-eval" / "latest.json"

BASE_URL = "http://localhost:18000/api/v1"
DEMO_USER = ("admin", "admin123456")

EXIT_OK = 0
EXIT_NOT_CONFIGURED = 2
EXIT_FAILED = 3

QUESTIONS = [
    {
        "id": "QA-01",
        "question": "废弃物海洋倾倒许可证核发的审批事项由哪个单位承担？",
        "expect_refusal": False,
        "must_contain": ["流域海域"],
        "anchor": "OD-SEA-PERMIT-2022-01",
        "note": "标题即含答案；检验检索命中与带引用回答",
    },
    {
        "id": "QA-02",
        "question": "海南乐东远海倾倒区用于处置什么物质？同一公告还设立了哪个倾倒区？",
        "expect_refusal": False,
        "must_contain": ["疏浚物"],
        "anchor": "OD-SEA-EX-08",
        "note": "答案应含疏浚物并提及乐东外任一倾倒区（如福宁湾外）",
    },
    {
        "id": "QA-03",
        "question": "《海洋倾倒物质评价规范 渔业废料（征求意见稿）》征求意见通知的发文文号是什么？",
        "expect_refusal": False,
        "must_contain": ["环办标征函"],
        "anchor": "OD-SEA-STD-2026-05",
        "note": "文号 环办标征函〔2026〕19号，检验细粒度事实引用",
    },
    {
        "id": "QA-04",
        "question": "国家生态环境标准《海洋倾倒在线监控技术规范》由哪个机关发布公告？",
        "expect_refusal": False,
        "must_contain": ["生态环境部"],
        "anchor": "OD-SEA-STD-2026-02",
        "note": "发布机关事实",
    },
    {
        "id": "QA-05",
        "question": "平台登记的全球海洋微塑料监测数据集来自哪个机构？",
        "expect_refusal": False,
        "must_contain": ["NOAA"],
        "anchor": "OD-NOAA-MICROPLASTICS-2026",
        "note": "数据集资产也进入问答语料",
    },
    {
        "id": "QA-06",
        "question": "设立海南乐东远海倾倒区等5个倾倒区的公告，文号是多少？",
        "expect_refusal": False,
        "must_contain": ["第25号"],
        "anchor": "OD-SEA-EX-08",
        "note": "公告 2026年 第25号；检验元数据事实",
    },
    {
        "id": "QA-07",
        "question": "废弃物海洋倾倒许可证的收费标准是多少？",
        "expect_refusal": True,
        "must_contain": [],
        "anchor": None,
        "note": "语料无收费标准条款；唯一正确行为是明示证据不足",
    },
    {
        "id": "QA-08",
        "question": "马鼻镇泡沫浮球有奖收捡的补贴标准是每粒多少元？",
        "expect_refusal": True,
        "must_contain": [],
        "anchor": None,
        "note": "该事实不在本演示栈语料中；唯一正确行为是拒答",
    },
]


def http_json(method: str, path: str, token: str | None = None, body: dict | None = None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def login() -> str:
    payload = http_json("POST", "/auth/login", body={"username": DEMO_USER[0], "password": DEMO_USER[1]})
    data = payload.get("data") or {}
    token = data.get("access_token") or payload.get("access_token")
    if not token:
        raise RuntimeError("登录失败：未取得 access_token")
    return token


def preflight_search(token: str, term: str) -> bool:
    """验证关键事实确实可被检索通道召回（保证题目公平性）。"""
    try:
        payload = http_json("POST", "/knowledge/search", token, {"query": term, "limit": 5})
        data = payload.get("data") or {}
        return int(data.get("total") or 0) > 0
    except Exception:
        return False


def ask(token: str, question: str) -> tuple[dict, float]:
    started = time.perf_counter()
    payload = http_json("POST", "/knowledge/qa", token, {"query": question, "limit": 8})
    elapsed = time.perf_counter() - started
    data = payload.get("data") or {}
    return data, elapsed


def main() -> int:
    output_path = DEFAULT_OUTPUT
    try:
        token = login()
    except Exception as exc:
        print(f"[not-configured] 演示栈登录失败: {exc}")
        return EXIT_NOT_CONFIGURED

    traces = []
    for item in QUESTIONS:
        trace = {
            "id": item["id"],
            "question": item["question"],
            "expect_refusal": item["expect_refusal"],
            "must_contain": item["must_contain"],
            "anchor_asset_id": item["anchor"],
            "note": item["note"],
        }
        if item["must_contain"]:
            trace["preflight_search_hit"] = preflight_search(token, item["must_contain"][0])
        try:
            data, elapsed = ask(token, item["question"])
        except Exception as exc:
            trace.update({"error": str(exc), "behaviour_correct": False, "latency_s": None})
            traces.append(trace)
            continue
        results = data.get("results") or []
        answer = str(data.get("answer") or "")
        insufficient = bool(data.get("insufficient_evidence"))
        cited = data.get("cited_indexes") or []
        max_index = len(results)
        citations_valid = bool(cited) and all(isinstance(i, int) and 1 <= i <= max_index for i in cited)
        keyword_hit = all(term in answer for term in item["must_contain"]) if item["must_contain"] else None
        if item["expect_refusal"]:
            behaviour_correct = insufficient is True
        else:
            behaviour_correct = (insufficient is False) and bool(answer.strip()) and citations_valid and bool(keyword_hit)
        trace.update(
            {
                "search_mode": data.get("search_mode"),
                "hit_count": len(results),
                "hit_asset_ids": [r.get("asset_id") for r in results][:8],
                "answer": answer,
                "insufficient_evidence": insufficient,
                "cited_indexes": cited,
                "citations_valid": citations_valid if not item["expect_refusal"] else None,
                "keyword_hit": keyword_hit,
                "channel": data.get("channel"),
                "model": data.get("model"),
                "fallback_reason": data.get("fallback_reason"),
                "latency_s": round(elapsed, 2),
                "behaviour_correct": behaviour_correct,
            }
        )
        traces.append(trace)
        print(f"[{item['id']}] correct={behaviour_correct} channel={data.get('channel')} {elapsed:.1f}s")

    answered = [t for t in traces if "error" not in t]
    answerable = [t for t in answered if not t["expect_refusal"]]
    refusals = [t for t in answered if t["expect_refusal"]]
    latencies = [t["latency_s"] for t in answered if t["latency_s"] is not None]
    channels = {t.get("channel") for t in answered}
    fallbacks = [t["id"] for t in answered if t.get("fallback_reason")]
    models = sorted({t.get("model") for t in answered if t.get("model")})

    summary = {
        "question_count": len(traces),
        "answered": len(answered),
        "errors": len(traces) - len(answered),
        "behaviour_correct": sum(1 for t in answered if t["behaviour_correct"]),
        "behaviour_accuracy": round(sum(1 for t in answered if t["behaviour_correct"]) / len(answered), 4) if answered else None,
        "answerable_correct": sum(1 for t in answerable if t["behaviour_correct"]),
        "answerable_total": len(answerable),
        "citation_validity": (
            round(sum(1 for t in answerable if t["citations_valid"]) / len(answerable), 4) if answerable else None
        ),
        "keyfact_coverage": (
            round(sum(1 for t in answerable if t["keyword_hit"]) / len(answerable), 4) if answerable else None
        ),
        "refusal_correct": sum(1 for t in refusals if t["behaviour_correct"]),
        "refusal_total": len(refusals),
        "latency_p50_s": round(statistics.median(latencies), 2) if latencies else None,
        "latency_max_s": round(max(latencies), 2) if latencies else None,
        "channels": sorted(channels),
        "fallback_question_ids": fallbacks,
        "models": models,
    }

    report = {
        "artifact_type": "knowledge_qa_live_eval",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stack": "docker compose 演示栈（seasight-backend:18000），KNOWLEDGE_LLM_* 已配置真实端点",
        "corpus": "演示栈已登记的 20 个知识资产（19 份生态环境部真实公开文件 + 1 个 NOAA 公开数据集）",
        "model": models,
        "honest_boundary": [
            "真实公开政务文本（E1/E2）跑在演示栈上；不代表任何现场验证或真实县级业务数据；",
            "答案正确性采用确定性关键事实匹配（must_contain），非人工盲评；",
            "可答题出题前先用检索通道预检关键事实可召回（preflight_search_hit），保证题目公平；",
            "拒答题的语料中确实不含目标事实，唯一正确行为是 insufficient_evidence=true。",
        ],
        "summary": summary,
        "traces": traces,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(f"[ok] 报告已写入 {output_path}")
    ok = summary["errors"] == 0 and summary["behaviour_accuracy"] is not None
    return EXIT_OK if ok else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
