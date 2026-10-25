#!/usr/bin/env python3
"""Build the retrieval benchmark for R-KN-07 (public corpus + ontology, gold asset IDs).

Reads the published ontology + ACTIVE assets from the local backend, then emits
three item pools into artifacts/knowledge-retrieval-eval/benchmark.json:

  single  -- one question per asset (title-conditioned template + paraphrase),
             gold = [asset_id]; measures plain retrieval quality.
  multihop-- questions built from 2-hop ontology relation chains (A -rel-> B -rel-> C):
             question names A and C, gold = the asset(s) hosting the chain;
             measures whether the retriever surfaces the bridging document.
  refuse  -- questions with NO supporting asset in the corpus (out-of-domain);
             a retriever "passes" when no hit reaches the score threshold
             (top score below cutoff => answer pipeline should refuse).

Every item is deterministic given the corpus (no model calls here): question
templates are fixed; gold comes from the ontology/asset tables themselves.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:18000/api/v1").rstrip("/")
DEFAULT_OUT = ROOT / "artifacts" / "knowledge-retrieval-eval" / "benchmark.json"

# Score cutoff used by the refusal pool: a run whose top-1 baseline score stays
# below this is considered "no confident hit" (the QA layer should refuse).
REFUSE_SCORE_CUTOFF = 6.0

ENTITY_TEMPLATES = [
    "关于{entity}的管理要求是什么？请检索依据文件。",
    "{entity}工作应遵循哪些规定？",
]

SINGLE_TEMPLATES = [
    "根据{kw}的有关规定，治理要求是什么？",
    "{kw}相关的管理文件主要讲了哪些内容？",
    "请检索与{kw}有关的依据文件。",
]

MULTIHOP_TEMPLATE = "{a}与{c}之间在治理流程上有什么关联？请检索支撑文件。"

REFUSE_POOL = [
    "海岛旅游民宿补贴政策有哪些？",
    "远洋渔船燃油补贴申报流程是什么？",
    "深海采矿勘探许可证如何办理？",
    "港口危险货物集装箱堆场的设计规范是什么？",
    "城市地下综合管廊的运维费用分摊办法？",
]


def api(path: str, payload: dict | None = None) -> dict:
    url = DEFAULT_BASE + path
    if payload is None:
        req = urllib.request.Request(url)
    else:
        req = urllib.request.Request(
            url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if isinstance(body, dict) and body.get("code") not in (0, None) and body.get("data") is None:
        raise SystemExit(f"API error on {path}: {body}")
    return body.get("data", body)


def keyword_of(title: str) -> str:
    """Strip doc-number suffixes and common administrative prefixes."""
    t = re.sub(r"（[^）]{2,30}）", "", title)
    t = re.sub(r"关于", "", t)
    t = re.sub(r"的通知$|的公告$|的通知$", "", t)
    t = t.strip()
    return t if 2 <= len(t) <= 24 else title[:20]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    assets_page = api("/knowledge/assets?page=1&page_size=100")
    assets = assets_page.get("items", [])
    if not assets:
        raise SystemExit("no ACTIVE assets; run scripts/open_data_knowledge_e2e.py first")

    # asset detail carries content text via versions; search hits expose asset_id + version
    versions = api("/knowledge/ontology-versions") if False else None  # placeholder, unused
    ov = api("/knowledge/ontology-versions/latest") if False else None  # unused
    ontology_list = api("/knowledge/ontology/versions")
    items = ontology_list if isinstance(ontology_list, list) else ontology_list.get("items", [])
    published = [v for v in items if v.get("status") == "published"]
    if not published:
        raise SystemExit("no published ontology; rerun the e2e loader")
    version_id = published[0]["version_id"]

    nodes_raw = api(f"/knowledge/ontology/versions/{version_id}/nodes")
    nodes = nodes_raw if isinstance(nodes_raw, list) else nodes_raw.get("items", [])
    rel_raw = api(f"/knowledge/ontology/versions/{version_id}/relations")
    relations = rel_raw if isinstance(rel_raw, list) else rel_raw.get("items", [])
    node_by_id = {n["node_id"]: n for n in nodes}

    single: list[dict] = []
    for a in assets:
        kw = keyword_of(a.get("title", ""))
        gold = [a["asset_id"]]
        for ti, tpl in enumerate(SINGLE_TEMPLATES):
            single.append({
                "id": f"single-{a['asset_id'][:8]}-{ti}",
                "question": tpl.format(kw=kw),
                "gold_asset_ids": gold,
                "category": "single",
                "title_hint": a.get("title", ""),
            })

    single2: list[dict] = []
    for n in nodes:
        if n.get("review_status") != "approved":
            continue
        ent = (n.get("canonical_name") or n.get("name") or "").strip()
        aid = n.get("source_asset_id")
        if not ent or len(ent) > 16 or not aid:
            continue
        for ti, tpl in enumerate(ENTITY_TEMPLATES[:1]):
            single2.append({
                "id": f"entity-{n['node_id'][:8]}-{ti}",
                "question": tpl.format(entity=ent),
                "gold_asset_ids": [aid],
                "category": "single2",
                "title_hint": ent,
            })

    multihop: list[dict] = []
    outgoing: dict[str, list[dict]] = {}
    for r in relations:
        outgoing.setdefault(r["source_node_id"], []).append(r)
    for src, outs in outgoing.items():
        a_name = node_by_id.get(src, {}).get("name")
        if not a_name:
            continue
        for r1 in outs:
            mid = r1["target_node_id"]
            for r2 in outgoing.get(mid, []):
                dst = r2["target_node_id"]
                if dst == src:
                    continue
                c_name = node_by_id.get(dst, {}).get("name")
                if not c_name:
                    continue
                gold_assets = sorted({node_by_id[src].get("source_asset_id"),
                                      node_by_id.get(mid, {}).get("source_asset_id"),
                                      node_by_id.get(dst, {}).get("source_asset_id")} - {None})
                if not gold_assets:
                    continue
                multihop.append({
                    "id": f"hop2-{src[:6]}-{mid[:6]}-{dst[:6]}",
                    "question": MULTIHOP_TEMPLATE.format(a=a_name, c=c_name),
                    "gold_asset_ids": gold_assets,
                    "category": "multihop",
                    "chain": [a_name, node_by_id.get(mid, {}).get("name", "?"), c_name],
                })
    # cap multihop to keep the benchmark balanced (chains are numerous & redundant)
    multihop = multihop[:120]

    refuse = [
        {"id": f"refuse-{i:02d}", "question": q, "gold_asset_ids": [], "category": "refuse",
         "score_cutoff": REFUSE_SCORE_CUTOFF}
        for i, q in enumerate(REFUSE_POOL)
    ]

    bench = {
        "registration": "R-KN-07",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "ontology_version_id": version_id,
        "asset_count": len(assets),
        "node_count": len(nodes),
        "relation_count": len(relations),
        "items": single + single2 + multihop + refuse,
        "counts": {"single": len(single), "single2": len(single2), "multihop": len(multihop), "refuse": len(refuse)},
        "note": "deterministic benchmark: templates fixed, gold from ontology/asset tables; "
                "refuse pool measured against baseline score cutoff only",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bench, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"benchmark -> {out}")
    print(json.dumps(bench["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
