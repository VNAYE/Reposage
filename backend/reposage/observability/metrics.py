"""Latency, token and cost accounting.

``MetricsRecorder`` is the only thing application code talks to; it prices a
``Usage`` and forwards it to whichever sink is configured.
"""

from __future__ import annotations

import statistics
import time
from collections import defaultdict
from typing import Any

from reposage.config import Settings
from reposage.core.plugins import Deps, metrics_sinks
from reposage.domain.interfaces import MetricsSink
from reposage.domain.models import MetricsSummary, ModelUsage, Usage


class CostModel:
    """Prices are per million tokens and configurable via env (they change over time)."""

    def __init__(self, input_per_mtok: float, output_per_mtok: float, embedding_per_mtok: float) -> None:
        self._input = input_per_mtok
        self._output = output_per_mtok
        self._embedding = embedding_per_mtok

    def apply(self, usage: Usage, *, kind: str = "chat") -> Usage:
        if kind == "embedding":
            tokens = usage.prompt_tokens or usage.total_tokens
            usage.cost_usd = tokens / 1_000_000 * self._embedding
        else:
            usage.cost_usd = (
                usage.prompt_tokens / 1_000_000 * self._input
                + usage.completion_tokens / 1_000_000 * self._output
            )
        return usage


class MetricsRecorder:
    def __init__(self, sink: MetricsSink, cost_model: CostModel) -> None:
        self._sink = sink
        self._cost = cost_model

    async def open(self) -> None:
        await self._sink.open()

    async def close(self) -> None:
        await self._sink.close()

    async def record(
        self,
        usage: Usage,
        *,
        kind: str,
        repo: str = "",
        verified: bool | None = None,
        guardrail: str = "allow",
    ) -> Usage:
        self._cost.apply(usage, kind=kind)
        await self._sink.record(
            usage,
            kind=kind,
            repo=repo,
            verified=verified,
            guardrail=guardrail,
        )
        return usage

    async def summary(self, *, hours: int = 24) -> MetricsSummary:
        return await self._sink.summary(hours=hours)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) < 2:
        return values[0]
    return statistics.quantiles(values, n=20)[18]


def _by_model(rows: list[dict[str, Any]]) -> tuple[ModelUsage, ...]:
    return tuple(
        ModelUsage(
            model=str(row["model"]),
            kind=str(row["kind"]),
            requests=int(row["requests"]),
            total_tokens=int(row["total_tokens"]),
            cost_usd=float(row["cost_usd"]),
            avg_latency_ms=float(row["avg_latency_ms"]),
        )
        for row in rows
    )


class LocalMetricsSink(MetricsSink):
    """In-memory sink for the HF demo, local dev and tests."""

    name = "local"

    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    async def record(
        self,
        usage: Usage,
        *,
        kind: str,
        repo: str = "",
        verified: bool | None = None,
        guardrail: str = "allow",
    ) -> None:
        self._rows.append(
            {
                "created_at": time.time(),
                "kind": kind,
                "model": usage.model,
                "repo": repo,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
                "cost_usd": usage.cost_usd,
                "latency_ms": usage.latency_ms,
                "verified": verified,
                "guardrail": guardrail,
            }
        )

    async def summary(self, *, hours: int = 24) -> MetricsSummary:
        cutoff = time.time() - hours * 3600
        rows = [row for row in self._rows if row["created_at"] >= cutoff]
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(row["model"], row["kind"])].append(row)
        aggregated = [
            {
                "model": model,
                "kind": kind,
                "requests": len(items),
                "prompt_tokens": sum(item["prompt_tokens"] for item in items),
                "completion_tokens": sum(item["completion_tokens"] for item in items),
                "total_tokens": sum(item["total_tokens"] for item in items),
                "cost_usd": sum(item["cost_usd"] for item in items),
                "avg_latency_ms": statistics.fmean(item["latency_ms"] for item in items),
            }
            for (model, kind), items in grouped.items()
        ]
        aggregated.sort(key=lambda row: row["requests"], reverse=True)
        return MetricsSummary(
            requests=len(rows),
            prompt_tokens=sum(row["prompt_tokens"] for row in rows),
            completion_tokens=sum(row["completion_tokens"] for row in rows),
            total_tokens=sum(row["total_tokens"] for row in rows),
            cost_usd=sum(row["cost_usd"] for row in rows),
            avg_latency_ms=statistics.fmean(row["latency_ms"] for row in rows) if rows else 0.0,
            p95_latency_ms=_p95([row["latency_ms"] for row in rows]),
            by_model=_by_model(aggregated),
        )


