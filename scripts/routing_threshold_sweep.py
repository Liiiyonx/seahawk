#!/usr/bin/env python3
"""Threshold-sensitivity sweep for the two-system rule router.

Question (anticipated reviewer objection): is the title-coverage cutoff 0.5
tuned on the benchmark? Answer by sweeping it: for each threshold t in
[0.1 .. 0.9], route every question by recomputing the deterministic
title-coverage signal (same bigram function as run_router_eval.py) and
evaluate the routed system from the frozen per-item rankings
(bm25_ablation.json / eval_306_snapshot.json). No model calls, fully
deterministic, no reruns needed.

Writes routing_threshold_sweep.json with per-threshold overall and per-type
metrics, plus the argmax threshold.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "artifacts" / "knowledge-retrieval-eval"
OUT = EVAL / "routing_threshold_sweep.json"
API = "http://127.0.0.1:18000/api/v1"
THRESHOLDS = [round(0.1 * i, 1) for i in range(1, 10)]


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
    per_k = {1: 0, 3: 0, 5: 0}
    mrr = 0.0
    n = 0
    for it in items:
        gold = set(it["gold_asset_ids"])
        rr = recip(results[it["id"]]["ranked_assets"], gold)
        mrr += rr
        n += 1
        rank = round(1 / rr) if rr else None
        for k in (1, 3, 5):
            if rank and rank <= k:
                per_k[k] += 1
    return {"n": n, **{f"hit@{k}": round(per_k[k] / n, 4) for k in (1, 3, 5)},
            "mrr": round(mrr / n, 4)}


def main() -> int:
    bench = json.loads((EVAL / "benchmark.json").read_text(encoding="utf-8"))
    snap = json.loads((EVAL / "eval_306_snapshot.json").read_text(encoding="utf-8"))
    bm25 = json.loads((EVAL / "bm25_ablation.json").read_text(encoding="utf-8"))
    items = [i for i in bench["items"] if i["category"] != "refuse"]

    titles = {}
    for a in get("/knowledge/assets?page=1&page_size=100").get("items", []):
        titles[a["asset_id"]] = a.get("title", "")
    title_bigrams = {aid: bigrams(t) for aid, t in titles.items() if t}

    covers = {}
    for it in items:
        qbi = bigrams(it["question"])
        best = 0.0
        for tb in title_bigrams.values():
            if tb:
                best = max(best, len(qbi & tb) / len(tb))
        covers[it["id"]] = best

    sweep = []
    for t in THRESHOLDS:
        routed = {}
        for it in items:
            src_sys = bm25["per_item"] if covers[it["id"]] >= t else snap["per_item"]["baseline"]
            routed[it["id"]] = src_sys[it["id"]]
        overall = metrics(items, routed)
        per_cat = {c: metrics([i for i in items if i["category"] == c], routed)
                   for c in ("single", "single2", "multihop")}
        n_bm25 = sum(1 for it in items if covers[it["id"]] >= t)
        sweep.append({"threshold": t, "overall": overall, "per_category": per_cat,
                      "routed_to_bm25": n_bm25})
        print(f"t={t:.1f}  overall h@1={overall['hit@1']:.3f} h@5={overall['hit@5']:.3f} "
              f"mrr={overall['mrr']:.3f}  (to bm25: {n_bm25})")

    best = max(sweep, key=lambda s: s["overall"]["mrr"])
    out = {
        "description": ("title-coverage threshold sweep for the two-system router; "
                        "rankings from frozen artifacts, deterministic, no model calls"),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "sweep": sweep,
        "best_threshold_by_mrr": best["threshold"],
        "h5_range_0.3_to_0.7": [min(s["overall"]["hit@5"] for s in sweep
                                    if 0.3 <= s["threshold"] <= 0.7),
                                max(s["overall"]["hit@5"] for s in sweep
                                    if 0.3 <= s["threshold"] <= 0.7)],
        "mrr_range_0.3_to_0.7": [min(s["overall"]["mrr"] for s in sweep
                                     if 0.3 <= s["threshold"] <= 0.7),
                                 max(s["overall"]["mrr"] for s in sweep
                                     if 0.3 <= s["threshold"] <= 0.7)],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"best threshold by MRR: {best['threshold']} | "
          f"h5 range 0.3-0.7: {out['h5_range_0.3_to_0.7']} | "
          f"mrr range 0.3-0.7: {out['mrr_range_0.3_to_0.7']}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
