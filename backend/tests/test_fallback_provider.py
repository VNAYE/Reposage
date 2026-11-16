from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from reposage.domain.interfaces import ChatProvider
from reposage.domain.models import ChatChunk, ChatResult, Usage
from reposage.providers.fallback import FallbackChatProvider


class _StubProvider(ChatProvider):
    name = "stub"

    def __init__(self, model: str, *, fail_before: bool = False, fail_after: bool = False) -> None:
        self._model = model
        self._fail_before = fail_before
        self._fail_after = fail_after

    @property
    def model(self) -> str:
        return self._model

    async def stream(self, *, system: str, prompt: str) -> AsyncIterator[ChatChunk]:
        if self._fail_before:
            raise RuntimeError("503 unavailable")
        yield ChatChunk(text="partial", usage=Usage(model=self._model))
        if self._fail_after:
            raise RuntimeError("connection dropped")
        yield ChatChunk(text=" answer", usage=Usage(model=self._model))

    async def complete(self, *, system: str, prompt: str, json_mode: bool = False) -> ChatResult:
        if self._fail_before:
            raise RuntimeError("503 unavailable")
        return ChatResult(text="ok", usage=Usage(model=self._model))


async def test_stream_falls_back_before_first_token() -> None:
    provider = FallbackChatProvider(
        [
            _StubProvider("primary", fail_before=True),
            _StubProvider("fallback"),
        ]
    )

    chunks = [chunk async for chunk in provider.stream(system="s", prompt="p")]

    assert "".join(chunk.text for chunk in chunks) == "partial answer"
    assert chunks[-1].usage.model == "fallback"


async def test_stream_retries_a_failure_that_happens_mid_answer() -> None:
    provider = FallbackChatProvider(
        [
            _StubProvider("primary", fail_after=True),
            _StubProvider("fallback"),
        ]
    )

    chunks = [chunk async for chunk in provider.stream(system="s", prompt="p")]

    assert "".join(chunk.text for chunk in chunks) == "partial answer"
    assert chunks[-1].usage.model == "fallback"


async def test_stream_skips_a_model_that_never_produces_a_token() -> None:
    class SilentProvider(_StubProvider):
        async def stream(self, *, system: str, prompt: str) -> AsyncIterator[ChatChunk]:
            await asyncio.sleep(5)
            yield ChatChunk(text="too late")

    provider = FallbackChatProvider(
        [SilentProvider("slow"), _StubProvider("fallback")],
        first_token_timeout=0.05,
    )

    chunks = [chunk async for chunk in provider.stream(system="s", prompt="p")]

    assert "".join(chunk.text for chunk in chunks) == "partial answer"
    assert chunks[-1].usage.model == "fallback"


async def test_complete_falls_back() -> None:
    provider = FallbackChatProvider(
        [
            _StubProvider("primary", fail_before=True),
            _StubProvider("fallback"),
        ]
    )

    result = await provider.complete(system="s", prompt="p")

    assert result.text == "ok"
    assert result.usage is not None
    assert result.usage.model == "fallback"


def test_requires_at_least_one_provider() -> None:
    with pytest.raises(ValueError):
        FallbackChatProvider([])
