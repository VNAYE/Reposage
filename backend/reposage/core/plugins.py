"""Registries for every extension point plus the dependency bundle passed to factories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from reposage.core.registry import Registry
from reposage.domain.interfaces import (
    ChatProvider,
    Chunker,
    EmbeddingProvider,
    Guardrail,
    IndexStore,
    MetricsSink,
    RepoLoader,
    Reranker,
    Verifier,
)

if TYPE_CHECKING:  # pragma: no cover
    from reposage.observability.metrics import MetricsRecorder

chat_providers: Registry[ChatProvider] = Registry("chat provider")
embedding_providers: Registry[EmbeddingProvider] = Registry("embedding provider")
index_stores: Registry[IndexStore] = Registry("index store")
metrics_sinks: Registry[MetricsSink] = Registry("metrics sink")
repo_loaders: Registry[RepoLoader] = Registry("repo loader")
chunkers: Registry[Chunker] = Registry("chunker")
rerankers: Registry[Reranker] = Registry("reranker")
guardrails: Registry[Guardrail] = Registry("guardrail")
verifiers: Registry[Verifier] = Registry("verifier")


@dataclass(frozen=True, slots=True)
class Deps:
    """Already-built collaborators a factory may need."""

    chat: ChatProvider | None = None
    embeddings: EmbeddingProvider | None = None
    metrics: MetricsRecorder | None = None