_METRICS_DDL = """
CREATE TABLE IF NOT EXISTS request_metrics (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    repo TEXT NOT NULL DEFAULT '',
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
    verified BOOLEAN,
    guardrail TEXT NOT NULL DEFAULT 'allow'
);
CREATE INDEX IF NOT EXISTS request_metrics_created_idx ON request_metrics (created_at DESC);
"""


class PostgresMetricsSink(MetricsSink):
    name = "postgres"

    def __init__(self, database_url: str, min_size: int = 1, max_size: int = 3) -> None:
        self._database_url = database_url
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any = None

    async def open(self) -> None:
        if self._pool is not None:
            return
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=self._database_url,
            min_size=self._min_size,
            max_size=self._max_size,
            open=False,
            kwargs={"row_factory": dict_row},
        )
        await pool.open(wait=True, timeout=30)
        async with pool.connection() as conn:
            await conn.execute(_METRICS_DDL)
        self._pool = pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def record(
        self,
        usage: Usage,
        *,
        kind: str,
        repo: str = "",
        verified: bool | None = None,
        guardrail: str = "allow",
    ) -> None:
        await self.open()
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO request_metrics
                    (kind, model, repo, prompt_tokens, completion_tokens, total_tokens,
                     cost_usd, latency_ms, verified, guardrail)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    kind,
                    usage.model,
                    repo,
                    usage.prompt_tokens,
                    usage.completion_tokens,
                    usage.total_tokens,
                    usage.cost_usd,
                    usage.latency_ms,
                    verified,
                    guardrail,
                ),
            )

    async def summary(self, *, hours: int = 24) -> MetricsSummary:
        await self.open()
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT model,
                       kind,
                       count(*)                              AS requests,
                       coalesce(sum(prompt_tokens), 0)       AS prompt_tokens,
                       coalesce(sum(completion_tokens), 0)   AS completion_tokens,
                       coalesce(sum(total_tokens), 0)        AS total_tokens,
                       coalesce(sum(cost_usd), 0)            AS cost_usd,
                       coalesce(avg(latency_ms), 0)          AS avg_latency_ms
                FROM request_metrics
                WHERE created_at >= now() - make_interval(hours => %s)
                GROUP BY model, kind
                ORDER BY requests DESC
                """,
                (hours,),
            )
            rows = list(await cursor.fetchall())
            totals_cursor = await conn.execute(
                """
                SELECT count(*)                              AS requests,
                       coalesce(sum(prompt_tokens), 0)       AS prompt_tokens,
                       coalesce(sum(completion_tokens), 0)   AS completion_tokens,
                       coalesce(sum(total_tokens), 0)        AS total_tokens,
                       coalesce(sum(cost_usd), 0)            AS cost_usd,
                       coalesce(avg(latency_ms), 0)          AS avg_latency_ms,
                       coalesce(percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms), 0)
                                                             AS p95_latency_ms
                FROM request_metrics
                WHERE created_at >= now() - make_interval(hours => %s)
                """,
                (hours,),
            )
            totals = await totals_cursor.fetchone()
        return MetricsSummary(
            requests=int(totals["requests"]),
            prompt_tokens=int(totals["prompt_tokens"]),
            completion_tokens=int(totals["completion_tokens"]),
            total_tokens=int(totals["total_tokens"]),
            cost_usd=float(totals["cost_usd"]),
            avg_latency_ms=float(totals["avg_latency_ms"]),
            p95_latency_ms=float(totals["p95_latency_ms"]),
            by_model=_by_model(rows),
        )


@metrics_sinks.register("local")
def _build_local(settings: Settings, deps: Deps | None = None) -> MetricsSink:
    return LocalMetricsSink()


@metrics_sinks.register("postgres")
def _build_postgres(settings: Settings, deps: Deps | None = None) -> MetricsSink:
    return PostgresMetricsSink(
        database_url=settings.database_url,
        min_size=settings.db_pool_min,
        max_size=min(settings.db_pool_max, 3),
    )
