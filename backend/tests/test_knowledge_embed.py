"""Unit tests for the hybrid retrieval helpers (no network calls)."""
from __future__ import annotations

from app.services.knowledge_embed import HybridChunk, HybridIndex, rrf_fuse


def test_rrf_fuse_prefers_assets_ranked_high_in_both() -> None:
    fused = rrf_fuse([
        ["a", "b", "c"],
        ["c", "a", "b"],
    ])
    # "a" and "c" appear top-2 in both rankings -> they must beat "b"
    assert set(fused[:2]) == {"a", "c"}
    assert fused[-1] == "b"


def test_rrf_fuse_handles_disjoint_rankings() -> None:
    fused = rrf_fuse([["x"], ["y"]])
    assert sorted(fused) == ["x", "y"]


def test_rrf_fuse_is_deterministic_on_ties() -> None:
    first = rrf_fuse([["p", "q"], ["q", "p"]])
    second = rrf_fuse([["p", "q"], ["q", "p"]])
    assert first == second


def test_hybrid_index_rank_assets_uses_best_chunk_score() -> None:
    index = HybridIndex()
    index._chunks = [
        HybridChunk(asset_id="a", asset_version_id="v1", text="t1", vector=[1.0, 0.0]),
        HybridChunk(asset_id="a", asset_version_id="v1", text="t2", vector=[0.0, 1.0]),
        HybridChunk(asset_id="b", asset_version_id="v2", text="t3", vector=[0.9, 0.1]),
    ]
    ranked = index.rank_assets([1.0, 0.0])
    # asset "a" has a perfect-match chunk; "b" is close but lower
    assert ranked[0] == "a"
    assert ranked[1] == "b"


def test_hybrid_index_stats_and_empty_rank() -> None:
    index = HybridIndex()
    assert index.stats()["chunks"] == 0
    assert index.rank_assets([1.0]) == []
