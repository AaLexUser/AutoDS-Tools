"""Rank fusion for multi-index vector retrieval.

Cosine scores from separate Neo4j vector indexes are not directly comparable
(e.g. 721 Method nodes vs 127 Example nodes). Reciprocal Rank Fusion (RRF)
combines per-index rankings without library-specific score adjustments.
"""

from __future__ import annotations

from neo4j_graphrag.types import RetrieverResultItem

from pygrad.graphrag.common import NODE_LABELS

DEFAULT_RRF_K = 60


def result_dedupe_key(metadata: dict) -> str:
    """Stable key for deduplicating fused results."""
    api_path = metadata.get("api_path")
    if api_path:
        return str(api_path)
    preview = metadata.get("content_preview", "")
    if preview:
        return str(preview)[:120]
    return ""


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[RetrieverResultItem]],
    top_k: int,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[str]:
    """Fuse ranked result lists from multiple indexes using RRF.

    Args:
        ranked_lists: Mapping of node label to ordered retrieval results
        top_k: Number of results to return
        rrf_k: RRF smoothing constant (default 60)

    Returns:
        Formatted result strings in fused rank order
    """
    fused_scores: dict[str, float] = {}
    content_by_key: dict[str, str] = {}

    for node_type in NODE_LABELS:
        items = ranked_lists.get(node_type, [])
        for rank, item in enumerate(items, start=1):
            metadata = item.metadata or {}
            key = result_dedupe_key(metadata)
            if not key:
                key = item.content[:120]
            fused_scores[key] = fused_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
            content_by_key[key] = item.content

    sorted_keys = sorted(fused_scores, key=lambda k: fused_scores[k], reverse=True)
    return [content_by_key[k] for k in sorted_keys[:top_k]]
