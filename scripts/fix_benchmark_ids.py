#!/usr/bin/env python3
"""CRITICAL FIX 2026-10-26: benchmark item ids were not unique.

The builder emitted ids like `single-OD-SEA-E-0` for EVERY asset of the
OD-SEA-E-* family (306 items -> 22 unique ids, 283 same-id-different-gold
conflicts). Every id-keyed per-item analysis silently collapsed: results
dicts kept one entry per id (last writer wins), and metrics paired each
item's gold with a ranking retrieved for a DIFFERENT question.

Fix: append an occurrence index to every duplicated id (`<id>-<k>`) so ids
are unique while questions/gold stay byte-identical. A rerun of the
evaluation with warm caches then produces correctly paired per-item results.
"""
from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

EVAL = Path(__file__).resolve().parent.parent / "artifacts" / "knowledge-retrieval-eval"
BENCH = EVAL / "benchmark.json"
BACKUP = EVAL / "benchmark_ids_collided_20261026.json"


def main() -> int:
    if not BACKUP.exists():
        shutil.copyfile(BENCH, BACKUP)
        print(f"backup -> {BACKUP.name}")
    bench = json.loads(BENCH.read_text(encoding="utf-8"))
    items = bench["items"]
    seen: Counter = Counter()
    for it in items:
        seen[it["id"]] += 1
        if seen[it["id"]] > 1 or True:  # re-id every item deterministically
            it["id"] = f"{it['id']}-{seen[it['id']] - 1}"
    dup = [k for k, v in Counter(i["id"] for i in items).items() if v > 1]
    assert not dup, f"still duplicated: {dup}"
    bench["note"] = (bench.get("note", "") +
        " | 2026-10-26: ids made unique by appending occurrence index "
        "(builder originally emitted per-template ids shared across assets; "
        "see benchmark_ids_collided_20261026.json for the original).")
    BENCH.write_text(json.dumps(bench, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"re-id'd {len(items)} items -> {len(set(i['id'] for i in items))} unique ids")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
