from __future__ import annotations

from reposage.providers.gemini import GeminiEmbeddingProvider


def _provider(**kwargs) -> GeminiEmbeddingProvider:
    return GeminiEmbeddingProvider("test-key", "gemini-embedding-001", 8, **kwargs)


def test_batches_respect_the_count_limit() -> None:
    provider = _provider(batch_size=2, tokens_per_minute=10_000)
    batches = provider._batches(["x" * 4000] * 5)

    assert all(len(batch) <= 2 for batch in batches)
    assert sum(len(batch) for batch in batches) == 5


def test_batches_respect_the_token_budget() -> None:
    provider = _provider(batch_size=10, tokens_per_minute=2_500)
    batches = provider._batches(["x" * 4000] * 5)

    assert len(batches) == 3
    assert all(len(batch) == 2 for batch in batches[:-1])


def test_zero_quota_disables_pacing_but_keeps_batches() -> None:
    provider = _provider(batch_size=4, tokens_per_minute=0)
    batches = provider._batches(["x" * 400] * 6)

    assert [len(batch) for batch in batches] == [4, 2]
