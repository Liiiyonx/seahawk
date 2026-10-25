#!/usr/bin/env python3
"""R-KN-07 ablation: pure lexical BM25 WITHOUT ontology-graph expansion.

The production baseline (System A in run_retrieval_eval.py) scores direct
lexical evidence PLUS one-hop ontology-graph evidence. Reviewers need the
graph-free ablation: BM25 over the SAME chunk corpus (title + content,
800-char chunks), asset ranking = best chunk score.

Tokenization is deterministic: CJK runs are split into character bigrams,
ASCII runs stay whole tokens (lowercased). No segmenter, no randomness --
fully reproducible. BM25 with k1=1.5, b=0.75.

Writes bm25_ablation.json in the same per_item schema as latest.json so
compute_significance.py can merge all four configurations. No model calls.
"""
from __future__ import annotations

import json
import math
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "artifacts" / "knowledge-retrieval-eval" / "benchmark.json"
OUT = ROOT / "artifacts" / "knowledge-retrieval-eval" / "bm25_ablation.json"
API_BASE = "http://127.0.0.1:18000/api/v1"
CHUNK_CHARS = 800
TOP_K = 8
HIT_KS = (1, 3, 5)
K1, B = 1.5, 0.75

TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    toks: list[str] = []
    for run in TOKEN_RE.findall((text or "").lower()):
        if re.match(r"[\u4e00-\u9fff]", run):
            toks.extend(run[i:i + 2] for i in range(len(run) - 1))
        else:
            toks.append(run)
    return toks


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    text = (text or "").strip()
    return [text[i:i + size] for i in range(0, len(text), size)] if text else []


def get(path: str) -> dict:
    with urllib.request.urlopen(API_BASE + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8")).get("data", {})


class BM25Index:
    def __init__(self, docs: list[list[str]]):
        self.docs = docs
        self.N = len(docs)
        self.dlen = [len(d) for d in docs]
        self.avgdl = sum(self.dlen) / self.N if self.N else 1.0
        self.tf: list[Counter] = [Counter(d) for d in docs]
        df: Counter = Counter()
        for c in self.tf:
            df.update(c.keys())
        self.idf = {t: math.log(1.0 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def score(self, query_toks: list[str], i: int) -> float:
        tf = self.tf[i]
        dl = self.dlen[i]
        s = 0.0
        for t in query_toks:
            f = tf.get(t)
            if not f:
                continue
            s += self.idf.get(t, 0.0) * f * (K1 + 1) / (f + K1 * (1 - B + B * dl / self.avgdl))
        return s


def rank_assets_from_scores(pairs: list[tuple[str, float]]) -> list[str]:
    best: dict[str, float] = {}
    for aid, s in pairs:
        if aid not in best or s > best[aid]:
            best[aid] = s
    return [a for a, _ in sorted(best.items(), key=lambda kv: -kv[1])]


def metrics_for(items: list[dict], results: dict[str, dict]) -> dict:
    per_k = {f"hit@{k}": 0 for k in HIT_KS}
    mrr_sum = 0.0
    n = 0
    for it in items:
        if it["category"] == "refuse":
            continue
        ranked = results[it["id"]]["ranked_assets"]
        gold = set(it["gold_asset_ids"])
        n += 1
        rank = next((i + 1 for i, a in enumerate(ranked) if a in gold), None)
        if rank:
            mrr_sum += 1.0 / rank
            for k in HIT_KS:
                if rank <= k:
                    per_k[f"hit@{k}"] += 1
    return {"n": n, **{k: round(v / n, 4) for k, v in per_k.items()}, "mrr": round(mrr_sum / n, 4)}


def main() -> int:
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    items = bench["items"]

    page = get("/knowledge/assets?page=1&page_size=100")
    assets = page.get("items", [])
    chunks: list[dict] = []
    for a in assets:
        detail = get(f"/knowledge/assets/{a['asset_id']}")
        versions = detail.get("versions") or [{}]
        v0 = versions[0] or {}
        content = v0.get("content_text") or json.dumps(v0.get("content_json") or {}, ensure_ascii=False)
        title = a.get("title", "")
        for ci, ck in enumerate(chunk_text(content)):
            chunks.append({"asset_id": a["asset_id"], "text": f"{title}\n{ck}"[:1600]})
    print(f"corpus: {len(assets)} assets -> {len(chunks)} chunks", flush=True)

    print("tokenizing ...", flush=True)
    doc_toks = [tokenize(c["text"]) for c in chunks]
    index = BM25Index(doc_toks)
    print(f"index: {len(index.idf)} terms", flush=True)

    results: dict[str, dict] = {}
    for idx, it in enumerate(items):
        q_toks = tokenize(it["question"])
        scored = [(c["asset_id"], index.score(q_toks, i)) for i, c in enumerate(chunks)]
        ranked = rank_assets_from_scores(scored)[:TOP_K]
        top1 = max((s for _, s in scored), default=0.0)
        results[it["id"]] = {"ranked_assets": ranked, "top1_score": round(top1, 4)}
        if (idx + 1) % 50 == 0:
            print(f"  {idx + 1}/{len(items)}", flush=True)

    cats = ("single", "single2", "multihop")
    single_min = min((results[i["id"]]["top1_score"] for i in items
                      if i["category"] in ("single", "single2")), default=0)
    refuse_max = max((results[i["id"]]["top1_score"] for i in items
                      if i["category"] == "refuse"), default=0)
    out = {
        "registration": "R-KN-07 ablation (bm25-no-graph)",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": {"counts": bench["counts"], "ontology_version_id": bench["ontology_version_id"]},
        "config": {"k1": K1, "b": B, "chunk_chars": CHUNK_CHARS, "top_k": TOP_K,
                   "tokenizer": "cjk char-bigram + ascii token (deterministic, no segmenter)"},
        "bm25": {c: metrics_for([i for i in items if i["category"] == c], results) for c in cats},
        "refuse": {"single_min_top1": single_min, "refuse_max_top1": refuse_max,
                   "separated": refuse_max < single_min},
        "per_item": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n==== BM25 (no graph) SUMMARY ====")
    print(json.dumps({"bm25": out["bm25"], "refuse": out["refuse"]}, ensure_ascii=False, indent=2))
    print(f"\nwritten -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
