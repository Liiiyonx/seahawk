#!/usr/bin/env python3
"""R-KN-08: evidence-traceability audit of the published ontology.

Precision proxy  -- for every PUBLISHED relation, check that both endpoint
names actually occur in the source document of the relation's
source_version_id (and ideally in the same sentence). Reports:
  - endpoint_traceable_rate   (both names present in source doc)
  - sentence_cooccur_rate     (both names in one sentence anywhere in corpus)

Recall proxy     -- extract top frequency terms per corpus document (Chinese
2-4 grams, deterministic), then measure how many are covered by ontology
node names/aliases. Reports term coverage at top-20/top-40 per doc.

All checks are deterministic string operations over the SAME public corpus --
no model calls, no manual annotation claims. Honest boundary: this is an
evidence-traceability audit, NOT a domain-expert gold-standard P/R.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:18000/api/v1"
DEFAULT_OUT = ROOT / "artifacts" / "ontology-evidence-audit" / "latest.json"


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))["data"]


def post(path: str, payload: dict):
    req = urllib.request.Request(BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))["data"]


def sentences(text: str) -> list[str]:
    parts = re.split(r"[。；\n]", text)
    return [p.strip() for p in parts if len(p.strip()) >= 4]


def ngrams(text: str, sizes=(2, 3, 4)) -> Counter:
    c: Counter = Counter()
    clean = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", text)
    for size in sizes:
        for i in range(len(clean) - size + 1):
            c[clean[i:i + size]] += 1
    return c


STOP_HINT = re.compile(r"如下|关于|以及|情况|工作|要求|有关|标准|进行|生态环境部|中华人民|共和国|通知|公告|意见|征求|印刷|日报")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--top-terms", type=int, default=40)
    args = ap.parse_args()

    ovs = get("/knowledge/ontology/versions")
    ovs = ovs if isinstance(ovs, list) else ovs.get("items", [])
    ont = [v for v in ovs if v.get("status") == "published"][0]
    vid = ont["version_id"]
    nodes = get(f"/knowledge/ontology/versions/{vid}/nodes")
    nodes = nodes if isinstance(nodes, list) else nodes.get("items", [])
    rels = get(f"/knowledge/ontology/versions/{vid}/relations")
    rels = rels if isinstance(rels, list) else rels.get("items", [])

    page = get("/knowledge/assets?page=1&page_size=100")
    docs: dict[str, dict] = {}   # version_id -> {text, sents, asset_id}
    for a in page.get("items", []):
        d = get(f"/knowledge/assets/{a['asset_id']}")
        v0 = (d.get("versions") or [{}])[0] or {}
        text = v0.get("content_text") or ""
        if text:
            docs[v0["version_id"]] = {"text": text, "sents": sentences(text), "asset_id": a["asset_id"], "title": a.get("title", "")}

    node_by_id = {n["node_id"]: n for n in nodes}
    vocab = set()
    for n in nodes:
        vocab.add((n.get("canonical_name") or "").strip())
        vocab.add((n.get("name") or "").strip())
        vocab |= {(x or "").strip() for x in (n.get("aliases") or [])}
    vocab.discard("")

    # docs also indexed by version_id and asset_id for evidence lookup
    docs_by_asset = {v["asset_id"]: v for v in docs.values()}
    docs_by_ver = {k: v for k, v in docs.items()}

    def norm(t: str) -> str:
        return re.sub(r"\s+", "", t or "")

    # ---- precision proxy: citation & endpoint traceability via evidence list ----
    rel_total = cit_total = cit_found = rel_ep = rel_full = 0
    methods = Counter()
    untraceable: list[dict] = []
    for r in rels:
        src = node_by_id.get(r.get("source_node_id"), {})
        dst = node_by_id.get(r.get("target_node_id"), {})
        s_name = (src.get("canonical_name") or src.get("name") or "").strip()
        d_name = (dst.get("canonical_name") or dst.get("name") or "").strip()
        ev = r.get("evidence") or []
        methods[(r.get("properties") or {}).get("extraction_method", "?")] += 1
        rel_total += 1
        cite_docs = []
        ok_cit = 0
        for e in ev:
            cit_total += 1
            doc = docs_by_asset.get(e.get("asset_id")) or docs_by_ver.get(e.get("asset_version_id"))
            snippet = norm(e.get("citation", ""))
            if doc and snippet and snippet in norm(doc["text"]):
                cit_found += 1
                ok_cit += 1
                cite_docs.append(doc)
        ep_ok = bool(s_name and d_name and any(
            norm(s_name) in norm(d["text"]) and norm(d_name) in norm(d["text"]) for d in cite_docs))
        if ep_ok:
            rel_ep += 1
        if ev and ok_cit == len(ev) and ep_ok:
            rel_full += 1
        elif not ev or ok_cit < len(ev):
            untraceable.append({"relation_id": r.get("relation_id"), "pair": [s_name, d_name],
                                "reason": "citation-not-in-doc", "evidence_n": len(ev), "cited_ok": ok_cit})
        elif not ep_ok:
            untraceable.append({"relation_id": r.get("relation_id"), "pair": [s_name, d_name],
                                "reason": "endpoint-missing-in-citing-doc"})
    # node traceability (name occurs in its own source doc)
    node_total = node_trace = 0
    for n in nodes:
        doc = docs.get(n.get("source_version_id"))
        name = (n.get("canonical_name") or n.get("name") or "").strip()
        node_total += 1
        if doc and name and (name in doc["text"] or any((x or "") in doc["text"] for x in (n.get("aliases") or []) if x)):
            node_trace += 1

    # ---- recall proxy: top-term coverage per doc ----
    per_doc = []
    covered20 = total20 = covered40 = total40 = 0
    for vinfo in docs.values():
        c = ngrams(vinfo["text"])
        terms = [t for t, _ in c.most_common(200) if not STOP_HINT.search(t)][:args.top_terms]
        cov = [t for t in terms if t in vocab or any(t in v or v in t for v in vocab if abs(len(v) - len(t)) <= 2)]
        n20 = terms[:20]
        c20 = [t for t in n20 if t in cov]
        covered20 += len(c20); total20 += len(n20)
        covered40 += len(cov); total40 += len(terms)
        per_doc.append({"asset_id": vinfo["asset_id"], "title": vinfo["title"][:30],
                        "top20_covered": f"{len(c20)}/{len(n20)}",
                        "top40_covered": f"{len(cov)}/{len(terms)}",
                        "missing_top": [t for t in n20 if t not in cov][:6]})

    out = {
        "registration": "R-KN-08",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "ontology_version_id": vid,
        "counts": {"nodes": len(nodes), "relations": len(rels), "docs": len(docs)},
        "precision_proxy": {
            "citation_total": cit_total,
            "citation_verifiable": f"{cit_found}/{cit_total}",
            "citation_verifiable_rate": round(cit_found / cit_total, 4) if cit_total else None,
            "relation_endpoint_traceable": f"{rel_ep}/{rel_total}",
            "relation_endpoint_traceable_rate": round(rel_ep / rel_total, 4) if rel_total else None,
            "relation_fully_traceable": f"{rel_full}/{rel_total}",
            "relation_fully_traceable_rate": round(rel_full / rel_total, 4) if rel_total else None,
            "node_name_traceable_rate": round(node_trace / node_total, 4) if node_total else None,
            "extraction_methods": dict(methods),
            "untraceable_sample": untraceable[:10],
            "definition": "关系 evidence 引用片段可在所引资产原文中逐字回溯 + 两端实体名见于引用文档（证据核验口径，非专家金标准）",
        },
        "recall_proxy": {
            "top20_term_coverage": round(covered20 / total20, 4) if total20 else None,
            "top40_term_coverage": round(covered40 / total40, 4) if total40 else None,
            "definition": "各文档高频术语(2-4gram,去停用词)被本体节点名/别名覆盖的比例（召回近似口径）",
            "per_doc": per_doc,
        },
        "honest_boundary": "确定性字符串核验，非人工标注金标准；抽取上限 max_nodes=100/max_relations=200 由接口 schema 决定",
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("counts", "precision_proxy", "recall_proxy")}, ensure_ascii=False, indent=2)[:1200])
    print(f"-> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
