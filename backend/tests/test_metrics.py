from __future__ import annotations

import pytest

from reposage.domain.models import Usage
from reposage.observability.metrics import CostModel, LocalMetricsSink, MetricsRecorder


def test_cost_model_prices_chat_tokens() -> None:
    usage = CostModel(0.30, 2.50, 0.15).apply(
        Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    )
    assert usage.cost_usd == pytest.approx(2.80)


def test_cost_model_prices_embedding_tokens_separately() -> None:
    usage = CostModel(0.30, 2.50, 0.15).apply(Usage(prompt_tokens=2_000_000), kind="embedding")
    assert usage.cost_usd == pytest.approx(0.30)


async def test_recorder_prices_and_summarises() -> None:
    recorder = MetricsRecorder(LocalMetricsSink(), CostModel(0.30, 2.50, 0.15))

    await recorder.record(
        Usage(prompt_tokens=1_000, completion_tokens=500, total_tokens=1_500, latency_ms=100, model="m"),
        kind="chat",
    )
    await recorder.record(
        Usage(prompt_tokens=2_000, completion_tokens=0, total_tokens=2_000, latency_ms=300, model="m"),
        kind="verify",
    )

    summary = await recorder.summary()

    assert summary.requests == 2
    assert summary.prompt_tokens == 3_000
    assert summary.total_tokens == 3_500
    assert summary.avg_latency_ms == pytest.approx(200)
    assert summary.p95_latency_ms > 0
    assert summary.cost_usd > 0
    assert {row.kind for row in summary.by_model} == {"chat", "verify"}


async def test_summary_window_excludes_old_rows() -> None:
    sink = LocalMetricsSink()
    await sink.record(Usage(total_tokens=10), kind="chat")
    assert (await sink.summary(hours=24)).requests == 1
    assert (await sink.summary(hours=0)).requests == 0
