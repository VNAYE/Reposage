"""Orchestrates load -> chunk -> embed -> store for one repository."""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import TypeVar

from reposage.config import Settings
from reposage.core.text import estimate_tokens
from reposage.domain.interfaces import Chunker, EmbeddingProvider, IndexStore, IndexingService, RepoLoader
from reposage.domain.models import IndexReport, RepoSpec, Usage
from reposage.observability.metrics import MetricsRecorder

T = TypeVar("T")


def _batched(items: Sequence[T], size: int) -> list[Sequence[T]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


class RepositoryIndexer(IndexingService):
    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingProvider,
        index: IndexStore,
        loaders: Mapping[str, RepoLoader],
        chunker: Chunker,
        metrics: MetricsRecorder | None = None,
    ) -> None:
        self._settings = settings
        self._embeddings = embeddings
        self._index = index
        self._loaders = loaders
        self._chunker = chunker
        self._metrics = metrics

    async def index_repo(self, spec: RepoSpec) -> IndexReport:
        started = time.perf_counter()
        loader = self._loaders.get(spec.source)
        if loader is None:
            available = ", ".join(sorted(self._loaders)) or "none"
            raise ValueError(f"unknown repository source {spec.source!r} (available: {available})")

        files = await loader.load(spec)
        chunks = [chunk for file in files for chunk in self._chunker.split(spec.slug, file)]
        truncated = max(0, len(chunks) - self._settings.max_chunks)
        chunks = chunks[: self._settings.max_chunks]
        if not chunks:
            raise ValueError(f"no chunks produced for {spec.slug} (are the files too small?)")

        await self._index.delete_repo(spec.slug)
        for batch in _batched(chunks, self._settings.embed_batch_size):
            texts = [chunk.content for chunk in batch]
            batch_started = time.perf_counter()
            vectors = await self._embeddings.embed_documents(texts)
            await self._index.upsert(spec.slug, batch, vectors)
            if self._metrics is not None:
                tokens = sum(estimate_tokens(text) for text in texts)
                await self._metrics.record(
                    Usage(
                        prompt_tokens=tokens,
                        total_tokens=tokens,
                        latency_ms=(time.perf_counter() - batch_started) * 1000,
                        model=self._embeddings.model,
                    ),
                    kind="embedding",
                    repo=spec.slug,
                )
        await self._index.flush()

        return IndexReport(
            repo=spec.slug,
            files=len(files),
            chunks=len(chunks),
            skipped=truncated,
            duration_ms=(time.perf_counter() - started) * 1000,
        )

    async def ensure_indexed(self, spec: RepoSpec) -> IndexReport | None:
        if await self._index.count(spec.slug) > 0:
            return None
        return await self.index_repo(spec)
