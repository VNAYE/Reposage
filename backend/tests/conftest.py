from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from reposage.config import Settings
from reposage.core.container import Container, build_container
from reposage.domain.models import RepoSpec
from reposage.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        chat_provider="fake",
        embedding_provider="fake",
        storage_backend="local",
        metrics_backend="local",
        local_index_path=str(tmp_path / "index.json"),
        embedding_dim=64,
        verify_answers=True,
        verifier_provider="composite",
        reranker="heuristic",
        max_chunks=200,
    )


@pytest.fixture
def container(settings: Settings) -> Container:
    return build_container(settings)


@pytest.fixture
def demo_repo() -> Path:
    return Path(__file__).resolve().parent.parent / "eval" / "fixtures" / "demo_repo"


@pytest_asyncio.fixture
async def indexed(container: Container, demo_repo: Path):
    spec = RepoSpec(owner="fixtures", name="demo_repo", ref=str(demo_repo), source="local")
    report = await container.indexing.index_repo(spec)
    return spec, report


@pytest.fixture
def client(container: Container):
    app = create_app(container.settings, container)
    with TestClient(app) as test_client:
        yield test_client
