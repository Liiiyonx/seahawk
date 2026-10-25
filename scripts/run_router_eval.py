#!/usr/bin/env python3
"""R-KN-07 extension: rule-based query-type router over the frozen snapshot.

Closes the gap between the oracle router (which knows query types) and a
deployable system. The router is a deterministic two-signal heuristic, fixed
a priori, no learning, no tuning on the benchmark labels:

  signal 1  title coverage -- character-bigram overlap between the query and
            each registered asset title, normalized by title bigrams
            (how much of the title the query reproduces). >= 0.5 -> title.
  signal 2  ontology entity mentions -- count of published-ontology node
            names/aliases (length >= 2) occurring verbatim in the query.
            >= 2 distinct nodes -> multi-hop.

  routing:  title        -> BM25 (no graph)
            else         -> Lex+Graph (production, graph expansion)

  oracle_v2 (per-type argmax over all stored systems, computed offline):
            title -> BM25, entity -> Lex+Graph, multi-hop -> Lex+Graph

Per-item rankings are taken verbatim from the frozen artifacts
(eval_306_snapshot.json + bm25_ablation.json), so no model calls, fully
deterministic. Outputs router confusion matrix, routed metrics per category,
and Wilcoxon tests (routed vs each system, per-question reciprocal rank).
"""
from __future__ import annotations

import json
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "artifacts" / "knowledge-retrieval-eval"
OUT = EVAL / "routing_eval.json"
API = "http://127.0.0.1:18000/api/v1"
TITLE_COVER = 0.5
MIN_NODE_LEN = 2


def get(path: str):
    with urllib.request.urlopen(API + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))["data"]


def bigrams(s: str) -> set[str]:
    s = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", s or "")
    return {s[i:i + 2] for i in range(len(s) - 1)} | ({s} if len(s) <= 2 else set())


def recip(ranked: list[str], gold: set[str]) -> float:
    rank = next((i + 1 for i, a in enumerate(ranked) if a in gold), None)
    return 1.0 / rank if rank else 0.0


def metrics(items, results):
    per_k = Counter(); mrr = 0.0; n = 0
    for it in items:
        if it["category"] == "refuse":
            continue
        rr = recip(results[it["id"]]["ranked_assets"], set(it["gold_asset_ids"]))
        mrr += rr; n += 1
        rank = round(1 / rr) if rr else None
        for k in (1, 3, 5):
            if rank and rank <= k:
                per_k[f"hit@{k}"] += 1
    return {"n": n, **{f"hit@{k}": round(per_k[f"hit@{k}"] / n, 4) for k in (1, 3, 5)},
            "mrr": round(mrr / n, 4)}


