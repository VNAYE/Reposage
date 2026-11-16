"""Ports of the application.

Every capability sits behind one of these interfaces. Adding a capability means
adding a new class in the matching package and registering it - no existing
class has to change (open/closed principle).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, ClassVar

from .events import AnswerEvent
from .models import (
    ChatChunk,
    ChatResult,
    Chunk,
    GuardrailVerdict,
    IndexReport,
    MetricsSummary,
    RepoSpec,
    RepoSummary,
    ScoredChunk,
    SourceFile,
    Usage,
    VerificationResult,
)

if TYPE_CHECKING:  # pragma: no cover
    from reposage.config import Settings


class ChatProvider(ABC):
    """LLM used for answering, reranking and verification."""

    name: ClassVar[str] = ""

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    def stream(self, *, system: str, prompt: str) -> AsyncIterator[ChatChunk]:
        """Yield text deltas; ``usage`` is cumulative and only needed on the last one."""

    @abstractmethod
    async def complete(self, *, system: str, prompt: str, json_mode: bool = False) -> ChatResult: ...


class EmbeddingProvider(ABC):
    name: ClassVar[str] = ""

    @property
    @abstractmethod
    def model(self) -> str: ...

    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...


class IndexStore(ABC):
    """Hybrid index: one adapter owns both the vector and keyword representations."""

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    @abstractmethod
    async def upsert(self, repo: str, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None: ...

    @abstractmethod
    async def vector_search(self, repo: str, vector: Sequence[float], limit: int) -> list[ScoredChunk]: ...

    @abstractmethod
    async def keyword_search(self, repo: str, query: str, limit: int) -> list[ScoredChunk]: ...

    @abstractmethod
    async def delete_repo(self, repo: str) -> None: ...

    @abstractmethod
    async def list_repos(self) -> list[RepoSummary]: ...

    @abstractmethod
    async def count(self, repo: str) -> int: ...

    async def flush(self) -> None:
        """Persist pending writes, if the backend buffers."""
        return None


class Retriever(ABC):
    @abstractmethod
    async def retrieve(self, *, repo: str, query: str, limit: int) -> list[ScoredChunk]: ...


class Reranker(ABC):
    name: ClassVar[str] = ""

    @abstractmethod
    async def rerank(
        self,
        *,
        query: str,
        chunks: Sequence[ScoredChunk],
        limit: int,
        repo: str = "",
    ) -> list[ScoredChunk]: ...


class Guardrail(ABC):
    name: ClassVar[str] = ""

    @abstractmethod
    def inspect(self, text: str) -> GuardrailVerdict: ...


class Verifier(ABC):
    name: ClassVar[str] = ""

    @abstractmethod
    async def verify(
        self,
        *,
        answer: str,
        sources: Sequence[ScoredChunk],
        question: str = "",
    ) -> VerificationResult: ...


class MetricsSink(ABC):
    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    @abstractmethod
    async def record(
        self,
        usage: Usage,
        *,
        kind: str,
        repo: str = "",
        verified: bool | None = None,
        guardrail: str = "allow",
    ) -> None: ...

    @abstractmethod
    async def summary(self, *, hours: int = 24) -> MetricsSummary: ...


class RepoLoader(ABC):
    name: ClassVar[str] = ""

    @abstractmethod
    async def load(self, spec: RepoSpec) -> list[SourceFile]: ...


class Chunker(ABC):
    @abstractmethod
    def split(self, repo: str, file: SourceFile) -> list[Chunk]: ...


class IndexingService(ABC):
    """Kept as a port so the API layer can be wired to a fake in tests."""

    @abstractmethod
    async def index_repo(self, spec: RepoSpec) -> IndexReport: ...

    @abstractmethod
    async def ensure_indexed(self, spec: RepoSpec) -> IndexReport | None: ...


class AnswerService(ABC):
    @abstractmethod
    def ask(self, *, repo: str, question: str) -> AsyncIterator[AnswerEvent]: ...


__all__ = [
    "AnswerService",
    "ChatProvider",
    "Chunker",
    "EmbeddingProvider",
    "Guardrail",
    "IndexStore",
    "IndexingService",
    "MetricsSink",
    "RepoLoader",
    "Reranker",
    "Retriever",
    "Settings",
    "Verifier",
]
