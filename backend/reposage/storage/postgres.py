"""Postgres + pgvector index: cosine similarity plus full-text keyword search."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from reposage.config import Settings
from reposage.core.plugins import Deps, index_stores
from reposage.core.text import tokenize
from reposage.domain.interfaces import IndexStore
from reposage.domain.models import Chunk, RepoSummary, ScoredChunk

_COLUMNS = "id, repo, path, start_line, end_line, language, symbol, content"

_UPSERT = f"""
INSERT INTO chunks ({_COLUMNS}, search_text, embedding)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
ON CONFLICT (id) DO UPDATE SET
    repo = EXCLUDED.repo,
    path = EXCLUDED.path,
    start_line = EXCLUDED.start_line,
    end_line = EXCLUDED.end_line,
    language = EXCLUDED.language,
    symbol = EXCLUDED.symbol,
    content = EXCLUDED.content,
    search_text = EXCLUDED.search_text,
    embedding = EXCLUDED.embedding
"""


def _vector_literal(vector: Sequence[float]) -> str:
    return json.dumps([float(value) for value in vector])


def _search_text(content: str) -> str:
    """Original text plus the pieces of identifiers, so FTS matches ``getUser``."""
    extra = " ".join(dict.fromkeys(tokenize(content)))
    return f"{content}\n{extra}"


def _to_chunk(row: dict[str, Any]) -> Chunk:
    return Chunk(
        id=row["id"],
        repo=row["repo"],
        path=row["path"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        language=row["language"],
        symbol=row["symbol"],
        content=row["content"],
    )


class PostgresIndex(IndexStore):
    name = "postgres"

    def __init__(self, database_url: str, dimensions: int, min_size: int = 1, max_size: int = 10) -> None:
        self._database_url = database_url
        self._dimensions = dimensions
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any = None

    # --- lifecycle ---------------------------------------------------------
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
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        async with pool.connection() as conn:
            await conn.execute(schema.replace("{dim}", str(self._dimensions)))
        self._pool = pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    # --- writes ------------------------------------------------------------
    async def upsert(self, repo: str, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        await self.open()
        rows = [
            (
                chunk.id,
                repo,
                chunk.path,
                chunk.start_line,
                chunk.end_line,
                chunk.language,
                chunk.symbol,
                chunk.content,
                _search_text(chunk.content),
                _vector_literal(vector),
            )
            for chunk, vector in zip(chunks, vectors)
        ]
        async with self._pool.connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.executemany(_UPSERT, rows)

    async def delete_repo(self, repo: str) -> None:
        await self.open()
        async with self._pool.connection() as conn:
            await conn.execute("DELETE FROM chunks WHERE repo = %s", (repo,))

    # --- reads -------------------------------------------------------------
    async def vector_search(self, repo: str, vector: Sequence[float], limit: int) -> list[ScoredChunk]:
        await self.open()
        literal = _vector_literal(vector)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""
                SELECT {_COLUMNS}, 1 - (embedding <=> %s::vector) AS score
                FROM chunks
                WHERE repo = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (literal, repo, literal, limit),
            )
            rows = await cursor.fetchall()
        return [ScoredChunk(chunk=_to_chunk(row), score=float(row["score"]), origins=("vector",)) for row in rows]

    async def keyword_search(self, repo: str, query: str, limit: int) -> list[ScoredChunk]:
        terms = list(dict.fromkeys(tokenize(query)))[:24]
        if not terms:
            return []
        await self.open()
        tsquery = " | ".join(terms)
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                f"""
                SELECT {_COLUMNS},
                       ts_rank_cd(to_tsvector('simple', search_text), to_tsquery('simple', %s)) AS score
                FROM chunks
                WHERE repo = %s
                  AND to_tsvector('simple', search_text) @@ to_tsquery('simple', %s)
                ORDER BY score DESC
                LIMIT %s
                """,
                (tsquery, repo, tsquery, limit),
            )
            rows = await cursor.fetchall()
        return [ScoredChunk(chunk=_to_chunk(row), score=float(row["score"]), origins=("keyword",)) for row in rows]

    async def list_repos(self) -> list[RepoSummary]:
        await self.open()
        async with self._pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT repo, count(*) AS chunks FROM chunks GROUP BY repo ORDER BY repo"
            )
            rows = await cursor.fetchall()
        return [RepoSummary(slug=row["repo"], chunks=int(row["chunks"])) for row in rows]

    async def count(self, repo: str) -> int:
        await self.open()
        async with self._pool.connection() as conn:
            cursor = await conn.execute("SELECT count(*) AS chunks FROM chunks WHERE repo = %s", (repo,))
            row = await cursor.fetchone()
        return int(row["chunks"]) if row else 0


@index_stores.register("postgres")
def _build_postgres(settings: Settings, deps: Deps | None = None) -> IndexStore:
    return PostgresIndex(
        database_url=settings.database_url,
        dimensions=settings.embedding_dim,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )
