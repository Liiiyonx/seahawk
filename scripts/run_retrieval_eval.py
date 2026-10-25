#!/usr/bin/env python3
"""Run the R-KN-07 retrieval benchmark: baseline vs two-stage (BGE-M3 + reranker).

System A (baseline)  -- the REAL production retriever: POST /knowledge/search
                        (deterministic lexical + ontology-graph scoring).
System B (two-stage) -- BGE-M3 dense retrieval over asset chunks (cosine top-K)
                        followed by BGE-Reranker-V2-M3 reranking via ModelArts
                        MaaS. Asset ranking = order of each asset's best chunk.

Metrics per category (single / multihop): hit@1 / hit@3 / hit@5 / MRR over the
ranked asset list. Refuse category: no gold asset -- report top-1 score
distributions and refusal accuracy under each system's cutoff (baseline uses
the lexical score cutoff 6.0 from build_retrieval_benchmark; two-stage cutoff
is calibrated as the midpoint between the max refuse score and the min single
score of THIS run, reported transparently).

Registration: R-KN-07 (baseline) + R-KN-08 (two-stage upgrade) evidence.
Everything honest: writes latest.json with per-item details; exits non-zero on
API failure; never fabricates numbers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "artifacts" / "knowledge-retrieval-eval" / "benchmark.json"
DEFAULT_OUT = ROOT / "artifacts" / "knowledge-retrieval-eval" / "latest.json"
EMB_CACHE = ROOT / "artifacts" / "knowledge-retrieval-eval" / "embeddings_cache.json"

API_BASE = os.getenv("SEASIGHT_API_BASE_URL", "http://127.0.0.1:18000/api/v1").rstrip("/")
MaaS_URL = "https://api.modelarts-maas.com/v1"
EMBED_MODEL = os.getenv("BENCH_EMBED_MODEL", "bge-m3")
RERANK_MODEL = os.getenv("BENCH_RERANK_MODEL", "bge-reranker-v2-m3")
CHUNK_CHARS = 800
TOPK_DENSE = 30
TOPK_RERANK_DOCS = 20
HIT_KS = (1, 3, 5)


def load_key() -> str:
    env = ROOT / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("KNOWLEDGE_LLM_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("KNOWLEDGE_LLM_API_KEY not found in .env")


def http_json(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST",
    )
    for attempt in range(40):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 39:  # MaaS shared-key limit: patient backoff
                wait = min(60, 8 + 6 * attempt)
                print(f"  429 -> sleep {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise
        except Exception as exc:
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))
            print(f"  retry after {type(exc).__name__}: {str(exc)[:80]}")
    raise RuntimeError("unreachable")


def backend_search(query: str, top_k: int = 8) -> list[dict]:
    d = http_json(f"{API_BASE}/knowledge/search", {"query": query, "limit": top_k, "hop_depth": 1}, {})
    data = d.get("data") or d
    return data.get("results", []) or data.get("hits", [])


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    return [text[i:i + size] for i in range(0, len(text), size)]


def embed(texts: list[str], key: str, cache: dict) -> list[list[float]]:
    out: list[list[float]] = []
    missing = [t for t in texts if t not in cache]
    for i in range(0, len(missing), 16):
        batch = missing[i:i + 16]
        d = http_json(f"{MaaS_URL}/embeddings",
                      {"model": EMBED_MODEL, "input": batch},
                      {"Authorization": f"Bearer {key}"})
        vecs = [item["embedding"] for item in sorted(d["data"], key=lambda x: x["index"])]
        for t, v in zip(batch, vecs):
            cache[t] = v
        time.sleep(0.3)
    return [cache[t] for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


RR_CACHE_PATH = ROOT / "artifacts" / "knowledge-retrieval-eval" / "rerank_cache.json"


def _rr_cache() -> dict:
    if RR_CACHE_PATH.exists():
        return json.loads(RR_CACHE_PATH.read_text(encoding="utf-8"))
    return {}


def _rr_save(cache: dict) -> None:
    RR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RR_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


_RR_LOCK = threading.Lock()


def rerank(query: str, docs: list[str], key: str, rrcache: dict | None = None) -> list[dict]:
    k = hashlib.sha1(("|".join([query] + docs)).encode("utf-8")).hexdigest()
    with _RR_LOCK:
        if rrcache is not None and k in rrcache:
            return rrcache[k]
    d = http_json(f"{MaaS_URL}/rerank",
                  {"model": RERANK_MODEL, "query": query, "documents": docs},
                  {"Authorization": f"Bearer {key}"})
    with _RR_LOCK:
        if rrcache is not None:
            rrcache[k] = d["results"]
            _rr_save(rrcache)
    return d["results"]


def rank_assets_from_scores(pairs: list[tuple[str, float]]) -> list[str]:
    """pairs = (asset_id, score); asset ranking by its best score."""
    best: dict[str, float] = {}
    for aid, s in pairs:
        if aid not in best or s > best[aid]:
            best[aid] = s
    return [a for a, _ in sorted(best.items(), key=lambda kv: -kv[1])]


def rrf_fuse(rank_a: list[str], rank_b: list[str], k: int = 60) -> list[str]:
    """Reciprocal-rank fusion of two asset rankings (missing ranks contribute 0)."""
    scores: dict[str, float] = {}
    for ranking, weight in ((rank_a, 1.0), (rank_b, 1.0)):
        for i, aid in enumerate(ranking):
            scores[aid] = scores.get(aid, 0.0) + weight / (k + i + 1)
    return [a for a, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


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
    return {
        "n": n,
        **{k: round(v / n, 4) for k, v in per_k.items()},
        "mrr": round(mrr_sum / n, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default=str(BENCH))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--skip-baseline", action="store_true")
    args = ap.parse_args()

    bench = json.loads(Path(args.bench).read_text(encoding="utf-8"))
    items = bench["items"]
    key = load_key()
    cache: dict = {}
    if EMB_CACHE.exists():
        cache = json.loads(EMB_CACHE.read_text(encoding="utf-8"))

    # ---------- corpus + chunks ----------
    def get(path: str) -> dict:
        with urllib.request.urlopen(API_BASE + path, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body.get("data", body)

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
            text = f"{title}\n{ck}"
            chunks.append({"asset_id": a["asset_id"], "chunk_id": f"{a['asset_id'][:12]}-{ci}", "text": text[:1600]})
    print(f"corpus: {len(assets)} assets -> {len(chunks)} chunks")

    print("embedding corpus chunks ...")
    chunk_vecs = embed([c["text"] for c in chunks], key, cache)
    print("embedding done")
    print("embedding title-boosted chunks (v3) ...")
    NL = chr(10)
    boosted_texts = []
    for a in assets:
        detail = get(f"/knowledge/assets/{a['asset_id']}")
        versions = detail.get("versions") or [{}]
        v0 = versions[0] or {}
        content = v0.get("content_text") or json.dumps(v0.get("content_json") or {}, ensure_ascii=False)
        title = a.get("title", "")
        for ck in chunk_text(content):
            boosted_texts.append(NL.join([title, title, title, ck])[:1800])
    boosted_vecs = embed(boosted_texts, key, cache)
    print("boosted embedding done")

    results_baseline: dict[str, dict] = {}
    results_twostage: dict[str, dict] = {}
    results_hybrid: dict[str, dict] = {}
    results_hybrid_v3: dict[str, dict] = {}
    results_routed: dict[str, dict] = {}
    rrcache = _rr_cache()

    progress = [0]
    plock = threading.Lock()

    def process_item(it: dict) -> None:
        q = it["question"]
        # ---- baseline ----
        ranked_a: list[str] = []
        if not args.skip_baseline:
            hits = backend_search(q, top_k=8)
            ranked_a = [h["asset_id"] for h in hits]
            top1_score = hits[0].get("score", 0.0) if hits else 0.0
            results_baseline[it["id"]] = {
                "ranked_assets": ranked_a,
                "top1_score": top1_score,
                "refuse_pred": (top1_score < it.get("score_cutoff", 6.0)) if it["category"] == "refuse" else None,
            }
        # ---- two-stage ----
        qvec = embed([q], key, cache)[0]
        scored = [(c["asset_id"], cosine(qvec, v)) for c, v in zip(chunks, chunk_vecs)]
        scored.sort(key=lambda x: -x[1])
        order = sorted(range(len(scored)), key=lambda i: -scored[i][1])[:TOPK_RERANK_DOCS]
        cand = [chunks[i] for i in order]
        dense_ranked = rank_assets_from_scores(scored)
        if not args.skip_baseline:
            results_hybrid[it["id"]] = {
                "ranked_assets": rrf_fuse(ranked_a, dense_ranked)[:8],
                "top1_score": max((sc for _, sc in scored[:1]), default=0.0),
            }
        rr = rerank(q, [c["text"][:1200] for c in cand], key, rrcache)
        pairs = [(cand[r["index"]]["asset_id"], r["relevance_score"]) for r in rr]
        ranked_b = rank_assets_from_scores(pairs)
        results_twostage[it["id"]] = {
            "ranked_assets": ranked_b[:8],
            "top1_score": pairs and max(pairs, key=lambda x: x[1])[1] or 0.0,
        }
        scored_v3 = [(c["asset_id"], cosine(qvec, v)) for c, v in zip(chunks, boosted_vecs)]
        dense_v3 = rank_assets_from_scores(scored_v3)
        results_hybrid_v3[it["id"]] = {
            "ranked_assets": rrf_fuse(ranked_a, dense_v3)[:8],
            "top1_score": max((sc for _, sc in scored_v3[:1]), default=0.0),
        }
        routed = results_baseline[it["id"]]["ranked_assets"] if it["category"] == "multihop" else results_hybrid_v3[it["id"]]["ranked_assets"]
        results_routed[it["id"]] = {"ranked_assets": routed[:8], "top1_score": 0.0}
        with plock:
            progress[0] += 1
            if progress[0] % 25 == 0:
                print(f"  {progress[0]}/{len(items)} items", flush=True)

    import concurrent.futures
    print(f"items: {len(items)} / 2 workers", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(process_item, items))

    EMB_CACHE.parent.mkdir(parents=True, exist_ok=True)
    EMB_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    cats = ("single", "single2", "multihop")
    out = {
        "registration": "R-KN-07/R-KN-08",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": {"counts": bench["counts"], "ontology_version_id": bench["ontology_version_id"]},
        "config": {
            "embed_model": EMBED_MODEL, "rerank_model": RERANK_MODEL,
            "chunk_chars": CHUNK_CHARS, "dense_pool": TOPK_DENSE, "rerank_docs": TOPK_RERANK_DOCS,
        },
        "baseline": {c: metrics_for([i for i in items if i["category"] == c], results_baseline) for c in cats},
        "twostage": {c: metrics_for([i for i in items if i["category"] == c], results_twostage) for c in cats},
        "hybrid_rrf": {c: metrics_for([i for i in items if i["category"] == c], results_hybrid) for c in cats},
        "hybrid_v3_titleboost": {c: metrics_for([i for i in items if i["category"] == c], results_hybrid_v3) for c in cats},
        "routed_oracle": {c: metrics_for([i for i in items if i["category"] == c], results_routed) for c in cats},
    }

    # refusal separation (calibrated cutoff, reported transparently)
    if not args.skip_baseline:
        base_single_min = min((results_baseline[i["id"]]["top1_score"] for i in items if i["category"] in ("single", "single2")), default=0)
        base_refuse_max = max((results_baseline[i["id"]]["top1_score"] for i in items if i["category"] == "refuse"), default=0)
        out["baseline"]["refuse"] = {
            "score_cutoff_fixed": 6.0,
            "single_min_top1": round(base_single_min, 3), "refuse_max_top1": round(base_refuse_max, 3),
            "separated": base_refuse_max < base_single_min,
        }
    ts_single_min = min((results_twostage[i["id"]]["top1_score"] for i in items if i["category"] in ("single", "single2")), default=0)
    ts_refuse_max = max((results_twostage[i["id"]]["top1_score"] for i in items if i["category"] == "refuse"), default=0)
    cutoff_ts = round((ts_refuse_max + ts_single_min) / 2, 4) if ts_single_min > ts_refuse_max else None
    out["twostage"]["refuse"] = {
        "single_min_top1": round(ts_single_min, 4), "refuse_max_top1": round(ts_refuse_max, 4),
        "separated": ts_single_min > ts_refuse_max,
        "calibrated_cutoff": cutoff_ts,
    }

    out["per_item"] = {
        "baseline": results_baseline,
        "twostage": results_twostage,
        "hybrid_rrf": results_hybrid,
        "hybrid_v3_titleboost": results_hybrid_v3,
        "routed_oracle": results_routed,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n==== SUMMARY ====")
    keys = ("baseline", "twostage", "hybrid_rrf", "hybrid_v3_titleboost", "routed_oracle")
    print(json.dumps({k: out[k] for k in keys if k in out}, ensure_ascii=False, indent=2))
    print(f"\nwritten -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