def main() -> int:
    bench = json.loads((EVAL / "benchmark.json").read_text(encoding="utf-8"))
    vid = bench["ontology_version_id"]
    snap = json.loads((EVAL / "eval_306_snapshot.json").read_text(encoding="utf-8"))
    bm25 = json.loads((EVAL / "bm25_ablation.json").read_text(encoding="utf-8"))
    items = bench["items"]

    # ontology vocabulary pinned to the benchmark's version
    nodes = get(f"/knowledge/ontology/versions/{vid}/nodes")
    nodes = nodes if isinstance(nodes, list) else nodes.get("items", [])
    vocab: list[str] = []
    for nd in nodes:
        for cand in ((nd.get("canonical_name") or ""), (nd.get("name") or ""),
                     *(nd.get("aliases") or [])):
            c = (cand or "").strip()
            if len(c) >= MIN_NODE_LEN:
                vocab.append(c)
    vocab = sorted(set(vocab))
    # shortest-first matching; drop names fully contained in a longer matched name
    titles = {}
    page = get("/knowledge/assets?page=1&page_size=100")
    for a in page.get("items", []):
        titles[a["asset_id"]] = a.get("title", "")
    print(f"vocab: {len(vocab)} names | titles: {len(titles)} | threshold cover>={TITLE_COVER}")

    # ---- route each question ----
    routed: dict[str, dict] = {}
    confusion = Counter()
    preds: dict[str, str] = {}
    for it in items:
        q = it["id"] and it["question"]
        qbi = bigrams(q)
        best_cover, best_asset = 0.0, ""
        for aid, t in titles.items():
            tb = bigrams(t)
            if not tb:
                continue
            cov = len(qbi & tb) / len(tb)
            if cov > best_cover:
                best_cover, best_asset = cov, aid
        hits = sorted({v for v in vocab if v in q}, key=len, reverse=True)
        # de-noise: drop names contained in an already-matched longer name
        kept = [h for h in hits if not any(h != k and h in k for k in hits)]
        if best_cover >= TITLE_COVER:
            pred = "single"          # title query
            src = bm25["per_item"][it["id"]]
        else:
            pred = "single2"         # content / multi-hop -> graph route
            src = snap["per_item"]["baseline"][it["id"]]
        preds[it["id"]] = pred
        route_name = "bm25" if pred == "single" else "graph"
        confusion[(it["category"], route_name)] += 1
        routed[it["id"]] = {"ranked_assets": src["ranked_assets"],
                            "top1_score": src.get("top1_score", 0.0),
                            "route": pred, "title_cover": round(best_cover, 3),
                            "nodes_matched": len(kept)}

    # ---- metrics + tests ----
    cats = ("single", "single2", "multihop")
    per_cat = {c: metrics([i for i in items if i["category"] == c], routed) for c in cats}
    overall = metrics([i for i in items if i["category"] != "refuse"], routed)

    systems = {
        "bm25": bm25["per_item"],
        "baseline": snap["per_item"]["baseline"],
        "twostage": snap["per_item"]["twostage"],
        "hybrid_rrf": snap["per_item"]["hybrid_rrf"],
        "hybrid_v3": snap["per_item"]["hybrid_v3_titleboost"],
        "routed_rule": routed,
        "routed_oracle": snap["per_item"]["routed_oracle"],
    }
    # oracle v2: per-type argmax system (title->bm25, entity/multihop->baseline)
    oracle2: dict[str, dict] = {}
    for it in items:
        srcsys = "bm25" if it["category"] == "single" else "baseline"
        src = systems[srcsys][it["id"]]
        oracle2[it["id"]] = {"ranked_assets": src["ranked_assets"],
                             "top1_score": src.get("top1_score", 0.0)}
    systems["oracle_v2"] = oracle2
    metrics_oracle2 = {c: metrics([i for i in items if i["category"] == c], oracle2)
                       for c in cats}
    overall_oracle2 = metrics([i for i in items if i["category"] != "refuse"], oracle2)
    rr = {name: {it["id"]: recip(res[it["id"]]["ranked_assets"], set(it["gold_asset_ids"]))
                 for it in items if it["category"] != "refuse"}
          for name, res in systems.items()}
    wil = {}
    for other in ("baseline", "bm25", "twostage", "hybrid_rrf", "hybrid_v3",
                  "routed_oracle", "oracle_v2"):
        x = [rr["routed_rule"][i] for i in rr["routed_rule"]]
        y = [rr[other][i] for i in rr["routed_rule"]]
        diffs = [a - b for a, b in zip(x, y) if a != b]
        if diffs:
            w = wilcoxon(x, y, zero_method="wilcox")
            wil[f"routed_rule vs {other}"] = {"p": float(w.pvalue),
                                              "mean_rr_gain": round(sum(diffs) / len(x), 4)}
        else:
            wil[f"routed_rule vs {other}"] = {"p": None, "mean_rr_gain": 0.0}

    # routing correctness: title -> bm25, non-title -> graph (refusal has no gold)
    router_acc = sum(n for (g, r), n in confusion.items()
                     if (g == "single") == (r == "bm25") and g != "refuse") / sum(
        n for (g, _), n in confusion.items() if g != "refuse")
    out = {
        "description": "deterministic 2-signal rule router over frozen snapshot; no model calls",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "ontology_version_id": vid,
        "rules": {"title_cover_min": TITLE_COVER, "min_node_len": MIN_NODE_LEN,
                  "route_title": "bm25", "route_else": "baseline(lex+graph)",
                  "oracle_v2": "title->bm25, entity/multihop->baseline"},
        "router_accuracy": round(router_acc, 4),
        "confusion": {f"{g}->{p}": n for (g, p), n in sorted(confusion.items())},
        "routed_rule": {"per_category": per_cat, "overall": overall},
        "oracle_v2": {"per_category": metrics_oracle2, "overall": overall_oracle2},
        "wilcoxon": wil,
        "per_item": routed,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"router_accuracy": out["router_accuracy"], "confusion": out["confusion"],
                      "overall": overall, "per_category": per_cat,
                      "oracle_v2": out["oracle_v2"], "wilcoxon": wil},
                     ensure_ascii=False, indent=1))
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
