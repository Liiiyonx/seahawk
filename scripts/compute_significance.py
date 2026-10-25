#!/usr/bin/env python3
"""Pairwise Wilcoxon signed-rank tests across retrieval configurations.

Inputs (read-only):
  artifacts/knowledge-retrieval-eval/latest.json        (backend/bge/rrf/v3/routed, per_item)
  artifacts/knowledge-retrieval-eval/bm25_ablation.json (pure BM25 no-graph, per_item)

For every category (single / single2 / multihop) and every config pair, the
paired sample is the per-question reciprocal rank (1/rank of the first gold
asset, 0 if absent). Wilcoxon signed-rank, two-sided, zero differences dropped
(scipy zero_method='wilcox'); if no non-zero difference exists, p is reported
as None. Also writes a frozen snapshot copy of latest.json so paper numbers
reference an immutable file, plus a paper-ready markdown main table.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "artifacts" / "knowledge-retrieval-eval"
LATEST = EVAL_DIR / "latest.json"
FROZEN = EVAL_DIR / "eval_306_snapshot.json"
BM25 = EVAL_DIR / "bm25_ablation.json"
OUT = EVAL_DIR / "significance.json"
TABLE = EVAL_DIR / "main_table.md"

CATS = ("single", "single2", "multihop")
HIT_KS = (1, 3, 5)


def load_config_results() -> dict[str, dict[str, dict]]:
    """config name -> item id -> {ranked_assets, ...}"""
    latest = json.loads(LATEST.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for name, results in latest["per_item"].items():
        out[name] = results
    bm25 = json.loads(BM25.read_text(encoding="utf-8"))
    out["bm25"] = bm25["per_item"]
    return out, latest


def recip_rank(ranked: list[str], gold: set[str]) -> float:
    rank = next((i + 1 for i, a in enumerate(ranked) if a in gold), None)
    return 1.0 / rank if rank else 0.0


def config_metrics(items: list[dict], results: dict[str, dict]) -> dict:
    per_k = {f"hit@{k}": 0 for k in HIT_KS}
    mrr = 0.0
    n = 0
    for it in items:
        gold = set(it["gold_asset_ids"])
        rr = recip_rank(results[it["id"]]["ranked_assets"], gold)
        mrr += rr
        n += 1
        rank = round(1 / rr) if rr else None
        for k in HIT_KS:
            if rank and rank <= k:
                per_k[f"hit@{k}"] += 1
    return {"n": n, **{k: round(v / n, 4) for k, v in per_k.items()}, "mrr": round(mrr / n, 4)}


def main() -> int:
    configs, latest = load_config_results()
    bench = json.loads((EVAL_DIR / "benchmark.json").read_text(encoding="utf-8"))
    items = bench["items"]

    # freeze the 306 snapshot so paper numbers reference an immutable file
    if not FROZEN.exists():
        shutil.copyfile(LATEST, FROZEN)
        print(f"frozen snapshot -> {FROZEN.name}")

    per_cat_items = {c: [i for i in items if i["category"] == c] for c in CATS}

    metrics: dict[str, dict] = {}
    rr_samples: dict[str, dict[str, list[float]]] = {}
    for name, results in configs.items():
        metrics[name] = {}
        rr_samples[name] = {}
        for c in CATS:
            metrics[name][c] = config_metrics(per_cat_items[c], results)
            rr_samples[name][c] = [
                recip_rank(results[it["id"]]["ranked_assets"], set(it["gold_asset_ids"]))
                for it in per_cat_items[c]
            ]

    sig: dict[str, dict] = {}
    for c in CATS:
        sig[c] = {}
        for a, b in combinations(configs.keys(), 2):
            x, y = rr_samples[a][c], rr_samples[b][c]
            diffs = [xi - yi for xi, yi in zip(x, y) if xi != yi]
            entry: dict = {"n": len(x), "n_nonzero_diff": len(diffs),
                           "mean_rr_diff": round(sum(diffs) / len(x), 4) if x else None}
            if len(diffs) == 0:
                entry.update({"statistic": None, "p_value": None, "note": "no non-zero differences"})
            else:
                stat = wilcoxon(x, y, zero_method="wilcox", alternative="two-sided")
                entry.update({"statistic": float(stat.statistic), "p_value": float(stat.pvalue)})
            sig[c][f"{a} vs {b}"] = entry

    out = {
        "description": "Wilcoxon signed-rank over per-question reciprocal rank; two-sided; zero diffs dropped",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": {"latest_run_at": latest.get("run_at"),
                            "ontology_version_id": latest.get("benchmark", {}).get("ontology_version_id")},
        "configs": sorted(configs.keys()),
        "metrics": metrics,
        "pairwise_wilcoxon": sig,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- paper-ready markdown table ----
    lines = ["# Main results (306-question benchmark, frozen snapshot eval_306_snapshot.json)", ""]
    lines.append("| Config | " + " | ".join(
        f"{c} hit@5 | {c} MRR" for c in CATS) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in CATS) + " |")
    best_h5 = {c: max(metrics[n][c]["hit@5"] for n in configs) for c in CATS}
    for name in sorted(configs):
        row = [name]
        for c in CATS:
            m = metrics[name][c]
            h5 = f"{m['hit@5']:.3f}" + (" **" if m["hit@5"] == best_h5[c] else "")
            row.append(f"{h5} | {m['mrr']:.3f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("Pairwise Wilcoxon p-values (per-question reciprocal rank):")
    lines.append("")
    for c in CATS:
        lines.append(f"**{c}**")
        lines.append("")
        names = sorted(configs)
        lines.append("| | " + " | ".join(names) + " |")
        lines.append("| --- | " + " | ".join("---" for _ in names) + " |")
        for a in names:
            row = [a]
            for b in names:
                if a == b:
                    row.append("—")
                else:
                    key = f"{a} vs {b}" if f"{a} vs {b}" in sig[c] else f"{b} vs {a}"
                    p = sig[c][key]["p_value"]
                    row.append(f"{p:.2e}" if p is not None else "n/a")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    TABLE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwritten -> {OUT}\nwritten -> {TABLE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
