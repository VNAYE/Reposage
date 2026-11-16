from __future__ import annotations

from pathlib import Path

from reposage.config import Settings
from reposage.core.container import build_container
from reposage.domain.models import RepoSpec
from reposage.storage.local_index import LocalIndex


async def test_index_survives_process_restart(tmp_path: Path, settings: Settings, demo_repo: Path) -> None:
    container = build_container(settings)
    spec = RepoSpec(owner="fixtures", name="demo_repo", ref=str(demo_repo), source="local")
    report = await container.indexing.index_repo(spec)
    await container.shutdown()

    reopened = LocalIndex(container.settings.local_index_path)
    await reopened.open()

    assert await reopened.count(spec.slug) == report.chunks
    assert await reopened.keyword_search(spec.slug, "validate token", 3)
    assert await reopened.vector_search(spec.slug, [0.0] * settings.embedding_dim, 3)
