"""Filesystem-backed hybrid index used for local dev, tests and the HF Space.

ponytail: every query scores all chunks of a repo in Python and the whole index
is rewritten on flush. Fine up to a few thousand chunks; Postgres is the
production path beyond that.
"""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from reposage.config import Settings
from reposage.core.plugins import Deps, index_stores
from reposage.core.text import tokenize
from reposage.domain.interfaces import IndexStore
from reposage.domain.models import Chunk, RepoSummary, ScoredChunk


@dataclass(slots=True)
class _Entry:
    chunk: Chunk
    vector: list[float]
    tokens: Counter[str]
    length: int
    norm: float


def _cosine(left: Sequence[float], right: Sequence[float], right_norm: float) -> float:
    if not left or not right or right_norm == 0.0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    if left_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


class LocalIndex(IndexStore):
    name = "local"

    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._repos: dict[str, dict[str, _Entry]] = {}
        self._dirty = False

    # --- lifecycle ---------------------------------------------------------
    async def open(self) -> None:
        if not self._path.exists():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        for repo, entries in payload.get("repos", {}).items():
            bucket: dict[str, _Entry] = {}
            for entry in entries:
                data = entry["chunk"]
                chunk = Chunk(
                    id=data["id"],
                    repo=repo,
                    path=data["path"],
                    start_line=data["start_line"],
                    end_line=data["end_line"],
                    language=data.get("language", ""),
                    symbol=data.get("symbol", ""),
                    content=data["content"],
                )
                tokens = Counter(tokenize(chunk.content))
                vector = list(entry.get("vector", []))
                bucket[chunk.id] = _Entry(
                    chunk=chunk,
                    vector=vector,
                    tokens=tokens,
                    length=sum(tokens.values()),
                    norm=math.sqrt(sum(value * value for value in vector)),
                )
            self._repos[repo] = bucket

    async def close(self) -> None:
        await self.flush()

    async def flush(self) -> None:
        if not self._dirty:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "repos": {
                repo: [
                    {"chunk": entry.chunk.to_dict(), "vector": entry.vector}
                    for entry in bucket.values()
                ]
                for repo, bucket in self._repos.items()
            },
        }
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, self._path)
        self._dirty = False

    # --- writes ------------------------------------------------------------
    async def upsert(self, repo: str, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors must have the same length")
        bucket = self._repos.setdefault(repo, {})
        for chunk, vector in zip(chunks, vectors):
            tokens = Counter(tokenize(chunk.content))
            values = list(vector)
            bucket[chunk.id] = _Entry(
                chunk=chunk,
                vector=values,
                tokens=tokens,
                length=sum(tokens.values()),
                norm=math.sqrt(sum(value * value for value in values)),
            )
        self._dirty = True

    async def delete_repo(self, repo: str) -> None:
        if self._repos.pop(repo, None) is not None:
            self._dirty = True

    # --- reads -------------------------------------------------------------
    async def vector_search(self, repo: str, vector: Sequence[float], limit: int) -> list[ScoredChunk]:
        entries = list(self._repos.get(repo, {}).values())
        scored = [
            ScoredChunk(chunk=entry.chunk, score=_cosine(vector, entry.vector, entry.norm), origins=("vector",))
            for entry in entries
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    async def keyword_search(self, repo: str, query: str, limit: int) -> list[ScoredChunk]:
        entries = list(self._repos.get(repo, {}).values())
        query_tokens = list(dict.fromkeys(tokenize(query)))
        if not entries or not query_tokens:
            return []

        document_count = len(entries)
        document_frequency = Counter(
            token for token in query_tokens if any(token in entry.tokens for entry in entries)
        )
        average_length = sum(entry.length for entry in entries) / document_count or 1.0
        k1, b = 1.5, 0.75

        scored: list[ScoredChunk] = []
        for entry in entries:
            score = 0.0
            for token in query_tokens:
                frequency = entry.tokens.get(token, 0)
                if not frequency:
                    continue
                idf = math.log(1 + (document_count - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5))
                score += idf * frequency * (k1 + 1) / (
                    frequency + k1 * (1 - b + b * entry.length / average_length)
                )
            if score > 0:
                scored.append(ScoredChunk(chunk=entry.chunk, score=score, origins=("keyword",)))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    async def list_repos(self) -> list[RepoSummary]:
        return [
            RepoSummary(slug=repo, chunks=len(bucket))
            for repo, bucket in sorted(self._repos.items())
        ]

    async def count(self, repo: str) -> int:
        return len(self._repos.get(repo, {}))


@index_stores.register("local")
def _build_local(settings: Settings, deps: Deps | None = None) -> IndexStore:
    return LocalIndex(path=settings.local_index_path)
