from __future__ import annotations

from reposage.core.container import Container


async def test_index_report_counts_match_store(indexed, container: Container) -> None:
    spec, report = indexed

    assert report.files >= 5
    assert report.chunks >= 5
    assert await container.index.count(spec.slug) == report.chunks

    repos = await container.index.list_repos()
    assert any(repo.slug == spec.slug and repo.chunks == report.chunks for repo in repos)


async def test_reindexing_replaces_instead_of_duplicating(indexed, container: Container) -> None:
    spec, _ = indexed
    second = await container.indexing.index_repo(spec)

    assert await container.index.count(spec.slug) == second.chunks


async def test_ensure_indexed_is_a_noop_when_populated(indexed, container: Container) -> None:
    spec, _ = indexed
    assert await container.indexing.ensure_indexed(spec) is None


async def test_unknown_source_is_rejected(container: Container) -> None:
    from reposage.domain.models import RepoSpec

    try:
        await container.indexing.index_repo(RepoSpec(owner="a", name="b", ref=".", source="nope"))
    except ValueError as exc:
        assert "unknown repository source" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
