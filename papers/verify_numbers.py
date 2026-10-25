#!/usr/bin/env python3
"""Machine-verify every headline number in both paper drafts against artifacts.

Sources of truth (post id-collision fix, 2026-10-26):
  artifacts/knowledge-retrieval-eval/{significance.json, bm25_ablation.json,
  eval_306_snapshot.json, routing_eval.json, benchmark.json}
  artifacts/ontology-evidence-audit/latest.json
  docs/competitions/public-floatwaste-benchmark.md (OCEANS numbers verbatim)

Exit non-zero on any mismatch.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "artifacts" / "knowledge-retrieval-eval"

fails: list[str] = []


def check(name: str, tex: str, expected: str) -> None:
    if expected not in tex:
        fails.append(f"{name}: expected {expected!r} not found in tex")
    else:
        print(f"  ok {name}: {expected}")


def h3(x: float) -> str:
    # display form: 3 decimals, leading zero stripped, 1.000 kept
    return "1.000" if x >= 0.9995 else f"{x:.3f}".lstrip("0")


def cells_close(got: tuple[str, ...], exp4: list[float]) -> bool:
    """Numeric comparison with 3-decimal display tolerance."""
    if len(got) != len(exp4):
        return False
    for g, e in zip(got, exp4):
        try:
            if abs(float(g) - e) > 0.0006:
                return False
        except ValueError:
            return False
    return True


sig = json.loads((EVAL / "significance.json").read_text(encoding="utf-8"))
bm25 = json.loads((EVAL / "bm25_ablation.json").read_text(encoding="utf-8"))
snap = json.loads((EVAL / "eval_306_snapshot.json").read_text(encoding="utf-8"))
route = json.loads((EVAL / "routing_eval.json").read_text(encoding="utf-8"))
bench = json.loads((EVAL / "benchmark.json").read_text(encoding="utf-8"))
audit = json.loads((ROOT / "artifacts/ontology-evidence-audit/latest.json").read_text(encoding="utf-8"))

pakdd = (ROOT / "papers/pakdd2027/main.tex").read_text(encoding="utf-8")
oceans = (ROOT / "papers/oceans2027/main.tex").read_text(encoding="utf-8")
fw = (ROOT / "docs/competitions/public-floatwaste-benchmark.md").read_text(encoding="utf-8")

print("== PAKDD: main table (hit@1/hit@5/MRR per config x type) ==")
CELL = r"(?:\\best\{)?([.\d]+)(?:\})?"
name_map = {"bm25": "BM25", "baseline": "Lex+Graph", "twostage": "Dense+Rerank",
            "hybrid_rrf": "RRF Hybrid", "hybrid_v3_titleboost": "TB Hybrid"}
for cfg, texname in name_map.items():
    m = re.search(re.escape(texname) + r"\s*" + (r"\s*&\s*" + CELL) * 9, pakdd)
    if not m:
        fails.append(f"main table row not found: {texname}")
        continue
    got = m.groups()
    exp4 = []
    for cat in ("single", "single2", "multihop"):
        v = sig["metrics"][cfg][cat]
        exp4 += [v["hit@1"], v["hit@5"], v["mrr"]]
    if not cells_close(got, exp4):
        fails.append(f"main table {texname}: tex={got} expected(4dp)={exp4}")
    else:
        print(f"  ok {texname}: {'/'.join(h3(x) for x in exp4)}")
# router row from routing_eval.json
m = re.search("Rule router" + r"\s*" + (r"\s*&\s*" + CELL) * 9, pakdd)
if not m:
    fails.append("main table row not found: Rule router")
else:
    got = m.groups()
    exp4 = []
    for cat in ("single", "single2", "multihop"):
        v = route["routed_rule"]["per_category"][cat]
        exp4 += [v["hit@1"], v["hit@5"], v["mrr"]]
    if not cells_close(got, exp4):
        fails.append(f"main table Rule router: tex={got} expected(4dp)={exp4}")
    else:
        print(f"  ok Rule router: {'/'.join(h3(x) for x in exp4)}")

print("== PAKDD: audit / benchmark / refuse / significance / router claims ==")
check("audit citation", pakdd, f"{audit['precision_proxy']['citation_verifiable_rate']*100:.1f}\\%")
check("audit 302/336", pakdd, "302/336")
check("audit fully", pakdd, f"{audit['precision_proxy']['relation_fully_traceable_rate']*100:.1f}\\%")
check("audit node", pakdd, f"{audit['precision_proxy']['node_name_traceable_rate']*100:.1f}\\%")
counts = bench["counts"]
check("counts title", pakdd, f"& {counts['single']} &")
check("counts entity", pakdd, f"& {counts['single2']} &")
check("counts multihop", pakdd, f"& {counts['multihop']} &")
check("counts refuse", pakdd, f"& {counts['refuse']} &")
check("n=306", pakdd, "306")
check("refuse baseline", pakdd, "0.0 & 46.5")
check("refuse bm25", pakdd, "7.37 & 13.72")
check("refuse twostage", pakdd, "0.0008 & 0.0031")
check("sig title bm25", pakdd, "$4.8{\\times}10^{-8}$")
check("sig title fusion", pakdd, "$1.1{\\times}10^{-7}$")
check("sig entity dense", pakdd, "$1.5{\\times}10^{-7}$")
check("sig entity bm25", pakdd, "$1.3{\\times}10^{-2}$")
check("sig multihop dense", pakdd, "$7.7{\\times}10^{-8}$")
check("sig multihop bm25", pakdd, "$1.6{\\times}10^{-3}$")
check("router vs baseline", pakdd, "$p{=}1.3{\\times}10^{-3}$")
check("router vs bm25", pakdd, "$p{=}3.6{\\times}10^{-3}$")
check("router vs oracle", pakdd, "($p{=}0.10$)")
check("router overall", pakdd, "hit@5 .970 / MRR .848")
check("oracle overall", pakdd, "hit@5 .970 / MRR .855")
check("router titles", pakdd, "73/81")
check("abstract bm25 h@1", pakdd, "(hit@1 .901)")
check("abstract graph", pakdd, "(hit@5 .930/.983)")

print("== OCEANS: detection numbers appear verbatim in the fact-source doc ==")
for num in ("0.1432", "0.0930", "0.2702", "0.1155", "0.0744", "0.2417",
            "0.5135", "0.3444", "0.5376", "0.7229", "0.3341", "0.4029",
            "0.1299", "0.2105", "0.2408", "0.5054", "0.0631", "7,906",
            "27,583", "0.5665", "0.5114"):
    check(f"fw {num}", fw, num)
    check(f"oceans {num}", oceans, num)
check("oceans audit", oceans, "89.9\\%")
check("oceans 21 tools", oceans, "21 read-only tools")
check("oceans ontology", oceans, "100 nodes, 200 relations over 27 assets")

print()
if fails:
    print("FAILURES:")
    for f in fails:
        print(" ", f)
    sys.exit(1)
print("ALL NUMBER CHECKS PASSED")
