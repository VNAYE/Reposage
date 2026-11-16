"""Model failover: use the next Gemini model when the current one is overloaded.

Each attempt is buffered server-side until it finishes. That way a model that
dies halfway through an answer can be retried on the next model without the
client seeing a half-answer, while the SSE response still streams tokens.

A model that accepts the connection but never produces a token is treated as
failed, which is what overloaded Gemini endpoints sometimes do.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from reposage.domain.interfaces import ChatProvider
from reposage.domain.models import ChatChunk, ChatResult

log = logging.getLogger(__name__)


async def _close(iterator: Any) -> None:
    closer = getattr(iterator, "aclose", None)
    if closer is not None:
        try:
            await closer()
        except Exception:  # pragma: no cover - best effort cleanup
            pass


class FallbackChatProvider(ChatProvider):
    name = "gemini"

    def __init__(
        self,
        providers: Sequence[ChatProvider],
        *,
        first_token_timeout: float = 10.0,
        stream_idle_timeout: float = 30.0,
        stream_timeout: float = 90.0,
        request_timeout: float = 30.0,
    ) -> None:
        if not providers:
            raise ValueError("FallbackChatProvider needs at least one provider")
        self._providers = list(providers)
        self._first_token_timeout = first_token_timeout
        self._stream_idle_timeout = stream_idle_timeout
        self._stream_timeout = stream_timeout
        self._request_timeout = request_timeout

    @property
    def model(self) -> str:
        return self._providers[0].model

    async def stream(self, *, system: str, prompt: str) -> AsyncIterator[ChatChunk]:
        last_error: Exception | None = None

        for provider in self._providers:
            try:
                chunks = await asyncio.wait_for(
                    self._collect(provider, system=system, prompt=prompt),
                    timeout=self._stream_timeout,
                )
            except Exception as exc:
                last_error = exc
                log.warning("chat model %s failed, trying next: %r", provider.model, exc)
                continue

            for chunk in chunks:
                yield chunk
            return

        raise last_error or RuntimeError("no chat providers are available")

    async def _collect(self, provider: ChatProvider, *, system: str, prompt: str) -> list[ChatChunk]:
        iterator = provider.stream(system=system, prompt=prompt).__aiter__()
        chunks: list[ChatChunk] = []
        try:
            chunks.append(
                await asyncio.wait_for(anext(iterator), timeout=self._first_token_timeout)
            )
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        anext(iterator), timeout=self._stream_idle_timeout
                    )
                except StopAsyncIteration:
                    return chunks
                chunks.append(chunk)
        finally:
            await _close(iterator)

    async def complete(self, *, system: str, prompt: str, json_mode: bool = False) -> ChatResult:
        last_error: Exception | None = None
        for provider in self._providers:
            try:
                return await asyncio.wait_for(
                    provider.complete(system=system, prompt=prompt, json_mode=json_mode),
                    timeout=self._request_timeout,
                )
            except Exception as exc:
                last_error = exc
                log.warning("chat model %s failed: %r", provider.model, exc)
        raise last_error or RuntimeError("no chat providers are available")
