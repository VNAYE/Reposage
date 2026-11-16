"""Framework-free domain objects shared by every layer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RepoSpec:
    """A repository to index. ``ref`` is a git ref, or a path for local sources."""

    owner: str
    name: str
    ref: str = "main"
    source: str = "github"

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"

    @classmethod
    def parse(cls, slug: str, ref: str = "main", source: str = "github") -> "RepoSpec":
        owner, _, name = slug.partition("/")
        if not owner or not name:
            raise ValueError(f"expected 'owner/name', got {slug!r}")
        return cls(owner=owner, name=name, ref=ref, source=source)

    def to_dict(self) -> dict[str, Any]:
        return {"slug": self.slug, "ref": self.ref, "source": self.source}


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: str
    content: str
    language: str


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    repo: str
    path: str
    start_line: int
    end_line: int
    language: str
    symbol: str
    content: str

    @staticmethod
    def build_id(repo: str, path: str, start_line: int, end_line: int) -> str:
        digest = hashlib.sha1(f"{repo}:{path}:{start_line}:{end_line}".encode()).hexdigest()
        return digest[:20]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
            "symbol": self.symbol,
            "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A chunk plus how it was found and how relevant it is."""

    chunk: Chunk
    score: float = 0.0
    origins: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {**self.chunk.to_dict(), "score": round(self.score, 6), "origins": list(self.origins)}


@dataclass(frozen=True, slots=True)
class Citation:
    source_id: str
    path: str
    start_line: int
    end_line: int
    symbol: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol": self.symbol,
        }


@dataclass(slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    model: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": round(self.latency_ms, 2),
            "model": self.model,
        }

    @classmethod
    def combined(cls, *usages: "Usage | None") -> "Usage":
        present = [u for u in usages if u is not None]
        return cls(
            prompt_tokens=sum(u.prompt_tokens for u in present),
            completion_tokens=sum(u.completion_tokens for u in present),
            total_tokens=sum(u.total_tokens for u in present),
            latency_ms=max((u.latency_ms for u in present), default=0.0),
            model=next((u.model for u in present if u.model), ""),
        )


@dataclass(frozen=True, slots=True)
class ChatChunk:
    text: str = ""
    usage: Usage | None = None


@dataclass(frozen=True, slots=True)
class ChatResult:
    text: str
    usage: Usage | None = None


@dataclass(frozen=True, slots=True)
class GuardrailVerdict:
    allowed: bool
    guardrail: str
    reason: str = ""
    sanitized_text: str = ""
    score: float = 0.0


@dataclass(frozen=True, slots=True)
class VerificationResult:
    supported: bool
    score: float
    verifier: str
    unsupported_claims: tuple[str, ...] = ()
    cited_sources: tuple[str, ...] = ()
    usage: Usage | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "score": round(self.score, 4),
            "verifier": self.verifier,
            "unsupported_claims": list(self.unsupported_claims),
            "cited_sources": list(self.cited_sources),
        }


@dataclass(frozen=True, slots=True)
class RepoSummary:
    slug: str
    chunks: int

    def to_dict(self) -> dict[str, Any]:
        return {"slug": self.slug, "chunks": self.chunks}


@dataclass(frozen=True, slots=True)
class IndexReport:
    repo: str
    files: int
    chunks: int
    skipped: int
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "files": self.files,
            "chunks": self.chunks,
            "skipped": self.skipped,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass(frozen=True, slots=True)
class ModelUsage:
    model: str
    kind: str
    requests: int
    total_tokens: int
    cost_usd: float
    avg_latency_ms: float


@dataclass(frozen=True, slots=True)
class MetricsSummary:
    requests: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    by_model: tuple[ModelUsage, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "by_model": [
                {
                    "model": m.model,
                    "kind": m.kind,
                    "requests": m.requests,
                    "total_tokens": m.total_tokens,
                    "cost_usd": round(m.cost_usd, 6),
                    "avg_latency_ms": round(m.avg_latency_ms, 2),
                }
                for m in self.by_model
            ],
        }
