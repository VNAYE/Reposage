"""Deterministic providers for tests, offline evaluation and CI (no API key needed)."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import AsyncIterator, Sequence

from reposage.config import Settings
from reposage.core.plugins import Deps, chat_providers, embedding_providers
from reposage.core.text import tokenize
from reposage.domain.interfaces import ChatProvider, EmbeddingProvider
from reposage.domain.models import ChatChunk, ChatResult, Usage

_VERIFIER_JSON = {
    "supported": True,
    "score": 1.0,
    "unsupported_claims": [],
    "cited_sources": [],
}


class FakeChatProvider(ChatProvider):
    """Streams a canned answer. Used by the test-suite and ``CHAT_PROVIDER=fake``."""

    name = "fake"

    def __init__(self, reply: str = "Based on the retrieved sources, see [S1].", model: str = "fake-chat") -> None:
        self._reply = reply
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def stream(self, *, system: str, prompt: str) -> AsyncIterator[ChatChunk]:
        words = self._reply.split(" ")
        for index, word in enumerate(words):
            suffix = "" if index == len(words) - 1 else " "
            usage = None
            if index == len(words) - 1:
                usage = Usage(
                    prompt_tokens=max(1, len(prompt) // 4),
                    completion_tokens=max(1, len(self._reply) // 4),
                    total_tokens=max(1, len(prompt) // 4) + max(1, len(self._reply) // 4),
                    model=self._model,
                )
            yield ChatChunk(text=word + suffix, usage=usage)

    async def complete(self, *, system: str, prompt: str, json_mode: bool = False) -> ChatResult:
        text = json.dumps(_VERIFIER_JSON) if json_mode else self._reply
        tokens = max(1, len(prompt) // 4)
        return ChatResult(
            text=text,
            usage=Usage(
                prompt_tokens=tokens,
                completion_tokens=max(1, len(text) // 4),
                total_tokens=tokens + max(1, len(text) // 4),
                model=self._model,
            ),
        )


class FakeEmbeddingProvider(EmbeddingProvider):
    """Hashing bag-of-words embedding: cheap, deterministic, good enough for tests."""

    name = "fake"

    def __init__(self, dimensions: int = 64) -> None:
        self._dimensions = dimensions

    @property
    def model(self) -> str:
        return "fake-embedding"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for token in tokenize(text):
            digest = hashlib.md5(token.encode()).hexdigest()
            vector[int(digest, 16) % self._dimensions] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


@chat_providers.register("fake")
def _build_chat(settings: Settings, deps: Deps | None = None) -> ChatProvider:
    return FakeChatProvider()


@embedding_providers.register("fake")
def _build_embeddings(settings: Settings, deps: Deps | None = None) -> EmbeddingProvider:
    return FakeEmbeddingProvider(dimensions=settings.embedding_dim)
