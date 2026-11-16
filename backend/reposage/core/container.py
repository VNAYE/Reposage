"""Wires the object graph. The only place that knows concrete implementations."""

from __future__ import annotations

from dataclasses import dataclass

import reposage.generation  # noqa: F401  (auto-registers guardrails/verifiers)
import reposage.ingestion  # noqa: F401  (auto-registers loaders/chunkers)
import reposage.providers  # noqa: F401  (auto-registers chat/embedding providers)
import reposage.retrieval  # noqa: F401  (auto-registers rerankers)
import reposage.storage  # noqa: F401  (auto-registers index stores)
from reposage.config import Settings
from reposage.core import plugins
from reposage.domain.interfaces import (
    ChatProvider,
    EmbeddingProvider,
    IndexStore,
    IndexingService,
    Reranker,
    Retriever,
    Verifier,
)
from reposage.generation.chat import ChatService
from reposage.generation.prompts import PromptBuilder
from reposage.ingestion.indexer import RepositoryIndexer
from reposage.ingestion.jobs import IndexJobStore
from reposage.observability.metrics import CostModel, MetricsRecorder
from reposage.retrieval.hybrid import HybridRetriever


@dataclass
class Container:
    settings: Settings
    chat: ChatProvider
    embeddings: EmbeddingProvider
    index: IndexStore
    metrics: MetricsRecorder
    retriever: Retriever
    chat_service: ChatService
    indexing: IndexingService
    jobs: IndexJobStore
    reranker: Reranker | None = None
    verifier: Verifier | None = None
    _started: bool = False

    async def startup(self) -> None:
        if self._started:
            return
        await self.index.open()
        await self.metrics.open()
        self._started = True

    async def shutdown(self) -> None:
        await self.metrics.close()
        await self.index.close()
        self._started = False


def build_container(settings: Settings) -> Container:
    chat = plugins.chat_providers.create(settings.chat_provider, settings)
    embeddings = plugins.embedding_providers.create(settings.embedding_provider, settings)

    base_deps = plugins.Deps(chat=chat, embeddings=embeddings)
    index = plugins.index_stores.create(settings.storage_backend, settings, base_deps)

    metrics_backend = (
        settings.storage_backend if settings.metrics_backend == "auto" else settings.metrics_backend
    )
    sink = plugins.metrics_sinks.create(metrics_backend, settings, base_deps)
    metrics = MetricsRecorder(
        sink,
        CostModel(
            input_per_mtok=settings.price_input_per_mtok,
            output_per_mtok=settings.price_output_per_mtok,
            embedding_per_mtok=settings.price_embedding_per_mtok,
        ),
    )

    deps = plugins.Deps(chat=chat, embeddings=embeddings, metrics=metrics)
    reranker = None if settings.reranker == "none" else plugins.rerankers.create(
        settings.reranker, settings, deps
    )
    verifier = None if not settings.verify_answers else plugins.verifiers.create(
        settings.verifier_provider, settings, deps
    )
    guardrails = [
        plugins.guardrails.create(name, settings, deps) for name in plugins.guardrails.names()
    ]

    chunker = plugins.chunkers.create(settings.chunker, settings, deps)
    loaders = {
        name: plugins.repo_loaders.create(name, settings, deps) for name in plugins.repo_loaders.names()
    }

    retriever = HybridRetriever(settings, embeddings, index, reranker)
    indexing = RepositoryIndexer(settings, embeddings, index, loaders, chunker, metrics)
    chat_service = ChatService(
        settings,
        guardrails=guardrails,
        retriever=retriever,
        chat=chat,
        metrics=metrics,
        prompt_builder=PromptBuilder(),
        verifier=verifier,
    )

    return Container(
        settings=settings,
        chat=chat,
        embeddings=embeddings,
        index=index,
        metrics=metrics,
        retriever=retriever,
        chat_service=chat_service,
        indexing=indexing,
        jobs=IndexJobStore(indexing),
        reranker=reranker,
        verifier=verifier,
    )
