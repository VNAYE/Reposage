"""Integration test for the Postgres + pgvector adapter.

Uses pgserver (pip-installable Postgres) so it runs without Docker. Skipped
when pgserver is not installed or has no wheel for the platform.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")

from reposage.config import Settings  # noqa: E402
from reposage.core.container import build_container  # noqa: E402
from reposage.domain.models import RepoSpec  # noqa: E402


async def test_postgres_index_and_metrics(demo_repo: Path) -> None:
    server = pgserver.get_server(tempfile.mkdtemp(prefix="reposage-test-pg-"), cleanup_mode="delete")
    container = None
    try:
        settings = Settings(
            chat_provider="fake",
            embedding_provider="fake",
            storage_backend="postgres",
            metrics_backend="postgres",
            database_url=server.get_uri(),
            embedding_dim=32,
            max_chunks=50,
            verify_answers=True,
            verifier_provider="composite",
        )
        container = build_container(settings)
        await container.startup()

        spec = RepoSpec(owner="fixtures", name="demo_repo", ref=str(demo_repo), source="local")
        report = await container.indexing.index_repo(spec)

        assert await container.index.count(spec.slug) == report.chunks
        hits = await container.retriever.retrieve(repo=spec.slug, query="validate token", limit=3)
        assert hits
        assert any(hit.origins for hit in hits)

        summary = await container.metrics.summary()
        assert summary.requests >= 1
        assert summary.by_model
    finally:
        if container is not None:
            await container.shutdown()
        server.cleanup()
