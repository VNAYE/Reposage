from __future__ import annotations

from reposage.core.container import Container
from reposage.domain.models import Chunk, RepoSpec, ScoredChunk


def _chunk(chunk_id: str, path: str) -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(
            id=chunk_id,
            repo="fixtures/demo_repo",
            path=path,
            start_line=1,
            end_line=3,
            language="python",
            symbol="",
            content="def example(): pass",
        ),
        score=1.0,
        origins=("seed",),
    )


async def test_hybrid_retrieval_finds_auth_file(indexed, container: Container) -> None:
    spec, _ = indexed
    hits = await container.retriever.retrieve(
        repo=spec.slug, query="How are authentication tokens validated?", limit=5
    )

    assert hits
    assert "auth.py" in [hit.chunk.path for hit in hits]
    assert any("keyword" in hit.origins for hit in hits)
    assert any("rerank" in hit.origins for hit in hits)


async def test_keyword_search_splits_identifiers(indexed, container: Container) -> None:
    spec, _ = indexed
    hits = await container.index.keyword_search(spec.slug, "retrieval_top_k", 5)

    assert hits
    assert hits[0].chunk.path == "config.py"


def test_rrf_ranks_documents_found_by_both_searches_first(container: Container) -> None:
    shared = _chunk("shared", "shared.py")
    only_vector = _chunk("vector", "vector.py")
    only_keyword = _chunk("keyword", "keyword.py")

    fused = container.retriever._fuse([shared, only_vector], [shared, only_keyword])

    assert fused[0].chunk.id == "shared"
    assert set(fused[0].origins) == {"vector", "keyword"}
    assert len(fused) == 3


async def test_unknown_repo_returns_no_hits(container: Container) -> None:
    assert await container.retriever.retrieve(repo="nobody/nothing", query="anything", limit=5) == []


async def test_retriever_works_when_embeddings_fail(container: Container, demo_repo) -> None:
    spec = RepoSpec(owner="fixtures", name="demo_repo", ref=str(demo_repo), source="local")
    await container.indexing.index_repo(spec)

    class BrokenEmbeddings:
        model = "broken"
        dimensions = 64

        async def embed_documents(self, texts):
            raise RuntimeError("boom")

        async def embed_query(self, text):
            raise RuntimeError("boom")

    container.retriever._embeddings = BrokenEmbeddings()  # type: ignore[attr-defined]
    hits = await container.retriever.retrieve(repo=spec.slug, query="token validation", limit=3)
    assert hits
