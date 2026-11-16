"""Hybrid retrieval: vector + keyword candidates fused with Reciprocal Rank Fusion."""

from __future__ import annotations

import logging

from reposage.config import Settings
from reposage.domain.interfaces import EmbeddingProvider, IndexStore, Reranker, Retriever
from reposage.domain.models import Chunk, ScoredChunk

log = logging.getLogger(__name__)


class HybridRetriever(Retriever):
    """Runs both searches, fuses ranks, then optionally reranks the shortlist."""

    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingProvider,
        index: IndexStore,
        reranker: Reranker | None = None,
    ) -> None:
        self._settings = settings
        self._embeddings = embeddings
        self._index = index
        self._reranker = reranker

    async def retrieve(self, *, repo: str, query: str, limit: int) -> list[ScoredChunk]:
        query = query.strip()
        if not query:
            return []

        vector_hits: list[ScoredChunk] = []
        try:
            vector = await self._embeddings.embed_query(query)
            vector_hits = await self._index.vector_search(repo, vector, self._settings.vector_candidates)
        except Exception as exc:  # keyword search still works without embeddings
            log.warning("vector search unavailable, using keyword results only: %s", exc)

        keyword_hits = await self._index.keyword_search(repo, query, self._settings.keyword_candidates)
        fused = self._fuse(vector_hits, keyword_hits)
        if not fused:
            return []

        if self._reranker is None:
            return fused[:limit]

        shortlist = fused[: self._settings.rerank_candidates]
        return await self._reranker.rerank(query=query, chunks=shortlist, limit=limit, repo=repo)

    def _fuse(
        self,
        vector_hits: list[ScoredChunk],
        keyword_hits: list[ScoredChunk],
    ) -> list[ScoredChunk]:
        scores: dict[str, float] = {}
        origins: dict[str, set[str]] = {}
        chunks: dict[str, Chunk] = {}

        for origin, hits in (("vector", vector_hits), ("keyword", keyword_hits)):
            for rank, hit in enumerate(hits, start=1):
                key = hit.chunk.id
                chunks[key] = hit.chunk
                scores[key] = scores.get(key, 0.0) + 1.0 / (self._settings.rrf_k + rank)
                origins.setdefault(key, set()).add(origin)

        ordered = sorted(scores, key=lambda key: scores[key], reverse=True)
        return [
            ScoredChunk(
                chunk=chunks[key],
                score=scores[key],
                origins=tuple(sorted(origins[key])),
            )
            for key in ordered
        ]
