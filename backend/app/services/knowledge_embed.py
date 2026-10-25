"""Dense retrieval helpers over the ModelArts MaaS embeddings/rerank endpoints.

The channel reuses ``KNOWLEDGE_LLM_BASE_URL`` / ``KNOWLEDGE_LLM_API_KEY``
(the same MaaS key serves chat, embeddings and rerank). Unconfigured or
failing calls never break search: callers fall back to lexical ranking.

``HybridIndex`` builds an in-memory chunk embedding index of the ACTIVE
knowledge corpus (title + content chunks). It rebuilds lazily when the
corpus fingerprint (asset count + max updated_at) changes, so asset edits
are picked up without a restart. Scale target: the public/demo corpus
(tens of documents); a larger corpus should move this to a vector store.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from app.core.config import settings


@dataclass
class HybridChunk:
    asset_id: str
    asset_version_id: str
    text: str
    vector: list[float] = field(default_factory=list)


def embed_base_url() -> str:
    return settings.knowledge_embed_base_url or settings.knowledge_llm_base_url


def embed_api_key() -> str:
    return settings.knowledge_embed_api_key or settings.knowledge_llm_api_key


def embed_channel_ready() -> bool:
    return bool(embed_base_url() and embed_api_key())


def _post(path: str, payload: dict, timeout: int = 60) -> dict:
    url = embed_base_url().rstrip("/") + path
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {embed_api_key()}",
        },
        method="POST",
    )
    last: Exception | None = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 5:
                time.sleep(6 + 5 * attempt)
                continue
            raise
        except Exception as exc:  # transient network hiccups
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"maas request failed: {last}")


def embed_texts(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), 16):
        batch = texts[i:i + 16]
        data = _post("/embeddings", {"model": settings.knowledge_embed_model, "input": batch})
        out.extend(item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"]))
        if i + 16 < len(texts):
            time.sleep(0.3)
    return out


def rerank_documents(query: str, documents: list[str]) -> list[dict]:
    data = _post(
        "/rerank",
        {"model": settings.knowledge_rerank_model, "query": query, "documents": documents},
    )
    return data.get("results", [])


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


def rrf_fuse(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal-rank fusion over asset-id rankings (stable, deterministic)."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for i, asset_id in enumerate(ranking):
            scores[asset_id] = scores.get(asset_id, 0.0) + 1.0 / (k + i + 1)
    return [a for a, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


class HybridIndex:
    """In-memory chunk index over the ACTIVE corpus, rebuilt on corpus change."""

    _CHUNK_CHARS = 800

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._chunks: list[HybridChunk] = []
        self._fingerprint: tuple[int, str] | None = None
        self._built_at: float = 0.0

    def _fingerprint_of(self, documents: list[tuple[str, str, str, str]]) -> tuple[int, str]:
        latest_version = max((d[1] for d in documents), default="")
        return len(documents), latest_version

    def build(self, documents: list[tuple[str, str, str, str]]) -> None:
        """documents: (asset_id, asset_version_id, title, content_text[, updated]) tuples."""
        chunks: list[HybridChunk] = []
        for doc in documents:
            asset_id, asset_version_id, title, content = doc[0], doc[1], doc[2], doc[3]
            text = (content or "").strip()
            pieces = [text[i:i + self._CHUNK_CHARS] for i in range(0, len(text), self._CHUNK_CHARS)] or [""]
            # 标题加权：R-KN-07 v3 评测显示 标题x3 前缀提升召回深度（hit@3/@5）
            for piece in pieces:
                chunks.append(HybridChunk(
                    asset_id=asset_id,
                    asset_version_id=asset_version_id,
                    text="\n".join([title, title, title, piece])[:1800],
                ))
        vectors = embed_texts([c.text for c in chunks])
        for chunk, vec in zip(chunks, vectors):
            chunk.vector = vec
        with self._lock:
            self._chunks = chunks
            self._built_at = time.time()

    def ensure(self, documents: list[tuple[str, str, str, str]]) -> bool:
        """Rebuild if needed; returns True when an index is available."""
        if not embed_channel_ready():
            return False
        fp = self._fingerprint_of(documents)
        with self._lock:
            fresh = self._chunks and self._fingerprint == fp
        if not fresh:
            try:
                self.build(documents)
                with self._lock:
                    self._fingerprint = fp
            except Exception:
                return bool(self._chunks)
        return True

    def rank_assets(self, query_vector: list[float]) -> list[str]:
        with self._lock:
            chunks = list(self._chunks)
        best: dict[str, float] = {}
        for c in chunks:
            if not c.vector:
                continue
            score = _cosine(query_vector, c.vector)
            if score > best.get(c.asset_id, -1.0):
                best[c.asset_id] = score
        return [a for a, _ in sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))]

    def stats(self) -> dict:
        with self._lock:
            return {"chunks": len(self._chunks), "built_at": self._built_at}


HYBRID_INDEX = HybridIndex()
