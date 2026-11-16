"""Hybrid retrieval helpers."""

from dataclasses import dataclass


@dataclass
class Hit:
    doc_id: str
    score: float


def rrf_fuse(rankings: list[list[Hit]], k: int = 60) -> list[Hit]:
    """Reciprocal Rank Fusion: score = sum(1 / (k + rank)) across rankings."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.doc_id] = scores.get(hit.doc_id, 0.0) + 1.0 / (k + rank)

    fused = [Hit(doc_id=doc_id, score=score) for doc_id, score in scores.items()]
    return sorted(fused, key=lambda hit: hit.score, reverse=True)


def hybrid_search(
    vector_hits: list[Hit],
    keyword_hits: list[Hit],
    limit: int = 5,
) -> list[Hit]:
    """Fuse vector and keyword candidates and keep the best `limit`."""
    return rrf_fuse([vector_hits, keyword_hits])[:limit]
