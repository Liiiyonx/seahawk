#!/usr/bin/env python3
"""Harvest marine-related articles from MEE server-rendered column pages.

Fetches the two known marine columns (plus pagination), filters links by marine
keywords, dedupes against the existing corpus manifest, downloads the article
HTML into artifacts/open-data-eval/corpus/, and writes extra_sources.json in
the same schema as SOURCE_PAGES in scripts/open_data_corpus.py (which loads it
as an extension list).
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "artifacts" / "open-data-eval" / "corpus"
MANIFEST = CORPUS / "manifest.json"
EXTRA = CORPUS / "extra_sources.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

COLUMNS = [
    "https://www.mee.gov.cn/ywgz/hysthjbh/hyqfglysp/",
    "https://www.mee.gov.cn/ywgz/hysthjbh/hyqfglysp/index_{p}.html",
    "https://www.mee.gov.cn/ywgz/hysthjbh/",
    "https://www.mee.gov.cn/ywgz/hysthjbh/index_{p}.html",
]
PAGES = (1, 2, 3)

MARINE_RE = re.compile(r"海洋|倾倒|岸滩|微塑料|海漂|海域|海岛|珊瑚|红树林|入海|海水|近岸|滨海|海洋生态|海洋环境")
ARTICLE_RE = re.compile(r"t20(\d{6})_(\d+)\.html")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="ignore")


def main() -> int:
    existing_urls: set[str] = set()
    if MANIFEST.exists():
        for doc in json.loads(MANIFEST.read_text(encoding="utf-8")).get("documents", []):
            existing_urls.add(doc.get("source_url", ""))
    existing_extra: list[dict] = []
    if EXTRA.exists():
        existing_extra = json.loads(EXTRA.read_text(encoding="utf-8"))
        for doc in existing_extra:
            existing_urls.add(doc.get("source_url", ""))

    found: dict[str, str] = {}
    for tpl in COLUMNS:
        pages: list[str] = [tpl] if "{p}" not in tpl else [tpl.format(p=p) for p in PAGES]
        for page in pages:
            try:
                html = fetch(page)
            except Exception as exc:
                print(f"skip {page}: {type(exc).__name__} {str(exc)[:50]}")
                continue
            for m in re.finditer(r'href="([^"]*?(t20\d{6}_\d+)\.html)"[^>]*>([^<]{8,120})<', html):
                path, _, title = m.group(1), m.group(2), m.group(3).strip()
                url = path if path.startswith("http") else "https://www.mee.gov.cn/" + path.lstrip("/").replace("gk0", "xxgk/xxgk/gk0", 1) if not path.startswith("http") and path.startswith(("xxgk", "gk")) else ("https://www.mee.gov.cn/" + path.lstrip("/") if not path.startswith("http") else path)
                # normalize: links on column pages come as relative like ../xxgk2018/... or absolute
                if not path.startswith("http"):
                    if path.startswith("./") or path.startswith("../"):
                        url = "https://www.mee.gov.cn/ywgz/hysthjbh/" + path
                    else:
                        url = "https://www.mee.gov.cn/" + path.lstrip("/")
                if not MARINE_RE.search(title):
                    continue
                found[url] = title
            time.sleep(0.5)

    # also add known-good explicit finds from search (already-public URLs)
    found.setdefault("https://www.mee.gov.cn/xxgk2018/xxgk/xxgk05/202301/t20230109_1012078.html",
                     "关于贯彻落实《国务院办公厅关于加强入河入海排污口监督管理工作的实施意见》的通知")

    new_docs: list[dict] = []
    seq = 1
    for url, title in sorted(found.items()):
        if url in existing_urls:
            continue
        m = ARTICLE_RE.search(url)
        if not m:
            continue
        ymd, art = m.group(1), m.group(2)
        year = "20" + ymd[:2]
        if title.startswith("关于发布国家生态环境标准") or "技术规范" in title or "技术导则" in title or "评价规范" in title or "监督管理技术指南" in title:
            kind, k = "标准公告", "STD"
        elif "批复" in title:
            kind, k = "环评批复", "PERMIT"
        elif "倾倒区" in title:
            kind, k = "倾倒区公告", "DUMP"
        else:
            kind, k = "海洋管理文件", "DOC"
        fname = f"extra-{year}-{art}.html"
        try:
            html = fetch(url)
        except Exception as exc:
            print(f"download fail {url}: {str(exc)[:50]}")
            continue
        if len(html) < 5000:
            print(f"too short, skip {url}")
            continue
        (CORPUS / fname).write_text(html, encoding="utf-8")
        new_docs.append({
            "file": fname,
            "title": title,
            "source_url": url,
            "publisher": "中华人民共和国生态环境部",
            "asset_id": f"OD-SEA-{k}-{year}-{seq:02d}",
            "asset_type": "document",
            "standard_codes": ["marine-" + kind, "open-data"],
            "_kind": kind,
        })
        print(f"  + [{kind}] {title[:44]} -> {fname}")
        seq += 1
        time.sleep(0.4)

    merged = existing_extra + new_docs
    EXTRA.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nnew: {len(new_docs)} | extra_sources total: {len(merged)} -> {EXTRA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
