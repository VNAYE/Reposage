"""Gemini implementations of the chat and embedding ports."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from collections.abc import AsyncIterator, Sequence
from typing import Any

from reposage.config import Settings
from reposage.core.plugins import Deps, chat_providers, embedding_providers
from reposage.core.text import estimate_tokens
from reposage.domain.interfaces import ChatProvider, EmbeddingProvider
from reposage.domain.models import ChatChunk, ChatResult, Usage
from reposage.providers.fallback import FallbackChatProvider

log = logging.getLogger(__name__)

_RETRY_DELAY_RE = re.compile(r"retry in (\d+(?:\.\d+)?)s", re.IGNORECASE)


class _TokenWindow:
    """Keeps estimated embedding tokens under a per-minute budget."""

    def __init__(self, tokens_per_minute: int, window: float = 60.0) -> None:
        self._limit = max(0, tokens_per_minute)
        self._window = window
        self._events: deque[tuple[float, int]] = deque()

    async def wait_for(self, tokens: int) -> None:
        if self._limit == 0:
            return
        tokens = min(tokens, self._limit)
        while True:
            now = time.monotonic()
            while self._events and now - self._events[0][0] >= self._window:
                self._events.popleft()
            used = sum(event_tokens for _, event_tokens in self._events)
            if used + tokens <= self._limit:
                self._events.append((now, tokens))
                return
            sleep_for = self._window - (now - self._events[0][0]) + 0.25
            await asyncio.sleep(max(0.5, sleep_for))


def _status_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _retry_delay(exc: Exception) -> float:
    match = _RETRY_DELAY_RE.search(str(exc))
    return min(float(match.group(1)) + 1.0, 90.0) if match else 30.0


def _text_of(chunk: Any) -> str:
    try:
        return getattr(chunk, "text", None) or ""
    except ValueError:  # pragma: no cover - defensive: non-text part
        return ""


def _usage_of(chunk: Any, model: str) -> Usage | None:
    meta = getattr(chunk, "usage_metadata", None)
    if meta is None:
        return None
    prompt = getattr(meta, "prompt_token_count", 0) or 0
    candidates = getattr(meta, "candidates_token_count", 0) or 0
    thoughts = getattr(meta, "thoughts_token_count", 0) or 0
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=candidates + thoughts,
        total_tokens=getattr(meta, "total_token_count", 0) or prompt + candidates + thoughts,
        model=model,
    )


class GeminiChatProvider(ChatProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        max_output_tokens: int = 2048,
        retry_attempts: int = 2,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required when CHAT_PROVIDER=gemini")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._retry_attempts = retry_attempts
        self._client_instance: Any = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def _client(self) -> Any:
        if self._client_instance is None:
            from google import genai
            from google.genai import types

            self._client_instance = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(
                        attempts=self._retry_attempts,
                        initial_delay=0.5,
                        max_delay=4.0,
                    )
                ),
            )
        return self._client_instance

    def _config(self, system: str, *, json_mode: bool) -> Any:
        from google.genai import types

        return types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.0 if json_mode else self._temperature,
            max_output_tokens=self._max_output_tokens,
            response_mime_type="application/json" if json_mode else "text/plain",
        )

    async def stream(self, *, system: str, prompt: str) -> AsyncIterator[ChatChunk]:
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=prompt,
            config=self._config(system, json_mode=False),
        )
        async for chunk in stream:
            text = _text_of(chunk)
            usage = _usage_of(chunk, self._model)
            if text or usage:
                yield ChatChunk(text=text, usage=usage)

    async def complete(self, *, system: str, prompt: str, json_mode: bool = False) -> ChatResult:
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=prompt,
            config=self._config(system, json_mode=json_mode),
        )
        return ChatResult(text=_text_of(response), usage=_usage_of(response, self._model))


class GeminiEmbeddingProvider(EmbeddingProvider):
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        dimensions: int,
        *,
        batch_size: int = 16,
        tokens_per_minute: int = 30_000,
        retry_attempts: int = 5,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required when EMBEDDING_PROVIDER=gemini")
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions
        self._batch_size = max(1, batch_size)
        budget = tokens_per_minute if tokens_per_minute > 0 else 20_000
        self._max_batch_tokens = min(budget, 20_000)
        self._limiter = _TokenWindow(tokens_per_minute)
        self._retry_attempts = max(1, retry_attempts)
        self._client_instance: Any = None

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def _client(self) -> Any:
        if self._client_instance is None:
            from google import genai

            self._client_instance = genai.Client(api_key=self._api_key)
        return self._client_instance

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embed(texts, task_type="RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed([text], task_type="CODE_RETRIEVAL_QUERY")
        return vectors[0]

    def _batches(self, texts: Sequence[str]) -> list[list[str]]:
        batches: list[list[str]] = []
        current: list[str] = []
        tokens = 0
        for text in texts:
            text_tokens = estimate_tokens(text)
            if current and (
                len(current) >= self._batch_size or tokens + text_tokens > self._max_batch_tokens
            ):
                batches.append(current)
                current, tokens = [], 0
            current.append(text)
            tokens += text_tokens
        if current:
            batches.append(current)
        return batches

    async def _embed(self, texts: Sequence[str], *, task_type: str) -> list[list[float]]:
        from google.genai import types

        vectors: list[list[float]] = []
        for batch in self._batches(texts):
            await self._limiter.wait_for(sum(estimate_tokens(text) for text in batch))
            response = await self._request_with_retry(batch, task_type, types)
            embeddings = getattr(response, "embeddings", None) or []
            if len(embeddings) != len(batch):
                raise RuntimeError(
                    f"embedding provider returned {len(embeddings)} vectors for {len(batch)} inputs"
                )
            for embedding in embeddings:
                values = list(embedding.values or [])
                if len(values) != self._dimensions:
                    raise RuntimeError(
                        f"expected {self._dimensions}-dim embeddings, got {len(values)}; "
                        "EMBEDDING_DIM must match the pgvector column and the model output"
                    )
                vectors.append(values)
        return vectors

    async def _request_with_retry(self, batch: list[str], task_type: str, types: Any) -> Any:
        for attempt in range(1, self._retry_attempts + 1):
            try:
                return await self._client.aio.models.embed_content(
                    model=self._model,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=self._dimensions,
                    ),
                )
            except Exception as exc:
                status = _status_code(exc)
                if status not in {429, 503} or attempt == self._retry_attempts:
                    raise
                delay = _retry_delay(exc)
                log.warning(
                    "embedding request hit %s, retrying in %.0fs (%d/%d)",
                    status,
                    delay,
                    attempt,
                    self._retry_attempts,
                )
                await asyncio.sleep(delay)
        raise RuntimeError("embedding retry loop exhausted")  # pragma: no cover


@chat_providers.register("gemini")
def _build_chat(settings: Settings, deps: Deps | None = None) -> ChatProvider:
    def make(model: str) -> GeminiChatProvider:
        return GeminiChatProvider(
            api_key=settings.gemini_api_key,
            model=model,
            temperature=settings.temperature,
            max_output_tokens=settings.max_output_tokens,
            retry_attempts=settings.gemini_retry_attempts,
        )

    primary = make(settings.chat_model)
    fallback_models = [
        name.strip()
        for name in settings.chat_fallback_models.split(",")
        if name.strip() and name.strip() != settings.chat_model
    ]
    if not fallback_models:
        return primary
    return FallbackChatProvider(
        [primary, *(make(name) for name in fallback_models)],
        first_token_timeout=settings.chat_first_token_timeout,
        stream_idle_timeout=settings.chat_stream_idle_timeout,
        stream_timeout=settings.chat_stream_timeout,
        request_timeout=settings.chat_request_timeout,
    )


@embedding_providers.register("gemini")
def _build_embeddings(settings: Settings, deps: Deps | None = None) -> EmbeddingProvider:
    return GeminiEmbeddingProvider(
        api_key=settings.gemini_api_key,
        model=settings.embedding_model,
        dimensions=settings.embedding_dim,
        batch_size=settings.embed_batch_size,
        tokens_per_minute=settings.embedding_tokens_per_minute,
    )
